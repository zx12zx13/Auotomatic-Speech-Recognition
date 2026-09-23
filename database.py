"""Modul basis data sistem evaluasi respons lisan.

Mengimplementasikan skema pada §3.2.3.3 proposal (Gambar 3.13, Tabel 3.2-3.8).

Basis data menyimpan hasil antara (pembicara, transkrip, segmen), bukan hanya
skor akhir, agar proses evaluasi dapat ditelusuri kembali, diverifikasi, serta
dianalisis apabila terjadi kesalahan penilaian.
"""

import os
import sqlite3
from datetime import datetime

import bcrypt
from dotenv import load_dotenv

# Skala rubrik berasal dari evaluator.py agar hanya ada satu sumber kebenaran.
from evaluator import SKALA_MAKS

load_dotenv()

# Memakai `or`, bukan nilai default os.getenv: bila .env memuat baris
# "DB_PATH=" (ada tetapi kosong), os.getenv mengembalikan string kosong.
# sqlite3.connect("") DIAM-DIAM membuat basis data sementara yang terhapus
# saat koneksi ditutup -- seluruh hasil evaluasi akan hilang meski sistem
# melaporkan penyimpanan berhasil.
DB_PATH = os.getenv("DB_PATH") or "evaluasi.db"

# Skema mengikuti Tabel 3.2-3.8 proposal. Tabel assessment diberi kolom skor
# per indikator karena rubrik memiliki 4 indikator, sedangkan proposal hanya
# menyediakan satu kolom `score`. Tanpa ini, analisis objektivitas per
# indikator (RM #2) tidak dapat dilakukan. Relasi antar tabel tidak berubah.
SKEMA = """
CREATE TABLE IF NOT EXISTS user (
    id_user    INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL UNIQUE,
    password   TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audio (
    id_audio        INTEGER PRIMARY KEY AUTOINCREMENT,
    id_user         INTEGER NOT NULL,
    filename        TEXT NOT NULL,
    filepath        TEXT,
    duration        REAL,
    processing_time REAL,
    time_audio      REAL,
    time_transcribe REAL,
    time_diarize    REAL,
    time_text       REAL,
    time_evaluate   REAL,
    uploaded_at     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'diproses',
    FOREIGN KEY (id_user) REFERENCES user(id_user)
);

CREATE TABLE IF NOT EXISTS speaker (
    id_speaker     INTEGER PRIMARY KEY AUTOINCREMENT,
    id_audio       INTEGER NOT NULL,
    speaker_label  TEXT NOT NULL,
    role           TEXT,
    total_duration REAL DEFAULT 0,
    FOREIGN KEY (id_audio) REFERENCES audio(id_audio)
);

CREATE TABLE IF NOT EXISTS transcript (
    id_transcript  INTEGER PRIMARY KEY AUTOINCREMENT,
    id_audio       INTEGER NOT NULL,
    full_text      TEXT,
    corrected_text TEXT,
    llm_text       TEXT,
    edited_text    TEXT,
    edited_at      TEXT,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (id_audio) REFERENCES audio(id_audio)
);

CREATE TABLE IF NOT EXISTS segment (
    id_segment    INTEGER PRIMARY KEY AUTOINCREMENT,
    id_speaker    INTEGER NOT NULL,
    id_transcript INTEGER NOT NULL,
    start_time    REAL,
    end_time      REAL,
    text          TEXT,
    FOREIGN KEY (id_speaker) REFERENCES speaker(id_speaker),
    FOREIGN KEY (id_transcript) REFERENCES transcript(id_transcript)
);

CREATE TABLE IF NOT EXISTS assessment (
    id_assessment     INTEGER PRIMARY KEY AUTOINCREMENT,
    id_audio          INTEGER NOT NULL,
    id_speaker        INTEGER,
    id_user           INTEGER NOT NULL,
    topik             TEXT,
    score             REAL,
    skala_maks        INTEGER,
    score_relevansi   INTEGER,
    score_konsep      INTEGER,
    score_kelengkapan INTEGER,
    score_koherensi   INTEGER,
    feedback          TEXT,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (id_audio) REFERENCES audio(id_audio),
    FOREIGN KEY (id_speaker) REFERENCES speaker(id_speaker),
    FOREIGN KEY (id_user) REFERENCES user(id_user)
);
"""


def get_conn():
    """Membuka koneksi basis data dengan foreign key diaktifkan.

    SQLite mematikan penegakan foreign key secara bawaan, sehingga harus
    dinyalakan di setiap koneksi agar relasi antar tabel benar-benar dijaga.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Kolom yang ditambahkan setelah basis data penelitian mulai terisi. CREATE
# TABLE IF NOT EXISTS tidak mengubah tabel yang sudah ada, sehingga kolom baru
# harus ditambahkan terpisah agar basis data lama ikut terbarui tanpa
# kehilangan data yang sudah terkumpul.
KOLOM_TAMBAHAN = [
    ("transcript", "llm_text", "TEXT"),
    # Lama pemrosesan satu rekaman (detik). Berbeda dari `duration` yang
    # merupakan panjang rekamannya sendiri: yang satu sifat berkasnya, yang
    # lain biaya komputasi sistem. Keduanya perlu terpisah karena laporan
    # penelitian menyebut waktu proses sebagai indikator kelayakan pakai.
    ("audio", "processing_time", "REAL"),
    # Suntingan manual guru atas transkrip. Ditaruh di kolom SENDIRI, tidak
    # menimpa corrected_text/llm_text: bila keluaran sistem ditimpa hasil
    # suntingan, tidak ada lagi cara membuktikan apa yang sebenarnya
    # dihasilkan sistem, dan seluruh pengukuran akurasi ASR kehilangan
    # rujukan.
    ("transcript", "edited_text", "TEXT"),
    ("transcript", "edited_at", "TEXT"),
    # Peran tiap pembicara (Guru/Siswa/Lainnya), ditetapkan guru setelah
    # mendengarkan rekaman. Diarisasi hanya mengelompokkan suara dan tidak
    # tahu siapa yang bicara, sehingga "Pembicara 1" adalah nomor klaster,
    # bukan peran. Tanpa kolom ini tidak ada cara memastikan sistem menilai
    # jawaban siswa, bukan pertanyaan gurunya.
    ("speaker", "role", "TEXT"),
    # Lama tiap tahap, dipisahkan dari total. Proposal §3.2.5 mewajibkan
    # pengukuran waktu proses; satu angka gabungan tidak dapat menjawab tahap
    # mana yang sebenarnya lambat, sehingga tidak berguna untuk pembahasan.
    ("audio", "time_audio", "REAL"),
    ("audio", "time_transcribe", "REAL"),
    ("audio", "time_diarize", "REAL"),
    ("audio", "time_text", "REAL"),
    ("audio", "time_evaluate", "REAL"),
    # Skala rubrik yang berlaku saat penilaian dibuat. WAJIB dicatat: skala
    # penelitian ini pernah berubah dari 1-4 menjadi 1-5, dan skor 4 pada dua
    # skala itu bukan nilai yang sama. Tanpa kolom ini, data lama dan baru akan
    # tercampur dalam satu perhitungan dan hasilnya tidak sah.
    ("assessment", "skala_maks", "INTEGER"),
]

# Peran yang boleh disimpan. Dibatasi agar isian bebas tidak menghasilkan
# ejaan beragam ("guru", "Guru ", "GURU") yang membuat peringatan salah nilai
# tidak pernah menyala.
PERAN_GURU = "Guru"
PERAN_SISWA = "Siswa"
PERAN_LAINNYA = "Lainnya"
PERAN_SAH = (PERAN_GURU, PERAN_SISWA, PERAN_LAINNYA)


def _migrasi(conn):
    """Menambahkan kolom baru pada basis data yang dibuat versi sebelumnya."""
    for tabel, kolom, tipe in KOLOM_TAMBAHAN:
        ada = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabel})")}
        if kolom in ada:
            continue
        conn.execute(f"ALTER TABLE {tabel} ADD COLUMN {kolom} {tipe}")
        print(f"Migrasi: kolom {tabel}.{kolom} ditambahkan.")

        if (tabel, kolom) == ("assessment", "skala_maks"):
            # Diisi HANYA pada saat kolomnya baru dibuat, ketika seluruh baris
            # yang ada dipastikan berasal dari masa skala 1-4. Menjalankannya
            # di lain waktu berisiko menandai baris skala 1-5 sebagai 1-4.
            cur = conn.execute(
                "UPDATE assessment SET skala_maks = 4 WHERE skala_maks IS NULL"
            )
            if cur.rowcount:
                print(
                    f"Migrasi: {cur.rowcount} penilaian lama ditandai berskala 1-4.\n"
                    f"         Penilaian baru memakai skala 1-{SKALA_MAKS}. Keduanya "
                    f"TIDAK boleh digabung dalam satu perhitungan."
                )


def init_db():
    """Membuat seluruh tabel bila belum ada, lalu menjalankan migrasi kolom."""
    with get_conn() as conn:
        conn.executescript(SKEMA)
        _migrasi(conn)
    print(f"Basis data siap: {DB_PATH}")


def _sekarang():
    return datetime.now().isoformat(timespec="seconds")


# ==============================
# USER
# ==============================
def buat_user(username, password):
    """Mendaftarkan pengguna baru dengan kata sandi ter-hash.

    Mengembalikan id_user. Melempar ValueError bila username sudah dipakai.
    """
    if not username or not username.strip():
        raise ValueError("Username tidak boleh kosong.")
    if not password:
        raise ValueError("Password tidak boleh kosong.")

    # Kata sandi disimpan sebagai hash bcrypt, tidak pernah dalam bentuk polos.
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    try:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO user (username, password, created_at) VALUES (?, ?, ?)",
                (username.strip(), hashed.decode("utf-8"), _sekarang()),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("Username sudah digunakan.")


def verifikasi_user(username, password):
    """Memeriksa kredensial. Mengembalikan id_user bila cocok, None bila tidak.

    Sengaja tidak membedakan 'username tidak ada' dan 'password salah' agar
    tidak membocorkan daftar pengguna terdaftar.
    """
    if not username or not password:
        return None

    with get_conn() as conn:
        row = conn.execute(
            "SELECT id_user, password FROM user WHERE username = ?", (username.strip(),)
        ).fetchone()

    if not row:
        return None
    if bcrypt.checkpw(password.encode("utf-8"), row["password"].encode("utf-8")):
        return row["id_user"]
    return None


def ambil_user(id_user):
    with get_conn() as conn:
        return conn.execute(
            "SELECT id_user, username, created_at FROM user WHERE id_user = ?", (id_user,)
        ).fetchone()


# ==============================
# PENYIMPANAN HASIL EVALUASI
# ==============================
def simpan_hasil(id_user, filename, durasi, segmen, full_text, corrected_text,
                 topik=None, hasil_evaluasi=None, pembicara_dinilai=None,
                 filepath=None, llm_text=None, waktu_proses=None, waktu_tahap=None):
    """Menyimpan satu proses evaluasi secara bertahap dalam satu transaksi.

    Urutan penyimpanan mengikuti alur proposal: audio -> speaker -> transcript
    -> segment -> assessment. Seluruhnya dalam satu transaksi agar tidak ada
    hasil setengah jadi bila terjadi kegagalan di tengah.

    Argumen:
        segmen: daftar dict berisi 'pembicara', 'mulai', 'selesai', 'teks'.
        full_text: transkrip mentah Whisper, seluruh pembicara.
        corrected_text: teks pembicara yang dinilai setelah pembersihan
            berbasis aturan.
        llm_text: teks setelah koreksi salah dengar oleh LLM, atau None bila
            koreksi tidak dilakukan/ditolak. Disimpan terpisah dari
            corrected_text agar perubahan yang dibuat LLM dapat ditelusuri;
            tanpa itu, koreksi tidak dapat dipertanggungjawabkan.
        hasil_evaluasi: dict keluaran evaluator.evaluate_response, atau None
            bila evaluasi tidak dilakukan/gagal.
        pembicara_dinilai: label pembicara yang dinilai, mis. "Pembicara 1".
        filepath: lokasi salinan rekaman yang disimpan sistem, agar guru dapat
            memutar ulang audionya dari histori dan mencocokkannya dengan
            transkrip. None bila rekaman tidak disalin.
        waktu_proses: lama SELURUH pemrosesan dalam detik.
        waktu_tahap: dict lama tiap tahap dalam detik, dengan kunci 'audio',
            'transcribe', 'diarize', 'text', dan 'evaluate'. Dipisahkan dari
            waktu_proses karena satu angka gabungan tidak dapat menjawab tahap
            mana yang lambat, sedangkan itulah yang dibahas pada laporan.

    Mengembalikan id_audio.
    """
    segmen = segmen or []
    tahap = waktu_tahap or {}
    with get_conn() as conn:
        # 1. audio
        cur = conn.execute(
            "INSERT INTO audio (id_user, filename, filepath, duration,"
            " processing_time, time_audio, time_transcribe, time_diarize,"
            " time_text, time_evaluate, uploaded_at, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (id_user, filename, filepath, durasi, waktu_proses,
             tahap.get("audio"), tahap.get("transcribe"), tahap.get("diarize"),
             tahap.get("text"), tahap.get("evaluate"), _sekarang(), "selesai"),
        )
        id_audio = cur.lastrowid

        # 2. speaker - total durasi bicara dihitung dari segmen
        durasi_pembicara = {}
        for s in segmen:
            label = s.get("pembicara")
            if not label:
                continue
            lama = (s.get("selesai", 0) or 0) - (s.get("mulai", 0) or 0)
            durasi_pembicara[label] = durasi_pembicara.get(label, 0) + max(lama, 0)

        peta_speaker = {}
        for label, total in sorted(durasi_pembicara.items()):
            cur = conn.execute(
                "INSERT INTO speaker (id_audio, speaker_label, total_duration)"
                " VALUES (?, ?, ?)",
                (id_audio, label, round(total, 2)),
            )
            peta_speaker[label] = cur.lastrowid

        # 3. transcript
        cur = conn.execute(
            "INSERT INTO transcript (id_audio, full_text, corrected_text, llm_text, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (id_audio, full_text, corrected_text, llm_text, _sekarang()),
        )
        id_transcript = cur.lastrowid

        # 4. segment
        for s in segmen:
            id_speaker = peta_speaker.get(s.get("pembicara"))
            if id_speaker is None:
                continue
            conn.execute(
                "INSERT INTO segment (id_speaker, id_transcript, start_time, end_time, text)"
                " VALUES (?, ?, ?, ?, ?)",
                (id_speaker, id_transcript, s.get("mulai"), s.get("selesai"), s.get("teks")),
            )

        # 5. assessment - hanya bila evaluasi menghasilkan penilaian sah
        if hasil_evaluasi:
            skor = hasil_evaluasi.get("skor", {})
            conn.execute(
                "INSERT INTO assessment (id_audio, id_speaker, id_user, topik, score,"
                " skala_maks, score_relevansi, score_konsep, score_kelengkapan,"
                " score_koherensi, feedback, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id_audio,
                    peta_speaker.get(pembicara_dinilai),
                    id_user,
                    topik,
                    hasil_evaluasi.get("skor_akhir"),
                    SKALA_MAKS,
                    skor.get("relevansi"),
                    skor.get("konsep"),
                    skor.get("kelengkapan"),
                    skor.get("koherensi"),
                    hasil_evaluasi.get("umpan_balik"),
                    _sekarang(),
                ),
            )

    return id_audio


# ==============================
# QUERY HISTORI
# ==============================
def statistik_user(id_user):
    """Menghitung ringkasan untuk kartu statistik dashboard.

    Seluruh angka dihitung dari data sungguhan milik guru yang login --
    dashboard tidak boleh menampilkan angka tempelan (hardcoded), karena
    tampilan ini ikut didemonstrasikan sebagai bukti kerja sistem.
    """
    with get_conn() as conn:
        audio = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(duration), 0) AS total_durasi "
            "FROM audio WHERE id_user = ?",
            (id_user,),
        ).fetchone()
        nilai = conn.execute(
            "SELECT COUNT(*) AS n, AVG(score) AS rata FROM assessment WHERE id_user = ?",
            (id_user,),
        ).fetchone()
        skala = [r["s"] for r in conn.execute(
            "SELECT DISTINCT COALESCE(skala_maks, 4) AS s FROM assessment"
            " WHERE id_user = ? ORDER BY s",
            (id_user,),
        )]

    # Rata-rata lintas skala TIDAK sah: skor 4 pada skala 1-4 adalah nilai
    # tertinggi, sedangkan pada skala 1-5 hanya nilai kedua tertinggi.
    # Merata-ratakannya menghasilkan angka yang tidak berarti apa-apa, jadi
    # angkanya ditahan dan percampurannya dilaporkan.
    campur = len(skala) > 1
    return {
        "jumlah_audio": audio["n"],
        "total_durasi": audio["total_durasi"],
        "jumlah_penilaian": nilai["n"],
        "rata_skor": None if campur else nilai["rata"],
        "skala": skala,
        "skala_tercampur": campur,
    }


def ambil_histori(id_user):
    """Mengambil daftar proses milik satu guru, terbaru lebih dahulu."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT a.id_audio, a.filename, a.duration, a.processing_time,
                   a.filepath, a.uploaded_at, a.status,
                   s.score, COALESCE(s.skala_maks, 4) AS skala_maks,
                   s.created_at AS waktu_nilai
            FROM audio a
            LEFT JOIN assessment s ON s.id_audio = a.id_audio
            WHERE a.id_user = ?
            ORDER BY a.uploaded_at DESC, a.id_audio DESC
            """,
            (id_user,),
        ).fetchall()


def ambil_penilaian(id_user):
    """Mengambil daftar hasil penilaian milik satu guru, terbaru lebih dahulu."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT s.id_assessment, s.topik, s.score,
                   COALESCE(s.skala_maks, 4) AS skala_maks, s.score_relevansi,
                   s.score_konsep, s.score_kelengkapan, s.score_koherensi,
                   s.feedback, s.created_at, a.filename, sp.speaker_label
            FROM assessment s
            JOIN audio a ON a.id_audio = s.id_audio
            LEFT JOIN speaker sp ON sp.id_speaker = s.id_speaker
            WHERE s.id_user = ?
            ORDER BY s.created_at DESC, s.id_assessment DESC
            """,
            (id_user,),
        ).fetchall()


def ambil_detail_audio(id_audio, id_user):
    """Mengambil detail satu proses beserta transkrip dan segmennya.

    id_user ikut disaring agar seorang guru tidak dapat membuka data guru lain
    hanya dengan menebak id_audio.
    """
    with get_conn() as conn:
        audio = conn.execute(
            "SELECT * FROM audio WHERE id_audio = ? AND id_user = ?", (id_audio, id_user)
        ).fetchone()
        if not audio:
            return None

        transkrip = conn.execute(
            "SELECT * FROM transcript WHERE id_audio = ?", (id_audio,)
        ).fetchone()
        segmen = conn.execute(
            """
            SELECT sg.start_time, sg.end_time, sg.text, sp.speaker_label, sp.role
            FROM segment sg
            JOIN speaker sp ON sp.id_speaker = sg.id_speaker
            WHERE sp.id_audio = ?
            ORDER BY sg.start_time
            """,
            (id_audio,),
        ).fetchall()
        penilaian = conn.execute(
            "SELECT * FROM assessment WHERE id_audio = ?", (id_audio,)
        ).fetchone()
        pembicara = conn.execute(
            "SELECT id_speaker, speaker_label, role, total_duration FROM speaker"
            " WHERE id_audio = ? ORDER BY speaker_label",
            (id_audio,),
        ).fetchall()

    # Peran pembicara yang dinilai dicari di sini, bukan di templat: halaman
    # detail harus dapat memperingatkan bila yang dinilai ternyata GURU, dan
    # peringatan itu tidak boleh bergantung pada logika yang tercecer di HTML.
    dinilai = None
    if penilaian:
        dinilai = next(
            (p for p in pembicara if p["id_speaker"] == penilaian["id_speaker"]), None
        )

    return {
        "audio": audio,
        "transkrip": transkrip,
        "segmen": segmen,
        "penilaian": penilaian,
        "pembicara": pembicara,
        # Pembicara yang skornya tercatat. None berarti penilaian menggabung
        # SELURUH pembicara -- termasuk ucapan guru -- yang membuat skor
        # siswa terangkat oleh kalimat yang bukan miliknya.
        "dinilai": dinilai,
    }


# ==============================
# SUNTING & HAPUS HISTORI
# ==============================
# Seluruh fungsi di bawah menyaring id_user pada klausa WHERE, bukan hanya
# memeriksanya di lapisan rute. Dengan begitu, satu rute yang lupa memeriksa
# kepemilikan tidak berubah menjadi celah yang memungkinkan seorang guru
# menyunting atau menghapus data guru lain.

def perbarui_transkrip(id_audio, id_user, teks):
    """Menyimpan suntingan manual guru atas transkrip.

    Keluaran asli sistem (`corrected_text` dan `llm_text`) TIDAK ditimpa.
    Suntingan masuk ke kolom terpisah supaya perbandingan "apa yang ditulis
    sistem" versus "apa yang dibetulkan guru" tetap dapat dilakukan; justru
    selisih itulah yang menjadi bukti seberapa akurat sistem bekerja.

    Mengirim teks kosong berarti membatalkan suntingan dan kembali memakai
    keluaran sistem.

    Mengembalikan True bila ada baris yang berubah, False bila proses tidak
    ditemukan atau bukan milik pengguna ini.
    """
    teks = (teks or "").strip()
    with get_conn() as conn:
        milik = conn.execute(
            "SELECT 1 FROM audio WHERE id_audio = ? AND id_user = ?",
            (id_audio, id_user),
        ).fetchone()
        if not milik:
            return False
        cur = conn.execute(
            "UPDATE transcript SET edited_text = ?, edited_at = ? WHERE id_audio = ?",
            (teks or None, _sekarang() if teks else None, id_audio),
        )
        return cur.rowcount > 0


def perbarui_topik(id_audio, id_user, topik):
    """Memperbarui topik/pertanyaan pada penilaian sebuah proses.

    Mengembalikan True bila ada baris yang berubah. False bila proses itu
    memang tidak punya baris penilaian (topik tidak diisi saat pemrosesan,
    atau evaluasi gagal), sehingga tidak ada yang dapat disunting.
    """
    topik = (topik or "").strip()
    with get_conn() as conn:
        milik = conn.execute(
            "SELECT 1 FROM audio WHERE id_audio = ? AND id_user = ?",
            (id_audio, id_user),
        ).fetchone()
        if not milik:
            return False
        cur = conn.execute(
            "UPDATE assessment SET topik = ? WHERE id_audio = ? AND id_user = ?",
            (topik or None, id_audio, id_user),
        )
        return cur.rowcount > 0


def perbarui_peran(id_audio, id_user, peran):
    """Menetapkan peran (Guru/Siswa/Lainnya) untuk tiap pembicara.

    Argumen `peran` adalah dict {id_speaker: peran}. Nilai di luar `PERAN_SAH`
    diperlakukan sebagai "belum dilabeli" (NULL), bukan disimpan apa adanya:
    ejaan yang beragam akan membuat pemeriksaan "yang dinilai ternyata guru"
    gagal menyala justru saat paling dibutuhkan.

    Mengembalikan jumlah pembicara yang perannya tersimpan, atau False bila
    proses tidak ditemukan/bukan milik pengguna ini.
    """
    with get_conn() as conn:
        milik = conn.execute(
            "SELECT 1 FROM audio WHERE id_audio = ? AND id_user = ?",
            (id_audio, id_user),
        ).fetchone()
        if not milik:
            return False

        jumlah = 0
        for id_speaker, nilai in (peran or {}).items():
            nilai = nilai if nilai in PERAN_SAH else None
            cur = conn.execute(
                # id_audio ikut disaring supaya id_speaker milik rekaman lain
                # tidak dapat diubah lewat kiriman formulir yang dirakit sendiri.
                "UPDATE speaker SET role = ? WHERE id_speaker = ? AND id_audio = ?",
                (nilai, id_speaker, id_audio),
            )
            jumlah += cur.rowcount
    return jumlah


def teks_pembicara_tersimpan(id_audio, id_user, id_speaker):
    """Mengambil segmen satu pembicara dari basis data, terurut menurut waktu.

    Dipakai untuk menilai ulang pembicara yang berbeda tanpa memproses ulang
    audionya: segmen per pembicara sudah tersimpan sejak pemrosesan pertama.

    Mengembalikan daftar dict berbentuk sama seperti keluaran diarisasi di
    app.py, agar dapat langsung diberikan ke `susun_teks_pembicara`.
    """
    with get_conn() as conn:
        milik = conn.execute(
            "SELECT 1 FROM audio WHERE id_audio = ? AND id_user = ?",
            (id_audio, id_user),
        ).fetchone()
        if not milik:
            return None
        baris = conn.execute(
            """
            SELECT sp.speaker_label, sg.start_time, sg.end_time, sg.text
            FROM segment sg
            JOIN speaker sp ON sp.id_speaker = sg.id_speaker
            WHERE sp.id_audio = ? AND sp.id_speaker = ?
            ORDER BY sg.start_time
            """,
            (id_audio, id_speaker),
        ).fetchall()

    return [
        {
            "pembicara": r["speaker_label"],
            "mulai": r["start_time"],
            "selesai": r["end_time"],
            "teks": r["text"],
        }
        for r in baris
    ]


def ganti_penilaian(id_audio, id_user, id_speaker, topik, hasil_evaluasi):
    """Mengganti penilaian sebuah proses dengan hasil penilaian ulang.

    Dipakai ketika ternyata sistem menilai pembicara yang keliru. Baris lama
    DIGANTI, bukan ditambah: satu proses hanya boleh punya satu skor berlaku,
    dan dua baris penilaian pada audio yang sama akan membuat ekspor data
    penelitian menghitung rekaman itu dua kali.

    `id_speaker` selalu tercatat, sehingga siapa yang dinilai tidak pernah
    lagi menjadi tebakan.

    Mengembalikan True bila berhasil, False bila proses tidak ditemukan atau
    bukan milik pengguna ini.
    """
    with get_conn() as conn:
        milik = conn.execute(
            "SELECT 1 FROM audio WHERE id_audio = ? AND id_user = ?",
            (id_audio, id_user),
        ).fetchone()
        if not milik:
            return False

        conn.execute("DELETE FROM assessment WHERE id_audio = ?", (id_audio,))
        skor = (hasil_evaluasi or {}).get("skor", {})
        conn.execute(
            "INSERT INTO assessment (id_audio, id_speaker, id_user, topik, score,"
            " skala_maks, score_relevansi, score_konsep, score_kelengkapan,"
            " score_koherensi, feedback, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                id_audio,
                id_speaker,
                id_user,
                topik,
                (hasil_evaluasi or {}).get("skor_akhir"),
                SKALA_MAKS,
                skor.get("relevansi"),
                skor.get("konsep"),
                skor.get("kelengkapan"),
                skor.get("koherensi"),
                (hasil_evaluasi or {}).get("umpan_balik"),
                _sekarang(),
            ),
        )
    return True


def hapus_histori(id_audio, id_user):
    """Menghapus satu proses beserta seluruh data turunannya.

    Penghapusan dilakukan dari anak ke induk (assessment, segment, transcript,
    speaker, lalu audio) karena foreign key diaktifkan; urutan terbalik akan
    ditolak SQLite. Seluruhnya dalam satu transaksi agar tidak menyisakan
    segmen atau penilaian yatim bila terjadi kegagalan di tengah.

    Mengembalikan lokasi berkas rekaman yang perlu ikut dihapus pemanggil
    (atau None), atau False bila proses tidak ditemukan/bukan milik pengguna
    ini. Berkasnya sengaja TIDAK dihapus di sini: basis data dan sistem berkas
    tidak berbagi transaksi, sehingga berkas dihapus hanya setelah transaksi
    basis data benar-benar berhasil.
    """
    with get_conn() as conn:
        baris = conn.execute(
            "SELECT filepath FROM audio WHERE id_audio = ? AND id_user = ?",
            (id_audio, id_user),
        ).fetchone()
        if not baris:
            return False

        conn.execute("DELETE FROM assessment WHERE id_audio = ?", (id_audio,))
        conn.execute(
            "DELETE FROM segment WHERE id_transcript IN"
            " (SELECT id_transcript FROM transcript WHERE id_audio = ?)",
            (id_audio,),
        )
        conn.execute("DELETE FROM transcript WHERE id_audio = ?", (id_audio,))
        conn.execute("DELETE FROM speaker WHERE id_audio = ?", (id_audio,))
        conn.execute("DELETE FROM audio WHERE id_audio = ?", (id_audio,))

    return baris["filepath"]


if __name__ == "__main__":
    init_db()
