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

Normalisasi bahasa (slang ke bentuk baku) mengacu pada §3.2.3 alur kerja
sistem serta Ardinata dkk. (2024), "Identifikasi dan Normalisasi Teks Slang".
"""

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
