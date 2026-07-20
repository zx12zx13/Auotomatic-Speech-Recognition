"""Peluncur server aplikasi.

Menjalankan aplikasi penuh (login, dashboard, modul analisis) tanpa harus
mengingat perintah uvicorn:

    python run_server.py

Port dapat diubah lewat variabel lingkungan PORT (bawaan: 8000). Direktori
kerja dipindah ke folder berkas ini lebih dahulu agar path relatif
("templates", "evaluasi.db") tetap benar dari mana pun skrip dipanggil.
"""
import os

import uvicorn

os.chdir(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    port = int(os.getenv("PORT") or "8000")
    print(f"Menjalankan server di http://localhost:{port}")
    uvicorn.run("main:app", host="127.0.0.1", port=port)
