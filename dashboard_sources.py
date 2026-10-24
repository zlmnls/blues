"""Network fetchers for the dashboard, chosen because they answer from overseas runners.

Tested from a US data centre on 2026-10-24 (same situation as GitHub Actions):
  works   Tencent kline (web.ifzq.gtimg.cn), Sina quotes/kline/snapshot (Referer needed),
          Yahoo chart API, Eastmoney datacenter-web, SSE commonQuery (Referer needed, ~5 s),
          CSIndex index-perf
  blocked Eastmoney push2 / push2his (connection closed), SZSE option report (403/reset)
Every call retries with backoff; callers record failures instead of inventing values.
"""
from datetime import datetime, timedelta, timezone
import json
import re
import time
import urllib.parse
import urllib.request

import pandas as pd

CN = timezone(timedelta(hours=8))
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}
SINA = {'Referer': 'https://finance.sina.com.cn/'}
SSE = {'Referer': 'https://www.sse.com.cn/'}


def http(url, params=None, headers=None, tries=4, timeout=20, encoding=None):
    if params:
        url = url + ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={**UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            if encoding:
                return raw.decode(encoding, 'replace')
            try:
                return raw.decode('utf-8')
            except UnicodeDecodeError:
                return raw.decode('gbk', 'replace')
        except Exception as exc:  # network errors are retried, then raised
            last = exc
            if i < tries - 1:
                time.sleep(2 * (i + 1))
    raise RuntimeError(f'{url[:120]} failed after {tries} tries: {last}')


def http_json(url, params=None, headers=None, **kw):
    return json.loads(http(url, params, headers, **kw))


# ------------------------------------------------------------------ daily bars

def _frame(rows):
    f = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    f['date'] = pd.to_datetime(f['date'])
    for c in ['open', 'high', 'low', 'close', 'volume']:
        f[c] = pd.to_numeric(f[c], errors='coerce')
    f = f.dropna(subset=['open', 'high', 'low', 'close']).drop_duplicates('date', keep='last')
    f = f.sort_values('date').reset_index(drop=True)
    f['volume'] = f['volume'].fillna(0)
    f['amount'] = f['close'] * f['volume']
    return f


def bars_tencent(symbol, start='2023-01-01'):
    end = (datetime.now(CN) + timedelta(days=1)).date().isoformat()
    j = http_json('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
                  {'param': f'{symbol},day,{start},{end},2000,'})
    rows = j['data'][symbol]['day']  # date, open, close, high, low, volume
    return _frame([[r[0], r[1], r[3], r[4], r[2], r[5]] for r in rows])


def bars_sina(symbol):
    j = http_json('https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData',
                  {'symbol': symbol, 'scale': 240, 'ma': 'no', 'datalen': 1023}, SINA)
    return _frame([[r['day'], r['open'], r['high'], r['low'], r['close'], r['volume']] for r in j])


def bars_yahoo(ticker, rng='5y'):
    j = None
    for host in ['query1', 'query2']:
        try:
            j = http_json(f'https://{host}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}',
                          {'range': rng, 'interval': '1d'}, {'User-Agent': 'Mozilla/5.0'}, tries=3)
            break
        except Exception:
            if host == 'query2':
                raise
    res = j['chart']['result'][0]
    tz = res['meta'].get('exchangeTimezoneName', 'America/New_York')
    q = res['indicators']['quote'][0]
    dates = pd.to_datetime(res['timestamp'], unit='s', utc=True).tz_convert(tz).tz_localize(None).normalize()
    f = _frame([[d, o, h, l, c, v] for d, o, h, l, c, v in
                zip(dates, q['open'], q['high'], q['low'], q['close'], q['volume'])])
    return f, tz


def bars_sina_gold():
    """Sina global futures daily bars for COMEX gold. No volume in this feed."""
    tag = datetime.now(timezone.utc).strftime('%Y_%m_%d')
    s = http('https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_GC' + tag +
             '=/GlobalFuturesService.getGlobalFuturesDailyKLine', {'symbol': 'GC', '_': tag, 'source': 'web'}, SINA)
    data = json.loads(s[s.index('(') + 1:s.rindex(')')])
    return _frame([[r['date'], r['open'], r['high'], r['low'], r['close'], r['volume']] for r in data])


def gold_bars(ticker='GC=F'):
    errors = []
    try:
        f, _ = bars_yahoo(ticker)
        if len(f) >= 300:
            return f, 'Yahoo Finance（GC=F）', errors
        errors.append(f'Yahoo: only {len(f)} rows')
    except Exception as exc:
        errors.append(f'Yahoo: {exc}')
    f = bars_sina_gold()
    f['volume'] = 1.0  # feed has no volume: equal weights, so VW-MACD falls back to plain MACD
    f['amount'] = f['close']
    return f, '新浪财经外盘期货 GC（无成交量，VW-MACD 退化为普通 MACD）', errors


def completed_gold_bars(f, now_utc=None):
    """COMEX daily session for date D ends 17:00 New York time on D. Drop a bar still trading."""
    now = pd.Timestamp(now_utc or datetime.now(timezone.utc)).tz_convert('America/New_York').tz_localize(None)
    keep = f['date'] + pd.Timedelta(hours=17) <= now
    return f.loc[keep].reset_index(drop=True)


def index_bars(inst):
    errors = []
    for name, fn in [('腾讯证券', lambda: bars_tencent(inst['tencent'])),
                     ('新浪财经', lambda: bars_sina(inst['sina'])),
                     ('Yahoo Finance', lambda: bars_yahoo(inst['yahoo'])[0])]:
        try:
            f = fn()
            if len(f) >= 300:
                return f, name, errors
            errors.append(f'{name}: only {len(f)} rows')
        except Exception as exc:
            errors.append(f'{name}: {exc}')
    raise RuntimeError('; '.join(errors))


# ------------------------------------------------------------ market snapshot

def sina_snapshot():
    """All A shares from Sina (latest only): price, change, volume, amount, turnover, PE, market cap."""
    base = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
    total = int(json.loads(http('https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
                                'Market_Center.getHQNodeStockCount', {'node': 'hs_a'}, SINA)))
    rows, page = [], 1
    while len(rows) < total and page < 120:
        part = http_json(base, {'page': page, 'num': 100, 'sort': 'symbol', 'asc': 1, 'node': 'hs_a',
                                'symbol': '', '_s_r_a': 'page'}, SINA)
        if not part:
            break
        rows.extend(part)
        page += 1
        time.sleep(0.05)
    seen = {r['symbol'] for r in rows}
    return rows, {'provider_total': total, 'received': len(rows), 'unique': len(seen)}


# ---------------------------------------------------------- observation data

def sse_option_day(date):
    j = http_json('https://query.sse.com.cn/commonQuery.do',
                  {'isPagination': 'false', 'sqlId': 'COMMON_SSE_ZQPZ_YSP_QQ_SJTJ_MRTJ_CX',
                   'tradeDate': date.replace('-', '')}, SSE, timeout=25)
    return j.get('result') or []


def datacenter(report, filt, sort, page_size=500, max_pages=40):
    base = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
    p = {'reportName': report, 'columns': 'ALL', 'sortColumns': sort, 'sortTypes': '-1',
         'pageSize': page_size, 'pageNumber': 1, 'source': 'WEB', 'client': 'WEB', 'filter': filt}
    first = http_json(base, p)
    if not first.get('success'):
        raise RuntimeError(f'{report}: {first.get("message")}')
    res = first['result']
    rows = list(res['data'])
    for n in range(2, min(int(res['pages']), max_pages) + 1):
        rows.extend(http_json(base, {**p, 'pageNumber': n})['result']['data'])
    return rows, int(res.get('count') or len(rows)), int(res['pages'])


def treasury(start):
    rows, _, _ = datacenter('RPTA_WEB_TREASURYYIELD', f"(SOLAR_DATE>='{start}')", 'SOLAR_DATE')
    f = pd.DataFrame({'date': pd.to_datetime([r['SOLAR_DATE'][:10] for r in rows]),
                      'cn2y': [r.get('EMM00588704') for r in rows],
                      'yield_10y_pct': [r.get('EMM00166466') for r in rows]})
    return f.dropna(subset=['yield_10y_pct']).sort_values('date').reset_index(drop=True)


def csindex_pe(code, start, end):
    j = http_json('https://www.csindex.com.cn/csindex-home/perf/index-perf',
                  {'indexCode': code, 'startDate': start.replace('-', ''), 'endDate': end.replace('-', '')})
    f = pd.DataFrame([{'date': r['tradeDate'], 'close': r['close'], 'pe_ttm': r.get('peg')} for r in j['data']])
    f['date'] = pd.to_datetime(f['date'])
    f['pe_ttm'] = pd.to_numeric(f['pe_ttm'], errors='coerce')
    return f.dropna(subset=['pe_ttm']).reset_index(drop=True)


def gdp_quarters():
    rows, _, _ = datacenter('RPT_ECONOMY_GDP', '', 'REPORT_DATE', page_size=40, max_pages=1)
    return [{'report_date': r['REPORT_DATE'][:10], 'label': r['TIME'], 'gdp_cum_100m': r['DOMESTICL_PRODUCT_BASE']}
            for r in rows]


def sina_futures_daily(symbol):
    s = http('https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20t=/InnerFuturesNewService.getDailyKLine',
             {'symbol': symbol}, SINA)
    data = json.loads(s[s.index('(') + 1:s.rindex(')')])
    f = pd.DataFrame(data)
    f['date'] = pd.to_datetime(f['d'])
    f['close'] = pd.to_numeric(f['c'], errors='coerce')
    return f[['date', 'close']].dropna()


def sina_hq(codes):
    s = http('https://hq.sinajs.cn/list=' + ','.join(codes), headers=SINA, encoding='gbk')
    out = {}
    for m in re.finditer(r'var hq_str_([\w]+)="([^"]*)";', s):
        out[m.group(1)] = m.group(2).split(',')
    return out


def etf_option_chain(cate='300ETF', underlying='510300'):
    """Near-month (>= 7 days left, else next) 300ETF option quotes from Sina."""
    meta = http_json('https://stock.finance.sina.com.cn/futures/api/openapi.php/StockOptionService.getStockName',
                     {'exchange': 'null', 'cate': cate}, SINA)
    months = sorted(set(meta['result']['data']['contractMonth']))
    for month in months:
        rem = http_json('https://stock.finance.sina.com.cn/futures/api/openapi.php/StockOptionService.getRemainderDay',
                        {'exchange': 'null', 'cate': cate, 'date': month}, SINA)['result']['data']
        if int(rem['remainderDays']) < 7:
            continue
        tag = month[2:4] + month[5:7]
        lists = sina_hq([f'OP_UP_{underlying}{tag}', f'OP_DOWN_{underlying}{tag}'])
        calls = [c for c in lists.get(f'OP_UP_{underlying}{tag}', []) if c]
        puts = [c for c in lists.get(f'OP_DOWN_{underlying}{tag}', []) if c]
        quotes = sina_hq(calls + puts)
        rows = []
        for side, codes in [('call', calls), ('put', puts)]:
            for code in codes:
                q = quotes.get(code)
                if not q or len(q) < 8:
                    continue
                rows.append({'code': code, 'kind': side, 'bid': float(q[1] or 0), 'last': float(q[2] or 0),
                             'ask': float(q[3] or 0), 'oi': float(q[5] or 0), 'strike': float(q[7]),
                             'name': q[37] if len(q) > 37 else '', 'time': q[32] if len(q) > 32 else ''})
        return {'month': month, 'expiry': rem['expireDay'], 'days': int(rem['remainderDays']), 'rows': rows}
    raise RuntimeError('no option month with >= 7 days left')
