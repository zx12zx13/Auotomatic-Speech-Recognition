"""Perhitungan User Acceptance Testing (UAT) sesuai §3.2.5 proposal.

Rumus (Tabel 3.9-3.10):  P = (ΣX / ΣXmaks) × 100
  ΣX     = jumlah total skor seluruh responden
  ΣXmaks = jumlah pertanyaan × bobot tertinggi (4) × jumlah responden

Pemakaian:
  python uat_hitung.py --template          -> membuat uat_jawaban.csv kosong
  python uat_hitung.py uat_jawaban.csv     -> menghitung hasil UAT

Berkas CSV diisi MANUAL dari kuesioner guru sungguhan. Skrip ini hanya
menghitung; ia tidak dan tidak boleh membuat data jawaban.
"""
import csv
import sys

BOBOT = {"A": 4, "B": 3, "C": 2, "D": 1}
JUMLAH_PERTANYAAN = 10
BOBOT_TERTINGGI = 4

PERTANYAAN = [
    # Aspek Sistem (System)
    "Apakah sistem dapat menerima dan memproses audio respons lisan dengan baik?",
    "Apakah sistem menampilkan hasil transkrip dengan jelas?",
    "Apakah sistem memberikan skor evaluasi secara otomatis dengan baik?",
    "Apakah sistem berjalan tanpa error selama digunakan?",
    # Aspek Pengguna (User)
    "Apakah sistem membantu Bapak/Ibu dalam menilai ujian lisan siswa?",
    "Apakah fitur histori memudahkan dalam melihat kembali hasil evaluasi?",
    "Apakah sistem membantu meningkatkan objektivitas penilaian?",
    # Aspek Antarmuka (Interface)
    "Apakah tampilan sistem mudah dipahami?",
    "Apakah informasi skor dan umpan balik mudah dibaca?",
    "Apakah navigasi antar menu mudah digunakan?",
]

ASPEK = {
    "Sistem": range(0, 4),
    "Pengguna": range(4, 7),
    "Antarmuka": range(7, 10),
}


def buat_template(path="uat_jawaban.csv"):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["responden"] + [f"q{i+1}" for i in range(JUMLAH_PERTANYAAN)])
        w.writerow(["(nama/kode guru)"] + ["A/B/C/D"] * JUMLAH_PERTANYAAN)
    print(f"Template dibuat: {path}")
    print("Isi satu baris per responden. Jawaban memakai huruf A, B, C, atau D")
    print("(A=Sangat Baik/4, B=Baik/3, C=Cukup/2, D=Kurang/1), lalu jalankan:")
    print(f"  python uat_hitung.py {path}")


def baca_jawaban(path):
    """Membaca CSV jawaban. Baris petunjuk (berisi 'A/B/C/D') dilewati."""
    responden = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        pembaca = csv.DictReader(f)
        kolom = [f"q{i+1}" for i in range(JUMLAH_PERTANYAAN)]
        hilang = [k for k in kolom if k not in (pembaca.fieldnames or [])]
        if hilang:
            raise SystemExit(f"Kolom {', '.join(hilang)} tidak ada di {path}.")
        for nomor, baris in enumerate(pembaca, start=2):
            jawaban = [str(baris[k] or "").strip().upper() for k in kolom]
            if "A/B/C/D" in jawaban:
                continue  # baris petunjuk dari template
            if all(j == "" for j in jawaban):
                continue  # baris kosong
            for k, j in zip(kolom, jawaban):
                if j not in BOBOT:
                    raise SystemExit(
                        f"Baris {nomor} kolom {k}: jawaban {j!r} tidak sah. "
                        f"Gunakan salah satu dari {', '.join(BOBOT)}."
                    )
            responden.append({
                "nama": (baris.get("responden") or f"Responden-{nomor-1}").strip(),
                "skor": [BOBOT[j] for j in jawaban],
            })
    return responden


def hitung(path):
    responden = baca_jawaban(path)
    if not responden:
        raise SystemExit(f"Tidak ada baris jawaban terisi di {path}.")

    n = len(responden)
    total = sum(sum(r["skor"]) for r in responden)
    maks = JUMLAH_PERTANYAAN * BOBOT_TERTINGGI * n
    p = total / maks * 100

    print(f"Jumlah responden : {n}")
    for r in responden:
        print(f"  - {r['nama']}: {sum(r['skor'])} / {JUMLAH_PERTANYAAN * BOBOT_TERTINGGI}")
    # Label ASCII agar aman dicetak di konsol Windows (cp1252).
    print(f"\nSigmaX     = {total}")
    print(f"SigmaXmaks = {JUMLAH_PERTANYAAN} x {BOBOT_TERTINGGI} x {n} = {maks}")
    print(f"P          = ({total} / {maks}) x 100 = {p:.2f}%")

    print("\nRincian per aspek:")
    for nama, indeks in ASPEK.items():
        sub_total = sum(r["skor"][i] for r in responden for i in indeks)
        sub_maks = len(indeks) * BOBOT_TERTINGGI * n
        print(f"  {nama:<10}: {sub_total}/{sub_maks} = {sub_total / sub_maks * 100:.2f}%")

    print("\nRincian per pertanyaan:")
    for i, teks in enumerate(PERTANYAAN):
        sub_total = sum(r["skor"][i] for r in responden)
        sub_maks = BOBOT_TERTINGGI * n
        print(f"  q{i+1:<2} {sub_total}/{sub_maks} ({sub_total / sub_maks * 100:.0f}%) - {teks}")

    print(
        "\nCatatan: proposal tidak menetapkan tabel kategori interpretasi "
        "persentase.\nTentukan kriteria kelayakan (mis. ambang penerimaan) "
        "bersama pembimbing\nsebelum menuliskan kesimpulan di BAB IV."
    )


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
    elif sys.argv[1] == "--template":
        buat_template(sys.argv[2] if len(sys.argv) > 2 else "uat_jawaban.csv")
    else:
        hitung(sys.argv[1])
