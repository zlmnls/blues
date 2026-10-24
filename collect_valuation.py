"""Optional public valuation series. Cookie/CSRF handshake follows AKShare docs.

No user credentials are requested. Failure is recorded, never replaced with
synthetic valuation data. Daily public request token is MD5 of calendar date.
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import hashlib
import json
import urllib.request
import urllib.parse
from fetch_data import save_json


class MetaParser(HTMLParser):
    token = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag=='meta' and a.get('name')=='_csrf':
            self.token = a.get('content')


def main():
    root = Path(__file__).resolve().parent
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    ua = {'User-Agent':'Mozilla/5.0'}
    sources = [
        ('shanghai_market_average','https://legulegu.com/stockdata/shanghaiPE',
         'https://legulegu.com/api/stock-data/market-pe',{'marketId':'1'},'pe','provider market-average PE; earnings period unspecified'),
        ('csi300_ttm','https://legulegu.com/stockdata/hs300-ttm-lyr',
         'https://legulegu.com/api/stockdata/index-basic-pe',{'indexCode':'000300.SH'},'addTtmPe','CSI300 aggregate TTM PE')]
    series, errors = [], []
    for name,page,base,params,key,kind in sources:
        try:
            with opener.open(urllib.request.Request(page,headers=ua),timeout=20) as response:
                html = response.read().decode('utf-8')
            parser = MetaParser()
            parser.feed(html)
            if not parser.token:
                raise ValueError('Public page did not expose expected CSRF metadata')
            url = base+'?'+urllib.parse.urlencode({**params,'token':hashlib.md5(today.encode()).hexdigest()})
            with opener.open(urllib.request.Request(url,headers={**ua,'Referer':page,'X-CSRF-Token':parser.token}),timeout=20) as response:
                payload = json.loads(response.read())
            rows = payload.get('data')
            if not isinstance(rows,list) or not rows:
                raise ValueError('No public valuation rows: '+str(payload)[:200])
            series.append({'name':name,'source_page':page,'request_url':url,'pe_field':key,'pe_kind':kind,'rows':rows})
            print('Valuation',name,len(rows),'keys',list(rows[-1]),flush=True)
        except Exception as exc:
            errors.append({'name':name,'error':str(exc)})
            print('Valuation unavailable:',name,type(exc).__name__,str(exc)[:150],flush=True)
    save_json(root/'data'/'valuation.json',{'fetched_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'series':series,'errors':errors})


if __name__=='__main__':
    main()
