from enum import StrEnum


class UserRole(StrEnum):
    SUPERADMIN = "SUPERADMIN"
    ADMIN_WILAYAH = "ADMIN_WILAYAH"
    SPV = "SPV"
    PIC = "PIC"
    KEUANGAN = "KEUANGAN"


class PenawaranStatus(StrEnum):
    DRAFT = "DRAFT"
    MENUNGGU_SPV = "MENUNGGU_SPV"
    REVISI = "REVISI"
    APPROVED = "APPROVED"
    BATAL = "BATAL"
    DEAL = "DEAL"
    BOOKING_PIC = "BOOKING_PIC"
    SURAT_TUGAS = "SURAT_TUGAS"
    PELAKSANAAN = "PELAKSANAAN"
    LHPP = "LHPP"
    SKLK3 = "SKLK3"
    INVOICE = "INVOICE"
    SELESAI = "SELESAI"


class ApprovalAction(StrEnum):
    APPROVE = "APPROVE"
    REVISI = "REVISI"


class LockReason(StrEnum):
    NORMAL = "NORMAL"
    NEGO = "NEGO"


class BookingStatus(StrEnum):
    DIAJUKAN = "DIAJUKAN"
    DISETUJUI = "DISETUJUI"
    RESCHEDULE = "RESCHEDULE"
    DIBATALKAN = "DIBATALKAN"


class SuratTugasStatus(StrEnum):
    MENUNGGU_SPV = "MENUNGGU_SPV"
    DISETUJUI = "DISETUJUI"
    DIBATALKAN = "DIBATALKAN"


class InvoiceStatus(StrEnum):
    MENUNGGU = "MENUNGGU"
    TERBIT = "TERBIT"
    FAKTUR_DIBUAT = "FAKTUR_DIBUAT"


class NotifStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
