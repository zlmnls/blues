"""Public data collectors. No account tokens; responses retain provenance.

Endpoint field contracts were checked against AKShare 1.19.3 (MIT) and the
exchanges' returned data. This is an independent, minimal urllib adapter.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import math
import time
import urllib.parse
import urllib.request

CN = timezone(timedelta(hours=8))


class PublicClient:
    def __init__(self, cache_dir, workers=6, offline=False):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.workers = workers
        self.offline = offline

    def get(self, base, params, headers=None, tag=''):
        url = base + '?' + urllib.parse.urlencode(params)
        key = hashlib.sha256((url + '|' + tag).encode()).hexdigest()
        path = self.cache_dir / (key + '.json')
        if path.exists():
            saved = json.loads(path.read_text(encoding='utf-8'))
            payload_bytes = json.dumps(saved['payload'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
            if hashlib.sha256(payload_bytes).hexdigest() != saved['payload_sha256']:
                raise ValueError('Cache checksum mismatch: ' + str(path))
            return saved['payload']
        if self.offline:
            raise FileNotFoundError('Missing cached response: ' + url)
        last = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', **(headers or {})})
                with urllib.request.urlopen(req, timeout=20) as res:
                    payload = json.loads(res.read())
                encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
                saved = {'url': url, 'fetched_at': datetime.now(CN).isoformat(),
                         'payload_sha256': hashlib.sha256(encoded).hexdigest(), 'payload': payload}
                temp = path.with_suffix('.tmp')
                temp.write_text(json.dumps(saved, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
                temp.replace(path)
                return payload
            except Exception as exc:
                last = exc
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f'Failed request {url}: {last}') from last

    def map(self, function, items, label):
        results, errors = [], []
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(function, item): item for item in items}
            n = len(futures)
            for done, future in enumerate(as_completed(futures), 1):
                item = futures[future]
                try:
                    results.append((item, future.result()))
                except Exception as exc:
                    errors.append({'item': str(item), 'error': str(exc)})
                if done % 250 == 0 or done == n:
                    print(f'{label}: {done}/{n}, failed={len(errors)}', flush=True)
        return results, errors


def snapshot(client, as_of):
    base = 'https://82.push2.eastmoney.com/api/qt/clist/get'
    params = {'pn': 1, 'pz': 100, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2, 'fid': 'f12',
              'fs': 'm:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048',
              'fields': 'f2,f3,f4,f5,f6,f8,f12,f13,f14,f18,f20,f124'}
    first = client.get(base, params, tag=as_of)['data']
    total = int(first['total'])
    page_size = len(first['diff'])
    if not page_size:
        raise ValueError('Empty universe response')
    pages = math.ceil(total / page_size)
    rows = list(first['diff'])
    def page(n):
        data = client.get(base, {**params, 'pn': n}, tag=as_of)['data']
        if int(data['total']) != total:
            raise ValueError('Universe changed while fetching; rerun snapshot')
        return data['diff']
    results, errors = client.map(page, range(2, pages + 1), 'snapshot')
    for _, result in results:
        rows.extend(result)
    if errors:
        raise RuntimeError('Incomplete snapshot pages: ' + str(errors))
    keys = [(r['f13'], r['f12']) for r in rows]
    if len(keys) != total or len(set(keys)) != total:
        raise ValueError(f'Universe coverage mismatch: {len(keys)}/{total}, unique={len(set(keys))}')
    dates = sorted({datetime.fromtimestamp(int(r['f124']), CN).date().isoformat()
                    for r in rows if r.get('f124') and str(r['f124']).isdigit()})
    if dates and dates[-1] > as_of:
        raise ValueError('Snapshot contains quotes after requested as_of; historical snapshot cannot be recreated from latest endpoint')
    return sorted(rows, key=lambda r: (r['f13'], r['f12'])), {'provider_total': total, 'quote_dates': dates,
        'universe': 'current mainland Shanghai/Shenzhen/Beijing A-share provider list',
        'historical_universe_limitation': 'Current-list retrospective sample; securities delisted before this list are absent.'}


def snapshot_sina(client, as_of):
    """Fallback whole-list snapshot. Upstream supplies clock time, not calendar date."""
    if not client.offline and as_of != datetime.now(CN).date().isoformat():
        raise ValueError('Sina snapshot is latest-only. A past calendar date requires an already-saved snapshot, not a new current request.')
    base = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
    params = {'page': 1, 'num': 80, 'sort': 'symbol', 'asc': 1, 'node': 'hs_a', 'symbol': '', '_s_r_a': 'page'}
    raw = []
    # Fetch each page once; low concurrency avoids repeatedly polling this source.
    for n in range(1, 110):
        page = client.get(base, {**params, 'page': n}, {'Referer': 'https://finance.sina.com.cn/'}, tag=as_of)
        if not page:
            break
        raw.extend(page)
        if len(page) < 80:
            break
        if n % 20 == 0:
            print(f'Sina snapshot pages: {n}', flush=True)
        time.sleep(0.08)
    else:
        raise ValueError('Snapshot did not reach terminal page')
    seen = [r['symbol'] for r in raw]
    if len(set(seen)) != len(seen):
        raise ValueError('Duplicate securities in Sina snapshot')
    def num(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    rows = []
    for r in raw:
        if r['symbol'][:2] not in {'sh', 'sz', 'bj'}:
            continue
        vol, cap = num(r['volume']), num(r.get('mktcap'))
        rows.append({'f12': r['code'], 'f13': 1 if r['symbol'].startswith('sh') else 0,
            'f14': r['name'], 'f2': num(r['trade']), 'f3': num(r['changepercent']),
            'f4': num(r['pricechange']), 'f5': None if vol is None else vol/100,
            'f6': num(r['amount']), 'f8': num(r.get('turnoverratio')), 'f18': num(r['settlement']),
            'f20': None if cap is None else cap*10000, 'f124': None,
            'sina_symbol': r['symbol'], 'source_clock': r.get('ticktime')})
    return rows, {'provider_total': len(rows), 'quote_dates': [], 'provider': 'Sina',
        'calendar_date_status': 'Only clock time is supplied; assigned collection date, not independently verified by snapshot endpoint.',
        'universe': 'Sina current mainland A-share provider list',
        'historical_universe_limitation': 'Current-list retrospective sample; delisted securities absent.'}


def klines_tencent(client, symbol, start, end, period='day', adjusted=True, quote=None):
    """Normalize QQ prices, amount in yuan and share volume with recorded calibration.

    Historical returns use qfq close changes. Price rounding/corporate-action
    revisions mean this is not a guaranteed match to official daily return flags.
    """
    adjust = 'qfq' if adjusted else ''
    payload = client.get('https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get',
                         {'param': f'{symbol},{period},{start},{end},640,{adjust}'})
    data = payload.get('data', {}).get(symbol, {})
    values = data.get(adjust+period, data.get(period, []))
    values = sorted(values, key=lambda row: row[0])
    if not values:
        return {'klines': [], 'volume_factor': None, 'volume_factor_method': 'no data'}
    last = values[-1]
    def f(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    factor, method = None, 'unknown'
    raw_volume, close = f(last[5]), f(last[2])
    if quote and last[0] == end and raw_volume and quote.get('f5'):
        ratio = quote['f5']*100/raw_volume
        for candidate in [1, 100]:
            if abs(ratio/candidate - 1) < 0.03:
                factor, method = candidate, 'same-date Sina share volume / Tencent raw volume'
    if factor is None and len(last)>8 and f(last[8]) and raw_volume and close:
        ratio = f(last[8])*10000/(raw_volume*close)
        for candidate in [1, 100]:
            if 0.5 < ratio/candidate < 2:
                factor, method = candidate, 'amount / (raw volume * last close), approximate unit calibration'
    output, previous = [], None
    for row in values:
        date, op, cl, hi, lo = row[0], *[f(x) for x in row[1:5]]
        pct = (cl/previous-1)*100 if cl and previous else None
        change = cl-previous if cl is not None and previous is not None else None
        previous = cl
        if not start <= date <= end:
            continue
        vol = f(row[5])
        volume_shares = vol*factor if vol is not None and factor is not None else None
        amount = f(row[8])*10000 if len(row)>8 and f(row[8]) is not None else None
        turn = f(row[7]) if len(row)>7 else None  # QQ field shown in percent units, as on the quote page.
        fields = [date,op,cl,hi,lo,volume_shares,amount,None,pct,change,turn]
        output.append(','.join('' if x is None else str(x) for x in fields))
    return {'klines': output, 'volume_factor': factor, 'volume_factor_method': method,
            'adjustment': 'qfq' if adjusted else 'unadjusted',
            'direction_method': 'change in supplied adjusted closes, subject to rounding and later revision',
            'turnover_unit': 'percent as supplied; not used for historical >5% results until cross-source validation'}


def klines(client, secid, start, end, period='daily', adjust=0):
    params = {'secid': secid, 'fields1': 'f1,f2,f3,f4,f5,f6',
              'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
              'klt': {'daily': 101, 'weekly': 102}[period], 'fqt': adjust,
              'beg': start.replace('-', ''), 'end': end.replace('-', ''), 'lmt': 10000}
    payload = client.get('https://push2his.eastmoney.com/api/qt/stock/kline/get', params)
    if payload.get('rc') != 0:
        raise ValueError('Kline provider error: ' + str(payload))
    data = payload.get('data')
    if not data:
        return []
    return data.get('klines') or []


def datacenter(client, report, date_filter, sort_columns, page_size=500):
    params = {'sortColumns': sort_columns, 'sortTypes': ','.join(['-1'] * len(sort_columns.split(','))),
              'pageSize': page_size, 'pageNumber': 1, 'reportName': report,
              'columns': 'ALL', 'source': 'WEB', 'client': 'WEB', 'filter': date_filter}
    base = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
    first = client.get(base, params)
    if not first.get('success') or not first.get('result'):
        raise ValueError(f'{report}: {str(first)[:300]}')
    result = first['result']
    rows, pages = list(result['data']), int(result['pages'])
    expected = result.get('count')
    def page(n):
        return client.get(base, {**params, 'pageNumber': n})['result']['data']
    results, errors = client.map(page, range(2, pages + 1), report)
    if errors:
        raise RuntimeError(str(errors))
    for _, response in results:
        rows.extend(response)
    if expected is not None and len(rows) != int(expected):
        raise ValueError(f'{report}: pagination mismatch {len(rows)}/{expected}')
    return rows


def options(client, date, exchange='SSE'):
    if exchange == 'SSE':
        payload = client.get('https://query.sse.com.cn/commonQuery.do',
                             {'isPagination': 'false', 'sqlId': 'COMMON_SSE_ZQPZ_YSP_QQ_SJTJ_MRTJ_CX',
                              'tradeDate': date.replace('-', '')}, {'Referer': 'https://www.sse.com.cn/'})
        return payload.get('result', [])
    payload = client.get('https://investor.szse.cn/api/report/ShowReport/data',
                         {'SHOWTYPE': 'JSON', 'CATALOGID': 'ysprdzb', 'TABKEY': 'tab1', 'txtQueryDate': date})
    return payload[0].get('data', [])


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
