import os
import re
import shutil
import time
import warnings
import gradio as gr
import torch
import whisper
from pyannote.audio import Pipeline
from pyannote.core import Segment, Annotation
import soundfile as sf
import noisereduce as nr
from pydub import AudioSegment, effects
from dotenv import load_dotenv

from evaluator import evaluate_response, format_hasil, EvaluationError
from text_preprocessing import susun_teks_pembicara, daftar_pembicara
from koreksi_fonetik import koreksi_asr_aturan
from session import id_user_dari_token
import database as db

# WAJIB untuk Windows
os.environ["SB_NO_SYMLINK"] = "1"
os.environ["TORCH_AUDIOMENTATIONS_DISABLE_WARNINGS"] = "1"

warnings.filterwarnings("ignore", category=UserWarning)

load_dotenv()

HF_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
if not HF_TOKEN:
    raise RuntimeError(
        "HUGGINGFACE_TOKEN belum diatur. Salin .env.example menjadi .env, lalu isi token "
        "dari https://huggingface.co/settings/tokens"
    )

# Batasan masalah penelitian: maksimal 5 pembicara per rekaman.
MAX_SPEAKERS = 5

# ==============================
# LOAD MODELS
# ==============================
# Memakai GPU bila tersedia. Whisper "medium" di CPU berjalan jauh lebih lambat
# daripada durasi rekamannya sendiri; di GPU prosesnya berkali-kali lipat lebih
# cepat. Deteksi otomatis, sehingga kode yang sama tetap jalan di mesin tanpa GPU.
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Ukuran model dapat diturunkan lewat .env (mis. "small") untuk mempercepat
# pengembangan. PERINGATAN: ukuran model memengaruhi mutu transkripsi, sehingga
# seluruh pengambilan data penelitian harus memakai SATU ukuran yang sama.
# Catat ukuran yang dipakai di laporan.
WHISPER_MODEL = os.getenv("WHISPER_MODEL") or "medium"
BAHASA = os.getenv("WHISPER_LANGUAGE") or "id"

loaded_whisper_models = {}

def get_whisper_model(model_name: str = None):
    if not model_name:
        model_name = WHISPER_MODEL
    if model_name not in loaded_whisper_models:
        print(f"Memuat Whisper ({model_name}) di {DEVICE.upper()}...")
        loaded_whisper_models[model_name] = whisper.load_model(model_name, device=DEVICE)
    return loaded_whisper_models[model_name]

# Pra-muat model default
whisper_model = get_whisper_model(WHISPER_MODEL)

print(f"Memuat Pyannote (diarization) di {DEVICE.upper()}...")
diarization_pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    use_auth_token=HF_TOKEN
)
diarization_pipeline.to(torch.device(DEVICE))

print("Semua model siap.")
if DEVICE == "cpu":
    print(
        "CATATAN: GPU tidak terdeteksi, proses berjalan di CPU dan akan lambat.\n"
        "         Bila mesin ini punya GPU NVIDIA, pasang PyTorch versi CUDA."
    )

# ==============================
# PYANNOTE DIARIZATION HELPER
# ==============================
def pyannote_diarization(audio_path, num_speakers):
    original_metric = "cosine"
    try:
        original_metric = diarization_pipeline.parameters(instantiated=True)["clustering"]["metric"]
    except KeyError:
        pass
    try:
        diarization_pipeline.parameters(instantiated=True)["clustering"]["metric"] = "euclidean"
        if num_speakers > 0:
            diarization = diarization_pipeline(audio_path, num_speakers=num_speakers)
        else:
            diarization = diarization_pipeline(audio_path)
    finally:
        diarization_pipeline.parameters(instantiated=True)["clustering"]["metric"] = original_metric
    return diarization

MIN_SPEECH_DURATION_S = 0.5

# ==============================
# AUDIO VALIDATION
# ==============================
SUPPORTED_AUDIO_FORMATS = (".wav", ".mp3")


class AudioValidationError(Exception):
    """Audio ditolak pada tahap validasi, sebelum masuk pra-pemrosesan."""
    pass


# Rekaman yang diunggah lewat Gradio berakhir di direktori sementara sistem
# operasi dan lenyap setelah beberapa waktu. Agar guru dapat memutar ulang
# audio dari histori dan mencocokkannya dengan transkrip, satu salinan
# disimpan di direktori tetap.
#
# PERINGATAN PRIVASI: sejak perubahan ini, suara siswa TERSIMPAN PERMANEN di
# mesin ini, bukan lagi berkas sementara. Rekaman suara adalah data pribadi.
# Sebelum pengambilan data penelitian, pastikan ada persetujuan (informed
# consent) siswa/wali, dan cantumkan penyimpanan ini pada bagian etika
# penelitian. Direktori di bawah sudah masuk .gitignore agar suara siswa tidak
# ikut terbit ke repositori publik.
DIR_REKAMAN = os.getenv("DIR_REKAMAN") or "rekaman"


def _nama_aman(nama):
    """Membersihkan nama berkas agar aman dipakai sebagai nama berkas di disk.

    Nama unggahan berasal dari pengguna dan tidak boleh dipercaya: tanpa
    pembersihan, nama seperti "../../evaluasi.db" dapat membuat penyimpanan
    menulis ke luar direktori rekaman.
    """
    nama = os.path.basename(nama or "rekaman")
    nama = re.sub(r"[^A-Za-z0-9._-]", "_", nama)
    return nama[-80:] or "rekaman"


def simpan_rekaman(audio_path):
    """Menyalin rekaman ke direktori tetap; mengembalikan lokasinya atau None.

    Kegagalan penyalinan tidak boleh membatalkan proses yang sudah berjalan:
    transkrip dan skor tetap sahih walau audionya tidak dapat diputar ulang.
    Kegagalan dilaporkan ke konsol agar tetap terlihat.
    """
    try:
        os.makedirs(DIR_REKAMAN, exist_ok=True)
        tujuan = os.path.join(
            DIR_REKAMAN, f"{int(time.time() * 1000)}_{_nama_aman(audio_path)}"
        )
        shutil.copy2(audio_path, tujuan)
        print(f"Salinan rekaman disimpan: {tujuan}")
        return tujuan
    except Exception as e:
        print(f"PERINGATAN: salinan rekaman GAGAL disimpan ({type(e).__name__}: {e}).")
        print("PERINGATAN: audio tidak akan dapat diputar ulang dari histori.")
        return None


def validate_audio(audio_path):
    """Memvalidasi berkas audio sesuai tahap [2] pipeline penelitian.

    Memeriksa keberadaan berkas, kesesuaian format, ukuran bukan 0 byte,
    keterbacaan isi berkas, serta durasi lebih dari 0 detik. Mengembalikan
    durasi rekaman dalam detik bila seluruh kriteria terpenuhi.
    """
    print("Mulai validasi audio...")

    if not audio_path or not os.path.exists(audio_path):
        raise AudioValidationError("File audio tidak ditemukan. Silakan unggah ulang.")

    ext = os.path.splitext(audio_path)[1].lower()
    if ext not in SUPPORTED_AUDIO_FORMATS:
        raise AudioValidationError(
            f"Format '{ext or 'tanpa ekstensi'}' tidak didukung. "
            f"Gunakan {' atau '.join(SUPPORTED_AUDIO_FORMATS)}."
        )

    if os.path.getsize(audio_path) == 0:
        raise AudioValidationError(
            "File audio kosong (0 byte). Silakan unggah berkas yang benar-benar berisi rekaman."
        )

    # Ekstensi yang benar tidak menjamin isi berkas benar-benar audio. Pembacaan
    # berkas di sini sekaligus menjadi pemeriksaan corrupt: berkas rusak atau
    # berkas non-audio yang disamarkan akan gagal di titik ini.
    try:
        segment = AudioSegment.from_file(audio_path)
    except Exception as e:
        raise AudioValidationError(
            f"File audio tidak dapat dibaca atau rusak (corrupt). Detail: {type(e).__name__}."
        ) from e

    duration = segment.duration_seconds
    if duration <= 0:
        raise AudioValidationError(
            "Durasi rekaman 0 detik. Silakan unggah rekaman yang berisi suara."
        )

    print(f"Validasi audio lolos: format={ext}, durasi={duration:.2f} detik")
    return duration


# ==============================
# AUDIO PRE-PROCESSING
# ==============================
def preprocess_audio(audio_path):
    print("Mulai pra-pemrosesan audio...")
    
    # 1. Noise Reduction
    print("   - Mengurangi noise...")
    try:
        data, samplerate = sf.read(audio_path)
        # Ambil channel pertama jika stereo
        if data.ndim > 1:
            data = data[:, 0]
        
        # Lakukan noise reduction
        reduced_noise_data = nr.reduce_noise(y=data, sr=samplerate)
        
        # 2. Normalisasi Volume
        print("   - Normalisasi volume...")
        # Konversi ke format yang bisa dibaca Pydub (16-bit PCM)
        normalized_data = (reduced_noise_data * 32767).astype("int16")
        
        # Buat AudioSegment dari data numpy
        audio_segment = AudioSegment(
            normalized_data.tobytes(), 
            frame_rate=samplerate,
            sample_width=normalized_data.dtype.itemsize, 
            channels=1
        )
        
        # Terapkan normalisasi
        normalized_audio = effects.normalize(audio_segment)
        
        # Simpan file yang sudah diproses
        processed_audio_path = audio_path.rsplit('.', 1)[0] + "_processed.wav"
        normalized_audio.export(processed_audio_path, format="wav")
        
        print(f"Pra-pemrosesan selesai. File disimpan di: {processed_audio_path}")
        return processed_audio_path

    except Exception as e:
        # Fallback ke audio mentah, tetapi jangan sampai kegagalan ini lolos tanpa terlihat:
        # tanpa peringatan eksplisit, seluruh hasil transkripsi bisa berasal dari audio
        # yang belum dinormalisasi maupun dibersihkan dari noise.
        print(f"PERINGATAN: pra-pemrosesan GAGAL ({type(e).__name__}: {e}).")
        print("PERINGATAN: audio diproses dalam kondisi mentah, tanpa noise reduction dan normalisasi.")
        return audio_path # Kembalikan path asli jika gagal


# ==============================
# CORE PROCESSING PIPELINE
# ==============================
def asr_pipeline(audio_file, num_speakers_val, topik="", pembicara_dinilai=1, model_name="medium",
                 request: gr.Request = None, progress=gr.Progress(track_tqdm=True)):
    if not audio_file:
        pesan = "Tidak ada file audio."
        return pesan, pesan, pesan, pesan

    num_speakers = min(int(num_speakers_val), MAX_SPEAKERS)
    print(f"Mulai pipeline ASR (Model: {model_name}) dan Diarization...")

    # Lama proses dicatat PER TAHAP, bukan hanya totalnya. Satu angka gabungan
    # tidak dapat menjawab tahap mana yang sebenarnya lambat, padahal itulah
    # yang perlu dibahas: transkripsi di CPU berjalan berkali-kali lipat lebih
    # lama daripada tahap lain, dan itu harus terbaca terpisah agar kesimpulan
    # tentang kelayakan pakai sistem tidak salah menuding tahap yang keliru.
    mulai_proses = time.perf_counter()
    waktu_tahap = {}

    def catat(nama, sejak):
        waktu_tahap[nama] = round(time.perf_counter() - sejak, 2)
        return time.perf_counter()

    # Validasi Audio: berkas yang tidak layak dihentikan di sini agar tidak
    # menimbulkan kesalahan pada tahap pemrosesan berikutnya.
    progress(0.05, desc="Memvalidasi berkas audio...")
    try:
        durasi_audio = validate_audio(audio_file)
    except AudioValidationError as e:
        pesan = f"❌ VALIDASI GAGAL: {e}"
        print(pesan)
        return pesan, pesan, pesan, pesan

    # Pra-pemrosesan Audio
    progress(0.15, desc="Pra-pemrosesan audio (noise reduction & normalisasi)...")
    processed_audio = preprocess_audio(audio_file)
    # Tahap 'audio' mencakup validasi sekaligus noise reduction dan normalisasi.
    penanda = catat("audio", mulai_proses)

    dialogue = ""
    # Tiga versi teks disimpan terpisah agar jejak pemrosesan dapat ditelusuri:
    # mentah Whisper (full_text), hasil pembersihan aturan (teks_aturan), dan
    # hasil koreksi salah dengar oleh LLM (teks_llm).
    teks_aturan = ""
    teks_llm = None
    try:
        # 1. Transkripsi Whisper
        selected_model = get_whisper_model(model_name)
        progress(0.25, desc=f"Mengonversi suara ke teks dengan Whisper ASR ({model_name})...")
        print(f"Mulai transkripsi Whisper dengan model '{model_name}'...")
        result = selected_model.transcribe(
            processed_audio,
            verbose=False,
            language=BAHASA,
            # fp16 hanya sahih di GPU; di CPU pemakaiannya justru memicu
            # peringatan dan pemrosesan mundur ke fp32.
            fp16=(DEVICE == "cuda"),
        )
        full_text = result.get("text", "Transkripsi gagal.").strip()
        penanda = catat("transcribe", penanda)
        print(f"Transkripsi Whisper selesai ({waktu_tahap['transcribe']:.1f} detik).")

        # 2. Diarisasi Pyannote
        progress(0.60, desc="Mengidentifikasi pembicara (Pyannote Diarization)...")
        print("Mulai diarization Pyannote...")
        diarization_result = pyannote_diarization(processed_audio, num_speakers)
        cleaned_diarization = Annotation(uri=diarization_result.uri)
        for turn, track, label in diarization_result.itertracks(yield_label=True):
            if turn.duration > MIN_SPEECH_DURATION_S:
                cleaned_diarization[turn, track] = label
        
        sorted_labels = sorted(cleaned_diarization.labels())
        speaker_map = {label: f"Pembicara {i+1}" for i, label in enumerate(sorted_labels)}
        
        dialogue = ""
        segmen_terstruktur = []
        for segment in result["segments"]:
            seg_start, seg_end = segment['start'], segment['end']
            speaker_durations = {}
            for turn, _, speaker_label in cleaned_diarization.itertracks(yield_label=True):
                intersection = turn & Segment(seg_start, seg_end)
                if intersection:
                    speaker_durations[speaker_label] = speaker_durations.get(speaker_label, 0) + intersection.duration

            if speaker_durations:
                dominant_speaker_label = max(speaker_durations, key=speaker_durations.get)
                speaker_name = speaker_map.get(dominant_speaker_label, "TIDAK DIKETAHUI")
            else:
                speaker_name = "TIDAK DIKETAHUI"

            dialogue += f"[{speaker_name}]: {segment['text'].strip()}\n\n"
            # Segmen disimpan terstruktur agar dapat disusun ulang menurut waktu
            # dan disaring per pembicara pada tahap pra-pemrosesan teks.
            segmen_terstruktur.append({
                "pembicara": speaker_name,
                "mulai": seg_start,
                "selesai": seg_end,
                "teks": segment['text'].strip(),
            })
        penanda = catat("diarize", penanda)
        print(f"Pipeline diarization selesai ({waktu_tahap['diarize']:.1f} detik).")

        # 3. Pra-pemrosesan Teks (tahap [9])
        progress(0.85, desc="Pra-pemrosesan teks & pemetaan dialog...")
        print("Mulai pra-pemrosesan teks...")
        pembicara_ada = daftar_pembicara(segmen_terstruktur)
        target = f"Pembicara {int(pembicara_dinilai)}" if int(pembicara_dinilai) > 0 else None

        if target and target not in pembicara_ada:
            teks_siswa = ""
            nlp_result = (
                f"⚠️ {target} tidak ditemukan dalam rekaman.\n\n"
                f"Pembicara yang terdeteksi: {', '.join(pembicara_ada) or '(tidak ada)'}\n\n"
                f"Pilih nomor pembicara yang sesuai, atau isi 0 untuk menilai seluruh pembicara."
            )
        else:
            teks_aturan = susun_teks_pembicara(segmen_terstruktur, target)
            label = target or "seluruh pembicara"

            # Koreksi salah dengar ASR berbasis aturan (Double Metaphone +
            # jarak Levenshtein atas bentuk fonetik). Teks sebelum koreksi
            # tetap ditampilkan berdampingan: koreksi yang tidak terlihat tidak
            # dapat diaudit guru, dan justru menyamarkan kesalahan transkripsi.
            progress(0.88, desc="Mengoreksi salah dengar ASR...")
            print("Mulai koreksi salah dengar ASR (berbasis aturan)...")

            koreksi = koreksi_asr_aturan(teks_aturan, topik)
            teks_siswa = koreksi["teks"]
            if koreksi["diterapkan"]:
                teks_llm = teks_siswa
            print(f"Koreksi ASR: {koreksi['catatan']}")

            daftar_ubah = "\n".join(
                f"  - {a} → {b}" for a, b in koreksi["perubahan"]
            ) or "  (tidak ada kata yang dilaporkan berubah)"

            nlp_result = (
                f"=== TEKS SEBELUM KOREKSI ({label}) ===\n\n{teks_aturan}\n\n"
                f"=== TEKS SETELAH KOREKSI ===\n\n"
                f"{teks_siswa if koreksi['diterapkan'] else '(tidak ada kata yang perlu dikoreksi)'}\n\n"
                f"=== KATA YANG DIKOREKSI ===\n{daftar_ubah}\n\n"
                f"=== INFORMASI ===\n"
                f"Status koreksi: {koreksi['catatan']}\n"
                f"Pembicara terdeteksi: {', '.join(pembicara_ada) or '(tidak ada)'}\n"
                f"Yang dinilai sistem: teks "
                f"{'SETELAH' if koreksi['diterapkan'] else 'SEBELUM'} koreksi."
            )
        penanda = catat("text", penanda)
        print(f"Pra-pemrosesan teks selesai ({waktu_tahap['text']:.2f} detik). "
              f"Target: {target or 'semua pembicara'}")

        # 4. Evaluasi LLM berbasis rubrik
        # Kegagalan evaluasi tidak boleh membatalkan transkripsi yang sudah
        # berhasil: guru tetap perlu melihat transkrip walau penilaian gagal.
        # `hasil` diinisialisasi agar tahap penyimpanan tetap aman ketika
        # evaluasi tidak dilakukan atau gagal.
        hasil = None
        if not topik or not topik.strip():
            eval_result = (
                "Topik atau pertanyaan belum diisi.\n\n"
                "Isi kolom 'Topik / Pertanyaan' lalu proses ulang untuk memperoleh "
                "skor dan umpan balik."
            )
        elif not teks_siswa:
            eval_result = (
                "❌ Tidak ada teks yang dapat dinilai.\n\n"
                "Periksa tab 'Pra-pemrosesan Teks' untuk melihat pembicara yang terdeteksi."
            )
        else:
            try:
                progress(0.92, desc="Menilai jawaban lisan dengan LLM...")
                print("Mulai evaluasi LLM...")
                # Yang dinilai adalah teks hasil pra-pemrosesan milik pembicara
                # yang dievaluasi, bukan transkrip mentah seluruh pembicara.
                hasil = evaluate_response(topik, teks_siswa)
                eval_result = format_hasil(hasil)
                print(f"Evaluasi selesai. Skor akhir: {hasil['skor_akhir']}")
            except EvaluationError as e:
                eval_result = f"❌ EVALUASI GAGAL: {e}"
                print(eval_result)
        # Dicatat di luar percabangan supaya evaluasi yang gagal maupun yang
        # dilewati tetap punya angka waktu, bukan lubang kosong di data.
        penanda = catat("evaluate", penanda)

        # 5. Penyimpanan ke basis data
        # Kegagalan penyimpanan tidak boleh membuang hasil yang sudah dihitung:
        # guru tetap melihat transkrip dan skor, disertai pemberitahuan bahwa
        # hasil tersebut tidak terdokumentasi.
        progress(0.97, desc="Menyimpan hasil ke basis data histori...")
        id_user = id_user_dari_token(request.cookies.get("session-id")) if request else None
        if id_user is None:
            eval_result += (
                "\n\n⚠️ Hasil TIDAK tersimpan: sesi login tidak terdeteksi. "
                "Buka modul ini melalui aplikasi (login terlebih dahulu) agar "
                "hasil masuk ke histori."
            )
        else:
            try:
                id_audio = db.simpan_hasil(
                    id_user=id_user,
                    filename=os.path.basename(audio_file),
                    durasi=durasi_audio,
                    segmen=segmen_terstruktur,
                    full_text=full_text,
                    corrected_text=teks_aturan,
                    llm_text=teks_llm,
                    topik=topik or None,
                    hasil_evaluasi=hasil,
                    pembicara_dinilai=target,
                    # Rekaman disalin hanya bila hasilnya benar-benar akan
                    # tersimpan; menyalin lebih awal akan meninggalkan berkas
                    # yatim di disk setiap kali sesi login tidak terdeteksi.
                    filepath=simpan_rekaman(audio_file),
                    waktu_proses=round(time.perf_counter() - mulai_proses, 1),
                    waktu_tahap=waktu_tahap,
                )
                print(f"Hasil tersimpan ke basis data (id_audio={id_audio}).")
                eval_result += f"\n\n✅ Hasil tersimpan ke histori (ID: {id_audio})."
            except Exception as e:
                print(f"PERINGATAN: penyimpanan ke basis data GAGAL ({type(e).__name__}: {e}).")
                eval_result += (
                    f"\n\n⚠️ Hasil TIDAK tersimpan ke histori "
                    f"({type(e).__name__}). Transkrip dan skor di atas tetap sahih."
                )

        progress(1.0, desc="Proses transkripsi & analisis selesai!")
        print("Semua proses selesai.")

    finally:
        # Hapus file audio yang diproses
        if processed_audio != audio_file and os.path.exists(processed_audio):
            os.remove(processed_audio)
            print(f"File sementara {processed_audio} dihapus.")

    return dialogue.strip(), full_text, nlp_result, eval_result

# ==============================
# GRADIO UNIFIED INTERFACE
# ==============================
# Tema diselaraskan dengan shell FastAPI (kertas hangat + hijau pinus) agar
# modul Gradio di dalam iframe tidak terlihat seperti aplikasi lain yang
# ditempel. PENTING: pada Gradio 6, theme/css TIDAK lagi diterima gr.Blocks
# (masuk **kwargs dan ditelan diam-diam) -- keduanya harus diberikan ke
# mount_gradio_app() (dipakai main.py) atau launch().
def tema_modul():
    return gr.themes.Soft(
        primary_hue="emerald",
        neutral_hue="stone",
        font=[gr.themes.GoogleFont("Schibsted Grotesk"), "system-ui", "sans-serif"],
        font_mono=[gr.themes.GoogleFont("Spline Sans Mono"), "Consolas", "monospace"],
    )


# Gaya modul. Memakai token yang sama dengan shell FastAPI (_tokens.css) agar
# modul di dalam iframe terbaca sebagai satu aplikasi, bukan halaman tempelan.
# Kelas yang dijadikan sasaran adalah kelas yang KITA beri sendiri lewat
# elem_classes/elem_id, bukan kelas internal Gradio, supaya gaya ini tidak
# rusak diam-diam saat Gradio diperbarui.
CSS_SELARAS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap');

:root {
    --kertas: #f6f3ec;
    --kartu: #fffdf8;
    --tinta: #1c2a24;
    --pinus: #1e5c46;
    --redup: #6d7a70;
    --garis: #e3ddcf;
    --amber: #c8722a;
    --amber-muda: #f7e8d6;
}

.gradio-container { background: var(--kertas) !important; max-width: 100% !important; }

/* Kepala modul */
#judul-modul h1 {
    font-family: 'Fraunces', Georgia, serif !important;
    font-weight: 700;
    font-size: 1.6rem;
    color: var(--tinta);
    margin: 0 0 0.25rem;
}
#judul-modul p { color: var(--redup); margin: 0; font-size: 0.92rem; }

/* Panel kiri dan kanan dijadikan kartu agar dua wilayahnya terbaca terpisah */
#panel-masukan, #panel-hasil {
    background: var(--kartu) !important;
    border: 1px solid var(--garis) !important;
    border-radius: 14px !important;
    padding: 1.1rem 1.15rem !important;
    box-shadow: 0 1px 2px rgba(28,42,36,.05), 0 4px 16px rgba(28,42,36,.04);
    align-self: flex-start;
}

/* Penanda langkah. Bernomor karena isian ini memang berurutan:
   rekaman dulu, baru topik, baru diproses. */
.langkah p {
    font-family: 'Spline Sans Mono', Consolas, monospace !important;
    font-size: 0.66rem !important;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--redup) !important;
    margin: 0.2rem 0 0.1rem !important;
}

/* Catatan peringatan tentang nomor pembicara */
.catatan-awas {
    background: var(--amber-muda);
    border-left: 3px solid var(--amber);
    border-radius: 0 8px 8px 0;
    padding: 0.6rem 0.8rem !important;
}
.catatan-awas p { font-size: 0.8rem !important; line-height: 1.55; margin: 0 !important; }

/* Tombol proses */
#tombol-proses { font-weight: 600; letter-spacing: 0.01em; }

/* Hasil penilaian */
#hasil-penilaian h2 {
    font-family: 'Fraunces', Georgia, serif !important;
    color: var(--pinus) !important;
    font-size: 1.25rem !important;
    margin: 0 0 0.7rem !important;
}
#hasil-penilaian h3 {
    font-size: 0.95rem !important;
    color: var(--tinta) !important;
    margin: 1.2rem 0 0.4rem !important;
}
#hasil-penilaian table { width: 100%; font-size: 0.88rem; }
#hasil-penilaian td, #hasil-penilaian th { padding: 0.45rem 0.6rem !important; }
#hasil-penilaian li { font-size: 0.87rem; line-height: 1.55; }

/* Footer bawaan Gradio ("Use via API", "Settings") disembunyikan: modul ini
   dipakai guru di dalam aplikasi, bukan sebagai demo yang berdiri sendiri. */
footer { display: none !important; }
"""


def create_unified_app():
    with gr.Blocks(title="Analisis Audio") as demo:
        gr.Markdown(
            "<h1>Analisis Audio</h1>"
            "<p>Unggah atau rekam respons lisan siswa untuk transkripsi, "
            "identifikasi pembicara, dan penilaian rubrik.</p>",
            elem_id="judul-modul",
        )
        
        with gr.Row(equal_height=False):
            # elem_id, bukan elem_classes: pada Gradio 6 elem_classes pada
            # gr.Column diterima tanpa keluhan tetapi tidak pernah sampai ke
            # DOM, sehingga gayanya hilang diam-diam.
            with gr.Column(scale=4, elem_id="panel-masukan"):
                gr.Markdown("Langkah 1 — Rekaman", elem_classes="langkah")
                # sources ditulis eksplisit agar tombol rekam tidak hilang bila
                # nilai bawaan Gradio berubah di versi mendatang.
                #
                # format="wav" WAJIB: rekaman mikrofon peramban dikirim sebagai
                # .webm, sedangkan validate_audio hanya menerima .wav/.mp3 --
                # sehingga rekaman langsung ditolak sebelum sempat diproses.
                audio_input = gr.Audio(
                    label="Unggah berkas .wav/.mp3 atau rekam langsung",
                    sources=["upload", "microphone"],
                    type="filepath",
                    format="wav",
                )

                gr.Markdown("Langkah 2 — Pertanyaan", elem_classes="langkah")
                topik_input = gr.Textbox(
                    lines=3,
                    label="Topik / Pertanyaan",
                    placeholder="Contoh: Jelaskan proses fotosintesis pada tumbuhan.",
                    info="Dasar penilaian sistem. Wajib diisi untuk memperoleh skor."
                )

                # Pengaturan teknis dilipat: guru cukup mengisi rekaman dan
                # pertanyaan, sementara pilihan model dan nomor pembicara jarang
                # diubah dan hanya membuat panel penuh bila selalu terbuka.
                with gr.Accordion("Pengaturan lanjutan", open=False):
                    model_input = gr.Dropdown(
                        choices=["tiny", "base", "small", "medium", "large"],
                        value=WHISPER_MODEL if WHISPER_MODEL in ["tiny", "base", "small", "medium", "large"] else "medium",
                        label="Model Whisper ASR",
                        info="Model besar lebih akurat tetapi jauh lebih lambat. "
                             "Pakai satu ukuran yang sama untuk seluruh pengambilan data."
                    )
                    num_speakers_input = gr.Slider(
                        minimum=0, maximum=MAX_SPEAKERS, step=1, value=0,
                        label="Jumlah Pembicara",
                        info=f"0 = deteksi otomatis. Maksimum {MAX_SPEAKERS}."
                    )
                    pembicara_input = gr.Slider(
                        minimum=0, maximum=MAX_SPEAKERS, step=1, value=1,
                        label="Pembicara yang Dinilai (tebakan awal)",
                        info="0 = gabungkan seluruh pembicara."
                    )
                    # Peringatannya dipisahkan dari `info` slider: sebagai satu
                    # paragraf panjang di bawah label, teks ini justru tidak
                    # terbaca. Padahal menilai orang yang keliru tetap
                    # menghasilkan skor yang tampak wajar, sehingga risikonya
                    # harus terlihat, bukan terselip.
                    gr.Markdown(
                        "**Nomor ini masih tebakan.** Urutan pembicara baru diketahui "
                        "setelah rekaman dianalisis, dan yang bicara lebih dahulu sering "
                        "kali guru. Periksa ulang di menu **Histori** — di sana rekaman "
                        "dapat diputar, peran tiap pembicara ditetapkan, dan penilaian "
                        "diulang bila nomornya keliru.\n\n"
                        "Mengisi 0 membuat ucapan guru ikut dinilai dan menaikkan skor siswa.",
                        elem_classes="catatan-awas",
                    )

                submit_btn = gr.Button(
                    "Proses Audio", variant="primary", size="lg", elem_id="tombol-proses"
                )

            with gr.Column(scale=6, elem_id="panel-hasil"):
                # Tab menggantikan dropdown pemilih tampilan. Selain lebih lazim,
                # ia menghapus penyembunyian/penampilan manual empat kotak teks
                # beserta penangan peristiwanya -- satu sumber kerumitan hilang.
                with gr.Tabs():
                    with gr.Tab("Penilaian"):
                        eval_out = gr.Markdown(
                            value=(
                                "Hasil penilaian akan muncul di sini setelah audio diproses.\n\n"
                                "Sistem menilai empat indikator rubrik pada skala 1–5, "
                                "disertai alasan tiap skor dan umpan balik untuk siswa."
                            ),
                            elem_id="hasil-penilaian",
                        )
                    with gr.Tab("Dialog per Pembicara"):
                        dialogue_out = gr.Textbox(
                            lines=20, show_label=False,
                            placeholder="Dialog yang sudah dipisahkan menurut pembicara "
                                        "akan muncul di sini.",
                        )
                    with gr.Tab("Transkrip Penuh"):
                        full_text_out = gr.Textbox(
                            lines=20, show_label=False,
                            placeholder="Transkrip mentah Whisper untuk seluruh "
                                        "pembicara akan muncul di sini.",
                        )
                    with gr.Tab("Pra-pemrosesan Teks"):
                        nlp_out = gr.Textbox(
                            lines=20, show_label=False,
                            placeholder="Teks sebelum dan sesudah koreksi salah dengar, "
                                        "beserta daftar kata yang berubah.",
                        )

        submit_btn.click(
            fn=asr_pipeline,
            inputs=[audio_input, num_speakers_input, topik_input, pembicara_input, model_input],
            outputs=[dialogue_out, full_text_out, nlp_out, eval_out]
        )
    return demo


if __name__ == "__main__":
    # Menjalankan modul analisis secara mandiri, terpisah dari shell FastAPI di main.py.
    # Untuk aplikasi penuh (login, dashboard, histori), gunakan: python run_server.py
    create_unified_app().launch(theme=tema_modul(), css=CSS_SELARAS)
