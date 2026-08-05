"""LLM vernacular-narration module.

Assembles the MSME 2-pager prose blocks from the frozen outputs of the
deterministic engines (readiness_snapshot, reconciliation_run,
validation_flag). The narrator is a translation/tone layer only —
:mod:`app.narrator.validator` rejects any output that contains a number
the caller did not pass in. See ``app/stubs/llm_narrator.py`` for the
original P1 contract this replaces.
"""
