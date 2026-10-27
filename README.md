# TCancy

Portal lowongan kerja dan magang untuk alumni HMTC ITS. Project ini dikerjakan untuk tugas Information
Security (kelompok 17), dengan fokus pada perlindungan data pribadi: seluruh data sensitif dan dokumen
disimpan dalam bentuk terenkripsi (AES, DES, RC4; mode non-ECB).

## Tech Stack

| Layer | Teknologi |
|---|---|
| Backend | FastAPI, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 16 |
| Rate limit | Redis 7 (penghitung request) |
| Frontend | Next.js 15, React 19, Tailwind CSS 3.4 |

## Prerequisites

- Docker (backend, PostgreSQL, dan Redis semuanya berjalan lewat Docker Compose)
- Node.js dan npm (hanya untuk frontend)

## Menjalankan Backend

```bash
cd backend
./setup-env.sh
docker compose up --build
```

API tersedia di `http://localhost:8010` (cek `http://localhost:8010/readyz`). Container API menunggu
PostgreSQL dan Redis sehat, menjalankan `alembic upgrade heads`, lalu menyalakan server. Tiga perintah
`perl` hanya perlu dijalankan sekali, untuk mengisi secret di `backend/.env`.

Perintah yang sering dipakai (jalankan dari `backend/`):

| Perintah | Fungsi |
|---|---|
| `docker compose up --build -d` | Jalankan di background |
| `docker compose logs -f api` | Lihat log API |
| `docker compose down` | Hentikan semua service (data tetap ada) |
| `docker compose down -v` | Hentikan dan hapus semua data (database dan upload) |
| `docker compose exec api python -m app.cli create-admin` | Buat akun admin (password ditanya lewat prompt) |

**Notes:**

- Setiap environment memakai secret masing-masing. Data terenkripsi dengan `MASTER_KEY` tertentu tidak
  dapat didekripsi dengan key lain, sehingga `MASTER_KEY` yang hilang berarti data tidak dapat dipulihkan.
- Compose menolak start bila `SESSION_SECRET`, `MASTER_KEY`, atau `BLIND_INDEX_KEY` kosong.
- Semua port hanya terbuka di `127.0.0.1`: PostgreSQL di `5433`, Redis di `6379`, API di `8010`. Bila `6379`
  sudah dipakai, set `REDIS_HOST_PORT` di `backend/.env` (misalnya `6380`).
- Compose memakai `COOKIE_SECURE=true` kecuali diubah. `.env.example` mengaturnya ke `false` supaya cookie
  jalan lewat `http://localhost`. Di production biarkan `true`.
- Container API berjalan sebagai user biasa (bukan root). Berkas upload disimpan di volume `uploads`.
- Redis hanya menyimpan penghitung rate limit, tanpa password dan tanpa penyimpanan ke disk. Data di
  dalamnya hilang saat container dihentikan, dan itu memang disengaja.
- Setelah pull perubahan storage (R7), semua anggota tim wajib menjalankan `docker compose down -v` sekali.
  Format penyimpanan berkas berubah, jadi berkas dan baris dokumen lama tidak bisa dibaca, dan volume
  `uploads` lama dimiliki root sehingga user non-root tidak bisa menulis ke dalamnya. `-v` menghapus semua
  data PostgreSQL dan upload lokal; unggah ulang dokumen setelahnya.

## Menjalankan Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend berjalan di `http://localhost:3000`, dan request ke `/api/v1/*` diteruskan ke
`http://localhost:8010`.

## Testing

Pastikan service berjalan (`docker compose up -d` dari `backend/`), lalu:

```bash
cd backend
docker compose exec postgres createdb -U tcancy tcancy_test   # sekali saja
docker compose run --rm \
  -e TEST_DATABASE_URL=postgresql+psycopg://tcancy:tcancy@postgres:5432/tcancy_test \
  -e REDIS_TEST_URL=redis://redis:6379/15 \
  api python -m pytest -q
```

**Notes:**

- Nama database testing harus berakhiran `_test`. Tes menghapus semua isinya, dan juga mengosongkan
  direktori upload di container tempat tes berjalan.
- Test membuat schema dengan `create_all` (bukan Alembic), sehingga migration tidak ikut teruji oleh
  `pytest`. Uji migration secara terpisah pada database kosong: `alembic upgrade heads`,
  `alembic downgrade base`, kemudian `alembic upgrade heads` kembali.
- Contract test di `backend/tests/contract/` harus tetap lulus, baik saat memakai stub maupun setelah
  stub diganti dengan implementasi asli.
- Tes Redis dilewati bila `REDIS_TEST_URL` tidak diisi. Tes hanya membuat dan menghapus key berawalan
  `rl:t-`.
- Lint backend: `ruff check .` di folder `backend` (konfigurasi di `backend/ruff.toml`, versi dipin di CI:
  `pip install ruff==0.8.6`).

## CI

GitHub Actions (`.github/workflows/ci.yml`) berjalan pada setiap push ke `main` dan setiap pull request:

| Job | Isi |
|---|---|
| `backend` | PostgreSQL 16 (database `tcancy_test`) dan Redis 7 sebagai service, `ruff check`, lalu `pytest` termasuk tes Redis |
| `frontend` | `npm ci`, `npm run build`, `npm run lint` (Node 22) |

**Notes:**

- `SESSION_SECRET`, `MASTER_KEY`, dan `BLIND_INDEX_KEY` dibuat acak pada setiap run dan tidak ada di repo.
  `COOKIE_SECURE=false` karena tes berjalan lewat HTTP.
- Action dipin ke commit SHA, bukan tag. Untuk memperbarui, ganti SHA dan komentar versinya bersamaan.

## Team

| Anggota | Fokus | Cakupan |
|---|---|---|
| Jason | Privasi dan akses | Profile terenkripsi dan blind index (email, NIK); consent per scope (profile, cv, video, identity) dan pencabutannya; aturan visibility untuk owner lowongan (data pelamar, akses CV/video, identitas dalam window 28 hari); batas download 20 per jam dan audit aksi owner; lowongan, lamaran, dashboard, matching, testimoni, dan fitur admin (kecuali audit dan benchmark) |
| Axel | Kriptografi dan dokumen | Implementasi crypto (AES, DES, RC4; mode non-ECB), vault, dan integrity check; upload, download, dan penghapusan dokumen terenkripsi, termasuk salinan dokumen per algorithm; endpoint analysis dan benchmark algorithm beserta rate limit-nya |
| Raynald | Auth dan keamanan platform | Authentication, session, dan password hashing; CSRF, rate limiting, batas ukuran request, dan audit log (append-only); storage, validasi tipe file, penghapusan akun, CLI, dan config; Dockerfile, `docker-compose.yml`, `.env.example`, `requirements.txt`, CI, dan test helper |
| Farel | Frontend dan integrasi | Frontend (Next.js) dan mock API sampai tersambung ke API asli; contract test, tools benchmark, dan dokumentasi; scaffold Fase 0 dan migration merge saat integrasi |