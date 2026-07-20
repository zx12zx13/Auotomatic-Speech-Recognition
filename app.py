import os
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

# Bahasa dipaku ke Indonesia: tanpa ini Whisper menjalankan deteksi bahasa lebih
# dahulu, dan pada rekaman kelas yang berisik bahasa kerap salah terdeteksi --
# hasilnya transkrip kacau sekaligus proses yang lebih lambat.
BAHASA = os.getenv("WHISPER_LANGUAGE") or "id"

print(f"Memuat Whisper ({WHISPER_MODEL}) di {DEVICE.upper()}...")
whisper_model = whisper.load_model(WHISPER_MODEL, device=DEVICE)

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
def asr_pipeline(audio_file, num_speakers_val, topik="", pembicara_dinilai=1,
                 request: gr.Request = None):
    if not audio_file:
        pesan = "Tidak ada file audio."
        return pesan, pesan, pesan, pesan

    num_speakers = min(int(num_speakers_val), MAX_SPEAKERS)
    print("Mulai pipeline ASR dan Diarization...")

    # Validasi Audio: berkas yang tidak layak dihentikan di sini agar tidak
    # menimbulkan kesalahan pada tahap pemrosesan berikutnya.
    try:
        durasi_audio = validate_audio(audio_file)
    except AudioValidationError as e:
        pesan = f"❌ VALIDASI GAGAL: {e}"
        print(pesan)
        return pesan, pesan, pesan, pesan

    # Pra-pemrosesan Audio
    processed_audio = preprocess_audio(audio_file)

    dialogue = ""
    try:
        # 1. Transkripsi Whisper
        print("Mulai transkripsi Whisper...")
        result = whisper_model.transcribe(
            processed_audio,
            verbose=False,
            language=BAHASA,
            # fp16 hanya sahih di GPU; di CPU pemakaiannya justru memicu
            # peringatan dan pemrosesan mundur ke fp32.
            fp16=(DEVICE == "cuda"),
        )
        full_text = result.get("text", "Transkripsi gagal.").strip()
        print("Transkripsi Whisper selesai.")

        # 2. Diarisasi Pyannote
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
        print("Pipeline diarization selesai.")

        # 3. Pra-pemrosesan Teks (tahap [9])
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
            teks_siswa = susun_teks_pembicara(segmen_terstruktur, target)
            label = target or "seluruh pembicara"
            nlp_result = (
                f"=== TEKS HASIL PRA-PEMROSESAN ({label}) ===\n\n{teks_siswa}\n\n"
                f"=== INFORMASI ===\n"
                f"Pembicara terdeteksi: {', '.join(pembicara_ada) or '(tidak ada)'}\n"
                f"Teks di atas inilah yang dinilai oleh sistem."
            )
        print(f"Pra-pemrosesan teks selesai. Target: {target or 'semua pembicara'}")

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
                print("Mulai evaluasi LLM...")
                # Yang dinilai adalah teks hasil pra-pemrosesan milik pembicara
                # yang dievaluasi, bukan transkrip mentah seluruh pembicara.
                hasil = evaluate_response(topik, teks_siswa)
                eval_result = format_hasil(hasil)
                print(f"Evaluasi selesai. Skor akhir: {hasil['skor_akhir']}")
            except EvaluationError as e:
                eval_result = f"❌ EVALUASI GAGAL: {e}"
                print(eval_result)

        # 5. Penyimpanan ke basis data
        # Kegagalan penyimpanan tidak boleh membuang hasil yang sudah dihitung:
        # guru tetap melihat transkrip dan skor, disertai pemberitahuan bahwa
        # hasil tersebut tidak terdokumentasi.
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
                    corrected_text=teks_siswa,
                    topik=topik or None,
                    hasil_evaluasi=hasil,
                    pembicara_dinilai=target,
                )
                print(f"Hasil tersimpan ke basis data (id_audio={id_audio}).")
                eval_result += f"\n\n✅ Hasil tersimpan ke histori (ID: {id_audio})."
            except Exception as e:
                print(f"PERINGATAN: penyimpanan ke basis data GAGAL ({type(e).__name__}: {e}).")
                eval_result += (
                    f"\n\n⚠️ Hasil TIDAK tersimpan ke histori "
                    f"({type(e).__name__}). Transkrip dan skor di atas tetap sahih."
                )

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


CSS_SELARAS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&display=swap');
.gradio-container { background: #f6f3ec !important; }
#judul-modul h1 {
    font-family: 'Fraunces', Georgia, serif !important;
    font-weight: 600;
    color: #1c2a24;
    margin-bottom: 0.2rem;
}
#judul-modul p { color: #6d7a70; margin-top: 0; }
"""


def create_unified_app():
    with gr.Blocks(title="Analisis Audio") as demo:
        gr.Markdown(
            "<h1>Analisis Audio</h1>"
            "<p>Unggah atau rekam respons lisan siswa untuk transkripsi, "
            "identifikasi pembicara, dan penilaian rubrik.</p>",
            elem_id="judul-modul",
        )
        
        with gr.Row():
            with gr.Column(scale=1):
                # sources ditulis eksplisit agar tombol rekam tidak hilang bila
                # nilai bawaan Gradio berubah di versi mendatang.
                #
                # format="wav" WAJIB: rekaman mikrofon peramban dikirim sebagai
                # .webm, sedangkan validate_audio hanya menerima .wav/.mp3 --
                # sehingga rekaman langsung ditolak sebelum sempat diproses.
                audio_input = gr.Audio(
                    label="Unggah atau Rekam Audio",
                    sources=["upload", "microphone"],
                    type="filepath",
                    format="wav",
                )
                topik_input = gr.Textbox(
                    lines=3,
                    label="Topik / Pertanyaan",
                    placeholder="Contoh: Jelaskan proses fotosintesis pada tumbuhan.",
                    info="Dasar penilaian oleh sistem. Wajib diisi untuk memperoleh skor."
                )
                num_speakers_input = gr.Slider(minimum=0, maximum=MAX_SPEAKERS, step=1, value=0, label=f"Jumlah Pembicara (0 = Otomatis, maks. {MAX_SPEAKERS})")
                pembicara_input = gr.Slider(
                    minimum=0, maximum=MAX_SPEAKERS, step=1, value=1,
                    label="Pembicara yang Dinilai",
                    info="Nomor pembicara yang merupakan siswa. Isi 0 untuk menilai seluruh pembicara."
                )
                submit_btn = gr.Button(" Proses Audio", variant="primary")

            with gr.Column(scale=2):
                with gr.Tabs():
                    with gr.TabItem("Penilaian"):
                        eval_out = gr.Textbox(lines=15, label="Skor & Umpan Balik (Rubrik)")
                    with gr.TabItem("Dialog"):
                        dialogue_out = gr.Textbox(lines=15, label="Dialog Berdasarkan Pembicara")
                    with gr.TabItem("Transkrip Penuh"):
                        full_text_out = gr.Textbox(lines=15, label="Hasil Transkrip Lengkap")
                    with gr.TabItem("Pra-pemrosesan Teks"):
                        nlp_out = gr.Textbox(lines=15, label="Teks Bersih yang Dinilai Sistem")

        submit_btn.click(
            fn=asr_pipeline,
            inputs=[audio_input, num_speakers_input, topik_input, pembicara_input],
            outputs=[dialogue_out, full_text_out, nlp_out, eval_out]
        )
    return demo


if __name__ == "__main__":
    # Menjalankan modul analisis secara mandiri, terpisah dari shell FastAPI di main.py.
    # Untuk aplikasi penuh (login, dashboard, histori), gunakan: python run_server.py
    create_unified_app().launch(theme=tema_modul(), css=CSS_SELARAS)
