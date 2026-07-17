# PENGUJIAN.md

Dokumentasi pelaksanaan pengujian §3.2.5 proposal: **Black Box**, **White Box**,
dan **UAT**. Kode uji ada di folder `tests/`; skenario mengikuti **Lampiran 5**
proposal (BB-001 s.d. BB-023, WB-001 s.d. WB-023).

**Terakhir dijalankan**: 17 Juli 2026 — `49 uji otomatis, semuanya lolos`.

## Cara Menjalankan

```bash
python -m unittest discover -s tests -v
```

Model Whisper/Pyannote **tidak dimuat** saat uji otomatis (pemuatnya di-stub);
selain itu semuanya sungguhan: rute FastAPI, template, UI Gradio, dan SQLite
(ke berkas sementara — `evaluasi.db` tidak tersentuh). Karena itu skenario yang
bergantung pada mutu model/API ditandai **UJI MANUAL** dan belum boleh diklaim
lolos di laporan.

## Penyesuaian terhadap Lampiran 5

Didokumentasikan terbuka, bukan disembunyikan — perlu diselaraskan di proposal:

1. **Username, bukan email.** Lampiran 5 menulis autentikasi berbasis email,
   padahal Tabel 3.2 proposal (tabel `user`) dan implementasinya memakai
   `username`. Skenario BB-001–BB-007 diuji dengan username. BB-003 (format
   email tidak valid) diganti dua kasus setara: konfirmasi password tidak
   cocok, dan username kosong.
2. **Pesan kegagalan login disatukan.** BB-005/BB-006 mengharapkan pesan
   berbeda ("User tidak ditemukan" vs "Password tidak cocok"). Implementasi
   sengaja memakai satu pesan "Username atau password salah" agar daftar
   pengguna terdaftar tidak dapat dienumerasi dari perbedaan pesan (keamanan).
   Ada uji khusus (BB-006b) yang memastikan kedua pesan identik.
3. **WB-007 (isActive) tidak berlaku.** Tabel `user` pada proposal maupun
   implementasi tidak memiliki kolom status aktif.
4. **VAD & deteksi pergantian pembicara implisit di model** (sesuai desain
   §3.2.2), sehingga WB-012–WB-015 bukan percabangan kode yang bisa diuji
   unit — masuk uji manual.

## 1. Black Box Testing

| TC-ID | Skenario | Status | Bukti / Keterangan |
|---|---|---|---|
| BB-001 | Registrasi data valid | ✅ LOLOS | Akun dibuat, bisa login (`test_bb001`) |
| BB-002 | Registrasi username terdaftar | ✅ LOLOS | Error "sudah digunakan" (`test_bb002`) |
| BB-003 | (disesuaikan) konfirmasi password beda; username kosong | ✅ LOLOS | `test_bb003`, `test_bb003b` |
| BB-004 | Login kredensial valid | ✅ LOLOS | Masuk dashboard (`test_bb004`) |
| BB-005 | Login user tidak terdaftar | ✅ LOLOS* | Pesan digabung, lihat Penyesuaian #2 (`test_bb005`) |
| BB-006 | Login password salah | ✅ LOLOS* | Pesan digabung (`test_bb006`, `test_bb006b`) |
| BB-007 | Login field kosong | ✅ LOLOS | "Username dan password wajib diisi" (`test_bb007`) |
| BB-008 | Upload .wav valid >5 detik | ✅ LOLOS | Durasi terbaca 6,0 dtk (`test_bb008`) |
| BB-009 | Upload format tidak didukung | ✅ LOLOS | .txt ditolak (`test_bb009`) |
| BB-010 | Upload file 0 byte | ✅ LOLOS | + berkas corrupt (`test_bb010`, `test_bb010b`) |
| BB-011 | Berkas tidak ada / durasi 0 | ✅ LOLOS | `test_bb011` |
| BB-012 | Audio hening → notifikasi | ⏳ UJI MANUAL | Perilaku model (Whisper/Pyannote) |
| BB-013 | Audio bersuara → lanjut transkripsi | ⏳ UJI MANUAL | Butuh model |
| BB-014 | Diarization 1 pembicara | ⏳ UJI MANUAL | Butuh model |
| BB-015 | Diarization >1 pembicara | ⏳ UJI MANUAL | Butuh model |
| BB-016 | Transkripsi audio jelas | ⏳ UJI MANUAL | Butuh model |
| BB-017 | Transkripsi audio noise berat | ⏳ UJI MANUAL | Butuh model |
| BB-018 | Evaluasi jawaban relevan | ⏳ UJI MANUAL | Butuh `GEMINI_API_KEY` (Iterasi 3) |
| BB-019 | Evaluasi jawaban sangat singkat | ⏳ UJI MANUAL | Butuh `GEMINI_API_KEY` |
| BB-020 | API gagal merespons | ✅ LOLOS | Simulasi koneksi putus & tanpa key → pesan jelas (`test_bb020`, `test_bb020b`) |
| BB-021 | Evaluasi berhasil → tersimpan | ✅ LOLOS | `test_bb021` |
| BB-022 | Histori tampil di dashboard | ✅ LOLOS | + skor per indikator di halaman Penilaian (`test_bb022`) |
| BB-023 | Akses histori tanpa login | ✅ LOLOS | Redirect ke login; rute konten 403 (`test_bb023`) |

Skenario tambahan di luar Lampiran 5 (keamanan): isolasi histori antar guru
(`test_bb023b`), cookie sesi palsu ditolak (`test_bb023c`).

## 2. White Box Testing

| TC-ID | Jalur | Status | Bukti / Keterangan |
|---|---|---|---|
| WB-001 | Registrasi semua valid | ✅ LOLOS | + password tersimpan hash bcrypt (`test_wb001`, `test_wb001b`) |
| WB-002 | Registrasi input tidak valid | ✅ LOLOS | Username/password kosong ditolak (`test_wb002`) |
| WB-003 | Username duplikat | ✅ LOLOS | `test_wb003` |
| WB-004 | Login user ada + password cocok | ✅ LOLOS | `test_wb004` |
| WB-005 | User tidak ditemukan | ✅ LOLOS | `test_wb005` |
| WB-006 | Password tidak cocok | ✅ LOLOS | + input kosong ditolak sebelum query (`test_wb006`, `test_wb006b`) |
| WB-007 | isActive = false | — TIDAK BERLAKU | Lihat Penyesuaian #3 |
| WB-008 | Audio valid → lanjut | ✅ LOLOS | `test_wb008` |
| WB-009 | Audio tidak valid → tolak | ✅ LOLOS | 4 cabang penolakan disusuri (`test_wb009`) |
| WB-010 | Normalisasi volume | ✅ LOLOS | Puncak amplitudo naik >0,8 (`test_wb010_wb011`) |
| WB-011 | Noise reduction | ✅ LOLOS | Berjalan tanpa fallback diam-diam |
| WB-012 | VAD → tidak ada suara | ⏳ UJI MANUAL | Implisit di model |
| WB-013 | VAD → ada suara | ⏳ UJI MANUAL | Implisit di model |
| WB-014 | SCD → >1 pembicara | ⏳ UJI MANUAL | Implisit di model |
| WB-015 | SCD → 1 pembicara | ⏳ UJI MANUAL | Implisit di model |
| WB-016 | Diarization ≤5 pembicara | ⏳ UJI MANUAL | Batas `MAX_SPEAKERS=5` ditegakkan di kode |
| WB-017 | Transkripsi kosong → berhenti | ⏳ UJI MANUAL | Butuh model |
| WB-018 | Transkripsi berisi → lanjut | ⏳ UJI MANUAL | Butuh model |
| WB-019 | Pra-pemrosesan teks | ✅ LOLOS | 6 uji: pembersihan, slang, pengulangan, urutan waktu, target hilang, tanpa target |
| WB-020 | Prompt builder | ✅ LOLOS | Rubrik 16 deskriptor + topik + jawaban masuk prompt (`test_wb020`) |
| WB-021 | Validasi skor LLM | ✅ LOLOS | Termasuk perbaikan **BUG-09** (`test_wb021*`) |
| WB-022 | Simpan hasil (transaksi) | ✅ LOLOS | 3 uji: 5 tabel terisi, transaksi utuh saat gagal, tanpa penilaian (`test_wb022*`) |
| WB-023 | Load histori/detail | ✅ LOLOS | + isolasi antar pengguna (`test_wb023*`) |

## 3. User Acceptance Testing (UAT)

Instrumen sesuai Tabel 3.9–3.10 proposal: 10 pertanyaan (Aspek Sistem 1–4,
Pengguna 5–7, Antarmuka 8–10), bobot A=4, B=3, C=2, D=1, rumus
`P = (SigmaX / SigmaXmaks) x 100`.

Alur pelaksanaan:

```bash
python uat_hitung.py --template     # membuat uat_jawaban.csv
# ... guru mengisi kuesioner, jawaban disalin ke CSV ...
python uat_hitung.py uat_jawaban.csv
```

Skrip menghitung P total, per aspek, dan per pertanyaan.

> ⚠️ **Data UAT wajib berasal dari responden guru sungguhan.** Belum
> dilaksanakan — menunggu sistem lengkap (uji Iterasi 3 dengan API key) dan
> responden. Mengarang jawaban kuesioner adalah pemalsuan data penelitian.

## Status Keseluruhan

| Pengujian | Otomatis | Manual tersisa |
|---|---|---|
| Black Box | 17/23 skenario + 2 tambahan | 6 skenario butuh model/API |
| White Box | 16/23 jalur (22 metode uji) | 6 jalur di dalam model; 1 tidak berlaku |
| UAT | Instrumen + skrip hitung siap | Pengambilan data responden |

**Sebelum sidang**: jalankan skenario UJI MANUAL end-to-end (isi `.env`,
proses audio sungguhan lewat UI, catat hasil di kolom "Hasil" Lampiran 5),
karena uji otomatis sengaja tidak mengklaim apa yang belum dibuktikan.
