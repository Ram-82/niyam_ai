"""SQLAlchemy declarative base + Postgres enum handles.

Enums are created by the initial Alembic migration. Here we bind Python-side
handles with ``create_type=False`` so SQLAlchemy never tries to (re-)create
them at metadata.create_all time.
"""
from __future__ import annotations

from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _pg_enum(*labels: str, name: str) -> PgEnum:
    return PgEnum(*labels, name=name, create_type=False, native_enum=True)


UserRoleEnum = _pg_enum("admin", "staff", name="user_role")
GstSchemeEnum = _pg_enum("regular", "composition", name="gst_scheme")
InvoiceSourceEnum = _pg_enum("csv_import", "manual", "api", name="invoice_source")
InvoiceDirectionEnum = _pg_enum("purchase", "sale", name="invoice_direction")
InvoiceStatusEnum = _pg_enum(
    "active", "superseded", "void", name="invoice_status"
)
ReturnTypeEnum = _pg_enum("GSTR2B", "GSTR1", "GSTR3B", name="return_type")
FlagSeverityEnum = _pg_enum("error", "warning", name="flag_severity")
MatchBucketEnum = _pg_enum(
    "matched", "probable", "supplier_default", "missing_entry", name="match_bucket"
)
ReconRunStatusEnum = _pg_enum(
    "pending", "running", "completed", "failed", name="recon_run_status"
)
B2BNoteTypeEnum = _pg_enum("credit_note", "debit_note", name="b2b_note_type")
ImportKindEnum = _pg_enum(
    "purchase_csv", "purchase_xlsx", "sales_csv", "sales_xlsx", "gstr2b_json",
    name="import_kind",
)
ImportStatusEnum = _pg_enum(
    "queued", "running", "completed", "failed", name="import_status"
)
FilingStatusEnum = _pg_enum(
    "draft", "approved", "filed", name="filing_status"
)
