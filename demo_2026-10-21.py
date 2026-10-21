"""Initial demo: sourced research -> independent estimate -> contrarian audit -> paper forecast (10 contracts, hypothetical)."""
import sys, json, time, os
sys.path.insert(0, os.path.dirname(__file__))
from kh import db, api as kapi, perf, auditor, quant
from kh.fees import fee
c = db.connect(); a = kapi.Public(db=c)
R = [
 dict(ticker="CONTROLS-2026-D", side="no", p=0.59, lo=0.52, hi=0.66,
  method="Median of 6 public Senate models dated Oct 20-21 2026 (53-62 FutureBallot, 56 CallTheMap, 55 DDHQ, 60 535.wtf, 64 Crosstab); band = model spread",
  sources=["https://futureballot.com/senate","https://www.callthemap.com/senate","https://votes.decisiondeskhq.com/forecast/2026/senate",
           "https://535.wtf/dispatches/540-our-model-gives-democrats-a-60-senate-chance-as-the-generic","https://crosstab.vote/senate-forecast/"],
  counter="Search synthesis also cited a COYNTOSS model at 67% (not opened). Markets aggregate late info and money; models disagree by >10pts. FutureBallot shows 61-67% 'if election were today'. Generic ballot D+8.5 (535.wtf) is strong for D.",
  audit="Settlement: Kalshi rule uses party of President pro tempore on Feb 1 2027 or media consensus; independents (e.g. Osborn NE) caucusing creates real ambiguity (FutureBallot range 53-62 depends on it). Edge disappears inside model spread."),
 dict(ticker="CONTROLH-2026-D", side="no", p=0.85, lo=0.77, hi=0.95,
  method="Spread of 4 public House models Oct 20-21 2026: DDHQ 77, CallTheMap 82, Crosstab 88, 535.wtf 99 (median ~85)",
  sources=["https://votes.decisiondeskhq.com/forecast/2026/house","https://www.callthemap.com/house","https://crosstab.vote/house/",
           "https://535.wtf/dispatches/540-our-model-gives-democrats-a-60-senate-chance-as-the-generic"],
  counter="535.wtf gives 99% and D+8.5 generic ballot; Trump approval at record lows (Reuters/Ipsos 31%). Models with lower D odds may be over-regressed to fundamentals. Market 90.8% sits inside model range.",
  audit="Model disagreement (77-99) is wider than the price gap; buying R at ~9c is a long-shot bet with fee drag. Not robust."),
 dict(ticker="KXAPRPOTUS-26OCT23-38.5", side="no", p=0.15, lo=0.07, hi=0.27,
  method="RCP approve 38.9 on Oct 19 (USA Today) -> 38.2 on Oct 21 (Wikipedia aggregator table; PredictIt Oct-21 market 88% on 38.2-38.4 corroborates). New polls trending lower (Reuters/Ipsos 31, WaPo/ABC 33, NBC/SurveyMonkey 34). Bucket 38.4-38.6 needs a +0.2..+0.4 rebound in 2 days.",
  sources=["https://en.wikipedia.org/wiki/Opinion_polling_on_the_second_Trump_presidency","https://www.usatoday.com/story/news/politics/2026/10/19/trump-approval-rating-reuters-ipsos-poll/92335405007/",
           "https://thehill.com/homenews/administration/6159609-trump-approval-record-low-reuters-ipsos/",
           "https://www.coinrithm.com/en/prediction-markets/predictit/What-will-President-Trump's-RCP-job-approval-rating-be-on-Oct-21"],
  counter="RCP average is a simple window average: old low polls rolling off or friendly polls (TIPP, Noble, Rasmussen-type) entering can lift it 0.3+ in a day. Silver Bulletin bounced from -23.9 to -22.3 on such polls. I could not load realclearpolling.com directly (bot-blocked), so 38.2 is second-hand.",
  audit="Primary settlement source not directly verified; one-day RCP moves of 0.3-0.5 are common; worst-case of band kills edge. Short-dated (resolves Oct 23 11:00 ET), useful for fast calibration."),
]
out = []
for r in R:
    m = a.market(r["ticker"])
    cur = c.execute("INSERT INTO research(ts,ticker,prob_yes,prob_lo,prob_hi,method,sources,counter_evidence,auditor,author) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (time.time(), r["ticker"], r["p"], r["lo"], r["hi"], r["method"], json.dumps(r["sources"]), r["counter"], r["audit"], "demo-2026-10-21"))
    rid = cur.lastrowid
    fid, avg, got, f, ev, top = perf.record_forecast(a, c, r["ticker"], r["side"], r["p"], r["lo"], r["hi"], rid, qty=10, note="demo")
    depth = top["no_ask_size"] if r["side"] == "no" else top["yes_ask_size"]
    amb = bool(auditor.AMBIG.search((m.get("rules_primary") or "") + (m.get("rules_secondary") or ""))) or "may be determined" in (m.get("rules_secondary") or "")
    ok, notes, evw = auditor.audit_model(r["p"], r["lo"], r["hi"], r["side"], avg, auditor.hours_to_close(m["close_time"]), depth, amb)
    out.append(dict(ticker=r["ticker"], side=r["side"], ts=time.strftime("%F %T %Z"), top=top, fill=round(avg, 4), qty=got, fee=f,
                    ev_per_contract=round(ev, 4), ev_worst=round(evw, 4), qualifies=ok, audit_notes=notes, research_id=rid, forecast_id=fid))
print(json.dumps(out, indent=1))
json.dump(out, open("research/demo_2026-10-21.json", "w"), indent=1)
