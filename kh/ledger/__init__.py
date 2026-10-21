"""Personal trading ledger (Phase 4): data contracts, store, engine. OFFLINE ONLY.

This package records trades *the owner executed manually elsewhere*. It contains no order,
cancel or transfer capability and imports no network code (a test enforces this). Records are
stored in a dedicated ``account.db`` that is physically separate from the research evidence.

All money and quantity values are ``decimal.Decimal``. Floats are rejected at the boundary so
binary rounding artefacts cannot enter the books.
"""
