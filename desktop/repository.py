"""Read-only snapshot queries. Each call owns its SQLite connection in its worker."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from kh import db, perf, integrity, calibration
from kh.cohorts import forecast_rows
from kh.accounting import amount
ROOT=Path(__file__).resolve().parents[1]
SNAPSHOT=ROOT/'data/kalshi.db'


def stamp(ts):
    return datetime.fromtimestamp(ts,ZoneInfo('America/Chicago')).strftime('%b %d, %Y · %H:%M %Z') if ts else 'Unavailable'


def money(x): return f'${x:,.2f}' if x is not None else 'Unavailable'
def cents(x): return f'{x*100:.1f}¢' if x is not None else '—'


class Repository:
    def __init__(self,path=SNAPSHOT): self.path=Path(path)

    def overview(self):
        with db.readonly(self.path) as c:
            last=dict(c.execute("SELECT * FROM scans WHERE status='ok' ORDER BY id DESC LIMIT 1").fetchone())
            cohorts={}
            for cohort in ('research','strategy'):
                s=perf.stats(c,cohort)
                rows=forecast_rows(c,cohort)
                s['cost']=float(sum(amount(r['qty'])*amount(r['exec_price'])+amount(r['fee']) for r in rows))
                s['rows']=[dict(r,price=cents(r['exec_price']),fee_text=money(r['fee']),pnl_text=money(r['pnl']) if r['id'] not in s['accounting_discrepancies'] else 'Mismatch',
                    probability=f"{r['prob_yes']*100:.1f}%",status='Open · paper' if r['outcome'] is None else 'Resolved · paper') for r in rows]
                cohorts[cohort]=s
            categories=[dict(name=r[0] or 'Uncategorized',count=r[1]) for r in c.execute('SELECT e.category,count(*) FROM markets m JOIN events e USING(event_ticker) GROUP BY e.category ORDER BY count(*) DESC LIMIT 8')]
            scans=[dict(time=stamp(r['finished']),markets=r['markets'] or 0,status=r['status']) for r in c.execute('SELECT * FROM scans ORDER BY id DESC LIMIT 8')]
            errors=integrity.verify(c)+integrity.verify_checkpoints(c)
            counts={t:c.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('markets','snapshots','alerts','hash_chain','research','research_queue')}
            classified=sum(v['forecasts_total'] for v in cohorts.values())
            unknown=c.execute('SELECT count(*) FROM forecasts').fetchone()[0]-classified
            return dict(asof=stamp(last['finished']),last=last,cohorts=cohorts,categories=categories,scans=scans,counts=counts,integrity_errors=errors,unknown_forecasts=unknown)

    def markets(self,search='',offset=0):
        with db.readonly(self.path) as c:
            if search:
                # Parameterized literal LIKE search; never interpret %/_ as query operators.
                term='%'+search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
                rows=c.execute("""SELECT m.*, e.category FROM markets m JOIN events e USING(event_ticker)
                    WHERE m.ticker LIKE ? ESCAPE '\\' OR m.title LIKE ? ESCAPE '\\'
                    ORDER BY m.ticker LIMIT 51 OFFSET ?""",(term,term,offset)).fetchall()
            else:
                rows=c.execute("""SELECT m.*,e.category FROM markets m JOIN events e USING(event_ticker)
                    WHERE m.ticker IN (SELECT ticker FROM forecasts) ORDER BY m.ticker LIMIT 51 OFFSET ?""",(offset,)).fetchall()
            output=[]
            for r in rows[:50]:
                s=c.execute('SELECT * FROM snapshots WHERE ticker=? ORDER BY ts DESC LIMIT 1',(r['ticker'],)).fetchone()
                output.append(dict(ticker=r['ticker'],title=r['title'] or r['ticker'],category=r['category'] or 'Other',bid=cents(s['yes_bid']) if s else '—',ask=cents(s['yes_ask']) if s else '—',volume=f"{s['volume_24h']:,.0f}" if s and s['volume_24h'] is not None else '—',asof=stamp(s['ts']) if s else 'No quote snapshot',status=r['status']))
            return dict(rows=output,more=len(rows)>50,offset=offset)

    def detail(self,ticker):
        with db.readonly(self.path) as c:
            m=c.execute('SELECT * FROM markets WHERE ticker=?',(ticker,)).fetchone()
            if m is None:return {}
            rows=list(c.execute('SELECT ts,yes_bid,yes_ask FROM snapshots WHERE ticker=? ORDER BY ts',(ticker,)))
            points=[dict(t=r['ts'],bid=r['yes_bid'],ask=r['yes_ask']) for r in rows if r['yes_bid'] is not None and r['yes_ask'] is not None]
            # Limit rendering points while retaining both endpoints.
            if len(points)>400: points=points[::max(1,len(points)//399)][:399]+[points[-1]]
            research=[dict(r) for r in c.execute('SELECT * FROM research WHERE ticker=? ORDER BY id',(ticker,))]
            for r in research:
                r['source_list']=json.loads(r['sources'] or '[]')
            return dict(ticker=ticker,title=m['title'],rules=m['rules_primary'] or 'No settlement rules in snapshot',secondary=m['rules_secondary'] or '',close=m['close_time'] or 'Unavailable',points=points,research=research,
                        span=f"{stamp(points[0]['t'])} — {stamp(points[-1]['t'])}" if points else 'No two-sided quote history')
