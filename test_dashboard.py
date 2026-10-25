import unittest

import numpy as np
import pandas as pd

import build_dashboard as B
import dashboard_sources as S
from indicators import technical
from signals import daily_signals


def bars(closes, start='2025-01-01'):
    c = np.asarray(closes, dtype=float)
    f = pd.DataFrame({'date': pd.bdate_range(start, periods=len(c)), 'open': c, 'high': c + 1, 'low': c - 1,
                      'close': c, 'volume': 1e6})
    f['amount'] = f['close'] * f['volume']
    return f


def ds(x):
    return pd.Timestamp(x).strftime('%Y-%m-%d')


class DashboardTests(unittest.TestCase):
    def test_level_block_distance_and_cross(self):
        t = bars([100, 102, 99, 98, 101])
        out = B.level_block(t, [{'price': 100, 'label': 'x'}], 2)[0]
        assert out['distance'] == 1 and out['distance_pct'] == 1.0
        assert out['side'] == '在点位上方'
        assert out['crossed_today'] is True
        assert out['last_cross']['date'] == ds(t['date'].iloc[-1]) and out['last_cross']['direction'] == '向上穿过'


    def test_valid_break_rules(self):
        close = pd.Series([101, 99.5, 99.4, 99.3])
        line = pd.Series([100.0] * 4)
        assert B.valid_break(close, line, 'down')['valid'] is True          # three closes below
        assert B.valid_break(pd.Series([101, 98.9]), pd.Series([100.0, 100.0]), 'down')['valid'] is True  # >1%
        assert B.valid_break(pd.Series([101, 99.5]), pd.Series([100.0, 100.0]), 'down')['valid'] is False


    def test_cloud_block_matches_state_and_next_cloud(self):
        rng = np.random.default_rng(1)
        t = technical(bars(100 + np.cumsum(rng.normal(0, 1, 300))))
        sig = daily_signals(t)
        c = B.cloud_block(t, sig, 2)
        top, bot = t['cloud_top'].iloc[-1], t['cloud_bottom'].iloc[-1]
        assert c['cloud_top'] == round(top, 2) and c['cloud_bottom'] == round(bot, 2)
        a, b = t['cloud_a_lead'].iloc[-22], t['cloud_b_lead'].iloc[-22]
        assert c['next_cloud_top'] == round(max(a, b), 2)
        assert {ln['price'] for ln in c['lines']} == {round(top, 2), round(bot, 2)}


    def test_completed_gold_bars_drops_open_session(self):
        f = bars([1, 2, 3], start='2026-10-21')  # Wed, Thu, Fri
        # 2026-10-23 10:00 New York = 14:00 UTC: Friday's session is still trading
        out = S.completed_gold_bars(f, pd.Timestamp('2026-10-23T14:00Z'))
        assert out['date'].iloc[-1] == pd.Timestamp('2026-10-22')
        out = S.completed_gold_bars(f, pd.Timestamp('2026-10-24T08:00Z'))
        assert out['date'].iloc[-1] == pd.Timestamp('2026-10-23')

    def test_szse_pcr_row_parses_overview_columns(self):
        rows = [{'bddm': '159915', 'rccjl': '2,526,987', 'rpcjl': '2,061,769', 'wpcrchys': '1,613,339', 'wpcrphys': '735,081'},
                {'bddm': '159919', 'rccjl': '150,991', 'rpcjl': '141,707', 'wpcrchys': '172,146', 'wpcrphys': '93,709'}]
        r = B.szse_pcr_row('2026-10-23', rows)
        assert r['call_volume'] == 2526987 + 150991 and r['put_volume'] == 2061769 + 141707
        assert abs(r['pcr_volume'] - (2061769 + 141707) / (2526987 + 150991)) < 1e-12
        assert abs(r['pcr_oi'] - (735081 + 93709) / (1613339 + 172146)) < 1e-12
        with self.assertRaises(RuntimeError):
            B.szse_pcr_row('2026-10-24', [])  # non-trading day: empty overview

    def test_combine_pcr_sums_before_dividing_and_keeps_common_dates(self):
        sse = pd.DataFrame({'date': ['2026-10-22', '2026-10-23'], 'call_volume': [100, 200], 'put_volume': [50, 300],
                            'call_oi': [10, 10], 'put_oi': [5, 5]})
        szse = pd.DataFrame({'date': ['2026-10-23', '2026-10-26'], 'call_volume': [800, 1], 'put_volume': [100, 1],
                             'call_oi': [30, 1], 'put_oi': [15, 1]})
        c = B.combine_pcr(sse, szse)
        assert c['date'].tolist() == ['2026-10-23']
        assert c['pcr_volume'].iloc[0] == (300 + 100) / (200 + 800)  # not the mean of 1.5 and 0.125
        assert c['pcr_oi'].iloc[0] == 20 / 40
        assert c['pcr_volume_sse'].iloc[0] == 1.5 and c['pcr_volume_szse'].iloc[0] == 0.125

    def test_fund_flow_summary_runs_and_sums(self):
        main = [5e9, -1e9, -2e9, 3e9, -4e9, -6e9, -8e9]
        f = pd.DataFrame({'date': pd.bdate_range('2026-10-13', periods=7), 'main': main, 'small': [0.0] * 7,
                          'medium': [0.0] * 7, 'large': [0.0] * 7, 'super': main, 'main_pct': [-1.0] * 7})
        s = B.fund_flow_summary(f)
        assert s['main_100m'] == -80 and s['run_days'] == 3 and s['run_side'] == '流出'
        assert abs(s['sum5_100m'] - (-2 + 3 - 4 - 6 - 8) * 10) < 1e-9
        assert s['outflow_days_20'] == 5

    def test_unavailable_items_follow_this_run(self):
        ok = {'pcr': {'status': 'ok', 'scope': 'both'}, 'fund_flow': {'status': 'ok'}}
        names = [u['name'] for u in B.unavailable_items(ok)]
        assert '深交所期权 PCR' not in names and '全市场资金流向' not in names
        bad = {'pcr': {'status': 'ok', 'scope': 'sse', 'szse_error': 'HTTP 403'}, 'fund_flow': {'status': '无数据', 'reason': 'closed'}}
        un = {u['name']: u['reason'] for u in B.unavailable_items(bad)}
        assert 'HTTP 403' in un['深交所期权 PCR'] and 'closed' in un['全市场资金流向']

    def test_eastmoney_gold_column_order(self):
        orig = S.http_json
        S.http_json = lambda *a, **k: {'data': {'klines': ['2026-10-23,4042.2,4010.0,4050.2,3989.1,173280']}}
        try:
            f = S.bars_eastmoney_gold()
        finally:
            S.http_json = orig
        r = f.iloc[-1]
        assert (r['open'], r['high'], r['low'], r['close'], r['volume']) == (4042.2, 4050.2, 3989.1, 4010.0, 173280)


if __name__ == '__main__':
    unittest.main()
