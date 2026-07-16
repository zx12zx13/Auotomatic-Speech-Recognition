# PLANNING.md

Rencana pengembangan produk skripsi:
**Pengembangan Sistem Evaluasi Berdasarkan Respons Lisan Siswa Menggunakan Automatic Speech Recognition**

Made Gunawan — NIM 2215051045
Prodi Pendidikan Teknik Informatika, Universitas Pendidikan Ganesha

Dokumen ini menurunkan BAB III (Metode Penelitian) dari proposal menjadi rencana kerja teknis untuk kode di folder ini. Status realisasi dicatat terpisah di [PROGRESS.md](PROGRESS.md).

---

## 1. Tujuan Produk

Sistem harus menjawab dua rumusan masalah proposal:

1. **Rancang bangun** sistem evaluasi otomatis respons lisan siswa yang mengatasi subjektivitas penilaian manual.
2. **Mengukur performa dan objektivitas** hasil penilaian sistem dibanding penilaian manual guru.

Kontribusi ilmiah penelitian ini **bukan** pada transkripsi (ASR sudah matang), melainkan pada **LLM sebagai evaluator berbasis rubrik**. Proposal secara eksplisit menyatakan bahwa sistem yang berhenti di transkripsi + pencocokan kata "tidak memberikan kontribusi ilmiah yang signifikan" (Ardian & Suryadi, 2024). Karena itu modul evaluasi LLM adalah prioritas tertinggi, bukan pelengkap.

**Aktor**: Guru (pengendali evaluasi) dan Siswa (penyedia respons lisan).
**Lokasi penelitian**: SMP Negeri 7 Singaraja (narasumber: Si Luh Made Intan Pebriyanti, S.Pd.).

---

## 2. Batasan Masalah (mengikat implementasi)

Batasan berikut dari proposal harus tercermin di kode, bukan hanya di dokumen:

| Batasan | Konsekuensi teknis |
|---|---|
| Fokus pada presentasi / ujian lisan terstruktur | Alur kerja berbasis "topik/soal → respons → skor", bukan percakapan bebas |
| Hanya menilai kualitas konten dan kualitas bahasa | Rubrik 4 indikator; tanpa penilaian kosakata lanjut atau gaya bahasa |
| Tanpa aspek non-verbal (intonasi, emosi, gestur) | Tidak ada modul analisis prosodi/emosi |
| **Maksimal 5 pembicara** | Slider jumlah pembicara harus dibatasi 0–5, bukan 0–10 |
| Format audio `.wav` / `.mp3` | Validasi format wajib menolak format lain |

---

## 3. Arsitektur Sistem

Pipeline sesuai Gambar 3.2 (Flowchart) dan Gambar 3.6 (Alur Kerja Sistem):

```
Guru menyiapkan topik/soal
        ↓
[1] Akuisisi Audio        → rekam langsung atau upload (.wav/.mp3)
        ↓
[2] Validasi Audio        → format, ukuran ≠ 0 byte, durasi > 0, tidak corrupt
        ↓
[3] Normalisasi Volume    → pydub effects.normalize(), 16-bit PCM
        ↓
[4] Noise Reduction       → soundfile + noisereduce.reduce_noise()
        ↓
[5] VAD                   → implisit di dalam Whisper & Pyannote (bukan modul terpisah)
        ↓
[6] Speaker Change Detect → implisit di dalam pipeline Pyannote
        ↓
[7] Speaker Diarization   → pyannote/speaker-diarization-3.1, embedding ECAPA-TDNN
        ↓
[8] Transkripsi (ASR)     → OpenAI Whisper (model "medium"), log-Mel + transformer
        ↓
[9] Pra-pemrosesan Teks   → normalisasi bahasa, kapitalisasi, rapikan segmen per pembicara
        ↓
[10] Evaluasi LLM         → Google Gemini API + prompt rubrik → skor + feedback naratif
        ↓
Simpan ke database → tampilkan ke guru
```

**Catatan desain penting**: Tahap [5] dan [6] sengaja **tidak** dibuat sebagai modul terpisah. Keduanya sudah tertangani secara internal oleh Whisper dan Pyannote. Yang perlu diimplementasikan eksplisit hanya penyaringan segmen di bawah `MIN_SPEECH_DURATION_S` (0.5 detik) agar batuk/deham tidak terhitung sebagai giliran bicara.

### Tumpukan Teknologi

| Lapis | Teknologi |
|---|---|
| Web framework | FastAPI + Jinja2 |
| UI modul analisis | Gradio (di-mount ke FastAPI via `gr.mount_gradio_app`) |
| ASR | `openai-whisper` (medium) |
| Diarization | `pyannote.audio` 3.1.1 + `speechbrain` |
| Evaluator | Google Gemini (via API) |
| Audio | `pydub`, `soundfile`, `noisereduce` |
| Basis data | SQL (SQLite untuk pengembangan; skema di §5) |

---

## 4. Rubrik Penilaian (Tabel 3.1)

Skala 1–4: **1 = Kurang, 2 = Cukup, 3 = Baik, 4 = Sangat Baik**.

| Indikator | 1 (Kurang) | 2 (Cukup) | 3 (Baik) | 4 (Sangat Baik) |
|---|---|---|---|---|
| **Relevansi terhadap Pertanyaan** | Tidak menjawab pertanyaan / keluar topik | Berkaitan dengan topik tetapi melebar dan kurang fokus | Sesuai pertanyaan, sedikit bagian kurang fokus | Sepenuhnya sesuai dan tetap fokus pada topik |
| **Ketepatan Konsep** | Konsep salah / pemahaman keliru | Beberapa kesalahan konsep yang memengaruhi isi | Sebagian besar benar, kesalahan kecil | Seluruh konsep benar dan sesuai materi |
| **Kelengkapan Isi** | Sangat singkat, tidak dikembangkan | Ada penjelasan tetapi kurang rinci, poin penting belum tercakup | Cukup lengkap, mencakup sebagian besar poin penting | Lengkap, terstruktur, mencakup poin penting secara jelas |
| **Koherensi dan Alur Logika** | Tidak runtut, sulit diikuti | Kurang teratur, ada lompatan ide | Cukup runtut, sedikit lompatan ide | Runtut, ide saling berhubungan, mudah dipahami |

Rubrik ini adalah **kontrak prompt**: teksnya harus masuk ke prompt Gemini apa adanya, dan output LLM wajib berformat terstruktur (JSON) berisi skor per indikator + alasan, agar dapat diekstrak dan disimpan ke tabel `assessment`.

Rancangan struktur prompt (sesuai §3.2.2 poin 10):
1. Instruksi penilaian (peran sebagai evaluator, gunakan hanya rubrik)
2. Kriteria evaluasi (tabel rubrik di atas)
3. Topik/soal yang diberikan guru
4. Teks jawaban siswa hasil pra-pemrosesan
5. Format output yang diharapkan (JSON: skor tiap indikator, skor akhir, feedback naratif)

---

## 5. Skema Basis Data (Gambar 3.13, Tabel 3.2–3.8)

Database menyimpan **hasil antara**, bukan hanya skor akhir — agar penilaian dapat ditelusuri ulang dan diverifikasi bila ada sengketa nilai.

**user** — `id_user` (PK), `username`, `password`, `created_at`
**audio** — `id_audio` (PK), `id_user` (FK), `filename`, `filepath`, `duration`, `uploaded_at`, `status`
**speaker** — `id_speaker` (PK), `id_audio` (FK), `speaker_label`, `total_duration`
**transcript** — `id_transcript` (PK), `id_audio` (FK), `full_text`, `corrected_text`, `created_at`
**segment** — `id_segment` (PK), `id_speaker` (FK), `id_transcript` (FK), `start_time`, `end_time`, `text`
**assessment** — `id_assessment` (PK), `id_audio` (FK), `id_speaker` (FK siswa dinilai), `id_user` (FK guru evaluator), `score`, `feedback`, `created_at`

> **Usulan penyesuaian**: tabel `assessment` proposal hanya punya satu kolom `score`. Karena rubrik memiliki 4 indikator, skor per indikator perlu tersimpan agar analisis objektivitas (§7.4) bisa dilakukan per indikator. Tambahkan kolom `score_relevansi`, `score_konsep`, `score_kelengkapan`, `score_koherensi`, dengan `score` tetap sebagai nilai akhir. Perubahan ini menambah kolom saja, tidak mengubah relasi, sehingga aman terhadap Gambar 3.13.

---

## 6. Halaman / Antarmuka (Gambar 3.14–3.19)

| Halaman | Fungsi | Activity Diagram |
|---|---|---|
| Login | Autentikasi guru, buat sesi | Gambar 3.9 |
| Registrasi | Buat akun, validasi kelengkapan & keunikan | Gambar 3.8 |
| Dashboard | Ringkasan & navigasi antar modul | — |
| Analisis Audio | Upload/rekam → validasi → transkrip → evaluasi | Gambar 3.10, 3.11 |
| Histori | Tinjau ulang evaluasi lampau dari database | Gambar 3.12 |
| Penilaian | Skor per indikator + umpan balik naratif | — |

---

## 7. Rencana Iterasi (Agile Development)

Model pengembangan: **Agile**, iteratif–inkremental, diawali **MVP** untuk menguji alur utama ASR → NLP → LLM (§3.2 proposal). Setiap iterasi diakhiri pengujian agar kesalahan ditemukan lebih awal.

### Iterasi 1 — Stabilkan MVP Pipeline (fondasi)
- Perbaiki bug pra-pemrosesan audio (import `noisereduce`, lihat PROGRESS.md §Bug).
- Pindahkan token Hugging Face dari kode ke variabel lingkungan (`.env`).
- Batasi slider jumlah pembicara ke maksimal **5** sesuai batasan masalah.
- Tambahkan blok `if __name__ == "__main__":` agar `python app.py` benar-benar jalan.
- **Selesai bila**: satu file audio 2 pembicara menghasilkan dialog berlabel pembicara tanpa error.

### Iterasi 2 — Validasi Audio (Gambar 3.10)
- Cek format (`.wav`/`.mp3`), ukuran ≠ 0 byte, durasi > 0, file tidak corrupt.
- Tolak file tidak valid dengan pesan error yang jelas; hentikan pipeline.
- **Selesai bila**: file `.txt` disamarkan jadi `.wav`, file 0 byte, dan file corrupt semuanya ditolak dengan pesan spesifik.

### Iterasi 3 — Modul Evaluasi LLM (inti penelitian)
- Integrasi Google Gemini API; API key di `.env`.
- Susun prompt rubrik (§4) dengan output JSON terstruktur.
- Parser respons → skor per indikator + skor akhir + feedback.
- Tangani kegagalan API (timeout, kuota, JSON tidak valid) dengan fallback yang jelas — jangan diam-diam mengembalikan skor 0.
- **Selesai bila**: satu transkrip menghasilkan 4 skor + feedback naratif yang konsisten pada pemanggilan berulang.

### Iterasi 4 — Pra-pemrosesan Teks yang Benar (§3.2.2 poin 9)
- Ganti kamus slang regex + penghitung kata (bukan bagian dari proposal) dengan: hapus spasi berlebih, kapitalisasi awal kalimat, rapikan struktur, susun ulang segmen per urutan waktu, fokuskan pada pembicara yang dievaluasi.
- **Selesai bila**: teks mentah Whisper tanpa tanda baca menjadi teks terstruktur siap dinilai.

### Iterasi 5 — Persistensi Database
- Implementasi 6 tabel (§5); ganti `fake_user_db`/`fake_session_db` dengan tabel `user` + sesi nyata.
- Hash password (`passlib`/`bcrypt`) — jangan simpan plaintext.
- Simpan bertahap: audio → speaker → transcript → segment → assessment.
- **Selesai bila**: hasil evaluasi bertahan setelah server di-restart.

### Iterasi 6 — Halaman Histori & Penilaian Nyata
- Ganti tabel HTML hardcoded dengan query database.
- Halaman Penilaian menampilkan skor per indikator + feedback.
- **Selesai bila**: evaluasi yang baru dibuat langsung muncul di Histori tanpa mengubah kode.

### Iterasi 7 — Pengujian (§3.2.5)
- **Black Box**: registrasi, login, input audio, transkripsi, tampilan hasil evaluasi. Skenario di Lampiran 5 proposal.
- **White Box**: validasi audio, pra-pemrosesan, transkripsi, pra-pemrosesan teks, evaluasi LLM — pastikan setiap percabangan kondisi terlewati.
- **UAT**: 10 pertanyaan (aspek Sistem, Pengguna, Antarmuka) kepada guru.

> Catatan: §3.2.5 menyebut "tiga pendekatan" tetapi menulis "Black Box Testing dan User Acceptance Testing (UAT)" — sub-bab berikutnya memuat Whitebox. Pengujian yang dilakukan **tiga**: Black Box, White Box, UAT. Kalimat pengantar di proposal perlu diperbaiki agar konsisten.

### Iterasi 8 — Pengukuran Objektivitas (menjawab RM #2)
- Bandingkan skor sistem vs skor manual guru pada sampel respons lisan yang sama.
- Ukur tingkat kesepakatan (mis. Cohen's Kappa / korelasi) sebagaimana pendekatan Morris et al. (2024).
- **Selesai bila**: ada data kuantitatif yang bisa masuk BAB IV.

---

## 8. Perhitungan UAT (Tabel 3.9–3.10)

Bobot jawaban: **A = 4** (Sangat Baik/Sangat Mudah), **B = 3** (Baik/Mudah), **C = 2** (Cukup), **D = 1** (Kurang).

```
P = (ΣX / ΣXmaks) × 100

P      = persentase tingkat penerimaan sistem
ΣX     = jumlah total skor seluruh responden
ΣXmaks = jumlah pertanyaan × bobot tertinggi × jumlah responden
```

10 pertanyaan UAT:
- **Aspek Sistem** (1–4): menerima & memproses audio; menampilkan transkrip; memberi skor otomatis; berjalan tanpa error.
- **Aspek Pengguna** (5–7): membantu menilai ujian lisan; fitur histori memudahkan; meningkatkan objektivitas.
- **Aspek Antarmuka** (8–10): tampilan mudah dipahami; skor & umpan balik mudah dibaca; navigasi mudah.

---

## 9. Jadwal Riset (Tabel 3.11)

Rencana proposal: **Oktober 2025 – Maret 2026** — Penyusunan Proposal, Seminar Proposal, Analisis, Desain.

Tabel 3.11 pada proposal terpotong setelah baris "Desain" dan belum memuat baris Pengembangan, Pengujian, dan Penyusunan Laporan. Tabel tersebut perlu dilengkapi, dan rentang waktunya disesuaikan dengan kondisi terkini sebelum sidang.

---

## 10. Menjalankan Sistem

```sh
# Aktifkan virtual environment (Windows)
.\.venv\Scripts\activate

# Install dependensi
pip install -r requirements.txt

# Jalankan aplikasi penuh (FastAPI + Gradio ter-mount)
uvicorn main:app --reload
```

Akses di `http://127.0.0.1:8000`. Modul analisis ter-mount di `/gradio/analisis`.

Variabel lingkungan yang diperlukan di `.env` (belum diterapkan, lihat Iterasi 1 & 3):

```
HUGGINGFACE_TOKEN=...
GEMINI_API_KEY=...
```

Catatan lingkungan Windows: `app.py` menyetel `SB_NO_SYMLINK=1` dan `TORCH_AUDIOMENTATIONS_DISABLE_WARNINGS=1` — keduanya wajib agar speechbrain/pyannote berjalan tanpa hak administrator.

---

## 11. Rujukan Kunci dari Proposal

| Topik | Rujukan |
|---|---|
| Kelemahan NLP berbasis kemiripan kata | Ardian & Suryadi (2024); Sihombing (2022) |
| LLM setara penilai manusia | Morris et al. (2024) |
| Asesmen lisan butuh analisis konten transkrip | Bannò et al. (2023) |
| Arsitektur input–NLP–model cerdas | Chaudhari et al. (2025) |
| ASR untuk respons lisan | Sujjada et al. (2024) |
| Hasil ASR tanpa tanda baca menyulitkan analisis | Azis et al. (2025) |
| Speaker diarization | Laurent (2021); Jin et al. (2021) |
