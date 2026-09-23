"""Koreksi salah dengar ASR berbasis aturan (tahap [9] pra-pemrosesan teks).

Menggantikan koreksi berbasis LLM (`text_preprocessing.koreksi_asr_llm`) sebagai
tahap koreksi yang dipakai pipeline. Alasannya bukan sekadar kecepatan:

  - DETERMINISTIK. Endpoint LLM terbukti memberi keluaran berbeda untuk masukan
    yang sama meski temperature=0.0. Penelitian ini mengklaim penilaian yang
    konsisten, sehingga tahap yang mengandung keacakan adalah beban yang tidak
    perlu ditanggung.
  - TIDAK MUNGKIN MENGARANG. LLM tidak mendengar audionya; ia menebak, sehingga
    berpotensi ikut "membetulkan" kekeliruan konsep siswa -- padahal kekeliruan
    itu justru objek penilaian indikator Ketepatan Konsep. Pencocok berbasis
    aturan hanya dapat menukar satu kata dengan kata yang ada di kamus; ia
    secara struktural tidak mampu menulis ulang makna.
  - CEPAT DAN LURING. Milidetik, bukan belasan menit; tanpa kunci API, tanpa
    mengirim ucapan siswa ke pihak ketiga.

RANCANGAN (mengikuti proposal §Tahap Pra-Pemrosesan Teks, dengan satu koreksi)

Proposal merancang dua tahap berurutan: Double Metaphone mencari kandidat
sebunyi, lalu Levenshtein ternormalisasi menyaring yang paling mirip
tulisannya. Pengujian menunjukkan kedua tahap itu BERTENTANGAN bila dijadikan
syarat-dan: Double Metaphone ada justru untuk mentoleransi ejaan yang jauh
berbeda, sedangkan Levenshtein ternormalisasi ada justru untuk menolaknya.
Pada contoh proposal sendiri, "bait" -> "byte", kode fonetiknya memang bertemu
(dua-duanya PT) tetapi Levenshtein kemudian memilih "bit" yang lebih dekat
tulisannya -- tahap penjaga ketepatan justru membuang jawaban yang benar.

Karena itu penyaringnya disatukan: jarak Levenshtein dihitung di atas bentuk
yang SUDAH dinormalisasi bunyinya, bukan di atas tulisan aslinya. Dengan
begitu perbedaan ejaan yang memang diharapkan ada tidak lagi dihukum, sementara
ambang jarak tetap menjaga agar koreksi tidak asal jauh.

Empat lapis, diperiksa berurutan:

  [1] Kamus koreksi dikenal. Pasangan salah dengar -> benar yang sudah
      terbukti, mis. "hater" -> "hardware". Perlu karena sebagian kesalahan ASR
      tidak punya hubungan ortografis maupun fonetik dengan kata sasarannya:
      "hater" dan "hardware" berbeda rangka konsonannya, sehingga tidak ada
      algoritma kemiripan yang akan mempertemukannya. Hubungannya ada di ranah
      akustik, bukan tulisan.
  [2] Gerbang kamus. Kata yang sudah sah dibiarkan apa adanya, sesuai
      rancangan proposal, agar kata umum tidak dipaksa berubah.
  [3] Double Metaphone terhadap glosarium istilah. Dipertahankan persis seperti
      proposal, dan memang tepat di sini: cakupannya dibatasi istilah serapan
      Inggris (cache, queue, byte), satu-satunya tempat aturan ejaan-ke-bunyi
      bahasa Inggris berlaku.
  [4] Kedekatan fonetik bahasa Indonesia. Bentuk ternormalisasi (pasangan
      bunyi yang lazim tertukar ASR diruntuhkan) dibandingkan dengan jarak
      Levenshtein. Ini yang menangkap "trainware" -> "brainware",
      "penyelasan" -> "penjelasan", "pemproses" -> "pemroses".

Seluruh perubahan dicatat beserta lapis yang menghasilkannya, sehingga tiap
koreksi dapat dipertanggungjawabkan satu per satu.
"""

import os
import re
import unicodedata

try:
    from metaphone import doublemetaphone
except ImportError:  # pragma: no cover - hanya bila pemasangan belum lengkap
    doublemetaphone = None

DIR_KAMUS = os.getenv("DIR_KAMUS") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "kamus"
)

# Ambang jarak Levenshtein pada bentuk ternormalisasi. Dinyatakan sebagai
# pecahan panjang kata supaya kata panjang boleh berbeda lebih banyak daripada
# kata pendek: satu huruf keliru pada kata 4 huruf jauh lebih meragukan
# daripada satu huruf keliru pada kata 12 huruf.
AMBANG_JARAK = 0.25

# Kata sangat pendek tidak dikoreksi. Pada kata 1-3 huruf, hampir semua kata
# lain berjarak dekat, sehingga koreksinya lebih sering salah daripada benar.
PANJANG_MINIMUM = 4

# Ambang jumlah kata agar daftar kata Indonesia dianggap kamus sungguhan.
#
# Ini pengaman penting. Gerbang kamus baru melindungi kata sah bila kamusnya
# memang lengkap. Dengan daftar kecil, kata sah yang kebetulan tidak terdaftar
# akan lolos ke tahap pencocokan lalu berpeluang tergantikan kata lain --
# persis kerusakan yang ingin dicegah.
MINIMUM_KAMUS_LENGKAP = 5000

# Aturan yang berlaku selama kamus belum lengkap (mode hemat).
#
# Angka di bawah bukan tebakan. Dengan ambang biasa, pengujian pada transkrip
# sungguhan (445 kata) menghasilkan koreksi palsu yang parah: "datang" menjadi
# "data", "kumpulan" menjadi "komponen", bahkan "Jadi" menjadi "Cache" --
# sebab kata-kata sah itu belum ada di daftar sehingga lolos ke pencocokan.
# Dua pembatas berikut menutup seluruh kasus tersebut sambil mempertahankan
# koreksi yang benar seperti "pemproses" dan "berhugungan":
#
#   - jarak harus TEPAT 1, bukan sepersekian panjang kata. Kata pendek terlalu
#     mudah berjarak dekat dengan kata lain yang tidak ada hubungannya.
#   - kata harus cukup panjang. Pada kata pendek, satu huruf berbeda hampir
#     tidak berarti apa-apa; "Jadi" dan "Cache" hanya terpaut satu lambang.
JARAK_MAKSIMUM_HEMAT = 1
PANJANG_MINIMUM_HEMAT = 7


# ==========================================================================
# JARAK LEVENSHTEIN
# ==========================================================================
def jarak_levenshtein(a, b):
    """Menghitung jarak edit Levenshtein antara dua string.

    Ditulis sendiri, tidak memakai pustaka luar, agar rumusnya dapat
    dijelaskan dan diverifikasi pada laporan penelitian -- mengikuti cara yang
    sama seperti perhitungan Kappa pada objektivitas.py.

    Memakai dua baris, bukan matriks penuh, karena hanya baris sebelumnya yang
    dibutuhkan untuk menghitung baris berikutnya.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    sebelum = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        sekarang = [i]
        for j, cb in enumerate(b, 1):
            sekarang.append(min(
                sebelum[j] + 1,          # penghapusan
                sekarang[j - 1] + 1,     # penyisipan
                sebelum[j - 1] + (ca != cb),  # penggantian
            ))
        sebelum = sekarang
    return sebelum[-1]


def jarak_ternormalisasi(a, b):
    """Jarak Levenshtein dibagi panjang string terpanjang. Rentang 0..1."""
    if not a and not b:
        return 0.0
    return jarak_levenshtein(a, b) / max(len(a), len(b))


# ==========================================================================
# NORMALISASI FONETIK BAHASA INDONESIA
# ==========================================================================
# Pasangan bunyi yang lazim tertukar pada transkripsi ASR bahasa Indonesia.
# Diruntuhkan ke satu lambang supaya kata yang hanya berbeda pada pasangan itu
# menjadi identik setelah normalisasi.
#
# Digraf harus diproses LEBIH DAHULU: bila "ng" diterjemahkan per huruf, ia
# menjadi N+K dan kehilangan identitasnya sebagai satu bunyi.
DIGRAF = [
    ("ng", "N"), ("ny", "Y"), ("sy", "S"), ("kh", "K"),
    ("ph", "F"), ("th", "T"), ("ch", "C"), ("qu", "K"),
]

# Konsonan bersuara dan tak bersuara diruntuhkan berpasangan (b/p, d/t, g/k,
# v/f, z/s) karena perbedaannya paling sering hilang pada rekaman kelas yang
# ber-noise. Vokal disederhanakan (i/e dan u/o) tetapi TIDAK dibuang: membuang
# vokal seperti Soundex membuat terlalu banyak kata berbeda menjadi seragam.
KELAS_BUNYI = str.maketrans({
    "b": "P", "p": "P",
    "d": "T", "t": "T",
    "g": "K", "k": "K", "q": "K",
    "v": "F", "f": "F",
    "z": "S", "s": "S", "x": "S",
    "j": "C", "c": "C",
    "w": "W", "y": "Y", "r": "R", "l": "L",
    "m": "M", "n": "N", "h": "H",
    "a": "A", "e": "E", "i": "E", "o": "O", "u": "O",
})


def bentuk_fonetik(kata):
    """Mengubah kata menjadi bentuk yang mewakili bunyinya.

    Contoh: "trainware" dan "brainware" sama-sama menjadi bentuk yang hanya
    berbeda satu lambang, sehingga jarak Levenshtein-nya 1 dan koreksinya
    dapat diterima dengan aman.
    """
    kata = unicodedata.normalize("NFKD", (kata or "").lower())
    kata = "".join(c for c in kata if not unicodedata.combining(c))
    kata = re.sub(r"[^a-z]", "", kata)
    if not kata:
        return ""

    for pola, ganti in DIGRAF:
        kata = kata.replace(pola, ganti.lower())

    kata = kata.translate(KELAS_BUNYI).upper()
    # Huruf kembar diruntuhkan: ASR kerap menggandakan atau menghilangkan
    # satu huruf pada bunyi yang sama.
    return re.sub(r"(.)\1+", r"\1", kata)


def kode_metaphone(kata):
    """Kode Double Metaphone (primer dan sekunder), untuk istilah serapan.

    Mengembalikan himpunan kosong bila pustaka metaphone tidak terpasang,
    sehingga lapis [3] dilewati tanpa menghentikan sistem.
    """
    if doublemetaphone is None:
        return set()
    return {k for k in doublemetaphone(kata or "") if k}


# ==========================================================================
# PEMUATAN KAMUS
# ==========================================================================
def _baca_daftar(nama):
    """Membaca satu berkas kamus. Baris kosong dan diawali '#' dilewati."""
    lokasi = os.path.join(DIR_KAMUS, nama)
    if not os.path.exists(lokasi):
        return []
    with open(lokasi, encoding="utf-8") as f:
        return [b.strip() for b in f if b.strip() and not b.startswith("#")]


def muat_kamus():
    """Memuat glosarium, koreksi dikenal, dan daftar kata Indonesia.

    Daftar kata Indonesia bersifat opsional. Tanpa berkas itu, sistem tetap
    berjalan tetapi hanya mengoreksi terhadap glosarium istilah -- cakupannya
    menyempit, dan itu dilaporkan lewat `catatan`, bukan didiamkan.
    """
    glosarium = _baca_daftar("glosarium_informatika.txt")

    dikenal = {}
    for baris in _baca_daftar("koreksi_dikenal.txt"):
        if "=" not in baris:
            continue
        salah, benar = baris.split("=", 1)
        salah, benar = salah.strip().lower(), benar.strip()
        if salah and benar:
            dikenal[salah] = benar

    kata_id = _baca_daftar("kata_indonesia.txt")
    return glosarium, dikenal, kata_id


class Korektor:
    """Korektor salah dengar ASR berbasis aturan.

    Kamus dimuat sekali saat objek dibuat, lalu indeks fonetiknya disusun di
    muka. Tanpa itu, tiap kata harus dibandingkan dengan seluruh kamus dan
    pemrosesan satu transkrip menjadi kuadratik.
    """

    def __init__(self, glosarium=None, dikenal=None, kata_id=None):
        if glosarium is None and dikenal is None and kata_id is None:
            glosarium, dikenal, kata_id = muat_kamus()

        self.glosarium = list(glosarium or [])
        self.dikenal = dict(dikenal or {})
        self.kata_id = list(kata_id or [])

        # Kata yang dianggap sudah benar dan tidak boleh diubah.
        self.aman = {k.lower() for k in self.glosarium} | {k.lower() for k in self.kata_id}

        # Kandidat pengganti. Kata umum hanya ikut menjadi kandidat bila
        # daftarnya sudah selengkap kamus sungguhan; lihat MINIMUM_KAMUS_LENGKAP.
        # Istilah bidang ditaruh lebih dahulu supaya menang saat jarak seri,
        # sesuai fokus proposal pada istilah teknis.
        self.kamus_lengkap = len(self.kata_id) >= MINIMUM_KAMUS_LENGKAP
        self.kandidat = self.glosarium + (self.kata_id if self.kamus_lengkap else [])

        self._fonetik = {k: bentuk_fonetik(k) for k in self.kandidat}
        self._indeks_metaphone = {}
        for istilah in self.glosarium:
            for kode in kode_metaphone(istilah):
                self._indeks_metaphone.setdefault(kode, []).append(istilah)

        # Kandidat dikelompokkan menurut panjang bentuk fonetiknya. Kata yang
        # panjangnya terpaut jauh mustahil lolos ambang jarak, jadi tak perlu
        # dibandingkan sama sekali.
        self._menurut_panjang = {}
        for k, f in self._fonetik.items():
            self._menurut_panjang.setdefault(len(f), []).append(k)

    # ------------------------------------------------------------------
    def koreksi_kata(self, kata):
        """Mengoreksi satu kata. -> (hasil, lapis, alasan)

        `hasil` bernilai None bila kata dibiarkan apa adanya.
        """
        inti = re.sub(r"^[^\w]+|[^\w]+$", "", kata)
        if not inti:
            return None, None, "bukan kata"

        rendah = inti.lower()

        # [1] Kamus koreksi dikenal -- paling dipercaya, diperiksa lebih dahulu
        #     supaya pasangan yang sudah terbukti tidak dikalahkan tebakan
        #     kemiripan. Tanpa lapis ini "bait" akan menjadi "bit", bukan "byte".
        if rendah in self.dikenal:
            return self.dikenal[rendah], "kamus", "pasangan salah dengar yang sudah dikenal"

        # [2] Gerbang kamus -- kata sah dibiarkan.
        if rendah in self.aman:
            return None, None, "kata sudah sah"

        # Selama kamus belum lengkap, hanya kata panjang yang boleh dikoreksi.
        batas_panjang = (PANJANG_MINIMUM if self.kamus_lengkap
                         else PANJANG_MINIMUM_HEMAT)
        if len(rendah) < batas_panjang:
            return None, None, (
                f"kata terlalu pendek ({len(rendah)} huruf, minimum "
                f"{batas_panjang}) untuk dikoreksi dengan aman"
            )

        # [3] Double Metaphone terhadap glosarium istilah serapan.
        kode = kode_metaphone(inti)
        sebunyi = []
        for k in kode:
            sebunyi.extend(self._indeks_metaphone.get(k, []))

        # [4] Kedekatan fonetik bahasa Indonesia.
        fon = bentuk_fonetik(inti)
        if not fon:
            return None, None, "tidak menghasilkan bentuk fonetik"

        batas = (max(1, round(len(fon) * AMBANG_JARAK)) if self.kamus_lengkap
                 else JARAK_MAKSIMUM_HEMAT)
        dekat = []
        for panjang in range(len(fon) - batas, len(fon) + batas + 1):
            dekat.extend(self._menurut_panjang.get(panjang, []))

        terbaik, jarak_terbaik = None, None
        for calon in dict.fromkeys(sebunyi + dekat):
            d = jarak_levenshtein(fon, self._fonetik[calon])
            if jarak_terbaik is None or d < jarak_terbaik:
                terbaik, jarak_terbaik = calon, d

        if terbaik is None:
            return None, None, "tidak ada kandidat"

        if jarak_terbaik > batas:
            return None, None, (
                f"kandidat terdekat '{terbaik}' berjarak {jarak_terbaik}, "
                f"melebihi ambang {batas}"
            )

        lapis = "metaphone" if terbaik in sebunyi else "fonetik-id"
        return terbaik, lapis, f"jarak fonetik {jarak_terbaik} dari ambang {batas}"

    # ------------------------------------------------------------------
    def koreksi_teks(self, teks, topik=None):
        """Mengoreksi seluruh teks. Bentuk kembaliannya sama dengan
        `text_preprocessing.koreksi_asr_llm`, sehingga kedua metode dapat
        ditukar di pipeline maupun dibandingkan berdampingan.

        `topik` diterima demi kesamaan bentuk pemanggilan, dan dipakai untuk
        melindungi kata yang memang muncul pada topik dari guru: kata yang
        ditulis guru sendiri jelas bukan salah dengar.
        """
        asli = (teks or "").strip()
        if not asli:
            return {
                "teks": asli, "asli": asli, "diterapkan": False,
                "catatan": "Tidak ada teks untuk dikoreksi.", "perubahan": [],
            }

        kata_topik = {k.lower() for k in re.findall(r"\w+", topik or "")}

        keluaran, perubahan, per_lapis = [], [], {}
        for potong in asli.split(" "):
            inti = re.sub(r"^[^\w]+|[^\w]+$", "", potong)
            if inti and inti.lower() in kata_topik:
                keluaran.append(potong)
                continue

            hasil, lapis, _ = self.koreksi_kata(potong)
            if not hasil or hasil.lower() == inti.lower():
                keluaran.append(potong)
                continue

            # Huruf besar di awal dipertahankan supaya kapitalisasi kalimat
            # yang sudah dirapikan tahap sebelumnya tidak rusak.
            if inti[:1].isupper():
                hasil = hasil[:1].upper() + hasil[1:]
            keluaran.append(potong.replace(inti, hasil, 1))
            perubahan.append((inti, hasil))
            per_lapis[lapis] = per_lapis.get(lapis, 0) + 1

        rincian = ", ".join(f"{n} lewat {l}" for l, n in sorted(per_lapis.items()))
        catatan = (
            f"Koreksi berbasis aturan: {len(perubahan)} kata diubah"
            + (f" ({rincian})." if rincian else ".")
        )
        if not self.kamus_lengkap:
            # Cakupan yang menyempit harus terbaca, bukan tersamar sebagai
            # "tidak ada yang perlu dikoreksi".
            catatan += (
                f" CATATAN: daftar kata Indonesia baru memuat {len(self.kata_id)} "
                f"kata (perlu {MINIMUM_KAMUS_LENGKAP} agar dianggap lengkap), "
                "sehingga koreksi dibatasi pada glosarium istilah dan kamus "
                "koreksi dikenal. Lihat kamus/README.md."
            )

        return {
            "teks": " ".join(keluaran),
            "asli": asli,
            "diterapkan": bool(perubahan),
            "catatan": catatan,
            "perubahan": perubahan,
        }


_korektor = None


def korektor_bawaan():
    """Korektor bersama, dimuat sekali seumur proses."""
    global _korektor
    if _korektor is None:
        _korektor = Korektor()
    return _korektor


def koreksi_asr_aturan(teks, topik=None):
    """Titik masuk yang dipakai pipeline. Sepadan dengan `koreksi_asr_llm`."""
    return korektor_bawaan().koreksi_teks(teks, topik)
