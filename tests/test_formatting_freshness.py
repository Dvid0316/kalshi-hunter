"""Formatting, freshness model, paths guard."""
from decimal import Decimal as D
import pytest

from desktop import formatting as fm, freshness as fr, paths


@pytest.mark.parametrize('value,want', [(0.35, '35.0¢'), (0.093, '9.3¢'), (0.0935, '9.35¢'), (0.3 + 0.0, '30.0¢'),
                                         (None, '—'), (float('nan'), '—'), ('0.5', '50.0¢'), (D('0.655'), '65.5¢'), (True, '—')])
def test_cents(value, want):
    assert fm.cents(value) == want


def test_float_artifacts_never_reach_the_screen():
    assert fm.cents(0.1 + 0.2) == '30.0¢'                       # 0.30000000000000004
    assert fm.money(0.1 + 0.2) == '$0.30'


@pytest.mark.parametrize('value,want', [(None, 'Unavailable'), (D('0'), '$0.00'), (D('-3.2'), '-$3.20'), (D('1234.567'), '$1,234.57'),
                                         (D('0.005'), '$0.00'), (D('0.015'), '$0.02'), ('nan', 'Unavailable'), (D('Infinity'), 'Unavailable')])
def test_money(value, want):
    assert fm.money(value) == want


def test_money_plus_sign_and_zero_is_a_real_zero():
    assert fm.money(D('5'), plus=True) == '+$5.00' and fm.money(D('0'), plus=True) == '$0.00'
    assert fm.money(D('0')) != fm.UNAVAILABLE


def test_other_helpers():
    assert fm.percent(0.592) == '59.2%' and fm.percent(None) == '—' and fm.percent(0.5, 0) == '50%'
    assert fm.spread_cents(0.65, 0.66) == '1.0¢' and fm.spread_cents(None, 0.66) == '—'
    assert fm.quantity(D('10')) == '10' and fm.quantity(D('2.50')) == '2.5' and fm.quantity(None) == '—'
    assert [fm.age_text(x) for x in (5, 120, 4000, 8000, 100000, 200000, None, -1)] == ['5 s', '2 min', '66 min', '2 h 13 min', '27 h 46 min', '2 d 7 h', 'unknown age', 'unknown age']
    assert fm.stamp(None) == 'Unavailable' and 'CDT' in fm.stamp(1792602962)


# ---------------------------------------------------------------- freshness
def test_archive_is_never_live_no_matter_how_recent():
    f = fr.classify(1000.0, 1001.0, 'archive')
    assert f.level is fr.Level.ARCHIVED and f.warn and 'ARCHIVED' in f.label
    assert not fr.quote_executable(1000.0, 1001.0, 'archive')
    assert not fr.mark_usable(1000.0, 1001.0, 'archive')


@pytest.mark.parametrize('age,level', [(10, fr.Level.LIVE), (fr.FRESH_MAX_S, fr.Level.LIVE), (fr.FRESH_MAX_S + 1, fr.Level.DELAYED),
                                        (fr.STALE_MAX_S, fr.Level.DELAYED), (fr.STALE_MAX_S + 1, fr.Level.STALE)])
def test_feed_levels(age, level):
    f = fr.classify(1000.0, 1000.0 + age, 'feed')
    assert f.level is level and f.warn == (level is not fr.Level.LIVE)


def test_missing_timestamp_is_unavailable_and_clock_skew_is_clamped():
    assert fr.classify(None, 5.0).level is fr.Level.UNAVAILABLE
    assert fr.classify(2000.0, 1000.0, 'feed').age_s == 0.0         # timestamp in the future
    assert not fr.mark_usable(2000.0, 1000.0, 'feed') and not fr.quote_executable(2000.0, 1000.0, 'feed')


def test_mark_and_executable_windows():
    assert fr.quote_executable(1000.0, 1060.0, 'feed') and not fr.quote_executable(1000.0, 1061.0, 'feed')
    assert fr.mark_usable(1000.0, 1300.0, 'feed') and not fr.mark_usable(1000.0, 1301.0, 'feed')


def test_connection_state_machine_and_backoff():
    S, E = fr.ConnectionState, fr.Event
    s = S.NOT_CONFIGURED
    for ev, want in [(E.CONFIGURE, S.CONNECTING), (E.CONNECT_FAIL, S.RECONNECTING), (E.CONNECT_FAIL, S.RECONNECTING),
                     (E.CONNECT_OK, S.CONNECTED), (E.TIMEOUT, S.STALE), (E.DATA, S.CONNECTED), (E.DISCONNECT, S.RECONNECTING),
                     (E.FATAL, S.ERROR), (E.CONNECT_OK, S.ERROR), (E.RESET, S.NOT_CONFIGURED)]:
        s = fr.next_state(s, ev)
        assert s is want, (ev, s)
    assert fr.next_state(S.NOT_CONFIGURED, E.DATA) is S.NOT_CONFIGURED       # data without a feed changes nothing
    assert [fr.backoff_seconds(n) for n in (0, 1, 2, 3, 8, 20)] == [0.0, 2.0, 4.0, 8.0, 256.0, 300.0]
    assert set(fr.STATE_TEXT) == set(S)


# ---------------------------------------------------------------- write guard
def test_writes_to_evidence_are_refused(tmp_path):
    for p in (paths.ROOT / 'data/kalshi.db', paths.ROOT / 'data/new.db', paths.ROOT / 'research/x.md',
              paths.ROOT / 'strategies/flb_v1.json', paths.ROOT / 'data/kalshi.db-wal', paths.ROOT / 'research/archive/a'):
        with pytest.raises(paths.EvidenceWriteError):
            paths.assert_writable_path(p)
    assert paths.assert_writable_path(tmp_path / 'ok.db') == (tmp_path / 'ok.db').resolve()
    assert paths.assert_writable_path(paths.var_dir() / 'cache/x.db')


def test_var_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv('KH_VAR_DIR', str(tmp_path / 'v'))
    assert paths.var_dir() == tmp_path / 'v' and paths.account_db_path() == tmp_path / 'v/account.db'
