"""Penyiapan bersama untuk seluruh berkas uji (§3.2.5 proposal).

Model Whisper dan Pyannote TIDAK dimuat: fungsi pemuatnya diganti stub
SEBELUM `app` di-import, karena pengujian otomatis menyasar logika program,
bukan kualitas model. Selain kedua stub itu, semuanya sungguhan: UI Gradio
benar-benar dibangun, rute FastAPI benar-benar di-mount, dan basis data
SQLite benar-benar ditulis (ke berkas sementara, bukan evaluasi.db).

Skenario yang mustahil diuji tanpa model/API sungguhan (transkripsi,
diarisasi, kualitas skor LLM) ditandai "uji manual" di PENGUJIAN.md —
tidak diklaim lolos di sini.
"""
import os
import sys
import tempfile

_DIR_PRODUK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _DIR_PRODUK not in sys.path:
    sys.path.insert(0, _DIR_PRODUK)

# Basis data sementara khusus pengujian — evaluasi.db tidak boleh tersentuh.
DIR_UJI = tempfile.mkdtemp(prefix="uji_asr_")
os.environ["DB_PATH"] = os.path.join(DIR_UJI, "uji.db")

# Token tiruan agar app.py lolos pemeriksaan konfigurasi saat import;
# pemuat model di bawah sudah di-stub sehingga token tidak pernah dipakai.
os.environ.setdefault("HUGGINGFACE_TOKEN", "token-tiruan-untuk-uji")

import whisper  # noqa: E402

whisper.load_model = lambda *a, **k: None

from pyannote.audio import Pipeline  # noqa: E402

class _PipelineTiruan:
    """Pengganti pipeline diarisasi saat pengujian.

    Menyediakan .to() karena app.py memindahkan pipeline ke GPU/CPU saat dimuat.
    """

    def to(self, perangkat):
        return self


Pipeline.from_pretrained = classmethod(lambda cls, *a, **k: _PipelineTiruan())

import app  # noqa: E402
import main  # noqa: E402
import database as db  # noqa: E402

__all__ = ["app", "main", "db", "DIR_UJI"]


_urut_user = 0


def user_unik(awalan="guru"):
    """Menghasilkan username unik agar tiap uji tidak saling mengganggu."""
    global _urut_user
    _urut_user += 1
    return f"{awalan}_{_urut_user}"


def klien_login(username=None, password="sandi-uji-123"):
    """Membuat TestClient yang sudah terdaftar dan login. -> (client, id_user)"""
    from fastapi.testclient import TestClient

    username = username or user_unik()
    c = TestClient(main.app)
    r = c.post("/register", data={
        "username": username,
        "password": password,
        "confirm_password": password,
    }, follow_redirects=False)
    assert r.status_code == 303, f"registrasi {username} gagal: {r.status_code}"
    r = c.post("/login", data={"username": username, "password": password},
               follow_redirects=False)
    assert r.status_code == 303, f"login {username} gagal: {r.status_code}"
    return c, db.verifikasi_user(username, password)


SEGMEN_CONTOH = [
    {"pembicara": "Pembicara 1", "mulai": 0.0, "selesai": 6.5,
     "teks": "Fotosintesis adalah proses tumbuhan membuat makanan."},
    {"pembicara": "Pembicara 2", "mulai": 6.5, "selesai": 9.0,
     "teks": "Bagus, lanjutkan."},
]

HASIL_EVALUASI_CONTOH = {
    "skor": {"relevansi": 4, "konsep": 3, "kelengkapan": 3, "koherensi": 4},
    "skor_akhir": 3.5,
    "umpan_balik": "Jawaban relevan dan runtut; konsep klorofil perlu diperdalam.",
}


def simpan_evaluasi_contoh(id_user, filename="ujian_lisan.wav"):
    """Menyimpan satu hasil evaluasi lengkap, jalur yang sama dengan app.py."""
    return db.simpan_hasil(
        id_user=id_user,
        filename=filename,
        durasi=95.0,
        segmen=SEGMEN_CONTOH,
        full_text="Fotosintesis adalah ... Bagus, lanjutkan.",
        corrected_text="Fotosintesis adalah proses tumbuhan membuat makanan.",
        topik="Jelaskan proses fotosintesis.",
        hasil_evaluasi=HASIL_EVALUASI_CONTOH,
        pembicara_dinilai="Pembicara 1",
    )
