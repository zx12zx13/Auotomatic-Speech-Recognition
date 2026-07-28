"""Uji impor seluruh modul — penjaga terhadap acuan yang tertinggal.

Ditambahkan setelah `konsistensi.py` ditemukan rusak: modul itu masih mengimpor
`GEMINI_MODEL` dari `evaluator.py`, nama yang lenyap ketika evaluator berpindah
dari Gemini ke endpoint yang kompatibel dengan OpenAI. Kerusakannya tidak
tertangkap suite mana pun karena `konsistensi.py` dan `uat_hitung.py` adalah
skrip baris perintah yang belum punya uji sendiri, sehingga kesalahannya baru
akan terlihat saat dijalankan untuk mengambil data penelitian — waktu yang
paling buruk untuk menemukannya.

Uji ini tidak memeriksa perilaku, hanya memastikan setiap modul masih dapat
dimuat. Itu sudah cukup untuk menangkap seluruh acuan nama yang tertinggal
setelah penggantian serupa berikutnya.
"""
import importlib
import os
import unittest

# `app` sengaja tidak dimasukkan: mengimpornya memuat Whisper dan pyannote,
# dan modul itu sudah tercakup lewat tests/util_uji.py.
MODUL = [
    "database",
    "evaluator",
    "konsistensi",
    "main",
    "objektivitas",
    "run_server",
    "session",
    "text_preprocessing",
    "uat_hitung",
]


class UjiImporModul(unittest.TestCase):
    """Setiap modul harus dapat diimpor tanpa melempar exception."""

    def test_seluruh_modul_dapat_diimpor(self):
        # `run_server` memanggil os.chdir saat diimpor; direktori kerja
        # dikembalikan agar uji lain yang memakai path relatif tidak terganggu.
        cwd = os.getcwd()
        try:
            for nama in MODUL:
                with self.subTest(modul=nama):
                    importlib.import_module(nama)
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
