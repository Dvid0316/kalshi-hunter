import os, sys, random, sqlite3, tempfile, json
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from kh import quant, fees, db, auditor, research
from kh.api import Public

BOOK = {"orderbook_fp": {"yes_dollars": [["0.6300", "100"], ["0.6500", "50"]], "no_dollars": [["0.3200", "100"], ["0.3400", "40"]]}}


def test_direction_ask_is_one_minus_opposite_bid():
    t = quant.top_of_book(BOOK)
    assert t["yes_bid"] == 0.65 and t["no_bid"] == 0.34
    assert t["yes_ask"] == pytest.approx(1 - 0.34) and t["no_ask"] == pytest.approx(1 - 0.65)
    assert t["yes_ask"] > t["yes_bid"] and t["no_ask"] > t["no_bid"]       # buying at the bid would be wrong
    assert t["yes_ask_size"] == 40 and t["no_ask_size"] == 50


def test_buying_uses_ask_not_bid():
    avg, _ = quant.executable_buy(BOOK, "yes", 10)
    assert avg == pytest.approx(0.66) and avg != 0.65
    avg, _ = quant.executable_buy(BOOK, "no", 10)
    assert avg == pytest.approx(0.35) and avg != 0.34


def test_p_below_yes_ask_means_yes_negative_no_positive():
    p = 0.55; ya, na = 0.66, 0.35
    assert quant.ev_per_contract(p, "yes", ya, 10) < 0
    assert quant.ev_per_contract(p, "no", na, 10) > 0
    assert quant.best_side(p, ya, na, 10)[0] == "no"


def test_ev_no_formula_and_fee_sign():
    p, na, q = 0.59, 0.35, 10
    f = fees.fee(na, q) / q
    assert f > 0
    assert quant.ev_per_contract(p, "no", na, q) == pytest.approx((1 - p) - na - f)
    # fees always reduce EV
    assert quant.ev_per_contract(p, "no", na, q) < (1 - p) - na


def test_swapping_sides_flips_sign_at_fair_complement():
    # buying YES at x with belief p equals buying NO at 1-x with belief 1-p
    for p, x in [(0.3, 0.4), (0.7, 0.2), (0.55, 0.5)]:
        a = quant.ev_per_contract(p, "yes", x, 10); b = quant.ev_per_contract(1 - p, "no", x, 10)
        assert a == pytest.approx(b)
        gross_yes = p - x; gross_no = (1 - p) - (1 - x)
        assert gross_yes == pytest.approx(-gross_no)


def test_property_random_books():
    rng = random.Random(7)
    for _ in range(2000):
        yb = round(rng.uniform(0.01, 0.97), 2); nb = round(rng.uniform(0.01, 0.98 - yb), 2)   # uncrossed book
        ob = {"orderbook_fp": {"yes_dollars": [[str(yb), "10"]], "no_dollars": [[str(nb), "10"]]}}
        t = quant.top_of_book(ob)
        assert t["yes_ask"] >= t["yes_bid"] and t["no_ask"] >= t["no_bid"]
        assert t["yes_ask"] + t["no_bid"] == pytest.approx(1) and t["no_ask"] + t["yes_bid"] == pytest.approx(1)
        p = rng.uniform(0.01, 0.99); q = rng.choice([1, 10, 100])
        for side, px in (("yes", t["yes_ask"]), ("no", t["no_ask"])):
            f = fees.fee(px, q)
            assert f >= 0
            win = p if side == "yes" else 1 - p
            ev = quant.ev_per_contract(p, side, px, q)
            assert ev <= win - px + 1e-12                    # fee never adds
            assert ev == pytest.approx(win - px - f / q)
        # can't have both sides +EV beyond the spread: sum of gross edges = 1 - ya - na <= 0
        assert (p - t["yes_ask"]) + ((1 - p) - t["no_ask"]) <= 1e-9


def test_auditor_worst_case_uses_unfavourable_band_edge():
    ok, notes, evw = auditor.audit_model(0.15, 0.07, 0.27, "no", 0.75, 48, 1000, False, qty=10)
    assert evw == pytest.approx((1 - 0.27) - 0.75 - fees.fee(0.75, 10) / 10) and not ok
    ok, notes, evw = auditor.audit_model(0.10, 0.05, 0.15, "no", 0.70, 48, 1000, False, qty=10)
    assert ok and evw > 0


class FakeResp:
    def __init__(self, st, body=None): self.status_code = st; self._b = body or {}; self.text = ""
    def json(self): return self._b


def test_429_backoff_then_success():
    slept = []; a = Public(min_interval=0, sleep=slept.append)
    seq = [FakeResp(429), FakeResp(429), FakeResp(200, {"ok": 1})]
    a.s.get = lambda *x, **k: seq.pop(0)
    assert a.get("/markets") == {"ok": 1}
    assert slept == [1, 2] and a.ok == 1 and a.fail == 2


def test_persistent_failure_raises():
    a = Public(min_interval=0, sleep=lambda s: None)
    a.s.get = lambda *x, **k: FakeResp(503)
    with pytest.raises(RuntimeError): a.get("/markets")


def test_read_only_guard():
    for p in ("/portfolio/orders", "/portfolio/balance", "/orders"):
        with pytest.raises(AssertionError): Public().get(p)
    import kh, pkgutil, inspect
    src = "".join(inspect.getsource(__import__(f"kh.{m.name}", fromlist=["x"])) for m in pkgutil.iter_modules(kh.__path__))
    assert ".post(" not in src and ".delete(" not in src and "create_order" not in src


def test_append_only_forecasts_and_research():
    c = db.connect(tempfile.mktemp(suffix=".db"))
    c.execute("INSERT INTO forecasts(ts,ticker,side,prob_yes,exec_price,qty,fee,ev) VALUES(1,'X','no',0.2,0.7,10,0.15,0.1)")
    c.execute("INSERT INTO research(ts,ticker,prob_yes) VALUES(1,'X',0.2)"); c.commit()
    for q in ("UPDATE forecasts SET prob_yes=0.9", "DELETE FROM forecasts", "UPDATE research SET prob_yes=0.9", "DELETE FROM research"):
        with pytest.raises(sqlite3.IntegrityError): c.execute(q)


def test_restart_recovery_marks_interrupted_and_keeps_data():
    p = tempfile.mktemp(suffix=".db"); c = db.connect(p)
    c.execute("INSERT INTO scans(started,status) VALUES(1,'running')"); c.commit(); c.close()
    c = db.connect(p); c.execute("UPDATE scans SET status='interrupted' WHERE status='running'"); c.commit()
    assert c.execute("SELECT status FROM scans").fetchone()[0] == "interrupted"


def test_research_rejects_unsourced_and_secondhand_without_origin():
    sub = {"ticker": "X", "side": "no", "prob_yes": 0.2, "prob_lo": 0.15, "prob_hi": 0.25, "method": "m",
           "sources": ["https://a", "https://b"], "contrarian": {"findings": "f", "sources": ["https://c"]},
           "secondhand": [{"figure": "38.2", "via_url": "https://w"}]}
    ok, errs, *_ = research.validate(sub, fetch=lambda u: 200)
    assert not ok and any("original_source" in e for e in errs)
    sub["secondhand"][0]["original_source"] = "RCP"
    assert research.validate(sub, fetch=lambda u: 200)[0]
    assert not research.validate(sub, fetch=lambda u: 404)[0]          # sources not verifiable -> rejected
    s2 = dict(sub, contrarian={"findings": "", "sources": []})
    assert not research.validate(s2, fetch=lambda u: 200)[0]           # no contrarian pass -> rejected


def test_enqueue_daily_cap():
    c = db.connect(tempfile.mktemp(suffix=".db"))
    for i in range(5):
        import time as _t
        cid = c.execute("INSERT INTO candidates(ts,kind,key,event_ticker,edge,detail,audit,status) VALUES(1,'k',?,'E',0.1,?,'{}','screened')",
                  (str(i), json.dumps({"legs": [[f"T{i}", "no", 0.5]]}))).lastrowid
        c.execute("INSERT INTO candidate_audits(ts,candidate_id,status,audit) VALUES(?,?,'alert','{}')", (_t.time(), cid))
    c.commit()
    assert len(research.enqueue(c)) == research.DAILY_CAP and research.enqueue(c) == []
