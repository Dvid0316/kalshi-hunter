import sys, os, json, random; sys.path.insert(0, os.path.dirname(__file__))
from kh import api as kapi, backtest, db
c = db.connect(); info = json.loads(c.execute("SELECT v FROM kv WHERE k='series'").fetchone()[0])
ser = {s: v.get("cat") for s, v in info.items() if v.get("cat") in backtest.CATS}
keys = sorted(ser); random.Random(1).shuffle(keys); keys = keys[: int(sys.argv[1]) if len(sys.argv) > 1 else 700]
a = kapi.Public(min_interval=0.25)
print("series", len(keys), "built", backtest.build_dataset(a, {k: ser[k] for k in keys}), "api calls", a.calls, flush=True)
