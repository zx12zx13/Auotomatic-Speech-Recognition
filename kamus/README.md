# Kamus untuk koreksi salah dengar ASR

Tiga berkas di direktori ini menentukan seberapa jauh `koreksi_fonetik.py`
dapat memperbaiki transkrip. Semuanya teks biasa, satu entri per baris, baris
diawali `#` diabaikan.

| Berkas | Peran |
|---|---|
| `koreksi_dikenal.txt` | Pasangan `salah = benar` yang sudah terbukti. Diperiksa paling dahulu. |
| `glosarium_informatika.txt` | Istilah bidang. Dilindungi dari koreksi **dan** menjadi kandidat pengganti. |
| `kata_indonesia.txt` | Kata umum bahasa Indonesia. Melindungi kata sah agar tidak diubah. |

## Yang perlu Anda lengkapi: `kata_indonesia.txt`

Berkas yang disertakan hanyalah **daftar awal**, bukan kamus lengkap. Selama
isinya masih di bawah 5.000 kata, sistem sengaja bekerja secara konservatif:

- kata di dalamnya tetap dilindungi (tidak akan diubah), tetapi
- **kandidat pengganti dibatasi pada glosarium istilah saja.**

Alasannya penting. Gerbang kamus baru benar-benar melindungi bila kamusnya
lengkap. Dengan daftar kecil, kata sah yang kebetulan belum terdaftar akan
lolos ke tahap pencocokan lalu berpeluang tergantikan kata lain — justru
kerusakan yang ingin dicegah. Lebih baik sistem mengoreksi sedikit tetapi
benar, daripada banyak tetapi merusak jawaban siswa.

Batas ini terbaca di kolom `Status koreksi` pada hasil pemrosesan, sehingga
keterbatasannya tidak pernah tersamar.

### Cara melengkapinya

Ganti isi `kata_indonesia.txt` dengan daftar kata dasar dan berimbuhan bahasa
Indonesia (satu kata per baris, huruf kecil). Sumber yang lazim dipakai:

- daftar kata KBBI yang tersedia terbuka,
- daftar kata dari korpus teks pelajaran yang relevan,
- gabungan keduanya, disaring dari kata yang jelas keliru.

Setelah daftarnya melampaui 5.000 kata, sistem otomatis memakai kata umum
sebagai kandidat pengganti, sehingga kesalahan seperti `pemproses` →
`pemroses` ikut tertangani tanpa perlu ditulis satu per satu di
`koreksi_dikenal.txt`.

## Menumbuhkan `koreksi_dikenal.txt`

Setiap kali menemukan salah dengar baru pada transkrip sungguhan, tambahkan
barisnya. Daftar ini memang dirancang tumbuh dari pengamatan, bukan disusun
sekali di awal.

**Hati-hati:** berkas ini mengalahkan gerbang kamus. Kata yang sah pun akan
tergantikan bila ditulis di sini — misalnya `bait = byte`, yang tepat untuk
materi Sistem Komputer tetapi keliru bila rekamannya membahas puisi. Tulis
hanya pasangan yang bentuk benarnya tidak meragukan pada mata pelajaran yang
sedang diujikan.

## Menyesuaikan glosarium

`glosarium_informatika.txt` disusun untuk materi Sistem Komputer, Informatika
Kelas VII. Untuk materi lain, ganti isinya dengan istilah materi tersebut.
Makin sesuai glosarium dengan topik rekaman, makin tepat koreksinya — dan
makin kecil peluang salah koreksi, karena kandidat yang tersedia memang
terbatas pada istilah yang relevan.
