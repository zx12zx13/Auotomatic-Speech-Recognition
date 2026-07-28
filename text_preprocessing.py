"""Modul pra-pemrosesan teks hasil transkripsi.

Mengimplementasikan tahap [9] pipeline penelitian (§3.2.2 poin 9 proposal):
membersihkan dan menyesuaikan teks mentah keluaran Whisper agar terstruktur
dan siap dianalisis oleh evaluator LLM.

Cakupan sesuai proposal:
- Menghapus spasi berlebih dan karakter yang tidak diperlukan
- Menyesuaikan huruf kapital pada awal kalimat
- Merapikan struktur kalimat
- Menyusun ulang teks berdasarkan urutan waktu dan memfokuskan pada
  pembicara yang menjadi objek evaluasi

Tambahan di luar cakupan proposal: koreksi kata yang salah didengar ASR dengan
bantuan LLM (`koreksi_asr_llm`). Pembersihan berbasis aturan tidak dapat
memulihkan kata yang salah dengar seperti "hater" → "hardware", karena
pemulihannya menuntut pemahaman konteks. Rancangan, batasan, dan risiko
metodologisnya dijelaskan pada bagian KOREKSI KESALAHAN ASR di bawah.

Normalisasi bahasa (slang ke bentuk baku) mengacu pada §3.2.3 alur kerja
sistem serta Ardinata dkk. (2024), "Identifikasi dan Normalisasi Teks Slang".
"""

import difflib
import json
import re

# Kamus normalisasi slang ke bentuk baku. Ditujukan untuk ragam lisan siswa
# yang lazim muncul pada transkripsi respons lisan di kelas.
KAMUS_SLANG = {
    r"\bgak\b": "tidak",
    r"\bnggak\b": "tidak",
    r"\bngga\b": "tidak",
    r"\bgk\b": "tidak",
    r"\btdk\b": "tidak",
    r"\bkalo\b": "kalau",
    r"\bklo\b": "kalau",
    r"\byg\b": "yang",
    r"\bgimana\b": "bagaimana",
    r"\bgmn\b": "bagaimana",
    r"\bak\b": "aku",
    r"\bsy\b": "saya",
    r"\bdgn\b": "dengan",
    r"\bkrn\b": "karena",
    r"\bkarna\b": "karena",
    r"\bjd\b": "jadi",
    r"\btrs\b": "terus",
    r"\budah\b": "sudah",
    r"\budh\b": "sudah",
    r"\bblm\b": "belum",
    r"\bbgt\b": "banget",
    r"\bkyk\b": "seperti",
    r"\bkayak\b": "seperti",
    r"\bsm\b": "sama",
    r"\bdlm\b": "dalam",
    r"\bhrs\b": "harus",
    r"\bbs\b": "bisa",
}

# Kata pengisi (filler) khas ujaran lisan. Dihapus karena tidak menyumbang
# makna dan dapat mengaburkan penilaian struktur bahasa.
KATA_PENGISI = [
    r"\beee+\b", r"\bemm+\b", r"\behm+\b", r"\bhmm+\b",
    r"\banu\b", r"\bapa ya\b",
]

# Karakter yang dipertahankan: huruf (termasuk beraksen), angka, spasi, dan
# tanda baca dasar. Sisanya dianggap artefak transkripsi dan dibuang.
POLA_KARAKTER_ASING = re.compile(r"[^\w\s.,!?;:()\-'\"À-ÿ]", re.UNICODE)


def normalisasi_slang(teks):
    """Mengubah kata tidak baku menjadi bentuk baku sesuai kamus."""
    for pola, ganti in KAMUS_SLANG.items():
        teks = re.sub(pola, ganti, teks, flags=re.IGNORECASE)
    return teks


def hapus_kata_pengisi(teks):
    """Menghapus kata pengisi khas ujaran lisan."""
    for pola in KATA_PENGISI:
        teks = re.sub(pola, " ", teks, flags=re.IGNORECASE)
    return teks


def hapus_pengulangan(teks):
    """Menghapus pengulangan kata berturut-turut sebanyak tiga kali atau lebih.

    Pengulangan tiga kali beruntun hampir pasti artefak ASR ("saya saya saya").
    Pengulangan dua kali sengaja dibiarkan karena dapat bermakna sah dalam
    bahasa Indonesia, misalnya penegasan "sangat sangat".
    """
    return re.sub(r"\b(\w+)(\s+\1\b){2,}", r"\1", teks, flags=re.IGNORECASE)


def rapikan_tanda_baca(teks):
    """Merapikan spasi di sekitar tanda baca dan menghapus tanda baca ganda."""
    teks = re.sub(r"\s+([.,!?;:])", r"\1", teks)      # spasi sebelum tanda baca
    teks = re.sub(r"([.,!?;:])(?=[^\s])", r"\1 ", teks)  # spasi sesudah tanda baca
    teks = re.sub(r"([.,!?;:])\1+", r"\1", teks)      # tanda baca berulang
    return teks


def kapitalisasi_kalimat(teks):
    """Mengapitalkan huruf pertama setiap kalimat.

    Hasil transkripsi Whisper tidak selalu memuat kapitalisasi yang konsisten,
    sehingga awal kalimat perlu disesuaikan agar teks terbaca terstruktur.
    """
    if not teks:
        return teks

    # Kapital setelah tanda akhir kalimat (. ! ?) yang diikuti spasi.
    teks = re.sub(
        r"([.!?]\s+)([a-zà-ÿ])",
        lambda m: m.group(1) + m.group(2).upper(),
        teks,
    )
    # Kapital pada huruf pertama teks.
    return teks[0].upper() + teks[1:] if teks else teks


def bersihkan_teks(teks):
    """Menjalankan seluruh rangkaian pembersihan teks tahap [9].

    Urutan disusun agar setiap langkah bekerja pada teks yang sudah rapi dari
    langkah sebelumnya: pembersihan karakter dahulu, normalisasi kata, lalu
    perapian struktur, dan kapitalisasi sebagai langkah terakhir.
    """
    if not teks or not teks.strip():
        return ""

    teks = POLA_KARAKTER_ASING.sub(" ", teks)
    teks = hapus_kata_pengisi(teks)
    teks = normalisasi_slang(teks)
    teks = hapus_pengulangan(teks)
    teks = re.sub(r"\s+", " ", teks).strip()   # spasi berlebih
    teks = rapikan_tanda_baca(teks)
    teks = re.sub(r"\s+", " ", teks).strip()
    teks = kapitalisasi_kalimat(teks)

    # Pastikan teks diakhiri tanda baca agar batas kalimat terakhir jelas.
    if teks and teks[-1] not in ".!?":
        teks += "."
    return teks


def susun_teks_pembicara(segmen, pembicara_target=None):
    """Menyusun teks berdasarkan urutan waktu, difokuskan pada satu pembicara.

    Argumen:
        segmen: daftar dict berisi kunci 'pembicara', 'mulai', dan 'teks'.
        pembicara_target: label pembicara yang dinilai, mis. "Pembicara 1".
            Bila None, seluruh pembicara digabungkan.

    Mengembalikan teks bersih siap dinilai. Bila pembicara target tidak
    ditemukan, mengembalikan string kosong agar pemanggil dapat memberi tahu
    guru secara eksplisit, bukan diam-diam menilai teks pembicara lain.
    """
    if not segmen:
        return ""

    terpilih = [s for s in segmen if pembicara_target is None
                or s.get("pembicara") == pembicara_target]
    if not terpilih:
        return ""

    # Urutkan berdasarkan waktu mulai agar alur penjelasan sesuai urutan asli.
    terpilih = sorted(terpilih, key=lambda s: s.get("mulai", 0))
    gabungan = " ".join(s.get("teks", "").strip() for s in terpilih)
    return bersihkan_teks(gabungan)


def daftar_pembicara(segmen):
    """Mengembalikan daftar label pembicara yang muncul, terurut."""
    return sorted({s.get("pembicara") for s in segmen if s.get("pembicara")})


# ==========================================================================
# KOREKSI KESALAHAN ASR OLEH LLM (lanjutan tahap [9] pra-pemrosesan teks)
# ==========================================================================
# Pembersihan berbasis aturan di atas hanya dapat merapikan bentuk teks; ia
# tidak dapat memulihkan kata yang salah didengar Whisper, misalnya "hater"
# yang seharusnya "hardware". Pemulihan semacam itu memerlukan pemahaman
# konteks, sehingga dikerjakan oleh LLM.
#
# PERINGATAN METODOLOGIS: LLM tidak mendengar audionya. Ia menebak kata yang
# paling mungkin, sehingga koreksi ini berpotensi ikut "membetulkan" kekeliruan
# konsep siswa -- padahal kekeliruan itu justru objek penilaian indikator
# Ketepatan Konsep. Karena itu:
#   - prompt melarang keras perubahan isi dan pembetulan konsep,
#   - hasil koreksi diverifikasi ambang kewajaran sebelum dipakai,
#   - teks sebelum dan sesudah koreksi sama-sama disimpan agar dapat diaudit.

# Ambang kewajaran koreksi. Koreksi salah dengar mengganti kata per kata,
# sehingga jumlah kata nyaris tidak berubah. Perubahan jumlah kata yang besar
# menandakan model meringkas, menambah kalimat, atau menjawab pertanyaan --
# bukan mengoreksi.
BATAS_SELISIH_KATA = 0.20    # maksimum 20% perubahan jumlah kata
BATAS_KEMIRIPAN = 0.50       # kemiripan minimum terhadap teks asli

# Transkrip dipotong sebelum dikirim ke LLM. Pengukuran pada endpoint yang
# dipakai sekarang: 40 kata selesai 23 detik, 80 kata 123 detik, dan 120 kata
# gagal (timeout); satu transkrip utuh 241 kata berakhir HTTP 502. Waktu
# tanggap naik jauh lebih cepat daripada panjang teks, sehingga potongan
# pendek bukan sekadar optimasi melainkan syarat agar tahap ini berjalan.
#
# Pemotongan juga menguntungkan secara metodologis: makin pendek teks yang
# dilihat model, makin sempit peluangnya menulis ulang isi, dan pemeriksaan
# kewajaran bekerja per potongan sehingga satu potongan yang ditolak tidak
# ikut membatalkan potongan lain yang sudah benar.
BATAS_KATA_POTONG = 50


def potong_teks(teks, batas=BATAS_KATA_POTONG):
    """Memotong teks pada batas kalimat, sedekat mungkin dengan `batas` kata.

    Pemotongan mengikuti akhir kalimat agar setiap potongan tetap punya
    konteks utuh; memotong di tengah kalimat akan membuat model kehilangan
    petunjuk untuk menebak kata yang rusak.
    """
    kalimat = [k for k in re.split(r"(?<=[.!?])\s+", (teks or "").strip()) if k]
    potongan, sekarang, jumlah = [], [], 0

    for k in kalimat:
        n = len(k.split())
        if sekarang and jumlah + n > batas:
            potongan.append(" ".join(sekarang))
            sekarang, jumlah = [], 0
        sekarang.append(k)
        jumlah += n

    if sekarang:
        potongan.append(" ".join(sekarang))
    return potongan


def periksa_kewajaran_koreksi(asli, koreksi):
    """Memeriksa apakah hasil koreksi masih wajar sebagai koreksi salah dengar.

    Mengembalikan (wajar: bool, alasan: str). Dipisahkan dari pemanggilan LLM
    agar dapat diuji tanpa jaringan.
    """
    kata_asli = asli.split()
    kata_koreksi = koreksi.split()

    if not kata_koreksi:
        return False, "hasil koreksi kosong"

    if not kata_asli:
        return False, "teks asli kosong"

    selisih = abs(len(kata_koreksi) - len(kata_asli)) / len(kata_asli)
    if selisih > BATAS_SELISIH_KATA:
        return False, (
            f"jumlah kata berubah {selisih:.0%} "
            f"({len(kata_asli)} → {len(kata_koreksi)}), melebihi batas "
            f"{BATAS_SELISIH_KATA:.0%}"
        )

    kemiripan = difflib.SequenceMatcher(None, kata_asli, kata_koreksi).ratio()
    if kemiripan < BATAS_KEMIRIPAN:
        return False, (
            f"kemiripan dengan teks asli hanya {kemiripan:.0%}, "
            f"di bawah batas {BATAS_KEMIRIPAN:.0%}"
        )

    return True, f"kemiripan {kemiripan:.0%}, selisih kata {selisih:.0%}"


def build_prompt_koreksi(teks, topik=None):
    """Menyusun prompt koreksi salah dengar ASR.

    Prompt sengaja membatasi model menjadi korektor kata, bukan penyunting isi:
    aturan 3 dan 4 adalah penjaga keabsahan penelitian.
    """
    konteks = (
        f"\nTOPIK PEMBELAJARAN (hanya untuk mengenali istilah bidang):\n{topik.strip()}\n"
        if topik and topik.strip() else ""
    )
    return f"""Anda adalah korektor transkrip hasil pengenalan suara otomatis (ASR) berbahasa Indonesia.

Teks di bawah berasal dari rekaman lisan yang ditranskripsikan mesin. Sebagian kata salah didengar sehingga menjadi kata yang mirip bunyinya tetapi tidak bermakna dalam konteksnya.

TUGAS: perbaiki HANYA kata yang jelas rusak akibat salah dengar.

ATURAN MUTLAK:
1. JANGAN menambah informasi, kalimat, penjelasan, atau contoh yang tidak ada pada teks asli.
2. JANGAN menghapus, meringkas, atau menyusun ulang isi. Jumlah kata harus tetap setara.
3. JANGAN menjawab atau melengkapi topik di atas. Anda korektor teks, bukan penjawab soal.
4. JANGAN membetulkan kekeliruan pemahaman pembicara. Bila pembicara menyampaikan konsep yang SALAH dengan kata-kata yang sudah jelas, biarkan apa adanya. Kekeliruan itu adalah data yang akan dinilai, bukan kesalahan transkripsi.
5. Perbaiki hanya bila kata pengganti mirip secara bunyi DAN jelas dari konteks. Contoh pola: "hater" → "hardware", "berhugungan" → "berhubungan".
6. Bila ragu, biarkan kata aslinya. Lebih baik satu kata tetap rusak daripada mengarang kata yang tidak diucapkan.
7. Pertahankan gaya bicara pembicara. Jangan memperhalus atau memperbaiki mutu bahasanya.
{konteks}
TEKS TRANSKRIP:
{teks.strip()}

FORMAT KELUARAN:
Keluarkan HANYA JSON murni tanpa teks tambahan dan tanpa markdown block, dengan skema:
{{
  "teks_koreksi": "<teks lengkap setelah dikoreksi>",
  "perubahan": [{{"asli": "<kata asli>", "koreksi": "<kata pengganti>"}}]
}}"""


def _koreksi_satu_potong(asli, topik, pemanggil):
    """Mengoreksi satu potongan teks. Dipakai oleh `koreksi_asr_llm`.

    Mengembalikan dict dengan kunci sama seperti `koreksi_asr_llm`, dan sama
    seperti fungsi itu tidak pernah melempar exception.
    """
    kosong = {
        "teks": asli,
        "asli": asli,
        "diterapkan": False,
        # `lengkap` menandai bahwa SELURUH potongan ini terkoreksi. Dipisahkan
        # dari `diterapkan` karena sebuah potongan dapat dibelah lalu hanya
        # sebagian bagiannya berhasil; tanpa penanda ini, keberhasilan sebagian
        # akan dilaporkan sebagai keberhasilan penuh dan kegagalannya hilang.
        "lengkap": False,
        "perubahan": [],
    }

    pesan = [
        {
            "role": "system",
            "content": (
                "Anda korektor transkrip ASR bahasa Indonesia. Anda hanya "
                "memperbaiki kata yang salah didengar, tidak pernah mengubah "
                "isi. Keluarkan SELALU JSON mentah yang sah tanpa markdown."
            ),
        },
        {"role": "user", "content": build_prompt_koreksi(asli, topik)},
    ]

    try:
        jawaban = pemanggil(pesan)
    except Exception as e:
        return {**kosong, "catatan": f"Koreksi dilewati, LLM gagal dihubungi ({type(e).__name__}): {e}"}

    try:
        data = json.loads(jawaban)
    except (json.JSONDecodeError, TypeError) as e:
        return {**kosong, "catatan": f"Koreksi dilewati, keluaran model bukan JSON sah: {e}"}

    if not isinstance(data, dict) or not isinstance(data.get("teks_koreksi"), str):
        return {**kosong, "catatan": "Koreksi dilewati, keluaran model tidak memuat 'teks_koreksi'."}

    hasil = data["teks_koreksi"].strip()
    wajar, alasan = periksa_kewajaran_koreksi(asli, hasil)
    if not wajar:
        # Teks asli dipertahankan. Koreksi yang mencurigakan lebih berbahaya
        # daripada transkrip yang masih rusak, karena hasilnya tampak rapi.
        return {**kosong, "catatan": f"Koreksi DITOLAK ({alasan}). Teks asli dipertahankan."}

    perubahan = []
    for p in data.get("perubahan") or []:
        if isinstance(p, dict) and p.get("asli") and p.get("koreksi"):
            perubahan.append((str(p["asli"]), str(p["koreksi"])))

    return {
        "teks": hasil,
        "asli": asli,
        "diterapkan": True,
        "lengkap": True,
        "catatan": f"Koreksi diterapkan ({alasan}); {len(perubahan)} kata dilaporkan berubah.",
        "perubahan": perubahan,
    }


def _belah_dua(teks):
    """Membelah satu potongan menjadi dua bagian pada batas kalimat.

    Mengembalikan daftar berisi dua bagian, atau daftar berisi teks aslinya
    bila potongan hanya terdiri atas satu kalimat sehingga tak dapat dibelah.
    """
    kalimat = [k for k in re.split(r"(?<=[.!?])\s+", (teks or "").strip()) if k]
    if len(kalimat) < 2:
        return [teks]
    tengah = len(kalimat) // 2
    return [" ".join(kalimat[:tengah]), " ".join(kalimat[tengah:])]


def _koreksi_bertingkat(asli, topik, pemanggil, sisa_belah=2):
    """Mengoreksi satu potongan; bila endpoint kehabisan waktu, potongan dibelah.

    Percobaan ulang dengan teks yang sama terbukti sia-sia: pada transkrip uji,
    potongan terpanjang (49 kata) gagal pada dua kali percobaan berturut-turut,
    sehingga kegagalannya bukan gangguan jaringan sesaat melainkan akibat
    panjang teks. Waktu tanggap endpoint naik jauh lebih cepat daripada panjang
    masukan (40 kata 23 detik, 80 kata 123 detik), jadi membelah potongan
    menjadi dua membuat tiap bagian kembali berada di bawah batas waktu.

    Pembelahan hanya dilakukan untuk kegagalan koneksi. Koreksi yang DITOLAK
    pemeriksaan kewajaran tidak diulang dalam bentuk apa pun: penolakannya
    beralasan, dan mengulang hanya memberi model kesempatan kedua untuk
    menulis ulang isi.
    """
    hasil = _koreksi_satu_potong(asli, topik, pemanggil)
    if hasil["diterapkan"] or sisa_belah <= 0:
        return hasil
    if "gagal dihubungi" not in hasil["catatan"]:
        return hasil

    bagian = _belah_dua(asli)
    if len(bagian) < 2:
        return hasil

    sub = [_koreksi_bertingkat(b, topik, pemanggil, sisa_belah - 1) for b in bagian]
    berhasil = [s for s in sub if s["diterapkan"]]
    if not berhasil:
        # Pembelahan tidak menolong; pertahankan catatan kegagalan yang asli
        # agar laporan tetap menunjuk sebab sesungguhnya.
        return hasil

    perubahan = []
    for s in sub:
        perubahan.extend(s["perubahan"])

    lengkap = all(s["lengkap"] for s in sub)
    catatan = (
        f"Koreksi diterapkan setelah potongan dibelah menjadi {len(bagian)} "
        f"bagian ({len(berhasil)} dari {len(bagian)} bagian berhasil); "
        f"{len(perubahan)} kata dilaporkan berubah."
    )
    if not lengkap:
        # Sebagian bagian tetap memakai teks asli. Ini harus terbaca di
        # laporan, bukan tersamar sebagai koreksi yang berhasil seluruhnya.
        belum = [s["catatan"] for s in sub if not s["lengkap"]]
        catatan += " Sebagian belum terkoreksi: " + " | ".join(belum)

    return {
        "teks": " ".join(s["teks"] for s in sub),
        "asli": asli,
        "diterapkan": True,
        "lengkap": lengkap,
        "catatan": catatan,
        "perubahan": perubahan,
    }


def koreksi_asr_llm(teks, topik=None, pemanggil=None, lapor=None):
    """Memperbaiki kata yang salah didengar ASR dengan bantuan LLM.

    Teks dipecah menjadi potongan pendek (lihat `BATAS_KATA_POTONG`) dan setiap
    potongan dikoreksi serta diperiksa kewajarannya sendiri-sendiri. Potongan
    yang koreksinya ditolak atau gagal dihubungi dikembalikan ke teks aslinya,
    sementara potongan lain tetap terkoreksi. Potongan yang gagal karena
    endpoint kehabisan waktu masih dibelah dua dan dicoba ulang per bagian
    (lihat `_koreksi_bertingkat`).

    Argumen:
        teks: teks hasil pembersihan berbasis aturan (`bersihkan_teks`).
        topik: topik/pertanyaan guru, dipakai sebagai petunjuk istilah bidang.
        pemanggil: fungsi pemanggil LLM, dapat diganti saat pengujian.
            Bawaannya `evaluator.panggil_llm`.
        lapor: fungsi opsional `lapor(indeks, total)` untuk menampilkan
            kemajuan; tahap ini memakan waktu puluhan detik per potongan.

    Mengembalikan dict:
        teks        -- teks yang layak dipakai (gabungan potongan; potongan
                       yang gagal tetap memakai teks aslinya)
        asli        -- teks sebelum koreksi, selalu diisi
        diterapkan  -- True bila minimal satu potongan berhasil dikoreksi
        catatan     -- ringkasan jumlah potongan berhasil/gagal, selalu diisi
        perubahan   -- daftar (asli, koreksi) gabungan yang dilaporkan model

    Fungsi ini TIDAK PERNAH melempar exception: kegagalan koreksi tidak boleh
    membatalkan transkripsi yang sudah berhasil. Kegagalan dilaporkan lewat
    `catatan`, sehingga tetap terlihat, tidak tersamar.
    """
    asli = (teks or "").strip()

    if not asli:
        return {
            "teks": asli,
            "asli": asli,
            "diterapkan": False,
            "catatan": "Tidak ada teks untuk dikoreksi.",
            "perubahan": [],
        }

    if pemanggil is None:
        # Diimpor di dalam fungsi agar modul ini tetap dapat diuji secara
        # luring tanpa memuat konfigurasi API.
        from evaluator import panggil_llm as pemanggil_bawaan
        pemanggil = pemanggil_bawaan

    potongan = potong_teks(asli)
    bagian, perubahan, gagal = [], [], []
    ada_koreksi = False

    for i, p in enumerate(potongan, 1):
        if lapor:
            lapor(i, len(potongan))
        hasil = _koreksi_bertingkat(p, topik, pemanggil)
        bagian.append(hasil["teks"])
        perubahan.extend(hasil["perubahan"])
        ada_koreksi = ada_koreksi or hasil["diterapkan"]
        # Potongan yang hanya terkoreksi sebagian ikut dilaporkan. Bila hanya
        # `diterapkan` yang diperiksa, bagian yang tetap rusak akan terhitung
        # sebagai keberhasilan penuh dan lolos dari laporan.
        if not hasil["lengkap"]:
            gagal.append(f"potongan {i}/{len(potongan)}: {hasil['catatan']}")

    berhasil = len(potongan) - len(gagal)
    catatan = (
        f"{berhasil} dari {len(potongan)} potongan terkoreksi seluruhnya; "
        f"{len(perubahan)} kata dilaporkan berubah."
    )
    if gagal:
        # Kegagalan per potongan ikut dicetak lengkap: bila hanya jumlahnya
        # yang dilaporkan, transkrip yang tidak terkoreksi akan tampak sama
        # saja dengan yang terkoreksi.
        catatan += "\n  Tidak terkoreksi:\n    " + "\n    ".join(gagal)

    return {
        "teks": " ".join(bagian),
        "asli": asli,
        # Cukup satu potongan (atau satu bagiannya) terkoreksi agar teks hasil
        # berbeda dari aslinya dan layak disimpan sebagai `llm_text`.
        "diterapkan": ada_koreksi,
        "catatan": catatan,
        "perubahan": perubahan,
    }
