"""Offline Phase 1–2 CLI. Scanner/account operations intentionally unavailable."""
import argparse, json
from pathlib import Path
from kh import db, validation


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['health', 'validate'])
    args = p.parse_args(argv)
    with db.readonly(Path(__file__).parent/'data/kalshi.db') as c:
        if args.mode == 'validate':
            print(validation.generate(c)[0])
        else:
            scan = c.execute("SELECT MAX(finished) FROM scans WHERE status='ok'").fetchone()[0]
            print(json.dumps({'mode':'offline snapshot','scanner_running':False,'snapshot_last_scan':scan,'live_health':'unavailable'}))


if __name__ == '__main__':
    main()
