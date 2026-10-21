"""Three strictly separate tracks, never pooled:
 A = mechanical backtest (historical, rule-based)   B = calibration of our researched forecasts vs market
 C = forward paper-trading performance (prospective fills)"""
import json, os, time, datetime as dt
from . import calibration as cal, backtest, integrity
ROOT = os.path.dirname(os.path.dirname(__file__))
FIG = os.path.join(ROOT, "research", "figures_v2"); OUTJ = os.path.join(ROOT, "data", "validation_v2.json")
ORIG_DB = os.path.join(ROOT, "research", "archive", "2026-10-21-original", "backtest_original_closeanchored.db")


def ct(t): return dt.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M CT") if t else "-"
def f(x, d=4): return "-" if x is None else (f"{x:.{d}f}" if isinstance(x, float) else str(x))
def ci(t): return "-" if not t or t[0] is None else f"[{t[0]:.4f}, {t[1]:.4f}]"


def _load_original():
    import sqlite3
    c = sqlite3.connect(ORIG_DB); c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute("SELECT * FROM pit WHERE yes_bid>0 AND yes_ask<1 AND yes_ask>yes_bid ORDER BY pred_ts")]
    for r in rows: r["early_closed"] = None   # not recorded in original data
    return rows


def track_a():
    out = {}
    sets = [("original (archived, close-anchored, iid CIs in old report)", _load_original)] + \
           [(f"corrected:{rule}", (lambda rule=rule: backtest.load(rule=rule))) for rule in ("sched24", "open72", "close24_legacy")]
    for name, loader in sets:
        rows = loader()
        if len(rows) < 20: out[name] = {"n_all": len(rows), "note": "too few rows"}; continue
        r = backtest.run(rows); test = r.pop("_test_rows"); r.pop("_fitted"); out[name] = r
        if name.startswith("corrected:sched24") or name.startswith("corrected:open72"):
            os.makedirs(FIG, exist_ok=True)
            cal.plot_reliability({"market mid at T (test)": ([backtest.mid(x) for x in test], [x["outcome"] for x in test])},
                                 os.path.join(FIG, f"A_{name.split(':')[1]}_market_reliability_test.png"), f"Track A {name}, test n={len(test)}")
    return {"rulesets": out}
def track_b(c):
    rows = c.execute("""SELECT f.id, f.ticker, f.side, f.prob_yes, m.mid_p, m.exec_implied_p, z.outcome FROM forecasts f
        JOIN resolutions z ON z.forecast_id=f.id LEFT JOIN forecast_market m ON m.forecast_id=f.id""").fetchall()
    total = c.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
    out = {"n_forecasts": total, "n_resolved": len(rows)}
    rows = [r for r in rows if r["mid_p"] is not None]
    if rows:
        ys = [r["outcome"] for r in rows]; ours = [r["prob_yes"] for r in rows]
        out["vs_mid"] = cal.compare(ours, [r["mid_p"] for r in rows], ys)
        out["vs_exec"] = cal.compare(ours, [r["exec_implied_p"] for r in rows], ys)
        os.makedirs(FIG, exist_ok=True)
        cal.plot_reliability({"ours": (ours, ys), "market mid": ([r["mid_p"] for r in rows], ys),
                              "market exec-implied": ([r["exec_implied_p"] for r in rows], ys)},
                             os.path.join(FIG, "B_reliability.png"), f"Track B: researched forecasts (n={len(rows)} resolved)")
    out["edges_at_forecast_time"] = [dict(r) for r in c.execute(
        """SELECT f.id, f.ticker, f.side, f.prob_yes, round(m.mid_p,4) mid_p, round(m.exec_implied_p,4) exec_implied_p,
           round(m.edge_vs_mid,4) edge_vs_mid, round(m.edge_vs_exec,4) edge_vs_exec, z.outcome FROM forecasts f
           LEFT JOIN forecast_market m ON m.forecast_id=f.id LEFT JOIN resolutions z ON z.forecast_id=f.id ORDER BY f.id""")]
    return out


def track_c(c):
    rs = c.execute("""SELECT f.*, z.outcome AS outcome, z.pnl AS pnl FROM forecasts f LEFT JOIN resolutions z ON z.forecast_id=f.id
                      WHERE COALESCE(f.note,'') NOT LIKE 'prereg_%' ORDER BY f.id""").fetchall()
    done = [r for r in rs if r["outcome"] is not None]; pn = [r["pnl"] for r in done]
    sl = [r["exec_price"] - r["est_price"] for r in rs if r["est_price"] is not None]  # paper fills only (not auditor re-checks)
    return {"n_fills": len(rs), "n_resolved": len(done), "n_open": len(rs) - len(done),
            "net_pnl": sum(pn) if pn else None, "mean_pnl_ci": cal.bootstrap(lambda i: sum(pn[j] for j in i) / len(i), len(pn)),
            "wins": sum(1 for r in done if (r["outcome"] == 1) == (r["side"] == "yes")),
            "losses": sum(1 for r in done if (r["outcome"] == 1) != (r["side"] == "yes")),
            "slippage_n": len(sl), "slippage_mean": (sum(sl) / len(sl)) if sl else None, "slippage_max": max(sl) if sl else None,
            "fills": [dict(ticker=r["ticker"], side=r["side"], ts=ct(r["ts"]), qty=r["qty"], est=r["est_price"], exec=r["exec_price"],
                           fee=r["fee"], outcome=r["outcome"], pnl=r["pnl"]) for r in rs]}


def track_c_flb(c):
    rs = c.execute("""SELECT f.*, z.outcome AS outcome, z.pnl AS pnl FROM forecasts f LEFT JOIN resolutions z ON z.forecast_id=f.id
                      WHERE f.note='prereg_flb_v1' ORDER BY f.id""").fetchall()
    done = [r for r in rs if r["outcome"] is not None]; pn = [r["pnl"] for r in done]
    ser = [r["ticker"].split("-")[0] for r in done]
    return {"n_entries": len(rs), "n_resolved": len(done), "n_series": len(set(ser)), "net_pnl": sum(pn) if pn else None,
            "mean_pnl_ci_cluster": cal.bootstrap(lambda i: sum(pn[j] for j in i) / len(i), len(pn), clusters=ser),
            "wins": sum(1 for r in done if (r["outcome"] == 1) == (r["side"] == "yes")),
            "losses": sum(1 for r in done if (r["outcome"] == 1) != (r["side"] == "yes"))}


def generate(c):
    integrity.seal(c)
    v = {"generated": time.time(), "A": track_a(), "B": track_b(c), "C": track_c(c), "C_flb": track_c_flb(c),
         "integrity_problems": integrity.verify(c) + integrity.verify_checkpoints(c)}
    json.dump({rs: {k: {p: d.get("trades", []) for p, d in st.items()} for k, st in R.get("strategies", {}).items()}
               for rs, R in v["A"]["rulesets"].items()}, open(os.path.join(ROOT, "data", "validation_trades_A_v2.json"), "w"), indent=1)
    strip = lambda R: {**{k: x for k, x in R.items() if k != "strategies"},
                       "strategies": {k: {p: {kk: vv for kk, vv in d.items() if kk != "trades"} for p, d in st.items()} for k, st in R.get("strategies", {}).items()}}
    json.dump({**v, "A": {"rulesets": {rs: strip(R) for rs, R in v["A"]["rulesets"].items()}}}, open(OUTJ, "w"), default=str, indent=1)
    path = os.path.join(ROOT, "research", f"validation_report_{dt.date.today()}_corrected.md"); open(path, "w").write(render_md(v)); return path, v


def render_md(v):
    A, B, C = v["A"], v["B"], v["C"]; L = []
    L += [f"# Kalshi Hunter validation report ({ct(v['generated'])})", "",
          "Research and paper trading only. The three tracks below are kept separate and are never pooled. Unit tests check arithmetic. They are not evidence of forecasting accuracy.", "",
          f"Integrity (hash chain over append-only tables, including screened candidates): {'intact' if not v['integrity_problems'] else v['integrity_problems']}. "
          f"The chain was first sealed at 2026-10-21 11:31 AM CT. Rows created before that (forecasts 1–3 at 9:58–9:59 AM CT) had no chain protection until then. "
          "External head-hash checkpoints are appended after every cycle to `research/chain_checkpoints.log`.", "",
          "## Plain answer",
          "**A measurable advantage over Kalshi market prices has NOT been demonstrated.** Track B has "
          f"{B['n_resolved']} resolved researched forecasts and track C has {C['n_resolved']} resolved paper fills, which is far too few to estimate anything. "
          "Track A tests only simple mechanical rules on historical quotes. See that section; no rule shows a cluster-robust positive result that is consistent across train and test and across decision-time rules. "
          "No predictive-advantage claim will be made until prospective tracks B and C support one with confidence intervals that exclude zero.", ""]
    L += ["## Track A: mechanical backtest (historical, rule-based)",
          "Original (archived) vs corrected are shown side by side. All CIs are **series-cluster bootstrap** 95% (2,000 resamples). The original report's CIs were i.i.d.; here they are recomputed with clustering.",
          "Decision-time rules: **sched24** = expected_expiration_time − 24h; **open72** = open_time + 72h (both known in advance). **close24_legacy** = actual close − 24h, which uses HINDSIGHT and is shown for reference only. Original = close24 on the archived dataset.",
          "Subsets: on_schedule = closed within 3 days of the expected expiration; early_closed = closed more than 3 days early. Under sched24, early-closed markets were already closed at T, so they're excluded (logged in `exclusions`) and that subset is empty by construction.", ""]
    for rs, R in A["rulesets"].items():
        L.append(f"### {rs}")
        if "strategies" not in R: L += [f"Not available: {R}", ""]; continue
        L.append(f"Rows all/train/test: {R['n_all']}/{R['n_train']}/{R['n_test']}. Test predictions {ct(R['test_span'][0])} to {ct(R['test_span'][1])}.")
        for nm, pt in [("test, all", R["probability_test"])] + [(f"test, {k}", x) for k, x in R.get("probability_test_by_subset", {}).items()]:
            if pt.get("n"):
                L.append(f"- Probability ({nm}): n={pt['n']} ({pt.get('n_clusters')} series). Calibration-map Brier {f(pt['ours']['brier'])} {ci(pt['ours']['brier_ci'])} vs market mid {f(pt['market']['brier'])} {ci(pt['market']['brier_ci'])}. Diff {f(pt['brier_diff'])} {ci(pt['brier_diff_ci'])}.")
            else:
                L.append(f"- Probability ({nm}): n=0")
        L += ["", "| strategy | part:subset | n | series | hit rate | wins | losses | net P&L $ (1-lot) | mean/trade | cluster 95% CI |", "|---|---|---|---|---|---|---|---|---|---|"]
        for k, st in R["strategies"].items():
            for p, d in st.items():
                L.append(f"| {k} | {p} | {d['n']} | {d['n_series']} | {f(d['hit_rate'],3)} | {d['wins']} | {d['losses']} | {f(d['net_pnl'],2)} | {f(d['mean_pnl'])} | {ci(d['mean_pnl_ci'])} |")
        L.append("")
    # favourite-longshot tail-risk check: zero observed losses cannot rule out a loss rate that erases the edge
    L += ["### Favourite-longshot (flb): why a positive cluster CI is still NOT evidence of an edge"]
    for rs, R in A["rulesets"].items():
        d = R.get("strategies", {}).get("flb", {}).get("test")
        if not d or not d["n"]: continue
        tr = [t for t in __import__("json").load(open(os.path.join(ROOT, "data", "validation_trades_A_v2.json")))[rs]["flb"]["test"]] if os.path.exists(os.path.join(ROOT, "data", "validation_trades_A_v2.json")) else []
        avg_px = (sum(t["price"] + t["fee"] for t in tr) / len(tr)) if tr else None
        be = (1 - avg_px) if avg_px else None
        L.append(f"- {rs}: test n={d['n']}, losses={d['losses']}. Average all-in cost {f(avg_px,3)}, so the break-even loss rate is about {f(be,3)}. "
                 f"The 95% upper bound on the true loss rate with {d['losses']} losses in {d['n']} (rule of three ≈ 3/n) is {f(3/d['n'] if d['losses']==0 else None,3)}, which is far above break-even. "
                 "A single loss costs about as much as 30–100 wins. The bootstrap can't resample a loss it never saw, so its CI understates this tail risk.")
    L += ["Conclusion: flb's small positive mean (about 1–2c/contract on 1-lots at 90c+ prices) is **not** a demonstrated advantage. It's pre-registered as forward paper strategy flb_v1 (track C2) for that reason.", ""]
    L += ["Every trade (wins and losses) for every ruleset: `data/validation_trades_A_v2.json`. Exclusions by ticker and reason: table `exclusions` in `data/backtest.db`. The 11 rows dropped on Oct 21 are covered in `research/exclusions_2026-10-21.csv` (see the note there). Data limitations: `research/CANDLE_LIMITATIONS.md`.", ""]
    L += ["## Track B: calibration of our researched forecasts vs market",
          f"Forecasts recorded (append-only, including auditor-rejected ones): {B['n_forecasts']}. Resolved: {B['n_resolved']}."]
    if B.get("vs_mid"):
        for k in ("vs_mid", "vs_exec"):
            x = B[k]; L.append(f"- {k}: n={x['n']}, ours Brier {f(x['ours']['brier'])} {ci(x['ours']['brier_ci'])}, market {f(x['market']['brier'])} {ci(x['market']['brier_ci'])}, diff {f(x['brier_diff'])} {ci(x['brier_diff_ci'])}")
    else:
        L.append("- No resolved forecasts, so Brier, log loss and reliability can't be computed. n is far too small to conclude anything.")
    L += ["", "Edge at forecast time (stored when each forecast was made):", "", "| id | ticker | side | our p(YES) | mid p | exec-implied p (spread+fees) | edge vs mid | edge vs exec | outcome |", "|---|---|---|---|---|---|---|---|---|"]
    for e in B["edges_at_forecast_time"]:
        L.append(f"| {e['id']} | {e['ticker']} | {e['side']} | {e['prob_yes']} | {e['mid_p']} | {e['exec_implied_p']} | {e['edge_vs_mid']} | {e['edge_vs_exec']} | {f(e['outcome'])} |")
    L += ["", "Track B limitations: 3 forecasts, all made by hand on one day and correlated (two are on the same midterm). They are pre-registered but not yet resolved. The two control markets settle no earlier than the Nov 3 election calls.", ""]
    L += ["## Track C: forward paper-trading performance (prospective fills)",
          f"Fills: {C['n_fills']} (open {C['n_open']}, resolved {C['n_resolved']}). Wins {C['wins']}, losses {C['losses']}. Net P&L: {f(C['net_pnl'],2)}. Mean P&L 95% CI: {ci(C['mean_pnl_ci'])}.",
          f"Slippage on paper fills (average fill minus quoted top-of-book ask), n={C['slippage_n']}: mean {f(C['slippage_mean'])}, max {f(C['slippage_max'])}.", "",
          "| ticker | side | time | qty | quoted | filled | fee | outcome | P&L |", "|---|---|---|---|---|---|---|---|---|"]
    for x in C["fills"]:
        L.append(f"| {x['ticker']} | {x['side']} | {x['ts']} | {x['qty']} | {x['est']} | {x['exec']} | {x['fee']} | {f(x['outcome'])} | {f(x['pnl'],2)} |")
    L += ["", "Track C limitations: fills are hypothetical taker fills that walk the live book, capped at displayed depth and charged fees. Queue position, latency and market impact are not modeled. n is far too small to conclude anything.", ""]
    F = v["C_flb"]
    L += ["## Track C2: pre-registered forward paper strategy flb_v1 (separate from researched fills)",
          f"Spec frozen in `strategies/flb_v1.json` (sha256 in `.sha256`; registration logged at 2026-10-21 12:00:44 CT in `research/chain_checkpoints.log`). The JSON's `registered_at` field says 12:05; the log entry is the authoritative time.",
          f"Entries {F['n_entries']}, resolved {F['n_resolved']} across {F['n_series']} series. Wins {F['wins']}, losses {F['losses']}. Net P&L {f(F['net_pnl'],2)}. Cluster CI {ci(F['mean_pnl_ci_cluster'])}.",
          "Success criterion set in advance: n ≥ 300 resolved, ≥ 30 series, cluster CI entirely above 0. Not met.", ""]
    return "\n".join(L)
