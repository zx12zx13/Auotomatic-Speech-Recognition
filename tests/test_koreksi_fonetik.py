"""Uji koreksi salah dengar ASR berbasis aturan (koreksi_fonetik.py).

Dua sisi diuji dengan bobot yang sama, dan sisi keduanya justru lebih penting:

  RECALL  -- kesalahan sungguhan berhasil dipulihkan.
  PRESISI -- kata yang SUDAH BENAR tidak ikut diubah.

Koreksi palsu lebih berbahaya daripada kesalahan yang dibiarkan. Transkrip
yang masih rusak terlihat rusak dan dapat diperiksa guru; kata benar yang
diganti kata lain justru terbaca rapi dan menyesatkan penilaian tanpa
meninggalkan jejak. Karena itu sebagian besar uji di bawah memastikan sistem
DIAM, bukan memastikan sistem mengoreksi.
"""
import unittest

from koreksi_fonetik import (
    Korektor, bentuk_fonetik, jarak_levenshtein, jarak_ternormalisasi,
    JARAK_MAKSIMUM_HEMAT, PANJANG_MINIMUM_HEMAT,
)


class UjiJarakLevenshtein(unittest.TestCase):
    """Rumus ditulis sendiri, jadi harus diverifikasi terhadap kasus dikenal."""

    def test_jarak_dasar(self):
        self.assertEqual(jarak_levenshtein("kitten", "sitting"), 3)
        self.assertEqual(jarak_levenshtein("kata", "kata"), 0)
        self.assertEqual(jarak_levenshtein("", "abc"), 3)
        self.assertEqual(jarak_levenshtein("abc", ""), 3)

    def test_jarak_simetris(self):
        self.assertEqual(jarak_levenshtein("hardware", "hater"),
                         jarak_levenshtein("hater", "hardware"))

    def test_jarak_ternormalisasi_rentang_nol_sampai_satu(self):
        self.assertEqual(jarak_ternormalisasi("kata", "kata"), 0.0)
        self.assertEqual(jarak_ternormalisasi("abc", "xyz"), 1.0)
        self.assertEqual(jarak_ternormalisasi("", ""), 0.0)


class UjiBentukFonetik(unittest.TestCase):
    """Normalisasi bunyi harus mendekatkan yang sebunyi, bukan semua kata."""

    def test_pasangan_bersuara_diruntuhkan(self):
        # b/p, d/t, g/k adalah pasangan yang paling sering tertukar pada ASR.
        self.assertEqual(bentuk_fonetik("bata"), bentuk_fonetik("pata"))
        self.assertEqual(bentuk_fonetik("gula"), bentuk_fonetik("kula"))

    def test_kesalahan_sungguhan_menjadi_berjarak_satu(self):
        """Inilah yang membuat penggabungan dua metode akhirnya bekerja."""
        for salah, benar in [("trainware", "brainware"),
                             ("pemproses", "pemroses"),
                             ("berhugungan", "berhubungan")]:
            with self.subTest(kata=salah):
                d = jarak_levenshtein(bentuk_fonetik(salah), bentuk_fonetik(benar))
                self.assertEqual(d, 1, f"{salah} -> {benar} berjarak {d}")

    def test_kata_tak_berhubungan_tetap_berjauhan(self):
        d = jarak_levenshtein(bentuk_fonetik("komputer"), bentuk_fonetik("sepeda"))
        self.assertGreater(d, 3)

    def test_digraf_diproses_sebagai_satu_bunyi(self):
        # Bila "ng" dipecah per huruf ia menjadi N+K dan kehilangan identitasnya.
        self.assertNotIn("NK", bentuk_fonetik("bangun"))

    def test_teks_kosong_tidak_meledak(self):
        self.assertEqual(bentuk_fonetik(""), "")
        self.assertEqual(bentuk_fonetik(None), "")
        self.assertEqual(bentuk_fonetik("123 !!"), "")


class UjiKorektorPresisi(unittest.TestCase):
    """Kata yang sudah benar TIDAK BOLEH diubah."""

    @classmethod
    def setUpClass(cls):
        cls.k = Korektor()

    def test_istilah_glosarium_dibiarkan(self):
        for w in ["hardware", "software", "brainware", "komputer", "monitor",
                  "prosesor", "keyboard", "memori"]:
            with self.subTest(kata=w):
                hasil, _, _ = self.k.koreksi_kata(w)
                self.assertIsNone(hasil, f"'{w}' seharusnya dibiarkan")

    def test_kata_umum_dibiarkan(self):
        for w in ["penjelasan", "kesempatan", "menghasilkan", "berhubungan",
                  "perangkat", "informasi", "pengguna", "kumpulan", "pengolah"]:
            with self.subTest(kata=w):
                hasil, _, _ = self.k.koreksi_kata(w)
                self.assertIsNone(hasil, f"'{w}' seharusnya dibiarkan")

    def test_kata_pendek_tidak_dikoreksi(self):
        """Pada kata pendek satu huruf berbeda nyaris tak berarti.

        Tanpa pembatas ini, pengujian pada transkrip sungguhan menghasilkan
        "Jadi" menjadi "Cache" -- dua kata yang tak berhubungan sama sekali.
        """
        hasil, _, alasan = self.k.koreksi_kata("Jadi")
        self.assertIsNone(hasil)
        hasil, _, _ = self.k.koreksi_kata("bel")
        self.assertIsNone(hasil)

    def test_kata_asing_tanpa_kandidat_dibiarkan(self):
        hasil, _, _ = self.k.koreksi_kata("zxqvwm")
        self.assertIsNone(hasil)

    def test_mode_hemat_memakai_ambang_ketat(self):
        """Selama kamus belum lengkap, ambangnya harus yang ketat."""
        self.assertFalse(self.k.kamus_lengkap)
        self.assertEqual(JARAK_MAKSIMUM_HEMAT, 1)
        self.assertGreaterEqual(PANJANG_MINIMUM_HEMAT, 7)


class UjiKorektorRecall(unittest.TestCase):
    """Kesalahan sungguhan harus dipulihkan."""

    @classmethod
    def setUpClass(cls):
        cls.k = Korektor()

    def test_kamus_koreksi_dikenal(self):
        for salah, benar in [("hater", "hardware"), ("trainware", "brainware"),
                             ("bait", "byte"), ("kyu", "queue")]:
            with self.subTest(kata=salah):
                hasil, lapis, _ = self.k.koreksi_kata(salah)
                self.assertEqual(hasil, benar)
                self.assertEqual(lapis, "kamus")

    def test_kamus_dikenal_mengalahkan_kemiripan(self):
        """Tanpa lapis kamus, "bait" akan menjadi "bit" -- lebih dekat
        tulisannya tetapi salah. Inilah cacat rancangan proposal yang ditutup."""
        hasil, _, _ = self.k.koreksi_kata("bait")
        self.assertEqual(hasil, "byte")
        self.assertNotEqual(hasil, "bit")

    def test_kedekatan_fonetik_indonesia(self):
        for salah, benar in [("pemproses", "pemroses"),
                             ("berhugungan", "berhubungan")]:
            with self.subTest(kata=salah):
                hasil, lapis, _ = self.k.koreksi_kata(salah)
                self.assertEqual(hasil, benar)
                self.assertEqual(lapis, "fonetik-id")

    def test_istilah_yang_llm_pun_melewatkannya(self):
        """"antipirus" -> "antivirus" tidak tertangkap koreksi LLM pada
        transkrip uji, tetapi tertangkap aturan p/v."""
        hasil, _, _ = self.k.koreksi_kata("antipirus")
        self.assertEqual(hasil, "antivirus")


class UjiKoreksiTeks(unittest.TestCase):
    """Perilaku pada teks utuh, termasuk bentuk kembaliannya."""

    @classmethod
    def setUpClass(cls):
        cls.k = Korektor()

    def test_bentuk_kembalian_sepadan_dengan_koreksi_llm(self):
        """Kedua metode harus dapat ditukar dan dibandingkan berdampingan."""
        h = self.k.koreksi_teks("Perangkat trainware adalah manusia.")
        for kunci in ("teks", "asli", "diterapkan", "catatan", "perubahan"):
            self.assertIn(kunci, h)

    def test_koreksi_diterapkan_dan_dicatat(self):
        h = self.k.koreksi_teks("Golongan ketiga adalah trainware.")
        self.assertIn("brainware", h["teks"])
        self.assertTrue(h["diterapkan"])
        self.assertIn(("trainware", "brainware"), h["perubahan"])

    def test_tanda_baca_dan_kapital_dipertahankan(self):
        h = self.k.koreksi_teks("Trainware adalah manusia.")
        self.assertIn("Brainware adalah manusia.", h["teks"])

    def test_teks_kosong(self):
        h = self.k.koreksi_teks("   ")
        self.assertFalse(h["diterapkan"])
        self.assertEqual(h["perubahan"], [])

    def test_teks_tanpa_kesalahan_tidak_berubah(self):
        asli = "Sistem komputer terdiri atas hardware, software, dan brainware."
        h = self.k.koreksi_teks(asli)
        self.assertEqual(h["teks"], asli)
        self.assertFalse(h["diterapkan"])

    def test_kata_pada_topik_guru_dilindungi(self):
        """Kata yang ditulis guru sendiri jelas bukan salah dengar."""
        k = Korektor(glosarium=["fotosintesis"],
                     dikenal={"fotosintesa": "fotosintesis"}, kata_id=[])
        h = k.koreksi_teks("Jelaskan fotosintesa itu.", topik="proses fotosintesa")
        self.assertIn("fotosintesa", h["teks"])
        self.assertEqual(h["perubahan"], [])

    def test_keterbatasan_kamus_dilaporkan(self):
        """Cakupan yang menyempit harus terbaca, bukan tersamar."""
        h = self.k.koreksi_teks("Golongan ketiga adalah trainware.")
        self.assertIn("dibatasi", h["catatan"].lower())
        self.assertIn("kamus/README.md", h["catatan"])

    def test_deterministik(self):
        """Alasan utama meninggalkan koreksi LLM: hasil yang dapat diulang."""
        teks = "Perangkat trainware dan pemproses data."
        hasil = {self.k.koreksi_teks(teks)["teks"] for _ in range(5)}
        self.assertEqual(len(hasil), 1)


if __name__ == "__main__":
    unittest.main()
