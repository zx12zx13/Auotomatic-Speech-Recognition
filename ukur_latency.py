"""Pengukuran waktu proses (latency) dan Real-Time Factor (RTF) per modul.

Melaksanakan Tabel 3.9 proposal (§3.2.5.6). Skrip ini MENGULANG tahapan yang
sama persis dengan `asr_pipeline()` di app.py, tetapi menyisipkan pencatatan
`time.perf_counter()` di setiap batas tahap sehingga waktu tiap modul dapat
dipisahkan.

    python ukur_latency.py rekaman/*.wav --topik "Sistem Komputer"

Keluaran: tabel per rekaman + rata-rata, disimpan ke `hasil_latency.csv`.

Catatan kejujuran data: skrip ini hanya MENGUKUR. Bila satu tahap gagal,
waktunya dilaporkan apa adanya beserta status gagal — bukan diisi perkiraan.
"""

import argparse
import csv
import glob
import os
import statistics
import sys
import time

# Pemuatan model terjadi saat app.py diimpor; waktunya dicatat terpisah sebagai
# biaya awal (startup) yang hanya dibayar sekali per proses server, bukan per
# rekaman. Mencampurnya ke waktu per rekaman akan melebih-lebihkan latency.
_t0 = time.perf_counter()
import app  # noqa: E402
from pyannote.core import Segment, Annotation  # noqa: E402
from text_preprocessing import susun_teks_pembicara, daftar_pembicara  # noqa: E402
from koreksi_fonetik import koreksi_asr_aturan  # noqa: E402
from evaluator import evaluate_response, EvaluationError  # noqa: E402
WAKTU_MUAT_MODEL = time.perf_counter() - _t0

TAHAP = [
    ("validasi", "Validasi audio"),
    ("prapemrosesan", "Pra-pemrosesan audio (normalisasi + noise reduction)"),
    ("transkripsi", "Transkripsi ASR (Whisper)"),
    ("diarisasi", "Speaker diarization (Pyannote)"),
    ("penyelarasan", "Penyelarasan segmen-pembicara"),
    ("prateks", "Pra-pemrosesan teks + koreksi fonetik"),
    ("evaluasi", "Evaluasi LLM (Gemini)"),
]


def ukur_satu(audio_path, topik, pembicara_dinilai, num_speakers, model_name):
    """Menjalankan pipeline penuh untuk satu rekaman, mencatat waktu tiap tahap."""
    t = {}
    catatan = []
    mulai_total = time.perf_counter()

    # [1] Validasi audio
    a = time.perf_counter()
    durasi_audio = app.validate_audio(audio_path)
    t["validasi"] = time.perf_counter() - a

    # [2] Pra-pemrosesan audio
    a = time.perf_counter()
    processed = app.preprocess_audio(audio_path)
    t["prapemrosesan"] = time.perf_counter() - a
    if processed == audio_path:
        catatan.append("pra-pemrosesan gagal, audio mentah dipakai")

    # [3] Transkripsi Whisper
    a = time.perf_counter()
    model = app.get_whisper_model(model_name)
    hasil_asr = model.transcribe(
        processed, verbose=False, language=app.BAHASA, fp16=(app.DEVICE == "cuda")
    )
    t["transkripsi"] = time.perf_counter() - a
    full_text = hasil_asr.get("text", "").strip()

    # [4] Diarisasi Pyannote
    a = time.perf_counter()
    diarization = app.pyannote_diarization(processed, num_speakers)
    t["diarisasi"] = time.perf_counter() - a

    # [5] Penyelarasan segmen ASR dengan label pembicara
    a = time.perf_counter()
    bersih = Annotation(uri=diarization.uri)
    for turn, track, label in diarization.itertracks(yield_label=True):
        if turn.duration > app.MIN_SPEECH_DURATION_S:
            bersih[turn, track] = label
    label_urut = sorted(bersih.labels())
    peta = {lab: f"Pembicara {i + 1}" for i, lab in enumerate(label_urut)}

    segmen = []
    for seg in hasil_asr["segments"]:
        awal, akhir = seg["start"], seg["end"]
        durasi_per_pembicara = {}
        for turn, _, lab in bersih.itertracks(yield_label=True):
            irisan = turn & Segment(awal, akhir)
            if irisan:
                durasi_per_pembicara[lab] = (
                    durasi_per_pembicara.get(lab, 0) + irisan.duration
                )
        if durasi_per_pembicara:
            dominan = max(durasi_per_pembicara, key=durasi_per_pembicara.get)
            nama = peta.get(dominan, "TIDAK DIKETAHUI")
        else:
            nama = "TIDAK DIKETAHUI"
        segmen.append(
            {
                "pembicara": nama,
                "mulai": awal,
                "selesai": akhir,
                "teks": seg["text"].strip(),
            }
        )
    t["penyelarasan"] = time.perf_counter() - a

    # [6] Pra-pemrosesan teks + koreksi fonetik
    a = time.perf_counter()
    ada = daftar_pembicara(segmen)
    target = f"Pembicara {pembicara_dinilai}" if pembicara_dinilai > 0 else None
    if target and target not in ada:
        catatan.append(f"{target} tidak terdeteksi; dinilai seluruh pembicara")
        target = None
    teks_aturan = susun_teks_pembicara(segmen, target)
    koreksi = koreksi_asr_aturan(teks_aturan, topik)
    teks_siswa = koreksi["teks"]
    t["prateks"] = time.perf_counter() - a

    # [7] Evaluasi LLM
    a = time.perf_counter()
    skor = None
    if not topik.strip() or not teks_siswa:
        catatan.append("evaluasi dilewati (topik/teks kosong)")
        t["evaluasi"] = 0.0
    else:
        try:
            hasil_eval = evaluate_response(topik, teks_siswa)
            skor = hasil_eval["skor_akhir"]
            t["evaluasi"] = time.perf_counter() - a
        except EvaluationError as e:
            t["evaluasi"] = time.perf_counter() - a
            catatan.append(f"evaluasi GAGAL: {e}")

    total = time.perf_counter() - mulai_total

    if processed != audio_path and os.path.exists(processed):
        os.remove(processed)

    return {
        "berkas": os.path.basename(audio_path),
        "durasi_audio": durasi_audio,
        "jumlah_pembicara": len(label_urut),
        "jumlah_segmen": len(segmen),
        "jumlah_kata": len(full_text.split()),
        "skor": skor,
        "total": total,
        "rtf": total / durasi_audio if durasi_audio else float("nan"),
        "catatan": "; ".join(catatan) or "-",
        **{k: t.get(k, float("nan")) for k, _ in TAHAP},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("audio", nargs="+", help="Berkas audio (boleh pola glob)")
    p.add_argument("--topik", default="", help="Topik/pertanyaan untuk evaluasi LLM")
    p.add_argument("--pembicara", type=int, default=0, help="Nomor pembicara dinilai (0 = semua)")
    p.add_argument("--num-speakers", type=int, default=0, help="0 = biarkan model menentukan")
    p.add_argument("--model", default=app.WHISPER_MODEL, help="Model Whisper")
    p.add_argument("--ulang", type=int, default=1, help="Jumlah pengulangan per rekaman")
    p.add_argument("--keluaran", default="hasil_latency.csv")
    args = p.parse_args()

    berkas = []
    for pola in args.audio:
        cocok = sorted(glob.glob(pola))
        berkas.extend(cocok if cocok else [pola])
    berkas = [b for b in berkas if os.path.isfile(b)]
    if not berkas:
        sys.exit("Tidak ada berkas audio yang ditemukan.")

    print(f"Perangkat        : {app.DEVICE}")
    print(f"Model Whisper    : {args.model}")
    print(f"Waktu muat model : {WAKTU_MUAT_MODEL:.2f} detik (sekali per proses)")
    print(f"Jumlah rekaman   : {len(berkas)} x {args.ulang} pengulangan\n")

    baris = []
    for b in berkas:
        for i in range(args.ulang):
            print(f"--- {os.path.basename(b)} (ulangan {i + 1}/{args.ulang}) ---")
            hasil = ukur_satu(b, args.topik, args.pembicara, args.num_speakers, args.model)
            hasil["ulangan"] = i + 1
            baris.append(hasil)
            print(
                f"    durasi audio {hasil['durasi_audio']:.1f}s | "
                f"total {hasil['total']:.1f}s | RTF {hasil['rtf']:.2f}\n"
            )

    kolom = ["berkas", "ulangan", "durasi_audio", "jumlah_pembicara", "jumlah_segmen",
             "jumlah_kata", "skor"] + [k for k, _ in TAHAP] + ["total", "rtf", "catatan"]
    with open(args.keluaran, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=kolom)
        w.writeheader()
        w.writerows(baris)

    print("=" * 78)
    print(f"{'Modul':<48}{'Rerata (s)':>12}{'RTF':>10}")
    print("-" * 78)
    total_durasi = sum(r["durasi_audio"] for r in baris)
    for kunci, nama in TAHAP:
        nilai = [r[kunci] for r in baris if r[kunci] == r[kunci]]
        if not nilai:
            continue
        rer = statistics.mean(nilai)
        rtf = sum(nilai) / total_durasi
        print(f"{nama:<48}{rer:>12.2f}{rtf:>10.3f}")
    print("-" * 78)
    tot = [r["total"] for r in baris]
    print(f"{'Total end-to-end':<48}{statistics.mean(tot):>12.2f}"
          f"{sum(tot) / total_durasi:>10.3f}")
    print("=" * 78)
    print(f"\nRincian per rekaman disimpan ke: {args.keluaran}")


if __name__ == "__main__":
    main()
