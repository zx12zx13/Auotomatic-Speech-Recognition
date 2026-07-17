"""Black Box Testing — skenario Lampiran 5 proposal (BB-001 s.d. BB-023).

Tiap kelas/metode uji diberi kode BB-XXX yang merujuk tabel Lampiran 5.
Penyesuaian terhadap Lampiran 5 (didokumentasikan di PENGUJIAN.md):
- Autentikasi memakai USERNAME, bukan email, mengikuti Tabel 3.2 proposal.
- BB-005/BB-006: pesan kesalahan login sengaja disatukan menjadi
  "Username atau password salah" agar daftar pengguna terdaftar tidak
  dapat dipancing dari perbedaan pesan (keamanan).
- Skenario yang membutuhkan model ASR/diarization atau Gemini API sungguhan
  (BB-012 s.d. BB-019) diuji manual, bukan di sini.
"""
import os
import unittest

from fastapi.testclient import TestClient

from tests import util_uji
from tests.util_uji import app, main, db


class UjiRegistrasi(unittest.TestCase):
    """MODUL 1 — Registrasi."""

    def test_bb001_registrasi_data_valid(self):
        c = TestClient(main.app)
        nama = util_uji.user_unik("bb001")
        r = c.post("/register", data={
            "username": nama, "password": "sandi123", "confirm_password": "sandi123",
        }, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertIn("/login", r.headers["location"])
        # Akun benar-benar tersimpan dan dapat dipakai login.
        self.assertIsNotNone(db.verifikasi_user(nama, "sandi123"))

    def test_bb002_registrasi_username_sudah_terdaftar(self):
        c = TestClient(main.app)
        nama = util_uji.user_unik("bb002")
        data = {"username": nama, "password": "s1", "confirm_password": "s1"}
        c.post("/register", data=data, follow_redirects=False)
        r = c.post("/register", data=data)
        self.assertEqual(r.status_code, 200)
        self.assertIn("sudah digunakan", r.text)

    def test_bb003_konfirmasi_password_tidak_cocok(self):
        # Lampiran 5 menguji format email; sistem memakai username (Tabel 3.2),
        # sehingga kasus ini diganti validasi input registrasi yang setara.
        c = TestClient(main.app)
        r = c.post("/register", data={
            "username": util_uji.user_unik("bb003"),
            "password": "abc", "confirm_password": "xyz",
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn("tidak cocok", r.text)

    def test_bb003b_registrasi_username_kosong(self):
        c = TestClient(main.app)
        r = c.post("/register", data={
            "username": "   ", "password": "abc", "confirm_password": "abc",
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn("wajib diisi", r.text)


class UjiLogin(unittest.TestCase):
    """MODUL 1 — Login."""

    def test_bb004_login_kredensial_valid(self):
        c, id_user = util_uji.klien_login()
        self.assertIsNotNone(id_user)
        r = c.get("/")
        self.assertEqual(r.status_code, 200)  # dashboard, bukan redirect

    def test_bb005_login_user_tidak_terdaftar(self):
        c = TestClient(main.app)
        r = c.post("/login", data={"username": "tidak-ada", "password": "x"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Username atau password salah", r.text)

    def test_bb006_login_password_salah(self):
        nama = util_uji.user_unik("bb006")
        util_uji.klien_login(username=nama)
        c = TestClient(main.app)
        r = c.post("/login", data={"username": nama, "password": "salah"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Username atau password salah", r.text)

    def test_bb006b_pesan_error_tidak_membedakan_user_dan_password(self):
        # Justifikasi penyesuaian BB-005/BB-006: kedua kegagalan harus
        # menghasilkan pesan yang SAMA agar username tidak bisa dienumerasi.
        nama = util_uji.user_unik("bb006b")
        util_uji.klien_login(username=nama)
        c = TestClient(main.app)
        r1 = c.post("/login", data={"username": "tidak-ada", "password": "x"})
        r2 = c.post("/login", data={"username": nama, "password": "salah"})
        self.assertIn("Username atau password salah", r1.text)
        self.assertIn("Username atau password salah", r2.text)

    def test_bb007_login_field_kosong(self):
        c = TestClient(main.app)
        r = c.post("/login", data={"username": "", "password": ""})
        self.assertEqual(r.status_code, 200)
        self.assertIn("wajib diisi", r.text)


class UjiUploadAudio(unittest.TestCase):
    """MODUL 2 — Upload/validasi berkas audio (validate_audio)."""

    @classmethod
    def setUpClass(cls):
        import numpy as np
        import soundfile as sf
        cls.dir = util_uji.DIR_UJI

        # BB-008: wav valid > 5 detik (nada 440 Hz, 6 detik).
        sr = 16000
        t = np.linspace(0, 6.0, 6 * sr, endpoint=False)
        cls.wav_valid = os.path.join(cls.dir, "valid_6detik.wav")
        sf.write(cls.wav_valid, 0.5 * np.sin(2 * np.pi * 440 * t), sr)

        # BB-009: format tidak didukung.
        cls.file_txt = os.path.join(cls.dir, "bukan_audio.txt")
        with open(cls.file_txt, "w") as f:
            f.write("ini bukan audio")

        # BB-010: berkas 0 byte.
        cls.wav_kosong = os.path.join(cls.dir, "kosong.wav")
        open(cls.wav_kosong, "w").close()

        # Tambahan: teks disamarkan berekstensi .wav (deteksi corrupt).
        cls.wav_palsu = os.path.join(cls.dir, "palsu.wav")
        with open(cls.wav_palsu, "w") as f:
            f.write("bukan isi wav")

    def test_bb008_upload_audio_valid(self):
        durasi = app.validate_audio(self.wav_valid)
        self.assertAlmostEqual(durasi, 6.0, places=1)

    def test_bb009_format_tidak_didukung(self):
        with self.assertRaises(app.AudioValidationError) as ctx:
            app.validate_audio(self.file_txt)
        self.assertIn("tidak didukung", str(ctx.exception))

    def test_bb010_file_kosong(self):
        with self.assertRaises(app.AudioValidationError) as ctx:
            app.validate_audio(self.wav_kosong)
        self.assertIn("0 byte", str(ctx.exception))

    def test_bb010b_file_corrupt(self):
        with self.assertRaises(app.AudioValidationError) as ctx:
            app.validate_audio(self.wav_palsu)
        self.assertIn("rusak", str(ctx.exception))

    def test_bb011_file_tidak_ada(self):
        with self.assertRaises(app.AudioValidationError) as ctx:
            app.validate_audio(os.path.join(self.dir, "tidak-ada.wav"))
        self.assertIn("tidak ditemukan", str(ctx.exception))


class UjiEvaluasiLLM(unittest.TestCase):
    """MODUL 6 — Evaluasi LLM: jalur kegagalan yang dapat diuji tanpa API."""

    def test_bb020_api_gagal_merespons(self):
        import evaluator

        class KlienGagal:
            def __init__(self, *a, **k):
                self.models = self

            def generate_content(self, *a, **k):
                raise ConnectionError("simulasi koneksi terputus")

        klien_asli = evaluator.genai.Client
        kunci_asli = os.environ.pop("GEMINI_API_KEY", None)
        os.environ["GEMINI_API_KEY"] = "kunci-tiruan"
        evaluator.genai.Client = KlienGagal
        try:
            with self.assertRaises(evaluator.EvaluationError) as ctx:
                evaluator.evaluate_response("Topik", "Jawaban siswa.")
            self.assertIn("Gagal menghubungi Gemini API", str(ctx.exception))
        finally:
            evaluator.genai.Client = klien_asli
            if kunci_asli is None:
                os.environ.pop("GEMINI_API_KEY", None)
            else:
                os.environ["GEMINI_API_KEY"] = kunci_asli

    def test_bb020b_tanpa_api_key_pesan_jelas(self):
        import evaluator
        kunci_asli = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with self.assertRaises(evaluator.EvaluationError) as ctx:
                evaluator.evaluate_response("Topik", "Jawaban siswa.")
            self.assertIn("GEMINI_API_KEY", str(ctx.exception))
        finally:
            if kunci_asli is not None:
                os.environ["GEMINI_API_KEY"] = kunci_asli


class UjiSimpanDanDashboard(unittest.TestCase):
    """MODUL 7 — Simpan hasil, histori, dan kontrol akses."""

    def test_bb021_evaluasi_berhasil_tersimpan_di_histori(self):
        c, id_user = util_uji.klien_login()
        util_uji.simpan_evaluasi_contoh(id_user, filename="bb021.wav")
        baris = db.ambil_histori(id_user)
        self.assertEqual(len(baris), 1)
        self.assertEqual(baris[0]["filename"], "bb021.wav")
        self.assertEqual(baris[0]["score"], 3.5)

    def test_bb022_histori_tampil_di_halaman(self):
        c, id_user = util_uji.klien_login()
        util_uji.simpan_evaluasi_contoh(id_user, filename="bb022.wav")
        r = c.get("/histori-content")
        self.assertEqual(r.status_code, 200)
        self.assertIn("bb022.wav", r.text)
        self.assertIn("3.50 / 4", r.text)
        # Halaman penilaian ikut menampilkan skor per indikator.
        r = c.get("/nilai-content")
        self.assertIn("Relevansi: <strong>4</strong>", r.text)

    def test_bb023_akses_histori_tanpa_login(self):
        c = TestClient(main.app)
        # Shell aplikasi: dialihkan ke login sesuai ekspektasi Lampiran 5.
        r = c.get("/app/histori", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["location"])
        # Rute konten iframe: ditolak eksplisit.
        self.assertEqual(c.get("/histori-content").status_code, 403)
        self.assertEqual(c.get("/nilai-content").status_code, 403)

    def test_bb023b_isolasi_histori_antar_guru(self):
        c1, id1 = util_uji.klien_login()
        c2, id2 = util_uji.klien_login()
        id_audio = util_uji.simpan_evaluasi_contoh(id1, filename="rahasia_guru1.wav")
        r = c2.get("/histori-content")
        self.assertNotIn("rahasia_guru1.wav", r.text)
        r = c2.get(f"/histori-content/{id_audio}")
        self.assertEqual(r.status_code, 404)

    def test_bb023c_cookie_sesi_palsu_ditolak(self):
        c = TestClient(main.app, cookies={"session-id": "admin"})
        r = c.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["location"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
