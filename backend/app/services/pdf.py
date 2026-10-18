from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.core.config import settings


def _wrap(text: str, width: int = 95) -> list[str]:
    words = (text or "").split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _fmt(d: date | None) -> str:
    if not d:
        return "-"
    bulan = [
        "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember",
    ]
    return f"{d.day} {bulan[d.month - 1]} {d.year}"


def render_surat_tugas(
    *,
    nomor: str,
    wilayah_nama: str,
    wilayah_alamat: str,
    pic_nama: str,
    pic_jabatan: str,
    perihal: str,
    tujuan: str,
    tanggal_tugas: date,
    penanggung_jawab: str,
    kota_terbit: str,
    ttd_path: str | None,
    output_path: str,
) -> str:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out), pagesize=A4)
    width, height = A4
    y = height - 30 * mm

    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, y, "SURAT TUGAS")
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2, y, f"Nomor: {nomor}")
    y -= 10 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, wilayah_nama.upper())
    y -= 5 * mm
    c.setFont("Helvetica", 9)
    for line in _wrap(wilayah_alamat, 90)[:2]:
        c.drawString(20 * mm, y, line)
        y -= 4.5 * mm
    c.line(20 * mm, y, width - 20 * mm, y)
    y -= 10 * mm

    c.setFont("Helvetica", 11)
    body = [
        f"Yang bertanda tangan di bawah ini memberikan tugas kepada {pic_nama}"
        + (f" ({pic_jabatan})" if pic_jabatan else "") + ":",
        "",
        f"Perihal: {perihal or '-'}",
        f"Tanggal pelaksanaan: {_fmt(tanggal_tugas)}",
        "",
        "Dengan uraian tugas sebagai berikut:",
    ]
    for item in body:
        for line in _wrap(item):
            c.drawString(20 * mm, y, line)
            y -= 6 * mm

    for line in _wrap(tujuan or "-"):
        c.drawString(26 * mm, y, f"\u2022 {line}")
        y -= 6 * mm

    y -= 4 * mm
    c.drawString(20 * mm, y, "Demikian surat tugas ini dibuat untuk dilaksanakan dengan penuh tanggung jawab.")
    y -= 4 * mm
    c.drawString(20 * mm, y, "Laporan hasil pelaksanaan wajib diserahkan kepada Admin Wilayah (LHPP).")

    y -= 14 * mm
    c.drawString(width - 90 * mm, y, f"{kota_terbit}, {_fmt(date.today())}")
    y -= 6 * mm
    c.drawString(width - 90 * mm, y, "Pimpinan / SPV Wilayah")
    y -= 22 * mm
    if ttd_path and Path(ttd_path).exists():
        try:
            c.drawImage(ttd_path, width - 88 * mm, y - 2 * mm, width=42 * mm, height=20 * mm,
                        mask="auto", preserveAspectRatio=True)
        except Exception:
            pass
    c.setFont("Helvetica-Bold", 11)
    c.drawString(width - 90 * mm, y - 4 * mm, penanggung_jawab or "...")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, 20 * mm, f"Dicetak dari Sistem Surat Penawaran - {settings.APP_NAME}")

    c.showPage()
    c.save()
    return str(out)
