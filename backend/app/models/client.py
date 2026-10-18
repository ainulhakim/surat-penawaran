from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import LockReason


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        Index(
            "uq_client_identity",
            text("lower(nama_perusahaan)"),
            text("lower(email)"),
            text("lower(kota)"),
            "kodepos",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nama_perusahaan: Mapped[str] = mapped_column(String(200), index=True)
    no_telpon: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    pic: Mapped[str] = mapped_column(String(120), default="")
    no_pic: Mapped[str] = mapped_column(String(40), default="")
    alamat: Mapped[str] = mapped_column(Text, default="")
    kota: Mapped[str] = mapped_column(String(80), default="", index=True)
    provinsi: Mapped[str] = mapped_column(String(80), default="")
    kodepos: Mapped[str] = mapped_column(String(10), default="")
    wilayah_id: Mapped[int | None] = mapped_column(ForeignKey("wilayah.id"), nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ClientLock(Base):
    __tablename__ = "client_locks"
    __table_args__ = (
        Index(
            "uq_client_lock_active",
            "client_id",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    penawaran_id: Mapped[int] = mapped_column(ForeignKey("penawaran.id"), index=True)
    wilayah_id: Mapped[int] = mapped_column(ForeignKey("wilayah.id"), index=True)
    locked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[LockReason] = mapped_column(String(20), default=LockReason.NORMAL)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_note: Mapped[str] = mapped_column(String(200), default="")

    client: Mapped["Client"] = relationship()
