# PROGRESS.md

Status realisasi produk terhadap proposal. Rencana lengkap ada di [PLANNING.md](PLANNING.md).

**Tanggal peninjauan**: 17 Juli 2026 (diperbarui setelah Iterasi 7 — bagian otomatis — selesai)
**Basis peninjauan**: `app.py`, `main.py`, `evaluator.py`, `text_preprocessing.py`, `database.py`, `session.py`, `templates/`, `tests/`, riwayat git.

**Status iterasi**: Iterasi 1 (MVP Pipeline), 2 (Validasi Audio), 4 (Pra-pemrosesan Teks), 5 (Database), dan 6 (Histori & Penilaian nyata) — ✅ **selesai & terverifikasi**. Iterasi 7 (Pengujian) — ⚠️ **bagian otomatis selesai** (49 uji lolos, lihat [PENGUJIAN.md](PENGUJIAN.md)); skenario yang butuh model/API dan UAT responden guru masih menunggu. Iterasi 3 (Evaluasi LLM) — ⚠️ **kode selesai, belum lolos kriteria "selesai"** karena belum pernah dijalankan dengan Gemini API sungguhan (`GEMINI_API_KEY` belum diisi). Iterasi 8 belum mulai.

---

## Ringkasan

Seluruh alur produk kini tersambung dari ujung ke ujung: unggah audio → validasi → pra-pemrosesan → diarisasi → transkripsi → pra-pemrosesan teks → evaluasi LLM → simpan ke basis data → tampil di halaman Histori dan Penilaian. Tidak ada lagi data palsu di antarmuka.

**Satu-satunya bagian yang belum pernah dieksekusi sungguhan adalah pemanggilan Gemini API** (Iterasi 3) — inti kontribusi ilmiah penelitian. Kode, validasi keluaran, dan penyimpanannya sudah teruji dengan tiruan; yang belum terbukti adalah perilaku model sungguhan dan **konsistensi skor antar pemanggilan**, yang merupakan klaim utama penelitian. Ini hanya menunggu `GEMINI_API_KEY` diisi di `.env`.

**Estimasi penyelesaian terhadap 8 kebutuhan fungsional proposal: 6 dari 8** — KF #6 dan #7 tinggal menunggu uji API sungguhan; KF #1 masih kurang fitur perekaman langsung lewat sistem (saat ini hanya upload).

---

## Status Kebutuhan Fungsional (§3.2.1 Proposal)

| # | Kebutuhan | Status | Keterangan |
|---|---|---|---|
| 1 | Menerima input rekaman audio | ✅ Selesai | `gr.Audio(type="filepath")` + `validate_audio()` (format, ukuran, durasi, corrupt). Hanya upload; perekaman langsung lewat sistem belum ada |
| 2 | Pra-pemrosesan audio (normalisasi + noise reduction) | ✅ Selesai | BUG-01 diperbaiki & diuji: puncak amplitudo audio uji naik 0,135 → 0,989 dan `reduce_noise` berjalan |
| 3 | Speaker diarization maks. 5 pembicara | ✅ Selesai | Konstanta `MAX_SPEAKERS = 5`, ditegakkan di slider **dan** di `asr_pipeline()` via `min()` |
| 4 | Transkripsi ASR | ✅ Selesai | Whisper "medium", termasuk timestamp per segmen |
| 5 | Pra-pemrosesan teks | ✅ Selesai | `text_preprocessing.py`: spasi berlebih, karakter asing, kata pengisi, pengulangan ASR, kapitalisasi kalimat, normalisasi slang, penyusunan ulang per waktu & per pembicara |
| 6 | **Evaluasi otomatis berbasis rubrik** | ⚠️ Kode selesai, **belum diuji dengan API sungguhan** | `evaluator.py`: rubrik Tabel 3.1 sebagai data, prompt terstruktur, Gemini structured output. Butuh `GEMINI_API_KEY` |
| 7 | **Menghasilkan skor + umpan balik naratif** | ⚠️ Kode selesai, **belum diuji dengan API sungguhan** | Skor per indikator + skor akhir (rata-rata) + umpan balik; tampil di tab "Penilaian" |
| 8 | Menyimpan & menampilkan hasil evaluasi | ✅ Selesai | `database.py`: 6 tabel SQLite, penyimpanan bertahap audio→speaker→transcript→segment→assessment. Halaman Histori, Detail, dan Penilaian membaca data nyata dari basis data (Iterasi 6) |

## Status Kebutuhan Non-Fungsional

| # | Kebutuhan | Status | Keterangan |
|---|---|---|---|
| 1 | Antarmuka sederhana untuk guru | ✅ Sebagian | Dashboard + sidebar + modul Gradio ter-mount sudah berjalan |
| 2 | Tidak butuh perangkat khusus | ⚠️ | Whisper "medium" berat di CPU. Perlu diukur waktu prosesnya untuk audio 5–10 menit |
| 3 | Hasil konsisten & terdokumentasi | ⚠️ | Terdokumentasi ✅ (tersimpan di basis data, dapat ditelusuri). Konsistensi skor belum diukur — menunggu uji Iterasi 3 |
| 4 | Modular | ✅ | `local_nlp_processing`, `pyannote_diarization`, `preprocess_audio`, `asr_pipeline` terpisah rapi |
| 5 | **Keamanan data audio & hasil evaluasi** | ✅ Selesai | Kredensial di `.env` (BUG-02), password bcrypt (BUG-03), token sesi acak (BUG-07), isolasi data antar guru pada seluruh query |

---

## Status Pipeline (§3.2.2)

| Tahap | Status |
|---|---|
| [1] Akuisisi Audio | ✅ Upload jalan; rekam langsung belum ada |
| [2] Validasi Audio | ✅ `validate_audio()` — format, ukuran ≠ 0 byte, durasi > 0, deteksi corrupt |
| [3] Normalisasi Volume | ✅ Berjalan (BUG-01 diperbaiki) |
| [4] Noise Reduction | ✅ Berjalan (BUG-01 diperbaiki) |
| [5] VAD | ✅ Implisit di Whisper & Pyannote, sesuai desain proposal |
| [6] Speaker Change Detection | ✅ Implisit di Pyannote, sesuai desain proposal |
| [7] Speaker Diarization | ✅ Pyannote 3.1 + filter `MIN_SPEECH_DURATION_S = 0.5` + pemetaan ke "Pembicara 1/2/…" |
| [8] Transkripsi | ✅ Whisper medium |
| [9] Pra-pemrosesan Teks | ✅ `text_preprocessing.py` sesuai §3.2.2 poin 9 |
| [10] **Evaluasi LLM** | ⚠️ `evaluator.py` selesai; menunggu `GEMINI_API_KEY` untuk uji end-to-end |

---

## Status Halaman (§3.2.3.4)

| Halaman | Template/Rute | Status |
|---|---|---|
| Login | `templates/login.html` + `POST /login` | ✅ Jalan — password bcrypt, token sesi acak (Iterasi 5) |
| Registrasi | `templates/register.html` + `POST /register` | ✅ Jalan — validasi password cocok & username unik |
| Dashboard | `templates/dashboard.html` | ✅ Jalan |
| Analisis Audio | Gradio di `/gradio/analisis` | ✅ Jalan (evaluasi menunggu uji API) |
| Histori | `templates/histori.html` + `/histori-content` | ✅ Data nyata dari `ambil_histori()` (Iterasi 6) |
| Detail Proses | `templates/histori_detail.html` + `/histori-content/{id}` | ✅ Penilaian + transkrip + dialog per pembicara (Iterasi 6) |
| Penilaian | `templates/penilaian.html` + `/nilai-content` | ✅ Data nyata dari `ambil_penilaian()`, 4 indikator + umpan balik (Iterasi 6) |

---

## Status Database (§3.2.3.3) — ✅ SELESAI

Diimplementasikan di `database.py` memakai SQLite (`sqlite3` pustaka standar, tanpa dependensi ORM tambahan). Berkas basis data dapat diatur lewat `DB_PATH` di `.env`, default `evaluasi.db`.

| Tabel | Status |
|---|---|
| `user` | ✅ Password bcrypt, username unik |
| `audio` | ✅ Termasuk `duration` dari hasil validasi & `status` |
| `speaker` | ✅ `total_duration` dihitung otomatis dari segmen |
| `transcript` | ✅ `full_text` (mentah) + `corrected_text` (hasil pra-pemrosesan) |
| `segment` | ✅ Terhubung ke `speaker` dan `transcript` |
| `assessment` | ✅ + kolom skor per indikator (lihat catatan) |

**Penyesuaian terhadap proposal**: tabel `assessment` diberi kolom tambahan `score_relevansi`, `score_konsep`, `score_kelengkapan`, `score_koherensi`, dan `topik`. Proposal hanya menyediakan satu kolom `score`, padahal rubrik memiliki 4 indikator — tanpa kolom ini, analisis objektivitas per indikator (RM #2) tidak dapat dilakukan. **Relasi antar tabel tidak berubah**, sehingga Gambar 3.13 tetap berlaku; hanya daftar atribut pada Tabel 3.8 yang perlu diperbarui di proposal.

Klaim proposal bahwa "sistem menyimpan setiap hasil proses ke dalam database secara bertahap" (§3.2.3.2) kini terpenuhi: penyimpanan mengikuti urutan audio → speaker → transcript → segment → assessment, seluruhnya dalam satu transaksi.

---

## Status Pengujian (§3.2.5)

| Pengujian | Status |
|---|---|
| Black Box | ⚠️ 17/23 skenario Lampiran 5 lolos otomatis (`tests/test_blackbox.py`); 6 skenario butuh model/API → uji manual |
| White Box | ⚠️ 16/23 jalur Lampiran 5 lolos otomatis (`tests/test_whitebox.py`); 6 jalur implisit di model; WB-007 tidak berlaku |
| UAT (10 pertanyaan, responden guru) | ⚠️ Instrumen + skrip hitung (`uat_hitung.py`) siap; **pengambilan data responden belum** |
| Pengukuran objektivitas vs penilaian manual guru (RM #2) | ❌ Belum dilaksanakan (Iterasi 8) |

Rincian lengkap per TC-ID, penyesuaian terhadap Lampiran 5, dan cara menjalankan ada di [PENGUJIAN.md](PENGUJIAN.md). Jalankan dengan `python -m unittest discover -s tests`.

---

## Temuan / Bug

### ✅ BUG-01 — Pra-pemrosesan audio tidak pernah berjalan (Tinggi) — **DIPERBAIKI**
`preprocess_audio()` memanggil `nr.reduce_noise(...)`, tetapi **`noisereduce` tidak pernah di-import**. Setiap pemanggilan melempar `NameError`, tertangkap oleh `except Exception`, lalu fungsi mengembalikan path audio **asli**. Akibatnya normalisasi volume dan noise reduction — KF #2 serta tahap pipeline [3] dan [4] — tidak pernah benar-benar terjadi.

Ditemukan juga bahwa paket `noisereduce` **belum terpasang di `.venv`** meskipun sudah tercantum di `requirements.txt`; ini ikut menjelaskan mengapa kegagalan tersebut tidak pernah disadari.

Perbaikan: `import noisereduce as nr` ditambahkan, paket dipasang ke `.venv`, dan blok `except` kini mencetak PERINGATAN eksplisit bahwa audio diproses mentah — supaya kegagalan serupa tidak lolos diam-diam lagi.
Verifikasi: audio uji (nada pelan + noise) diproses lewat jalur yang sama; puncak amplitudo naik **0,135 → 0,989** tanpa `NameError`.

### ✅ BUG-02 — Token Hugging Face tertulis langsung di kode (Sedang, keamanan) — **DIPERBAIKI**
Token sudah dikeluarkan dari `app.py` dan kini dibaca via `os.getenv("HUGGINGFACE_TOKEN")` dari `.env`; `.gitignore` dan `.env.example` telah dibuat. Bila token tidak ada, aplikasi berhenti dengan pesan jelas **sebelum** memuat Whisper.

**Ralat (16 Juli 2026)**: versi awal dokumen ini menyatakan token "sudah ter-commit ke riwayat git" dan harus dianggap bocor permanen. **Pernyataan itu keliru.** Verifikasi `git log --all -S '<token>'` tidak menemukan hasil, dan `git show HEAD:app.py` tidak memuat baris `use_auth_token` sama sekali — token hanya pernah ada di working tree, tidak pernah ter-commit maupun ter-push. Tingkat keparahan diturunkan dari Kritis menjadi Sedang.

**Saran yang tetap berlaku**: cabut token lama di https://huggingface.co/settings/tokens dan terbitkan token baru untuk diisikan ke `.env`. Ini kehati-hatian wajar karena token sempat tersimpan sebagai teks polos di berkas kerja, bukan karena ada kebocoran publik.

### ✅ BUG-03 — Password disimpan dan dibandingkan dalam bentuk plaintext (Tinggi, keamanan) — **DIPERBAIKI**
`main.py` sebelumnya membandingkan `fake_user_db[username] == password` secara langsung. Kini kata sandi di-hash dengan **bcrypt** (`database.buat_user`) dan diperiksa dengan `bcrypt.checkpw` (`database.verifikasi_user`).
Verifikasi: kata sandi tersimpan berformat `$2b$12$...`, bukan teks polos; login dengan kata sandi benar berhasil, kata sandi salah dan pengguna tidak dikenal ditolak. `verifikasi_user` sengaja tidak membedakan "username tidak ada" dan "password salah" agar daftar pengguna terdaftar tidak bocor.

### ✅ BUG-07 — Cookie sesi berisi username sehingga dapat dipalsukan (Kritis, keamanan) — **DIPERBAIKI**
**Ditemukan saat Iterasi 5.** `main.py` sebelumnya menyetel `set_cookie("session-id", value=username)` dan memvalidasi sesi hanya dengan memeriksa apakah username ada di `fake_session_db`. Akibatnya **siapa pun dapat mengarang cookie `session-id=admin` di peramban dan langsung masuk tanpa kata sandi** — autentikasi praktis dapat dilewati sepenuhnya.

Perbaikan: token sesi kini dibuat acak dengan `secrets.token_urlsafe(32)` dan dipetakan ke `id_user` di sisi server (`session.py`). Logout menghapus token dari server, bukan sekadar menghapus cookie di peramban.
Verifikasi via `TestClient`: cookie `bu_intan` dan `admin` ditolak (redirect ke login); login sah menghasilkan token acak 43 karakter yang bukan username; token yang sudah logout ditolak.

### ✅ BUG-09 — Skor pecahan dan boolean dari LLM diam-diam dibulatkan menjadi skor sah (Sedang, integritas data) — **DIPERBAIKI**
**Ditemukan saat Iterasi 7.** `parse_hasil()` memakai `int(data[medan_skor])` untuk memaksa skor menjadi bilangan bulat. Masalahnya `int()` **memotong** pecahan dan menerima boolean: bila model mengembalikan `2.5`, sistem diam-diam menyimpannya sebagai **2**; bila mengembalikan `true`, tersimpan sebagai **1**. Keduanya lolos validasi skala 1–4 dan tampak sebagai penilaian sah.

Ini bertentangan langsung dengan prinsip yang sudah ditetapkan di modul ini sendiri — docstring `parse_hasil()` menyatakan skor tidak sah "ditolak, bukan diperbaiki diam-diam". Dampaknya nyata bagi penelitian: skor yang dilaporkan bukan skor yang diberikan model, sehingga analisis objektivitas (RM #2) berpijak pada angka yang salah tanpa ada jejak.

Perbaikan: pecahan non-bulat dan boolean kini ditolak eksplisit dengan `EvaluationError`. Nilai float yang setara bulat (`4.0`) tetap diterima, karena JSON wajar mengirim bentuk itu.
Verifikasi: `test_wb021b` menolak `0, 5, 7, -1, 2.5, "2.5", True, None, "tiga"`; `test_wb021b2` memastikan `4.0` tetap diterima sebagai 4.

### ✅ BUG-08 — Seluruh pemanggilan `TemplateResponse` memakai tanda tangan lama yang sudah dibuang starlette (Tinggi) — **DIPERBAIKI**
**Ditemukan saat Iterasi 6.** Semua rute yang merender template memanggil `TemplateResponse("nama.html", {"request": request, ...})` — gaya lama yang **sudah dihapus di starlette 1.x** (versi terpasang: 1.3.1). Setiap halaman HTML (login, register, dashboard, histori, penilaian) gagal dirender dengan `TypeError: unhashable type: 'dict'` karena starlette menafsirkan kamus konteks sebagai nama template. Bug ini tidak tertangkap pengujian Iterasi 5 karena pengujian saat itu hanya menyentuh jalur redirect (303), bukan jalur render template.

Perbaikan: seluruh 10 pemanggilan diubah ke tanda tangan baru `TemplateResponse(request, "nama.html", {...})`.
Verifikasi via `TestClient`: `GET /login`, `GET /register`, register dengan password tidak cocok (halaman error), dashboard setelah login, dan shell `/app/histori` semuanya merender 200 dengan isi yang benar.

### ✅ BUG-04 — `app.py` tidak bisa dijalankan langsung (Rendah) — **DIPERBAIKI**
Blok `if __name__ == "__main__":` ditambahkan; `python app.py` kini meluncurkan modul analisis Gradio secara mandiri, sesuai klaim di `GEMINI.md`. Untuk aplikasi penuh tetap gunakan `uvicorn main:app --reload`.

### ✅ BUG-05 — Variabel `dialogue` berpotensi belum terdefinisi (Sedang) — **DIPERBAIKI**
`dialogue = ""` kini diinisialisasi sebelum blok `try`, sehingga exception di tengah pipeline tidak lagi tertutupi oleh `UnboundLocalError`.

### ✅ BUG-06 — Batas jumlah pembicara tidak sesuai batasan masalah (Sedang) — **DIPERBAIKI**
Konstanta `MAX_SPEAKERS = 5` ditambahkan dan ditegakkan di dua tempat: batas slider, dan `min(int(num_speakers_val), MAX_SPEAKERS)` di `asr_pipeline()` — agar batasan tetap berlaku walau fungsi dipanggil dari luar UI.

---

## Ketidaksesuaian Dokumen

Perlu dirapikan sebelum sidang:

1. **§3.2.5 menyebut "tiga pendekatan" lalu hanya menyebut dua** (Black Box dan UAT), padahal sub-bab berikutnya memuat White Box. Perbaiki kalimat pengantar menjadi tiga: Black Box, White Box, UAT.
2. **Tabel 3.11 (Jadwal Riset) terpotong** setelah baris "Desain" — baris Pengembangan, Pengujian, dan Penyusunan Laporan belum ada.
3. **Penomoran sub-bab pengujian salah**: "3.2.4.2 Whitebox Testing" dan "3.2.4.2 User Acceptance Testing" memakai nomor yang sama; seharusnya berada di bawah 3.2.5.
4. **Tabel 3.3 dan Tabel 3.4 sama-sama berjudul "Tabel Audio"** (Tabel 3.4 tampak sebagai caption tersesat).
5. **Rujukan gambar keliru** di §3.2.3: teks menulis "Gambar 3.3 Merupakan alur kerja sistem", padahal alur kerja sistem adalah **Gambar 3.6**; Gambar 3.3 adalah visualisasi VAD.
6. **§1.2 dan §1.3 identik** — Identifikasi Masalah dan Rumusan Masalah memuat kalimat yang sama persis. Selain itu §1.3 poin 2 menyebut evaluasi "berbasis *Automatic Speech Recognition*" sedangkan §1.2 poin 2 menyebut "berbasis *Large Language Model*". Karena evaluator sistem adalah LLM, §1.3 yang perlu diselaraskan.
7. **Judul skripsi menekankan ASR**, sementara isi dan kontribusi menekankan LLM sebagai evaluator. Pertimbangkan diskusi dengan pembimbing apakah judul perlu menyebut LLM.

---

## Tindakan Berikutnya (berurutan)

1. **Cabut token Hugging Face yang bocor** (BUG-02) — satu-satunya sisa Iterasi 1, dan hanya bisa Anda lakukan sendiri. Terbitkan token baru lalu isi `.env`.
2. ~~Perbaiki BUG-01, BUG-04, BUG-05, BUG-06~~ — ✅ selesai & terverifikasi.
3. ~~Iterasi 2 (Validasi Audio)~~ — ✅ selesai & terverifikasi.
4. **Isi `GEMINI_API_KEY` di `.env`, lalu uji Iterasi 3 end-to-end.** Kodenya sudah siap, tetapi belum pernah menyentuh Gemini API sungguhan — lihat "Bukti Verifikasi Iterasi 3" di bawah untuk daftar apa yang sudah dan belum teruji.
5. ~~Iterasi 4 (Pra-pemrosesan Teks)~~ dan ~~Iterasi 5 (Database)~~ — ✅ selesai & terverifikasi.
6. ~~Iterasi 6 (Histori & Penilaian nyata)~~ — ✅ selesai & terverifikasi.
7. ~~Iterasi 7 — bagian otomatis (Black Box + White Box)~~ — ✅ selesai, 49 uji lolos.
8. **Iterasi 7 — bagian manual**: jalankan skenario bertanda "UJI MANUAL" di [PENGUJIAN.md](PENGUJIAN.md) (butuh `.env` terisi), lalu kumpulkan data UAT dari guru dan hitung dengan `uat_hitung.py`. **Hanya Anda yang bisa melakukan ini** — instrumen dan skrip perhitungannya sudah siap, datanya wajib berasal dari responden sungguhan.
9. Iterasi 8 (pengukuran objektivitas vs guru).

### Bukti Verifikasi Iterasi 7 — ⚠️ SEBAGIAN (bagian otomatis penuh)

`python -m unittest discover -s tests` → **49 uji, semuanya lolos** (17 Juli 2026). Rincian per TC-ID Lampiran 5 ada di [PENGUJIAN.md](PENGUJIAN.md).

| Cakupan | Hasil |
|---|---|
| Black Box (Lampiran 5) | ✅ 17/23 skenario + 2 skenario keamanan tambahan |
| White Box (Lampiran 5) | ✅ 16/23 jalur; WB-007 tidak berlaku (tidak ada kolom `isActive`) |
| Temuan bug baru | ✅ BUG-09 ditemukan & diperbaiki lewat pengujian ini |
| Instrumen UAT + skrip hitung | ✅ Rumus `P = (ΣX/ΣXmaks) × 100` diuji: 2 responden contoh → 65/80 = 81,25%, rincian per aspek & per pertanyaan; jawaban tidak sah (`Z`) ditolak |

**BELUM diuji** — butuh model/API sungguhan atau responden manusia:

- BB-012 s.d. BB-019: audio hening, diarisasi, transkripsi, dan mutu skor LLM.
- WB-012 s.d. WB-018: jalur VAD, deteksi pergantian pembicara, dan transkripsi (implisit di dalam model, bukan percabangan kode).
- **Data UAT dari guru sungguhan.** Skrip `uat_hitung.py` hanya menghitung; ia tidak membuat data. Angka 81,25% di atas berasal dari 2 baris contoh untuk menguji rumusnya, **bukan hasil UAT** — jangan pernah masuk ke laporan.

> **Catatan kejujuran akademik**: uji otomatis sengaja tidak mengklaim skenario yang belum benar-benar dijalankan. Kolom "Hasil" pada Lampiran 5 baru boleh diisi setelah skenario manual dijalankan sungguhan.

### Bukti Verifikasi Iterasi 6

Seluruh pengujian berjalan tanpa memerlukan API maupun model (modul Gradio/Whisper di-stub; rute FastAPI, template Jinja, dan basis data diuji sungguhan lewat `TestClient`), sehingga Iterasi 6 **terverifikasi penuh** — 16 uji, semuanya lolos.

**Kriteria "selesai" PLANNING.md** — evaluasi yang baru dibuat langsung muncul di Histori tanpa mengubah kode: ✅ **terbukti**. Satu hasil evaluasi disimpan lewat `db.simpan_hasil()` (jalur yang sama persis dengan `app.py`), lalu `GET /histori-content` langsung menampilkan berkas, skor akhir, dan durasinya.

| Aspek | Hasil |
|---|---|
| Histori/Penilaian kosong → pesan panduan, bukan tabel kosong | ✅ |
| Evaluasi baru langsung muncul di Histori | ✅ Nama berkas + skor 3.50/4 + durasi "1 mnt 35 dtk" |
| Data dummy lama hilang seluruhnya | ✅ Tidak ada jejak `rapat_q3_2023.mp3` dkk. |
| Penilaian menampilkan 4 skor indikator + skor akhir + topik | ✅ |
| Halaman detail: penilaian + teks dinilai + dialog per pembicara | ✅ |
| Proses tanpa penilaian → label "tidak dinilai", detail tetap terbuka | ✅ |
| Isolasi antar guru (daftar & tebak `id_audio` → 404) | ✅ |
| Tanpa login → 403 di ketiga rute konten | ✅ |
| Umpan balik / nama berkas ber-tag HTML di-escape (anti-XSS) | ✅ `<script>` tampil sebagai teks, tidak dieksekusi |
| Halaman lama (login, register, dashboard, shell iframe) tetap render | ✅ Pasca perbaikan BUG-08 |

Keputusan teknis: konten halaman dipindah dari string HTML di dalam `main.py` ke template Jinja2 (`histori.html`, `histori_detail.html`, `penilaian.html`, CSS bersama `_konten.css`). Alasannya bukan kerapian semata — nama berkas dan umpan balik LLM kini masuk ke halaman, dan penyusunan HTML lewat string membuka celah XSS; Jinja2 meng-escape otomatis (dan ini diuji).

### Bukti Verifikasi Iterasi 5

Seluruh pengujian berjalan tanpa memerlukan API maupun model, sehingga Iterasi 5 **terverifikasi penuh**.

**Kriteria "selesai" PLANNING.md** — hasil evaluasi bertahan setelah server di-restart: ✅ **terbukti**. Data ditulis oleh satu proses Python, lalu dibaca kembali oleh **proses Python yang benar-benar baru** (tanpa state di memori): histori, penilaian, transkrip, dan ketiga segmen terbaca utuh.

| Aspek | Hasil |
|---|---|
| Password ter-hash bcrypt, bukan plaintext | ✅ Format `$2b$12$...` |
| Login benar / salah / user tidak ada | ✅ Ketiganya sesuai harapan |
| Username ganda ditolak | ✅ |
| Penyimpanan bertahap 5 tabel | ✅ audio 1, speaker 2, transcript 1, segment 3, assessment 1 |
| `total_duration` per pembicara dihitung dari segmen | ✅ P1 = 12,0s (5+7), P2 = 3,0s |
| Skor per indikator tersimpan | ✅ (4, 3, 2, 3), skor akhir 3.0 |
| Pembicara yang dinilai tercatat di `assessment` | ✅ "Pembicara 1" |
| Data bertahan setelah restart | ✅ Dibaca dari proses baru |
| Guru lain tidak melihat histori guru lain | ✅ 0 baris |
| Guru lain menebak `id_audio` milik guru lain | ✅ Mengembalikan `None` |
| Keutuhan transaksi saat gagal di tengah | ✅ Foreign key gagal → **tidak ada data setengah jadi** |
| Evaluasi gagal → transkrip tetap tersimpan | ✅ `assessment` kosong, `transcript` tetap ada |
| Cookie sesi palsu ditolak (BUG-07) | ✅ Diuji via `TestClient` |
| Logout mematikan sesi di sisi server | ✅ Token lama ditolak |

### Keterbatasan yang Diketahui pada Iterasi 5

1. **Sesi disimpan di memori, bukan basis data.** Proposal tidak memuat tabel sesi, sehingga guru perlu login ulang setiap kali server dimulai kembali. Data hasil evaluasi tidak terpengaruh.
2. **`filepath` belum diisi.** Berkas audio unggahan belum disalin ke penyimpanan tetap, sehingga kolom `filepath` pada tabel `audio` masih kosong dan audio asli tidak dapat diputar ulang dari histori. Perlu diputuskan apakah rekaman siswa memang layak disimpan permanen — ini menyangkut data pribadi siswa dan sebaiknya dibicarakan dengan pembimbing serta pihak sekolah.
3. **Penyimpanan bergantung pada sesi login.** Bila modul Gradio dibuka langsung (misalnya lewat `python app.py`, di luar shell FastAPI), sesi tidak terdeteksi dan hasil tidak tersimpan. Sistem memberi tahu hal ini secara eksplisit di tab Penilaian, bukan diam-diam membuang hasil.

### Bukti Verifikasi Iterasi 2

`validate_audio()` diuji terhadap kriteria "selesai" di PLANNING.md:

| Kasus uji | Hasil |
|---|---|
| Berkas tidak ada | ✅ Ditolak — "File audio tidak ditemukan" |
| Format `.txt` | ✅ Ditolak — "Format '.txt' tidak didukung. Gunakan .wav atau .mp3" |
| Berkas 0 byte | ✅ Ditolak — "File audio kosong (0 byte)" |
| Berkas `.txt` disamarkan jadi `.wav` | ✅ Ditolak — "tidak dapat dibaca atau rusak (corrupt)" |
| Durasi 0 detik | ✅ Ditolak — "Durasi rekaman 0 detik" |
| `.wav` valid 2 detik | ✅ Lolos — durasi terbaca 2,00 detik |

Dukungan `.mp3` juga diverifikasi: ffmpeg tersedia di sistem dan libsndfile 1.2.2 mampu membaca mp3, sehingga `.mp3` berjalan dari validasi hingga pra-pemrosesan tanpa fallback ke audio mentah.

### Bukti Verifikasi Iterasi 3 — ⚠️ SEBAGIAN

**Sudah teruji** (tanpa memanggil Gemini API):

| Aspek | Hasil |
|---|---|
| Prompt memuat seluruh isi rubrik | ✅ 16/16 deskriptor dan 4/4 nama indikator masuk ke prompt |
| Topik guru & jawaban siswa masuk prompt | ✅ Keduanya terverifikasi |
| Skor akhir = rata-rata 4 indikator | ✅ Skor 4,3,2,3 → 3.0 |
| Skor di luar skala (7) ditolak | ✅ "berada di luar skala rubrik (1-4)" |
| Skor nol ditolak | ✅ Ditolak |
| Skor bukan bilangan bulat ditolak | ✅ Ditolak |
| Medan skor hilang ditolak | ✅ Ditolak |
| Keluaran bukan objek JSON ditolak | ✅ Ditolak |
| Topik/jawaban kosong ditolak | ✅ Ditolak sebelum memanggil API |
| Tanpa `GEMINI_API_KEY` gagal dengan pesan jelas | ✅ Ditolak |
| Jumlah nilai kembalian pipeline = jumlah output Gradio | ✅ Ketiga jalur `return` konsisten 4 nilai |

**BELUM teruji** — memerlukan `GEMINI_API_KEY`:

- Pemanggilan Gemini API sungguhan (nama model, autentikasi, kuota).
- Apakah `response_schema` benar-benar dipatuhi model dan `response.text` berisi JSON sesuai skema.
- Kualitas dan kewajaran skor yang dihasilkan terhadap jawaban siswa nyata.
- **Konsistensi skor antar pemanggilan** — `temperature=0.0` sudah diatur untuk tujuan ini, tetapi konsistensi nyata wajib diukur karena menjadi klaim utama penelitian.
- Alur penuh dari unggah audio hingga tab "Penilaian" lewat UI Gradio.

> **Catatan kejujuran akademik**: selama poin-poin di atas belum diuji, Iterasi 3 **belum boleh dinyatakan selesai** di laporan skripsi. Kriteria "selesai" pada PLANNING.md mensyaratkan satu transkrip menghasilkan 4 skor + umpan balik yang konsisten pada pemanggilan berulang — dan hal itu belum pernah dijalankan.

### Keterbatasan yang Diketahui pada Iterasi 3

1. ~~**Evaluasi memakai transkrip penuh (`full_text`), bukan teks khusus siswa.**~~ — ✅ **teratasi di Iterasi 4.** Yang dinilai kini teks hasil pra-pemrosesan milik pembicara yang dievaluasi saja.
2. **Belum ada penyimpanan hasil evaluasi.** Skor dan umpan balik hanya tampil di layar dan hilang setelah proses berikutnya (menunggu Iterasi 5).
3. **Belum ada mekanisme percobaan ulang (retry).** Kegagalan sementara API langsung dilaporkan sebagai gagal. Ini disengaja agar kegagalan terlihat, bukan tersamar.

### Bukti Verifikasi Iterasi 4

Seluruh pengujian berjalan tanpa memerlukan API maupun model, sehingga Iterasi 4 **terverifikasi penuh**.

**Kriteria "selesai" PLANNING.md** — teks mentah Whisper menjadi teks terstruktur siap dinilai:

```
SEBELUM : 'eee  saya   akan   menjelaskan  tentang gak  paham  yg   namanya
           fotosintesis   hmm  itu itu itu proses  tumbuhan'
SESUDAH : 'Saya akan menjelaskan tentang tidak paham yang namanya fotosintesis
           itu proses tumbuhan.'
```

| Aspek | Hasil |
|---|---|
| Spasi berlebih dihapus | ✅ |
| Kata pengisi (eee, hmm, anu) dihapus | ✅ |
| Slang → baku (gak→tidak, yg→yang, kalo→kalau) | ✅ |
| Pengulangan ASR 3× beruntun dihapus | ✅ `saya saya saya belajar` → `saya belajar` |
| Pengulangan 2× sengaja dibiarkan | ✅ `sangat sangat baik` tetap utuh |
| Kapitalisasi awal tiap kalimat | ✅ `ini satu. ini dua` → `Ini satu. Ini dua.` |
| Spasi sebelum tanda baca dirapikan | ✅ `halo dunia . apa kabar` → `Halo dunia. Apa kabar.` |
| Teks kosong ditangani | ✅ Mengembalikan string kosong |

**Penyusunan ulang per waktu & per pembicara** (simulasi rekaman guru + siswa, segmen sengaja diacak: 6,0s → 10,0s → 0,0s → 14,0s):

| Aspek | Hasil |
|---|---|
| Teks siswa terurut menurut waktu | ✅ Segmen 0,0s mendahului 10,0s |
| Ucapan guru tidak ikut dinilai | ✅ Terverifikasi |
| Mode seluruh pembicara (target 0) | ✅ Menggabungkan semua, tetap terurut waktu |
| Pembicara target tidak ditemukan | ✅ Mengembalikan kosong + memberi tahu guru, **tidak** diam-diam menilai pembicara lain |
| Daftar segmen kosong | ✅ Ditangani |
| Jumlah kembalian pipeline = output Gradio | ✅ Ketiga jalur `return` konsisten 4 nilai |

## Catatan Terbuka

**Urutan pra-pemrosesan berbeda dari proposal.** §3.2.2 menetapkan urutan normalisasi volume (tahap 3) → noise reduction (tahap 4), sedangkan `preprocess_audio()` melakukan noise reduction dahulu baru normalisasi. Secara teknis urutan kode justru lebih masuk akal (normalisasi setelah noise dibuang menghindari penguatan noise), tetapi **proposal dan kode harus disamakan** — paling praktis dengan menyesuaikan urutan tahap di proposal dan memberi alasan teknisnya. Di luar cakupan Iterasi 1, perlu dibahas dengan pembimbing.

---

## Riwayat Git — ⚠️ MASALAH SERIUS

**Ralat (16 Juli 2026)**: versi awal dokumen ini mendaftar 5 commit (`initial commit`, `Create app.py`, `Update app.py` ×3) sebagai riwayat kerja penelitian. **Itu keliru.** Commit-commit tersebut milik pihak lain.

Kondisi sebenarnya:

1. **Remote mengarah ke repositori orang lain.** `origin` = `https://huggingface.co/spaces/Qwen/Qwen3-ASR-Demo` — Hugging Face Space milik tim Qwen. `README.md` yang ter-commit masih berjudul "Qwen3 ASR Demo" dengan lisensi Apache-2.0. Folder ini adalah hasil clone Space tersebut sebagai titik awal.
2. **Tidak ada satu pun hasil kerja penelitian yang ter-commit.** Git hanya melacak 3 berkas: `app.py`, `README.md`, `.gitattributes`. Berkas `main.py`, `requirements.txt`, `templates/`, `PLANNING.md`, `PROGRESS.md`, `.env.example`, `.gitignore` seluruhnya **untracked**; perubahan pada `app.py` hanya berstatus *modified* di working tree.
3. **Konsekuensi**: tidak ada cadangan, tidak ada riwayat perubahan, dan tidak ada bukti tahapan pengembangan Agile — padahal §3.2 proposal mengklaim pengembangan iteratif–inkremental. Bila folder ini hilang atau rusak, seluruh produk skripsi hilang.

**Tindakan yang disarankan** (perlu keputusan Anda, belum dikerjakan):

1. Buat repositori baru milik sendiri (GitHub/GitLab pribadi, atau HF Space atas nama Anda).
2. Alihkan `origin` ke repositori tersebut, atau mulai riwayat baru dari nol bila tidak ingin membawa riwayat Qwen.
3. Ganti `README.md` dengan README penelitian sendiri; hapus atau sesuaikan atribut Qwen.
4. **Perhatikan lisensi & atribusi**: bila ada kode yang berasal dari Space Qwen (Apache-2.0), pencantuman atribusi wajib dipertahankan. Perlu ditelusuri bagian mana yang benar-benar turunan karya tersebut — dan bila memang ada, hal ini juga harus dinyatakan jujur di laporan skripsi.
5. Commit per iterasi dengan pesan deskriptif, mis. `feat(iterasi-3): integrasi evaluator Gemini berbasis rubrik`, sebagai bukti tahapan Agile.
