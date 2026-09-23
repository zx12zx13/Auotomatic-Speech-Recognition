import os
import json
import urllib.request
import urllib.error

from dotenv import load_dotenv

load_dotenv()

# Konfigurasi LLM API
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or "https://9router-iaak.srv1746580.hstgr.cloud/v1"
LLM_API_KEY = os.getenv("LLM_API_KEY") or "sk-0f575f000c66e733-md7mx7-b9655e47"
LLM_MODEL = os.getenv("LLM_MODEL") or "FreeCoder"

# Kunci cadangan di atas tertulis langsung di kode. Repositori penelitian ini
# publik, sehingga kunci akan ikut terbit ke internet pada commit berikutnya
# bila tidak dipindahkan ke .env lebih dahulu. Peringatan sengaja dicetak agar
# masalah ini terlihat, bukan tersamar -- lihat BUG-02 yang serupa.
if not os.getenv("LLM_API_KEY"):
    # Tanpa emoji: konsol Windows memakai cp1252 dan akan melempar
    # UnicodeEncodeError, sehingga peringatan justru menghentikan aplikasi.
    print(
        "PERINGATAN: LLM_API_KEY tidak ditemukan di .env, sistem memakai "
        "kunci cadangan yang tertulis di evaluator.py.\n"
        "            Pindahkan LLM_API_KEY, LLM_BASE_URL, dan LLM_MODEL ke "
        ".env sebelum melakukan commit berikutnya."
    )

# Skala rubrik. SATU-SATUNYA tempat skala didefinisikan: objektivitas.py dan
# modul lain mengimpornya dari sini. Sebelumnya skala ditulis ulang di
# objektivitas.py, dan bila keduanya berbeda, Quadratic Weighted Kappa akan
# memakai jumlah kategori yang keliru lalu menghasilkan angka yang salah tanpa
# satu pun pesan galat.
SKALA_MIN, SKALA_MAKS = 1, 5

KATEGORI_SKOR = {
    1: "Sangat Kurang",
    2: "Kurang",
    3: "Cukup",
    4: "Baik",
    5: "Sangat Baik",
}

# Rubrik Penilaian (Tabel 3.1 proposal) sebagai satu sumber kebenaran: dipakai
# untuk menyusun prompt sekaligus memvalidasi keluaran model. Bila rubrik di
# proposal berubah, cukup ubah di sini agar prompt ikut menyesuaikan.
RUBRIK = {
    "relevansi": {
        "nama": "Relevansi terhadap Pertanyaan",
        "deskriptor": {
            1: "Jawaban tidak menjawab pertanyaan atau keluar dari topik yang diminta.",
            2: "Jawaban hanya menyinggung topik sekilas, sebagian besar isinya di luar pertanyaan.",
            3: "Jawaban masih berkaitan dengan topik, namun pembahasannya melebar dan kurang fokus.",
            4: "Jawaban sudah sesuai dengan pertanyaan, hanya terdapat sedikit bagian yang kurang fokus.",
            5: "Jawaban sepenuhnya sesuai dengan pertanyaan dan pembahasan tetap fokus pada topik.",
        },
    },
    "konsep": {
        "nama": "Ketepatan Konsep",
        "deskriptor": {
            1: "Konsep yang disampaikan salah atau menunjukkan pemahaman yang keliru.",
            2: "Sebagian besar konsep keliru, hanya sedikit bagian yang benar.",
            3: "Terdapat beberapa kesalahan konsep yang cukup memengaruhi isi jawaban.",
            4: "Konsep yang disampaikan sebagian besar benar, hanya terdapat kesalahan kecil.",
            5: "Seluruh konsep yang disampaikan benar dan sesuai dengan materi pembelajaran.",
        },
    },
    "kelengkapan": {
        "nama": "Kelengkapan Isi",
        "deskriptor": {
            1: "Penjelasan sangat singkat dan tidak dikembangkan.",
            2: "Hanya menyebutkan poin tanpa penjelasan yang berarti.",
            3: "Penjelasan sudah ada, tetapi masih kurang rinci dan belum mencakup poin penting.",
            4: "Penjelasan cukup lengkap dan sudah mencakup sebagian besar poin penting.",
            5: "Penjelasan lengkap, terstruktur, dan mencakup poin-poin penting secara jelas.",
        },
    },
    "koherensi": {
        "nama": "Koherensi dan Alur Logika",
        "deskriptor": {
            1: "Jawaban tidak runtut dan sulit diikuti alurnya.",
            2: "Terdapat banyak lompatan ide sehingga alurnya sulit diikuti.",
            3: "Alur penjelasan kurang teratur dan terdapat lompatan ide.",
            4: "Alur penjelasan cukup runtut meskipun masih ada sedikit lompatan ide.",
            5: "Jawaban tersusun secara runtut, ide saling berhubungan, dan mudah dipahami.",
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
Keluarkan HANYA JSON murni (tanpa teks tambahan dan tanpa ```json markdown block) dengan skema berikut:
{{
  "skor_relevansi": <integer 1-4>,
  "alasan_relevansi": "<string>",
  "skor_konsep": <integer 1-4>,
  "alasan_konsep": "<string>",
  "skor_kelengkapan": <integer 1-4>,
  "alasan_kelengkapan": "<string>",
  "skor_koherensi": <integer 1-4>,
  "alasan_koherensi": "<string>",
  "umpan_balik": "<string>"
}}"""


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
    hasil["skor_akhir"] = round(sum(hasil["skor"].values()) / len(RUBRIK), 2)
    return hasil


def _lepas_pagar_kode(teks):
    """Membuang pembungkus ```json ... ``` bila model menyertakannya."""
    teks = (teks or "").strip()
    if not teks.startswith("```"):
        return teks
    baris = teks.splitlines()
    if baris and baris[0].startswith("```"):
        baris = baris[1:]
    if baris and baris[-1].strip() == "```":
        baris = baris[:-1]
    return "\n".join(baris).strip()


def panggil_llm(pesan, temperature=0.0, timeout=60):
    """Mengirim daftar pesan ke API LLM dan mengembalikan isi jawabannya.

    Dipakai bersama oleh evaluasi rubrik dan koreksi transkrip ASR
    (`text_preprocessing.koreksi_asr_llm`) agar konfigurasi endpoint hanya
    berada di satu tempat: bila endpoint berpindah, hanya satu berkas berubah.

    `temperature` dipatok 0.0 secara bawaan karena penelitian ini mengklaim
    hasil yang konsisten -- pemanggilan tidak boleh mengandung keacakan.
    """
    api_key = os.getenv("LLM_API_KEY") or LLM_API_KEY
    base_url = os.getenv("LLM_BASE_URL") or LLM_BASE_URL
    model_name = os.getenv("LLM_MODEL") or LLM_MODEL

    if not api_key:
        raise EvaluationError("LLM_API_KEY belum diatur.")

    payload = {
        "model": model_name,
        "messages": pesan,
        "temperature": temperature,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_json = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise EvaluationError(f"Gagal menghubungi API LLM ({type(e).__name__}): {e}") from e

    try:
        return _lepas_pagar_kode(resp_json["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as e:
        raise EvaluationError(
            f"Format respons LLM API tidak valid ({type(e).__name__}): {resp_json}"
        ) from e


def evaluate_response(topik, jawaban_siswa):
    """Menilai satu respons lisan siswa dan mengembalikan skor serta umpan balik.

    Mengembalikan dict berisi: skor (per indikator), alasan (per indikator),
    skor_akhir (rata-rata), dan umpan_balik.
    """
    if not topik or not topik.strip():
        raise EvaluationError("Topik atau pertanyaan dari guru belum diisi.")
    if not jawaban_siswa or not jawaban_siswa.strip():
        raise EvaluationError("Tidak ada teks jawaban siswa yang dapat dinilai.")

    prompt = build_prompt(topik, jawaban_siswa)
    pesan = [
        {
            "role": "system",
            "content": "Anda adalah evaluator rubrik respons lisan siswa. Keluarkan SELALU dalam format JSON mentah yang sah tanpa penjelasan atau markdown block ```json."
        },
        {"role": "user", "content": prompt},
    ]

    content_text = panggil_llm(pesan)

    try:
        data = json.loads(content_text)
    except json.JSONDecodeError as e:
        raise EvaluationError(f"Keluaran model bukan JSON yang sah: {e}. Teks mentah: {content_text}") from e

    return parse_hasil(data)


def format_hasil(hasil):
    """Menyusun hasil penilaian menjadi Markdown untuk ditampilkan kepada guru.

    Memakai Markdown, bukan teks berpembatas '===', supaya skor terbaca sebagai
    tabel dan bukan sebagai keluaran konsol. Guru membaca hasil ini untuk
    mengambil keputusan tentang nilai siswa; keterbacaannya bagian dari mutu
    sistem, bukan hiasan.
    """
    baris = [
        f"## Skor Akhir: {hasil['skor_akhir']} dari {SKALA_MAKS}",
        "",
        "| Indikator | Skor | Kategori |",
        "|---|:---:|---|",
    ]
    for kunci, isi in RUBRIK.items():
        skor = hasil["skor"][kunci]
        baris.append(f"| {isi['nama']} | **{skor}** | {KATEGORI_SKOR[skor]} |")

    alasan = [(isi["nama"], hasil["alasan"].get(kunci))
              for kunci, isi in RUBRIK.items() if hasil["alasan"].get(kunci)]
    if alasan:
        baris += ["", "### Alasan Penilaian", ""]
        baris += [f"- **{nama}** — {teks}" for nama, teks in alasan]

    baris += ["", "### Umpan Balik untuk Siswa", ""]
    baris.append(hasil["umpan_balik"] or "_(tidak ada umpan balik)_")
    return "\n".join(baris)
