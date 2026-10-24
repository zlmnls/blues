"""Build the GitHub Pages dashboard data: latest.json plus a dated archive copy.

Usage: python build_dashboard.py [--out dashboard] [--skip-slow]

Nothing here invents values: a source that fails is written as status '无数据' with the
reason, and the page shows that text.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import traceback

import numpy as np
import pandas as pd

import dashboard_config as C
import dashboard_sources as S
from indicators import technical, weekly_bars, market_metrics, shareholder_monthly, equity_bond_candidate
from signals import daily_signals, weekly_signals, combine
import observation_points as O

CN = S.CN
DAILY_KEEP, WEEKLY_KEEP = 180, 110


# ------------------------------------------------------------------ helpers

def rnd(x, n=2):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, n) if math.isfinite(x) else None


def ds(ts):
    return None if ts is None or pd.isna(ts) else pd.Timestamp(ts).strftime('%Y-%m-%d')


def vn(key):
    """The blogger's note for an observation point; its video citation is kept as video_source."""
    return {('video_source' if k == 'source' else k): v for k, v in C.OBS_NOTES.get(key, {}).items()}


def no_data(reason, **extra):
    return {'status': '无数据', 'reason': reason, **extra}


def guarded(name, fn, errors):
    try:
        return fn()
    except Exception as exc:
        errors.append({'item': name, 'error': f'{type(exc).__name__}: {exc}'[:400]})
        traceback.print_exc()
        return no_data(f'数据源请求失败：{type(exc).__name__}: {str(exc)[:160]}')


def last_true_date(frame, col):
    hit = frame.loc[frame[col].fillna(False).astype(bool), 'date']
    return ds(hit.iloc[-1]) if len(hit) else None


# --------------------------------------------------------------- technicals

def cloud_block(t, sig, digits):
    """Position against the Ichimoku cloud, the prices that would enter/leave it, and events."""
    last = t.iloc[-1]
    top, bot, close = float(last['cloud_top']), float(last['cloud_bottom']), float(last['close'])
    state = int(sig['cloud_state'].iloc[-1])
    # The cloud for the next bar is already known (spans are projected 22 bars ahead).
    nxt_a, nxt_b = t['cloud_a_lead'].iloc[-22], t['cloud_b_lead'].iloc[-22]
    nxt_top, nxt_bot = max(nxt_a, nxt_b), min(nxt_a, nxt_b)
    pos = {1: '云上方', 0: '云层中', -1: '云下方'}[state]
    if state == 1:
        lines = [{'label': '入云价（收盘跌到此价以下即入云）', 'price': top, 'next': nxt_top},
                 {'label': '跌出云底价（收盘低于此价即跌破云）', 'price': bot, 'next': nxt_bot}]
    elif state == 0:
        lines = [{'label': '向上出云价（收盘站上此价）', 'price': top, 'next': nxt_top},
                 {'label': '向下出云价（收盘跌破此价）', 'price': bot, 'next': nxt_bot}]
    else:
        lines = [{'label': '入云价（收盘涨到此价以上即入云）', 'price': bot, 'next': nxt_bot},
                 {'label': '向上出云价（收盘站上此价即突破云）', 'price': top, 'next': nxt_top}]
    for ln in lines:
        ln['distance_pct'] = rnd(100 * (ln['price'] / close - 1), 2)
        ln['price'], ln['next'] = rnd(ln['price'], digits), rnd(ln['next'], digits)
    prev = sig['cloud_state'].shift(1)
    st = sig['cloud_state']
    ev = pd.DataFrame({'date': sig['date'],
                       'enter_from_above': prev.eq(1) & st.le(0),
                       'enter_from_below': prev.eq(-1) & st.ge(0),
                       'exit_up': sig['break_above_cloud'],
                       'exit_down': sig['break_below_cloud'],
                       'exit_fail': sig['cloud_exit_fail']})
    names = {'enter_from_above': '从上方入云', 'enter_from_below': '从下方入云', 'exit_up': '向上出云（突破云）',
             'exit_down': '向下出云（跌破云）', 'exit_fail': '出云失败'}
    events = []
    for col, name in names.items():
        d = last_true_date(ev, col)
        if d:
            row = t.loc[t['date'].eq(pd.Timestamp(d))].iloc[0]
            events.append({'type': col, 'label': name, 'date': d, 'close': rnd(row['close'], digits),
                           'cloud_top': rnd(row['cloud_top'], digits), 'cloud_bottom': rnd(row['cloud_bottom'], digits)})
        else:
            events.append({'type': col, 'label': name, 'date': None})
    marks = []
    for col, name in names.items():
        for d in ev.loc[ev[col].fillna(False).astype(bool), 'date'].tail(12):
            marks.append({'date': ds(d), 'type': col, 'label': name})
    return {'position': pos, 'state': state, 'cloud_top': rnd(top, digits), 'cloud_bottom': rnd(bot, digits),
            'next_cloud_top': rnd(nxt_top, digits), 'next_cloud_bottom': rnd(nxt_bot, digits),
            'cloud_color': '阳云（先行 A 在上）' if last['cloud_a'] >= last['cloud_b'] else '阴云（先行 B 在上）',
            'lines': lines, 'last_events': events, 'marks': marks}


def series_block(t, sig, keep, digits):
    t = t.tail(keep)
    sig = sig.set_index('date').reindex(t['date']).reset_index()
    out = {'date': [ds(d) for d in t['date']]}
    for col in ['open', 'high', 'low', 'close', 'cloud_a', 'cloud_b', 'boll_middle_20', 'boll_upper', 'boll_lower']:
        out[col] = [rnd(v, digits) for v in t[col]]
    for col in ['vw_dif', 'vw_dea', 'vw_histogram']:
        out[col] = [rnd(v, 4) for v in t[col]]
    out['cci'] = [rnd(v, 1) for v in t['cci_14']]
    out['volume'] = [rnd(v, 0) for v in t['volume']]
    # Future cloud: the last 22 projected values (bars +1..+22).
    full_a = t['cloud_a_lead'].tail(22).tolist()
    full_b = t['cloud_b_lead'].tail(22).tolist()
    out['future_cloud_a'] = [rnd(v, digits) for v in full_a]
    out['future_cloud_b'] = [rnd(v, digits) for v in full_b]
    flags = {}
    for col in ['boll_upper_reject', 'cci_top_divergence', 'short_risk_signal', 'vw_both_below_zero']:
        if col in sig:
            flags[col] = [ds(d) for d, v in zip(sig['date'], sig[col]) if bool(v) is True]
    out['flags'] = flags
    return out


def latest_values(t, digits):
    r = t.iloc[-1]
    return {'date': ds(r['date']), 'open': rnd(r['open'], digits), 'high': rnd(r['high'], digits),
            'low': rnd(r['low'], digits), 'close': rnd(r['close'], digits),
            'change_pct': rnd(100 * (r['close'] / t['close'].iloc[-2] - 1), 2) if len(t) > 1 else None,
            'tenkan': rnd(r['conversion_7'], digits), 'kijun': rnd(r['base_22'], digits),
            'cloud_a': rnd(r['cloud_a'], digits), 'cloud_b': rnd(r['cloud_b'], digits),
            'vw_dif': rnd(r['vw_dif'], 4), 'vw_dea': rnd(r['vw_dea'], 4), 'vw_hist': rnd(r['vw_histogram'], 4),
            'boll_mid': rnd(r['boll_middle_20'], digits), 'boll_upper': rnd(r['boll_upper'], digits),
            'boll_lower': rnd(r['boll_lower'], digits), 'cci': rnd(r['cci_14'], 1)}


def rule_states(ds_, ws_, comb, inst_key):
    """The blogger's (bearish) rules: active today / last date seen."""
    lw, ld = ws_.iloc[-1], ds_.iloc[-1]
    weekly = {'w_enter_cloud': ('enter_cloud_from_above', ws_), 'w_vw_below_zero': ('vw_both_below_zero', ws_),
              'w_boll_upper_reject': ('boll_upper_reject', ws_), 'w_cci_top_div': ('cci_top_divergence', ws_)}
    daily = {'d_cloud_exit_fail': ('cloud_exit_fail', ds_), 'd_vw_below_zero': ('vw_both_below_zero', ds_),
             'd_boll_upper_reject': ('boll_upper_reject', ds_), 'd_cci_top_div': ('cci_top_divergence', ds_),
             'combo_short': ('short_risk_signal', comb)}
    out = []
    for rule in C.BLOGGER_RULES:
        col, frame = {**weekly, **daily}[rule['id']]
        series = frame[col].fillna(False).astype(bool)
        if rule['id'].endswith('below_zero'):
            # a state, not an event: report whether it holds now and when it started
            active = bool(series.iloc[-1])
            start = None
            if active:
                flip = series.ne(series.shift(1)).cumsum()
                start = ds(frame.loc[flip.eq(flip.iloc[-1]), 'date'].iloc[0])
            last = start
        else:
            active = bool(series.iloc[-1])
            last = last_true_date(frame.assign(_s=series), '_s')
        out.append({**rule, 'active': active, 'last_date': last,
                    'signal': ('卖出/看空' if active else '未触发'),
                    'applies_note': None if inst_key == 'sh000001' else '博主只对上证指数讲过这套规则，套用到本标的是延伸'})
    wb = comb['w_weekly_bias'].iloc[-1] if 'w_weekly_bias' in comb else None
    w_bias = None if wb is None or pd.isna(wb) else int(wb)
    return out, w_bias


def level_block(t, levels, digits):
    """Distance to each level, which side the close is on, and the last close-to-close crossing."""
    close = t['close']
    c = float(close.iloc[-1])
    out = []
    for lv in levels:
        p = float(lv['price'])
        side = np.sign(close - p)
        changed = side.ne(side.shift(1)) & side.shift(1).notna() & side.ne(0)
        crosses = t.loc[changed, ['date', 'close']]
        last_cross = None
        if len(crosses):
            r = crosses.iloc[-1]
            last_cross = {'date': ds(r['date']), 'direction': '向上穿过' if r['close'] > p else '向下穿过'}
        today_cross = bool(changed.iloc[-1])
        touched = bool(t['low'].iloc[-1] <= p <= t['high'].iloc[-1])
        out.append({**lv, 'price': rnd(p, digits), 'distance': rnd(c - p, digits),
                    'distance_pct': rnd(100 * (c / p - 1), 2),
                    'side': '在点位上方' if c > p else ('在点位下方' if c < p else '正好在点位'),
                    'crossed_today': today_cross, 'touched_today': touched, 'last_cross': last_cross})
    return out


def consecutive(series_bool):
    n = 0
    for v in reversed(list(series_bool)):
        if v:
            n += 1
        else:
            break
    return n


def valid_break(close, line, direction):
    """The plan's rule: 3 straight closes beyond the line, or a close beyond it by 1% or more."""
    if direction == 'down':
        beyond = close < line
        pct = 100 * (1 - close.iloc[-1] / line.iloc[-1])
    else:
        beyond = close > line
        pct = 100 * (close.iloc[-1] / line.iloc[-1] - 1)
    n = consecutive(beyond)
    return {'consecutive_closes_beyond': n, 'beyond_pct': rnd(pct, 2),
            'valid': bool(n >= 3 or (n >= 1 and pct >= 1.0))}


def gold_plan(t, wt, digits):
    g = C.GOLD_PLAN
    close = t['close']
    anchor = pd.Timestamp(g['anchor_date'])
    n_days = int((t['date'] > anchor).sum())
    channel = []
    # trading-day offset of each bar from the last bar on/before the anchor date
    anchor_pos = int((t['date'] <= anchor).sum()) - 1
    steps = pd.Series(np.arange(len(t)) - anchor_pos, index=t.index, dtype=float)
    for ch in g['channel']:
        line = ch['base'] + g['channel_step_per_day'] * steps
        channel.append({**ch, 'price': rnd(line.iloc[-1], digits), 'line': line})
    ma10, ma20 = close.rolling(10).mean(), close.rolling(20).mean()
    c, last = float(close.iloc[-1]), t.iloc[-1]
    ma_hi = max(float(ma10.iloc[-1]), float(ma20.iloc[-1]))
    after_fomc = last['date'] >= pd.Timestamp(g['fomc_result_date']) - pd.Timedelta(days=1)
    b1 = after_fomc and c >= ma_hi
    in_zone2 = float(last['low']) <= 3950 and c >= 3900
    body = abs(float(last['close']) - float(last['open']))
    lower_shadow = min(float(last['close']), float(last['open'])) - float(last['low'])
    stop_candle = bool(float(last['close']) > float(last['open']) or (body > 0 and lower_shadow >= 2 * body))
    wclose = wt['close']
    weekly_3900 = valid_break(wclose, pd.Series(3900.0, index=wclose.index), 'down')
    upper = next(ch for ch in channel if ch['id'] == 'ch_upper')
    mid = next(ch for ch in channel if ch['id'] == 'ch_mid')
    b3 = valid_break(close, upper['line'], 'up')
    mid_break = valid_break(close, mid['line'], 'down')
    k4000 = valid_break(close, pd.Series(4000.0, index=close.index), 'down')
    batches = [
        {'name': '第一批（1/3）', 'side': 'buy',
         'rule': '议息会议（10/29 北京时间公布）之后，日线收盘站回 MA10/MA20（10/23 测算为 4140～4160）',
         'status': '买入（已触发）' if b1 else '未触发',
         'detail': f'最新收盘 {c:.1f}；MA10 {ma10.iloc[-1]:.1f}、MA20 {ma20.iloc[-1]:.1f}，需收在 {ma_hi:.1f} 上方' + ('' if after_fomc else '；议息会议还没开完'),
         'price': rnd(ma_hi, digits)},
        {'name': '第二批（1/3）', 'side': 'buy',
         'rule': '回到 3900～3950 并出现止跌 K 线；若周线有效跌破 3900，改在 3500～3630 接',
         'status': ('候选：进入区间，需人工确认止跌 K 线' if in_zone2 else '未触发') if not weekly_3900['valid'] else '改用 3500～3630 区间',
         'detail': f'最新最低 {last["low"]:.1f}、收盘 {c:.1f}；当日 K 线' + ('有止跌迹象（收阳或长下影）' if stop_candle else '没有止跌迹象') +
                   f'；周线收盘连续 {weekly_3900["consecutive_closes_beyond"]} 周在 3900 下方',
         'price': 3925.0},
        {'name': '第三批（1/3）', 'side': 'buy',
         'rule': '有效突破通道上轨（3 个收盘在上方，或收盘高出 1% 以上）',
         'status': '买入（已触发）' if b3['valid'] else '未触发',
         'detail': f'上轨今日约 {upper["price"]}（每个交易日下移约 4 美元），收盘距上轨 {100 * (c / upper["price"] - 1):.1f}%',
         'price': upper['price']},
        {'name': '风控', 'side': 'sell',
         'rule': '周线收盘有效跌破买入所依的支撑区，先减半',
         'status': '卖出减半（已触发）' if weekly_3900['valid'] else '未触发（目前按 3900 支撑区计算，空仓时不适用）',
         'detail': f'周线最新收盘 {wclose.iloc[-1]:.1f}', 'price': 3900.0},
    ]
    levels = [{'price': ch['price'], 'label': ch['label'] + '（按每日 -4 推算）', 'kind': 'channel'} for ch in channel]
    levels += [dict(x) for x in g['fixed']]
    return {'source': g['source'], 'trading_days_since_anchor': n_days, 'batches': batches,
            'checks': {'中轨有效跌破': {**mid_break, 'line': mid['price']}, '4000 有效跌破': k4000,
                       '周线 3900 有效跌破': weekly_3900},
            'ma10': rnd(ma10.iloc[-1], digits), 'ma20': rnd(ma20.iloc[-1], digits),
            'channel_series': {ch['id']: [rnd(v, digits) for v in ch['line'].tail(DAILY_KEEP)] for ch in channel}}, levels


def instrument_block(inst, now_utc, errors):
    digits = inst['digits']
    if inst['market'] == 'gold':
        raw, source, fetch_errors = S.gold_bars(inst['yahoo'])
        daily = S.completed_gold_bars(raw, now_utc)
        source += '，只用已收完的交易日'
        notes = ['GC=F 是近月连续合约，和同花顺 GC0W 主连的换月时点可能不同，点位会有几美元差异',
                 'Yahoo 有个别日子成交量为 0（今年 4/2、7/2），这些日子在 VW-MACD 里没有权重']
    else:
        daily, source, fetch_errors = S.index_bars(inst)
        notes = ['指数成交量来自数据源的「手」，VW-MACD 只用量的相对大小，不受单位影响']
    for e in fetch_errors:
        errors.append({'item': inst['key'] + ' 行情备用源', 'error': e})
    d = technical(daily)
    wk = weekly_bars(daily)
    w = technical(wk)
    dsig, wsig = daily_signals(d), weekly_signals(w)
    comb = combine(dsig, wsig)
    rules, w_bias = rule_states(dsig, wsig, comb, inst['key'])
    levels = [dict(x, source=x.get('source')) for x in C.BLOGGER_LEVELS.get(inst['key'], [])]
    for lv in levels:
        lv['owner'] = 'blogger'
    plan = None
    if inst['market'] == 'gold':
        plan, plan_levels = gold_plan(d, w, digits)
        for lv in plan_levels:
            lv['owner'] = 'plan'
            lv['source'] = C.GOLD_PLAN['source']
        levels += plan_levels
    week_complete = bool(wk['week_complete'].iloc[-1]) if 'week_complete' in wk else None
    blk = {
        'key': inst['key'], 'name': inst['name'], 'source': source, 'notes': notes,
        'daily': {'latest': latest_values(d, digits), 'cloud': cloud_block(d, dsig, digits),
                  'series': series_block(d, comb, DAILY_KEEP, digits)},
        'weekly': {'latest': latest_values(w, digits), 'cloud': cloud_block(w, wsig, digits),
                   'series': series_block(w, wsig, WEEKLY_KEEP, digits),
                   'last_week_complete': week_complete},
        'weekly_bias': {1: '偏多', -1: '偏空', 0: '中性'}.get(w_bias, None),
        'rules': rules,
        'buy_rule_note': C.BUY_RULE_NOTE,
        'levels': level_block(d, levels, digits) if levels else [],
        'levels_note': None if levels else '博主未给出本标的的点位',
        'blogger_dates': C.BLOGGER_DATES.get(inst['key'], []),
        'gold_plan': plan,
    }
    if plan:
        blk['daily']['series']['plan_channel'] = plan.pop('channel_series')
    return blk, d


# ------------------------------------------------------- observation points

def third_friday(y, m):
    d = date(y, m, 15)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def obs_breadth_and_valuation(as_of, hist):
    rows, meta = S.sina_snapshot()
    f = pd.DataFrame(rows)
    frame = pd.DataFrame({'pct_change': pd.to_numeric(f['changepercent'], errors='coerce'),
                          'close': pd.to_numeric(f['trade'], errors='coerce'),
                          'amount': pd.to_numeric(f['amount'], errors='coerce'),
                          'volume': pd.to_numeric(f['volume'], errors='coerce'),
                          'turnover_pct': pd.to_numeric(f['turnoverratio'], errors='coerce')})
    m = market_metrics(frame)
    pe = pd.to_numeric(f['per'], errors='coerce')
    active = frame['close'].gt(0)
    med, n_m = O.equal_weight_pe(pd.DataFrame({'pe_ttm': pe[active]}), method='median')
    cap_100m = float(pd.to_numeric(f['mktcap'], errors='coerce')[active].sum()) / 1e4  # 万元 -> 亿元
    ticktime = f['ticktime'].dropna().max() if 'ticktime' in f else None
    breadth = {'status': 'ok', 'date': as_of, 'source': '新浪财经全 A 股快照',
               'up': m['up_count'], 'down': m['down_count'], 'flat': m['flat_count'], 'active': m['active_count'],
               'net_advances': m['net_advances'], 'up_pct': rnd(m['up_pct_all'], 1),
               'amount_ratio': rnd(m['amount_ratio'], 2), 'ad_ratio': rnd(m['ad_ratio'], 2),
               'trin_amount': rnd(m['trin_amount'], 2), 'trin_volume': rnd(m['trin_volume'], 2),
               'turnover_gt5_pct': rnd(m['turnover_gt5_pct'], 2), 'total_amount_100m': rnd(m['total_amount'] / 1e8, 0),
               'snapshot': {**meta, 'last_tick': ticktime},
               'note': '阿姆氏指标 TRIN =（上涨家数/下跌家数）÷（上涨成交额/下跌成交额），大于 1 表示资金偏向下跌股。换手率>5% 占比用当日所有在交易的股票，没有按历史换手筛掉任何股票',
               **vn('breadth')}
    # MCL from the archive of net advances (needs 39 trading days of archive)
    h = hist[['date', 'net_advances']].dropna() if 'net_advances' in hist else pd.DataFrame()
    if len(h) >= 39:
        net = h['net_advances'].astype(float)
        mcl = net.ewm(span=19, adjust=False).mean() - net.ewm(span=39, adjust=False).mean()
        breadth['mcl_candidate'] = rnd(mcl.iloc[-1], 1)
    else:
        breadth['mcl_candidate'] = None
        breadth['mcl_note'] = f'麦克莱兰指标（候选写法 EMA19−EMA39 净上涨家数）需要 39 个交易日的存档，目前 {len(h)} 天'
    eqpe = {'status': 'ok' if med else '无数据', 'date': as_of,
            'source': '全市场中位数：新浪财经快照 per 字段；沪深300 市盈率：中证指数公司',
            'median_positive': rnd(med, 2), 'n_median': n_m, **vn('equal_pe')}
    return breadth, eqpe, cap_100m


def obs_cap_gdp(as_of, cap_100m):
    if cap_100m is None:
        return no_data('全 A 股快照没拿到，算不出总市值', **vn('cap_gdp'))
    q = S.gdp_quarters()
    by = {}
    for r in q:
        y, mth = int(r['report_date'][:4]), int(r['report_date'][5:7])
        by[(y, mth)] = (r['gdp_cum_100m'], r['label'])
    latest = q[0]
    y, mth = int(latest['report_date'][:4]), int(latest['report_date'][5:7])
    # Eastmoney dates the cumulative quarters as YYYY-03/06/09/12-01
    if mth == 12:
        ttm, basis = latest['gdp_cum_100m'], latest['label']
    else:
        prev_full = by.get((y - 1, 12))
        prev_same = by.get((y - 1, mth))
        if not prev_full or not prev_same:
            return no_data('GDP 季度数据不全，算不出滚动四季度', **vn('cap_gdp'))
        ttm = latest['gdp_cum_100m'] + prev_full[0] - prev_same[0]
        basis = f'{latest["label"]} + {y - 1}年第4季度'
    return {'status': 'ok', 'date': as_of, 'value_pct': rnd(100 * cap_100m / ttm, 1),
            'market_cap_100m': rnd(cap_100m, 0), 'gdp_ttm_100m': rnd(ttm, 0), 'gdp_basis': basis,
            'source': '总市值：新浪全 A 股快照 mktcap 合计；GDP：东方财富数据中心（国家统计局累计值）',
            'note': '市值不含北交所以外的境外上市公司；分母是最近四个季度的名义 GDP', **vn('cap_gdp')}


def obs_equity_bond(as_of):
    start = (pd.Timestamp(as_of) - pd.Timedelta(days=760)).strftime('%Y-%m-%d')
    pe = S.csindex_pe('000300', start, as_of)
    ty = S.treasury(start)
    f = equity_bond_candidate(pe, ty, window=250, band_sigma=2, band_ddof=1)
    b = O.equity_bond_bottom_signal(f, window=250, k=2.0, ddof=1)
    last, lb = f.iloc[-1], b.iloc[-1]
    hist = f.tail(250)
    return {'status': 'ok', 'date': ds(last['date']), 'spread': rnd(last['spread_pct_points'], 2),
            'pe_ttm': rnd(last['pe_ttm'], 2), 'yield_10y': rnd(last['yield_10y_pct'], 4),
            'upper': rnd(lb['upper'], 2), 'middle': rnd(lb['middle'], 2), 'lower': rnd(lb['lower'], 2),
            'zone': {'above_upper': '上轨上方', 'upper_half': '中轨与上轨之间', 'lower_half': '中轨与下轨之间', 'below_lower': '下轨下方'}.get(lb['zone']),
            'touch_upper': bool(lb['touch_upper']), 'last_touch_upper': last_true_date(b, 'touch_upper'),
            'signal': '潜在底部证据（博主未说买入）' if bool(lb['touch_upper']) else '未触及上轨',
            'history': {'date': [ds(x) for x in hist['date']], 'spread': [rnd(x, 3) for x in hist['spread_pct_points']],
                        'upper': [rnd(x, 3) for x in hist['upper']], 'lower': [rnd(x, 3) for x in hist['lower']],
                        'middle': [rnd(x, 3) for x in hist['rolling_mean']]},
            'source': '沪深300 市盈率：中证指数公司；10 年期国债收益率：东方财富数据中心',
            'note': '利差 = 100/PE − 10 年国债收益率（百分点）；带宽用 250 个交易日、±2 倍样本标准差。博主用的指数、窗口和倍数没公开',
            **vn('equity_bond')}, ty


def obs_pcr(sse_dates, hist_path):
    """SSE ETF option PCR (volume). History is kept in a CSV and only missing days are fetched."""
    hist_path = Path(hist_path)
    old = pd.read_csv(hist_path, dtype={'date': str}) if hist_path.exists() else pd.DataFrame(columns=['date'])
    have = set(old['date'])
    want = [d for d in sse_dates[-90:] if d not in have]
    new, errs = [], []

    def one(d):
        rows = S.sse_option_day(d)
        num = lambda v: float(str(v).replace(',', '') or 0)
        cv = sum(num(r['CALL_VOLUME']) for r in rows)
        pv = sum(num(r['PUT_VOLUME']) for r in rows)
        coi = sum(num(r['LEAVES_CALL_QTY']) for r in rows)
        poi = sum(num(r['LEAVES_PUT_QTY']) for r in rows)
        if not rows or cv <= 0:
            raise RuntimeError('empty')
        return {'date': d, 'call_volume': cv, 'put_volume': pv, 'call_oi': coi, 'put_oi': poi,
                'pcr_volume': pv / cv, 'pcr_oi': poi / coi if coi else None, 'underlyings': len(rows)}

    with ThreadPoolExecutor(4) as ex:
        futs = {d: ex.submit(one, d) for d in want}
        for d, fu in futs.items():
            try:
                new.append(fu.result())
            except Exception as exc:
                errs.append(f'{d}: {exc}')
    f = pd.concat([old, pd.DataFrame(new)], ignore_index=True) if new else old
    f = f.drop_duplicates('date', keep='last').sort_values('date').reset_index(drop=True)
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    f.to_csv(hist_path, index=False)
    if len(f) < 60:
        return no_data(f'上交所 PCR 只拿到 {len(f)} 天，带宽需要 60 天', fetch_errors=errs[:5], **vn('pcr'))
    f['date'] = pd.to_datetime(f['date'])
    b = O.pcr_spike(f, 'pcr_volume', window=60, k=2.0, ddof=1)
    lb = b.iloc[-1]
    tail = b.tail(90)
    sig = '风险提示（看空）：触及上轨' if bool(lb['touch_upper']) else ('接近上轨，还没碰到' if bool(lb['rising_toward_upper']) else '未触及上轨')
    return {'status': 'ok', 'date': ds(lb['date']), 'pcr_volume': rnd(lb['value'], 3), 'upper': rnd(lb['upper'], 3),
            'middle': rnd(lb['middle'], 3), 'lower': rnd(lb['lower'], 3), 'pcr_oi': rnd(f['pcr_oi'].iloc[-1], 3),
            'touch_upper': bool(lb['touch_upper']), 'last_touch_upper': last_true_date(b, 'touch_upper'), 'signal': sig,
            'history': {'date': [ds(x) for x in tail['date']], 'value': [rnd(x, 3) for x in tail['value']],
                        'upper': [rnd(x, 3) for x in tail['upper']], 'middle': [rnd(x, 3) for x in tail['middle']]},
            'fetch_errors': errs[:5],
            'source': '上交所股票期权每日统计（全部 ETF 期权合计）',
            'note': 'PCR = 认沽成交量 / 认购成交量；带宽 60 个交易日、±2 倍样本标准差。深交所期权数据在海外服务器上请求被拒（403），所以只含上交所',
            **vn('pcr')}


def obs_etf_volume():
    f = S.bars_tencent('sh510300', start='2025-01-01')
    v = O.volume_context(f[['date', 'volume']])
    last = v.iloc[-1]
    year = f['date'].dt.year.iloc[-1]
    ytd = f.loc[f['date'].dt.year.eq(year)]
    peak = ytd.loc[ytd['volume'].idxmax()]
    tail = f.tail(120)
    return {'status': 'ok', 'date': ds(last['date']), 'volume_lots': rnd(last['volume'], 0),
            'vs_5d_avg': rnd(last['vs_5d_avg'], 2), 'vs_20d_avg': rnd(last['vs_20d_avg'], 2),
            'vs_ytd_max': rnd(last['vs_ytd_max'], 2), 'ytd_peak_date': ds(peak['date']), 'ytd_peak_lots': rnd(peak['volume'], 0),
            'history': {'date': [ds(x) for x in tail['date']], 'volume': [rnd(x, 0) for x in tail['volume']]},
            'source': '腾讯证券日线（510300 沪深300ETF，成交量单位：手）', **vn('etf_volume')}


def obs_holdings():
    names = ['中央汇金投资有限责任公司', '中央汇金资产管理有限责任公司']
    counts = {}
    for nm in names:
        rows, _, _ = S.datacenter('RPT_F10_EH_FREEHOLDERS', f'(HOLDER_NAME="{nm}")(END_DATE>=\'2024-01-01\')', 'END_DATE')
        for r in rows:
            k = r['END_DATE'][:10]
            counts.setdefault(k, {}).setdefault(nm, set()).add(r['SECURITY_CODE'])
    periods = sorted(k for k in counts if k[5:] in ('03-31', '06-30', '09-30', '12-31'))
    table = [{'period': p, 'huijin_invest': len(counts[p].get(names[0], ())),
              'huijin_asset_mgmt': len(counts[p].get(names[1], ())),
              'total_unique': len(set().union(*counts[p].values()))} for p in periods]
    return {'status': 'ok', 'date': periods[-1] if periods else None, 'table': table[-8:],
            'source': '东方财富数据中心 十大流通股东（RPT_F10_EH_FREEHOLDERS）',
            'note': '只统计两家汇金公司出现在十大流通股东里的股票家数。博主画面的 144→17 口径不同（可能含产品/不同披露范围），数字对不上；三季报还在披露中，最新一期会逐日变化',
            **vn('holdings')}


def obs_basis(as_of):
    fut = S.sina_futures_daily('IF0')
    spot = S.bars_tencent('sh000300', start='2025-06-01')[['date', 'close']]
    m = fut.merge(spot, on='date', suffixes=('_f', '_s')).sort_values('date')
    last = m.iloc[-1]
    d = last['date'].date()
    exp = third_friday(d.year, d.month)
    if exp < d:
        ny, nm = (d.year + (d.month == 12), d.month % 12 + 1)
        exp = third_friday(ny, nm)
    days = (exp - d).days
    b = O.futures_basis([last['close_f']], [last['close_s']], [days]).iloc[0]
    hist = m.tail(120)
    hb = O.futures_basis(hist['close_f'].values, hist['close_s'].values)
    return {'status': 'ok', 'date': ds(last['date']), 'futures_close': rnd(last['close_f'], 1), 'spot_close': rnd(last['close_s'], 2),
            'basis': rnd(b['basis'], 2), 'basis_pct': rnd(b['basis_pct'], 3), 'annualized_pct': rnd(b['annualized_pct'], 2),
            'days_to_expiry': days, 'state': '贴水' if b['basis'] < 0 else '升水',
            'history': {'date': [ds(x) for x in hist['date']], 'basis_pct': [rnd(x, 3) for x in hb['basis_pct']]},
            'source': '新浪财经 IF 当月连续（IF0）收盘价 vs 腾讯证券沪深300 收盘价',
            'note': '基差 = 期货 − 现货，负数为贴水；到期日按当月第三个周五近似，节假日顺延没处理。用的是收盘价，不是结算价',
            **vn('basis')}


def obs_iv(rate_pct):
    chain = S.etf_option_chain()
    spot = float(S.sina_hq(['sh510300'])['sh510300'][3])
    rows = [r for r in chain['rows'] if r['strike'] > 0]
    std = [r for r in rows if 'A' not in r['name']] or rows
    strikes = sorted({r['strike'] for r in std})
    k = min(strikes, key=lambda x: abs(x - spot))
    T = chain['days'] / 365.0
    r = (rate_pct or 1.5) / 100.0
    out = {}
    for kind, code in [('call', 'C'), ('put', 'P')]:
        q = next(x for x in std if x['strike'] == k and x['kind'] == kind)
        price = (q['bid'] + q['ask']) / 2 if q['bid'] > 0 and q['ask'] > 0 else q['last']
        iv = O.implied_vol(code, price, spot, k, T, r)
        g = O.greeks(code, spot, k, T, r, iv) if iv else None
        out[kind] = {'contract': q['name'], 'price': rnd(price, 4), 'iv_pct': rnd(100 * iv, 2) if iv else None,
                     'delta': rnd(g['delta'], 3) if g else None, 'gamma': rnd(g['gamma'], 3) if g else None,
                     'vega_per_pt': rnd(g['vega'] / 100, 4) if g else None, 'theta_per_day': rnd(g['theta'] / 365, 4) if g else None,
                     'quote_time': q['time']}
    return {'status': 'ok', 'date': (out['call']['quote_time'] or '')[:10] or None, 'underlying_price': spot, 'strike': k,
            'expiry': chain['expiry'], 'days_to_expiry': chain['days'], 'rate_pct': rnd(r * 100, 3), **out,
            'atm_iv_pct': rnd(np.nanmean([x for x in [out['call']['iv_pct'], out['put']['iv_pct']] if x is not None]), 2)
            if (out['call']['iv_pct'] or out['put']['iv_pct']) else None,
            'source': '新浪财经 300ETF 期权（510300）报价，自算 Black-Scholes 隐含波动率',
            'note': '取离到期还有 7 天以上的最近月份、最接近平值的标准合约；价格用买卖中间价；无风险利率用 2 年期国债。Vega 是波动率每 1 个百分点，Theta 是每个自然日',
            **vn('iv')}


def obs_insider(as_of):
    start = (pd.Timestamp(as_of) - pd.Timedelta(days=200)).strftime('%Y-%m-%d')
    filt = f"(NOTICE_DATE>='{start}')(NOTICE_DATE<='{as_of}')"
    rows, count, pages = S.datacenter('RPT_SHARE_HOLDER_INCREASE', filt, 'NOTICE_DATE')
    table, meta = shareholder_monthly(rows, as_of)
    table = table.tail(6)
    zh = {'month': '月份', 'increase_events': '增持次数', 'decrease_events': '减持次数',
          'increase_shares_10k': '增持万股', 'decrease_shares_10k': '减持万股', 'net_shares_10k': '净增减万股',
          'candidate_sell_buy_shares_pct': '减/增股数比%', 'candidate_sell_buy_events_pct': '减/增次数比%',
          'candidate_decrease_event_share_pct': '减持次数占比%'}
    recs = [{zh.get(k, k): (rnd(v, 1) if isinstance(v, float) else v) for k, v in r.items()} for r in table.to_dict('records')]
    return {'status': 'ok', 'date': as_of, 'months': recs, 'rows_fetched': len(rows), 'rows_reported': count,
            'source': '东方财富数据中心 股东增减持（RPT_SHARE_HOLDER_INCREASE），按公告月份',
            'note': '减持/增持股数比 = 减持股数 ÷ 增持股数 × 100。高管增减持没并入（代码里没有高管汇总），博主的算法也没公开',
            **vn('insider')}


# ---------------------------------------------------------------- assembly

def build(out_dir, now_utc=None, skip_slow=False):
    now_utc = now_utc or datetime.now(timezone.utc)
    now_cn = now_utc.astimezone(CN)
    out_dir = Path(out_dir)
    data_dir = out_dir / 'data'
    errors = []
    instruments, frames = {}, {}
    for inst in C.INSTRUMENTS:
        try:
            blk, d = instrument_block(inst, now_utc, errors)
            instruments[inst['key']] = blk
            frames[inst['key']] = d
        except Exception as exc:
            traceback.print_exc()
            errors.append({'item': inst['key'], 'error': f'{type(exc).__name__}: {exc}'[:400]})
            instruments[inst['key']] = {'key': inst['key'], 'name': inst['name'], **no_data(f'行情没拿到：{exc}'[:200])}
    sh = frames.get('sh000001')
    a_date = ds(sh['date'].iloc[-1]) if sh is not None else None
    sse_dates = [ds(x) for x in sh['date']] if sh is not None else []
    hist_path = data_dir / 'history' / 'market_daily.csv'
    hist = pd.read_csv(hist_path) if hist_path.exists() else pd.DataFrame(columns=['date'])
    hist = hist.loc[hist['date'] != a_date]

    obs = {}
    snap = guarded('breadth', lambda: obs_breadth_and_valuation(a_date, hist), errors)
    if isinstance(snap, tuple):
        obs['breadth'], obs['equal_pe'], cap = snap
    else:
        obs['breadth'] = {**snap, **vn('breadth')}
        obs['equal_pe'] = {**snap, **vn('equal_pe')}
        cap = None
    obs['cap_gdp'] = guarded('cap_gdp', lambda: obs_cap_gdp(a_date, cap), errors)
    eb = guarded('equity_bond', lambda: obs_equity_bond(a_date), errors)
    rate = None
    if isinstance(eb, tuple):
        obs['equity_bond'], ty = eb
        pe_now = obs['equity_bond']['pe_ttm']
        zone = O.valuation_zone(pe_now, C.OBS_NOTES['equal_pe']['opportunity'], C.OBS_NOTES['equal_pe']['danger'])
        obs['equal_pe'].update({'csi300_pe': pe_now, 'csi300_pe_date': obs['equity_bond']['date'],
                                'zone_vs_blogger': {'danger': '危险区（≥14.18）', 'opportunity': '机会区（≤11.61）', 'middle': '两个阈值之间'}.get(zone),
                                'status': 'ok'})
        rate = float(ty['cn2y'].dropna().iloc[-1]) if ty['cn2y'].notna().any() else None
    else:
        obs['equity_bond'] = {**eb, **vn('equity_bond')}
    obs['pcr'] = guarded('pcr', lambda: obs_pcr(sse_dates, data_dir / 'history' / 'sse_pcr.csv'), errors) \
        if not skip_slow else no_data('本次本地运行跳过', **vn('pcr'))
    obs['etf_volume'] = guarded('etf_volume', obs_etf_volume, errors)
    obs['holdings'] = guarded('holdings', obs_holdings, errors)
    obs['basis'] = guarded('basis', lambda: obs_basis(a_date), errors)
    obs['iv'] = guarded('iv', lambda: obs_iv(rate), errors)
    obs['insider'] = guarded('insider', lambda: obs_insider(a_date), errors)
    for k in ['pcr', 'etf_volume', 'holdings', 'basis', 'iv', 'insider', 'cap_gdp']:
        if obs[k].get('status') != 'ok':
            obs[k] = {**vn(k), **obs[k]}
    unavailable = [
        {'name': '深交所期权 PCR', 'reason': '深交所接口对海外服务器返回 403 / 断开，GitHub Actions 上拿不到'},
        {'name': '债券仓位占比', 'reason': '博主没说是哪一类资金的仓位，没有可算的定义'},
        {'name': '汇金 / 中证金融仓位报告', 'reason': '博主没展示数据来源和算法'},
        {'name': '全市场资金流向', 'reason': '博主没公开算法；东方财富资金流接口（push2）在海外也连不上'},
        {'name': 'P20 / P60（站上 20/60 日线占比）', 'reason': '要逐股拉 5,500 多只股票的历史 K 线，每天跑太重，看板没接入'},
        {'name': '高管增减持比例', 'reason': '代码里只有股东增减持汇总，高管部分的算法博主没公开'},
        {'name': '博主综合评分', 'reason': '博主没公开权重和算法'},
    ]
    # history row for the daily observation archive
    row = {'date': a_date}
    b = obs['breadth']
    if b.get('status') == 'ok':
        row.update({k: b[k] for k in ['up', 'down', 'net_advances', 'amount_ratio', 'trin_amount', 'turnover_gt5_pct']})
    if obs['equal_pe'].get('status') == 'ok':
        row.update({'csi300_pe': obs['equal_pe'].get('csi300_pe'), 'equal_pe_median': obs['equal_pe'].get('median_positive')})
    if obs['cap_gdp'].get('status') == 'ok':
        row['cap_gdp_pct'] = obs['cap_gdp']['value_pct']
    if obs['iv'].get('status') == 'ok':
        row['atm_iv_pct'] = obs['iv']['atm_iv_pct']
    if obs['basis'].get('status') == 'ok':
        row['if_basis_pct'] = obs['basis']['basis_pct']
    if a_date:
        hist = pd.concat([hist, pd.DataFrame([row])], ignore_index=True).sort_values('date')
        hist_path.parent.mkdir(parents=True, exist_ok=True)
        hist.to_csv(hist_path, index=False)
    obs['daily_history'] = {c: [None if pd.isna(v) else v for v in hist[c].tolist()] for c in hist.columns}

    archive_key = now_cn.strftime('%Y-%m-%d')
    payload = {
        'generated_at_utc': now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'generated_at_beijing': now_cn.strftime('%Y-%m-%d %H:%M'),
        'archive_key': archive_key,
        'a_share_date': a_date,
        'gold_date': instruments.get('gc', {}).get('daily', {}).get('latest', {}).get('date'),
        'params': {'ichimoku': '7 / 22 / 44，云前移 22', 'vw_macd': '12 / 26 / 9', 'boll': '20，2 倍样本标准差（通达信 STD）', 'cci': '14'},
        'instruments': instruments,
        'observations': obs,
        'unavailable': unavailable,
        'errors': errors,
        'disclaimer': '仅为技术分析研究，不构成投资建议。',
    }
    data_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    (data_dir / 'latest.json').write_text(text, encoding='utf-8')
    (data_dir / 'archive').mkdir(exist_ok=True)
    (data_dir / 'archive' / f'{archive_key}.json').write_text(text, encoding='utf-8')
    dates = sorted(p.stem for p in (data_dir / 'archive').glob('*.json'))
    (data_dir / 'index.json').write_text(json.dumps({'dates': dates[::-1], 'latest': archive_key}, ensure_ascii=False), encoding='utf-8')
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='dashboard')
    ap.add_argument('--skip-slow', action='store_true')
    a = ap.parse_args()
    p = build(a.out, skip_slow=a.skip_slow)
    print(json.dumps({'a_share_date': p['a_share_date'], 'gold_date': p['gold_date'], 'archive': p['archive_key'],
                      'errors': p['errors']}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
