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
    id_audio    INTEGER PRIMARY KEY AUTOINCREMENT,
    id_user     INTEGER NOT NULL,
    filename    TEXT NOT NULL,
    filepath    TEXT,
    duration    REAL,
    uploaded_at TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'diproses',
    FOREIGN KEY (id_user) REFERENCES user(id_user)
);

CREATE TABLE IF NOT EXISTS speaker (
    id_speaker     INTEGER PRIMARY KEY AUTOINCREMENT,
    id_audio       INTEGER NOT NULL,
    speaker_label  TEXT NOT NULL,
    total_duration REAL DEFAULT 0,
    FOREIGN KEY (id_audio) REFERENCES audio(id_audio)
);

CREATE TABLE IF NOT EXISTS transcript (
    id_transcript  INTEGER PRIMARY KEY AUTOINCREMENT,
    id_audio       INTEGER NOT NULL,
    full_text      TEXT,
    corrected_text TEXT,
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


def init_db():
    """Membuat seluruh tabel bila belum ada."""
    with get_conn() as conn:
        conn.executescript(SKEMA)
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
                 filepath=None):
    """Menyimpan satu proses evaluasi secara bertahap dalam satu transaksi.

    Urutan penyimpanan mengikuti alur proposal: audio -> speaker -> transcript
    -> segment -> assessment. Seluruhnya dalam satu transaksi agar tidak ada
    hasil setengah jadi bila terjadi kegagalan di tengah.

    Argumen:
        segmen: daftar dict berisi 'pembicara', 'mulai', 'selesai', 'teks'.
        hasil_evaluasi: dict keluaran evaluator.evaluate_response, atau None
            bila evaluasi tidak dilakukan/gagal.
        pembicara_dinilai: label pembicara yang dinilai, mis. "Pembicara 1".

    Mengembalikan id_audio.
    """
    segmen = segmen or []
    with get_conn() as conn:
        # 1. audio
        cur = conn.execute(
            "INSERT INTO audio (id_user, filename, filepath, duration, uploaded_at, status)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (id_user, filename, filepath, durasi, _sekarang(), "selesai"),
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
            "INSERT INTO transcript (id_audio, full_text, corrected_text, created_at)"
            " VALUES (?, ?, ?, ?)",
            (id_audio, full_text, corrected_text, _sekarang()),
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
                " score_relevansi, score_konsep, score_kelengkapan, score_koherensi,"
                " feedback, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id_audio,
                    peta_speaker.get(pembicara_dinilai),
                    id_user,
                    topik,
                    hasil_evaluasi.get("skor_akhir"),
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
def ambil_histori(id_user):
    """Mengambil daftar proses milik satu guru, terbaru lebih dahulu."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT a.id_audio, a.filename, a.duration, a.uploaded_at, a.status,
                   s.score, s.created_at AS waktu_nilai
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
            SELECT s.id_assessment, s.topik, s.score, s.score_relevansi,
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
            SELECT sg.start_time, sg.end_time, sg.text, sp.speaker_label
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

    return {
        "audio": audio,
        "transkrip": transkrip,
        "segmen": segmen,
        "penilaian": penilaian,
    }


if __name__ == "__main__":
    init_db()
