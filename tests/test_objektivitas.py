"""Uji perhitungan objektivitas (Iterasi 8).

Rumus Kappa ditulis sendiri di objektivitas.py agar transparan dan dapat
dipertanggungjawabkan di BAB IV. Kebenarannya diverifikasi dua arah:
  1. Terhadap contoh yang dihitung tangan (nilai Kappa diketahui).
  2. Terhadap sklearn.metrics.cohen_kappa_score sebagai pembanding
     independen, termasuk varian quadratic weighted.
"""
import os
import random
import unittest

from tests import util_uji  # menyiapkan sys.path + DB_PATH sementara

import objektivitas as ob


class UjiRumusKappa(unittest.TestCase):
    """Verifikasi rumus terhadap nilai yang diketahui dan terhadap sklearn."""

    def test_contoh_hitung_tangan(self):
        # Matriks kontingensi klasik 2 kategori (dipetakan ke skor 1 dan 2):
        #            guru=1  guru=2
        #   sistem=1   20      5
        #   sistem=2   10      15
        # Po = (20+15)/50 = 0.70
        # Pe = (25/50)(30/50) + (25/50)(20/50) = 0.30 + 0.20 = 0.50
        # kappa = (0.70-0.50)/(1-0.50) = 0.40
        sistem = [1] * 25 + [2] * 25
        guru = [1] * 20 + [2] * 5 + [1] * 10 + [2] * 15
        self.assertAlmostEqual(ob.cohen_kappa(sistem, guru), 0.40, places=10)
        self.assertAlmostEqual(ob.kesepakatan_persis(sistem, guru), 0.70, places=10)

    def test_kesepakatan_sempurna(self):
        sistem = [1, 2, 3, 4, 1, 2, 3, 4]
        self.assertAlmostEqual(ob.cohen_kappa(sistem, list(sistem)), 1.0, places=10)
        self.assertAlmostEqual(ob.cohen_kappa(sistem, list(sistem), berbobot=True), 1.0, places=10)
        self.assertEqual(ob.kesepakatan_persis(sistem, list(sistem)), 1.0)

    def test_kappa_tidak_terdefinisi_dilaporkan_none(self):
        # Kedua penilai memberi skor identik untuk SELURUH sampel -> Pe = 1.
        # Harus None (tidak terdefinisi), bukan dipaksa 0 atau 1.
        sistem = [4] * 10
        guru = [4] * 10
        self.assertIsNone(ob.cohen_kappa(sistem, guru))
        self.assertIsNone(ob.cohen_kappa(sistem, guru, berbobot=True))
        self.assertEqual(ob.interpretasi_kappa(None), "tidak terdefinisi")

    def test_cocok_dengan_sklearn_tanpa_bobot(self):
        from sklearn.metrics import cohen_kappa_score
        rng = random.Random(42)
        for _ in range(50):
            n = rng.randint(10, 60)
            sistem = [rng.randint(1, 4) for _ in range(n)]
            guru = [rng.randint(1, 4) for _ in range(n)]
            punya = ob.cohen_kappa(sistem, guru)
            acuan = cohen_kappa_score(sistem, guru, labels=ob.KATEGORI)
            self.assertAlmostEqual(punya, acuan, places=9)

    def test_cocok_dengan_sklearn_quadratic_weighted(self):
        from sklearn.metrics import cohen_kappa_score
        rng = random.Random(7)
        for _ in range(50):
            n = rng.randint(10, 60)
            sistem = [rng.randint(1, 4) for _ in range(n)]
            # Skor guru berkorelasi dengan sistem agar menyerupai data nyata.
            guru = [min(4, max(1, s + rng.choice([-1, 0, 0, 1]))) for s in sistem]
            punya = ob.cohen_kappa(sistem, guru, berbobot=True)
            acuan = cohen_kappa_score(sistem, guru, weights="quadratic",
                                      labels=ob.KATEGORI)
            self.assertAlmostEqual(punya, acuan, places=9)

    def test_qwk_lebih_tinggi_dari_kappa_saat_selisih_kecil(self):
        # QWK memberi hukuman lebih ringan untuk selisih 1 tingkat.
        sistem = [1, 2, 3, 4, 2, 3, 1, 4, 3, 2]
        guru = [2, 3, 4, 3, 1, 2, 2, 3, 4, 1]  # selalu meleset 1 tingkat
        self.assertGreater(ob.cohen_kappa(sistem, guru, berbobot=True),
                           ob.cohen_kappa(sistem, guru, berbobot=False))

    def test_pearson_cocok_dengan_scipy(self):
        from scipy.stats import pearsonr
        rng = random.Random(1)
        for _ in range(20):
            n = rng.randint(10, 40)
            a = [rng.randint(1, 4) for _ in range(n)]
            b = [min(4, max(1, x + rng.choice([-1, 0, 1]))) for x in a]
            if len(set(a)) < 2 or len(set(b)) < 2:
                continue
            self.assertAlmostEqual(ob.pearson(a, b), pearsonr(a, b)[0], places=9)

    def test_pearson_tanpa_variasi_none(self):
        self.assertIsNone(ob.pearson([3, 3, 3], [1, 2, 3]))

    def test_kesepakatan_berdekatan(self):
        sistem = [1, 2, 3, 4]
        guru = [2, 2, 1, 4]  # selisih: 1, 0, 2, 0
        self.assertEqual(ob.kesepakatan_berdekatan(sistem, guru), 0.75)
        self.assertEqual(ob.kesepakatan_persis(sistem, guru), 0.5)

    def test_interpretasi_landis_koch(self):
        self.assertIn("sangat kuat", ob.interpretasi_kappa(0.85))
        self.assertIn("kuat", ob.interpretasi_kappa(0.65))
        self.assertIn("sedang", ob.interpretasi_kappa(0.50))
        self.assertIn("rendah", ob.interpretasi_kappa(0.30))
        self.assertIn("lebih buruk", ob.interpretasi_kappa(-0.1))


class UjiBacaData(unittest.TestCase):
    """Validasi berkas masukan — data cacat harus ditolak, bukan dihitung."""

    def _tulis(self, nama, isi):
        path = os.path.join(util_uji.DIR_UJI, nama)
        with open(path, "w", encoding="utf-8") as f:
            f.write(isi)
        return path

    KEPALA = ("id_audio,filename,topik,relevansi_sistem,relevansi_guru,"
              "konsep_sistem,konsep_guru,kelengkapan_sistem,kelengkapan_guru,"
              "koherensi_sistem,koherensi_guru\n")

    def test_baca_data_lengkap(self):
        p = self._tulis("ob_ok.csv", self.KEPALA +
                        "1,a.wav,Topik,4,3,3,3,2,2,3,4\n"
                        "2,b.wav,Topik,2,2,1,2,4,4,3,3\n")
        pasangan, n = ob.baca_data(p)
        self.assertEqual(n, 2)
        self.assertEqual(pasangan["relevansi"], ([4, 2], [3, 2]))
        self.assertEqual(pasangan["koherensi"], ([3, 3], [4, 3]))

    def test_baris_kosong_dilewati(self):
        p = self._tulis("ob_kosong.csv", self.KEPALA +
                        ",,,,,,,,,,\n"
                        "1,a.wav,Topik,4,3,3,3,2,2,3,4\n")
        _, n = ob.baca_data(p)
        self.assertEqual(n, 1)

    def test_baris_terisi_sebagian_ditolak(self):
        # Kolom guru belum diisi -> menghitung diam-diam akan menyesatkan.
        p = self._tulis("ob_sebagian.csv", self.KEPALA +
                        "1,a.wav,Topik,4,,3,3,2,2,3,4\n")
        with self.assertRaises(ob.DataTidakSah) as ctx:
            ob.baca_data(p)
        self.assertIn("terisi sebagian", str(ctx.exception))

    def test_skor_di_luar_skala_ditolak(self):
        p = self._tulis("ob_luar.csv", self.KEPALA +
                        "1,a.wav,Topik,5,3,3,3,2,2,3,4\n")
        with self.assertRaises(ob.DataTidakSah) as ctx:
            ob.baca_data(p)
        self.assertIn("di luar skala", str(ctx.exception))

    def test_skor_bukan_angka_ditolak(self):
        p = self._tulis("ob_teks.csv", self.KEPALA +
                        "1,a.wav,Topik,baik,3,3,3,2,2,3,4\n")
        with self.assertRaises(ob.DataTidakSah):
            ob.baca_data(p)

    def test_kolom_hilang_ditolak(self):
        p = self._tulis("ob_kolom.csv", "id_audio,filename\n1,a.wav\n")
        with self.assertRaises(ob.DataTidakSah) as ctx:
            ob.baca_data(p)
        self.assertIn("tidak ada", str(ctx.exception))

    def test_tanpa_baris_terisi_ditolak(self):
        p = self._tulis("ob_hampa.csv", self.KEPALA)
        with self.assertRaises(ob.DataTidakSah):
            ob.baca_data(p)


class UjiEksporBasisData(unittest.TestCase):
    """--ekspor menarik skor sistem dan mengosongkan kolom guru."""

    def test_ekspor_isi_kolom_sistem_kosongkan_kolom_guru(self):
        import csv as _csv
        from tests.util_uji import db

        id_user = db.buat_user(util_uji.user_unik("ob_ekspor"), "sandi")
        util_uji.simpan_evaluasi_contoh(id_user, filename="ekspor.wav")

        path = os.path.join(util_uji.DIR_UJI, "ob_ekspor.csv")
        ob.ekspor_dari_basis_data(path)

        with open(path, newline="", encoding="utf-8-sig") as f:
            baris = list(_csv.DictReader(f))

        cocok = [b for b in baris if b["filename"] == "ekspor.wav"]
        self.assertEqual(len(cocok), 1)
        b = cocok[0]
        # Skor sistem sesuai HASIL_EVALUASI_CONTOH (4, 3, 3, 4).
        self.assertEqual(b["relevansi_sistem"], "4")
        self.assertEqual(b["konsep_sistem"], "3")
        self.assertEqual(b["kelengkapan_sistem"], "3")
        self.assertEqual(b["koherensi_sistem"], "4")
        # Kolom guru WAJIB kosong: skor guru tidak boleh disarankan sistem.
        for k in ob.INDIKATOR:
            self.assertEqual(b[f"{k}_guru"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
