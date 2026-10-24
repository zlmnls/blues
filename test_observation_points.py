import math
import unittest
import numpy as np
import pandas as pd
from indicators import equity_bond_candidate
from observation_points import (rolling_band, band_events, equity_bond_bottom_signal, pcr_spike,
    disclosed_holdings_change, holdings_as_of, volume_context, equal_weight_pe, valuation_zone,
    market_cap_to_gdp, gdp_ttm_from_quarters, futures_basis, bs_price, greeks, implied_vol,
    long_put_pnl, bottom_checklist)


class BandTests(unittest.TestCase):
    def test_band_is_causal_and_uses_requested_ddof(self):
        s = pd.Series(np.arange(30, dtype=float) ** 1.5)
        b1 = rolling_band(s, 10, 2, ddof=1)
        b0 = rolling_band(s, 10, 2, ddof=0)
        self.assertAlmostEqual(b1['upper'].iloc[9], s[:10].mean() + 2 * s[:10].std(ddof=1))
        self.assertLess(b0['upper'].iloc[-1], b1['upper'].iloc[-1])
        changed = s.copy(); changed.iloc[-1] = 1e6
        pd.testing.assert_series_equal(rolling_band(changed, 10)['upper'].iloc[:-1], b1['upper'].iloc[:-1])

    def test_events_touch_and_middle_cross(self):
        b = pd.DataFrame({'value': [0., 1.5, 3.0], 'middle': [1., 1., 1.], 'upper': [3., 3., 3.], 'lower': [-1., -1., -1.]})
        e = band_events(b)
        self.assertEqual(list(e['cross_middle_up']), [False, True, False])
        self.assertEqual(list(e['touch_upper']), [False, False, True])
        self.assertEqual(list(e['zone']), ['lower_half', 'upper_half', 'above_upper'])

    def test_equity_bond_ddof_option_keeps_old_default(self):
        d = pd.date_range('2025-01-31', periods=14, freq='ME')
        pe = pd.DataFrame({'date': d, 'pe_ttm': np.linspace(12, 15, 14)})
        ty = pd.DataFrame({'date': d, 'yield_10y_pct': np.linspace(1.6, 1.9, 14)})
        old = equity_bond_candidate(pe, ty, window=12)
        exp = old['spread_pct_points'].rolling(12).std(ddof=0)
        pd.testing.assert_series_equal(old['rolling_std'], exp, check_names=False)
        new = equity_bond_candidate(pe, ty, window=12, band_ddof=1)
        self.assertGreater(new['rolling_std'].iloc[-1], old['rolling_std'].iloc[-1])

    def test_bottom_signal_separates_touch_from_midway(self):
        vals = [0.0] * 11 + [0.2, -0.2] * 5 + [0.15, 5.0]
        f = pd.DataFrame({'date': pd.date_range('2024-01-01', periods=len(vals)), 'spread_pct_points': vals})
        s = equity_bond_bottom_signal(f, window=12, k=2)
        self.assertTrue(s['bottom_candidate'].iloc[-1])
        self.assertTrue(s['midway'].iloc[-2])
        self.assertFalse(s['bottom_candidate'].iloc[-2])

    def test_pcr_rising_but_not_touching(self):
        vals = [0.8, 0.9] * 15 + [0.95, 1.6]
        f = pd.DataFrame({'date': pd.date_range('2026-01-01', periods=len(vals)), 'pcr_volume': vals})
        p = pcr_spike(f, window=30)
        self.assertTrue(p['rising_toward_upper'].iloc[-2])
        self.assertTrue(p['spike'].iloc[-1])


class DisclosureTests(unittest.TestCase):
    def rows(self):
        r = [{'holder': 'HJ', 'security': f'S{i}', 'report_period': '2026Q1', 'notice_date': '2026-04-25'} for i in range(144)]
        r += [{'holder': 'HJ', 'security': f'S{i}', 'report_period': '2026Q2', 'notice_date': '2026-08-20'} for i in range(16)]
        r += [{'holder': 'HJ', 'security': 'S99', 'report_period': '2026Q2', 'notice_date': '2026-08-30'}]
        r += [{'holder': 'HJ', 'security': 'S99', 'report_period': '2026Q2', 'notice_date': '2026-08-30'}]
        return r

    def test_count_change_matches_screen_example(self):
        c = disclosed_holdings_change(self.rows())
        last = c.iloc[-1]
        self.assertEqual(last['holdings_count'], 17)
        self.assertAlmostEqual(last['count_change_pct'], 100 * (17 / 144 - 1))
        self.assertEqual(last['available_date'], pd.Timestamp('2026-08-30'))

    def test_as_of_does_not_see_unpublished_period(self):
        c = disclosed_holdings_change(self.rows())
        self.assertEqual(holdings_as_of(c, '2026-08-25')['report_period'].iloc[0], '2026Q1')
        self.assertEqual(holdings_as_of(c, '2026-08-30')['report_period'].iloc[0], '2026Q2')

    def test_volume_context_excludes_today_from_average(self):
        d = pd.bdate_range('2026-01-02', periods=30)
        v = [100.0] * 29 + [130.0]
        v[3] = 500.0
        f = volume_context(pd.DataFrame({'date': d, 'volume': v}), reference_dates=[d[3]])
        self.assertAlmostEqual(f['vs_5d_avg'].iloc[-1], 1.3)
        self.assertAlmostEqual(f['vs_ytd_max'].iloc[-1], 130 / 500)
        self.assertAlmostEqual(f[f'vs_{d[3]:%Y%m%d}'].iloc[-1], 130 / 500)

    def test_market_cap_to_gdp_uses_released_gdp_only(self):
        q = pd.DataFrame({'period_end': ['2025-06-30', '2025-09-30', '2025-12-31', '2026-03-31', '2026-06-30'],
                          'gdp_q': [30., 32., 35., 31., 33.],
                          'release_date': ['2025-07-15', '2025-10-20', '2026-01-17', '2026-04-16', '2026-07-15']})
        g = gdp_ttm_from_quarters(q)
        self.assertEqual(list(g['gdp_ttm']), [128.0, 131.0])
        cap = pd.DataFrame({'date': ['2026-04-15', '2026-04-16', '2026-07-20'], 'market_cap': [100., 100., 100.]})
        r = market_cap_to_gdp(cap, g)
        self.assertTrue(math.isnan(r['cap_to_gdp'].iloc[0]))
        self.assertAlmostEqual(r['cap_to_gdp'].iloc[1], 100 / 128)
        self.assertAlmostEqual(r['cap_to_gdp'].iloc[2], 100 / 131)


class ValuationTests(unittest.TestCase):
    def test_equal_weight_pe_methods(self):
        cs = pd.DataFrame({'pe_ttm': [10., 20., 40., -50., np.nan]})
        h, n = equal_weight_pe(cs, method='harmonic')
        self.assertEqual(n, 4)
        self.assertAlmostEqual(h, 1 / np.mean([0.1, 0.05, 0.025, -0.02]))
        self.assertEqual(equal_weight_pe(cs, method='median'), (20.0, 3))
        self.assertAlmostEqual(equal_weight_pe(cs, method='mean_pos')[0], 70 / 3)

    def test_zone_on_screen_reading(self):
        self.assertEqual(valuation_zone(13, 11.61, 14.18), 'middle')
        self.assertEqual(valuation_zone(14.18, 11.61, 14.18), 'danger')
        self.assertEqual(valuation_zone(11.0, 11.61, 14.18), 'opportunity')

    def test_basis_sign_and_annualizing(self):
        b = futures_basis([3960.], [4000.], days_to_expiry=[73])
        self.assertEqual(b['basis'].iloc[0], -40)
        self.assertAlmostEqual(b['basis_pct'].iloc[0], -1.0)
        self.assertAlmostEqual(b['annualized_pct'].iloc[0], -5.0)


class OptionTests(unittest.TestCase):
    def test_known_black_scholes_values_and_parity(self):
        c = bs_price('C', 100, 100, 1, 0.05, 0.2)
        p = bs_price('P', 100, 100, 1, 0.05, 0.2)
        self.assertAlmostEqual(c, 10.4506, places=4)
        self.assertAlmostEqual(p, 5.5735, places=4)
        self.assertAlmostEqual(c - p, 100 - 100 * math.exp(-0.05), places=10)

    def test_implied_vol_round_trip_and_bounds(self):
        p = bs_price('P', 2.9, 3.0, 60 / 365, 0.015, 0.23, 0.01)
        self.assertAlmostEqual(implied_vol('P', p, 2.9, 3.0, 60 / 365, 0.015, 0.01), 0.23, places=6)
        self.assertIsNone(implied_vol('P', 0.05, 2.9, 3.0, 60 / 365, 0.015))

    def test_greeks_match_finite_differences(self):
        args = dict(S=4.0, K=3.9, T=0.25, r=0.02, sigma=0.25, q=0.01)
        for kind in 'CP':
            g = greeks(kind, **args)
            h = 1e-4
            f = lambda **kw: bs_price(kind, **{**args, **kw})
            self.assertAlmostEqual(g['delta'], (f(S=4 + h) - f(S=4 - h)) / (2 * h), places=5)
            self.assertAlmostEqual(g['gamma'], (f(S=4 + h) - 2 * f() + f(S=4 - h)) / h ** 2, places=3)
            self.assertAlmostEqual(g['vega'], (f(sigma=.25 + h) - f(sigma=.25 - h)) / (2 * h), places=5)
            self.assertAlmostEqual(g['rho'], (f(r=.02 + h) - f(r=.02 - h)) / (2 * h), places=5)
            self.assertAlmostEqual(g['theta'], -(f(T=.25 + h) - f(T=.25 - h)) / (2 * h), places=4)

    def test_iv_crush_can_erase_right_direction(self):
        K, r = 4.0, 0.015
        entry = bs_price('P', 4.0, K, 30 / 365, r, 0.40)
        exit_ = bs_price('P', 3.92, K, 25 / 365, r, 0.18)
        res = long_put_pnl(entry, exit_, 4.0, 3.92, K, 30 / 365, 25 / 365, r)
        self.assertGreater(res['move_and_time'], 0)
        self.assertLess(res['iv_change'], 0)
        self.assertLess(res['total'], 0)
        self.assertAlmostEqual(res['total'], res['move_and_time'] + res['iv_change'])

    def test_checklist_reports_unknowns(self):
        c = bottom_checklist(holdings_recovered=False, erp_touch_upper=False, cap_gdp_zone='danger')
        self.assertEqual(c['met'], 0)
        self.assertEqual(c['known'], 3)
        self.assertEqual(c['unknown'], ['bond_position_low'])


if __name__ == '__main__':
    unittest.main()
