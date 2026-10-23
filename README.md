# Web Apps Surat Penawaran Multi Wilayah

Platform surat penawaran multi-wilayah (Pusat & Wilayah) untuk alur:
Client → Penawaran → Approval SPV (ttd digital) → Lock Client → Deal (PO/SPK) → Booking PIC →
Surat Tugas → LHPP → SKLK3 → Invoice → Faktur → Selesai.

## Jalankan

```bash
docker compose build
docker compose up -d          # backend di 127.0.0.1:8003
curl http://127.0.0.1:8003/api/v1/health
```

Dokumentasi API otomatis: `http://127.0.0.1:8003/api/docs`

## Akun awal (Pusat)

- Superadmin: `superadmin@suratpenawaran.id` / password di `backend/.env` (`SUPERADMIN_PASSWORD`) — **wajib diganti dari default**

## Struktur

- `backend/app/models` — 18 tabel (wilayah, users, clients, client_locks, master, penawaran, approval_logs, pic, pic_bookings, surat_tugas, lhpp, sklk3, invoice, audit, notif targets)
- `backend/app/api/v1` — router per domain
- `backend/app/services` — numbering, locks, notify (Telegram), pdf, files, seed, audit
- `docs/plans/` — rencana implementasi

## Aturan rahasia & lock

1. Client dapat dikunci global setelah penawaran disetujui SPV: **15 hari** (normal) / **7 hari** (nego).
2. Selama terkunci, wilayah lain **tidak bisa** membuat penawaran ke client tersebut (HTTP 409).
3. Detail harga penawaran hanya dapat dilihat wilayah pembuat + Pusat (HTTP 403 untuk wilayah lain).
4. Wilayah lain hanya melihat daftar publik: **nama perusahaan + kota**.
5. Pelepasan lock otomatis lewat `POST /api/v1/internal/maintenance` (cron harian).
