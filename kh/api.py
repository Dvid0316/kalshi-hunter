"""Unauthenticated public Kalshi market-data client. READ-ONLY: only GET requests, no keys, no order endpoints."""
import time, requests, re
BASE = "https://api.elections.kalshi.com/trade-api/v2"
ALLOWED_PREFIXES = ("/events", "/markets", "/series", "/exchange/status")


class Public:
    def __init__(self, db=None, min_interval=0.25, sleep=time.sleep):
        self.s = requests.Session(); self.s.headers["User-Agent"] = "kalshi-hunter-research/0.1"
        self.db = db; self.min_interval = min_interval; self.sleep = sleep; self._last = 0.0; self.calls = 0; self.ok = 0; self.fail = 0

    def get(self, path, params=None):
        if not re.fullmatch(r"/(?:events|markets|series)(?:/[A-Za-z0-9_.-]+)*|/exchange/status", path) or "portfolio" in path:
            raise AssertionError("read-only public endpoints only")
        for attempt in range(6):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0: self.sleep(wait)
            t0 = time.time(); self._last = t0
            try:
                r = self.s.get(BASE + path, params=params, timeout=20, allow_redirects=False); st = r.status_code
            except requests.RequestException:
                st = -1; r = None
            self.calls += 1
            if self.db is not None:
                self.db.execute("INSERT INTO api_log(ts,path,status,ms) VALUES(?,?,?,?)",
                                (t0, path, st, (time.time() - t0) * 1000))
            if st == 200:
                self.ok += 1; return r.json()
            self.fail += 1
            if st in (429, -1) or st >= 500:
                self.sleep(min(30, 2 ** attempt)); continue
            raise RuntimeError(f"GET {path} -> {st}: {r.text[:200] if r is not None else ''}")
        raise RuntimeError(f"GET {path} failed after retries")

    def paged(self, path, key, params, max_pages=200):
        params = dict(params); cur = None; seen = set()
        for _ in range(max_pages):
            if cur: params["cursor"] = cur
            d = self.get(path, params)
            for x in d.get(key) or []: yield x
            cur = d.get("cursor")
            if not cur: return
            if cur in seen: raise RuntimeError("Repeated pagination cursor")
            seen.add(cur)
        raise RuntimeError("Pagination incomplete: page cap reached")

    def orderbook(self, ticker, depth=10):
        return self.get(f"/markets/{ticker}/orderbook", {"depth": depth})

    def market(self, ticker):
        return self.get(f"/markets/{ticker}")["market"]
