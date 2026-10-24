"""Fetch independently verifiable public observations; resumable through cache."""
from pathlib import Path
from datetime import datetime
import argparse
import json
from fetch_data import CN, PublicClient, snapshot, snapshot_sina, klines, klines_tencent, datacenter, options, save_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--as-of', default=datetime.now(CN).date().isoformat())
    parser.add_argument('--start', default='2025-10-01')
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--limit', type=int, default=0, help='0 = entire current provider list; positive number = explicit sample only')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    client = PublicClient(root/'cache', args.workers, args.offline)
    try:
        rows, meta = snapshot(client, args.as_of)
    except Exception as exc:
        print('Eastmoney snapshot unavailable; using independent Sina provider:', str(exc)[:100], flush=True)
        rows, meta = snapshot_sina(client, args.as_of)
    save_json(root/'data'/'snapshot.json', {'as_of': args.as_of, 'meta': meta, 'rows': rows})
    print('Universe verified:', len(rows), meta['quote_dates'], flush=True)
    chosen = rows[:args.limit] if args.limit else rows
    universe = [{'code': r['f12'], 'secid': f"{r['f13']}.{r['f12']}", 'name': r['f14'],
                 'symbol': r.get('sina_symbol') or (('sh' if r['f13']==1 else ('bj' if r['f12'].startswith(('4','8','92')) else 'sz'))+r['f12']),
                 'quote': r} for r in chosen]
    def daily(item):
        result = klines_tencent(client, item['symbol'], args.start, args.as_of, quote=item['quote'])
        return {'security': {k:v for k,v in item.items() if k!='quote'}, **result}
    results, errors = client.map(daily, universe, 'stock daily histories')
    histories = [value for _, value in results]
    histories.sort(key=lambda value: value['security']['secid'])
    save_json(root/'data'/'stock_histories.json', {'as_of': args.as_of, 'start': args.start,
              'universe_meta': meta, 'requested': len(chosen), 'received': len(histories),
              'scope': 'explicit limited sample' if args.limit else 'entire current provider list, retrospectively fetched',
              'adjustment': 'Tencent qfq prices; direction uses adjusted-close changes, subject to rounding and revision',
              'errors': errors, 'histories': histories})
    if errors:
        print('History errors retained explicitly:', len(errors), flush=True)
    index_daily = klines(client, '1.000001', '2023-01-01', args.as_of)
    try:
        index_weekly = klines(client, '1.000001', '2023-01-01', args.as_of, 'weekly')
    except Exception:
        index_weekly = []  # Calculate completed weekly bars from cached daily observations in analyze.py.
    save_json(root/'data'/'index.json', {'secid': '1.000001', 'name': '上证指数', 'daily': index_daily, 'weekly': index_weekly})
    dates = [x.split(',')[0] for x in index_daily if x.split(',')[0] >= args.start]
    def option_day(item):
        date, exchange = item
        return {'date': date, 'exchange': exchange, 'rows': options(client, date, exchange)}
    results, errors = client.map(option_day, [(d, ex) for d in dates for ex in ['SSE', 'SZSE']], 'option statistics')
    save_json(root/'data'/'options.json', {'as_of': args.as_of, 'scope': 'SSE + SZSE ETF options; excludes CFFEX index options',
              'days': [v for _, v in sorted(results, key=lambda x: x[0])], 'errors': errors})
    start = '2023-01-01'
    shareholder_filter = f"(END_DATE>='{start}')(END_DATE<='{args.as_of}')(NOTICE_DATE<='{args.as_of}')"
    holders = datacenter(client, 'RPT_SHARE_HOLDER_INCREASE', shareholder_filter, 'END_DATE,SECURITY_CODE,EITIME')
    save_json(root/'data'/'shareholders.json', {'as_of': args.as_of, 'filter': shareholder_filter, 'rows': holders})
    executive_filter = f"(CHANGE_DATE>='{start}')(CHANGE_DATE<='{args.as_of}')"
    executives = datacenter(client, 'RPT_EXECUTIVE_HOLD_DETAILS', executive_filter, 'CHANGE_DATE,SECURITY_CODE,PERSON_NAME', 5000)
    save_json(root/'data'/'executives.json', {'as_of': args.as_of, 'filter': executive_filter,
              'point_in_time_warning': 'Effective-date records; no verified historical announcement timestamp. Not point-in-time backtest inputs.',
              'rows': executives})
    treasury = datacenter(client, 'RPTA_WEB_TREASURYYIELD',
                          f"(SOLAR_DATE>='{start}')(SOLAR_DATE<='{args.as_of}')", 'SOLAR_DATE', 500)
    save_json(root/'data'/'treasury.json', {'as_of': args.as_of, 'yield_unit': 'percent', 'rows': treasury})
    print('Collection complete.', flush=True)


if __name__ == '__main__':
    main()
