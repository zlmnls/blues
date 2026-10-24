"""Data observation points from the 2026-10-14..10-19 videos (21922-21925).

Every function here computes a transparent, testable candidate. The videos name
the observation points and show charts, but do not publish windows, multipliers,
universes or thresholds. Those stay parameters; nothing here claims to be the
author's exact formula.

Time rule: anything built from disclosures (holdings reports, GDP) is keyed to
the date the number became public, never to the period it describes.
"""
import math
import numpy as np
import pandas as pd


# ---------------------------------------------------------------- bands

def rolling_band(series, window, k=2.0, ddof=1, min_periods=None):
    """Mean +/- k standard deviations over a trailing window (causal).

    ddof=1 is the sample standard deviation (Tongdaxin STD). The videos do not say
    which software draws the PCR and stock-bond bands, so it is a parameter.
    """
    s = pd.Series(series, dtype=float)
    mp = window if min_periods is None else min_periods
    mean = s.rolling(window, min_periods=mp).mean()
    std = s.rolling(window, min_periods=mp).std(ddof=ddof)
    out = pd.DataFrame({'value': s, 'middle': mean, 'upper': mean + k * std, 'lower': mean - k * std})
    out['z_score'] = (s - mean) / std.replace(0, np.nan)
    return out


def band_events(band, touch_tol=0.0):
    """Where the value sits against its band and when it crosses a line.

    touch_upper: value >= upper*(1-touch_tol) on this bar.
    cross_middle_up / cross_middle_down: close-to-close crossing of the middle line.
    zone: 'above_upper', 'upper_half', 'lower_half', 'below_lower' or None.
    """
    b = band.copy()
    v, m, u, l = b['value'], b['middle'], b['upper'], b['lower']
    valid = v.notna() & m.notna() & u.notna() & l.notna()
    b['touch_upper'] = valid & v.ge(u - touch_tol * u.abs())
    b['touch_lower'] = valid & v.le(l + touch_tol * l.abs())
    prev_v, prev_m = v.shift(1), m.shift(1)
    b['cross_middle_up'] = valid & prev_v.lt(prev_m) & v.ge(m)
    b['cross_middle_down'] = valid & prev_v.gt(prev_m) & v.le(m)
    zone = np.select([v.ge(u), v.ge(m), v.gt(l), v.le(l)],
                     ['above_upper', 'upper_half', 'lower_half', 'below_lower'], default='')
    b['zone'] = pd.Series(zone, index=b.index).where(valid & (pd.Series(zone, index=b.index) != ''))
    return b


# ------------------------------------------------- stock-bond spread (21924)

def equity_bond_bottom_signal(erp_frame, window=12, k=2.0, ddof=1, touch_tol=0.0):
    """21924 04:10-04:46: spread touching the upper std band marked the Sep-2024 and
    Apr-2025 lows; crossing only the middle line was 'not yet a bottom'.

    Input: equity_bond_candidate() output (needs date, spread_pct_points).
    Output columns: bottom_candidate (touch upper), midway (crossed middle upward,
    upper not reached).
    """
    f = erp_frame[['date', 'spread_pct_points']].dropna().sort_values('date').reset_index(drop=True)
    b = band_events(rolling_band(f['spread_pct_points'], window, k, ddof), touch_tol)
    b.insert(0, 'date', f['date'])
    b['bottom_candidate'] = b['touch_upper']
    b['midway'] = b['zone'].eq('upper_half')
    return b


# --------------------------------------------------- PCR spike (21922)

def pcr_spike(pcr_frame, column='pcr_volume', window=60, k=2.0, ddof=1):
    """21922 01:58-02:47: a PCR bar jumping toward the upper band (May 13, Jun 22,
    Sep 21) was read as short-term risk. He said the Oct-16 bar had NOT reached
    the upper band yet, so 'touch_upper' and 'rising_toward_upper' are separate.

    pcr_frame: one row per date (e.g. pcr_history() rows with underlying=='ALL').
    The video does not say volume vs open-interest PCR, window or k.
    """
    f = pcr_frame[['date', column]].dropna().sort_values('date').reset_index(drop=True)
    b = band_events(rolling_band(f[column], window, k, ddof))
    b.insert(0, 'date', f['date'])
    jump = b['value'].diff()
    b['rising_toward_upper'] = jump.gt(0) & b['zone'].eq('upper_half') & ~b['touch_upper']
    b['spike'] = b['touch_upper']
    return b


# ---------------------------------------- disclosed holdings (21922, 21924)

def disclosed_holdings_change(rows, holder_col='holder', security_col='security',
                              period_col='report_period', notice_col='notice_date',
                              shares_col=None):
    """Count of distinct securities each holder discloses per report period, and the
    change versus the previous period. 21922 showed Huijin's count going from 144
    (2026 Q1 report) to 17 (2026 interim report).

    'available_date' is the latest notice date among that period's rows: the
    count is not knowable before every holding of the period has been published.
    The number of holdings is not money flow; shares are summed only if given and
    only within one holder (mixing stock shares and ETF units is the caller's job
    to avoid).
    """
    f = pd.DataFrame(rows).copy()
    f[notice_col] = pd.to_datetime(f[notice_col], errors='coerce')
    f = f.dropna(subset=[holder_col, security_col, period_col, notice_col])
    f = f.drop_duplicates(subset=[holder_col, security_col, period_col])
    agg = {'holdings_count': (security_col, 'nunique'), 'available_date': (notice_col, 'max')}
    if shares_col:
        f[shares_col] = pd.to_numeric(f[shares_col], errors='coerce')
        agg['shares_total'] = (shares_col, 'sum')
    g = f.groupby([holder_col, period_col]).agg(**agg).reset_index().sort_values([holder_col, period_col])
    g['prev_count'] = g.groupby(holder_col)['holdings_count'].shift(1)
    g['count_change'] = g['holdings_count'] - g['prev_count']
    g['count_change_pct'] = 100 * (g['holdings_count'] / g['prev_count'] - 1)
    if shares_col:
        g['shares_change'] = g['shares_total'] - g.groupby(holder_col)['shares_total'].shift(1)
    return g.reset_index(drop=True)


def holdings_as_of(changes, as_of, holder_col='holder'):
    """Latest period per holder that was public on as_of (no look-ahead)."""
    c = changes.loc[changes['available_date'].le(pd.Timestamp(as_of))]
    return c.sort_values('available_date').groupby(holder_col).tail(1).reset_index(drop=True)


# ------------------------------------------------ ETF volume context (21924)

def volume_context(frame, short=5, medium=20, reference_dates=()):
    """21924 00:46-01:23: Oct-15 300ETF volume was up versus last week/month but far
    below July and January, so 'not a volume surge'. This puts both views side by side.

    frame: date, volume (daily, one ETF). reference_dates: dates whose volume the
    bar is compared with (e.g. the July and January peaks he pointed at).
    vs_*_avg uses the PRIOR bars only, so today's bar is not in its own average.
    """
    f = frame[['date', 'volume']].copy()
    f['date'] = pd.to_datetime(f['date'])
    f = f.sort_values('date').reset_index(drop=True)
    v = f['volume'].astype(float)
    f[f'vs_{short}d_avg'] = v / v.shift(1).rolling(short, min_periods=short).mean()
    f[f'vs_{medium}d_avg'] = v / v.shift(1).rolling(medium, min_periods=medium).mean()
    year = f['date'].dt.year
    f['ytd_max_before'] = v.groupby(year).transform(lambda x: x.shift(1).cummax())
    f['vs_ytd_max'] = v / f['ytd_max_before']
    for d in reference_dates:
        d = pd.Timestamp(d)
        ref = f.loc[f['date'].eq(d), 'volume']
        name = f'vs_{d:%Y%m%d}'
        f[name] = (v / float(ref.iloc[0])).where(f['date'].gt(d)) if len(ref) else np.nan
    return f


# ---------------------------------------- equal-weight PE and zones (21922)

def equal_weight_pe(cross_section, pe_col='pe_ttm', method='harmonic'):
    """One date's market-wide equal-weight PE from per-stock PE.

    The video shows a value (PE 13 on 2026-10-16) but not the construction, so the
    method is explicit:
      harmonic  1 / mean(1/PE) over all valid stocks, losses included (earnings
                yield averaged with equal weights; robust to tiny positive E)
      median    median PE of stocks with PE > 0
      mean_pos  arithmetic mean PE of stocks with PE > 0 (sensitive to outliers)
    Returns (value, n_used).
    """
    pe = pd.to_numeric(pd.Series(cross_section[pe_col]), errors='coerce')
    pe = pe[np.isfinite(pe) & pe.ne(0)]
    if method == 'harmonic':
        ey = (1.0 / pe).mean()
        return (float(1.0 / ey) if ey > 0 else None), int(len(pe))
    pos = pe[pe.gt(0)]
    if not len(pos):
        return None, 0
    if method == 'median':
        return float(pos.median()), int(len(pos))
    if method == 'mean_pos':
        return float(pos.mean()), int(len(pos))
    raise ValueError('method must be harmonic, median or mean_pos')


def valuation_zone(value, opportunity, danger):
    """'danger' at/above the danger value, 'opportunity' at/below the opportunity value,
    else 'middle'. On 2026-10-16 the screen showed PE 13 between 11.61 and 14.18,
    i.e. 'middle' by this rule, although he called it a high-valuation zone. How he
    derives the two values is not shown, so they are inputs."""
    if value is None or not math.isfinite(value):
        return None
    if value >= danger:
        return 'danger'
    if value <= opportunity:
        return 'opportunity'
    return 'middle'


def percentile_thresholds(history, low_q=0.2, high_q=0.8):
    """A reproducible stand-in for opportunity/danger values: trailing quantiles."""
    s = pd.Series(history, dtype=float).dropna()
    return float(s.quantile(low_q)), float(s.quantile(high_q))


# ---------------------------------------------- market cap / GDP (21924)

def market_cap_to_gdp(cap_frame, gdp_frame):
    """21924 03:54-04:09: total market value / national GDP.

    cap_frame: date, market_cap (same currency unit as GDP).
    gdp_frame: release_date, gdp_ttm (nominal GDP over the trailing 4 quarters as
    published on release_date). Each cap date uses the latest GDP released on or
    before it, so revisions and release lags do not leak forward.
    """
    c = cap_frame[['date', 'market_cap']].copy()
    c['date'] = pd.to_datetime(c['date'])
    g = gdp_frame[['release_date', 'gdp_ttm']].copy()
    g['release_date'] = pd.to_datetime(g['release_date'])
    f = pd.merge_asof(c.sort_values('date'), g.sort_values('release_date'),
                      left_on='date', right_on='release_date', direction='backward')
    f['cap_to_gdp'] = f['market_cap'] / f['gdp_ttm'].where(f['gdp_ttm'].gt(0))
    return f


def gdp_ttm_from_quarters(quarters):
    """quarters: period_end, gdp_q (nominal, single quarter), release_date.
    Returns release_date, gdp_ttm once four consecutive quarters are known."""
    q = quarters.copy()
    q['period_end'] = pd.to_datetime(q['period_end'])
    q['release_date'] = pd.to_datetime(q['release_date'])
    q = q.sort_values('period_end').reset_index(drop=True)
    q['gdp_ttm'] = q['gdp_q'].rolling(4, min_periods=4).sum()
    q['release_date'] = q['release_date'].cummax()
    return q.dropna(subset=['gdp_ttm'])[['period_end', 'release_date', 'gdp_ttm']]


# ------------------------------------------------- futures basis (21922)

def futures_basis(futures_price, spot_price, days_to_expiry=None):
    """Basis = F - S (negative = discount, 贴水). basis_pct = (F/S - 1)*100.
    annualized_pct = basis_pct * 365 / days_to_expiry when days are given.
    21922 only names 升贴水; contract month and sign convention are not shown."""
    F = pd.Series(futures_price, dtype=float)
    S = pd.Series(spot_price, dtype=float)
    out = pd.DataFrame({'basis': F - S, 'basis_pct': 100 * (F / S.where(S.gt(0)) - 1)})
    if days_to_expiry is not None:
        d = pd.Series(days_to_expiry, dtype=float)
        out['annualized_pct'] = out['basis_pct'] * 365 / d.where(d.gt(0))
    return out


# ------------------------------------------ option IV and Greeks (21923, 21925)

def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _npdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs_price(kind, S, K, T, r, sigma, q=0.0):
    """Black-Scholes-Merton price of a European call ('C') or put ('P').
    SSE/SZSE ETF options and CFFEX index options are European-style.
    T in years, r and q continuous annual rates, sigma annual decimal."""
    if T <= 0 or sigma <= 0:
        fwd = S * math.exp(-q * max(T, 0)) - K * math.exp(-r * max(T, 0))
        return max(fwd, 0.0) if kind == 'C' else max(-fwd, 0.0)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if kind == 'C':
        return S * math.exp(-q * T) * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
    if kind == 'P':
        return K * math.exp(-r * T) * _ncdf(-d2) - S * math.exp(-q * T) * _ncdf(-d1)
    raise ValueError("kind must be 'C' or 'P'")


def greeks(kind, S, K, T, r, sigma, q=0.0):
    """Delta, Gamma, Vega (per 1.00 vol, divide by 100 for per vol point),
    Theta (per year, divide by 365 for per calendar day), Rho (per 1.00 rate)."""
    sq = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * sq)
    d2 = d1 - sigma * sq
    dq, dr = math.exp(-q * T), math.exp(-r * T)
    gamma = dq * _npdf(d1) / (S * sigma * sq)
    vega = S * dq * _npdf(d1) * sq
    common = -S * dq * _npdf(d1) * sigma / (2 * sq)
    if kind == 'C':
        delta = dq * _ncdf(d1)
        theta = common - r * K * dr * _ncdf(d2) + q * S * dq * _ncdf(d1)
        rho = K * T * dr * _ncdf(d2)
    elif kind == 'P':
        delta = -dq * _ncdf(-d1)
        theta = common + r * K * dr * _ncdf(-d2) - q * S * dq * _ncdf(-d1)
        rho = -K * T * dr * _ncdf(-d2)
    else:
        raise ValueError("kind must be 'C' or 'P'")
    return {'delta': delta, 'gamma': gamma, 'vega': vega, 'theta': theta, 'rho': rho}


def implied_vol(kind, price, S, K, T, r, q=0.0, lo=1e-4, hi=5.0, tol=1e-8, max_iter=200):
    """Invert bs_price by bisection. Returns None when the price is outside the
    no-arbitrage range (below intrinsic value or above the upper bound)."""
    if T <= 0 or price <= 0:
        return None
    if price < bs_price(kind, S, K, T, r, lo, q) - tol or price > bs_price(kind, S, K, T, r, hi, q) + tol:
        return None
    a, b = lo, hi
    for _ in range(max_iter):
        m = 0.5 * (a + b)
        if bs_price(kind, S, K, T, r, m, q) > price:
            b = m
        else:
            a = m
        if b - a < tol:
            break
    return 0.5 * (a + b)


def long_put_pnl(entry, exit_price, spot_entry, spot_exit, K, T_entry, T_exit, r, q=0.0):
    """Split a long put's P&L into the part from the move/time (at the entry IV) and
    the part from the IV change. 21923 04:01-04:09: buying at high IV and seeing IV
    fall can leave a right-direction trade near flat or losing; 21925 00:34-00:53:
    direction plus rising IV compounds. Prices in premium units per share."""
    iv0 = implied_vol('P', entry, spot_entry, K, T_entry, r, q)
    iv1 = implied_vol('P', exit_price, spot_exit, K, T_exit, r, q)
    if iv0 is None or iv1 is None:
        return None
    at_old_iv = bs_price('P', spot_exit, K, T_exit, r, iv0, q)
    return {'iv_entry': iv0, 'iv_exit': iv1, 'total': exit_price - entry,
            'move_and_time': at_old_iv - entry, 'iv_change': exit_price - at_old_iv}


# ------------------------------------------------- checklist (21924, 21925)

def bottom_checklist(holdings_recovered=None, bond_position_low=None, erp_touch_upper=None,
                     cap_gdp_zone=None):
    """The conditions he said were NOT met on 2026-10-16 for a bottom. Each input is
    True/False or None (unknown). No weights or minimum count were disclosed, so this
    only reports which conditions hold; it does not output a buy decision."""
    items = {
        'holdings_recovered': holdings_recovered,
        'bond_position_low': bond_position_low,
        'erp_touch_upper': erp_touch_upper,
        'cap_gdp_not_overvalued': None if cap_gdp_zone is None else cap_gdp_zone != 'danger',
    }
    known = {k: v for k, v in items.items() if v is not None}
    return {'items': items, 'met': sum(bool(v) for v in known.values()), 'known': len(known),
            'unknown': [k for k, v in items.items() if v is None]}
