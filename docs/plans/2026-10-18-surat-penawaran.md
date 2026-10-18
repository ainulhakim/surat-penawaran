# Web Apps Surat Penawaran Multi Wilayah — Implementation Plan

**Goal:** Aplikasi surat penawaran multi-wilayah (Pusat + Wilayah) dengan workflow rahasia, lock client, approval SPV ber-tanda-tangan digital, penjadwalan PIC, surat tugas, LHPP, SKLK3, dan invoice.

**Architecture:** FastAPI (API-first, `/api/v1`) + PostgreSQL 16 + SQLAlchemy 2.0. Notifikasi via Bot Telegram (multi-kanal: SPV/Pimpinan, Grup Admin, Grup Keuangan). UI server-rendered (Jinja2 + Bootstrap/HTMX) — API tetap tersedia untuk klien lain/Next.js di masa depan.

**Tech Stack:** Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, psycopg3, pydantic v2, python-jose (JWT), passlib+bcrypt 4.2.1, reportlab (PDF), Docker Compose.

**Deploy:** Hermes Sumopod (ubuntu@100.122.7.126) — backend `127.0.0.1:8003`, Postgres `127.0.0.1:5435`, volume `sp_pgdata` + `sp_uploads`.

---

## Aturan bisnis kunci (dari brief 29 poin)

1. Pusat (SUPERADMIN) CRUD semua wilayah; Wilayah punya Admin sendiri (poin 1-3, 27).
2. Client terpusat, kunci unik = `lower(nama_perusahaan) + lower(email) + lower(kota) + kodepos` (poin 4).
3. Kategori → Bidang → Objek sebagai master data Pusat (poin 5).
4. Harga penawaran diisi manual Admin Wilayah (poin 6).
5. SPV wilayah approve/revisi + tanda tangan digital image (poin 7-8).
6. Setelah approve: masuk dashboard, **lock client 15 hari** (poin 9-10). Nego → **7 hari** (poin 12).
7. Penawaran rahasia: hanya wilayah pembuat + Pusat (poin 11). Wilayah lain hanya lihat nama perusahaan + kota (poin 28).
8. Deal: input tanggal PO + nomor SPK (poin 13).
9. PIC: master data + agenda + booking + reschedule/approve (poin 14-16).
10. Surat Tugas auto-generate PDF + ttd SPV, bisa diunduh/dicetak (poin 17-19).
11. LHPP: deadline 7 hari + reminder Telegram + checklist + bukti screenshot opsional (poin 20-24).
12. SKLK3: submit tanggal muncul (poin 25).
13. Invoice: tanggal otomatis/bisa diatur, notif Telegram ke Grup Keuangan untuk faktur (poin 26).
14. Template surat tugas (poin 29).

## Status Implementasi

- [x] **Phase 1 — Core & separator wilayah**: models lengkap (wilayah, users, clients, master, penawaran, approval, lock, PIC, booking, surat tugas, lhpp, sklk3, invoice, audit, notif target), auth JWT, RBAC, CRUD wilayah/users/clients/master, penawaran workflow, eksekusi (PIC→invoice), dashboard, maintenance cron. **44/44 smoke test pass.**
- [ ] **Phase 2 — UI Admin/Pusat** (Jinja + Bootstrap): login, dashboard, CRUD client, form penawaran + item harga manual, halaman approval SPV (kanvas tanda tangan), upload ttd.
- [ ] **Phase 3 — PIC & Surat Tugas**: halaman agenda/booking, template surat tugas editable, download/print PDF.
- [ ] **Phase 4 — LHPP/SKLK3/Invoice**: halaman checklist, upload bukti, halaman keuangan.
- [ ] **Phase 5 — Bot Telegram**: bot khusus (approval inline button, notif multi-grup), webhook.
- [ ] **Phase 6 — Hardening**: Alembic migration, rate limit login, OWASP review, backup harian, CF tunnel `penawaran.ainulhakim.com`.

## Endpoint utama (sudah live)

- `POST /api/v1/auth/login`, `GET /auth/me`, `POST /auth/change-password`, `POST /users/me/ttd`
- `GET|POST|PATCH|DELETE /api/v1/wilayah` (Pusat)
- `GET|POST|PATCH|DELETE /api/v1/users`
- `GET|POST|PATCH|DELETE /api/v1/clients`, `GET /clients/publik`
- `GET|POST /api/v1/master/{kategori,bidang,objek}`
- `POST /penawaran`, `PATCH /penawaran/{id}`, `POST /penawaran/{id}/submit`, `/approval`, `/deal`, `GET /penawaran/{id}/riwayat`, `GET /penawaran/publik`
- `GET|POST /pic`, `GET /pic/agenda`, `POST /booking`, `POST /booking/{id}/respond`, `POST /surat-tugas/dari-booking/{id}`, `POST /surat-tugas/{id}/approve`, `GET /surat-tugas/{id}/pdf`
- `POST /lhpp/{penawaran_id}`, `PATCH /lhpp/{id}`, `POST /sklk3/{id}`, `POST /invoice/{id}`, `POST /invoice/{id}/faktur`
- `GET /dashboard/summary`, `POST /internal/maintenance` (cron: release lock kedaluwarsa + reminder LHPP)

## Verifikasi

```bash
cd /home/ubuntu/surat-penawaran
docker compose ps                       # sp-backend healthy, sp-postgres healthy
curl -sS http://127.0.0.1:8003/api/v1/health
python3 /tmp/sp_smoke.py                # 44/44 langkah OK
docker exec sp-backend ls /app/uploads/surat_tugas/   # PDF surat tugas
```

## Pitfalls yang sudah ditemui

- `email-validator` wajib untuk `EmailStr` pydantic (ImportError saat start).
- Jangan `User(**data, email=...)` bila `data` masih memuat `email` → TypeError multiple values.
- bcrypt 4.2.1 + passlib memunculkan warning `__about__` (harmless, jangan upgrade ke 5.x).
- `docker compose up -d` diblokir di terminal foreground → jalankan via `background=true`.
