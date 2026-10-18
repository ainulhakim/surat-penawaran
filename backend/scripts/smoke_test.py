import json, urllib.request, urllib.error

BASE = "http://127.0.0.1:8003/api/v1"
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
results = []

def call(method, path, token=None, body=None, expect=200):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=30) as r:
            code, payload = r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            payload = {"raw": raw.decode(errors="replace")[:300]}
        code = e.code
    ok = (code == expect)
    results.append((ok, f"{method} {path} -> {code} (harap {expect})", payload if not ok else ""))
    return code, payload

def login(email, pw):
    c, p = call("POST", "/auth/login", body={"email": email, "password": pw})
    return p.get("access_token")

# 1. login pusat
tok = login("superadmin@suratpenawaran.id", "SuperAdmin2026!")
call("GET", "/auth/me", tok)

# 2. wilayah
call("POST", "/wilayah", tok, {"kode": "JTG", "nama": "Wilayah Jawa Tengah", "provinsi": "Jawa Tengah",
                              "kota": "Semarang", "kodepos": "50134", "alamat": "Jl. Pemuda 1", "telepon": "024111"}, 201)
call("POST", "/wilayah", tok, {"kode": "JBR", "nama": "Wilayah Jawa Barat", "provinsi": "Jawa Barat",
                              "kota": "Bandung", "kodepos": "40111", "alamat": "Jl. Asia Afrika 1"}, 201)
call("GET", "/wilayah", tok)

# 3. users
call("POST", "/users", tok, {"nama": "Admin Jateng", "email": "admin.jtg@suratpenawaran.id",
                             "password": "AdminJtg2026!", "role": "ADMIN_WILAYAH", "wilayah_id": 1}, 201)
call("POST", "/users", tok, {"nama": "SPV Jateng", "email": "spv.jtg@suratpenawaran.id",
                             "password": "SpvJtg2026!", "role": "SPV", "wilayah_id": 1}, 201)
call("POST", "/users", tok, {"nama": "Admin Jabar", "email": "admin.jbr@suratpenawaran.id",
                             "password": "AdminJbr2026!", "role": "ADMIN_WILAYAH", "wilayah_id": 2}, 201)
call("POST", "/users", tok, {"nama": "Keuangan Jateng", "email": "keu.jtg@suratpenawaran.id",
                             "password": "KeuJtg2026!", "role": "KEUANGAN", "wilayah_id": 1}, 201)

admin_jtg = login("admin.jtg@suratpenawaran.id", "AdminJtg2026!")
spv_jtg = login("spv.jtg@suratpenawaran.id", "SpvJtg2026!")
admin_jbr = login("admin.jbr@suratpenawaran.id", "AdminJbr2026!")
keu_jtg = login("keu.jtg@suratpenawaran.id", "KeuJtg2026!")

# 4. master kategori/bidang/objek
call("POST", "/master/kategori", tok, {"kode": "K3B", "nama": "K3 Konstruksi"}, 201)
call("POST", "/master/bidang", tok, {"kategori_id": 2, "kode": "Riksa", "nama": "Riksa Uji"}, 201)
call("POST", "/master/objek", tok, {"bidang_id": 2, "kode": "RK-01", "nama": "Riksa Uji Pesawat Angkat", "satuan": "unit"}, 201)

# 5. client
c, client = call("POST", "/clients", admin_jtg, {"nama_perusahaan": "PT Maju Bangun Sejahtera", "no_telpon": "0247654321",
    "email": "proc@majubangun.co.id", "pic": "Budi Santoso", "no_pic": "08123456789",
    "alamat": "Kawasan Industri Candi Blok C", "kota": "Semarang", "provinsi": "Jawa Tengah", "kodepos": "50134"}, 201)
client_id = client.get("id")
call("POST", "/clients", admin_jtg, {"nama_perusahaan": "PT Maju Bangun Sejahtera", "email": "proc@majubangun.co.id",
    "kota": "Semarang", "kodepos": "50134"}, 409)  # duplikat
call("GET", "/clients/publik", admin_jbr)

# 6. penawaran
c, pen = call("POST", "/penawaran", admin_jtg, {"client_id": client_id, "perihal": "Penawaran Riksa Uji 2026",
    "is_nego": False, "items": [
        {"kategori_id": 2, "bidang_id": 2, "objek_id": 2, "uraian": "Riksa uji overhead crane", "qty": 3,
         "satuan": "unit", "harga_satuan": 4500000},
        {"uraian": "Mobilisasi & dokumen", "qty": 1, "satuan": "paket", "harga_satuan": 1500000}]}, 201)
pen_id = pen.get("id")
call("POST", f"/penawaran/{pen_id}/submit", admin_jtg)

# rahasia: wilayah lain tidak boleh lihat detail
call("GET", f"/penawaran/{pen_id}", admin_jbr, expect=403)
call("GET", "/penawaran/publik", admin_jbr)

# 7. approval SPV tanpa ttd -> gagal
call("POST", f"/penawaran/{pen_id}/approval", spv_jtg, {"aksi": "APPROVE"}, 400)
call("POST", f"/penawaran/{pen_id}/approval", spv_jtg, {"aksi": "APPROVE", "ttd_image_base64": "data:image/png;base64," + PNG})
c, pen2 = call("GET", f"/penawaran/{pen_id}", admin_jtg)
print("  status:", pen2.get("status"), "| valid_until:", pen2.get("valid_until"), "| total:", pen2.get("harga_total"))

# 8. lock client -> wilayah lain tidak bisa buat penawaran
c, lockinfo = call("GET", f"/clients/{client_id}", admin_jbr)
print("  lock:", lockinfo.get("lock_status"), lockinfo.get("lock_until"))
call("POST", "/penawaran", admin_jbr, {"client_id": client_id, "perihal": "Coba serobot",
    "items": [{"uraian": "x", "qty": 1, "harga_satuan": 1000}]}, 409)

# 9. deal
call("POST", f"/penawaran/{pen_id}/deal", admin_jtg, {"tgl_po": "2026-10-25", "no_spk": "SPK/MBS/X/2026/077",
                                                      "nilai_po": 15000000})

# 10. PIC & booking
c, pic = call("POST", "/pic", admin_jtg, {"nama": "Rizky Pratama", "no_hp": "081298765432",
                                          "email": "rizky@suratpenawaran.id", "keahlian": "Ahli K3 Umum",
                                          "wilayah_id": 1}, 201)
pic_id = pic.get("id")
c, booking = call("POST", "/booking", admin_jtg, {"penawaran_id": pen_id, "pic_id": pic_id,
                                                  "tanggal_tugas": "2026-11-02", "catatan": "Survey pagi"}, 201)
bid = booking.get("id")
call("GET", "/pic/agenda", admin_jtg)
call("POST", f"/booking/{bid}/respond", admin_jtg, {"aksi": "APPROVE"})

# 11. surat tugas
c, st = call("POST", f"/surat-tugas/dari-booking/{bid}", admin_jtg)
st_id = st.get("id")
call("POST", f"/surat-tugas/{st_id}/approve", spv_jtg, {"ttd_image_base64": "data:image/png;base64," + PNG})

# 12. LHPP
c, lhpp = call("POST", f"/lhpp/{pen_id}", admin_jtg)
call("PATCH", f"/lhpp/{lhpp['lhpp_id']}", admin_jtg, {"tanggal_selesai": "2026-11-02"})
call("PATCH", f"/lhpp/{lhpp['lhpp_id']}", admin_jtg, {"is_uploaded": True,
    "checklist": {"lhpp_external": True, "sklk3": False}, "bukti_screenshot_base64": "data:image/png;base64," + PNG})

# 13. SKLK3 + invoice
call("POST", f"/sklk3/{pen_id}", admin_jtg, {"nomor": "SKLK3/2026/1188", "tanggal_muncul": "2026-11-10"})
c, inv = call("POST", f"/invoice/{pen_id}", admin_jtg, {"keterangan": "Invoice termin 1"})
call("POST", f"/invoice/{inv['invoice_id']}/faktur", keu_jtg, {"faktur_nomor": "FK/2026/0912"})

# 14. dashboard + maintenance
c, summ = call("GET", "/dashboard/summary", tok)
print("  summary pusat:", json.dumps(summ, indent=None))
c, summ2 = call("GET", "/dashboard/summary", admin_jtg)
call("POST", "/internal/maintenance")

# verifikasi PDF surat tugas ada
import subprocess
print(subprocess.run(["docker","exec","sp-backend","sh","-c","ls -la /app/uploads/surat_tugas/ /app/uploads/ttd/"],
                     capture_output=True, text=True).stdout)

gagal = [r for r in results if not r[0]]
print(f"\n=== HASIL: {len(results) - len(gagal)}/{len(results)} langkah OK ===")
for ok, desc, extra in gagal:
    print("GAGAL:", desc, extra)