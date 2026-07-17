"""Pengukuran objektivitas sistem terhadap penilaian manual guru (RM #2).

Membandingkan skor sistem dengan skor manual guru pada respons lisan yang
sama, mengikuti pendekatan Morris et al. (2024) pada penilaian otomatis
jawaban konstruksi.

Ukuran yang dihitung per indikator rubrik dan secara keseluruhan:
  - Persentase kesepakatan persis (exact agreement)
  - Persentase kesepakatan berdekatan (adjacent, selisih <= 1)
  - Cohen's Kappa (tanpa bobot)
  - Quadratic Weighted Kappa -- ukuran utama untuk skor rubrik ordinal,
    karena selisih 1 tingkat tidak sama buruknya dengan selisih 3 tingkat
  - Korelasi Pearson
  - Rata-rata selisih (sistem - guru), menunjukkan arah bias

Pemakaian:
  python objektivitas.py --ekspor           -> tarik skor sistem dari basis
                                               data ke objektivitas_data.csv
  python objektivitas.py --template         -> CSV kosong (bila skor sistem
                                               dicatat manual)
  python objektivitas.py objektivitas_data.csv   -> hitung

Kolom guru diisi MANUAL oleh guru yang menilai rekaman yang sama tanpa
melihat skor sistem. Skrip ini hanya menghitung; ia tidak dan tidak boleh
membuat data penilaian.

Rumus Cohen's Kappa:
    kappa = (Po - Pe) / (1 - Pe)
        Po = proporsi kesepakatan teramati
        Pe = proporsi kesepakatan yang diharapkan secara kebetulan

Rumus Quadratic Weighted Kappa:
    kappa_w = 1 - (sum(w_ij * O_ij) / sum(w_ij * E_ij))
        w_ij = (i - j)^2 / (k - 1)^2,  k = jumlah kategori skor (4)
"""
import csv
import os
import sys

SKALA_MIN, SKALA_MAKS = 1, 4
KATEGORI = list(range(SKALA_MIN, SKALA_MAKS + 1))

INDIKATOR = {
    "relevansi": "Relevansi terhadap Pertanyaan",
    "konsep": "Ketepatan Konsep",
    "kelengkapan": "Kelengkapan Isi",
    "koherensi": "Koherensi dan Alur Logika",
}

KOLOM = ["id_audio", "filename", "topik"]
for _k in INDIKATOR:
    KOLOM += [f"{_k}_sistem", f"{_k}_guru"]


class DataTidakSah(Exception):
    pass


# ==============================
# STATISTIK
# ==============================
def _matriks_kontingensi(a, b):
    """Matriks k x k dari sepasang daftar skor."""
    idx = {k: i for i, k in enumerate(KATEGORI)}
    n = len(KATEGORI)
    m = [[0] * n for _ in range(n)]
    for x, y in zip(a, b):
        m[idx[x]][idx[y]] += 1
    return m


def kesepakatan_persis(a, b):
    return sum(1 for x, y in zip(a, b) if x == y) / len(a)


def kesepakatan_berdekatan(a, b):
    return sum(1 for x, y in zip(a, b) if abs(x - y) <= 1) / len(a)


def cohen_kappa(a, b, berbobot=False):
    """Cohen's Kappa. berbobot=True -> Quadratic Weighted Kappa.

    Mengembalikan None bila Kappa tidak terdefinisi (Pe = 1), yaitu ketika
    kedua penilai memberi skor yang sama persis untuk seluruh sampel. Ini
    dilaporkan apa adanya, bukan dipaksa menjadi 0 atau 1 -- keduanya akan
    menyesatkan.
    """
    N = len(a)
    m = _matriks_kontingensi(a, b)
    n = len(KATEGORI)

    baris = [sum(m[i]) for i in range(n)]           # total penilai A
    kolom = [sum(m[i][j] for i in range(n)) for j in range(n)]  # penilai B

    if berbobot:
        w = [[((i - j) ** 2) / ((n - 1) ** 2) for j in range(n)] for i in range(n)]
    else:
        w = [[0 if i == j else 1 for j in range(n)] for i in range(n)]

    # O = proporsi teramati, E = proporsi diharapkan (perkalian marginal)
    num = sum(w[i][j] * m[i][j] for i in range(n) for j in range(n)) / N
    den = sum(w[i][j] * baris[i] * kolom[j] for i in range(n) for j in range(n)) / (N * N)

    if den == 0:
        return None  # tidak terdefinisi
    return 1 - num / den


def pearson(a, b):
    """Korelasi Pearson. None bila salah satu deret tidak punya variasi."""
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    kov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return None
    return kov / (va * vb) ** 0.5


def interpretasi_kappa(k):
    """Kategori Landis & Koch (1977). Sertakan rujukan bila dipakai di BAB IV."""
    if k is None:
        return "tidak terdefinisi"
    if k < 0.00:
        return "lebih buruk dari kebetulan (poor)"
    if k < 0.21:
        return "sangat rendah (slight)"
    if k < 0.41:
        return "rendah (fair)"
    if k < 0.61:
        return "sedang (moderate)"
    if k < 0.81:
        return "kuat (substantial)"
    return "sangat kuat (almost perfect)"


# ==============================
# BERKAS
# ==============================
def _tulis_csv(path, baris):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(KOLOM)
        for b in baris:
            w.writerow([b.get(k, "") for k in KOLOM])


def buat_template(path="objektivitas_data.csv"):
    _tulis_csv(path, [{k: "" for k in KOLOM}])
    print(f"Template dibuat: {path}")
    print("Isi satu baris per respons lisan yang dinilai.")


def ekspor_dari_basis_data(path="objektivitas_data.csv"):
    """Menarik skor sistem dari basis data; kolom guru dikosongkan.

    Alat riset luring milik peneliti, dijalankan langsung atas basis datanya
    sendiri. Sengaja TIDAK diberi rute web dan tidak dipakai modul mana pun,
    agar jaminan isolasi data antar guru pada aplikasi tetap utuh.
    """
    import database as db

    with db.get_conn() as conn:
        baris_db = conn.execute(
            """
            SELECT s.id_audio, a.filename, s.topik, s.score_relevansi,
                   s.score_konsep, s.score_kelengkapan, s.score_koherensi
            FROM assessment s
            JOIN audio a ON a.id_audio = s.id_audio
            ORDER BY s.id_assessment
            """
        ).fetchall()

    if not baris_db:
        raise SystemExit(
            f"Tidak ada penilaian di basis data ({db.DB_PATH}).\n"
            "Proses beberapa rekaman lewat aplikasi terlebih dahulu."
        )

    baris = []
    for r in baris_db:
        b = {"id_audio": r["id_audio"], "filename": r["filename"],
             "topik": r["topik"] or ""}
        for k in INDIKATOR:
            b[f"{k}_sistem"] = r[f"score_{k}"]
            b[f"{k}_guru"] = ""  # diisi guru
        baris.append(b)

    _tulis_csv(path, baris)
    print(f"{len(baris)} penilaian sistem diekspor ke: {path}")
    print("\nLangkah berikutnya:")
    print("  1. Minta guru menilai rekaman yang SAMA memakai rubrik yang sama,")
    print("     TANPA melihat kolom *_sistem (agar tidak terpengaruh).")
    print("  2. Isi kolom *_guru dengan skor guru (1-4).")
    print(f"  3. Jalankan: python objektivitas.py {path}")


def baca_data(path):
    pasangan = {k: ([], []) for k in INDIKATOR}
    jumlah_baris = 0

    with open(path, newline="", encoding="utf-8-sig") as f:
        pembaca = csv.DictReader(f)
        hilang = [k for k in KOLOM if k not in (pembaca.fieldnames or [])]
        if hilang:
            raise DataTidakSah(f"Kolom {', '.join(hilang)} tidak ada di {path}.")

        for nomor, baris in enumerate(pembaca, start=2):
            nilai = {}
            kosong = 0
            for k in INDIKATOR:
                for sisi in ("sistem", "guru"):
                    mentah = str(baris[f"{k}_{sisi}"] or "").strip()
                    if not mentah:
                        kosong += 1
                        continue
                    try:
                        skor = int(mentah)
                    except ValueError:
                        raise DataTidakSah(
                            f"Baris {nomor} kolom {k}_{sisi}: {mentah!r} bukan "
                            f"bilangan bulat."
                        )
                    if not SKALA_MIN <= skor <= SKALA_MAKS:
                        raise DataTidakSah(
                            f"Baris {nomor} kolom {k}_{sisi}: skor {skor} di luar "
                            f"skala rubrik ({SKALA_MIN}-{SKALA_MAKS})."
                        )
                    nilai[f"{k}_{sisi}"] = skor

            if kosong == len(INDIKATOR) * 2:
                continue  # baris kosong / template
            if kosong:
                raise DataTidakSah(
                    f"Baris {nomor} terisi sebagian ({kosong} sel kosong). "
                    f"Lengkapi atau hapus baris tersebut - baris setengah "
                    f"terisi akan membuat perhitungan menyesatkan."
                )

            for k in INDIKATOR:
                pasangan[k][0].append(nilai[f"{k}_sistem"])
                pasangan[k][1].append(nilai[f"{k}_guru"])
            jumlah_baris += 1

    if jumlah_baris == 0:
        raise DataTidakSah(f"Tidak ada baris terisi lengkap di {path}.")
    return pasangan, jumlah_baris


# ==============================
# PELAPORAN
# ==============================
def _fmt(x, digit=3):
    return "n/a" if x is None else f"{x:.{digit}f}"


def _baris_hasil(nama, sistem, guru):
    return {
        "nama": nama,
        "n": len(sistem),
        "persis": kesepakatan_persis(sistem, guru),
        "berdekatan": kesepakatan_berdekatan(sistem, guru),
        "kappa": cohen_kappa(sistem, guru, berbobot=False),
        "qwk": cohen_kappa(sistem, guru, berbobot=True),
        "r": pearson(sistem, guru),
        "selisih": sum(s - g for s, g in zip(sistem, guru)) / len(sistem),
    }


def hitung(path):
    pasangan, n = baca_data(path)

    hasil = [_baris_hasil(INDIKATOR[k], *pasangan[k]) for k in INDIKATOR]
    # Keseluruhan: seluruh pasangan skor indikator digabung.
    semua_s = [x for k in INDIKATOR for x in pasangan[k][0]]
    semua_g = [x for k in INDIKATOR for x in pasangan[k][1]]
    total = _baris_hasil("KESELURUHAN", semua_s, semua_g)

    print(f"Sumber data      : {path}")
    print(f"Jumlah respons   : {n}")
    print(f"Jumlah pasangan  : {len(semua_s)} (= {n} respons x {len(INDIKATOR)} indikator)")

    # Label ASCII agar aman dicetak di konsol Windows (cp1252).
    print(f"\n{'Indikator':<32} {'n':>4} {'Persis':>8} {'Dekat':>8} {'Kappa':>8} {'QWK':>8} {'r':>8} {'Bias':>7}")
    print("-" * 88)
    for h in hasil + [total]:
        if h["nama"] == "KESELURUHAN":
            print("-" * 88)
        print(f"{h['nama']:<32} {h['n']:>4} {h['persis']*100:>7.1f}% "
              f"{h['berdekatan']*100:>7.1f}% {_fmt(h['kappa']):>8} {_fmt(h['qwk']):>8} "
              f"{_fmt(h['r']):>8} {h['selisih']:>+7.2f}")

    print("\n('Persis' = skor sama; 'Dekat' = selisih <= 1 tingkat; "
          "'Bias' = rata-rata sistem - guru)")
    print(f"\nUkuran utama - Quadratic Weighted Kappa keseluruhan: {_fmt(total['qwk'])}")
    print(f"Interpretasi (Landis & Koch, 1977): {interpretasi_kappa(total['qwk'])}")
    print(f"Rata-rata selisih (sistem - guru)  : {total['selisih']:+.2f} "
          f"({'sistem cenderung lebih tinggi' if total['selisih'] > 0.05 else 'sistem cenderung lebih rendah' if total['selisih'] < -0.05 else 'tidak ada bias berarti'})")

    _peringatan(n, total)


def _peringatan(n, total):
    catatan = []
    if n < 30:
        catatan.append(
            f"Jumlah sampel kecil (n={n}). Kappa pada sampel kecil sangat tidak "
            "stabil - sebutkan n secara eksplisit di BAB IV dan hindari klaim "
            "yang terlalu kuat."
        )
    if total["kappa"] is None or total["qwk"] is None:
        catatan.append(
            "Kappa tidak terdefinisi: kedua penilai memberi skor identik untuk "
            "seluruh sampel, sehingga kesepakatan kebetulan (Pe) = 1. Perluas "
            "variasi mutu jawaban pada sampel."
        )
    elif total["persis"] > 0.9 and total["kappa"] is not None and total["kappa"] < 0.4:
        catatan.append(
            "Paradoks Kappa: kesepakatan persis tinggi tetapi Kappa rendah. "
            "Ini terjadi bila skor menumpuk di satu kategori. Laporkan keduanya, "
            "jangan hanya salah satu."
        )

    catatan.append(
        "Skor guru wajib diberikan TANPA melihat skor sistem. Bila guru sempat "
        "melihatnya, angka kesepakatan menjadi bias dan tidak sah dipakai "
        "menjawab RM #2."
    )
    catatan.append(
        "Proposal tidak menetapkan ambang kesepakatan minimum. Sepakati "
        "kriterianya dengan pembimbing sebelum menarik kesimpulan."
    )

    print("\nCATATAN:")
    for c in catatan:
        print(f"  - {c}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "-h"
    berkas = sys.argv[2] if len(sys.argv) > 2 else "objektivitas_data.csv"
    try:
        if arg in ("-h", "--help"):
            print(__doc__)
        elif arg == "--template":
            buat_template(berkas)
        elif arg == "--ekspor":
            ekspor_dari_basis_data(berkas)
        elif not os.path.exists(arg):
            raise SystemExit(f"Berkas tidak ditemukan: {arg}")
        else:
            hitung(arg)
    except DataTidakSah as e:
        raise SystemExit(f"Data tidak sah: {e}")
