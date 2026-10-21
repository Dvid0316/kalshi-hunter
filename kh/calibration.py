"""Forecast-quality metrics. Unit tests check the math; only resolved out-of-sample forecasts are evidence of accuracy."""
import math, random

EPS = 1e-3  # log-loss clip: p in [EPS, 1-EPS]


def brier(ps, ys):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps) if ps else None


def log_loss(ps, ys, eps=EPS):
    if not ps: return None
    t = 0.0
    for p, y in zip(ps, ys):
        p = min(1 - eps, max(eps, p)); t -= y * math.log(p) + (1 - y) * math.log(1 - p)
    return t / len(ps)


def reliability(ps, ys, bins=10):
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(ps) if (lo <= p < hi) or (b == bins - 1 and p == 1.0)]
        if idx:
            out.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": len(idx), "mean_p": sum(ps[i] for i in idx) / len(idx),
                        "freq": sum(ys[i] for i in idx) / len(idx)})
    return out


def bootstrap(fn, n, reps=2000, seed=0, clusters=None):
    """Percentile 95% CI of fn(index_list). If `clusters` (list of cluster ids, len n) is given, resample whole
    clusters (block/cluster bootstrap) so correlated items (same series/event) move together."""
    if n == 0: return (None, None)
    rng = random.Random(seed); vals = []
    groups = None
    if clusters is not None:
        g = {}
        for i, k in enumerate(clusters): g.setdefault(k, []).append(i)
        groups = list(g.values())
    for _ in range(reps):
        if groups:
            idx = [i for _ in range(len(groups)) for i in groups[rng.randrange(len(groups))]]
        else:
            idx = [rng.randrange(n) for _ in range(n)]
        if not idx: continue
        v = fn(idx)
        if v is not None: vals.append(v)
    vals.sort()
    return (vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))])


def compare(ours, market, ys, reps=2000, clusters=None):
    """Full comparison block with CIs, incl. Brier difference (ours - market; negative = we're better)."""
    n = len(ys); sub = lambda xs, idx: [xs[i] for i in idx]
    res = {"n": n, "n_clusters": len(set(clusters)) if clusters else None, "ci_method": "cluster bootstrap" if clusters else "iid bootstrap"}
    for name, ps in (("ours", ours), ("market", market)):
        res[name] = {"brier": brier(ps, ys), "brier_ci": bootstrap(lambda i: brier(sub(ps, i), sub(ys, i)), n, reps, clusters=clusters),
                     "log_loss": log_loss(ps, ys), "log_loss_ci": bootstrap(lambda i: log_loss(sub(ps, i), sub(ys, i)), n, reps, clusters=clusters)}
    res["brier_diff"] = (brier(ours, ys) - brier(market, ys)) if n else None
    res["brier_diff_ci"] = bootstrap(lambda i: brier(sub(ours, i), sub(ys, i)) - brier(sub(market, i), sub(ys, i)), n, reps, clusters=clusters)
    return res


def plot_reliability(series, path, title):
    """series: {label: (ps, ys)}. Writes PNG with bin counts annotated."""
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 6)); ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
    for label, (ps, ys) in series.items():
        r = reliability(ps, ys)
        if not r: continue
        ax.plot([b["mean_p"] for b in r], [b["freq"] for b in r], "o-", label=f"{label} (n={len(ps)})")
        for b in r: ax.annotate(str(b["n"]), (b["mean_p"], b["freq"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("forecast P(YES)"); ax.set_ylabel("observed YES frequency"); ax.set_title(title, fontsize=9)
    ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)
