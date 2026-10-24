import unittest
import numpy as np
import pandas as pd
from indicators import (market_metrics, technical, weekly_bars, pcr_history,
                        shareholder_monthly, equity_bond_candidate, safe_ratio)


class IndicatorTests(unittest.TestCase):
    def market(self):
        return pd.DataFrame({'close':[10.,11.,9.,8.], 'pct_change':[1.,2.,-1.,0.],
            'volume':[100.,100.,100.,50.], 'amount':[1000.,1000.,1000.,500.],
            'turnover_pct':[5.,5.01,np.nan,0.]})

    def test_flat_stocks_stay_in_denominator(self):
        r=market_metrics(self.market())
        self.assertEqual(r['up_pct_all'],50)
        self.assertAlmostEqual(r['up_pct_directional'],200/3)
        self.assertEqual(r['up_count']+r['down_count']+r['flat_count'],r['active_count'])

    def test_trin_neutral_when_volume_and_count_ratios_agree(self):
        r=market_metrics(self.market())
        self.assertEqual(r['trin_amount'],1)
        self.assertEqual(r['trin_volume'],1)

    def test_missing_and_suspended_not_zero_filled(self):
        f=self.market()
        f.loc[0,'amount']=0
        f.loc[1,'pct_change']=np.nan
        r=market_metrics(f)
        self.assertEqual(r['excluded_count'],2)
        self.assertIsNone(r['trin_amount'])

    def test_turnover_threshold_is_strict_and_missing_excluded(self):
        r=market_metrics(self.market())
        self.assertEqual(r['turnover_valid_count'],3)
        self.assertEqual(r['turnover_gt5_count'],1)
        self.assertAlmostEqual(r['turnover_gt5_pct'],100/3)

    def test_trin_invariant_to_consistent_unit_rescaling(self):
        f=self.market()
        a=market_metrics(f)
        f['volume']*=100
        f['amount']/=10000
        b=market_metrics(f)
        self.assertEqual(a['trin_volume'],b['trin_volume'])
        self.assertEqual(a['trin_amount'],b['trin_amount'])

    def bars(self,n=120):
        close=pd.Series(np.arange(n,dtype=float)+100)
        return pd.DataFrame({'date':pd.bdate_range('2025-01-01',periods=n),'close':close,
            'open':close-.2,'high':close+1,'low':close-1,'volume':np.arange(n,dtype=float)+1000,'amount':10000.})

    def test_vw_macd_constant_prices_zero_after_warmup(self):
        f=self.bars()
        f[['open','close','high','low']]=10.
        out=technical(f)
        np.testing.assert_allclose(out['vw_dif'].dropna(),0)
        np.testing.assert_allclose(out['vw_dea'].dropna(),0)

    def test_technical_features_do_not_change_when_future_rows_append(self):
        f=self.bars()
        before=technical(f.iloc[:90]).reset_index(drop=True)
        after=technical(f).iloc[:90].reset_index(drop=True)
        pd.testing.assert_frame_equal(before,after)

    def test_zero_volume_does_not_create_infinity(self):
        f=self.bars()
        f['volume']=0
        result=technical(f)
        self.assertTrue(result['vw_dif'].isna().all())

    def test_weekly_bar_label_is_observed_date(self):
        f=self.bars(7)
        result=weekly_bars(f)
        self.assertLessEqual(result['date'].max(),f['date'].max())
        self.assertTrue(set(result['date']).issubset(set(f['date'])))

    def option(self,code,calls,puts):
        return {'TRADE_DATE':'2026-09-21','SECURITY_CODE':code,'SECURITY_ABBR':code,
                'CALL_VOLUME':str(calls),'PUT_VOLUME':str(puts),'LEAVES_CALL_QTY':str(calls),'LEAVES_PUT_QTY':str(puts)}

    def test_pcr_aggregates_counts_not_mean_of_ratios(self):
        f,issues=pcr_history([{'date':'2026-09-21','exchange':'SSE','rows':[self.option('a',10,90),self.option('b',90,10)]}])
        self.assertEqual(f.loc[f['underlying'].eq('ALL'),'pcr_volume'].iloc[0],1)
        self.assertTrue(any('Combined PCR withheld' in x.get('reason','') for x in issues))

    def test_option_date_mismatch_fails(self):
        with self.assertRaises(ValueError):
            pcr_history([{'date':'2026-09-22','exchange':'SSE','rows':[self.option('a',10,90)]}])

    def test_future_announcement_not_visible_at_earlier_cutoff(self):
        event={'SECURITY_CODE':'000001','HOLDER_NAME':'x','NOTICE_DATE':'2026-10-24',
               'START_DATE':'2026-10-01','END_DATE':'2026-10-23','DIRECTION':'减持','CHANGE_NUM':10}
        earlier={**event,'NOTICE_DATE':'2026-10-23','DIRECTION':'增持'}
        f,quality=shareholder_monthly([event,earlier,earlier],'2026-10-23')
        self.assertEqual(f.iloc[0]['increase_events'],1)
        self.assertEqual(f.iloc[0]['decrease_events'],0)
        self.assertEqual(quality['exact_duplicates_removed'],1)

    def test_equity_bond_units_and_same_day_alignment(self):
        pe=pd.DataFrame({'date':pd.date_range('2026-01-01',periods=3),'pe_ttm':[10.,20.,0.]})
        y=pd.DataFrame({'date':pd.date_range('2026-01-02',periods=3),'yield_10y_pct':[2.,2.,2.]})
        f=equity_bond_candidate(pe,y,window=2)
        self.assertEqual(len(f),2)
        self.assertEqual(f.iloc[0]['spread_pct_points'],3)
        self.assertTrue(pd.isna(f.iloc[1]['spread_pct_points']))

    def test_zero_denominator_is_unknown(self):
        self.assertIsNone(safe_ratio(1,0))
        self.assertIsNone(safe_ratio(0,0))


if __name__=='__main__':
    unittest.main()
