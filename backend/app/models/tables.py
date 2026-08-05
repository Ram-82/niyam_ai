"""SQLAlchemy 2.x models mirroring migration 0001_initial.

Rules of the road:
* Every tenant table carries firm_id (denormalized) to keep RLS policies
  cheap. Read this file next to the migration — they should agree line for
  line on columns and constraints.
* Money is BIGINT paise everywhere. No floats.
* Foreign keys use ON DELETE semantics defined at the DB layer; SQLAlchemy
  side just declares the target.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    B2BNoteTypeEnum,
    Base,
    FlagSeverityEnum,
    GstSchemeEnum,
    ImportKindEnum,
    ImportStatusEnum,
    InvoiceDirectionEnum,
    InvoiceSourceEnum,
    InvoiceStatusEnum,
    MatchBucketEnum,
    ReconRunStatusEnum,
    ReturnTypeEnum,
    UserRoleEnum,
)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CAFirm(Base):
    __tablename__ = "ca_firm"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default="pilot")
    created_at: Mapped[datetime] = _created_at()


class AppUser(Base):
    __tablename__ = "app_user"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(UserRoleEnum, nullable=False)
    totp_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    totp_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = _created_at()


class UserInvite(Base):
    """Firm-scoped invite token created by an admin.

    ``token_hash`` stores the SHA-256 hex digest of the raw URL-safe token
    (32 bytes -> 43-char base64). The raw token is returned once at creation
    and never persisted, so a DB dump cannot be used to accept invites.
    """

    __tablename__ = "user_invite"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role: Mapped[str] = mapped_column(UserRoleEnum, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    invited_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = _created_at()


class Client(Base):
    __tablename__ = "client"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trade_name: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default="en")
    # Optional E.164 default for WhatsApp delivery (migration 0010). The
    # CA can override on a per-delivery basis; this is the "usual" number.
    whatsapp_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class ClientAssignment(Base):
    __tablename__ = "client_assignment"
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "client_id"),
    )


class GstinProfile(Base):
    __tablename__ = "gstin_profile"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client.id", ondelete="CASCADE"),
        nullable=False,
    )
    gstin: Mapped[str] = mapped_column(Text, nullable=False)
    state_code: Mapped[str] = mapped_column(Text, nullable=False)
    scheme: Mapped[str] = mapped_column(
        GstSchemeEnum, nullable=False, server_default="regular"
    )
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        UniqueConstraint("client_id", "gstin", name="gstin_profile_client_gstin_uniq"),
    )


class Invoice(Base):
    __tablename__ = "invoice"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gstin_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gstin_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(InvoiceSourceEnum, nullable=False)
    direction: Mapped[str] = mapped_column(InvoiceDirectionEnum, nullable=False)
    invoice_number: Mapped[str] = mapped_column(Text, nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    counterparty_gstin: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    taxable_value_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cgst_paise: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    sgst_paise: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    igst_paise: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hsn_sac: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        InvoiceStatusEnum, nullable=False, server_default="active"
    )
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        UniqueConstraint(
            "gstin_profile_id", "content_hash", name="invoice_content_hash_uniq"
        ),
    )


class GstnPull(Base):
    __tablename__ = "gstn_pull"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gstin_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gstin_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    return_type: Mapped[str] = mapped_column(ReturnTypeEnum, nullable=False)
    period: Mapped[str] = mapped_column(Text, nullable=False)  # 'YYYYMM'
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="json_import"
    )
    pulled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class B2BEntry(Base):
    __tablename__ = "b2b_entry"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gstn_pull_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gstn_pull.id", ondelete="CASCADE"),
        nullable=False,
    )
    supplier_gstin: Mapped[str] = mapped_column(Text, nullable=False)
    invoice_number: Mapped[str] = mapped_column(Text, nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    taxable_value_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_paise_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    itc_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    # NULL for regular invoices. Populated in P2 CDN parsing. Until then,
    # every ITC summary must be labeled "before credit/debit note adjustments."
    note_type: Mapped[Optional[str]] = mapped_column(
        B2BNoteTypeEnum, nullable=True
    )
    # IMS passthrough (migration 0006). Stored, not read — no engine uses
    # these yet. See README "IMS-era 2B semantics" TODO.
    ims_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ims_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class ValidationFlag(Base):
    __tablename__ = "validation_flag"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoice.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_code: Mapped[str] = mapped_column(Text, nullable=False)
    rule_pack_version: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(FlagSeverityEnum, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = _created_at()


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_run"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gstin_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gstin_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    period: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        ReconRunStatusEnum, nullable=False, server_default="pending"
    )
    rule_pack_version: Mapped[str] = mapped_column(Text, nullable=False)
    # Provenance: the exact 2B snapshot this run matched against.
    gstn_pull_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gstn_pull.id", ondelete="RESTRICT"),
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = _created_at()


class MatchResult(Base):
    __tablename__ = "match_result"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reconciliation_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoice.id", ondelete="SET NULL"),
        nullable=True,
    )
    b2b_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("b2b_entry.id", ondelete="SET NULL"),
        nullable=True,
    )
    bucket: Mapped[str] = mapped_column(MatchBucketEnum, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, server_default="1.0"
    )
    rule_pack_version: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = _created_at()


class ReadinessSnapshot(Base):
    """APPEND ONLY. GRANTs and triggers reject UPDATE/DELETE."""
    __tablename__ = "readiness_snapshot"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gstin_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gstin_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    return_type: Mapped[str] = mapped_column(ReturnTypeEnum, nullable=False)
    period: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    blockers: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    arithmetic: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    rule_pack_version: Mapped[str] = mapped_column(Text, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RulePack(Base):
    """Global. Not tenant-scoped. App role has SELECT only."""
    __tablename__ = "rule_pack"
    id: Mapped[uuid.UUID] = _uuid_pk()
    version: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class AuditLog(Base):
    """APPEND ONLY."""
    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    diff: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConsentLog(Base):
    """APPEND ONLY. Revoke by inserting a superseding row."""
    __tablename__ = "consent_log"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client.id", ondelete="CASCADE"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    granted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )


class ImportJob(Base):
    """Row per uploaded file. A queued worker updates ``status`` + counts."""
    __tablename__ = "import_job"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gstin_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gstin_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(ImportKindEnum, nullable=False)
    status: Mapped[str] = mapped_column(
        ImportStatusEnum, nullable=False, server_default="queued"
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    period: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    accepted_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    rejected_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    duplicate_rows: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    rejected_rows_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class GspSession(Base):
    """Encrypted vendor session per GSTIN profile.

    ``token_ciphertext`` is application-layer AEAD (see ``app/gsp/crypto``).
    Plaintext token NEVER lives in the DB, in logs, or in
    ``vendor_context`` — a CHECK constraint on the column asserts it stays
    a JSON object (opaque, non-secret).
    """

    __tablename__ = "gsp_session"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gstin_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gstin_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    vendor_context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    connected_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class GspCallLog(Base):
    """APPEND ONLY per-call meter (GSP charges per call)."""

    __tablename__ = "gsp_call_log"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gstin_profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gstin_profile.id", ondelete="SET NULL"),
        nullable=True,
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    period: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_kind: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class NarrationRun(Base):
    """APPEND ONLY record of every LLM narration generated (migration 0009).

    The prose here is the machine's original. A CA edit lands on a
    separate ``narration_edit`` row (P3) and never mutates this one.
    """

    __tablename__ = "narration_run"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    gstin_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gstin_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    return_type: Mapped[str] = mapped_column(ReturnTypeEnum, nullable=False)
    period: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    generated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DeliveryRequest(Base):
    """CA-approval gate for a WhatsApp send (migration 0010).

    Mutable until locked_at is set — that happens automatically on the
    first send attempt so the CA cannot revise the approval retroactively.
    """

    __tablename__ = "delivery_request"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client.id", ondelete="CASCADE"),
        nullable=False,
    )
    gstin_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gstin_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    narration_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("narration_run.id", ondelete="RESTRICT"),
        nullable=True,
    )
    match_result_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("match_result.id", ondelete="RESTRICT"),
        nullable=True,
    )
    whatsapp_number_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    template_name: Mapped[str] = mapped_column(Text, nullable=False)
    template_language: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )


class DeliveryAttempt(Base):
    """Append-only per-send attempt (migration 0010).

    The row is inserted with status='queued', updated to 'sent'/'failed'
    once the transport returns, and updated further by Meta webhook
    callbacks ('delivered'/'read'/'failed'). The immutable columns
    (firm_id, delivery_request_id, provider, attempted_at) are protected
    by a BEFORE UPDATE trigger; DELETE is rejected outright.
    """

    __tablename__ = "delivery_attempt"
    id: Mapped[uuid.UUID] = _uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ca_firm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    delivery_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("delivery_request.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_message_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_kind: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
