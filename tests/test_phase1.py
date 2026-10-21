import json, sqlite3, subprocess, sys, time
from decimal import Decimal
from pathlib import Path
import pytest
from kh import accounting, db, perf, validation, integrity, research, backtest
from kh.cohorts import forecast_rows

@pytest.mark.parametrize('side,outcome,want', [('yes',1,'4.82'),('yes',0,'-5.18'),('no',0,'4.82'),('no',1,'-5.18')])
def test_four_settlements(side,outcome,want):
    assert accounting.settlement_pnl(side,10,.5,.18,outcome)==Decimal(want)

def test_fractional_precision():
    assert accounting.settlement_pnl('no','2.5','.093','.06',0)==Decimal('2.2075')

@pytest.mark.parametrize('args', [('bad',1,.5,0,1),('yes',0,.5,0,1),('yes',1,1.1,0,1),('yes',1,.5,-1,1),('yes',1,.5,0,2),('yes',1,float('nan'),0,1)])
def test_invalid_accounting(args):
    with pytest.raises(ValueError): accounting.settlement_pnl(*args)

@pytest.fixture
def ledger(tmp_path):
    c=db.connect(tmp_path/'paper.db')
    for i,note in enumerate(['demo','prereg_flb_v1','preregXbad','unknown'],1):
        c.execute("INSERT INTO forecasts(id,ts,ticker,side,prob_yes,exec_price,qty,fee,note) VALUES(?,1,?,'yes',.8,.5,10,.18,?)",(i,f'T{i}',note))
    c.commit()
    yield c
    c.close()

class Settled:
    def market(self,ticker): return {'result':'yes'}

def test_real_resolution_path_and_separation(ledger):
    assert perf.resolve(Settled(),ledger)==4
    assert perf.resolve(Settled(),ledger)==0
    for cohort in ('research','strategy'):
        s=perf.stats(ledger,cohort)
        assert s['forecasts_total']==s['resolved']==1
        assert s['net_pnl']==4.82 and s['accounting_discrepancies']==[]
    assert ledger.execute('SELECT outcome FROM forecasts WHERE id=1').fetchone()[0] is None
    assert validation.track_b(ledger)['n_forecasts']==1
    assert validation.track_c_flb(ledger)['n_resolved']==1

def test_unresolved_and_mismatch(ledger):
    assert perf.stats(ledger)['net_pnl'] is None
    ledger.execute('INSERT INTO resolutions(ts,forecast_id,outcome,pnl) VALUES(2,1,1,999)');ledger.commit()
    s=perf.stats(ledger)
    assert s['accounting_discrepancies']==[1] and s['net_pnl'] is None

def test_verify_does_not_seal_or_write(ledger):
    assert integrity.verify(ledger)==['hash_chain missing']
    integrity.seal(ledger)
    ledger.execute("INSERT INTO research(ts,ticker) VALUES(1,'X')");ledger.commit()
    ledger.execute('PRAGMA query_only=ON')
    assert any('unsealed' in s for s in integrity.verify(ledger))

def test_backtest_label_purge():
    rows=[dict(pred_ts=i,close_ts=i+.1,label_available_ts=i+.2) for i in range(10)]
    rows[0]['label_available_ts']=7
    rows[1]['label_available_ts']=None
    train,test=backtest.split(rows)
    assert len(train)==4 and all(r['label_available_ts']<test[0]['pred_ts'] for r in train)

def test_unknown_cli_cannot_start():
    p=subprocess.run([sys.executable,'run.py','loop'],capture_output=True,text=True)
    assert p.returncode==2 and 'invalid choice' in p.stderr

@pytest.mark.parametrize('fault', ['depth','expiry','status','rules','drift','worst_ev','fee','missing_fee','empty_fee','stale_fee','secondary','age','network','none'])
def test_alert_full_revalidation(ledger,fault):
    now=time.time()
    ledger.execute("INSERT INTO events VALUES('E','S','Event','Politics',0,1)")
    ledger.execute("INSERT INTO markets(ticker,event_ticker) VALUES('T1','E')")
    if fault!='missing_fee': ledger.execute("INSERT INTO kv VALUES('series',?)",(json.dumps({'S':{} if fault=='empty_fee' else {'m':20 if fault=='fee' else 1}}),))
    ledger.execute("INSERT INTO kv VALUES('series_ts',?)",(str(now-99999 if fault=='stale_fee' else now),))
    payload={'rules_secondary':'original secondary','prob':[.7,.75,.8], 'rules':'settles yes if measured value exceeds threshold'}
    if fault=='worst_ev':payload['prob']=[.54,.6,.7]
    ledger.execute("INSERT INTO alerts(ts,ticker,side,exec_price,payload,approved_by_auditor) VALUES(?,'T1','yes',.5,?,1)",(now-1000 if fault=='age' else now,json.dumps(payload)));ledger.commit()
    class Fake:
        def market(self,t):
            if fault=='network':raise RuntimeError('offline')
            return dict(status='closed' if fault=='status' else 'active', close_time=None if fault=='expiry' else '2099-01-01T00:00:00Z',rules_primary='changed' if fault=='rules' else payload['rules'],rules_secondary='changed' if fault=='secondary' else 'original secondary')
        def orderbook(self,*args):
            return {'orderbook_fp':{'yes_dollars':[['.49','100']], 'no_dollars':[[('.45' if fault=='drift' else '.48' if fault=='worst_ev' else '.50'), '1' if fault=='depth' else '100']]}}
    assert bool(research.pending_alerts(Fake(),ledger,now=now))==(fault=='none')
    assert ledger.execute('SELECT approved_by_auditor FROM alerts').fetchone()[0]==1
