"""Declaration of the currently-effective legal documents.

Adding a new version is a code change (edit this file + drop a new .md in
``documents/``) rather than a runtime toggle. That means every deploy is
answerable to "which document versions are effective right now" via git
history alone.

TODO-VERIFY-WITH-COUNSEL: the content of every document referenced here
mirrors the marketing copy shipped in ``frontend/app/v2/legal/dpa/page.tsx``
as of 2026-08-19. It has NOT been reviewed by counsel. Do not present
these documents to a real customer until legal review is complete and the
version bumped to reflect the reviewed text.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class LegalDocument:
    doc_type: str          # 'terms' | 'dpa'
    version: str           # semver-shaped; free-form.
    filename: str          # under app/legal/documents/
    effective_from: str    # ISO date; when this version became binding.
    notes: str             # short human note for git-log readers.


# Order matters only for display; the gate treats every entry as required.
CURRENT_DOCUMENTS: Sequence[LegalDocument] = (
    LegalDocument(
        doc_type="terms",
        version="1.0.0",
        filename="terms_v1_0_0.md",
        effective_from="2026-08-19",
        notes="Initial version. Placeholder text pending counsel review.",
    ),
    LegalDocument(
        doc_type="dpa",
        version="1.0.0",
        filename="dpa_v1_0_0.md",
        effective_from="2026-08-19",
        notes="Mirrors the v2 marketing DPA page. Pending counsel review.",
    ),
)


REQUIRED_DOC_TYPES = tuple(d.doc_type for d in CURRENT_DOCUMENTS)
