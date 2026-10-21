"""Tamper evidence: per-row SHA-256 content hash + a hash chain over all append-only rows (in seal order).
Triggers already block UPDATE/DELETE; this detects edits made by bypassing them (e.g. dropping triggers)."""
import hashlib, json, time
import os
TABLES = ["forecasts", "research", "research_runs", "resolutions", "research_audits", "forecast_market",
          "candidates_legacy", "candidates", "candidate_audits"]
CHECKPOINT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "research", "chain_checkpoints.log")
FIRST_SEAL_NOTE = "first seal 2026-10-21 11:31 AM CT; rows created before then (forecasts 1-3 at 9:58-9:59 AM CT) were unprotected by the chain until that seal"


def row_hash(row):
    return hashlib.sha256(json.dumps(dict(row), sort_keys=True, default=str).encode()).hexdigest()


def _ensure(c):
    c.execute("""CREATE TABLE IF NOT EXISTS hash_chain(seq INTEGER PRIMARY KEY, ts REAL, tbl TEXT, row_id INT,
                 content_hash TEXT, prev_hash TEXT, chain_hash TEXT, UNIQUE(tbl,row_id))""")
    for op in ("UPDATE", "DELETE"):
        c.execute(f"CREATE TRIGGER IF NOT EXISTS ro_hash_chain_{op.lower()} BEFORE {op} ON hash_chain "
                  "BEGIN SELECT RAISE(ABORT, 'hash_chain is append-only'); END")


def seal(c):
    _ensure(c); n = 0
    last = c.execute("SELECT chain_hash FROM hash_chain ORDER BY seq DESC LIMIT 1").fetchone()
    prev = last[0] if last else "GENESIS"
    for t in TABLES:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone(): continue
        for r in c.execute(f"SELECT * FROM {t} WHERE id NOT IN (SELECT row_id FROM hash_chain WHERE tbl=?) ORDER BY id", (t,)).fetchall():
            h = row_hash(r); ch = hashlib.sha256((prev + t + str(r["id"]) + h).encode()).hexdigest()
            c.execute("INSERT INTO hash_chain(ts,tbl,row_id,content_hash,prev_hash,chain_hash) VALUES(?,?,?,?,?,?)",
                      (time.time(), t, r["id"], h, prev, ch)); prev = ch; n += 1
    c.commit(); return n


def checkpoint(c, path=CHECKPOINT):
    """External anchor: append head hash + count + time to a file outside the DB (detects a full DB rewrite
    if the log, or a copy of it, is kept elsewhere)."""
    _ensure(c)
    h = c.execute("SELECT seq, chain_hash FROM hash_chain ORDER BY seq DESC LIMIT 1").fetchone()
    line = json.dumps({"ts": time.strftime("%FT%T%z"), "head_seq": h[0] if h else 0, "head_hash": h[1] if h else "GENESIS"})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f: f.write(line + "\n")
    return line


def verify_checkpoints(c, path=CHECKPOINT):
    """Every recorded head must still be present in the chain at that seq."""
    if not os.path.exists(path): return []
    bad = []
    for ln in open(path):
        try: d = json.loads(ln)
        except ValueError: continue          # non-checkpoint lines (e.g. sha256sum of pre-registration docs)
        if d.get("head_seq", 0) == 0: continue
        r = c.execute("SELECT chain_hash FROM hash_chain WHERE seq=?", (d["head_seq"],)).fetchone()
        if not r or r[0] != d["head_hash"]: bad.append(f"checkpoint {d['ts']} seq {d['head_seq']} mismatch")
    return bad


def verify(c):
    """Returns list of problems; empty = intact."""
    _ensure(c); probs = []; prev = "GENESIS"
    for s in c.execute("SELECT * FROM hash_chain ORDER BY seq").fetchall():
        r = c.execute(f"SELECT * FROM {s['tbl']} WHERE id=?", (s["row_id"],)).fetchone()
        if r is None: probs.append(f"{s['tbl']}#{s['row_id']} missing"); continue
        if row_hash(r) != s["content_hash"]: probs.append(f"{s['tbl']}#{s['row_id']} content changed")
        if s["prev_hash"] != prev or hashlib.sha256((prev + s["tbl"] + str(s["row_id"]) + s["content_hash"]).encode()).hexdigest() != s["chain_hash"]:
            probs.append(f"chain broken at seq {s['seq']}")
        prev = s["chain_hash"]
    return probs
