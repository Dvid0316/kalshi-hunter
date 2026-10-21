"""Kalshi Hunter service. Usage: python run.py loop | once | resolve"""
import sys, time, json, traceback, logging, os
from logging.handlers import RotatingFileHandler
LOG = logging.getLogger("kh")
sys.path.insert(0, __import__("os").path.dirname(__file__))
from kh import validation
from kh import db, api as kapi, scanner, auditor, perf, dashboard, research, integrity

INTERVAL = 300


def cycle(c, a):
    sid, ne, nm, nc = scanner.scan(a, c)
    info = scanner.series_info(c)
    # audit fresh structural candidates with meaningful screen edge
    for r in c.execute("""SELECT * FROM candidates k WHERE status='screened' AND edge>=? AND ts>?
                          AND NOT EXISTS (SELECT 1 FROM candidate_audits a WHERE a.candidate_id=k.id) ORDER BY edge DESC LIMIT 15""",
                       (auditor.ALERT_EDGE, time.time() - 900)).fetchall():
        ev = c.execute("SELECT series_ticker FROM events WHERE event_ticker=?", (r["event_ticker"],)).fetchone()
        try:
            auditor.audit_structural(a, c, r, scanner.fee_mult(info, ev[0] if ev else None))
        except Exception as e:
            db.log_error(c, "audit", e)
    perf.resolve(a, c)
    research.enqueue(c)
    try:
        from kh import prereg_flb; prereg_flb.run(a, c)
    except Exception as e:
        db.log_error(c, "flb_v1", e)
    integrity.seal(c); integrity.checkpoint(c)
    last_v = c.execute("SELECT v FROM kv WHERE k='validation_ts'").fetchone()
    if not last_v or time.time() - float(last_v[0]) > 3600:
        try:
            validation.generate(c)
        except Exception as e:
            db.log_error(c, "validation", e)
        c.execute("INSERT OR REPLACE INTO kv VALUES('validation_ts',?)", (str(time.time()),)); c.commit()
    # prune snapshots older than 7 days
    c.execute("DELETE FROM snapshots WHERE ts<?", (time.time() - 7 * 86400,)); c.commit()
    dashboard.render(c)
    LOG.info(f"scan {sid}: events={ne} markets={nm} candidates={nc} api_calls={a.calls}")


def main(mode):
    c = db.connect(); a = kapi.Public(db=c)
    if mode == "once": return cycle(c, a)
    if mode == "health":
        r = c.execute("SELECT MAX(finished) FROM scans WHERE status='ok'").fetchone()[0]
        age = time.time() - r if r else None
        h = {"last_ok_scan_age_s": round(age) if age else None, "healthy": bool(age and age < 3 * INTERVAL),
             "errors_last_hour": c.execute("SELECT COUNT(*) FROM errors WHERE ts>?", (time.time() - 3600,)).fetchone()[0]}
        print(json.dumps(h)); sys.exit(0 if h["healthy"] else 1)
    if mode == "validate": return print(validation.generate(c)[0])
    if mode == "claim": return print(json.dumps(research.claim(c)))
    if mode == "submit":  # run.py submit sub.json [queue_id] ; sub.json may contain "usage": {...}
        sub = json.load(open(sys.argv[2])); qid = int(sys.argv[3]) if len(sys.argv) > 3 else None
        return print(json.dumps(research.submit(a, c, sub, qid, sub.get("usage")), indent=1))
    if mode == "pending-alerts": return print(json.dumps(research.pending_alerts(a, c), indent=1))
    if mode == "mark-alerted": return research.mark_alerted(c, int(sys.argv[2]))
    if mode == "resolve": return print(perf.resolve(a, c))
    h = RotatingFileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "service.log"), maxBytes=5_000_000, backupCount=5)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s")); LOG.addHandler(h); LOG.setLevel(logging.INFO)
    c.execute("INSERT INTO service_starts(ts,pid) VALUES(?,?)", (time.time(), os.getpid()))
    c.execute("UPDATE scans SET status='interrupted' WHERE status='running'"); c.commit()  # restart recovery
    LOG.info("service start; resuming from DB")
    while True:
        t0 = time.time()
        try: cycle(c, a)
        except Exception as e:
            LOG.error(traceback.format_exc()); db.log_error(c, "cycle", traceback.format_exc())
            c.execute("UPDATE scans SET status='error' WHERE status='running'"); c.commit()
            try: dashboard.render(c)
            except Exception: pass
        time.sleep(max(10, INTERVAL - (time.time() - t0)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "loop")
