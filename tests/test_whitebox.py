"""White Box Testing — jalur/percabangan Lampiran 5 proposal (WB-001 s.d. WB-023).

Tiap metode uji diberi kode WB-XXX yang merujuk tabel Lampiran 5. Jalur yang
berada di dalam model (VAD, deteksi pergantian pembicara, diarisasi,
transkripsi — WB-012 s.d. WB-018) tidak dapat diuji tanpa model sungguhan
dan ditandai "uji manual" di PENGUJIAN.md. WB-007 (isActive) tidak berlaku:
tabel user pada proposal maupun implementasi tidak memiliki kolom status
aktif.
"""
import os
import unittest

from tests import util_uji
from tests.util_uji import app, db


class UjiAutentikasi(unittest.TestCase):
    """WB-001 s.d. WB-006 — percabangan modul autentikasi (database.py)."""

    def test_wb001_registrasi_semua_field_valid(self):
        nama = util_uji.user_unik("wb001")
        id_user = db.buat_user(nama, "sandi123")
        self.assertIsInstance(id_user, int)
        baris = db.ambil_user(id_user)
        self.assertEqual(baris["username"], nama)

    def test_wb001b_password_tersimpan_sebagai_hash_bcrypt(self):
        nama = util_uji.user_unik("wb001b")
        db.buat_user(nama, "sandi-rahasia")
        with db.get_conn() as conn:
            tersimpan = conn.execute(
                "SELECT password FROM user WHERE username = ?", (nama,)
            ).fetchone()["password"]
        self.assertTrue(tersimpan.startswith("$2b$"))
        self.assertNotIn("sandi-rahasia", tersimpan)

    def test_wb002_registrasi_input_tidak_valid(self):
        with self.assertRaises(ValueError):
            db.buat_user("", "sandi")
        with self.assertRaises(ValueError):
            db.buat_user("   ", "sandi")
        with self.assertRaises(ValueError):
            db.buat_user(util_uji.user_unik("wb002"), "")

    def test_wb003_registrasi_username_duplikat(self):
        nama = util_uji.user_unik("wb003")
        db.buat_user(nama, "sandi")
        with self.assertRaises(ValueError) as ctx:
            db.buat_user(nama, "sandi-lain")
        self.assertIn("sudah digunakan", str(ctx.exception))

    def test_wb004_login_user_ada_password_cocok(self):
        nama = util_uji.user_unik("wb004")
        id_dibuat = db.buat_user(nama, "sandi123")
        self.assertEqual(db.verifikasi_user(nama, "sandi123"), id_dibuat)

    def test_wb005_login_user_tidak_ditemukan(self):
        self.assertIsNone(db.verifikasi_user("tidak-terdaftar", "apa saja"))

    def test_wb006_login_password_tidak_cocok(self):
        nama = util_uji.user_unik("wb006")
        db.buat_user(nama, "benar")
        self.assertIsNone(db.verifikasi_user(nama, "salah"))

    def test_wb006b_input_kosong_ditolak_sebelum_query(self):
        self.assertIsNone(db.verifikasi_user("", "sandi"))
        self.assertIsNone(db.verifikasi_user("nama", ""))


class UjiValidasiAudio(unittest.TestCase):
    """WB-008 / WB-009 — percabangan validate_audio (app.py)."""

    @classmethod
    def setUpClass(cls):
        import numpy as np
        import soundfile as sf
        sr = 16000
        t = np.linspace(0, 2.0, 2 * sr, endpoint=False)
        cls.wav_valid = os.path.join(util_uji.DIR_UJI, "wb_valid.wav")
        sf.write(cls.wav_valid, 0.5 * np.sin(2 * np.pi * 440 * t), sr)

    def test_wb008_audio_valid_lanjut(self):
        self.assertGreater(app.validate_audio(self.wav_valid), 0)

    def test_wb009_setiap_cabang_penolakan(self):
        # Cabang 1: berkas tidak ada / None.
        for jalur in (None, "", os.path.join(util_uji.DIR_UJI, "hilang.wav")):
            with self.assertRaises(app.AudioValidationError):
                app.validate_audio(jalur)
        # Cabang 2: ekstensi tidak didukung.
        f_txt = os.path.join(util_uji.DIR_UJI, "wb.txt")
        with open(f_txt, "w") as f:
            f.write("x")
        with self.assertRaises(app.AudioValidationError):
            app.validate_audio(f_txt)
        # Cabang 3: 0 byte.
        f_0 = os.path.join(util_uji.DIR_UJI, "wb_nol.wav")
        open(f_0, "w").close()
        with self.assertRaises(app.AudioValidationError):
            app.validate_audio(f_0)
        # Cabang 4: isi bukan audio (corrupt).
        f_palsu = os.path.join(util_uji.DIR_UJI, "wb_palsu.wav")
        with open(f_palsu, "w") as f:
            f.write("bukan wav")
        with self.assertRaises(app.AudioValidationError):
            app.validate_audio(f_palsu)


class UjiPraPemrosesanAudio(unittest.TestCase):
    """WB-010 / WB-011 — aliran data preprocess_audio (app.py)."""

    def test_wb010_wb011_noise_reduction_dan_normalisasi(self):
        import numpy as np
        import soundfile as sf
        sr = 16000
        t = np.linspace(0, 2.0, 2 * sr, endpoint=False)
        # Nada pelan (puncak 0,1) + noise acak kecil.
        rng = np.random.default_rng(42)
        sinyal = 0.1 * np.sin(2 * np.pi * 440 * t) + 0.01 * rng.standard_normal(len(t))
        jalur = os.path.join(util_uji.DIR_UJI, "wb_pelan.wav")
        sf.write(jalur, sinyal, sr)

        keluar = app.preprocess_audio(jalur)
        try:
            # Kegagalan TIDAK boleh diam-diam fallback ke audio mentah.
            self.assertNotEqual(keluar, jalur, "preprocess_audio fallback ke audio mentah")
            data, _ = sf.read(keluar)
            puncak_awal = float(np.max(np.abs(sinyal)))
            puncak_akhir = float(np.max(np.abs(data)))
            # Normalisasi harus menaikkan puncak amplitudo mendekati 1.0.
            self.assertGreater(puncak_akhir, puncak_awal)
            self.assertGreater(puncak_akhir, 0.8)
        finally:
            if keluar != jalur and os.path.exists(keluar):
                os.remove(keluar)


class UjiPraPemrosesanTeks(unittest.TestCase):
    """WB-019 — percabangan text_preprocessing.py."""

    def test_wb019_bersihkan_teks_semua_tahap(self):
        from text_preprocessing import bersihkan_teks
        kotor = ("eee  saya   akan   menjelaskan  tentang gak  paham  yg   "
                 "namanya fotosintesis   hmm  itu itu itu proses  tumbuhan")
        bersih = bersihkan_teks(kotor)
        self.assertNotIn("eee", bersih)          # kata pengisi hilang
        self.assertNotIn("gak", bersih)          # slang ternormalisasi
        self.assertIn("tidak", bersih)
        self.assertIn("yang", bersih)
        self.assertNotIn("  ", bersih)           # spasi ganda hilang
        self.assertNotIn("itu itu itu", bersih)  # pengulangan ASR hilang
        self.assertTrue(bersih[0].isupper())     # kapitalisasi kalimat

    def test_wb019b_pengulangan_dua_kali_dibiarkan(self):
        from text_preprocessing import hapus_pengulangan
        self.assertIn("sangat sangat", hapus_pengulangan("dia sangat sangat baik"))
        self.assertNotIn("saya saya saya",
                         hapus_pengulangan("saya saya saya belajar"))

    def test_wb019c_teks_kosong(self):
        from text_preprocessing import bersihkan_teks
        self.assertEqual(bersihkan_teks(""), "")
        self.assertEqual(bersihkan_teks(None), "")

    def test_wb019d_susun_teks_per_pembicara_terurut_waktu(self):
        from text_preprocessing import susun_teks_pembicara
        segmen_acak = [
            {"pembicara": "Pembicara 1", "mulai": 10.0, "selesai": 12.0, "teks": "kedua"},
            {"pembicara": "Pembicara 2", "mulai": 5.0, "selesai": 8.0, "teks": "guru bicara"},
            {"pembicara": "Pembicara 1", "mulai": 0.0, "selesai": 4.0, "teks": "pertama"},
        ]
        hasil = susun_teks_pembicara(segmen_acak, "Pembicara 1")
        self.assertLess(hasil.lower().find("pertama"), hasil.lower().find("kedua"))
        self.assertNotIn("guru bicara", hasil)

    def test_wb019e_pembicara_target_tidak_ada(self):
        from text_preprocessing import susun_teks_pembicara
        segmen = [{"pembicara": "Pembicara 1", "mulai": 0, "selesai": 1, "teks": "halo"}]
        # Tidak boleh diam-diam menilai pembicara lain.
        self.assertEqual(susun_teks_pembicara(segmen, "Pembicara 3"), "")

    def test_wb019f_tanpa_target_gabungkan_semua(self):
        from text_preprocessing import susun_teks_pembicara
        segmen = [
            {"pembicara": "Pembicara 2", "mulai": 5, "selesai": 6, "teks": "dua"},
            {"pembicara": "Pembicara 1", "mulai": 0, "selesai": 1, "teks": "satu"},
        ]
        hasil = susun_teks_pembicara(segmen, None).lower()
        self.assertLess(hasil.find("satu"), hasil.find("dua"))


class UjiEvaluatorLLM(unittest.TestCase):
    """WB-020 / WB-021 — prompt builder dan validasi keluaran evaluator.py."""

    def test_wb020_prompt_memuat_rubrik_topik_jawaban(self):
        from evaluator import build_prompt, RUBRIK
        prompt = build_prompt("Jelaskan fotosintesis.", "Fotosintesis adalah ...")
        self.assertIn("Jelaskan fotosintesis.", prompt)
        self.assertIn("Fotosintesis adalah ...", prompt)
        for indikator in RUBRIK:
            self.assertIn(RUBRIK[indikator]["nama"], prompt)
            for deskriptor in RUBRIK[indikator]["deskriptor"].values():
                self.assertIn(deskriptor, prompt)

    @staticmethod
    def _keluaran_model(**ubah):
        """Keluaran model sesuai _skema_keluaran(), dengan medan yang bisa diubah."""
        data = {
            "skor_relevansi": 4, "alasan_relevansi": "a",
            "skor_konsep": 3, "alasan_konsep": "b",
            "skor_kelengkapan": 2, "alasan_kelengkapan": "c",
            "skor_koherensi": 3, "alasan_koherensi": "d",
            "umpan_balik": "cukup baik",
        }
        data.update(ubah)
        return data

    def test_wb021_keluaran_valid_dihitung_rata_rata(self):
        from evaluator import parse_hasil
        hasil = parse_hasil(self._keluaran_model())
        self.assertEqual(hasil["skor_akhir"], 3.0)  # (4+3+2+3)/4
        self.assertEqual(hasil["skor"]["relevansi"], 4)
        self.assertEqual(hasil["umpan_balik"], "cukup baik")

    def test_wb021b_skor_di_luar_skala_atau_bukan_bulat_ditolak(self):
        # BUG-09: int(2.5) memotong jadi 2 dan int(True) jadi 1 — keduanya
        # dulu lolos diam-diam sebagai skor sah. Kini wajib ditolak.
        from evaluator import parse_hasil, EvaluationError
        for skor_salah in (0, 5, 7, -1, 2.5, "2.5", True, None, "tiga"):
            with self.assertRaises(EvaluationError, msg=f"skor {skor_salah!r} lolos"):
                parse_hasil(self._keluaran_model(skor_relevansi=skor_salah))

    def test_wb021b2_skor_float_bulat_diterima(self):
        # JSON dapat mengirim 4.0 alih-alih 4; nilai setara bulat tetap sah.
        from evaluator import parse_hasil
        hasil = parse_hasil(self._keluaran_model(skor_relevansi=4.0))
        self.assertEqual(hasil["skor"]["relevansi"], 4)

    def test_wb021c_medan_hilang_atau_bukan_objek_ditolak(self):
        from evaluator import parse_hasil, EvaluationError
        data = self._keluaran_model()
        del data["skor_konsep"]
        with self.assertRaises(EvaluationError):
            parse_hasil(data)  # medan skor hilang
        with self.assertRaises(EvaluationError):
            parse_hasil([1, 2, 3])  # bukan objek JSON
        with self.assertRaises(EvaluationError):
            parse_hasil("bukan objek")

    def test_wb021d_input_kosong_ditolak_sebelum_memanggil_api(self):
        from evaluator import evaluate_response, EvaluationError
        with self.assertRaises(EvaluationError):
            evaluate_response("", "jawaban")
        with self.assertRaises(EvaluationError):
            evaluate_response("topik", "   ")


class UjiDatabase(unittest.TestCase):
    """WB-022 / WB-023 — penyimpanan bertahap dan pembacaan histori."""

    def test_wb022_simpan_bertahap_lima_tabel(self):
        id_user = db.buat_user(util_uji.user_unik("wb022"), "sandi")
        id_audio = util_uji.simpan_evaluasi_contoh(id_user)
        with db.get_conn() as conn:
            def hitung(tabel, kolom, nilai):
                return conn.execute(
                    f"SELECT COUNT(*) c FROM {tabel} WHERE {kolom} = ?", (nilai,)
                ).fetchone()["c"]
            self.assertEqual(hitung("audio", "id_audio", id_audio), 1)
            self.assertEqual(hitung("speaker", "id_audio", id_audio), 2)
            self.assertEqual(hitung("assessment", "id_audio", id_audio), 1)
            id_transcript = conn.execute(
                "SELECT id_transcript FROM transcript WHERE id_audio = ?",
                (id_audio,),
            ).fetchone()["id_transcript"]
            self.assertEqual(hitung("segment", "id_transcript", id_transcript), 2)

    def test_wb022b_transaksi_gagal_tidak_meninggalkan_data_setengah_jadi(self):
        import sqlite3
        with db.get_conn() as conn:
            jumlah_awal = conn.execute("SELECT COUNT(*) c FROM audio").fetchone()["c"]
        # id_user fiktif melanggar foreign key -> seluruh transaksi batal.
        with self.assertRaises(sqlite3.IntegrityError):
            util_uji.simpan_evaluasi_contoh(999999)
        with db.get_conn() as conn:
            jumlah_akhir = conn.execute("SELECT COUNT(*) c FROM audio").fetchone()["c"]
        self.assertEqual(jumlah_awal, jumlah_akhir)

    def test_wb022c_tanpa_hasil_evaluasi_assessment_tidak_dibuat(self):
        id_user = db.buat_user(util_uji.user_unik("wb022c"), "sandi")
        id_audio = db.simpan_hasil(
            id_user=id_user, filename="tanpa_nilai.wav", durasi=10.0,
            segmen=util_uji.SEGMEN_CONTOH, full_text="t", corrected_text="t",
            hasil_evaluasi=None,
        )
        with db.get_conn() as conn:
            jumlah = conn.execute(
                "SELECT COUNT(*) c FROM assessment WHERE id_audio = ?", (id_audio,)
            ).fetchone()["c"]
        self.assertEqual(jumlah, 0)
        # Transkrip tetap tersimpan walau penilaian tidak ada.
        self.assertEqual(len(db.ambil_histori(id_user)), 1)

    def test_wb023_load_histori_dan_detail(self):
        id_user = db.buat_user(util_uji.user_unik("wb023"), "sandi")
        id_audio = util_uji.simpan_evaluasi_contoh(id_user)

        histori = db.ambil_histori(id_user)
        self.assertEqual(len(histori), 1)

        penilaian = db.ambil_penilaian(id_user)
        self.assertEqual(len(penilaian), 1)
        self.assertEqual(penilaian[0]["score_relevansi"], 4)
        self.assertEqual(penilaian[0]["speaker_label"], "Pembicara 1")

        detail = db.ambil_detail_audio(id_audio, id_user)
        self.assertIsNotNone(detail)
        self.assertEqual(len(detail["segmen"]), 2)
        # Segmen terurut waktu.
        self.assertLessEqual(detail["segmen"][0]["start_time"],
                             detail["segmen"][1]["start_time"])

    def test_wb023b_isolasi_antar_pengguna(self):
        id_a = db.buat_user(util_uji.user_unik("wb023b_a"), "sandi")
        id_b = db.buat_user(util_uji.user_unik("wb023b_b"), "sandi")
        id_audio = util_uji.simpan_evaluasi_contoh(id_a)
        self.assertEqual(len(db.ambil_histori(id_b)), 0)
        self.assertEqual(len(db.ambil_penilaian(id_b)), 0)
        self.assertIsNone(db.ambil_detail_audio(id_audio, id_b))


if __name__ == "__main__":
    unittest.main(verbosity=2)
