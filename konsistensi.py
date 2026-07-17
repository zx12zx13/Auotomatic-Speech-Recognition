"""Pengukuran konsistensi evaluator LLM (KNF #3 proposal).

Proposal mengklaim sistem menghasilkan penilaian yang "konsisten dan
terdokumentasi". Klaim itu harus dibuktikan, bukan diasumsikan dari
temperature=0.0: LLM tetap dapat menghasilkan keluaran berbeda pada
pemanggilan berulang.

Dua hal yang diukur:

1. KONSISTENSI (ulangi): jawaban yang SAMA dinilai berulang kali. Skor
   seharusnya identik. Dilaporkan: berapa kali skor berubah, dan sebarannya.

2. DISKRIMINASI (bedakan): jawaban dengan mutu BERBEDA dinilai sekali
   masing-masing. Skor seharusnya berbeda sesuai mutunya. Sistem yang
   memberi nilai sama untuk semua jawaban memang "konsisten" -- tetapi tidak
   berguna. Konsistensi tanpa diskriminasi adalah konsistensi yang menipu.

Pemakaian:
  python konsistensi.py ulangi [n]     -> nilai 1 jawaban n kali (default 5)
  python konsistensi.py bedakan        -> nilai 4 jawaban bermutu beda
"""
import statistics
import sys
import time

from evaluator import evaluate_response, EvaluationError, GEMINI_MODEL, RUBRIK

JEDA_DETIK = 4  # menahan laju agar tidak menabrak kuota tier gratis

TOPIK = "Jelaskan proses fotosintesis pada tumbuhan."

# Satu jawaban bermutu sedang -- sengaja tidak sempurna agar skor tidak
# menempel di batas atas skala, yang akan menyembunyikan variasi.
JAWABAN_UJI = (
    "Fotosintesis itu proses tumbuhan bikin makanan sendiri. Tumbuhan butuh "
    "sinar matahari sama air. Nanti hasilnya jadi makanan buat tumbuhannya. "
    "Terus keluar oksigen juga."
)

# Empat tingkat mutu untuk menguji daya beda sistem.
JAWABAN_BERTINGKAT = [
    ("Sangat kurang", "Fotosintesis itu tumbuhan. Ada daunnya. Warnanya hijau."),
    ("Kurang", "Fotosintesis proses tumbuhan bikin makanan. Butuh matahari."),
    ("Baik", "Fotosintesis adalah proses tumbuhan membuat makanan. Tumbuhan "
             "menyerap air dan karbon dioksida, lalu dengan bantuan cahaya "
             "matahari diubah menjadi glukosa dan oksigen."),
    ("Sangat baik", "Fotosintesis adalah proses tumbuhan mengubah energi cahaya "
                    "menjadi energi kimia. Air diserap akar, karbon dioksida "
                    "masuk lewat stomata. Di kloroplas, klorofil menangkap "
                    "cahaya matahari untuk mengubah air dan karbon dioksida "
                    "menjadi glukosa dan oksigen. Glukosa menjadi sumber energi "
                    "tumbuhan, oksigen dilepaskan ke udara."),
]


def _panggil(topik, jawaban, urutan):
    try:
        return evaluate_response(topik, jawaban)
    except EvaluationError as e:
        print(f"  [{urutan}] GAGAL: {e}")
        return None


def ulangi(n=5):
    """Menilai jawaban yang sama n kali dan melaporkan variasinya."""
    print(f"Model     : {GEMINI_MODEL}")
    print(f"Pengujian : jawaban SAMA dinilai {n} kali (temperature=0.0)")
    print(f"Jawaban   : {JAWABAN_UJI[:60]}...\n")

    hasil = []
    for i in range(1, n + 1):
        h = _panggil(TOPIK, JAWABAN_UJI, i)
        if h:
            hasil.append(h)
            skor = " ".join(f"{k[:4]}={h['skor'][k]}" for k in RUBRIK)
            print(f"  [{i}] {skor}  akhir={h['skor_akhir']}")
        if i < n:
            time.sleep(JEDA_DETIK)

    if len(hasil) < 2:
        raise SystemExit("\nTerlalu sedikit hasil untuk dibandingkan.")

    print(f"\n{'Indikator':<32} {'Nilai unik':>12} {'Konsisten?':>12}")
    print("-" * 58)
    semua_stabil = True
    for k in RUBRIK:
        nilai = [h["skor"][k] for h in hasil]
        unik = sorted(set(nilai))
        stabil = len(unik) == 1
        semua_stabil &= stabil
        print(f"{RUBRIK[k]['nama']:<32} {str(unik):>12} {'ya' if stabil else 'TIDAK':>12}")

    akhir = [h["skor_akhir"] for h in hasil]
    print("-" * 58)
    print(f"{'Skor akhir':<32} {str(sorted(set(akhir))):>12} "
          f"{'ya' if len(set(akhir)) == 1 else 'TIDAK':>12}")

    print(f"\nJumlah pemanggilan berhasil : {len(hasil)}/{n}")
    print(f"Rentang skor akhir          : {min(akhir)} - {max(akhir)}")
    if len(akhir) > 1:
        print(f"Simpangan baku skor akhir   : {statistics.pstdev(akhir):.4f}")

    if semua_stabil and len(set(akhir)) == 1:
        print("\nHASIL: skor IDENTIK pada seluruh pemanggilan.")
        print("Catatan: ini bukti untuk n kecil pada SATU jawaban. Konsistensi")
        print("penuh perlu diuji pada beberapa jawaban dengan mutu beragam,")
        print("dan sebaiknya diulang pada hari berbeda (model dapat diperbarui")
        print("Google tanpa pemberitahuan).")
    else:
        print("\nHASIL: skor BERVARIASI meski temperature=0.0.")
        print("Ini temuan penting dan harus dilaporkan apa adanya di BAB IV,")
        print("bukan disembunyikan. Pertimbangkan melaporkan rata-rata beserta")
        print("simpangan bakunya, dan bahas implikasinya terhadap klaim KNF #3.")


def bedakan():
    """Menilai empat jawaban bermutu berbeda untuk menguji daya beda."""
    print(f"Model     : {GEMINI_MODEL}")
    print("Pengujian : 4 jawaban bermutu BERBEDA, dinilai sekali masing-masing\n")

    hasil = []
    for i, (label, jawaban) in enumerate(JAWABAN_BERTINGKAT, start=1):
        h = _panggil(TOPIK, jawaban, label)
        if h:
            hasil.append((label, h))
            skor = " ".join(f"{k[:4]}={h['skor'][k]}" for k in RUBRIK)
            print(f"  {label:<14} {skor}  akhir={h['skor_akhir']}")
        if i < len(JAWABAN_BERTINGKAT):
            time.sleep(JEDA_DETIK)

    if len(hasil) < 2:
        raise SystemExit("\nTerlalu sedikit hasil untuk dibandingkan.")

    akhir = [h["skor_akhir"] for _, h in hasil]
    naik = all(a < b for a, b in zip(akhir, akhir[1:]))
    print(f"\nSkor akhir berurutan : {akhir}")
    print(f"Rentang              : {min(akhir)} - {max(akhir)}")

    if naik:
        print("\nHASIL: skor NAIK sejalan dengan mutu jawaban. Sistem mampu")
        print("membedakan mutu -- konsistensinya bermakna, bukan sekadar")
        print("memberi angka yang sama untuk semua.")
    elif len(set(akhir)) == 1:
        print("\nHASIL: seluruh jawaban memperoleh skor SAMA. Sistem tidak")
        print("membedakan mutu; konsistensi menjadi tidak bermakna. Ini masalah")
        print("serius bagi klaim penelitian dan wajib dilaporkan.")
    else:
        print("\nHASIL: skor berbeda tetapi TIDAK berurutan sesuai mutu.")
        print("Periksa apakah urutan mutu jawaban uji memang sudah tepat, lalu")
        print("laporkan ketidaksesuaian ini apa adanya.")


if __name__ == "__main__":
    perintah = sys.argv[1] if len(sys.argv) > 1 else "-h"
    if perintah == "ulangi":
        ulangi(int(sys.argv[2]) if len(sys.argv) > 2 else 5)
    elif perintah == "bedakan":
        bedakan()
    else:
        print(__doc__)
