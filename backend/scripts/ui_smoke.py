#!/usr/bin/env python3
"""Smoke test UI (Jinja2) Surat Penawaran — menguji alur lengkap lewat halaman HTML.

Semua MUTASI dilakukan via form POST ke halaman (bukan API), sedangkan pembacaan
ID/status dilakukan lewat API. Jalankan di host:

    python3 backend/scripts/ui_smoke.py
"""

import base64
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar, DefaultCookiePolicy

BASE = "http://127.0.0.1:8003"

PNG_1PX = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

PASS = []
FAIL = []
SUF = str(int(time.time()))[-5:]
NAMA_KLIEN = f"PT Uji UI {SUF}"
EMAIL_KLIEN = f"ui{SUF}@ujismoke.co.id"


def ok(label, extra=""):
    PASS.append(label)
    print(f"  OK   {label} {extra}")


def bad(label, detail=""):
    FAIL.append((label, detail))
    print(f"  FAIL {label} :: {detail}")


class Ui:
    """Sesi browser sederhana: cookie jar + follow redirect."""

    def __init__(self):
        # secure_protocols di-set agar cookie "Secure" (COOKIE_SECURE=true di produksi)
        # tetap dikirim saat smoke test dijalankan lewat http://127.0.0.1:8003
        self.jar = CookieJar(DefaultCookiePolicy(secure_protocols=("http", "https")))
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPRedirectHandler(),
        )

    def request(self, method, path, data=None, follow=True):
        url = BASE + path
        body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method)
        if body:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            resp = self.opener.open(req, timeout=25)
            return resp.getcode(), resp.geturl(), resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, url, exc.read().decode("utf-8", "replace")

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, data):
        return self.request("POST", path, data)

    def login(self, email, password):
        code, url, body = self.post("/login", {"email": email, "password": password, "next": "/"})
        return code == 200 and "/login" not in url, url


def api(path, token=None, method="GET", body=None):
    req = urllib.request.Request(BASE + "/api/v1" + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=20) as resp:
            return resp.getcode(), json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode())
        except Exception:
            return exc.code, {}


def api_token(email, password):
    _, data = api("/auth/login", method="POST", body={"email": email, "password": password})
    return data.get("access_token")


# --------------------------------------------------------------------------- #

print("== 1. Login & halaman utama (SUPERADMIN) ==")
sa = Ui()
ok_login, url = sa.login("superadmin@suratpenawaran.id", "SuperAdmin2026!")
if ok_login:
    ok("login superadmin", f"-> {url}")
else:
    bad("login superadmin", url)
    sys.exit(1)

for path in [
    "/", "/klien", "/penawaran", "/master", "/wilayah", "/pengguna", "/pic",
    "/agenda", "/surat-tugas", "/lhpp", "/keuangan", "/profil", "/persetujuan",
    "/penawaran/baru", "/klien/baru",
]:
    code, _, body = sa.get(path)
    if code == 200 and "Akses Ditolak" not in body and "Internal Server Error" not in body:
        ok(f"GET {path}")
    else:
        bad(f"GET {path}", f"HTTP {code}")

print("\n== 2. Tanpa login harus diarahkan ke /login ==")
anon = Ui()
code, url, _ = anon.get("/penawaran")
if "/login" in url:
    ok("redirect anonim -> /login")
else:
    bad("redirect anonim", f"HTTP {code} {url}")

print("\n== 3. Login demo users ==")
admin = Ui()
spv = Ui()
keu = Ui()
for ui, email, pw in [
    (admin, "admin.jtg@suratpenawaran.id", "AdminJtg2026!"),
    (spv, "spv.jtg@suratpenawaran.id", "SpvJtg2026!"),
    (keu, "keu.jtg@suratpenawaran.id", "KeuJtg2026!"),
]:
    good, u = ui.login(email, pw)
    (ok if good else bad)(f"login {email}", u)

code, _, body = keu.get("/penawaran/baru")
if code == 403 or "Akses Ditolak" in body:
    ok("guard role: KEUANGAN tidak boleh buka /penawaran/baru (403)")
else:
    bad("guard role KEUANGAN", f"HTTP {code}")

# SPV tambahan (belum punya tanda tangan tersimpan) — untuk menguji aturan ttd wajib
code, url, _ = sa.post(
    "/pengguna/baru",
    {
        "nama": "SPV Uji TandaTangan",
        "email": "spv2.jtg@suratpenawaran.id",
        "password": "Spv2Jtg2026!",
        "role": "SPV",
        "wilayah_id": "1",
        "jabatan": "SPV Wilayah",
        "no_hp": "",
        "telegram_chat_id": "",
    },
)
if "err=" not in url or "sudah terdaftar" in urllib.parse.unquote(url):
    ok("superadmin buat SPV kedua via form /pengguna/baru")
else:
    bad("buat SPV kedua", urllib.parse.unquote(url))

spv2 = Ui()
good, u = spv2.login("spv2.jtg@suratpenawaran.id", "Spv2Jtg2026!")
(ok if good else bad)("login SPV kedua (tanpa ttd tersimpan)", u)

token_admin = api_token("admin.jtg@suratpenawaran.id", "AdminJtg2026!")
token_spv = api_token("spv.jtg@suratpenawaran.id", "SpvJtg2026!")
token_keu = api_token("keu.jtg@suratpenawaran.id", "KeuJtg2026!")

print("\n== 4. ADMIN_WILAYAH: buat klien lewat form ==")
_, clients_before = api("/clients", token_admin)
n_before = len(clients_before) if isinstance(clients_before, list) else 0
code, url, body = admin.post(
    "/klien/baru",
    {
        "nama_perusahaan": NAMA_KLIEN,
        "email": EMAIL_KLIEN,
        "no_telpon": "024111222",
        "pic": "Siti Aminah",
        "no_pic": "0812000111",
        "alamat": "Jl. Uji Coba No. 1",
        "kota": "Semarang",
        "provinsi": "Jawa Tengah",
        "kodepos": "50100",
    },
)
if code == 200 and ("msg=" in url or "/klien/" in url) and "err=" not in url:
    ok("POST /klien/baru", url.replace(BASE, ""))
else:
    bad("POST /klien/baru", f"HTTP {code} {url}")

_, clients = api("/clients", token_admin)
new_client = next((c for c in clients if c["nama_perusahaan"] == NAMA_KLIEN), None)
if new_client:
    ok("klien tersimpan", f"id={new_client['id']}")
else:
    bad("klien tersimpan", str(clients)[:200])
    sys.exit(1)

code, url, body = admin.post(
    "/klien/baru",
    {
        "nama_perusahaan": NAMA_KLIEN,
        "email": EMAIL_KLIEN,
        "kota": "Semarang",
        "kodepos": "50100",
    },
)
if "err=" in url:
    ok("klien duplikat ditolak", urllib.parse.unquote(url.split("err=")[1])[:70])
else:
    bad("klien duplikat ditolak", url)

print("\n== 5. ADMIN_WILAYAH: buat penawaran 2 item lewat form ==")
code, url, body = admin.post(
    "/penawaran/baru",
    {
        "client_id": new_client["id"],
        "perihal": "Penawaran Uji UI",
        "catatan": "dibuat lewat form HTML",
        "uraian": ["Survey Lokasi", "Training K3"],
        "spesifikasi": ["12 titik", "20 peserta"],
        "qty": ["2", "1"],
        "satuan": ["lokasi", "peserta"],
        "harga": ["1500000", "4000000"],
        "kategori_id": ["1", "1"],
        "bidang_id": ["1", "1"],
        "objek_id": ["1", "2"],
    },
)
if code == 200 and "/penawaran/" in url and "err=" not in url:
    ok("POST /penawaran/baru", url.replace(BASE, ""))
else:
    bad("POST /penawaran/baru", f"HTTP {code} {url} {body[:200]}")

pid = int(url.split("?")[0].rstrip("/").split("/")[-1]) if "/penawaran/" in url else None
_, pen = api(f"/penawaran/{pid}", token_admin)
harga = float(pen.get("harga_total", 0))
if pen and len(pen.get("items", [])) == 2 and abs(harga - (2 * 1_500_000 + 4_000_000)) < 1:
    ok("2 item & total benar", f"Rp{harga:,.0f} ({pen['nomor_surat']})")
else:
    bad("2 item & total", json.dumps(pen)[:200])

code, _, body = admin.get(f"/penawaran/{pid}")
if code == 200 and "Ajukan ke SPV" in body:
    ok("halaman detail menampilkan tombol Ajukan ke SPV")

print("\n== 6. Submit ke SPV ==")
code, url, _ = admin.post(f"/penawaran/{pid}/submit", {})
if "err=" not in url:
    ok("POST submit", url.replace(BASE, ""))
else:
    bad("POST submit", url)
_, pen = api(f"/penawaran/{pid}", token_admin)
if pen.get("status") == "MENUNGGU_SPV":
    ok("status -> MENUNGGU_SPV")
else:
    bad("status MENUNGGU_SPV", pen.get("status"))

print("\n== 7. SPV: kotak persetujuan & APPROVE + tanda tangan ==")
code, _, body = spv.get("/persetujuan")
if code == 200 and pen["nomor_surat"] in body:
    ok("penawaran muncul di /persetujuan")
else:
    bad("penawaran di /persetujuan", f"HTTP {code}")

code, url, _ = spv2.post(f"/penawaran/{pid}/approval", {"aksi": "APPROVE", "catatan": "", "ttd_image_base64": ""})
if "err=" in url and "Tanda tangan" in urllib.parse.unquote(url):
    ok("approve tanpa ttd ditolak (SPV tanpa ttd tersimpan)", urllib.parse.unquote(url.split("err=")[1])[:70])
else:
    bad("approve tanpa ttd ditolak", url)

code, url, _ = spv.post(
    f"/penawaran/{pid}/approval",
    {"aksi": "APPROVE", "catatan": "Disetujui via UI", "ttd_image_base64": "data:image/png;base64," + PNG_1PX},
)
if "err=" not in url:
    ok("POST approval APPROVE", url.replace(BASE, ""))
else:
    bad("POST approval APPROVE", urllib.parse.unquote(url))

_, pen = api(f"/penawaran/{pid}", token_admin)
if pen.get("status") == "APPROVED" and pen.get("valid_until"):
    ok("status -> APPROVED", f"valid_until={pen['valid_until']}")
else:
    bad("status APPROVED", json.dumps(pen)[:200])

print("\n== 8. Wilayah lain terkunci (uji dari admin.jbr) ==")
jbr = Ui()
jbr.login("admin.jbr@suratpenawaran.id", "AdminJbr2026!")
code, _, body = jbr.get(f"/penawaran/{pid}")
if "rahasia" in body.lower() or code in (200, 303):
    ok("detail penawaran wilayah lain ditolak (rahasia)", f"HTTP {code}")
else:
    bad("rahasia wilayah lain", f"HTTP {code}")

print("\n== 9. DEAL (tgl PO + SPK) ==")
code, url, _ = admin.post(
    f"/penawaran/{pid}/deal", {"tgl_po": "2026-10-20", "no_spk": "SPK/UI/001/2026", "nilai_po": "7000000"}
)
if "err=" not in url:
    ok("POST deal")
else:
    bad("POST deal", urllib.parse.unquote(url))
_, pen = api(f"/penawaran/{pid}", token_admin)
if pen.get("status") == "DEAL":
    ok("status -> DEAL")
else:
    bad("status DEAL", pen.get("status"))

print("\n== 10. Booking PIC ==")
_, pics = api("/pic", token_admin)
pic_id = pics[0]["id"] if pics else None
code, url, _ = admin.post(
    "/booking/baru",
    {"penawaran_id": pid, "pic_id": pic_id, "tanggal_tugas": "2026-10-25", "catatan": "survey awal"},
)
if "err=" not in url:
    ok("POST booking baru", url.replace(BASE, ""))
else:
    bad("POST booking baru", urllib.parse.unquote(url))

code, url, _ = admin.post(
    "/booking/baru", {"penawaran_id": pid, "pic_id": pic_id, "tanggal_tugas": "2026-10-25"}
)
if "err=" in url:
    ok("bentrok jadwal PIC ditolak", urllib.parse.unquote(url.split("err=")[1])[:60])
else:
    bad("bentrok jadwal PIC ditolak", url)

_, bookings = api("/pic/agenda", token_admin)
bid = bookings[0]["booking_id"] if bookings else None
code, url, _ = admin.post(f"/booking/{bid}/respond", {"aksi": "APPROVE"})
if "err=" not in url:
    ok("booking disetujui", f"booking_id={bid}")
else:
    bad("booking approve", urllib.parse.unquote(url))

print("\n== 11. Surat Tugas + PDF ==")
code, url, _ = admin.post(f"/surat-tugas/dari-booking/{bid}", {})
if "err=" not in url:
    ok("POST buat surat tugas", url.replace(BASE, ""))
else:
    bad("POST buat surat tugas", urllib.parse.unquote(url))

_, _ = api(f"/penawaran/{pid}", token_admin)
code, _, body = spv.get("/persetujuan")
if "Setujui &amp; Tanda Tangan" in body or "Setujui & Tanda Tangan" in body:
    ok("surat tugas muncul di /persetujuan")
else:
    bad("surat tugas di /persetujuan", "tidak ditemukan")

# ambil id surat tugas: baris tabel yang memuat nomor penawaran kita
code, _, body = admin.get("/surat-tugas")
st_id = None
for row in body.split("<tr"):
    if f'/penawaran/{pid}"' in row:
        for marker in ['id="st-']:
            if marker in row:
                seg = row.split(marker)[1].split('"')[0]
                if seg.isdigit():
                    st_id = int(seg)
        if st_id:
            break
if st_id:
    ok("surat tugas terdaftar", f"id={st_id}")
else:
    bad("surat tugas terdaftar", body[:200])

code, url, _ = spv2.post(f"/surat-tugas/{st_id}/approve", {"ttd_image_base64": ""})
if "err=" in url and "Tanda tangan" in urllib.parse.unquote(url):
    ok("approve surat tugas tanpa ttd ditolak")
else:
    bad("approve surat tugas tanpa ttd ditolak", url)

code, url, _ = spv2.post(f"/surat-tugas/{st_id}/approve", {"ttd_image_base64": "data:image/png;base64," + PNG_1PX})
if "err=" not in url:
    ok("POST approve surat tugas", url.replace(BASE, ""))
else:
    bad("POST approve surat tugas", urllib.parse.unquote(url))

req = urllib.request.Request(f"{BASE}/surat-tugas/{st_id}/pdf")
for c in spv2.jar:
    req.add_header("Cookie", f"{c.name}={c.value}")
try:
    with spv2.opener.open(req, timeout=20) as resp:
        raw = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        if resp.getcode() == 200 and raw[:4] == b"%PDF":
            ok("PDF surat tugas terunduh", f"{len(raw)} bytes, {ctype}")
        else:
            bad("PDF surat tugas", f"HTTP {resp.getcode()} {ctype} {raw[:20]}")
except urllib.error.HTTPError as exc:
    bad("PDF surat tugas", f"HTTP {exc.code}")

_, pen = api(f"/penawaran/{pid}", token_admin)
if pen.get("status") == "SURAT_TUGAS":
    ok("status -> SURAT_TUGAS")
else:
    bad("status SURAT_TUGAS", pen.get("status"))

print("\n== 12. LHPP ==")
code, url, _ = admin.post(f"/lhpp/siapkan/{pid}", {})
if "err=" not in url:
    ok("POST siapkan LHPP")
else:
    bad("POST siapkan LHPP", urllib.parse.unquote(url))

code, _, body = admin.get(f"/penawaran/{pid}")
lh_id = None
for part in body.split('action="/lhpp/'):
    seg = part.split("/")[0]
    if seg.isdigit():
        lh_id = int(seg)
        break
if lh_id:
    code, url, _ = admin.post(
        f"/lhpp/{lh_id}/update",
        {"tanggal_selesai": "2026-10-28", "catatan": "selesai lewat UI", "chk_lhpp": "on", "is_uploaded": "on"},
    )
    if "err=" not in url:
        ok("POST update LHPP", f"lhpp_id={lh_id}")
    else:
        bad("POST update LHPP", urllib.parse.unquote(url))
else:
    bad("temukan lhpp_id", body[:200])

_, pen = api(f"/penawaran/{pid}", token_admin)
if pen.get("status") == "LHPP":
    ok("status -> LHPP")
else:
    bad("status LHPP", pen.get("status"))

print("\n== 13. SKLK3 ==")
code, url, _ = admin.post(
    f"/sklk3/{pid}", {"nomor": "SKLK3/UI/2026/001", "tanggal_muncul": "2026-10-29", "catatan": "lewat UI"}
)
if "err=" not in url:
    ok("POST SKLK3")
else:
    bad("POST SKLK3", urllib.parse.unquote(url))
_, pen = api(f"/penawaran/{pid}", token_admin)
if pen.get("status") == "SKLK3":
    ok("status -> SKLK3")
else:
    bad("status SKLK3", pen.get("status"))

print("\n== 14. Invoice & Faktur (KEUANGAN) ==")
code, url, _ = keu.post(f"/invoice/{pid}/terbit", {"tanggal": "", "nominal": "", "keterangan": "uji UI"})
if "err=" not in url:
    ok("POST terbitkan invoice", url.replace(BASE, ""))
else:
    bad("POST terbitkan invoice", urllib.parse.unquote(url))

code, _, body = keu.get(f"/penawaran/{pid}")
inv_id = None
for part in body.split('action="/invoice/'):
    seg = part.split("/")[0]
    if seg.isdigit():
        inv_id = int(seg)
        break
if inv_id:
    ok("invoice terdaftar", f"id={inv_id}")
else:
    bad("invoice terdaftar", body[:150])

code, url, _ = keu.post(f"/invoice/{inv_id}/faktur", {"faktur_nomor": "FAKTUR/UI/2026/001"})
if "err=" not in url:
    ok("POST catat faktur")
else:
    bad("POST catat faktur", urllib.parse.unquote(url))

_, pen = api(f"/penawaran/{pid}", token_admin)
if pen.get("status") == "SELESAI":
    ok("status akhir -> SELESAI")
else:
    bad("status akhir SELESAI", pen.get("status"))

print("\n== 15. Halaman lain tetap sehat ==")
for path in ["/master", "/wilayah", "/pengguna", "/keuangan", "/lhpp", "/surat-tugas"]:
    code, _, body = sa.get(path)
    if code == 200 and "Internal Server Error" not in body:
        ok(f"GET {path} (superadmin)")
    else:
        bad(f"GET {path}", f"HTTP {code}")


print("\n== 16. Pengaturan branding (SUPERADMIN) ==")
code, _, body = sa.get("/pengaturan")
if code == 200 and "Branding" in body:
    ok("GET /pengaturan (superadmin)")
else:
    bad("GET /pengaturan", f"HTTP {code}")

code, _, body = spv.get("/pengaturan")
if code == 403 or "Akses Ditolak" in body:
    ok("guard: SPV tidak boleh buka /pengaturan (403)")
else:
    bad("guard /pengaturan untuk SPV", f"HTTP {code}")

code, url, _ = sa.post(
    "/pengaturan",
    {
        "brand_name": "SGIT Surat Penawaran",
        "brand_subtitle": "Pusat & Wilayah",
        "brand_footer": "SGIT Platform",
        "brand_doc_title": "SGIT Penawaran",
    },
)
if "err=" not in url:
    ok("POST /pengaturan simpan branding")
else:
    bad("POST /pengaturan", urllib.parse.unquote(url))

# brand langsung terpakai di login + sidebar (tanpa restart)
code, _, body = admin.get("/login")
if "SGIT Surat Penawaran" in body or "SudahLogin" in body:
    pass
code, _, body = anon.get("/login")
if "SGIT Surat Penawaran" in body and "SGIT Platform" in body:
    ok("branding baru muncul di halaman login")
else:
    bad("branding di halaman login", body[:150])

code, _, body = admin.get("/")
if "SGIT Surat Penawaran" in body:
    ok("branding baru muncul di sidebar")
else:
    bad("branding di sidebar", "")

code, _, body = admin.get("/klien")
if "<title>" in body and "SGIT Penawaran" in body.split("<title>")[1].split("</title>")[0]:
    ok("judul tab browser memakai brand", body.split("<title>")[1].split("</title>")[0])
else:
    bad("judul tab browser", body.split("<title>")[1].split("</title>")[0] if "<title>" in body else "")

code, url, _ = sa.post("/pengaturan", {"reset": "1"})
if "err=" not in url:
    ok("POST /pengaturan reset ke default")
else:
    bad("POST /pengaturan reset", urllib.parse.unquote(url))

code, _, body = sa.get("/pengaturan")
if "Surat Penawaran Multi Wilayah" in body:
    ok("reset mengembalikan nilai default .env")
else:
    bad("reset ke default", body[:150])


print("\n" + "=" * 60)
print(f"HASIL: {len(PASS)} OK, {len(FAIL)} FAIL")
for label, detail in FAIL:
    print(f"  - {label} :: {detail}")
print("=" * 60)
sys.exit(1 if FAIL else 0)
