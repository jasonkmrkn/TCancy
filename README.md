# TCancy

Portal lowongan kerja dan magang untuk alumni HMTC ITS. Project ini dikerjakan untuk tugas Information
Security (kelompok 17), dengan fokus pada perlindungan data pribadi: seluruh data sensitif dan dokumen
disimpan dalam bentuk terenkripsi (AES, DES, RC4; mode non-ECB).

## Tech Stack

| Layer | Teknologi |
|---|---|
| Backend | FastAPI, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 16 |
| Frontend | Next.js 15, React 19, Tailwind CSS 3.4 |

## Prerequisites

- Python 3.11
- Node.js dan npm
- Docker (untuk PostgreSQL)

## Getting Started

### 1. Database

Jalankan service `postgres` dari `backend/docker-compose.yml` (port host `5433`), lalu buat dua database:
satu untuk aplikasi dan satu untuk testing.

**Notes:**

- Nama database testing harus berakhiran `_test`.

### 2. Environment Variables

Salin `backend/.env.example` menjadi `backend/.env`, lalu isi variable berikut:

| Variable | Deskripsi | Cara generate |
|---|---|---|
| `SESSION_SECRET` | Secret untuk session (minimal 32 byte) | `openssl rand -base64 32` |
| `MASTER_KEY` | Master key enkripsi (base64 dari 32 byte) | `openssl rand -base64 32` |
| `BLIND_INDEX_KEY` | Key untuk blind index (email, NIK) | `openssl rand -hex 32` |

**Notes:**

- Setiap environment memakai secret masing-masing. Data terenkripsi dengan `MASTER_KEY` tertentu tidak
  dapat didekripsi dengan key lain, sehingga `MASTER_KEY` yang hilang berarti data tidak dapat dipulihkan.
- Untuk pengembangan lokal via HTTP, set `COOKIE_SECURE=false`.
- Saat ini `docker-compose.yml` dan `.env.example` belum meneruskan `SESSION_SECRET`, sehingga container
  API gagal start sampai variable tersebut diisi.

### 3. Backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade heads
uvicorn app.main:app --port 8010
```

**Notes:**

- Gunakan `alembic upgrade heads`, bukan `head`, karena terdapat beberapa head migration.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend berjalan di `http://localhost:3000`, dan request ke `/api/v1/*` diteruskan ke
`http://localhost:8010`.

## Testing

```bash
export TEST_DATABASE_URL="postgresql+psycopg://<user>:<password>@localhost:5433/<nama>_test"
python -m pytest
```

**Notes:**

- Test membuat schema dengan `create_all` (bukan Alembic), sehingga migration tidak ikut teruji oleh
  `pytest`. Uji migration secara terpisah pada database kosong: `alembic upgrade heads`,
  `alembic downgrade base`, kemudian `alembic upgrade heads` kembali.
- Contract test di `backend/tests/contract/` harus tetap lulus, baik saat memakai stub maupun setelah
  stub diganti dengan implementasi asli.

## Team

| Anggota | Fokus | Cakupan |
|---|---|---|
| Jason | Privasi dan akses | Profile terenkripsi dan blind index (email, NIK); consent per scope (profile, cv, video, identity) dan pencabutannya; aturan visibility untuk owner lowongan (data pelamar, akses CV/video, identitas dalam window 28 hari); batas download 20 per jam dan audit aksi owner; lowongan, lamaran, dashboard, matching, testimoni, dan fitur admin (kecuali audit dan benchmark) |
| Axel | Kriptografi dan dokumen | Implementasi crypto (AES, DES, RC4; mode non-ECB), vault, dan integrity check; upload, download, dan penghapusan dokumen terenkripsi, termasuk salinan dokumen per algorithm; endpoint analysis dan benchmark algorithm beserta rate limit-nya |
| Raynald | Auth dan keamanan platform | Authentication, session, dan password hashing; CSRF, rate limiting, batas ukuran request, dan audit log (append-only); storage, validasi tipe file, penghapusan akun, CLI, dan config; Dockerfile, `docker-compose.yml`, `.env.example`, `requirements.txt`, CI, dan test helper |
| Farel | Frontend dan integrasi | Frontend (Next.js) dan mock API sampai tersambung ke API asli; contract test, tools benchmark, dan dokumentasi; scaffold Fase 0 dan migration merge saat integrasi |
