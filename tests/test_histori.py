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


def _simpan(id_user, filepath=None, waktu_proses=None, topik="Jelaskan fotosintesis."):
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
