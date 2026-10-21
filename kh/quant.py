"""Orderbook -> executable prices, EV after fees, and cross-market inconsistency detection."""
from .fees import fee


def parse_book(ob: dict):
    """Kalshi orderbook_fp has only BIDS: yes_dollars and no_dollars as [[price, size], ...] ascending.
    A YES ask at p exists because someone bids NO at 1-p."""
    o = ob.get("orderbook_fp", ob) or {}
    yes = [(float(p), float(s)) for p, s in (o.get("yes_dollars") or [])]
    no = [(float(p), float(s)) for p, s in (o.get("no_dollars") or [])]
    yes.sort(key=lambda x: -x[0]); no.sort(key=lambda x: -x[0])  # best bid first
    return yes, no


def asks_from_bids(opp_bids):
    """Asks for side S = 1 - bids on the opposite side, cheapest first."""
    return [(round(1 - p, 6), s) for p, s in opp_bids]


def top_of_book(ob: dict):
    yes, no = parse_book(ob)
    yb = yes[0] if yes else (None, 0)
    nb = no[0] if no else (None, 0)
    ya = (round(1 - nb[0], 6), nb[1]) if nb[0] is not None else (None, 0)
    na = (round(1 - yb[0], 6), yb[1]) if yb[0] is not None else (None, 0)
    return {"yes_bid": yb[0], "yes_bid_size": yb[1], "no_bid": nb[0], "no_bid_size": nb[1],
            "yes_ask": ya[0], "yes_ask_size": ya[1], "no_ask": na[0], "no_ask_size": na[1]}


def vwap_to_fill(asks, qty):
    """Walk ask levels; return (avg_price, filled_qty)."""
    got = 0.0; cost = 0.0
    for p, s in asks:
        take = min(s, qty - got)
        if take <= 0: break
        got += take; cost += take * p
    return ((cost / got) if got else None, got)


def executable_buy(ob: dict, side: str, qty: float):
    """Average executable price to BUY qty contracts of side ('yes'/'no') by taking liquidity."""
    yes, no = parse_book(ob)
    asks = asks_from_bids(no if side == "yes" else yes)
    return vwap_to_fill(asks, qty)


def ev_per_contract(prob_yes: float, side: str, price: float, contracts: float = 100, mult: float = 1.0):
    """Expected profit per contract for buying `side` at `price` (taker), after fees."""
    p_win = prob_yes if side == "yes" else 1 - prob_yes
    f = fee(price, contracts, mult) / contracts
    return p_win * 1.0 - price - f


def best_side(prob_yes, yes_ask, no_ask, contracts=100, mult=1.0):
    out = []
    if yes_ask is not None and 0 < yes_ask < 1:
        out.append(("yes", yes_ask, ev_per_contract(prob_yes, "yes", yes_ask, contracts, mult)))
    if no_ask is not None and 0 < no_ask < 1:
        out.append(("no", no_ask, ev_per_contract(prob_yes, "no", no_ask, contracts, mult)))
    return max(out, key=lambda x: x[2]) if out else None


# ---------- structural (model-free) inconsistencies ----------

def mutex_arbs(markets, mult=1.0, contracts=1, min_edge=0.0):
    """markets: list of dicts with ticker, yes_ask, no_ask (dollars), from ONE mutually exclusive event.
    1) BUY ALL NO: if at most one YES can occur, buying NO on all n pays >= n-1. Riskless iff mutual exclusivity holds.
    2) BUY ALL YES: pays exactly 1 only if the set is also EXHAUSTIVE (exactly one resolves YES) -> flagged needs_exhaustive.
    Returns list of findings with guaranteed profit per 1-contract set after taker fees."""
    res = []
    n = len(markets)
    if n < 2: return res
    nos = [m["no_ask"] for m in markets]
    if all(x is not None and 0 < x < 1 for x in nos):
        cost = sum(nos) + sum(fee(x, contracts, mult) / contracts for x in nos)
        edge = (n - 1) - cost
        if edge > min_edge:
            res.append({"kind": "mutex_all_no", "edge": round(edge, 4), "cost": round(cost, 4),
                        "payout_min": n - 1, "needs_exhaustive": False,
                        "legs": [(m["ticker"], "no", m["no_ask"]) for m in markets]})
    yeses = [m["yes_ask"] for m in markets]
    if all(x is not None and 0 < x < 1 for x in yeses):
        cost = sum(yeses) + sum(fee(x, contracts, mult) / contracts for x in yeses)
        edge = 1 - cost
        if edge > min_edge:
            res.append({"kind": "mutex_all_yes", "edge": round(edge, 4), "cost": round(cost, 4),
                        "payout_min": 1, "needs_exhaustive": True,
                        "legs": [(m["ticker"], "yes", m["yes_ask"]) for m in markets]})
    return res


def ladder_violations(markets, mult=1.0, contracts=1, min_edge=0.0):
    """Threshold ladder in one event. For strike_type 'greater' (YES if value > strike):
    P(> high) <= P(> low). If yes_bid(high) > yes_ask(low) the ladder is inverted: buy YES(low) + buy NO(high)
    costs yes_ask(low)+no_ask(high) and pays >= 1 in every state. For 'less', the order is reversed."""
    out = []
    by_type = {}
    for m in markets:
        if m.get("strike") is None or m.get("strike_type") not in ("greater", "less"): continue
        by_type.setdefault(m["strike_type"], []).append(m)
    for st, ms in by_type.items():
        ms = sorted(ms, key=lambda m: m["strike"])
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                lo, hi = ms[i], ms[j]
                # 'greater': YES(lo) dominates YES(hi). 'less': YES(hi) dominates YES(lo).
                dom, sub = (lo, hi) if st == "greater" else (hi, lo)
                if dom.get("yes_ask") is None or sub.get("no_ask") is None: continue
                if not (0 < dom["yes_ask"] < 1 and 0 < sub["no_ask"] < 1): continue
                cost = dom["yes_ask"] + sub["no_ask"] + fee(dom["yes_ask"], contracts, mult) / contracts \
                    + fee(sub["no_ask"], contracts, mult) / contracts
                edge = 1 - cost
                if edge > min_edge:
                    out.append({"kind": "ladder_" + st, "edge": round(edge, 4), "cost": round(cost, 4),
                                "payout_min": 1, "needs_exhaustive": False,
                                "legs": [(dom["ticker"], "yes", dom["yes_ask"]), (sub["ticker"], "no", sub["no_ask"])]})
    return out


def brier(prob, outcome):
    return (prob - outcome) ** 2
