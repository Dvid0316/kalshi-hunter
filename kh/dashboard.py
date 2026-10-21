import html, json, time, datetime as dt, os
from . import perf
OUT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "index.html")


def ts(t):
    return dt.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M CT") if t else ""


def table(rows, cols):
    h = "<tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr>"
    for r in rows:
        h += "<tr>" + "".join(f"<td>{html.escape(str(x))}</td>" for x in r) + "</tr>"
    return f"<table>{h}</table>"


def render(c):
    raise RuntimeError("Legacy HTML dashboard retired; use the offline Qt desktop")
