"""Uji pelabelan peran pembicara dan penilaian ulang.

Menutup satu kegagalan yang paling berbahaya pada sistem ini: menilai ucapan
orang yang keliru. Diarisasi hanya mengelompokkan suara, sehingga "Pembicara 1"
adalah nomor klaster, bukan peran. Bila nomor yang dinilai jatuh ke guru,
evaluator tetap bekerja dengan benar dan tetap mengeluarkan skor yang tampak
wajar -- tidak ada galat, tidak ada tanda apa pun. Karena itu yang diuji di
sini bukan hanya "peran tersimpan", melainkan bahwa keadaan berbahaya
BENAR-BENAR TERLIHAT di halaman.

Penilaian ulang diuji dengan evaluator tiruan: yang diuji adalah jalur program
dan penggantian datanya, bukan mutu penilaian model.
"""
import unittest
from unittest import mock

from tests import util_uji
from tests.util_uji import db


def _simpan(id_user, pembicara_dinilai="Pembicara 1", topik="Jelaskan fotosintesis."):
    return db.simpan_hasil(
        id_user=id_user,
        filename="ujian_lisan.wav",
        durasi=95.0,
        segmen=util_uji.SEGMEN_CONTOH,
        full_text="Fotosintesis adalah ... Bagus, lanjutkan.",
        corrected_text="Fotosintesis adalah proses tumbuhan membuat makanan.",
        topik=topik,
        hasil_evaluasi=util_uji.HASIL_EVALUASI_CONTOH,
        pembicara_dinilai=pembicara_dinilai,
    )


def _id_speaker(id_audio, id_user, label):
    detail = db.ambil_detail_audio(id_audio, id_user)
    return next(p["id_speaker"] for p in detail["pembicara"] if p["speaker_label"] == label)


class UjiPeranPembicara(unittest.TestCase):
    """Penetapan peran Guru/Siswa oleh guru."""

    def test_peran_tersimpan_dan_tampil(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user)
        id1 = _id_speaker(id_audio, id_user, "Pembicara 1")
        id2 = _id_speaker(id_audio, id_user, "Pembicara 2")

        r = c.post(f"/histori-content/{id_audio}/peran", data={
            f"peran_{id1}": "Siswa", f"peran_{id2}": "Guru",
        }, follow_redirects=False)
        self.assertEqual(r.status_code, 303)

        detail = db.ambil_detail_audio(id_audio, id_user)
        peran = {p["speaker_label"]: p["role"] for p in detail["pembicara"]}
        self.assertEqual(peran, {"Pembicara 1": "Siswa", "Pembicara 2": "Guru"})

    def test_peran_ngawur_disimpan_sebagai_belum_dilabeli(self):
        """Ejaan bebas akan membuat peringatan 'yang dinilai guru' gagal menyala."""
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user)
        id1 = _id_speaker(id_audio, id_user, "Pembicara 1")

        c.post(f"/histori-content/{id_audio}/peran", data={f"peran_{id1}": "guru "})

        detail = db.ambil_detail_audio(id_audio, id_user)
        self.assertIsNone(detail["pembicara"][0]["role"])

    def test_tidak_dapat_melabeli_milik_guru_lain(self):
        _, id_pemilik = util_uji.klien_login()
        id_audio = _simpan(id_pemilik)
        id1 = _id_speaker(id_audio, id_pemilik, "Pembicara 1")

        penyusup, _ = util_uji.klien_login()
        r = penyusup.post(f"/histori-content/{id_audio}/peran",
                          data={f"peran_{id1}": "Siswa"}, follow_redirects=False)
        self.assertEqual(r.status_code, 404)
        self.assertIsNone(db.ambil_detail_audio(id_audio, id_pemilik)["pembicara"][0]["role"])

    def test_pembicara_rekaman_lain_tidak_ikut_berubah(self):
        """id_speaker dari rekaman lain tidak boleh tersunting lewat formulir rakitan."""
        c, id_user = util_uji.klien_login()
        id_a = _simpan(id_user)
        id_b = _simpan(id_user)
        id_speaker_b = _id_speaker(id_b, id_user, "Pembicara 1")

        c.post(f"/histori-content/{id_a}/peran", data={f"peran_{id_speaker_b}": "Siswa"})

        detail_b = db.ambil_detail_audio(id_b, id_user)
        self.assertIsNone(detail_b["pembicara"][0]["role"])


class UjiPeringatanSalahNilai(unittest.TestCase):
    """Keadaan berbahaya harus terbaca di halaman, bukan hanya tersimpan."""

    def test_menilai_guru_memunculkan_peringatan(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, pembicara_dinilai="Pembicara 1")
        id1 = _id_speaker(id_audio, id_user, "Pembicara 1")
        c.post(f"/histori-content/{id_audio}/peran", data={f"peran_{id1}": "Guru"})

        r = c.get(f"/histori-content/{id_audio}")
        self.assertIn("Yang dinilai adalah GURU", r.text)

    def test_menilai_siswa_tidak_memunculkan_peringatan(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, pembicara_dinilai="Pembicara 1")
        id1 = _id_speaker(id_audio, id_user, "Pembicara 1")
        c.post(f"/histori-content/{id_audio}/peran", data={f"peran_{id1}": "Siswa"})

        r = c.get(f"/histori-content/{id_audio}")
        self.assertNotIn("Yang dinilai adalah GURU", r.text)
        self.assertIn("Yang dinilai: Pembicara 1", r.text)

    def test_belum_dilabeli_diberi_pengingat(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, pembicara_dinilai="Pembicara 1")

        r = c.get(f"/histori-content/{id_audio}")
        self.assertIn("Belum dipastikan siapa yang dinilai", r.text)

    def test_gabung_semua_pembicara_diberi_peringatan(self):
        """pembicara_dinilai=None berarti ucapan guru ikut masuk ke skor siswa."""
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, pembicara_dinilai=None)

        detail = db.ambil_detail_audio(id_audio, id_user)
        self.assertIsNone(detail["dinilai"])

        r = c.get(f"/histori-content/{id_audio}")
        self.assertIn("menggabungkan SELURUH pembicara", r.text)


class UjiNilaiUlang(unittest.TestCase):
    """Penilaian ulang memakai pembicara yang benar."""

    HASIL_BARU = {
        "skor": {"relevansi": 2, "konsep": 2, "kelengkapan": 1, "koherensi": 2},
        "skor_akhir": 1.75,
        "umpan_balik": "Jawaban terlalu singkat.",
    }

    def test_nilai_ulang_mengganti_skor_dan_mencatat_pembicara(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, pembicara_dinilai="Pembicara 1")
        id2 = _id_speaker(id_audio, id_user, "Pembicara 2")

        with mock.patch("main.evaluate_response", return_value=self.HASIL_BARU) as tiruan:
            r = c.post(f"/histori-content/{id_audio}/nilai-ulang",
                       data={"id_speaker": id2}, follow_redirects=False)
        self.assertEqual(r.status_code, 303)

        # Yang dinilai harus teks Pembicara 2, bukan teks pembicara sebelumnya.
        teks_dikirim = tiruan.call_args[0][1]
        self.assertIn("Bagus, lanjutkan", teks_dikirim)
        self.assertNotIn("Fotosintesis", teks_dikirim)

        detail = db.ambil_detail_audio(id_audio, id_user)
        self.assertAlmostEqual(detail["penilaian"]["score"], 1.75)
        self.assertEqual(detail["dinilai"]["speaker_label"], "Pembicara 2")

    def test_nilai_ulang_tidak_meninggalkan_dua_baris_penilaian(self):
        """Dua baris pada audio yang sama membuat ekspor menghitung ganda."""
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user)
        id2 = _id_speaker(id_audio, id_user, "Pembicara 2")

        with mock.patch("main.evaluate_response", return_value=self.HASIL_BARU):
            c.post(f"/histori-content/{id_audio}/nilai-ulang", data={"id_speaker": id2})

        with db.get_conn() as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM assessment WHERE id_audio = ?", (id_audio,)
            ).fetchone()["n"]
        self.assertEqual(n, 1)

    def test_penilaian_gagal_tidak_menghapus_skor_lama(self):
        from evaluator import EvaluationError

        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user)
        id2 = _id_speaker(id_audio, id_user, "Pembicara 2")

        with mock.patch("main.evaluate_response",
                        side_effect=EvaluationError("endpoint mati")):
            r = c.post(f"/histori-content/{id_audio}/nilai-ulang",
                       data={"id_speaker": id2})

        self.assertIn("Penilaian ulang GAGAL", r.text)
        detail = db.ambil_detail_audio(id_audio, id_user)
        self.assertAlmostEqual(detail["penilaian"]["score"], 3.5)
        self.assertEqual(detail["dinilai"]["speaker_label"], "Pembicara 1")

    def test_nilai_ulang_tanpa_topik_ditolak_dengan_pesan_jelas(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, topik=None)
        id2 = _id_speaker(id_audio, id_user, "Pembicara 2")

        with mock.patch("main.evaluate_response") as tiruan:
            r = c.post(f"/histori-content/{id_audio}/nilai-ulang",
                       data={"id_speaker": id2})

        self.assertIn("butuh topik", r.text)
        tiruan.assert_not_called()

    def test_tidak_dapat_menilai_ulang_milik_guru_lain(self):
        _, id_pemilik = util_uji.klien_login()
        id_audio = _simpan(id_pemilik)
        id2 = _id_speaker(id_audio, id_pemilik, "Pembicara 2")

        penyusup, _ = util_uji.klien_login()
        with mock.patch("main.evaluate_response", return_value=self.HASIL_BARU) as tiruan:
            r = penyusup.post(f"/histori-content/{id_audio}/nilai-ulang",
                              data={"id_speaker": id2}, follow_redirects=False)

        self.assertEqual(r.status_code, 404)
        tiruan.assert_not_called()
        self.assertAlmostEqual(
            db.ambil_detail_audio(id_audio, id_pemilik)["penilaian"]["score"], 3.5)


if __name__ == "__main__":
    unittest.main()
