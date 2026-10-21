import os, sys, sqlite3, tempfile, math, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from kh import calibration as cal, integrity, db, backtest, quant, perf


def test_brier_logloss_known_values():
    assert cal.brier([0.8, 0.3], [1, 0]) == pytest.approx((0.04 + 0.09) / 2)
    assert cal.log_loss([0.8], [1]) == pytest.approx(-math.log(0.8))
    assert cal.log_loss([0.0], [1]) == pytest.approx(-math.log(cal.EPS))       # clipped, finite


def test_reliability_bins_counts():
    r = cal.reliability([0.05, 0.07, 0.95, 1.0], [0, 1, 1, 1])
    assert [b["n"] for b in r] == [2, 2] and r[0]["freq"] == 0.5


def test_bootstrap_ci_contains_point_and_diff_sign():
    ys = [1, 0] * 50; good = [0.9 if y else 0.1 for y in ys]; bad = [0.5] * 100
    res = cal.compare(good, bad, ys, reps=300)
    lo, hi = res["brier_diff_ci"]
    assert res["brier_diff"] < 0 and lo <= res["brier_diff"] <= hi and hi < 0


def test_hash_chain_detects_tampering():
    c = db.connect(tempfile.mktemp(suffix=".db"))
    c.execute("INSERT INTO forecasts(ts,ticker,side,prob_yes,exec_price,qty,fee,ev) VALUES(1,'X','no',0.2,0.7,10,0.15,0.1)"); c.commit()
    assert integrity.seal(c) == 1 and integrity.verify(c) == []
    c.execute("DROP TRIGGER ro_forecasts_update"); c.execute("UPDATE forecasts SET prob_yes=0.9"); c.commit()
    assert any("content changed" in p for p in integrity.verify(c))


def _rows():
    return [{"ticker": f"T{i}", "pred_ts": 1000 + i * 100, "close_ts": 1000 + i * 100 + 50, "f_ts": 1000 + i * 100 - 3601,
             "f_prev_ts": 1000 + i * 100 - 90000, "yes_bid": 0.04, "yes_ask": 0.06, "prev_mid": 0.2, "outcome": i % 2} for i in range(20)]


def test_leakage_detector_fails_on_lookahead():
    rows = _rows(); assert backtest.leakage_violations(rows) == []
    rows[3]["f_ts"] = rows[3]["pred_ts"] - 3600                  # feature at the prediction time = leak
    assert backtest.leakage_violations(rows) == ["T3"]
    with pytest.raises(AssertionError): backtest.run(rows, reps=10)


def test_real_backtest_dataset_has_no_lookahead():
    if not os.path.exists(backtest.DS): pytest.skip("dataset not built")
    rows = backtest.load(); assert rows and backtest.leakage_violations(rows) == []


def test_time_split_is_ordered_and_purged():
    tr, te = backtest.split(_rows())
    assert max(r["pred_ts"] for r in tr) < min(r["pred_ts"] for r in te)
    assert all(r["close_ts"] < te[0]["pred_ts"] for r in tr)


def test_backtest_fill_uses_ask_and_fee():
    r = {"ticker": "X", "yes_bid": 0.04, "yes_ask": 0.06, "outcome": 0, "pred_ts": 1}
    t = backtest.trade(r, "no")
    assert t["price"] == pytest.approx(0.96) and t["fee"] == 0.01 and t["pnl"] == pytest.approx(1 - 0.96 - 0.01)


def test_paper_fill_capped_at_depth_walks_levels():
    ob = {"orderbook_fp": {"yes_dollars": [["0.30", "5"]], "no_dollars": [["0.60", "3"], ["0.55", "4"]]}}
    avg, got = quant.executable_buy(ob, "yes", 100)
    assert got == 7 and avg == pytest.approx((3 * 0.40 + 4 * 0.45) / 7)


def test_market_implied_probabilities():
    top = {"yes_bid": 0.65, "yes_ask": 0.66}
    mid, ex = perf.market_implied("no", top, 0.35, 10, 0.16)
    assert mid == pytest.approx(0.655) and ex == pytest.approx(1 - 0.366)


def test_candidates_append_only_and_chained():
    c = db.connect(tempfile.mktemp(suffix=".db"))
    db.upsert_candidate(c, "k", "key", "E", 0.1, {}, {}, "screened"); c.commit()
    with pytest.raises(sqlite3.IntegrityError): c.execute("UPDATE candidates SET status='x'")
    with pytest.raises(sqlite3.IntegrityError): c.execute("DELETE FROM candidates")
    assert integrity.seal(c) >= 1 and integrity.verify(c) == []


def test_cluster_bootstrap_wider_than_iid_for_correlated_data():
    xs = [1.0] * 10 + [-1.0] * 10; cl = ["a"] * 10 + ["b"] * 10   # two perfectly correlated clusters
    f = lambda i: sum(xs[j] for j in i) / len(i)
    iid = cal.bootstrap(f, 20, 500); clu = cal.bootstrap(f, 20, 500, clusters=cl)
    assert (clu[1] - clu[0]) > (iid[1] - iid[0])


def test_decision_time_rules_use_advance_info_only():
    m = {"expected_expiration_time": "2026-10-10T00:00:00Z", "open_time": "2026-10-01T00:00:00Z",
         "close_time": "2026-10-03T00:00:00Z", "settlement_ts": "2026-10-03T01:00:00Z"}
    m2 = dict(m, close_time="2026-10-09T00:00:00Z", settlement_ts="2026-10-09T01:00:00Z")   # different actual close
    for rule in ("sched24", "open72"):
        assert backtest.decision_time(m, rule) == backtest.decision_time(m2, rule)        # unaffected by when it actually closed
    assert backtest.decision_time(m, "close24_legacy") != backtest.decision_time(m2, "close24_legacy")


def test_external_checkpoint_detects_rewrite(tmp_path):
    p = str(tmp_path / "x.db"); c = db.connect(p)
    c.execute("INSERT INTO forecasts(ts,ticker,side,prob_yes,exec_price,qty,fee,ev) VALUES(1,'X','no',0.2,0.7,10,0.15,0.1)"); c.commit()
    integrity.seal(c); cp = str(tmp_path / "cp.log"); integrity.checkpoint(c, cp)
    assert integrity.verify_checkpoints(c, cp) == []
    c.close(); os.remove(p); c = db.connect(p)              # full rewrite: fresh DB, same row, chain rebuilt
    c.execute("INSERT INTO forecasts(ts,ticker,side,prob_yes,exec_price,qty,fee,ev) VALUES(2,'X','no',0.2,0.7,10,0.15,0.1)"); c.commit(); integrity.seal(c)
    assert integrity.verify_checkpoints(c, cp) != []


def test_flb_spec_hash_frozen():
    from kh import prereg_flb
    P = prereg_flb.params(); assert P["buy_no_if_mid_lte"] == 0.10 and P["buy_yes_if_mid_gte"] == 0.90
