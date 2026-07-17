"""Rejected-row model + CSV materialization.

Rejects are stored as JSONB on ``import_job.rejected_rows_json``. The
download endpoint materializes them to CSV on demand.

Kept dead simple: a row_index (1-based, matches how a user sees the file
in Excel), the raw values as a dict, and a machine-readable ``reason``
code plus a human message.
"""
from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RejectedRow:
    row_index: int
    reason: str          # 'missing_required' | 'bad_amount' | 'bad_date' | 'schema' | ...
    message: str
    raw: dict[str, Any] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


def rejects_to_csv(rejects: list[dict[str, Any]]) -> bytes:
    """Materialize ``import_job.rejected_rows_json`` as UTF-8 CSV bytes.

    Column order: row_index, reason, message, then union of ``raw`` keys
    sorted alphabetically for a stable file across runs.
    """
    raw_keys: set[str] = set()
    for r in rejects:
        raw_keys.update((r.get("raw") or {}).keys())
    columns = ["row_index", "reason", "message", *sorted(raw_keys)]

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    for r in rejects:
        raw = r.get("raw") or {}
        w.writerow(
            [r.get("row_index"), r.get("reason"), r.get("message")]
            + [raw.get(k, "") for k in sorted(raw_keys)]
        )
    return buf.getvalue().encode("utf-8")
