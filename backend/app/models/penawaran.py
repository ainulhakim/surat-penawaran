from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import PenawaranStatus


class Penawaran(Base):
    __tablename__ = "penawaran"
    __table_args__ = (UniqueConstraint("nomor_surat", name="uq_penawaran_nomor"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nomor_surat: Mapped[str] = mapped_column(String(60), index=True, default="")
    nomor_urut: Mapped[int] = mapped_column(Integer, default=0)
    tahun: Mapped[int] = mapped_column(Integer, index=True, default=0)

    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    wilayah_id: Mapped[int] = mapped_column(ForeignKey("wilayah.id"), index=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    perihal: Mapped[str] = mapped_column(String(250), default="")
    catatan: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[PenawaranStatus] = mapped_column(String(30), default=PenawaranStatus.DRAFT, index=True)

    is_nego: Mapped[bool] = mapped_column(Boolean, default=False)
    harga_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ttd_spv_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revisi_catatan: Mapped[str] = mapped_column(Text, default="")

    tgl_po: Mapped[date | None] = mapped_column(Date, nullable=True)
    no_spk: Mapped[str] = mapped_column(String(80), default="")
    nilai_po: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    client: Mapped["Client"] = relationship()
    items: Mapped[list["PenawaranItem"]] = relationship(
        back_populates="penawaran", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["ApprovalLog"]] = relationship(back_populates="penawaran")


class PenawaranItem(Base):
    __tablename__ = "penawaran_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    penawaran_id: Mapped[int] = mapped_column(ForeignKey("penawaran.id"), index=True)
    kategori_id: Mapped[int | None] = mapped_column(ForeignKey("kategori.id"), nullable=True)
    bidang_id: Mapped[int | None] = mapped_column(ForeignKey("bidang.id"), nullable=True)
    objek_id: Mapped[int | None] = mapped_column(ForeignKey("objek.id"), nullable=True)

    uraian: Mapped[str] = mapped_column(String(300))
    spesifikasi: Mapped[str] = mapped_column(Text, default="")
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("1"))
    satuan: Mapped[str] = mapped_column(String(30), default="unit")
    harga_satuan: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    is_nego: Mapped[bool] = mapped_column(Boolean, default=False)
    harga_nego: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    penawaran: Mapped["Penawaran"] = relationship(back_populates="items")


class ApprovalLog(Base):
    __tablename__ = "approval_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    penawaran_id: Mapped[int] = mapped_column(ForeignKey("penawaran.id"), index=True)
    spv_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    aksi: Mapped[str] = mapped_column(String(20))
    catatan: Mapped[str] = mapped_column(Text, default="")
    ttd_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    penawaran: Mapped["Penawaran"] = relationship(back_populates="approvals")
