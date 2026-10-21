import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from kh import fees, quant, db, perf


def test_fee_matches_published_table():
    # Kalshi fee schedule table: 100 contracts @ $0.50 -> $1.75; @ $0.10 -> $0.63; @ $0.01 -> $0.07
    assert fees.fee(0.50, 100) == 1.75
    assert fees.fee(0.10, 100) == 0.63
    assert fees.fee(0.01, 100) == 0.07
    # single contract rounds up to the cent: 0.07*.5*.5=0.0175 -> 0.02 (table: $0.02)
    assert fees.fee(0.50, 1) == 0.02
    assert fees.fee(0.05, 1) == 0.01


def test_fee_edges_and_multiplier():
    assert fees.fee(0.0, 10) == 0 and fees.fee(1.0, 10) == 0
    assert fees.fee(0.5, 100, multiplier=0) == 0
    assert fees.fee(0.5, 100, maker=True) == 0.44  # 0.0175*100*.25=0.4375 -> 0.44


def test_orderbook_to_prices():
    ob = {"orderbook_fp": {"yes_dollars": [["0.02", "28"], ["0.04", "12"]], "no_dollars": [["0.58", "100"], ["0.66", "90"]]}}
    t = quant.top_of_book(ob)
    assert t["yes_bid"] == 0.04 and t["no_bid"] == 0.66
    assert t["yes_ask"] == 0.34 and t["yes_ask_size"] == 90
    assert t["no_ask"] == 0.96 and t["no_ask_size"] == 12
    avg, got = quant.executable_buy(ob, "yes", 100)   # 90 @ .34 + 10 @ .42
    assert got == 100 and abs(avg - (90 * .34 + 10 * .42) / 100) < 1e-9
    avg, got = quant.executable_buy(ob, "no", 1000)
    assert got == 40


def test_ev():
    ev = quant.ev_per_contract(0.6, "yes", 0.50, 100)
    assert abs(ev - (0.6 - 0.5 - 0.0175)) < 1e-9
    ev = quant.ev_per_contract(0.6, "no", 0.45, 100)
    assert abs(ev - (0.4 - 0.45 - fees.fee(0.45, 100) / 100)) < 1e-9
    s = quant.best_side(0.2, 0.5, 0.5)
    assert s[0] == "no"


def test_mutex_arbs():
    ms = [{"ticker": "A", "yes_ask": 0.30, "no_ask": 0.60}, {"ticker": "B", "yes_ask": 0.30, "no_ask": 0.60},
          {"ticker": "C", "yes_ask": 0.30, "no_ask": 0.60}]
    r = {x["kind"]: x for x in quant.mutex_arbs(ms)}
    assert r["mutex_all_yes"]["needs_exhaustive"] is True
    assert abs(r["mutex_all_yes"]["edge"] - (1 - 0.9 - 3 * 0.02)) < 1e-9
    assert abs(r["mutex_all_no"]["edge"] - (2 - 1.8 - 3 * 0.02)) < 1e-9
    fair = [{"ticker": "A", "yes_ask": 0.51, "no_ask": 0.51}, {"ticker": "B", "yes_ask": 0.51, "no_ask": 0.51}]
    assert quant.mutex_arbs(fair) == []


def test_ladder():
    good = [{"ticker": "T3", "strike": 3, "strike_type": "greater", "yes_ask": 0.6, "no_ask": 0.42},
            {"ticker": "T4", "strike": 4, "strike_type": "greater", "yes_ask": 0.4, "no_ask": 0.62}]
    assert quant.ladder_violations(good) == []
    bad = [{"ticker": "T3", "strike": 3, "strike_type": "greater", "yes_ask": 0.30, "no_ask": 0.72},
           {"ticker": "T4", "strike": 4, "strike_type": "greater", "yes_ask": 0.62, "no_ask": 0.40}]
    v = quant.ladder_violations(bad)
    assert len(v) == 1 and v[0]["legs"][0] == ("T3", "yes", 0.30) and v[0]["legs"][1] == ("T4", "no", 0.40)
    assert abs(v[0]["edge"] - (1 - 0.70 - 0.02 - 0.02)) < 1e-9


def test_db_persistence_and_perf():
    p = tempfile.mktemp(suffix=".db")
    c = db.connect(p)
    db.upsert_candidate(c, "k", "key", "EV", 0.1, {"a": 1}, {}, "screened")
    db.upsert_candidate(c, "k", "key", "EV", 0.2, {"a": 2}, {}, "alert")
    c.execute("""INSERT INTO forecasts(ts,ticker,side,prob_yes,prob_lo,prob_hi,est_price,exec_price,exec_ts,qty,fee,ev,
                 resolved,outcome,pnl) VALUES(1,'X','yes',0.8,0.7,0.9,0.5,0.5,1,10,0.18,0.28,1,1,4.82)""")
    c.commit(); c.close()
    c = db.connect(p)  # reopen = survives restart
    r = c.execute("SELECT * FROM candidates ORDER BY id").fetchall()   # append-only: changed edge -> new row, old kept
    assert len(r) == 2 and r[0]["status"] == "screened" and r[-1]["status"] == "alert" and json.loads(r[-1]["detail"])["a"] == 2
    s = perf.stats(c)
    assert s["resolved"] == 0 and s["forecasts_total"] == 1
    c.execute("INSERT INTO resolutions(ts,forecast_id,outcome,pnl) VALUES(2,1,1,4.82)"); c.commit()
    s = perf.stats(c)
    assert s["resolved"] == 1 and abs(s["brier"] - 0.04) < 1e-9 and abs(s["brier_market"] - 0.25) < 1e-9 and "too small" in s["note"]


def test_api_refuses_non_public_paths():
    from kh.api import Public
    import pytest
    with pytest.raises(AssertionError):
        Public().get("/portfolio/orders")
