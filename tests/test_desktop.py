from pathlib import Path
import os, subprocess, sys, sqlite3, socket
import pytest
from desktop.repository import Repository
from kh import db
ROOT=Path(__file__).resolve().parents[1]

def test_snapshot_repository_is_readonly_and_separated(monkeypatch):
    def deny(*args,**kwargs):raise AssertionError('Network access forbidden')
    monkeypatch.setattr(socket.socket,'connect',deny)
    r=Repository();o=r.overview()
    assert o['cohorts']['research']['forecasts_total']==3
    assert o['cohorts']['strategy']['forecasts_total']==5
    assert o['cohorts']['research']['net_pnl'] is None
    assert o['cohorts']['research']['cost']==12.29
    assert o['unknown_forecasts']==0 and not o['integrity_errors']
    assert set(x['id'] for x in o['cohorts']['research']['rows']).isdisjoint(x['id'] for x in o['cohorts']['strategy']['rows'])
    with db.readonly(r.path) as c:
        with pytest.raises(sqlite3.OperationalError):c.execute("DELETE FROM kv")

def test_search_pagination_and_detail():
    r=Repository()
    assert len(r.markets()['rows'])==8
    assert r.markets("%' OR 1=1 --")['rows']==[]
    first=r.markets('Trump');second=r.markets('Trump',50)
    assert len(first['rows'])<=50 and first['more']
    assert not set(x['ticker'] for x in first['rows']) & set(x['ticker'] for x in second['rows'])
    d=r.detail('CONTROLS-2026-D')
    assert d['points'] and d['research'] and all(p['bid']<=p['ask'] for p in d['points'])
    assert r.detail('MISSING')=={}

@pytest.mark.parametrize('args',[['--smoke'],['--interaction-test'],['--smoke','--compact']])
def test_qml_pages_and_interaction(args):
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',PYTHONDONTWRITEBYTECODE='1')
    p=subprocess.run([sys.executable,'-m','desktop.app']+args,cwd=ROOT,env=env,capture_output=True,text=True,timeout=35)
    assert p.returncode==0,p.stdout+p.stderr
    assert '"qml_warnings": []' in p.stdout
