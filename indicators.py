"""Transparent indicator definitions. Undefined original algorithms stay undefined."""
import math
import numpy as np
import pandas as pd

KLINE_COLUMNS = ['date','open','close','high','low','volume','amount','amplitude','pct_change','price_change','turnover_pct']


def safe_ratio(numerator, denominator):
    if denominator is None or not math.isfinite(float(denominator)) or float(denominator) <= 0:
        return None
    if numerator is None or not math.isfinite(float(numerator)):
        return None
    return float(numerator)/float(denominator)


def number(value):
    try:
        result = float(str(value).replace(',', '').replace('%', ''))
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def parse_klines(rows):
    if not rows:
        return pd.DataFrame(columns=KLINE_COLUMNS)
    values = [r.split(',') if isinstance(r, str) else r for r in rows]
    if any(len(r) != len(KLINE_COLUMNS) for r in values):
        raise ValueError('Unexpected daily-bar schema')
    df = pd.DataFrame(values, columns=KLINE_COLUMNS)
    df['date'] = pd.to_datetime(df['date'], errors='raise')
    if df['date'].duplicated().any():
        raise ValueError('Duplicate trading dates')
    df = df.sort_values('date').reset_index(drop=True)
    for col in KLINE_COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def market_metrics(frame):
    """Percentages use active securities with valid returns and positive amount.

    Volume TRIN gets a separate complete-case count; no mixing volume units.
    Unchanged securities remain in red-rate denominator and amount-share totals.
    """
    valid = frame['pct_change'].notna() & frame['close'].gt(0) & frame['amount'].gt(0)
    f = frame.loc[valid]
    up = f['pct_change'].gt(1e-9)
    down = f['pct_change'].lt(-1e-9)
    u, d, n = int(up.sum()), int(down.sum()), len(f)
    flat = n-u-d
    au, ad, total = f.loc[up,'amount'].sum(), f.loc[down,'amount'].sum(), f['amount'].sum()
    ad_ratio = safe_ratio(u,d)
    amount_ratio = safe_ratio(au,ad)
    v = f.loc[f['volume'].notna() & f['volume'].gt(0)]
    vu, vd = v['pct_change'].gt(1e-9), v['pct_change'].lt(-1e-9)
    volume_ratio = safe_ratio(v.loc[vu,'volume'].sum(),v.loc[vd,'volume'].sum())
    volume_ad_ratio = safe_ratio(int(vu.sum()),int(vd.sum()))
    turnover = f.loc[f['turnover_pct'].notna() & f['turnover_pct'].ge(0)]
    result = {'source_rows': len(frame), 'active_count': n, 'up_count':u, 'down_count':d,
        'flat_count':flat, 'excluded_count':len(frame)-n, 'net_advances':u-d,
        'up_pct_all': None if not n else 100*u/n,
        'up_pct_directional': None if not u+d else 100*u/(u+d),
        'down_pct_all': None if not n else 100*d/n,
        'ad_ratio':ad_ratio, 'amount_ratio':amount_ratio,
        'trin_amount':safe_ratio(ad_ratio,amount_ratio),
        'trin_volume':safe_ratio(volume_ad_ratio,volume_ratio),
        'volume_valid_count':len(v), 'up_amount':float(au),'down_amount':float(ad),'total_amount':float(total),
        'up_amount_pct':safe_ratio(100*au,total),'down_amount_pct':safe_ratio(100*ad,total),
        'turnover_valid_count':len(turnover), 'turnover_gt5_count':int(turnover['turnover_pct'].gt(5).sum()),
        'turnover_gt5_pct':None if not len(turnover) else 100*turnover['turnover_pct'].gt(5).mean()}
    for period in [20,60]:
        column = f'above_ma{period}'
        if column in f:
            usable = f[column].dropna()
            result[f'candidate_p{period}_eligible'] = len(usable)
            result[f'candidate_p{period}_pct'] = None if not len(usable) else 100*float(usable.mean())
    return result


def snapshot_metrics(rows):
    df = pd.DataFrame(rows).rename(columns={'f2':'close','f3':'pct_change','f5':'volume','f6':'amount','f8':'turnover_pct'})
    for c in ['close','pct_change','volume','amount','turnover_pct']:
        df[c] = pd.to_numeric(df[c],errors='coerce')
    df['volume'] = df['volume']*100  # normalized snapshot container uses lots
    return market_metrics(df)


def market_history(histories, quote_rows):
    quotes = {r['f12']:r for r in quote_rows}
    frames, quality = [], []
    for h in histories:
        f = parse_klines(h['klines'])
        if f.empty:
            quality.append({'code':h['security']['code'],'rows':0,'turnover_calibrated':False})
            continue
        code = h['security']['code']
        quote = quotes.get(code,{})
        latest_t = f.iloc[-1]['turnover_pct']
        quoted_t = number(quote.get('f8'))
        turnover_ok = bool(quoted_t is not None and quoted_t>=0.3 and pd.notna(latest_t)
                           and abs(float(latest_t)-quoted_t)<=max(0.03,0.06*quoted_t))
        if not turnover_ok:
            f['turnover_pct'] = np.nan
        for period in [20,60]:
            ma = f['close'].rolling(period,min_periods=period).mean()
            above = (f['close']>ma).astype(float)
            f[f'above_ma{period}'] = above.where(ma.notna())
        f['code'] = code
        frames.append(f)
        quality.append({'code':code,'rows':len(f),'turnover_calibrated':turnover_ok,
                        'volume_factor':h.get('volume_factor'),'volume_factor_method':h.get('volume_factor_method')})
    if not frames:
        raise ValueError('No security histories available')
    panel = pd.concat(frames,ignore_index=True)
    records = []
    for date, f in panel.groupby('date',sort=True):
        records.append({'date':date,**market_metrics(f)})
    out = pd.DataFrame(records).sort_values('date').reset_index(drop=True)
    out['candidate_adl'] = out['net_advances'].cumsum()
    net = out['net_advances'].astype(float)
    out['candidate_mcl_raw_19_39'] = net.ewm(span=19,adjust=False,min_periods=39).mean()-net.ewm(span=39,adjust=False,min_periods=39).mean()
    out['candidate_mcl_display'] = 50+0.1*out['candidate_mcl_raw_19_39']
    rana = net/(out['up_count']+out['down_count']).replace(0,np.nan)*1000
    out['candidate_mcl_ratio_adjusted'] = rana.ewm(span=19,adjust=False,min_periods=39).mean()-rana.ewm(span=39,adjust=False,min_periods=39).mean()
    # No invented composite score. P20/P60 and MCL names are hypotheses only.
    return out, quality


def technical(frame):
    f = frame.copy()
    c,v,h,l = f['close'],f['volume'],f['high'],f['low']
    weighted = c*v
    short = weighted.rolling(12,min_periods=12).sum()/v.rolling(12,min_periods=12).sum().replace(0,np.nan)
    long = weighted.rolling(26,min_periods=26).sum()/v.rolling(26,min_periods=26).sum().replace(0,np.nan)
    f['vw_dif'] = short-long
    f['vw_dea'] = f['vw_dif'].ewm(span=9,adjust=False,min_periods=9).mean()
    f['vw_histogram'] = 2*(f['vw_dif']-f['vw_dea'])
    f['conversion_7'] = (h.rolling(7).max()+l.rolling(7).min())/2
    f['base_22'] = (h.rolling(22).max()+l.rolling(22).min())/2
    # Shift=22 is an explicit assumption; only past values feed today's cloud.
    f['cloud_a_assumed_shift22'] = ((f['conversion_7']+f['base_22'])/2).shift(22)
    f['cloud_b_assumed_shift22'] = ((h.rolling(44).max()+l.rolling(44).min())/2).shift(22)
    f['boll_middle_20'] = c.rolling(20).mean()
    std = c.rolling(20).std(ddof=0)
    f['boll_upper_assumed_2sigma'] = f['boll_middle_20']+2*std
    f['boll_lower_assumed_2sigma'] = f['boll_middle_20']-2*std
    tp = (h+l+c)/3
    tp_mean = tp.rolling(14).mean()
    mad = tp.rolling(14).apply(lambda a: np.abs(a-a.mean()).mean(),raw=True)
    f['cci_14'] = (tp-tp_mean)/(0.015*mad.replace(0,np.nan))
    return f


def weekly_bars(daily):
    f = daily.set_index('date').sort_index()
    agg = {'open':'first','high':'max','low':'min','close':'last','volume':'sum','amount':'sum'}
    # A group is labelled with the last observed session, never a future Friday.
    result = f.resample('W-FRI').agg(agg)
    dates = f.index.to_series().resample('W-FRI').max()
    result['date'] = dates
    result = result.dropna(subset=['open','close','date']).reset_index(drop=True)
    return result[['date','open','close','high','low','volume','amount']]


def pcr_history(days):
    records, issues = [], []
    for day in days:
        rows = day['rows']
        if not rows:
            issues.append({'date':day['date'],'exchange':day['exchange'],'reason':'empty response; not replaced with zero'})
            continue
        normalized = []
        for row in rows:
            if day['exchange']=='SSE':
                if str(row.get('TRADE_DATE',''))[:10] != day['date']:
                    raise ValueError('SSE option date mismatch')
                code,name = row['SECURITY_CODE'],row['SECURITY_ABBR']
                calls,puts = number(row['CALL_VOLUME']),number(row['PUT_VOLUME'])
                coi,poi = number(row['LEAVES_CALL_QTY']),number(row['LEAVES_PUT_QTY'])
            else:
                code,name = row['bddm'],row['bdmc']
                calls,puts = number(row['rccjl']),number(row['rpcjl'])
                coi,poi = number(row['wpcrchys']),number(row['wpcrphys'])
            if any(x is None or x<0 for x in [calls,puts,coi,poi]):
                raise ValueError('Invalid option contract counts')
            rec = {'date':day['date'],'exchange':day['exchange'],'underlying':code,'name':name,
                   'call_volume':calls,'put_volume':puts,'call_oi':coi,'put_oi':poi,
                   'pcr_volume':safe_ratio(puts,calls),'pcr_oi':safe_ratio(poi,coi)}
            normalized.append(rec)
            records.append(rec)
        totals = {k:sum(r[k] for r in normalized) for k in ['call_volume','put_volume','call_oi','put_oi']}
        records.append({'date':day['date'],'exchange':day['exchange'],'underlying':'ALL','name':'exchange aggregate',
                       **totals,'pcr_volume':safe_ratio(totals['put_volume'],totals['call_volume']),
                       'pcr_oi':safe_ratio(totals['put_oi'],totals['call_oi'])})
    f = pd.DataFrame(records)
    if f.empty:
        return f,issues
    totals = f.loc[f['underlying'].eq('ALL')].groupby('date')[['call_volume','put_volume','call_oi','put_oi']].sum()
    coverage = f.loc[f['underlying'].eq('ALL')].groupby('date')['exchange'].nunique()
    combined = []
    for date,row in totals.iterrows():
        if coverage.loc[date]!=2:
            issues.append({'date':date,'reason':'Combined PCR withheld: one exchange missing'})
            continue
        combined.append({'date':date,'exchange':'SSE+SZSE','underlying':'ALL','name':'ETF options aggregate, excludes CFFEX',
            **row.to_dict(),'pcr_volume':safe_ratio(row['put_volume'],row['call_volume']),
            'pcr_oi':safe_ratio(row['put_oi'],row['call_oi'])})
    return pd.concat([f,pd.DataFrame(combined)],ignore_index=True).sort_values(['date','exchange','underlying']),issues


def shareholder_monthly(rows,as_of):
    f = pd.DataFrame(rows)
    for col in ['NOTICE_DATE','START_DATE','END_DATE']:
        f[col] = pd.to_datetime(f[col],errors='coerce')
    f = f.loc[f['NOTICE_DATE'].notna() & f['NOTICE_DATE'].le(pd.Timestamp(as_of))].copy()
    keys = ['SECURITY_CODE','HOLDER_NAME','NOTICE_DATE','START_DATE','END_DATE','DIRECTION','CHANGE_NUM']
    before = len(f)
    f = f.drop_duplicates(subset=keys)
    f['shares_10k'] = pd.to_numeric(f['CHANGE_NUM'],errors='coerce').abs()
    f['month'] = f['NOTICE_DATE'].dt.to_period('M').astype(str)
    records = []
    for month,g in f.groupby('month',sort=True):
        buys,sells = g.loc[g['DIRECTION'].eq('增持')],g.loc[g['DIRECTION'].eq('减持')]
        b,s = buys['shares_10k'].sum(),sells['shares_10k'].sum()
        records.append({'month':month,'increase_events':len(buys),'decrease_events':len(sells),
            'increase_shares_10k':float(b),'decrease_shares_10k':float(s),'net_shares_10k':float(b-s),
            'candidate_sell_buy_shares_pct':safe_ratio(100*s,b),
            'candidate_sell_buy_events_pct':safe_ratio(100*len(sells),len(buys)),
            'candidate_decrease_event_share_pct':safe_ratio(100*len(sells),len(sells)+len(buys))})
    return pd.DataFrame(records),{'exact_duplicates_removed':before-len(f),'records_used':len(f),
        'time_basis':'announcement date, not effective interval date',
        'limitation':'Not merged with executives. Cumulative/overlapping disclosure intervals may remain; these are ratio candidates, not an audited net-flow series.'}


def equity_bond_candidate(pe_frame, treasury_frame, window=252, band_sigma=2):
    """Explicit hypothesis: earnings yield 100/PE minus 10y yield in percent."""
    f = pe_frame[['date','pe_ttm']].merge(treasury_frame[['date','yield_10y_pct']],on='date',how='inner').sort_values('date')
    f['spread_pct_points'] = 100/f['pe_ttm'].where(f['pe_ttm'].gt(0))-f['yield_10y_pct']
    f['rolling_mean'] = f['spread_pct_points'].rolling(window,min_periods=window).mean()
    f['rolling_std'] = f['spread_pct_points'].rolling(window,min_periods=window).std(ddof=0)
    f['upper'] = f['rolling_mean']+band_sigma*f['rolling_std']
    f['lower'] = f['rolling_mean']-band_sigma*f['rolling_std']
    f['z_score'] = (f['spread_pct_points']-f['rolling_mean'])/f['rolling_std'].replace(0,np.nan)
    return f
