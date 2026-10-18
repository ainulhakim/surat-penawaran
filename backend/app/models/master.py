from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Kategori(Base):
    __tablename__ = "kategori"
    __table_args__ = (UniqueConstraint("kode", name="uq_kategori_kode"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kode: Mapped[str] = mapped_column(String(20), index=True)
    nama: Mapped[str] = mapped_column(String(150))
    deskripsi: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bidang: Mapped[list["Bidang"]] = relationship(back_populates="kategori")


class Bidang(Base):
    __tablename__ = "bidang"
    __table_args__ = (UniqueConstraint("kategori_id", "kode", name="uq_bidang_kategori_kode"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kategori_id: Mapped[int] = mapped_column(ForeignKey("kategori.id"), index=True)
    kode: Mapped[str] = mapped_column(String(20))
    nama: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    kategori: Mapped["Kategori"] = relationship(back_populates="bidang")
    objek: Mapped[list["Objek"]] = relationship(back_populates="bidang")


class Objek(Base):
    __tablename__ = "objek"
    __table_args__ = (UniqueConstraint("bidang_id", "kode", name="uq_objek_bidang_kode"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bidang_id: Mapped[int] = mapped_column(ForeignKey("bidang.id"), index=True)
    kode: Mapped[str] = mapped_column(String(20))
    nama: Mapped[str] = mapped_column(String(200))
    satuan: Mapped[str] = mapped_column(String(30), default="unit")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bidang: Mapped["Bidang"] = relationship(back_populates="objek")
