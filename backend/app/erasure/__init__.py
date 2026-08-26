"""Crypto-shredding erasure mechanism.

Ships the plumbing only, per ``docs/compliance/retention-and-erasure.md``:

* ``keys`` — allocate, wrap/unwrap, destroy a per-subject symmetric key.
* ``service`` — create + execute + refuse an erasure request.

There is deliberately no end-user API exposed. Enabling a real erasure
endpoint requires TODO-VERIFY-WITH-COUNSEL sign-off on the retention
policy that determines who can request erasure and when it can be
refused.
"""
