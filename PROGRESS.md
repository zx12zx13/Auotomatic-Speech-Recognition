# PROGRESS.md

Status realisasi produk terhadap proposal. Rencana lengkap ada di [PLANNING.md](PLANNING.md).

**Tanggal peninjauan**: 16 Juli 2026 (diperbarui setelah Iterasi 1 selesai)
**Basis peninjauan**: `app.py`, `main.py`, `requirements.txt`, `templates/`, riwayat git (5 commit).

**Status iterasi**: Iterasi 1 (Stabilkan MVP Pipeline) dan Iterasi 2 (Validasi Audio) — ✅ **selesai & terverifikasi**. Iterasi 3 (Evaluasi LLM) — ⚠️ **kode selesai, belum lolos kriteria "selesai"** karena belum pernah dijalankan dengan Gemini API sungguhan (`GEMINI_API_KEY` belum diisi). Iterasi 4–8 belum mulai.

---

## Ringkasan

Pipeline **ASR + Speaker Diarization sudah berjalan** dan itu adalah pencapaian terbesar sejauh ini. Namun **modul evaluasi LLM — inti kontribusi ilmiah penelitian — belum ada sama sekali**, dan seluruh persistensi data masih palsu (dictionary di memori + tabel HTML hardcoded).

Kondisi produk saat ini setara dengan **"sistem transkripsi + diarisasi"**, bukan **"sistem evaluasi"**. Proposal sendiri menegaskan (Ardian & Suryadi, 2024) bahwa sistem yang berhenti di transkripsi tanpa metode evaluasi yang jelas *tidak memberikan kontribusi ilmiah yang signifikan*. Karena itu, prioritas mutlak berikutnya adalah **Iterasi 3 (Evaluasi LLM)**.

Setelah Iterasi 1, seluruh **tahap pemrosesan audio (KF #1–#4) kini berjalan dan terverifikasi**. Yang tersisa justru bagian yang menentukan nilai penelitian: evaluasi, penyimpanan, dan pelaporan hasil.

**Estimasi penyelesaian terhadap 8 kebutuhan fungsional proposal: 4 dari 8 (± 50%)** — KF #1 masih kurang fitur perekaman langsung lewat sistem (saat ini hanya upload).

---

## Status Kebutuhan Fungsional (§3.2.1 Proposal)

| # | Kebutuhan | Status | Keterangan |
|---|---|---|---|
| 1 | Menerima input rekaman audio | ✅ Selesai | `gr.Audio(type="filepath")` + `validate_audio()` (format, ukuran, durasi, corrupt). Hanya upload; perekaman langsung lewat sistem belum ada |
| 2 | Pra-pemrosesan audio (normalisasi + noise reduction) | ✅ Selesai | BUG-01 diperbaiki & diuji: puncak amplitudo audio uji naik 0,135 → 0,989 dan `reduce_noise` berjalan |
| 3 | Speaker diarization maks. 5 pembicara | ✅ Selesai | Konstanta `MAX_SPEAKERS = 5`, ditegakkan di slider **dan** di `asr_pipeline()` via `min()` |
| 4 | Transkripsi ASR | ✅ Selesai | Whisper "medium", termasuk timestamp per segmen |
| 5 | Pra-pemrosesan teks | ❌ Tidak sesuai | Yang ada: kamus slang regex + penghitung 5 kata terbanyak. Tidak satupun diminta proposal |
| 6 | **Evaluasi otomatis berbasis rubrik** | ⚠️ Kode selesai, **belum diuji dengan API sungguhan** | `evaluator.py`: rubrik Tabel 3.1 sebagai data, prompt terstruktur, Gemini structured output. Butuh `GEMINI_API_KEY` |
| 7 | **Menghasilkan skor + umpan balik naratif** | ⚠️ Kode selesai, **belum diuji dengan API sungguhan** | Skor per indikator + skor akhir (rata-rata) + umpan balik; tampil di tab "Penilaian" |
| 8 | Menyimpan & menampilkan hasil evaluasi | ❌ Palsu | Histori & Penilaian berisi data dummy hardcoded (`rapat_q3_2023.mp3`, dll.) |

## Status Kebutuhan Non-Fungsional

| # | Kebutuhan | Status | Keterangan |
|---|---|---|---|
| 1 | Antarmuka sederhana untuk guru | ✅ Sebagian | Dashboard + sidebar + modul Gradio ter-mount sudah berjalan |
| 2 | Tidak butuh perangkat khusus | ⚠️ | Whisper "medium" berat di CPU. Perlu diukur waktu prosesnya untuk audio 5–10 menit |
| 3 | Hasil konsisten & terdokumentasi | ❌ | Tidak ada dokumentasi hasil karena tidak ada database |
| 4 | Modular | ✅ | `local_nlp_processing`, `pyannote_diarization`, `preprocess_audio`, `asr_pipeline` terpisah rapi |
| 5 | **Keamanan data audio & hasil evaluasi** | ❌ **Kritis** | Lihat BUG-02 dan BUG-03 |

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
| [9] Pra-pemrosesan Teks | ❌ Yang ada bukan yang diminta proposal |
| [10] **Evaluasi LLM** | ⚠️ `evaluator.py` selesai; menunggu `GEMINI_API_KEY` untuk uji end-to-end |

---

## Status Halaman (§3.2.3.4)

| Halaman | Template/Rute | Status |
|---|---|---|
| Login | `templates/login.html` + `POST /login` | ⚠️ Jalan, tapi password plaintext & sesi palsu |
| Registrasi | `templates/register.html` + `POST /register` | ⚠️ Jalan, validasi password cocok & username unik ada |
| Dashboard | `templates/dashboard.html` | ✅ Jalan |
| Analisis Audio | Gradio di `/gradio/analisis` | ✅ Jalan (tanpa evaluasi) |
| Histori | `/histori-content` | ❌ HTML + data dummy hardcoded di dalam `main.py` |
| Penilaian | `/nilai-content` | ❌ HTML + data dummy hardcoded di dalam `main.py` |

---

## Status Database (§3.2.3.3)

**Belum ada database sama sekali.** Tidak ada engine SQL, ORM, migrasi, maupun file `.db`.

| Tabel | Status |
|---|---|
| `user` | ❌ Diganti `fake_user_db = {"admin": "password"}` di memori |
| `audio` | ❌ Belum ada |
| `speaker` | ❌ Belum ada |
| `transcript` | ❌ Belum ada |
| `segment` | ❌ Belum ada |
| `assessment` | ❌ Belum ada |

Konsekuensi: seluruh akun dan hasil analisis **hilang setiap kali server di-restart**. Klaim proposal bahwa "sistem menyimpan setiap hasil proses ke dalam database secara bertahap" (§3.2.3.2, Histori Transkrip) belum terpenuhi.

---

## Status Pengujian (§3.2.5)

| Pengujian | Status |
|---|---|
| Black Box | ❌ Belum dilaksanakan |
| White Box | ❌ Belum dilaksanakan |
| UAT (10 pertanyaan, responden guru) | ❌ Belum dilaksanakan |
| Pengukuran objektivitas vs penilaian manual guru (RM #2) | ❌ Belum dilaksanakan |

Tidak ada berkas test di repositori. Karena model pengembangan Agile mengharuskan pengujian bertahap per modul, mulai menulis skenario Black Box begitu Iterasi 2 selesai — jangan tunggu semua fitur rampung.

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

### BUG-03 — Password disimpan dan dibandingkan dalam bentuk plaintext (Tinggi, keamanan) — *terbuka*
`main.py:174` membandingkan `fake_user_db[username] == password` secara langsung. Perlu hashing (`bcrypt`) saat implementasi tabel `user` di Iterasi 5.

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
5. Iterasi 4 (Pra-pemrosesan Teks sesuai proposal).
6. Iterasi 5 (Database) → Iterasi 6 (Histori & Penilaian nyata).
7. Iterasi 7 (Black Box, White Box, UAT) → Iterasi 8 (pengukuran objektivitas vs guru).

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

1. **Evaluasi memakai transkrip penuh (`full_text`), bukan teks khusus siswa.** Bila rekaman memuat suara guru, ucapan guru ikut dinilai. §3.2.2 poin 9 proposal mensyaratkan teks disusun ulang dan "memfokuskan pada pembicara yang menjadi objek evaluasi" — ini baru akan tertangani di **Iterasi 4**. Sampai saat itu, gunakan rekaman yang hanya berisi suara siswa agar hasil penilaian sahih.
2. **Belum ada penyimpanan hasil evaluasi.** Skor dan umpan balik hanya tampil di layar dan hilang setelah proses berikutnya (menunggu Iterasi 5).
3. **Belum ada mekanisme percobaan ulang (retry).** Kegagalan sementara API langsung dilaporkan sebagai gagal. Ini disengaja agar kegagalan terlihat, bukan tersamar.

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
