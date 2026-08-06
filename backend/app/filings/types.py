"""Filing generation types.

Keep this file tiny — it exists so generators and the service agree on
the shape of a filing payload without importing each other. Payloads
are plain dicts (JSON-round-trippable) because they land in a JSONB
column and go out over HTTP verbatim; wrapping them in dataclasses
would only add noise.
"""
from __future__ import annotations

from typing import Literal, TypedDict


ReturnType = Literal["GSTR1", "GSTR3B"]


class FilingPayload(TypedDict):
    """Common envelope over both GSTR-1 and GSTR-3B payloads."""

    gstin: str
    fp: str  # 'MMYYYY' — GSTN's period format, not our internal 'YYYYMM'
    return_type: ReturnType
    rule_pack_version: str
    generated_at: str
    body: dict


def to_gstn_period(yyyymm: str) -> str:
    """Convert internal 'YYYYMM' to GSTN's 'MMYYYY' upload format."""
    if len(yyyymm) != 6 or not yyyymm.isdigit():
        raise ValueError(f"invalid period {yyyymm!r}; expected YYYYMM")
    return yyyymm[4:6] + yyyymm[0:4]
