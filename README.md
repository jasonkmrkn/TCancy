# TCancy

Portal lowongan kerja dan magang alumni HMTC ITS. Project tugas Information Security (kelompok 17):
semua data pribadi dan dokumen disimpan dalam bentuk terenkripsi (AES, DES, RC4; mode non-ECB).

- Backend: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16
- Frontend: Next.js 15, React 19, Tailwind 3.4

## Cara menjalankan

**Database (Docker, hanya PostgreSQL):** service `postgres` di `backend/docker-compose.yml`, port host 5433.
Buat dua database: satu untuk aplikasi dan satu untuk test. Nama database test **harus berakhiran `_test`**.

**Backend** (dari folder `backend`, dengan virtual environment Python 3.11):

```bash
pip install -r requirements.txt
alembic upgrade heads        # bukan "head": ada beberapa head migration
uvicorn app.main:app --port 8010
```

**Frontend** (dari folder `frontend`): `npm install`, lalu `npm run dev` (port 3000). Request ke `/api/v1/*`
di-forward ke `http://localhost:8010`.

## Environment variable

Salin `backend/.env.example` ke `.env` (jangan di-commit). Secret berikut **wajib** diisi dan berbeda di tiap
mesin, jangan dikirim lewat chat:

| Variable | Cara membuat |
|---|---|
| `SESSION_SECRET` (minimal 32 byte) | `openssl rand -base64 32` |
| `MASTER_KEY` (base64 dari 32 byte) | `openssl rand -base64 32` |
| `BLIND_INDEX_KEY` | `openssl rand -hex 32` |

Catatan:

- Kalau `MASTER_KEY` hilang, data terenkripsi tidak bisa dibuka lagi. Data dari satu mesin juga tidak bisa
  dibuka di mesin lain yang memakai key berbeda.
- Untuk HTTP lokal, set `COOKIE_SECURE=false`.
- Saat ini `docker-compose.yml` dan `.env.example` belum meneruskan `SESSION_SECRET`, sehingga container API
  gagal start sampai variable itu diisi.

## Testing

```bash
export TEST_DATABASE_URL="postgresql+psycopg://<user>:<password>@localhost:5433/<nama>_test"
python -m pytest
```

Test membuat schema dengan `create_all` (bukan Alembic), jadi migration tidak ikut teruji oleh `pytest`.
Uji migration secara terpisah pada database kosong: `alembic upgrade heads`, `alembic downgrade base`,
lalu `alembic upgrade heads` lagi.

Contract test di `backend/tests/contract/` harus tetap hijau, baik saat memakai stub maupun saat stub sudah
diganti implementasi asli.

## Jobdesk

| Anggota | Fokus | Cakupan |
|---|---|---|
| Jason | Privasi dan akses | Profile terenkripsi dan blind index (email, NIK); consent per scope (profile, cv, video, identity) dan pencabutannya; aturan visibility untuk owner lowongan (data pelamar, akses CV/video, identitas dalam window 28 hari); batas download 20 per jam dan audit aksi owner; lowongan, lamaran, dashboard, matching, testimoni, dan fitur admin (kecuali audit dan benchmark) |
| Axel | Kriptografi dan dokumen | Implementasi crypto (AES, DES, RC4; mode non-ECB), vault, dan integrity check; upload, download, dan penghapusan dokumen terenkripsi, termasuk salinan dokumen per algorithm; endpoint analysis dan benchmark algorithm beserta rate limit-nya |
| Raynald | Auth dan keamanan platform | Authentication, session, dan password hashing; CSRF, rate limiting, batas ukuran request, dan audit log (append-only); storage, validasi tipe file, penghapusan akun, CLI, dan config; Dockerfile, `docker-compose.yml`, `.env.example`, `requirements.txt`, CI, dan test helper |
| Farel | Frontend dan integrasi | Frontend (Next.js) dan mock API sampai tersambung ke API asli; contract test, tools benchmark, dan dokumentasi; scaffold Fase 0 dan migration merge saat integrasi |
