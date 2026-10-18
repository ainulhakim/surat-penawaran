from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import BookingStatus, InvoiceStatus, SuratTugasStatus


class Pic(Base):
    __tablename__ = "pic"
    __table_args__ = (UniqueConstraint("nama", "no_hp", name="uq_pic_identitas"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nama: Mapped[str] = mapped_column(String(120), index=True)
    no_hp: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    telegram_chat_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    wilayah_id: Mapped[int | None] = mapped_column(ForeignKey("wilayah.id"), nullable=True, index=True)
    keahlian: Mapped[str] = mapped_column(String(200), default="")
    is_aktif: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PicBooking(Base):
    __tablename__ = "pic_bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    penawaran_id: Mapped[int] = mapped_column(ForeignKey("penawaran.id"), index=True)
    pic_id: Mapped[int] = mapped_column(ForeignKey("pic.id"), index=True)
    wilayah_id: Mapped[int] = mapped_column(ForeignKey("wilayah.id"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    tanggal_tugas: Mapped[date] = mapped_column(Date, index=True)
    tanggal_usulan: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[BookingStatus] = mapped_column(String(20), default=BookingStatus.DIAJUKAN, index=True)
    catatan: Mapped[str] = mapped_column(Text, default="")
    alasan_reschedule: Mapped[str] = mapped_column(Text, default="")
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pic: Mapped["Pic"] = relationship()


class SuratTugas(Base):
    __tablename__ = "surat_tugas"
    __table_args__ = (UniqueConstraint("nomor", name="uq_surat_tugas_nomor"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nomor: Mapped[str] = mapped_column(String(60), index=True, default="")
    penawaran_id: Mapped[int] = mapped_column(ForeignKey("penawaran.id"), index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("pic_bookings.id"), index=True)
    pic_id: Mapped[int] = mapped_column(ForeignKey("pic.id"), index=True)
    wilayah_id: Mapped[int] = mapped_column(ForeignKey("wilayah.id"), index=True)

    perihal: Mapped[str] = mapped_column(String(250), default="")
    tujuan: Mapped[str] = mapped_column(Text, default="")
    tanggal_tugas: Mapped[date] = mapped_column(Date)
    status: Mapped[SuratTugasStatus] = mapped_column(String(20), default=SuratTugasStatus.MENUNGGU_SPV, index=True)
    ttd_spv_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    booking: Mapped["PicBooking"] = relationship()
    pic: Mapped["Pic"] = relationship()


class Lhpp(Base):
    __tablename__ = "lhpp"

    id: Mapped[int] = mapped_column(primary_key=True)
    penawaran_id: Mapped[int] = mapped_column(ForeignKey("penawaran.id"), unique=True, index=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("pic_bookings.id"), nullable=True)
    wilayah_id: Mapped[int] = mapped_column(ForeignKey("wilayah.id"), index=True)

    wajib: Mapped[bool] = mapped_column(Boolean, default=True)
    tanggal_selesai: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    is_uploaded: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bukti_screenshot_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    catatan: Mapped[str] = mapped_column(Text, default="")
    checklist: Mapped[str] = mapped_column(Text, default="{}")
    reminder_count: Mapped[int] = mapped_column(Numeric(3, 0), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Sklk3(Base):
    __tablename__ = "sklk3"

    id: Mapped[int] = mapped_column(primary_key=True)
    penawaran_id: Mapped[int] = mapped_column(ForeignKey("penawaran.id"), unique=True, index=True)
    wilayah_id: Mapped[int] = mapped_column(ForeignKey("wilayah.id"), index=True)
    nomor: Mapped[str] = mapped_column(String(80), default="")
    tanggal_muncul: Mapped[date | None] = mapped_column(Date, nullable=True)
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    catatan: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invoice(Base):
    __tablename__ = "invoice"

    id: Mapped[int] = mapped_column(primary_key=True)
    penawaran_id: Mapped[int] = mapped_column(ForeignKey("penawaran.id"), index=True)
    wilayah_id: Mapped[int] = mapped_column(ForeignKey("wilayah.id"), index=True)

    nomor: Mapped[str] = mapped_column(String(60), default="")
    tanggal: Mapped[date | None] = mapped_column(Date, nullable=True)
    tanggal_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    nominal: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    status: Mapped[InvoiceStatus] = mapped_column(String(20), default=InvoiceStatus.MENUNGGU, index=True)
    keterangan: Mapped[str] = mapped_column(Text, default="")

    notif_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    faktur_nomor: Mapped[str] = mapped_column(String(80), default="")
    faktur_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
