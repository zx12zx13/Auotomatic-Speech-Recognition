"""Penyimpanan sesi aktif yang dipakai bersama oleh main.py dan app.py.

Modul terpisah karena main.py mengimpor app.py; bila sesi disimpan di main.py,
app.py tidak dapat membacanya tanpa menimbulkan impor melingkar.

Sesi disimpan di memori: proposal tidak memuat tabel sesi, sehingga pengguna
perlu login ulang setelah server dimulai kembali. Data hasil evaluasi tetap
tersimpan di basis data dan tidak terpengaruh.
"""

# token acak -> id_user
sesi_aktif = {}


def id_user_dari_token(token):
    """Mengembalikan id_user pemilik token sesi, atau None bila tidak sah."""
    if not token:
        return None
    return sesi_aktif.get(token)
