"""Signal rules from episode 21 of 《金融宝藏》 (weekly direction, daily timing).

Every rule only reads bars up to the bar it marks, so a signal never changes when
later bars are appended. Pivot-based rules (CCI divergence) are marked on the bar
that confirms the pivot, `right` bars after the high itself.

Usage:
    from indicators import technical, weekly_bars
    from signals import daily_signals, weekly_signals, combine
    d = technical(daily); w = technical(weekly_bars(daily))
    table = combine(daily_signals(d), weekly_signals(w))
"""
import numpy as np
import pandas as pd


def _flag(x):
    return x.fillna(False).astype(bool)


def _first_in_cluster(flags, cooldown):
    """Keep a flag only if the same flag did not fire in the previous `cooldown` bars.
    Causal: looks back only. Stops one touch-and-hold episode from firing every day."""
    if cooldown <= 0:
        return flags
    out = flags.to_numpy().copy()
    last = -10**9
    for i, v in enumerate(out):
        if v:
            if i - last <= cooldown:
                out[i] = False
            else:
                last = i
    return pd.Series(out, index=flags.index)


def cloud_signals(t, touch_tol=0.001, max_bars_out=3, prior_lookback=30, cooldown=3):
    """Ichimoku rules from the video.

    cloud_state: 1 close above cloud, 0 inside, -1 below (NaN while the cloud is warming up).
    enter_cloud_from_above (入云): previous close above the cloud, this close at or below its top.
    cloud_exit_fail (出云失败, bearish): price had been below the cloud within
      `prior_lookback` bars, then either
        a) the high reaches the cloud top (within touch_tol) but the close stays under it, or
        b) closes above the top for 1..max_bars_out bars, then closes back under it.
    cloud_support_hold (mirror, bullish): price had been above the cloud, the low reaches the
      cloud bottom but the close stays above it, or a short break below is recovered.
    """
    f = pd.DataFrame(index=t.index)
    c, h, l = t['close'], t['high'], t['low']
    top, bot = t['cloud_top'], t['cloud_bottom']
    ready = top.notna() & bot.notna()
    state = pd.Series(np.select([c > top, c < bot], [1, -1], 0), index=t.index).astype(float).where(ready)
    f['cloud_state'] = state
    prev = state.shift(1)
    f['enter_cloud_from_above'] = _flag((prev == 1) & (state <= 0))
    f['break_below_cloud'] = _flag((prev >= 0) & (state == -1))
    f['break_above_cloud'] = _flag((prev <= 0) & (state == 1))

    was_below = _flag((state == -1).astype(float).rolling(prior_lookback, min_periods=1).max().shift(1) == 1)
    was_above = _flag((state == 1).astype(float).rolling(prior_lookback, min_periods=1).max().shift(1) == 1)

    above_top = _flag(c > top)
    below_bot = _flag(c < bot)
    run_above = above_top.groupby((~above_top).cumsum()).cumsum()
    run_below = below_bot.groupby((~below_bot).cumsum()).cumsum()

    touch_fail = (c.shift(1) < top.shift(1)) & (h >= top * (1 - touch_tol)) & (c < top)
    false_break = (~above_top) & ready & run_above.shift(1).between(1, max_bars_out)
    f['cloud_exit_fail'] = _first_in_cluster(_flag((touch_fail | false_break) & was_below), cooldown)

    hold = (c.shift(1) > bot.shift(1)) & (l <= bot * (1 + touch_tol)) & (c > bot)
    false_drop = (~below_bot) & ready & run_below.shift(1).between(1, max_bars_out)
    f['cloud_support_hold'] = _first_in_cluster(_flag((hold | false_drop) & was_above), cooldown)
    # "三出": how many failed exits in the last 60 bars
    f['cloud_exit_fail_count_60'] = f['cloud_exit_fail'].astype(int).rolling(60, min_periods=1).sum()
    return f


def vwmacd_signals(t):
    """VW-MACD: fast (DIF) and slow (DEA) lines vs the zero axis and each other."""
    f = pd.DataFrame(index=t.index)
    dif, dea = t['vw_dif'], t['vw_dea']
    both_below = _flag((dif < 0) & (dea < 0))
    both_above = _flag((dif > 0) & (dea > 0))
    f['vw_both_below_zero'] = both_below
    f['vw_both_above_zero'] = both_above
    # 快慢线跌破零轴: first bar on which both lines are below zero
    f['vw_zero_break_down'] = both_below & ~both_below.shift(1, fill_value=False)
    f['vw_zero_break_up'] = both_above & ~both_above.shift(1, fill_value=False)
    f['vw_dead_cross'] = _flag((dif < dea) & (dif.shift(1) >= dea.shift(1)))
    f['vw_golden_cross'] = _flag((dif > dea) & (dif.shift(1) <= dea.shift(1)))
    return f


def boll_signals(t, tol=0.01, cooldown=5):
    """Bollinger as a sub-chart: a test of the upper band that does not close above it is
    the video's "在上轨顶部、没有突破上轨 → 失能". tol widens 'touch' to within 1%."""
    f = pd.DataFrame(index=t.index)
    c, h, l = t['close'], t['high'], t['low']
    ub, lb, mid = t['boll_upper'], t['boll_lower'], t['boll_middle_20']
    f['boll_upper_reject'] = _first_in_cluster(_flag((h >= ub * (1 - tol)) & (c < ub)), cooldown)
    f['boll_lower_reject'] = _first_in_cluster(_flag((l <= lb * (1 + tol)) & (c > lb)), cooldown)
    f['boll_close_above_upper'] = _flag(c > ub)
    f['boll_close_below_middle'] = _flag((c < mid) & (c.shift(1) >= mid.shift(1)))
    f['boll_pct_b'] = (c - lb) / (ub - lb).replace(0, np.nan)
    return f


def _pivots(series, left, right, kind):
    """Boolean pivot flags placed on the CONFIRMATION bar (pivot index + right)."""
    win = left + right + 1
    roll = series.rolling(win, min_periods=win)
    ext = roll.max() if kind == 'high' else roll.min()
    centre = series.shift(right)
    return _flag(centre == ext)


def cci_divergence(t, left=3, right=2, eq_tol=0.01, min_cci_drop=10.0, max_gap=60):
    """CCI top/bottom divergence by joining confirmed swing highs/lows.

    Top divergence: the newer price swing high is at least the older one (within eq_tol),
    but the CCI peak around it (+-right bars) is lower by min_cci_drop or more.
    Marked on the confirmation bar, so it lags the actual high by `right` bars.
    """
    h, l, cci = t['high'], t['low'], t['cci_14']
    n = len(t)
    top = np.zeros(n, bool)
    bottom = np.zeros(n, bool)
    conf_hi = _pivots(h, left, right, 'high').to_numpy()
    conf_lo = _pivots(l, left, right, 'low').to_numpy()
    cci_peak = cci.rolling(2 * right + 1, min_periods=1).max().to_numpy()   # window ends at confirm bar
    cci_trough = cci.rolling(2 * right + 1, min_periods=1).min().to_numpy()
    hv, lv = h.to_numpy(), l.to_numpy()
    last_hi = last_lo = None
    for i in range(n):
        if conf_hi[i]:
            p = i - right
            cur = (p, hv[p], cci_peak[i])
            if last_hi is not None and p - last_hi[0] <= max_gap and np.isfinite(cur[2]) and np.isfinite(last_hi[2]):
                if cur[1] >= last_hi[1] * (1 - eq_tol) and cur[2] <= last_hi[2] - min_cci_drop:
                    top[i] = True
            last_hi = cur
        if conf_lo[i]:
            p = i - right
            cur = (p, lv[p], cci_trough[i])
            if last_lo is not None and p - last_lo[0] <= max_gap and np.isfinite(cur[2]) and np.isfinite(last_lo[2]):
                if cur[1] <= last_lo[1] * (1 + eq_tol) and cur[2] >= last_lo[2] + min_cci_drop:
                    bottom[i] = True
            last_lo = cur
    return pd.DataFrame({'cci_top_divergence': top, 'cci_bottom_divergence': bottom}, index=t.index)


def _all_signals(t, **kw):
    parts = [t[['date', 'close']], cloud_signals(t), vwmacd_signals(t), boll_signals(t),
             cci_divergence(t, **kw)]
    return pd.concat(parts, axis=1)


def daily_signals(t):
    return _all_signals(t, left=3, right=2)


def weekly_signals(t):
    s = _all_signals(t, left=2, right=1)
    if 'week_complete' in t:
        s['week_complete'] = t['week_complete'].values
    # Weekly direction (周线定方向). -1: close in/below cloud and VW-MACD DIF below zero.
    # +1: close above cloud and both VW-MACD lines above zero. 0 otherwise.
    bear = (s['cloud_state'] <= 0) & (t['vw_dif'] < 0)
    bull = (s['cloud_state'] == 1) & s['vw_both_above_zero']
    s['weekly_bias'] = np.select([bear, bull], [-1.0, 1.0], 0.0)
    s.loc[s['cloud_state'].isna() | t['vw_dif'].isna(), 'weekly_bias'] = np.nan
    return s


def combine(daily_sig, weekly_sig, completed_weeks_only=True, recent=5):
    """Attach the latest weekly bias to each daily bar and score the daily triggers.

    completed_weeks_only=True drops a partial last week, so live runs and back-tests use
    the same information (last finished week). The weekly bar of week W is dated its last
    session, so an as-of merge never hands a daily bar a week that has not closed yet.
    """
    w = weekly_sig.copy()
    if completed_weeks_only and 'week_complete' in w:
        w = w[w['week_complete']]
    w = w[['date', 'weekly_bias', 'cloud_state', 'vw_both_below_zero', 'boll_upper_reject', 'cci_top_divergence']]
    w = w.rename(columns={c: 'w_' + c for c in w.columns if c != 'date'})
    d = pd.merge_asof(daily_sig.sort_values('date'), w.sort_values('date'), on='date', direction='backward')
    recent_any = lambda col: d[col].astype(float).rolling(recent, min_periods=1).max().fillna(0).astype(bool)
    d['bear_confirmations'] = (recent_any('cloud_exit_fail').astype(int) + d['vw_both_below_zero'].astype(int)
                               + recent_any('boll_upper_reject').astype(int)
                               + d['cci_top_divergence'].astype(float).rolling(10, min_periods=1).max().fillna(0).astype(int))
    d['bull_confirmations'] = (recent_any('cloud_support_hold').astype(int) + d['vw_both_above_zero'].astype(int)
                               + recent_any('boll_lower_reject').astype(int)
                               + d['cci_bottom_divergence'].astype(float).rolling(10, min_periods=1).max().fillna(0).astype(int))
    # The 9/22 pattern: weekly bearish, a failed exit from the daily cloud, and both daily
    # VW-MACD lines below zero. Other confirmations are counted, not required.
    d['short_risk_signal'] = (d['w_weekly_bias'] == -1) & d['cloud_exit_fail'] & d['vw_both_below_zero']
    d['long_setup_signal'] = (d['w_weekly_bias'] == 1) & d['cloud_support_hold'] & d['vw_both_above_zero']
    return d


if __name__ == '__main__':
    import argparse, sys
    from indicators import technical, weekly_bars
    ap = argparse.ArgumentParser(description='Print recent signals for a CSV (date,open,high,low,close,volume) or a yfinance ticker')
    ap.add_argument('source', help='CSV path, or a yfinance ticker such as 000001.SS or GC=F')
    ap.add_argument('--since', default=None)
    a = ap.parse_args()
    if a.source.endswith('.csv'):
        raw = pd.read_csv(a.source, parse_dates=['date'])
    else:
        import yfinance as yf
        raw = yf.download(a.source, period='5y', auto_adjust=False, progress=False)
        raw.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in raw.columns]
        raw = raw.reset_index().rename(columns={'Date': 'date'})
    raw['amount'] = raw.get('amount', raw['close'] * raw['volume'])
    raw = raw.dropna(subset=['open', 'high', 'low', 'close']).reset_index(drop=True)
    d = technical(raw)
    w = technical(weekly_bars(raw))
    out = combine(daily_signals(d), weekly_signals(w))
    if a.since:
        out = out[out['date'] >= a.since]
    keys = ['cloud_exit_fail', 'cloud_support_hold', 'vw_zero_break_down', 'vw_zero_break_up', 'boll_upper_reject',
            'boll_lower_reject', 'cci_top_divergence', 'cci_bottom_divergence', 'short_risk_signal', 'long_setup_signal']
    hits = out[out[keys].any(axis=1)]
    cols = ['date', 'close', 'w_weekly_bias', 'cloud_state'] + keys + ['bear_confirmations', 'bull_confirmations']
    pd.set_option('display.width', 250)
    print(hits[cols].to_string(index=False))
    sys.exit(0)
