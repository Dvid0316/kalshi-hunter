"""CSV/JSON import for the personal ledger. Local files only: the importer never opens a network connection.

Canonical columns (header row required, extra columns ignored, order irrelevant)

  fills:        fill_id?, ticker, side, action, count, price, fee?, ts, order_id?, is_taker?, note?
  settlements:  settlement_id?, ticker, market_result, settled_ts, revenue, fee?, yes_count?, no_count?,
                yes_total_cost?, no_total_cost?
  cash:         txn_id?, ts, kind, amount, note?

Prices are dollars unless ``price_unit='cents'``. Naive timestamps are read in ``tz`` (default America/Chicago).
A bad row is *rejected and logged*, never guessed at, and never blocks the good rows.
This is NOT a parser for any specific Kalshi export: map your export to these columns first.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from decimal import Decimal
from pathlib import Path

from . import models as M
from .store import AccountStore, BatchResult

MAX_BYTES = 20_000_000
SIGNATURES = {
    'fills': {'ticker', 'side', 'action', 'count', 'price'},
    'settlements': {'ticker', 'market_result', 'revenue'},
    'cash': {'kind', 'amount'},
}


def _rows(path: Path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
        raise M.LedgerError(f'File too large ({len(raw):,} bytes; limit {MAX_BYTES:,})')
    sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode('utf-8-sig', errors='replace')
    if str(path).lower().endswith('.json'):
        data = json.loads(text, parse_float=Decimal)      # 0.40 in JSON is exact decimal text, not a binary float
        if isinstance(data, dict):
            data = data.get('records') or data.get('rows') or []
        if not isinstance(data, list):
            raise M.LedgerError('JSON must be a list of records')
        return [dict(r) for r in data if isinstance(r, dict)], sha
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise M.LedgerError('The file has no header row')
    return [{(k or '').strip().lower(): (v or '') for k, v in row.items()} for row in reader], sha


def detect_kind(rows) -> str:
    cols = set(rows[0]) if rows else set()
    for kind, need in SIGNATURES.items():
        if need <= cols:
            return kind
    raise M.LedgerError('Cannot tell what this file contains. Expected columns for fills, settlements or cash '
                        '(see docs/ACCOUNT_DATA_CONTRACT.md).')


def import_file(store: AccountStore, path, *, kind=None, price_unit='dollars', tz='America/Chicago',
                source=None) -> BatchResult:
    path = Path(path)
    rows, sha = _rows(path)
    kind = kind or detect_kind(rows)
    if kind not in SIGNATURES:
        raise M.LedgerError(f'unknown import kind {kind!r}')
    source = source or ('json' if path.suffix.lower() == '.json' else 'csv')
    good, bad = [], []
    for n, row in enumerate(rows, start=2):       # row 1 is the header
        try:
            if kind == 'fills':
                good.append(M.make_fill(row, price_unit=price_unit, tz=tz, source=source))
            elif kind == 'settlements':
                good.append(M.make_settlement(row, tz=tz, source=source))
            else:
                good.append(M.make_cash(row, tz=tz, source=source))
        except M.LedgerError as exc:
            bad.append((f'row {n}: ' + json.dumps(row, default=str)[:200], str(exc)))
    adder = {'fills': store.add_fills, 'settlements': store.add_settlements, 'cash': store.add_cash}[kind]
    return adder(good, source=source, label=path.name, sha256=sha, rejected=bad)
