import os
import warnings
import gradio as gr
import whisper
import re
from collections import Counter
from pyannote.audio import Pipeline
from pyannote.core import Segment, Annotation
import soundfile as sf
import noisereduce as nr
from pydub import AudioSegment, effects
from dotenv import load_dotenv

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
print("Memuat Whisper...")
whisper_model = whisper.load_model("medium")

print("Memuat Pyannote (diarization)...")
diarization_pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    use_auth_token=HF_TOKEN
)

print("Semua model siap.")

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

# ==============================
# NLP AUTO CORRECTION (OPTIONAL)
# ==============================
def local_nlp_processing(text):
    if not text: return "Tidak ada teks."
    kamus = {
        r"\bgak\b": "tidak", r"\bnggak\b": "tidak", r"\bkalo\b": "kalau",
        r"\byg\b": "yang", r"\bgimana\b": "bagaimana", r"\bak\b": "aku", r"\bsy\b": "saya"
    }
    corrected = text
    for p, rpl in kamus.items():
        corrected = re.sub(p, rpl, corrected, flags=re.IGNORECASE)
    words = re.findall(r"\b\w+\b", corrected.lower())
    most_common = Counter(words).most_common(5)
    output = f"--- ✅ HASIL KOREKSI ---\n{corrected}\n\n---  KATA TERBANYAK ---\n"
    for w, c in most_common:
        output += f"- {w}: {c}\n"
    return output

MIN_SPEECH_DURATION_S = 0.5

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
def asr_pipeline(audio_file, num_speakers_val):
    if not audio_file:
        return "Tidak ada file audio.", "Tidak ada file audio.", "Tidak ada file audio."

    num_speakers = min(int(num_speakers_val), MAX_SPEAKERS)
    print("Mulai pipeline ASR dan Diarization...")

    # Pra-pemrosesan Audio
    processed_audio = preprocess_audio(audio_file)

    dialogue = ""
    try:
        # 1. Transkripsi Whisper
        print("Mulai transkripsi Whisper...")
        result = whisper_model.transcribe(processed_audio, verbose=False)
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
        print("Pipeline diarization selesai.")

        # 3. Proses NLP Lokal
        nlp_result = local_nlp_processing(full_text)
        
        print("Semua proses selesai.")
        
    finally:
        # Hapus file audio yang diproses
        if processed_audio != audio_file and os.path.exists(processed_audio):
            os.remove(processed_audio)
            print(f"File sementara {processed_audio} dihapus.")

    return dialogue.strip(), full_text, nlp_result

# ==============================
# GRADIO UNIFIED INTERFACE
# ==============================
def create_unified_app():
    with gr.Blocks(title="ASR & Diarization") as demo:
        gr.Markdown("<h1 style='text-align:center'> Analisis Audio Lengkap</h1><p style='text-align:center'>Unggah file audio untuk transkripsi, identifikasi pembicara, dan analisis teks.</p>")
        
        with gr.Row():
            with gr.Column(scale=1):
                audio_input = gr.Audio(label="Upload Audio", type="filepath")
                num_speakers_input = gr.Slider(minimum=0, maximum=MAX_SPEAKERS, step=1, value=0, label=f"Jumlah Pembicara (0 = Otomatis, maks. {MAX_SPEAKERS})")
                submit_btn = gr.Button(" Proses Audio", variant="primary")
            
            with gr.Column(scale=2):
                with gr.Tabs():
                    with gr.TabItem("Dialog"):
                        dialogue_out = gr.Textbox(lines=15, label="Dialog Berdasarkan Pembicara")
                    with gr.TabItem("Transkrip Penuh"):
                        full_text_out = gr.Textbox(lines=15, label="Hasil Transkrip Lengkap")
                    with gr.TabItem("Analisis NLP"):
                        nlp_out = gr.Textbox(lines=15, label="Koreksi & Analisis Teks")

        submit_btn.click(
            fn=asr_pipeline,
            inputs=[audio_input, num_speakers_input],
            outputs=[dialogue_out, full_text_out, nlp_out]
        )
    return demo


if __name__ == "__main__":
    # Menjalankan modul analisis secara mandiri, terpisah dari shell FastAPI di main.py.
    # Untuk aplikasi penuh (login, dashboard, histori), gunakan: uvicorn main:app --reload
    create_unified_app().launch()
