"""Legal document versioning + firm-level acceptance recording.

Two independent things that must not be conflated:

* ``documents`` — the versioned document files that live in
  ``app/legal/documents/`` and are hashed at import time. This is what
  the gate compares against.
* ``LegalAcceptance`` — an append-only row proving a specific
  (firm, user, doc_type, doc_version, content_hash) tuple was recorded
  at a point in time. Never mutated. Superseded by a later acceptance
  row when the document hash changes.
"""
