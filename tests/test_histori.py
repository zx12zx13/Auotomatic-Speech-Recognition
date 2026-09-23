"""Uji histori: pemutaran rekaman, lama proses, penyuntingan, dan penghapusan.

Menguji tiga hal yang tidak boleh keliru pada halaman histori:

1. KEPEMILIKAN. Rekaman suara siswa adalah data pribadi. Setiap rute yang
   menyajikan, menyunting, atau menghapus data harus menolak pengguna lain,
   bukan sekadar menyembunyikan tautannya di antarmuka.

2. JEJAK AUDIT. Suntingan guru tidak boleh menimpa keluaran sistem. Bila
   tertimpa, tidak ada lagi cara membuktikan apa yang sesungguhnya dihasilkan
   sistem, dan pengukuran akurasi ASR kehilangan rujukan.

3. KEBERSIHAN PENGHAPUSAN. Menghapus satu proses harus ikut membuang seluruh
   data turunannya. Segmen atau penilaian yatim akan mengacaukan hitungan
   statistik dan ekspor data penelitian.
"""
import os
import unittest

from tests import util_uji
from tests.util_uji import db


def _buat_rekaman_uji(nama="rekaman_uji.wav", isi=b"RIFF-palsu-untuk-uji"):
    """Menulis berkas tiruan di direktori sementara uji, mengembalikan lokasinya.

    Isinya tidak perlu audio sungguhan: yang diuji adalah penyajian berkas dan
    pemeriksaan kepemilikannya, bukan pemutarannya.
    """
    lokasi = os.path.join(util_uji.DIR_UJI, nama)
    with open(lokasi, "wb") as f:
        f.write(isi)
    return lokasi


def _simpan(id_user, filepath=None, waktu_proses=None, topik="Jelaskan fotosintesis.",
            waktu_tahap=None):
    return db.simpan_hasil(
        id_user=id_user,
        filename="ujian_lisan.wav",
        durasi=95.0,
        segmen=util_uji.SEGMEN_CONTOH,
        full_text="Fotosintesis adalah ... Bagus, lanjutkan.",
        corrected_text="Fotosintesis adalah proses tumbuhan membuat makanan.",
        llm_text="Fotosintesis adalah proses tumbuhan membuat makanan sendiri.",
        topik=topik,
        hasil_evaluasi=util_uji.HASIL_EVALUASI_CONTOH,
        pembicara_dinilai="Pembicara 1",
        filepath=filepath,
        waktu_proses=waktu_proses,
        waktu_tahap=waktu_tahap,
    )


class UjiRekamanHistori(unittest.TestCase):
    """Penyajian berkas rekaman dari halaman histori."""

    def test_rekaman_dapat_diputar_pemiliknya(self):
        c, id_user = util_uji.klien_login()
        lokasi = _buat_rekaman_uji("milik_pemilik.wav")
        id_audio = _simpan(id_user, filepath=lokasi)

        r = c.get(f"/histori/audio/{id_audio}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"RIFF-palsu-untuk-uji")

    def test_rekaman_guru_lain_tidak_dapat_diambil(self):
        """Menebak id_audio tidak boleh membuka rekaman milik guru lain."""
        _, id_pemilik = util_uji.klien_login()
        id_audio = _simpan(id_pemilik, filepath=_buat_rekaman_uji("rahasia.wav"))

        penyusup, _ = util_uji.klien_login()
        r = penyusup.get(f"/histori/audio/{id_audio}")
        self.assertEqual(r.status_code, 404)
        self.assertNotIn(b"RIFF-palsu", r.content)

    def test_rekaman_tanpa_login_ditolak(self):
        from fastapi.testclient import TestClient

        _, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, filepath=_buat_rekaman_uji("tanpa_login.wav"))

        r = TestClient(util_uji.main.app).get(f"/histori/audio/{id_audio}")
        self.assertEqual(r.status_code, 403)

    def test_proses_lama_tanpa_salinan_rekaman_dijawab_jelas(self):
        """Proses sebelum fitur ini ada tidak punya berkas; jangan galat 500."""
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, filepath=None)

        r = c.get(f"/histori/audio/{id_audio}")
        self.assertEqual(r.status_code, 404)

        # Halamannya harus mengatakannya terus terang, bukan menampilkan
        # pemutar audio yang diam saja saat ditekan.
        halaman = c.get(f"/histori-content/{id_audio}")
        self.assertIn("Rekaman tidak tersimpan", halaman.text)
        self.assertNotIn(f'src="/histori/audio/{id_audio}"', halaman.text)

    def test_berkas_terhapus_dari_disk_dijawab_404(self):
        """Basis data dapat menunjuk berkas yang sudah lenyap dari disk."""
        c, id_user = util_uji.klien_login()
        lokasi = _buat_rekaman_uji("akan_dihapus.wav")
        id_audio = _simpan(id_user, filepath=lokasi)
        os.remove(lokasi)

        r = c.get(f"/histori/audio/{id_audio}")
        self.assertEqual(r.status_code, 404)

    def test_pemutar_muncul_bila_rekaman_ada(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, filepath=_buat_rekaman_uji("ada.wav"))

        r = c.get(f"/histori-content/{id_audio}")
        self.assertIn("<audio", r.text)
        self.assertIn(f"/histori/audio/{id_audio}", r.text)


class UjiLamaProses(unittest.TestCase):
    """Lama pemrosesan dicatat terpisah dari durasi rekaman."""

    def test_lama_proses_tersimpan_dan_tampil(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, waktu_proses=664.2)

        detail = db.ambil_detail_audio(id_audio, id_user)
        self.assertAlmostEqual(detail["audio"]["processing_time"], 664.2)
        # Durasi rekaman tidak boleh ikut tertimpa lama proses.
        self.assertAlmostEqual(detail["audio"]["duration"], 95.0)

        r = c.get("/histori-content")
        self.assertIn("Lama Proses", r.text)
        self.assertIn("11 mnt 4 dtk", r.text)   # 664 detik

    def test_proses_lama_tanpa_catatan_waktu_tampil_sebagai_strip(self):
        """Data lama tidak punya angka ini; jangan diisi angka karangan."""
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, waktu_proses=None)

        detail = db.ambil_detail_audio(id_audio, id_user)
        self.assertIsNone(detail["audio"]["processing_time"])

        r = c.get(f"/histori-content/{id_audio}")
        self.assertIn("Lama proses -", r.text)


class UjiWaktuPerTahap(unittest.TestCase):
    """Lama tiap tahap dicatat terpisah dari totalnya.

    Satu angka gabungan tidak dapat menjawab tahap mana yang lambat, padahal
    itulah yang dibahas pada laporan. Transkripsi di CPU berjalan berkali lipat
    lebih lama daripada tahap lain, dan itu harus terbaca sendiri agar
    kesimpulan tentang kelayakan pakai sistem tidak salah menuding.
    """

    TAHAP = {"audio": 12.5, "transcribe": 480.0, "diarize": 150.0,
             "text": 0.05, "evaluate": 21.6}

    def test_tiap_tahap_tersimpan_terpisah(self):
        _, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, waktu_proses=664.2, waktu_tahap=self.TAHAP)

        a = db.ambil_detail_audio(id_audio, id_user)["audio"]
        self.assertAlmostEqual(a["time_transcribe"], 480.0)
        self.assertAlmostEqual(a["time_diarize"], 150.0)
        self.assertAlmostEqual(a["time_text"], 0.05)
        self.assertAlmostEqual(a["time_evaluate"], 21.6)
        self.assertAlmostEqual(a["time_audio"], 12.5)
        # Total tetap ada dan tidak tertimpa salah satu tahap.
        self.assertAlmostEqual(a["processing_time"], 664.2)

    def test_rincian_tampil_di_halaman_detail(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, waktu_proses=664.2, waktu_tahap=self.TAHAP)

        r = c.get(f"/histori-content/{id_audio}")
        self.assertIn("Rincian Waktu Proses", r.text)
        self.assertIn("Transkripsi (Whisper)", r.text)
        self.assertIn("480.0 dtk", r.text)
        # Bagian terhadap total ikut ditampilkan: 480/664,2 = 72%.
        self.assertIn("72%", r.text)

    def test_proses_lama_tanpa_rincian_tidak_menampilkan_tabel_kosong(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, waktu_proses=100.0, waktu_tahap=None)

        r = c.get(f"/histori-content/{id_audio}")
        self.assertNotIn("Rincian Waktu Proses", r.text)


class UjiSkalaRubrik(unittest.TestCase):
    """Skala rubrik dicatat pada tiap penilaian.

    Skala penelitian ini pernah berubah dari 1-4 menjadi 1-5. Skor 4 pada dua
    skala itu bukan nilai yang sama, sehingga tanpa pencatatan skala, data
    lama dan baru akan tercampur dalam satu perhitungan dan hasilnya tidak sah.
    """

    def test_penilaian_baru_mencatat_skala_berlaku(self):
        from evaluator import SKALA_MAKS

        _, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user)
        p = db.ambil_detail_audio(id_audio, id_user)["penilaian"]
        self.assertEqual(p["skala_maks"], SKALA_MAKS)

    def test_penilaian_ulang_juga_mencatat_skala(self):
        from evaluator import SKALA_MAKS

        _, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user)
        id_speaker = db.ambil_detail_audio(id_audio, id_user)["pembicara"][0]["id_speaker"]
        db.ganti_penilaian(id_audio, id_user, id_speaker, "Topik",
                           util_uji.HASIL_EVALUASI_CONTOH)

        p = db.ambil_detail_audio(id_audio, id_user)["penilaian"]
        self.assertEqual(p["skala_maks"], SKALA_MAKS)

    def test_skala_lama_ditandai_di_halaman(self):
        """Penilaian berskala lama harus terbaca sebagai skala lama."""
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user)
        with db.get_conn() as conn:
            conn.execute("UPDATE assessment SET skala_maks = 4 WHERE id_audio = ?",
                         (id_audio,))

        r = c.get(f"/histori-content/{id_audio}")
        self.assertIn("skala lama 1", r.text)
        self.assertIn("3.50 / 4", r.text)

    def test_rata_rata_tidak_dihitung_bila_skala_tercampur(self):
        """Merata-ratakan lintas skala menghasilkan angka tanpa arti."""
        _, id_user = util_uji.klien_login()
        id_a = _simpan(id_user)
        _simpan(id_user)
        with db.get_conn() as conn:
            conn.execute("UPDATE assessment SET skala_maks = 4 WHERE id_audio = ?",
                         (id_a,))

        stat = db.statistik_user(id_user)
        self.assertTrue(stat["skala_tercampur"])
        self.assertIsNone(stat["rata_skor"])
        self.assertEqual(stat["skala"], [4, 5])

    def test_rata_rata_dihitung_bila_skala_seragam(self):
        _, id_user = util_uji.klien_login()
        _simpan(id_user)
        _simpan(id_user)

        stat = db.statistik_user(id_user)
        self.assertFalse(stat["skala_tercampur"])
        self.assertAlmostEqual(stat["rata_skor"], 3.5)


class UjiSuntingHistori(unittest.TestCase):
    """Penyuntingan manual guru atas transkrip dan topik."""

    def test_suntingan_tidak_menimpa_keluaran_sistem(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user)

        r = c.post(f"/histori-content/{id_audio}/sunting", data={
            "topik": "Jelaskan fotosintesis.",
            "transkrip": "Fotosintesis adalah proses tumbuhan membuat makanannya sendiri.",
        }, follow_redirects=False)
        self.assertEqual(r.status_code, 303)

        t = db.ambil_detail_audio(id_audio, id_user)["transkrip"]
        self.assertIn("makanannya sendiri", t["edited_text"])
        self.assertIsNotNone(t["edited_at"])
        # Inti uji ini: keluaran sistem harus tetap utuh sebagai pembanding.
        self.assertEqual(
            t["corrected_text"], "Fotosintesis adalah proses tumbuhan membuat makanan."
        )
        self.assertEqual(
            t["llm_text"], "Fotosintesis adalah proses tumbuhan membuat makanan sendiri."
        )

    def test_suntingan_tampil_di_halaman_detail(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user)
        c.post(f"/histori-content/{id_audio}/sunting",
               data={"topik": "", "transkrip": "Teks hasil betulan guru."})

        r = c.get(f"/histori-content/{id_audio}")
        self.assertIn("Transkrip Hasil Suntingan Guru", r.text)
        self.assertIn("Teks hasil betulan guru.", r.text)

    def test_suntingan_kosong_membatalkan_suntingan(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user)
        c.post(f"/histori-content/{id_audio}/sunting",
               data={"topik": "", "transkrip": "Betulan pertama."})
        c.post(f"/histori-content/{id_audio}/sunting",
               data={"topik": "", "transkrip": "   "})

        t = db.ambil_detail_audio(id_audio, id_user)["transkrip"]
        self.assertIsNone(t["edited_text"])
        self.assertIsNone(t["edited_at"])

    def test_topik_dapat_disunting(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user, topik="Topik lama.")
        c.post(f"/histori-content/{id_audio}/sunting",
               data={"topik": "Topik baru yang lebih jelas.", "transkrip": "apa pun"})

        p = db.ambil_detail_audio(id_audio, id_user)["penilaian"]
        self.assertEqual(p["topik"], "Topik baru yang lebih jelas.")
        # Skor tidak boleh ikut berubah: skor adalah keluaran sistem yang
        # sedang diteliti, dan halaman sunting tidak menjalankan ulang penilaian.
        self.assertAlmostEqual(p["score"], 3.5)

    def test_tidak_dapat_menyunting_milik_guru_lain(self):
        _, id_pemilik = util_uji.klien_login()
        id_audio = _simpan(id_pemilik)

        penyusup, _ = util_uji.klien_login()
        r = penyusup.post(f"/histori-content/{id_audio}/sunting",
                          data={"topik": "dibajak", "transkrip": "dibajak"},
                          follow_redirects=False)
        self.assertEqual(r.status_code, 404)

        d = db.ambil_detail_audio(id_audio, id_pemilik)
        self.assertIsNone(d["transkrip"]["edited_text"])
        self.assertEqual(d["penilaian"]["topik"], "Jelaskan fotosintesis.")


class UjiHapusHistori(unittest.TestCase):
    """Penghapusan satu proses beserta seluruh data turunannya."""

    def test_hapus_membuang_seluruh_data_turunan(self):
        c, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user)

        r = c.post(f"/histori-content/{id_audio}/hapus", follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertIsNone(db.ambil_detail_audio(id_audio, id_user))

        # Baris yatim akan mengacaukan statistik dan ekspor data penelitian.
        with db.get_conn() as conn:
            for tabel in ("assessment", "speaker"):
                sisa = conn.execute(
                    f"SELECT COUNT(*) AS n FROM {tabel} WHERE id_audio = ?", (id_audio,)
                ).fetchone()["n"]
                self.assertEqual(sisa, 0, f"{tabel} masih menyisakan baris yatim")
            sisa_transkrip = conn.execute(
                "SELECT COUNT(*) AS n FROM transcript WHERE id_audio = ?", (id_audio,)
            ).fetchone()["n"]
            self.assertEqual(sisa_transkrip, 0)
            sisa_segmen = conn.execute(
                "SELECT COUNT(*) AS n FROM segment sg JOIN speaker sp"
                " ON sp.id_speaker = sg.id_speaker WHERE sp.id_audio = ?", (id_audio,)
            ).fetchone()["n"]
            self.assertEqual(sisa_segmen, 0)

    def test_hapus_juga_membuang_berkas_rekaman(self):
        c, id_user = util_uji.klien_login()
        lokasi = _buat_rekaman_uji("ikut_terhapus.wav")
        id_audio = _simpan(id_user, filepath=lokasi)

        c.post(f"/histori-content/{id_audio}/hapus")
        self.assertFalse(os.path.exists(lokasi),
                         "rekaman suara siswa harus ikut terhapus dari disk")

    def test_hapus_tidak_mengganggu_proses_lain(self):
        c, id_user = util_uji.klien_login()
        id_dihapus = _simpan(id_user)
        id_bertahan = _simpan(id_user)

        c.post(f"/histori-content/{id_dihapus}/hapus")
        self.assertIsNone(db.ambil_detail_audio(id_dihapus, id_user))
        self.assertIsNotNone(db.ambil_detail_audio(id_bertahan, id_user))

    def test_tidak_dapat_menghapus_milik_guru_lain(self):
        _, id_pemilik = util_uji.klien_login()
        id_audio = _simpan(id_pemilik)

        penyusup, _ = util_uji.klien_login()
        r = penyusup.post(f"/histori-content/{id_audio}/hapus", follow_redirects=False)
        self.assertEqual(r.status_code, 404)
        self.assertIsNotNone(db.ambil_detail_audio(id_audio, id_pemilik))

    def test_hapus_tanpa_login_ditolak(self):
        from fastapi.testclient import TestClient

        _, id_user = util_uji.klien_login()
        id_audio = _simpan(id_user)

        r = TestClient(util_uji.main.app).post(f"/histori-content/{id_audio}/hapus")
        self.assertEqual(r.status_code, 403)
        self.assertIsNotNone(db.ambil_detail_audio(id_audio, id_user))


if __name__ == "__main__":
    unittest.main()
