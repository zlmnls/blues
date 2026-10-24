import unittest
import numpy as np
import pandas as pd
from indicators import technical, weekly_bars
from signals import daily_signals, weekly_signals, combine, cloud_signals, cci_divergence


def bars(n=300, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    dates = pd.bdate_range('2025-01-01', periods=n)
    return pd.DataFrame({'date': dates, 'open': close + rng.normal(0, .3, n), 'close': close,
                         'high': close + abs(rng.normal(.8, .3, n)), 'low': close - abs(rng.normal(.8, .3, n)),
                         'volume': rng.integers(1000, 5000, n).astype(float), 'amount': 0.0})


class SignalTests(unittest.TestCase):
    def test_bollinger_uses_sample_std_like_tongdaxin(self):
        f = bars(60)
        t = technical(f)
        exp = f['close'].rolling(20).mean() + 2 * f['close'].rolling(20).std(ddof=1)
        pd.testing.assert_series_equal(t['boll_upper'], exp, check_names=False)
        t0 = technical(f, boll_ddof=0)
        self.assertLess(t0['boll_upper'].iloc[-1], t['boll_upper'].iloc[-1])

    def test_cloud_is_spans_from_22_bars_ago(self):
        t = technical(bars(120))
        pd.testing.assert_series_equal(t['cloud_a'], t['cloud_a_lead'].shift(22), check_names=False)
        self.assertTrue((t['cloud_top'].dropna() >= t['cloud_bottom'].dropna()).all())

    def test_signals_do_not_change_when_future_rows_append(self):
        f = bars(300)
        full = daily_signals(technical(f)).iloc[:250].reset_index(drop=True)
        part = daily_signals(technical(f.iloc[:250])).reset_index(drop=True)
        pd.testing.assert_frame_equal(full, part)

    def test_weekly_partial_week_is_flagged_and_skipped(self):
        f = bars(300)
        f = f[f['date'] <= '2026-02-04']          # ends on a Wednesday
        w = weekly_bars(f)
        self.assertFalse(w['week_complete'].iloc[-1])
        self.assertTrue(w['week_complete'].iloc[:-1].all())
        d = combine(daily_signals(technical(f)), weekly_signals(technical(w)))
        # the partial week's bias must not be attached to its own days
        self.assertEqual(len(d), len(f))

    def test_cloud_exit_fail_touch_and_close_below(self):
        n = 6
        t = pd.DataFrame({'close': [90, 91, 92, 99, 96, 95], 'high': [91, 92, 93, 101, 97, 96],
                          'low': [89, 90, 91, 97, 95, 94], 'cloud_top': [100.0] * n, 'cloud_bottom': [95.0] * n})
        s = cloud_signals(t, prior_lookback=5)
        self.assertTrue(s['cloud_exit_fail'].iloc[3])
        self.assertFalse(s['cloud_exit_fail'].iloc[:3].any())

    def test_cci_top_divergence_is_marked_on_confirmation_bar(self):
        high = [10, 11, 12, 15, 12, 11, 10, 11, 12, 16, 12, 11, 10]
        cci = [0, 50, 100, 200, 100, 50, 0, 30, 60, 120, 60, 30, 0]
        t = pd.DataFrame({'high': high, 'low': [h - 1 for h in high], 'cci_14': cci})
        s = cci_divergence(t, left=3, right=2)
        self.assertEqual(list(np.where(s['cci_top_divergence'])[0]), [11])


if __name__ == '__main__':
    unittest.main()
