import html
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
        num_spk = int(num_speakers) if num_speakers is not None else 0
        if num_spk > 0:
            diarization = diarization_pipeline(audio_path, num_speakers=num_spk)
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
# VISUAL FORMATTING HELPERS (APPLE HIG)
# ==============================
def _format_detik(detik):
    """Format detik ke format MM:SS."""
    if detik is None:
        return "00:00"
    m = int(detik) // 60
    s = int(detik) % 60
    return f"{m:02d}:{s:02d}"


def _empty_state_html(judul: str, deskripsi: str, ikon: str = "waveform"):
    """Menghasilkan kartu empty state bergaya Apple HIG."""
    ikon_map = {
        "waveform": "🎙️",
        "chat": "💬",
        "spellcheck": "📝",
        "doc": "📄",
        "alert": "⚠️",
    }
    simbol = ikon_map.get(ikon, "🎙️")
    return f"""
    <div class="empty-state-box">
        <div class="empty-state-icon">{simbol}</div>
        <div class="empty-state-title">{html.escape(judul)}</div>
        <p class="empty-state-desc">{html.escape(deskripsi)}</p>
    </div>
    """


def _empty_state_eval_md():
    return (
        "### 📋 Menunggu Pemrosesan Audio\n\n"
        "Hasil penilaian rubrik akademik akan ditampilkan di sini setelah audio berhasil dianalisis.\n\n"
        "- **Empat Indikator Rubrik**: Relevansi, Penguasaan Konsep, Kelengkapan Jawaban, dan Koherensi/Alur.\n"
        "- **Umpan Balik Kualitatif**: Analisis kekuatan dan area peningkatan untuk siswa.\n"
        "- **Skor Otomatis**: Skala 1–4 per kriteria berlandaskan model bahasa terstruktur."
    )


def _empty_state_transcript_md():
    return (
        "### 📄 Transkrip Belum Tersedia\n\n"
        "Transkrip verbatim otomatis dari model Whisper ASR akan muncul di sini beserta durasi dan estimasi jumlah kata."
    )


def format_dialogue_html(segmen_terstruktur):
    """Menyusun segmen dialog menjadi kartu percakapan terstruktur (Apple HIG Chat Cards)."""
    if not segmen_terstruktur:
        return _empty_state_html("Belum Ada Dialog", "Dialog yang terpisah menurut giliran bicara akan tampil di sini.", "chat")

    items_html = []
    for seg in segmen_terstruktur:
        spk = seg.get("pembicara", "TIDAK DIKETAHUI")
        angka_match = re.search(r"\d+", spk)
        nomor = int(angka_match.group()) if angka_match else 1
        kelas_spk = f"badge-spk-{(nomor - 1) % 5 + 1}"
        card_spk = f"spk-card-{(nomor - 1) % 5 + 1}"

        mulai = _format_detik(seg.get("mulai", 0))
        selesai = _format_detik(seg.get("selesai", 0))
        teks = html.escape(seg.get("teks", "").strip())

        items_html.append(f"""
        <div class="dialogue-card {card_spk}">
            <div class="dialogue-header">
                <span class="speaker-badge {kelas_spk}">
                    <span class="speaker-dot"></span> {html.escape(spk)}
                </span>
                <span class="dialogue-time">{mulai} &ndash; {selesai}</span>
            </div>
            <div class="dialogue-text">{teks}</div>
        </div>
        """)

    return f'<div class="dialogue-list">{"".join(items_html)}</div>'


def format_nlp_html(pembicara_ada, target, teks_aturan, teks_siswa, koreksi):
    """Menyusun laporan koreksi fonetik dan pra-pemrosesan teks ke dalam visual report."""
    label_target = target or "Seluruh Pembicara"
    daftar_pembicara_str = ", ".join(pembicara_ada) if pembicara_ada else "(tidak ada)"

    # Kondisi jika target pembicara tidak ditemukan
    if target and target not in pembicara_ada:
        return f"""
        <div class="nlp-container">
            <div class="callout-card callout-warning">
                <div class="callout-icon">⚠️</div>
                <div class="callout-body">
                    <strong>{html.escape(target)} tidak ditemukan dalam rekaman.</strong><br>
                    Pembicara yang terdeteksi: <em>{html.escape(daftar_pembicara_str)}</em>.<br>
                    Silakan atur nomor target pembicara yang sesuai pada pengaturan lanjutan di panel kiri, atau gunakan nilai 0 untuk mengevaluasi seluruh pembicara.
                </div>
            </div>
        </div>
        """

    if not teks_siswa and not teks_aturan:
        return _empty_state_html("Belum Ada Pra-pemrosesan", "Hasil normalisasi teks dan koreksi fonetik salah dengar akan tampil di sini.", "spellcheck")

    status_koreksi = koreksi.get("catatan", "-")
    diterapkan = koreksi.get("diterapkan", False)
    perubahan = koreksi.get("perubahan", [])

    status_badge_class = "status-badge-ok" if diterapkan else "status-badge-neutral"
    status_icon = "✓" if diterapkan else "ℹ"

    # Tabel Perubahan Kata
    if perubahan:
        baris_tabel = []
        for a, b in perubahan:
            baris_tabel.append(f"""
            <tr>
                <td><span class="badge-kata-asli">{html.escape(a)}</span></td>
                <td style="text-align:center; color: var(--redup);">&rarr;</td>
                <td><span class="badge-kata-koreksi">{html.escape(b)}</span></td>
            </tr>
            """)
        tabel_html = f"""
        <div class="koreksi-section">
            <div class="section-subjudul">Daftar Kata yang Dikoreksi Secara Fonetik:</div>
            <table class="tabel-koreksi">
                <thead>
                    <tr>
                        <th>Bentuk Salah Dengar (ASR)</th>
                        <th style="width: 30px;"></th>
                        <th>Koreksi Berdasarkan Topik</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(baris_tabel)}
                </tbody>
            </table>
        </div>
        """
    else:
        tabel_html = """
        <div class="koreksi-info-box">
            <span class="info-icon">ℹ️</span> Tidak ditemukan istilah salah dengar fonetik yang perlu diperbaiki. Teks transkripsi sudah konsisten dengan leksikon topik.
        </div>
        """

    return f"""
    <div class="nlp-container">
        <div class="nlp-summary-card">
            <div class="nlp-badge-group">
                <span class="status-badge {status_badge_class}">
                    <span class="dot"></span> {status_icon} Status: {html.escape(status_koreksi)}
                </span>
                <span class="status-badge status-badge-target">
                    👤 Target Evaluasi: {html.escape(label_target)}
                </span>
            </div>
            <div class="nlp-meta-info">
                <strong>Pembicara terdeteksi:</strong> {html.escape(daftar_pembicara_str)}
            </div>
        </div>

        {tabel_html}

        <div class="nlp-compare-grid">
            <div class="compare-card">
                <div class="compare-header">
                    <span class="compare-title">Teks Sebelum Koreksi</span>
                    <span class="compare-tag">{html.escape(label_target)}</span>
                </div>
                <div class="compare-body">{html.escape(teks_aturan or "(kosong)")}</div>
            </div>
            <div class="compare-card highlight-card">
                <div class="compare-header">
                    <span class="compare-title">Teks Terkoreksi (Dinilai LLM)</span>
                    <span class="compare-tag tag-ready">Siap Evaluasi</span>
                </div>
                <div class="compare-body">{html.escape(teks_siswa or teks_aturan or "(kosong)")}</div>
            </div>
        </div>
    </div>
    """


def format_full_transcript_markdown(full_text, durasi_audio=0, model_name="medium"):
    """Menyusun tampilan transkrip penuh dengan metadata ringkas."""
    if not full_text or full_text == "Transkripsi gagal.":
        return _empty_state_transcript_md()

    jumlah_kata = len(full_text.split())
    durasi_str = _format_detik(durasi_audio)

    return f"""
<div class="transcript-meta-bar">
    <span class="meta-pill">⏱ Durasi: <strong>{durasi_str}</strong></span>
    <span class="meta-pill">📝 Total: <strong>{jumlah_kata} kata</strong></span>
    <span class="meta-pill">🤖 ASR: <strong>Whisper {model_name}</strong></span>
</div>

### Teks Transkripsi Lengkap

{full_text}
"""


# ==============================
# CORE PROCESSING PIPELINE
# ==============================
def asr_pipeline(audio_file, num_speakers_val, topik="", pembicara_dinilai=1, model_name="medium",
                 request: gr.Request = None, progress=gr.Progress(track_tqdm=True)):
    if not audio_file:
        pesan_err = "Silakan unggah berkas audio atau rekam langsung terlebih dahulu."
        return (
            _empty_state_html("Belum Ada Rekaman", pesan_err, "alert"),
            f"> ℹ️ *{pesan_err}*",
            _empty_state_html("Belum Ada Analisis", pesan_err, "alert"),
            f"### ⚠️ Peringatan\n\n{pesan_err}"
        )

    num_speakers = min(int(num_speakers_val), MAX_SPEAKERS)
    print(f"Mulai pipeline ASR (Model: {model_name}) dan Diarization...")

    mulai_proses = time.perf_counter()
    waktu_tahap = {}

    def catat(nama, sejak):
        waktu_tahap[nama] = round(time.perf_counter() - sejak, 2)
        return time.perf_counter()

    # Validasi Audio
    progress(0.05, desc="Memvalidasi berkas audio...")
    try:
        durasi_audio = validate_audio(audio_file)
    except AudioValidationError as e:
        pesan = f"Validasi gagal: {e}"
        print(f"❌ {pesan}")
        return (
            _empty_state_html("Validasi Audio Gagal", str(e), "alert"),
            f"> ⚠️ *{pesan}*",
            _empty_state_html("Validasi Audio Gagal", str(e), "alert"),
            f"### ❌ Validasi Audio Gagal\n\n{e}"
        )

    # Pra-pemrosesan Audio
    progress(0.15, desc="Pra-pemrosesan audio (noise reduction & normalisasi)...")
    processed_audio = preprocess_audio(audio_file)
    penanda = catat("audio", mulai_proses)

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

            segmen_terstruktur.append({
                "pembicara": speaker_name,
                "mulai": seg_start,
                "selesai": seg_end,
                "teks": segment['text'].strip(),
            })
        penanda = catat("diarize", penanda)
        print(f"Pipeline diarization selesai ({waktu_tahap['diarize']:.1f} detik).")

        # 3. Pra-pemrosesan Teks
        progress(0.85, desc="Pra-pemrosesan teks & pemetaan dialog...")
        print("Mulai pra-pemrosesan teks...")
        pembicara_ada = daftar_pembicara(segmen_terstruktur)
        target_val = int(pembicara_dinilai) if pembicara_dinilai is not None else 0
        target = f"Pembicara {target_val}" if target_val > 0 else None

        if target and target not in pembicara_ada:
            teks_siswa = ""
            koreksi = {
                "teks": "",
                "diterapkan": False,
                "catatan": f"{target} tidak ditemukan dalam rekaman",
                "perubahan": []
            }
        else:
            teks_aturan = susun_teks_pembicara(segmen_terstruktur, target)
            progress(0.88, desc="Mengoreksi salah dengar ASR...")
            print("Mulai koreksi salah dengar ASR (berbasis aturan)...")

            koreksi = koreksi_asr_aturan(teks_aturan, topik)
            teks_siswa = koreksi["teks"]
            if koreksi["diterapkan"]:
                teks_llm = teks_siswa
            print(f"Koreksi ASR: {koreksi['catatan']}")

        penanda = catat("text", penanda)
        print(f"Pra-pemrosesan teks selesai ({waktu_tahap['text']:.2f} detik). Target: {target or 'semua pembicara'}")

        # 4. Evaluasi LLM berbasis rubrik
        hasil = None
        if not topik or not topik.strip():
            eval_result = (
                "### ℹ️ Topik Belum Diisi\n\n"
                "Kolom **Topik / Pertanyaan** di sebelah kiri belum diisi.\n\n"
                "Silakan isi pertanyaan panduan lalu proses kembali untuk memperoleh skor rubrik dan umpan balik."
            )
        elif not teks_siswa:
            eval_result = (
                "### ❌ Tidak Ada Teks yang Dapat Dinilai\n\n"
                "Pembicara yang ditargetkan tidak memiliki ucapan dalam rekaman. "
                "Periksa tab **Koreksi Fonetik & NLP** untuk melihat daftar pembicara yang terdeteksi."
            )
        else:
            try:
                progress(0.92, desc="Menilai jawaban lisan dengan LLM...")
                print("Mulai evaluasi LLM...")
                hasil = evaluate_response(topik, teks_siswa)
                eval_result = format_hasil(hasil)
                print(f"Evaluasi selesai. Skor akhir: {hasil['skor_akhir']}")
            except EvaluationError as e:
                eval_result = f"### ❌ Evaluasi Gagal\n\n{e}"
                print(eval_result)
        penanda = catat("evaluate", penanda)

        # 5. Penyimpanan ke basis data
        progress(0.97, desc="Menyimpan hasil ke basis data histori...")
        id_user = id_user_dari_token(request.cookies.get("session-id")) if request else None
        if id_user is None:
            eval_result += (
                "\n\n> ⚠️ **Sesi Tamu**: Hasil tidak otomatis tersimpan ke histori karena belum masuk akun guru."
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
                    filepath=simpan_rekaman(audio_file),
                    waktu_proses=round(time.perf_counter() - mulai_proses, 1),
                    waktu_tahap=waktu_tahap,
                )
                print(f"Hasil tersimpan ke basis data (id_audio={id_audio}).")
                eval_result += f"\n\n> ✅ **Tersimpan ke Histori**: Rekaman dan penilaian dicatat dengan ID `{id_audio}`."
            except Exception as e:
                print(f"PERINGATAN: penyimpanan ke basis data GAGAL ({type(e).__name__}: {e}).")
                eval_result += f"\n\n> ⚠️ Hasil tidak tersimpan ke histori ({type(e).__name__}). Namun transkrip dan skor di atas tetap sah."

        # Format visual keluaran
        dialogue_html = format_dialogue_html(segmen_terstruktur)
        nlp_html = format_nlp_html(pembicara_ada, target, teks_aturan, teks_siswa, koreksi)
        full_text_md = format_full_transcript_markdown(full_text, durasi_audio, model_name)

        progress(1.0, desc="Proses transkripsi & analisis selesai!")
        print("Semua proses selesai.")

    finally:
        if processed_audio != audio_file and os.path.exists(processed_audio):
            os.remove(processed_audio)
            print(f"File sementara {processed_audio} dihapus.")

    return dialogue_html, full_text_md, nlp_html, eval_result


# ==============================
# GRADIO UNIFIED INTERFACE
# ==============================
def tema_modul():
    return gr.themes.Soft(
        primary_hue="emerald",
        neutral_hue="stone",
        font=[gr.themes.GoogleFont("Schibsted Grotesk"), "system-ui", "sans-serif"],
        font_mono=[gr.themes.GoogleFont("Spline Sans Mono"), "Consolas", "monospace"],
    )


# Gaya modul (Apple HIG + Lembar Ukur Akademik)
CSS_SELARAS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap');

:root {
    --kertas: #f6f3ec;
    --kartu: #fffdf8;
    --tinta: #1c2a24;
    --pinus: #1e5c46;
    --pinus-tua: #14402f;
    --pinus-muda: #e7efe9;
    --redup: #6d7a70;
    --garis: #e3ddcf;
    --garis-tegas: #cfc7b4;
    --amber: #c8722a;
    --amber-muda: #f7e8d6;
    --hijau-ok: #2c7a4b;
    --hijau-ok-bg: #e2f2e6;
    --merah: #a8362e;
    --merah-bg: #f8e5e2;
}

/* Kunci scrolling luar pada halaman iframe (Desktop) */
html, body {
    height: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow-x: hidden !important;
    overflow-y: hidden !important;
    background: var(--kertas) !important;
}

.gradio-container {
    background: var(--kertas) !important;
    max-width: 100% !important;
    width: 100% !important;
    height: 100vh !important;
    padding: 1rem 1.4rem !important;
    box-sizing: border-box !important;
    overflow-x: hidden !important;
    overflow-y: hidden !important;
}

/* Sembunyikan header internal Gradio karena sudah ada di shell aplikasi */
#judul-modul { display: none !important; }

/* Baris utama: flex tinggi seragam untuk desktop */
#row-utama {
    height: calc(100vh - 2rem) !important;
    min-height: 520px !important;
    gap: 1.4rem !important;
    align-items: stretch !important;
    width: 100% !important;
    max-width: 100% !important;
    box-sizing: border-box !important;
}

/* Panel Masukan (Kiri) dan Hasil (Kanan) simetris */
#panel-masukan, #panel-hasil {
    background: var(--kartu) !important;
    border: 1px solid var(--garis) !important;
    border-radius: 16px !important;
    padding: 1.25rem 1.35rem !important;
    box-shadow: 0 1px 3px rgba(28,42,36,.04), 0 4px 16px rgba(28,42,36,.03) !important;
    box-sizing: border-box !important;
    height: 100% !important;
    max-height: 100% !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-start !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    min-width: 0 !important;
}

#panel-masukan > * {
    flex-shrink: 0 !important;
    width: 100% !important;
}

#step-1-col, #step-2-col {
    padding: 0 !important;
    margin: 0 !important;
    border: none !important;
    background: transparent !important;
    width: 100% !important;
}

/* Hilangkan scrollbar horizontal pada baris tab */
.tab-nav, .tabs > div:first-child {
    scrollbar-width: none !important;
    -ms-overflow-style: none !important;
}
.tab-nav::-webkit-scrollbar, .tabs > div:first-child::-webkit-scrollbar {
    display: none !important;
}

/* Custom scrollbars halus */
#panel-masukan::-webkit-scrollbar, #panel-hasil::-webkit-scrollbar { width: 6px; }
#panel-masukan::-webkit-scrollbar-track, #panel-hasil::-webkit-scrollbar-track { background: transparent; }
#panel-masukan::-webkit-scrollbar-thumb, #panel-hasil::-webkit-scrollbar-thumb {
    background: rgba(109,122,112,0.25);
    border-radius: 6px;
}
#panel-masukan::-webkit-scrollbar-thumb:hover, #panel-hasil::-webkit-scrollbar-thumb:hover {
    background: rgba(109,122,112,0.45);
}

/* Netralkan label bawaan Gradio dari warna mint neon */
span.label-text, .block-label, label > span {
    background: var(--pinus-muda) !important;
    color: var(--pinus-tua) !important;
    border: 1px solid rgba(30, 92, 70, 0.16) !important;
    border-radius: 6px !important;
    font-size: 0.76rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    padding: 0.18rem 0.55rem !important;
}

/* Komponen Audio kompak */
.gradio-audio {
    padding: 0.2rem 0 !important;
}
.gradio-audio .upload-container, .gradio-audio [data-testid="dropzone"] {
    min-height: 80px !important;
    max-height: 105px !important;
    border: 1.5px dashed var(--garis-tegas) !important;
    background: #faf8f3 !important;
    padding: 0.5rem !important;
    border-radius: 10px !important;
}
.gradio-audio .upload-container:hover, .gradio-audio [data-testid="dropzone"]:hover {
    border-color: var(--pinus) !important;
    background: var(--pinus-muda) !important;
}
.gradio-audio [data-testid="dropzone"] p, .gradio-audio .upload-container p {
    color: var(--redup) !important;
    font-size: 0.82rem !important;
}
.gradio-audio [data-testid="dropzone"] svg, .gradio-audio .upload-container svg {
    color: var(--pinus) !important;
    width: 22px !important;
    height: 22px !important;
}
.gradio-audio [data-testid="dropzone"] span,
.gradio-audio .upload-container span,
.gradio-audio [data-testid="dropzone"] button,
.gradio-audio .upload-container button {
    color: var(--pinus) !important;
    font-weight: 600 !important;
}

/* Textbox */
textarea {
    font-size: 0.88rem !important;
    line-height: 1.45 !important;
    border: 1px solid var(--garis-tegas) !important;
    border-radius: 9px !important;
    background: #fffdf9 !important;
}
textarea:focus {
    border-color: var(--pinus) !important;
    box-shadow: 0 0 0 2px var(--pinus-muda) !important;
}

/* Segmented Stepper Tabs (Apple HIG) */
#wizard-tabs > .tab-nav, #wizard-tabs > div:first-child {
    display: flex !important;
    background: #f0ebe1 !important;
    border: 1px solid var(--garis) !important;
    border-radius: 12px !important;
    padding: 3px !important;
    margin-bottom: 0.9rem !important;
    gap: 4px !important;
}
#wizard-tabs > .tab-nav button, #wizard-tabs > div:first-child button {
    flex: 1 1 0 !important;
    text-align: center !important;
    font-size: 0.84rem !important;
    font-weight: 600 !important;
    padding: 0.42rem 0.75rem !important;
    border-radius: 8px !important;
    color: var(--redup) !important;
    background: transparent !important;
    border: none !important;
    transition: all 0.18s ease !important;
}
#wizard-tabs > .tab-nav button.selected, #wizard-tabs > div:first-child button.selected {
    color: var(--pinus-tua) !important;
    background: #ffffff !important;
    box-shadow: 0 1px 4px rgba(28,42,36,0.1) !important;
}

.step-section-header {
    margin: 0.1rem 0 0.65rem 0;
}
.step-title {
    font-size: 0.94rem;
    font-weight: 700;
    color: var(--tinta);
    margin: 0 0 0.2rem 0;
}
.step-subtitle {
    font-size: 0.8rem;
    color: var(--redup);
    margin: 0;
    line-height: 1.4;
}

/* Card Ringkasan Audio Terpilih (Langkah 2) */
#summary-header-row {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    background: var(--pinus-muda) !important;
    border: 1px solid rgba(30,92,70,0.22) !important;
    border-radius: 11px !important;
    padding: 0.45rem 0.75rem !important;
    margin-bottom: 0.75rem !important;
    gap: 8px !important;
}
.audio-summary-card {
    display: flex;
    align-items: center;
    gap: 9px;
    min-width: 0;
}
.audio-summary-card .summary-left {
    display: flex;
    align-items: center;
    gap: 9px;
    min-width: 0;
}
.audio-summary-card .summary-icon {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: var(--pinus);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.76rem;
    font-weight: 700;
    flex-shrink: 0;
}
.audio-summary-card .summary-info {
    display: flex;
    flex-direction: column;
    min-width: 0;
}
.audio-summary-card .summary-title {
    font-size: 0.68rem;
    font-weight: 700;
    color: var(--pinus-tua);
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.audio-summary-card .summary-name {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--tinta);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 170px;
}

#tombol-lanjut {
    background: linear-gradient(180deg, #246f54 0%, #1a513d 100%) !important;
    color: #fff !important;
    font-weight: 600 !important;
    font-size: 0.92rem !important;
    padding: 0.68rem 1.1rem !important;
    border-radius: 11px !important;
    border: 1px solid rgba(0,0,0,0.12) !important;
    box-shadow: 0 2px 5px rgba(26,81,61,0.2) !important;
    margin-top: 0.9rem !important;
    width: 100% !important;
    cursor: pointer !important;
    transition: all 0.18s ease-in-out !important;
}
#tombol-lanjut:hover {
    background: linear-gradient(180deg, #2b8263 0%, #1e5c46 100%) !important;
    box-shadow: 0 4px 12px rgba(26,81,61,0.26) !important;
    transform: translateY(-1px);
}

#tombol-ubah-audio {
    background: #fff !important;
    border: 1px solid rgba(30,92,70,0.3) !important;
    color: var(--pinus) !important;
    font-size: 0.74rem !important;
    padding: 0.28rem 0.65rem !important;
    border-radius: 7px !important;
    font-weight: 600 !important;
    flex-shrink: 0;
    cursor: pointer !important;
}
#tombol-ubah-audio:hover {
    background: var(--pinus-muda) !important;
    border-color: var(--pinus) !important;
}

/* Accordion Parameter (Apple HIG Disclosure) */
.gradio-accordion, [data-testid="accordion"] {
    border: 1px solid var(--garis) !important;
    border-radius: 12px !important;
    background: #fbf9f4 !important;
    margin: 0.75rem 0 0.4rem 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}
.gradio-accordion > .label-wrap, [data-testid="accordion"] > .label-wrap {
    padding: 0.6rem 0.85rem !important;
    background: #fbf9f4 !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    color: var(--tinta) !important;
}
.gradio-accordion[open] > .label-wrap, [data-testid="accordion"][open] > .label-wrap {
    border-bottom: 1px solid var(--garis) !important;
    background: #f5f0e4 !important;
}

/* Tombol Proses Utama (Taktil, selalu terlihat) */
#tombol-proses {
    background: linear-gradient(180deg, #246f54 0%, #1a513d 100%) !important;
    color: #fff !important;
    font-weight: 600 !important;
    font-size: 0.94rem !important;
    padding: 0.7rem 1.2rem !important;
    border-radius: 11px !important;
    border: 1px solid rgba(0,0,0,0.12) !important;
    box-shadow: 0 2px 5px rgba(26,81,61,0.22) !important;
    cursor: pointer !important;
    transition: all 0.18s ease-in-out !important;
    margin: 0.9rem 0 0.5rem 0 !important;
    width: 100% !important;
}
#tombol-proses:hover {
    background: linear-gradient(180deg, #2b8263 0%, #1e5c46 100%) !important;
    box-shadow: 0 4px 12px rgba(26,81,61,0.28) !important;
    transform: translateY(-1px);
}
#tombol-proses:active {
    transform: translateY(0);
    box-shadow: 0 1px 3px rgba(26,81,61,0.2) !important;
}

/* Callout Catatan */
.callout-card {
    display: flex;
    gap: 9px;
    background: var(--amber-muda);
    border-left: 3px solid var(--amber);
    border-radius: 0 8px 8px 0;
    padding: 0.65rem 0.85rem;
    margin: 0.5rem 0;
    font-size: 0.8rem;
    line-height: 1.45;
    color: var(--tinta);
}
.callout-warning {
    background: #fdf5e8;
    border-left-color: var(--amber);
}
.callout-icon { font-size: 1.05rem; line-height: 1; flex-shrink: 0; }
.callout-body { flex: 1; }

/* Navigasi Tab: selalu berjejer horizontal tanpa menu dropdown '...' */
.tab-nav, .tabs > div:first-child {
    display: flex !important;
    flex-wrap: nowrap !important;
    overflow-x: auto !important;
    gap: 4px !important;
    border-bottom: 1.5px solid var(--garis) !important;
    padding-bottom: 0.35rem !important;
    margin-bottom: 0.85rem !important;
}
.tab-nav button, .tabs > div:first-child button {
    flex: 1 1 auto !important;
    white-space: nowrap !important;
    padding: 0.5rem 0.75rem !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
    color: var(--redup) !important;
    background: transparent !important;
    border: none !important;
    transition: all 0.15s ease !important;
}
.tab-nav button.selected, .tabs > div:first-child button.selected {
    color: var(--pinus-tua) !important;
    background: var(--pinus-muda) !important;
    border-bottom: 2px solid var(--pinus) !important;
}

/* Hilangkan tombol dropdown tiga titik bawaan Gradio */
.tab-nav + button, .tab-nav [aria-label="More tabs"], .tab-dropdown, [data-testid="overflow-menu"], button[aria-label="More tabs"] {
    display: none !important;
    visibility: hidden !important;
    width: 0 !important;
    height: 0 !important;
    pointer-events: none !important;
}

/* Empty States */
.empty-state-box {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2.8rem 1.2rem;
    text-align: center;
    color: var(--redup);
}
.empty-state-icon {
    width: 44px;
    height: 44px;
    border-radius: 12px;
    background: var(--pinus-muda);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.3rem;
    margin-bottom: 0.8rem;
}
.empty-state-title {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 600;
    font-size: 1.05rem;
    color: var(--tinta);
    margin: 0 0 0.3rem 0;
}
.empty-state-desc {
    font-size: 0.85rem;
    max-width: 340px;
    line-height: 1.5;
    margin: 0;
    color: var(--redup);
}

/* Hasil Penilaian */
#hasil-penilaian h2 {
    font-family: 'Fraunces', Georgia, serif !important;
    color: var(--pinus) !important;
    font-size: 1.3rem !important;
    margin: 0 0 0.8rem !important;
    padding-bottom: 0.45rem;
    border-bottom: 1px solid var(--garis);
}
#hasil-penilaian h3 {
    font-family: 'Fraunces', Georgia, serif !important;
    font-size: 1rem !important;
    color: var(--tinta) !important;
    margin: 1.2rem 0 0.45rem !important;
}
#hasil-penilaian table {
    width: 100%;
    border-collapse: collapse;
    margin: 0.7rem 0 1.1rem;
    font-size: 0.88rem;
    background: var(--kartu);
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid var(--garis);
}
#hasil-penilaian th {
    background: var(--pinus-muda);
    color: var(--pinus);
    font-family: 'Spline Sans Mono', Consolas, monospace;
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 0.5rem 0.75rem !important;
    border-bottom: 1px solid var(--garis);
}
#hasil-penilaian td {
    padding: 0.6rem 0.75rem !important;
    border-bottom: 1px solid var(--garis);
    color: var(--tinta);
}
#hasil-penilaian tr:last-child td { border-bottom: none; }
#hasil-penilaian blockquote {
    border-left: 3px solid var(--pinus);
    background: var(--pinus-muda);
    margin: 0.9rem 0;
    padding: 0.65rem 0.9rem;
    border-radius: 0 8px 8px 0;
    font-size: 0.86rem;
}

/* Dialog Pembicara */
.dialogue-list {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
    padding: 0.3rem 0;
}
.dialogue-card {
    background: #fbf9f4;
    border: 1px solid var(--garis);
    border-radius: 11px;
    padding: 0.8rem 1rem;
    transition: border-color 0.18s, box-shadow 0.18s;
}
.dialogue-card:hover {
    border-color: var(--garis-tegas);
    box-shadow: 0 2px 6px rgba(28,42,36,0.04);
}
.dialogue-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.4rem;
}
.speaker-badge {
    font-size: 0.72rem;
    font-weight: 600;
    padding: 0.18rem 0.6rem;
    border-radius: 20px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
.speaker-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
}
.badge-spk-1 { background: var(--pinus-muda); color: var(--pinus); border: 1px solid rgba(30,92,70,0.2); }
.badge-spk-2 { background: var(--amber-muda); color: var(--amber); border: 1px solid rgba(200,114,42,0.2); }
.badge-spk-3 { background: #e8ecf4; color: #2b4c7e; border: 1px solid rgba(43,76,126,0.2); }
.badge-spk-4 { background: #f3e8f4; color: #7e2b7a; border: 1px solid rgba(126,43,122,0.2); }
.badge-spk-5 { background: #e8f4f2; color: #2b7e72; border: 1px solid rgba(43,126,114,0.2); }

.spk-card-1 { border-left: 3.5px solid var(--pinus); }
.spk-card-2 { border-left: 3.5px solid var(--amber); }
.spk-card-3 { border-left: 3.5px solid #2b4c7e; }
.spk-card-4 { border-left: 3.5px solid #7e2b7a; }
.spk-card-5 { border-left: 3.5px solid #2b7e72; }

.dialogue-time {
    font-family: 'Spline Sans Mono', Consolas, monospace;
    font-size: 0.68rem;
    color: var(--redup);
    background: rgba(109,122,112,0.08);
    padding: 0.12rem 0.4rem;
    border-radius: 5px;
}
.dialogue-text {
    color: var(--tinta);
    font-size: 0.9rem;
    line-height: 1.55;
    margin: 0;
}

/* Koreksi Fonetik */
.nlp-container {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding: 0.25rem 0;
}
.nlp-summary-card {
    background: #fbf9f4;
    border: 1px solid var(--garis);
    border-radius: 11px;
    padding: 0.85rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}
.nlp-badge-group {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    align-items: center;
}
.status-badge {
    font-size: 0.72rem;
    font-weight: 600;
    padding: 0.22rem 0.6rem;
    border-radius: 20px;
    display: inline-flex;
    align-items: center;
    gap: 5px;
}
.status-badge-ok { background: var(--hijau-ok-bg); color: var(--hijau-ok); }
.status-badge-neutral { background: var(--pinus-muda); color: var(--pinus); }
.status-badge-target { background: var(--amber-muda); color: var(--amber); }
.nlp-meta-info { font-size: 0.8rem; color: var(--redup); }

.koreksi-section { margin-top: 0.15rem; }
.section-subjudul {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--tinta);
    margin-bottom: 0.4rem;
}
.tabel-koreksi {
    width: 100%;
    border-collapse: collapse;
    border: 1px solid var(--garis);
    border-radius: 8px;
    overflow: hidden;
    font-size: 0.84rem;
    background: var(--kartu);
}
.tabel-koreksi th {
    background: rgba(30,92,70,0.06);
    color: var(--redup);
    font-family: 'Spline Sans Mono', Consolas, monospace;
    font-size: 0.68rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 0.45rem 0.7rem;
    text-align: left;
    border-bottom: 1px solid var(--garis);
}
.tabel-koreksi td {
    padding: 0.5rem 0.7rem;
    border-bottom: 1px solid var(--garis);
}
.badge-kata-asli {
    background: var(--merah-bg);
    color: var(--merah);
    padding: 0.16rem 0.45rem;
    border-radius: 5px;
    font-family: 'Spline Sans Mono', Consolas, monospace;
    font-size: 0.78rem;
}
.badge-kata-koreksi {
    background: var(--hijau-ok-bg);
    color: var(--hijau-ok);
    font-weight: 600;
    padding: 0.16rem 0.45rem;
    border-radius: 5px;
    font-family: 'Spline Sans Mono', Consolas, monospace;
    font-size: 0.78rem;
}
.koreksi-info-box {
    background: var(--pinus-muda);
    color: var(--pinus-tua);
    padding: 0.7rem 0.9rem;
    border-radius: 8px;
    font-size: 0.82rem;
    line-height: 1.5;
}

.nlp-compare-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.85rem;
}
@media (max-width: 900px) {
    .nlp-compare-grid { grid-template-columns: 1fr; }
}
.compare-card {
    background: #fbf9f4;
    border: 1px solid var(--garis);
    border-radius: 9px;
    padding: 0.8rem 0.95rem;
    display: flex;
    flex-direction: column;
}
.highlight-card {
    border-color: rgba(30,92,70,0.3);
    background: #f9fbf9;
}
.compare-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.45rem;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid var(--garis);
}
.compare-title {
    font-size: 0.76rem;
    font-weight: 600;
    color: var(--tinta);
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.compare-tag {
    font-size: 0.68rem;
    background: rgba(109,122,112,0.1);
    color: var(--redup);
    padding: 0.1rem 0.42rem;
    border-radius: 4px;
    font-family: 'Spline Sans Mono', Consolas, monospace;
}
.tag-ready {
    background: var(--hijau-ok-bg);
    color: var(--hijau-ok);
    font-weight: 600;
}
.compare-body {
    font-size: 0.86rem;
    line-height: 1.5;
    color: var(--tinta);
    white-space: pre-wrap;
}

/* Transkrip Lengkap */
.transcript-meta-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin-bottom: 0.9rem;
    padding-bottom: 0.7rem;
    border-bottom: 1px solid var(--garis);
}
.meta-pill {
    font-size: 0.72rem;
    background: rgba(109,122,112,0.08);
    color: var(--tinta);
    padding: 0.22rem 0.6rem;
    border-radius: 6px;
    font-family: 'Spline Sans Mono', Consolas, monospace;
}

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

        with gr.Row(equal_height=True, elem_id="row-utama"):
            # Panel Masukan (Kiri) - Progressive Disclosure Stepper (Apple HIG)
            with gr.Column(scale=4, elem_id="panel-masukan", min_width=0):
                with gr.Tabs(elem_id="wizard-tabs") as wizard_tabs:
                    # --- LANGKAH 1: INPUT AUDIO ---
                    with gr.Tab("1. Audio Siswa", id="tab-audio"):
                        gr.HTML("""
                        <div class="step-section-header">
                            <h3 class="step-title">Unggah atau Rekam Audio</h3>
                            <p class="step-subtitle">Pilih berkas rekaman lisan (.wav / .mp3) atau rekam mikrofon secara langsung.</p>
                        </div>
                        """)
                        audio_input = gr.Audio(
                            label="Berkas Audio (.wav / .mp3) atau Rekam Mikrofon",
                            sources=["upload", "microphone"],
                            type="filepath",
                            format="wav",
                        )
                        btn_ke_step_2 = gr.Button(
                            "Lanjut: Atur Pertanyaan Rubrik →",
                            variant="primary",
                            size="lg",
                            elem_id="tombol-lanjut"
                        )

                    # --- LANGKAH 2: RINGKASAN AUDIO + PERTANYAAN & PARAMETER ---
                    with gr.Tab("2. Topik & Evaluasi", id="tab-topik"):
                        with gr.Row(elem_id="summary-header-row"):
                            audio_summary_html = gr.HTML(
                                value="""
                                <div class="audio-summary-card">
                                    <div class="summary-left">
                                        <span class="summary-icon">✓</span>
                                        <div class="summary-info">
                                            <span class="summary-title">Berkas Audio Terpilih</span>
                                            <span class="summary-name">Siap dianalisis</span>
                                        </div>
                                    </div>
                                </div>
                                """,
                                elem_id="audio-summary-content"
                            )
                            btn_ubah_audio = gr.Button(
                                "↺ Ganti Audio",
                                size="sm",
                                variant="secondary",
                                elem_id="tombol-ubah-audio"
                            )

                        gr.HTML("""
                        <div class="step-section-header">
                            <h3 class="step-title">Topik / Pertanyaan Evaluasi</h3>
                            <p class="step-subtitle">Dasar penilaian LLM terhadap rubrik konten lisan siswa.</p>
                        </div>
                        """)
                        topik_input = gr.Textbox(
                            lines=2,
                            label="Pertanyaan Guru (Rubrik)",
                            placeholder="Contoh: Jelaskan tahapan proses fotosintesis pada tumbuhan hijau.",
                            info="Dasar penilaian LLM terhadap rubrik konten lisan siswa."
                        )

                        submit_btn = gr.Button(
                            "▶ Proses Analisis Audio", variant="primary", size="lg", elem_id="tombol-proses"
                        )

                        with gr.Accordion("⚙️ Pengaturan Lanjutan (Model & Pembicara)", open=False):
                            model_input = gr.Dropdown(
                                choices=["tiny", "base", "small", "medium", "large"],
                                value=WHISPER_MODEL if WHISPER_MODEL in ["tiny", "base", "small", "medium", "large"] else "medium",
                                label="Model Whisper ASR",
                                info="Model medium seimbang antara akurasi leksikal dan waktu proses."
                            )
                            num_speakers_input = gr.Dropdown(
                                choices=[
                                    ("0 — Deteksi Otomatis (Bawaan)", 0),
                                    ("1 Pembicara (Monolog)", 1),
                                    ("2 Pembicara (Tanya Jawab)", 2),
                                    ("3 Pembicara", 3),
                                    ("4 Pembicara", 4),
                                    ("5 Pembicara (Maksimum)", 5),
                                ],
                                value=0,
                                label="Jumlah Pembicara",
                                info="0 = Sistem mendeteksi otomatis batas giliran tiap orang yang berbicara."
                            )
                            pembicara_input = gr.Dropdown(
                                choices=[
                                    ("0 — Seluruh Pembicara Digabung", 0),
                                    ("Pembicara 1 (Target Evaluasi Siswa)", 1),
                                    ("Pembicara 2", 2),
                                    ("Pembicara 3", 3),
                                    ("Pembicara 4", 4),
                                    ("Pembicara 5", 5),
                                ],
                                value=1,
                                label="Nomor Pembicara yang Dinilai",
                                info="Pilih nomor urut pembicara yang ucapannya akan dinilai oleh rubrik LLM."
                            )
                            gr.HTML("""
                            <div class="callout-card callout-warning">
                                <div class="callout-icon">💡</div>
                                <div class="callout-body">
                                    <strong>Tips Pembicara:</strong> Urutan nomor pembicara terdeteksi otomatis. Bila rekaman diawali pertanyaan guru, sesuaikan nomor target atau atur di menu <strong>Histori</strong>.
                                </div>
                            </div>
                            """)

            # Panel Hasil (Kanan)
            with gr.Column(scale=6, elem_id="panel-hasil", min_width=0):
                with gr.Tabs():
                    with gr.Tab("Penilaian", id="tab-penilaian"):
                        eval_out = gr.Markdown(
                            value=_empty_state_eval_md(),
                            elem_id="hasil-penilaian",
                        )
                    with gr.Tab("Dialog", id="tab-dialog"):
                        dialogue_out = gr.HTML(
                            value=_empty_state_html("Belum Ada Dialog", "Dialog terpisah per pembicara beserta waktu bicara akan tampil di sini setelah audio diproses.", "chat"),
                            elem_id="hasil-dialog",
                        )
                    with gr.Tab("Koreksi Fonetik", id="tab-nlp"):
                        nlp_out = gr.HTML(
                            value=_empty_state_html("Belum Ada Analisis NLP", "Laporan koreksi salah dengar dan audit teks siswa akan ditampilkan di sini.", "spellcheck"),
                            elem_id="hasil-nlp",
                        )
                    with gr.Tab("Transkrip", id="tab-transkrip"):
                        full_text_out = gr.Markdown(
                            value=_empty_state_transcript_md(),
                            elem_id="hasil-transkrip",
                        )

        # Navigasi Antar-Langkah (Bebas Bug Gradio)
        def ke_langkah_2(audio):
            if not audio:
                gr.Warning("Silakan unggah atau rekam audio siswa terlebih dahulu.")
                return gr.Tabs(selected="tab-audio"), gr.update()
            nama_file = os.path.basename(audio) if isinstance(audio, str) else "Rekaman Audio"
            summary_html = f"""
            <div class="audio-summary-card">
                <div class="summary-left">
                    <span class="summary-icon">✓</span>
                    <div class="summary-info">
                        <span class="summary-title">Berkas Audio Terpilih</span>
                        <span class="summary-name" title="{html.escape(nama_file)}">{html.escape(nama_file)}</span>
                    </div>
                </div>
            </div>
            """
            return gr.Tabs(selected="tab-topik"), summary_html

        def kembali_ke_langkah_1():
            return gr.Tabs(selected="tab-audio")

        btn_ke_step_2.click(
            fn=ke_langkah_2,
            inputs=[audio_input],
            outputs=[wizard_tabs, audio_summary_html]
        )
        btn_ubah_audio.click(
            fn=kembali_ke_langkah_1,
            outputs=[wizard_tabs]
        )

        submit_btn.click(
            fn=asr_pipeline,
            inputs=[audio_input, num_speakers_input, topik_input, pembicara_input, model_input],
            outputs=[dialogue_out, full_text_out, nlp_out, eval_out]
        )
    return demo


if __name__ == "__main__":
    create_unified_app().launch(theme=tema_modul(), css=CSS_SELARAS)

