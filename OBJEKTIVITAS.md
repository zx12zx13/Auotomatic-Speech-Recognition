# OBJEKTIVITAS.md

Panduan pengukuran objektivitas sistem terhadap penilaian manual guru —
**Iterasi 8**, menjawab **Rumusan Masalah #2**.

> ⚠️ **Status: alat siap, data belum ada.** Skrip `objektivitas.py` sudah
> selesai dan rumusnya terverifikasi, tetapi **belum ada satu pun data
> nyata**. Angka apa pun yang muncul dari data contoh **bukan hasil
> penelitian** dan tidak boleh masuk laporan.

## Mengapa diukur begini

Proposal (§1.2, §1.3) menyatakan masalahnya adalah **subjektivitas** penilaian
lisan manual. Klaim bahwa sistem "lebih objektif" hanya sah bila ditunjukkan
bahwa skor sistem **sepakat dengan penilaian guru** pada respons yang sama —
pendekatan yang dipakai Morris et al. (2024) untuk penilaian otomatis jawaban
konstruksi.

## Ukuran yang dihitung

| Ukuran | Arti | Catatan |
|---|---|---|
| **Kesepakatan persis** | % skor sistem sama persis dengan guru | Mudah dipahami, tapi mengabaikan faktor kebetulan |
| **Kesepakatan berdekatan** | % selisih ≤ 1 tingkat | Wajar dilaporkan: dua guru pun sering beda 1 tingkat |
| **Cohen's Kappa** | Kesepakatan setelah dikoreksi faktor kebetulan | Menganggap semua ketidaksepakatan sama buruknya |
| **Quadratic Weighted Kappa (QWK)** | Kappa dengan hukuman kuadratik | **Ukuran utama** — skor rubrik bersifat ordinal, meleset 3 tingkat jauh lebih buruk daripada 1 tingkat |
| **Korelasi Pearson** | Keeratan hubungan linear | Pelengkap, bukan pengganti Kappa |
| **Rata-rata selisih** | Arah bias (sistem − guru) | Positif = sistem cenderung lebih murah hati |

Rumus ditulis sendiri di `objektivitas.py` (bukan memanggil pustaka) agar
dapat dipertanggungjawabkan dan disalin ke BAB III/IV:

```
Cohen's Kappa:  kappa = (Po - Pe) / (1 - Pe)
QWK:            kappa_w = 1 - ( sum(w_ij * O_ij) / sum(w_ij * E_ij) )
                w_ij = (i - j)^2 / (k - 1)^2,   k = 4 kategori skor
```

Kebenarannya diverifikasi dua arah (`tests/test_objektivitas.py`):
contoh yang dihitung tangan (Kappa = 0,40) **dan** 100 perbandingan acak
terhadap `sklearn.metrics.cohen_kappa_score` (termasuk varian quadratic),
serta Pearson terhadap `scipy.stats.pearsonr`.

## Prosedur Pelaksanaan

### 1. Kumpulkan skor sistem

Proses sejumlah rekaman respons lisan siswa lewat aplikasi seperti biasa,
lalu ekspor skornya:

```bash
python objektivitas.py --ekspor
```

Menghasilkan `objektivitas_data.csv` berisi skor sistem, dengan kolom
`*_guru` **sengaja dikosongkan**.

### 2. Kumpulkan skor guru — **secara buta**

Minta guru menilai **rekaman yang sama** memakai **rubrik yang sama**
(Tabel 3.1), lalu isi kolom `*_guru`.

> 🔴 **Guru tidak boleh melihat skor sistem sebelum menilai.** Bila melihat,
> penilaiannya terpengaruh (*anchoring*), angka kesepakatan menjadi bias, dan
> hasilnya tidak sah untuk menjawab RM #2. Paling aman: berikan lembar berisi
> rekaman + rubrik saja, tanpa kolom `*_sistem`.

Pertimbangkan melibatkan **lebih dari satu guru**. Kesepakatan antar-guru
sendiri (*inter-rater reliability*) adalah pembanding yang kuat: bila sistem
vs guru setara dengan guru vs guru, itu argumen yang jauh lebih meyakinkan
daripada angka tunggal.

### 3. Hitung

```bash
python objektivitas.py objektivitas_data.csv
```

Keluaran: tabel per indikator + keseluruhan, ukuran utama QWK, interpretasi
Landis & Koch (1977), arah bias, dan catatan peringatan otomatis.

## Yang Perlu Diputuskan Bersama Pembimbing

1. **Jumlah sampel (n).** Skrip memperingatkan bila n < 30. Kappa pada sampel
   kecil sangat tidak stabil. Sepakati jumlah rekaman yang memadai.
2. **Ambang kesepakatan.** Proposal tidak menetapkan kriteria minimum.
   Kategori Landis & Koch dipakai sebagai rujukan umum, tetapi ambang
   kelayakan untuk penelitian ini perlu disepakati **sebelum** melihat hasil
   — menentukannya setelah melihat angka adalah praktik yang tidak sehat.
3. **Variasi mutu jawaban.** Bila semua sampel bermutu serupa, skor menumpuk
   di satu kategori dan Kappa menjadi rendah atau tidak terdefinisi meski
   kesepakatan persis tinggi (*paradoks Kappa* — skrip mendeteksi dan
   memperingatkan ini). Pilih sampel yang mencakup jawaban baik, sedang, dan
   kurang.
4. **Etika & perizinan.** Rekaman suara siswa adalah data pribadi. Perlu izin
   sekolah dan orang tua/wali sebelum pengambilan data.

## Yang TIDAK Dilakukan Sistem

Skrip ini **hanya menghitung**. Ia tidak membuat, menebak, atau melengkapi
data penilaian:

- Kolom `*_guru` hasil `--ekspor` selalu kosong (ada ujinya).
- Baris terisi sebagian **ditolak**, tidak dihitung sebagian.
- Skor di luar skala 1–4 atau bukan angka **ditolak**.
- Kappa yang tidak terdefinisi dilaporkan `n/a`, **bukan** dipaksa 0 atau 1.

Mengarang skor guru adalah pemalsuan data penelitian. Data harus datang dari
guru sungguhan yang menilai rekaman sungguhan.
