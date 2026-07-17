"""Modul evaluasi respons lisan siswa menggunakan Large Language Model.

Mengimplementasikan tahap [10] pipeline penelitian (§3.2.2 proposal): teks hasil
pra-pemrosesan dinilai oleh LLM berdasarkan rubrik penilaian (Tabel 3.1), lalu
menghasilkan skor per indikator dan umpan balik naratif.

Modul ini sengaja dipisahkan dari app.py agar dapat diuji secara mandiri.
"""

import os
import json

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Model dapat diganti lewat .env tanpa mengubah kode, mis. ke gemini-2.5-pro
# bila diperlukan kualitas penalaran yang lebih tinggi saat pengujian.
# Memakai `or`, bukan nilai default os.getenv: bila .env memuat baris
# "GEMINI_MODEL=" (ada tetapi kosong), os.getenv mengembalikan string kosong
# dan default TIDAK dipakai -- pemanggilan API lalu gagal "model is required".
#
# Model dipaku pada versi stabil tertentu, BUKAN alias seperti
# "gemini-flash-latest": isi alias berubah sewaktu-waktu tanpa pemberitahuan,
# dan pergantian model di tengah penelitian membuat pengukuran konsistensi
# maupun objektivitas tidak dapat direproduksi. Bila model diganti, catat
# tanggal dan versinya di laporan.
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.5-flash"

SKALA_MIN, SKALA_MAKS = 1, 4

KATEGORI_SKOR = {
    1: "Kurang",
    2: "Cukup",
    3: "Baik",
    4: "Sangat Baik",
}

# Rubrik Penilaian (Tabel 3.1 proposal) sebagai satu sumber kebenaran: dipakai
# untuk menyusun prompt sekaligus memvalidasi keluaran model. Bila rubrik di
# proposal berubah, cukup ubah di sini agar prompt ikut menyesuaikan.
RUBRIK = {
    "relevansi": {
        "nama": "Relevansi terhadap Pertanyaan",
        "deskriptor": {
            1: "Jawaban tidak menjawab pertanyaan atau keluar dari topik yang diminta.",
            2: "Jawaban masih berkaitan dengan topik, namun pembahasannya melebar dan kurang fokus.",
            3: "Jawaban sudah sesuai dengan pertanyaan, hanya terdapat sedikit bagian yang kurang fokus.",
            4: "Jawaban sepenuhnya sesuai dengan pertanyaan dan pembahasan tetap fokus pada topik.",
        },
    },
    "konsep": {
        "nama": "Ketepatan Konsep",
        "deskriptor": {
            1: "Konsep yang disampaikan salah atau menunjukkan pemahaman yang keliru.",
            2: "Terdapat beberapa kesalahan konsep yang cukup memengaruhi isi jawaban.",
            3: "Konsep yang disampaikan sebagian besar benar, hanya terdapat kesalahan kecil.",
            4: "Seluruh konsep yang disampaikan benar dan sesuai dengan materi pembelajaran.",
        },
    },
    "kelengkapan": {
        "nama": "Kelengkapan Isi",
        "deskriptor": {
            1: "Penjelasan sangat singkat dan tidak dikembangkan.",
            2: "Penjelasan sudah ada, tetapi masih kurang rinci dan belum mencakup poin penting.",
            3: "Penjelasan cukup lengkap dan sudah mencakup sebagian besar poin penting.",
            4: "Penjelasan lengkap, terstruktur, dan mencakup poin-poin penting secara jelas.",
        },
    },
    "koherensi": {
        "nama": "Koherensi dan Alur Logika",
        "deskriptor": {
            1: "Jawaban tidak runtut dan sulit diikuti alurnya.",
            2: "Alur penjelasan kurang teratur dan terdapat lompatan ide.",
            3: "Alur penjelasan cukup runtut meskipun masih ada sedikit lompatan ide.",
            4: "Jawaban tersusun secara runtut, ide saling berhubungan, dan mudah dipahami.",
        },
    },
}


class EvaluationError(Exception):
    """Evaluasi LLM gagal dan tidak menghasilkan penilaian yang sah."""
    pass


def _skema_keluaran():
    """Skema JSON yang diwajibkan kepada model.

    Memakai structured output agar keluaran tidak perlu diurai dari teks bebas,
    sehingga penilaian tidak gagal hanya karena variasi format jawaban model.
    """
    properti = {}
    for kunci in RUBRIK:
        properti[f"skor_{kunci}"] = {
            "type": "INTEGER",
            "description": f"Skor {RUBRIK[kunci]['nama']}, bilangan bulat {SKALA_MIN}-{SKALA_MAKS}.",
        }
        properti[f"alasan_{kunci}"] = {
            "type": "STRING",
            "description": f"Alasan singkat pemberian skor {RUBRIK[kunci]['nama']}.",
        }
    properti["umpan_balik"] = {
        "type": "STRING",
        "description": "Umpan balik naratif untuk siswa: apa yang sudah baik dan apa yang perlu diperbaiki.",
    }
    return {
        "type": "OBJECT",
        "properties": properti,
        "required": list(properti.keys()),
    }


def _format_rubrik():
    """Menyusun rubrik menjadi teks yang dapat dibaca model."""
    baris = []
    for kunci, isi in RUBRIK.items():
        baris.append(f"\nIndikator: {isi['nama']} (kunci: {kunci})")
        for skor in sorted(isi["deskriptor"]):
            baris.append(f"  Skor {skor} ({KATEGORI_SKOR[skor]}): {isi['deskriptor'][skor]}")
    return "\n".join(baris)


def build_prompt(topik, jawaban_siswa):
    """Menyusun prompt evaluasi sesuai struktur §3.2.2 poin 10 proposal.

    Urutan: instruksi penilaian, kriteria evaluasi, topik/soal guru, teks
    jawaban siswa, lalu format keluaran yang diharapkan.
    """
    return f"""Anda adalah evaluator yang menilai respons lisan siswa yang telah ditranskripsikan menjadi teks.

INSTRUKSI PENILAIAN:
- Nilai HANYA berdasarkan rubrik di bawah ini, jangan memakai kriteria lain.
- Nilai isi jawaban dan struktur bahasanya, bukan gaya bicara atau kefasihan.
- Teks berasal dari transkripsi otomatis, sehingga wajar bila tanda baca kurang
  rapi atau terdapat pengulangan kata. Jangan menurunkan skor karena hal itu.
- Berikan skor bilangan bulat {SKALA_MIN} sampai {SKALA_MAKS} untuk setiap indikator.
- Sertakan alasan singkat yang merujuk pada isi jawaban siswa secara spesifik.
- Bersikaplah konsisten: jawaban dengan mutu setara harus memperoleh skor setara.

KRITERIA EVALUASI (RUBRIK):
{_format_rubrik()}

TOPIK ATAU PERTANYAAN DARI GURU:
{topik.strip()}

TRANSKRIP JAWABAN SISWA:
{jawaban_siswa.strip()}

FORMAT KELUARAN:
Balas dalam format JSON sesuai skema yang diberikan, memuat skor dan alasan untuk
setiap indikator, serta umpan balik naratif yang ditujukan kepada siswa dalam
bahasa Indonesia."""


def parse_hasil(data):
    """Memvalidasi dan merapikan keluaran model menjadi hasil penilaian.

    Skor di luar skala rubrik ditolak, bukan diperbaiki diam-diam: penilaian
    yang tidak sah lebih baik terlihat daripada tersimpan sebagai angka keliru.
    """
    if not isinstance(data, dict):
        raise EvaluationError(f"Keluaran model bukan objek JSON (tipe: {type(data).__name__}).")

    hasil = {"skor": {}, "alasan": {}}
    for kunci in RUBRIK:
        medan_skor = f"skor_{kunci}"
        if medan_skor not in data:
            raise EvaluationError(f"Keluaran model tidak memuat '{medan_skor}'.")

        mentah = data[medan_skor]
        # int() memotong pecahan (int(2.5) -> 2) dan menerima bool
        # (int(True) -> 1), sehingga keduanya harus ditolak eksplisit —
        # bukan diam-diam diubah menjadi skor yang tampak sah.
        if isinstance(mentah, bool) or (
            isinstance(mentah, float) and not mentah.is_integer()
        ):
            raise EvaluationError(
                f"Skor '{kunci}' bukan bilangan bulat: {mentah!r}."
            )
        try:
            skor = int(mentah)
        except (TypeError, ValueError):
            raise EvaluationError(
                f"Skor '{kunci}' bukan bilangan bulat: {mentah!r}."
            )

        if not SKALA_MIN <= skor <= SKALA_MAKS:
            raise EvaluationError(
                f"Skor '{kunci}' = {skor} berada di luar skala rubrik "
                f"({SKALA_MIN}-{SKALA_MAKS})."
            )

        hasil["skor"][kunci] = skor
        hasil["alasan"][kunci] = str(data.get(f"alasan_{kunci}", "")).strip()

    hasil["umpan_balik"] = str(data.get("umpan_balik", "")).strip()
    # Skor akhir = rata-rata keempat indikator, tetap pada skala 1-4.
    hasil["skor_akhir"] = round(sum(hasil["skor"].values()) / len(RUBRIK), 2)
    return hasil


def evaluate_response(topik, jawaban_siswa):
    """Menilai satu respons lisan siswa dan mengembalikan skor serta umpan balik.

    Mengembalikan dict berisi: skor (per indikator), alasan (per indikator),
    skor_akhir (rata-rata), dan umpan_balik.
    """
    if not topik or not topik.strip():
        raise EvaluationError("Topik atau pertanyaan dari guru belum diisi.")
    if not jawaban_siswa or not jawaban_siswa.strip():
        raise EvaluationError("Tidak ada teks jawaban siswa yang dapat dinilai.")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EvaluationError(
            "GEMINI_API_KEY belum diatur. Salin .env.example menjadi .env, lalu isi "
            "API key dari https://aistudio.google.com/app/apikey"
        )

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(topik, jawaban_siswa)

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                # Suhu 0 agar penilaian sekonsisten mungkin antar pemanggilan;
                # konsistensi adalah tujuan utama penelitian ini.
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=_skema_keluaran(),
            ),
        )
    except Exception as e:
        raise EvaluationError(
            f"Gagal menghubungi Gemini API ({type(e).__name__}): {e}"
        ) from e

    if not getattr(response, "text", None):
        raise EvaluationError("Gemini API mengembalikan respons kosong.")

    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise EvaluationError(f"Keluaran model bukan JSON yang sah: {e}") from e

    return parse_hasil(data)


def format_hasil(hasil):
    """Menyusun hasil penilaian menjadi teks untuk ditampilkan kepada guru."""
    baris = ["=== HASIL PENILAIAN ===", ""]
    for kunci, isi in RUBRIK.items():
        skor = hasil["skor"][kunci]
        baris.append(f"{isi['nama']}: {skor} ({KATEGORI_SKOR[skor]})")
        if hasil["alasan"].get(kunci):
            baris.append(f"   Alasan: {hasil['alasan'][kunci]}")
        baris.append("")
    baris.append(f"SKOR AKHIR: {hasil['skor_akhir']} dari {SKALA_MAKS}")
    baris.append("")
    baris.append("=== UMPAN BALIK ===")
    baris.append(hasil["umpan_balik"] or "(tidak ada umpan balik)")
    return "\n".join(baris)
