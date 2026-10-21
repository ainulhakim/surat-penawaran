#!/usr/bin/env python3
"""Verifikasi brief poin 11/28: order lintas wilayah tampil, harga disembunyikan,
list klien tetap tampil tapi tidak bisa dipilih bila terkunci wilayah lain."""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar

BASE = "http://127.0.0.1:8003"
FAIL = []


def cek(nama, kondisi, info=""):
    print(("  OK   " if kondisi else "  GAGAL") + f" | {nama}" + (f" — {info}" if info else ""))
    if not kondisi:
        FAIL.append(nama)


class Ui:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar(http.cookiejar.DefaultCookiePolicy(secure_protocols=("http", "https")))
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def get(self, path):
        with self.op.open(BASE + path, timeout=30) as r:
            return r.status, r.geturl(), r.read().decode()

    def post(self, path, data):
        req = urllib.request.Request(BASE + path, data=urllib.parse.urlencode(data).encode())
        with self.op.open(req, timeout=30) as r:
            return r.status, r.geturl(), r.read().decode()

    def login(self, email, pw):
        return self.post("/login", {"email": email, "password": pw, "next": "/"})


def api_login(email, pw):
    req = urllib.request.Request(
        BASE + "/api/v1/auth/login",
        data=json.dumps({"email": email, "password": pw}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]


def api_get(path, token):
    req = urllib.request.Request(BASE + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


KLIEN_JTG = "PT Maju Bangun Sejahtera"
NOMOR_JTG = "001/SP/JTG/X/2026"
PERIHAL_JTG = "Penawaran Riksa Uji 2026"
HARGA_JTG = "Rp 15.000.000"

print("== 1. ADMIN JTG: order sendiri tampil lengkap ==")
jtg = Ui()
jtg.login("admin.jtg@suratpenawaran.id", "AdminJtg2026!")
_, _, html = jtg.get("/penawaran")
cek("nomor surat sendiri tampil", NOMOR_JTG in html)
cek("perihal sendiri tampil", PERIHAL_JTG in html)
cek("harga sendiri tampil", HARGA_JTG in html)

print("== 2. ADMIN JBR (/penawaran): order JTG tetap tampil, rahasia disembunyikan ==")
jbr = Ui()
jbr.login("admin.jbr@suratpenawaran.id", "AdminJbr2026!")
_, _, html_list = jbr.get("/penawaran")
cek("nama perusahaan JTG tetap tampil", KLIEN_JTG in html_list)
cek("nomor surat JTG disembunyikan", NOMOR_JTG not in html_list)
cek("perihal JTG disembunyikan", PERIHAL_JTG not in html_list)
cek("harga JTG disembunyikan", HARGA_JTG not in html_list and "15.000.000" not in html_list)
cek("penanda harga disembunyikan", "disembunyikan" in html_list)
cek("badge wilayah lain", "wilayah lain" in html_list)

print("== 3. DASHBOARD JBR ==")
_, _, html_dash = jbr.get("/")
cek("order JTG tampil di dashboard", KLIEN_JTG in html_dash)
cek("harga JTG disembunyikan di dashboard", "15.000.000" not in html_dash)
cek("perihal JTG disembunyikan di dashboard", PERIHAL_JTG not in html_dash)
cek("badge 'dari wilayah lain'", "dari wilayah lain" in html_dash)

print("== 4. DAFTAR KLIEN JBR: semua klien tampil, yang terkunci nonaktif ==")
_, _, html_klien = jbr.get("/klien")
cek("klien wilayah JTG tetap tampil", KLIEN_JTG in html_klien)
cek("status nonaktif", "TIDAK AKTIF" in html_klien)
cek("tidak ada link buat penawaran utk klien terkunci",
    html_klien.count(f'/penawaran/baru?client_id=1"') == 0)

print("== 5. FORM PENAWARAN BARU JBR: opsi klien terkunci disabled ==")
_, _, html_form = jbr.get("/penawaran/baru")
opsi1 = re.search(r"<option value=\"1\"[^>]*>", html_form)
cek("opsi klien terkunci ditemukan", bool(opsi1), opsi1.group(0) if opsi1 else "")
cek("opsi klien terkunci disabled", bool(opsi1) and "disabled" in opsi1.group(0))
cek("keterangan wilayah pemegang lock", "Wilayah Jawa Tengah" in html_form)
cek("ada optgroup wilayah sendiri", "Wilayah Anda" in html_form)

print("== 6. API penawaran: baris wilayah lain tanpa isi rahasia ==")
t_jbr = api_login("admin.jbr@suratpenawaran.id", "AdminJbr2026!")
baris = api_get("/api/v1/penawaran", t_jbr)
lain = [r for r in baris if r.get("wilayah_id") == 1]
cek("API mengembalikan order wilayah lain", bool(lain), f"{len(lain)} baris")
cek("akses_penuh=False", all(r["akses_penuh"] is False for r in lain))
cek("nomor_surat dikosongkan", all(r["nomor_surat"] == "" for r in lain))
cek("harga_total None", all(r["harga_total"] is None for r in lain))
cek("nama perusahaan tetap ada", all(r["nama_perusahaan"] for r in lain))
t_jtg = api_login("admin.jtg@suratpenawaran.id", "AdminJtg2026!")
sendiri = [r for r in api_get("/api/v1/penawaran", t_jtg) if r["wilayah_id"] == 1]
cek("JTG tetap akses penuh atas ordernya", all(r["akses_penuh"] for r in sendiri) and bool(sendiri))

print("== 7. API clients: can_quote & info lock ==")
klien_jbr = api_get("/api/v1/clients?size=200", t_jbr)
c1 = next((c for c in klien_jbr if c["id"] == 1), None)
cek("klien JTG tampil di API JBR", c1 is not None)
cek("can_quote=False utk klien terkunci", bool(c1) and c1["can_quote"] is False)
cek("lock_wilayah_nama terisi", bool(c1) and c1["lock_wilayah_nama"] == "Wilayah Jawa Tengah", str(c1 and c1.get("lock_wilayah_nama")))

print("== 8. Draft wilayah lain TIDAK bocor ==")
_, url, _ = jbr.post(
    "/klien/baru",
    {
        "nama_perusahaan": "PT Klien Jabar Uji",
        "email": "jabar.uji@example.com",
        "no_telpon": "0221234567",
        "pic": "Dedi",
        "no_pic": "081200000001",
        "alamat": "Jl. Asia Afrika 1",
        "kota": "Bandung",
        "provinsi": "Jawa Barat",
        "kodepos": "40111",
    },
)
cid = None
m = re.search(r"/klien/(\d+)/edit", url)
if m:
    cid = int(m.group(1))
else:
    m = re.search(r"ID%20(\d+)|ID (\d+)", urllib.parse.unquote(url))
    if m:
        cid = int(m.group(1) or m.group(2))
cek("klien JBR siap (baru/duplikat)", cid is not None, url.replace(BASE, ""))
_, url, _ = jbr.post(
    "/penawaran/baru",
    {
        "client_id": str(cid),
        "perihal": "Penawaran Rahasia Jabar",
        "catatan": "",
        "uraian": ["Jasa Uji"],
        "spesifikasi": [""],
        "qty": ["1"],
        "satuan": ["unit"],
        "harga": ["1000000"],
        "nego": [],
        "harga_nego": [""],
        "kategori_id": [""],
        "bidang_id": [""],
        "objek_id": [""],
    },
)
cek("draft penawaran JBR dibuat", "/penawaran/" in url and "err=" not in url, url.replace(BASE, ""))
_, _, html_jbr2 = jbr.get("/penawaran")
cek("JBR melihat draft sendiri lengkap", "Penawaran Rahasia Jabar" in html_jbr2 and "Rp 1.000.000" in html_jbr2)
_, _, html_jtg2 = jtg.get("/penawaran")
cek("JTG tidak melihat draft JBR", "PT Klien Jabar Uji" not in html_jtg2 and "Penawaran Rahasia Jabar" not in html_jtg2)
_, _, html_jtg_klien = jtg.get("/klien")
cek("JTG melihat klien JBR (data klien terpusat)", "PT Klien Jabar Uji" in html_jtg_klien)

print()
if FAIL:
    print(f"=== HASIL: {len(FAIL)} GAGAL ===")
    for f in FAIL:
        print(" -", f)
    sys.exit(1)
print("=== HASIL: SEMUA CEK LULUS ===")
