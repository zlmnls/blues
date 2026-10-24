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


if __name__ == '__main__':
    unittest.main()
