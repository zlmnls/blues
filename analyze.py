"""Recompute outputs from saved inputs, without network access."""
from pathlib import Path
import hashlib
import json
import platform
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from indicators import (parse_klines, snapshot_metrics, market_history, technical,
                        weekly_bars, pcr_history, shareholder_monthly, equity_bond_candidate,
                        KLINE_COLUMNS, market_metrics)
from fetch_data import save_json

ROOT=Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT/'data'/(name+'.json')).read_text(encoding='utf-8'))


def records(frame):
    return json.loads(frame.to_json(orient='records',date_format='iso',double_precision=10))


def setup_plot():
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({'axes.unicode_minus':False,'figure.facecolor':'white',
                         'axes.spines.top':False,'axes.spines.right':False,
                         'axes.grid':True,'grid.alpha':0.18,'font.size':10})


def finish(fig,path):
    fig.autofmt_xdate()
    fig.savefig(path,dpi=150,bbox_inches='tight',facecolor='white')
    plt.close(fig)


def charts(out,breadth,index_daily,index_tech,pcr,holders,erp):
    setup_plot()
    figdir=out/'figures'
    figdir.mkdir(exist_ok=True)
    b=breadth.loc[breadth['date'].ge('2026-05-01')]
    ix=index_daily.loc[index_daily['date'].ge('2026-05-01')]
    fig,axs=plt.subplots(4,1,figsize=(12,11),sharex=True,layout='constrained')
    axs[0].plot(ix['date'],ix['close'],color='#1d3557',label='上证指数（东财历史响应）')
    axs[0].legend(loc='upper left')
    axs[0].set_title('公开数据复现｜当前新浪名册回溯样本，非原作者原始数据')
    axs[1].plot(b['date'],b['up_pct_all'],color='#176b55',label='上涨股票占比（平盘纳入分母）')
    axs[1].axhline(50,color='gray',linestyle='--',lw=1)
    axs[1].set_ylim(0,100)
    axs[1].set_ylabel('%')
    axs[1].legend(loc='upper left')
    axs[2].plot(b['date'],b['trin_amount'],color='#b55220',label='TRIN：成交额口径')
    axs[2].plot(b['date'],b['trin_volume'],color='#64748b',alpha=.7,label='TRIN：成交量口径')
    axs[2].axhline(1,color='gray',linestyle='--',lw=1)
    axs[2].set_yscale('log')
    axs[2].set_ylabel('倍数（对数轴）')
    axs[2].legend(loc='upper left')
    axs[3].plot(b['date'],b['candidate_p20_pct'],label='P20 候选：价格高于 MA20 的占比',color='#2563eb')
    axs[3].plot(b['date'],b['candidate_p60_pct'],label='P60 候选：价格高于 MA60 的占比',color='#8b5cf6')
    axs[3].set_ylim(0,100)
    axs[3].set_ylabel('%')
    axs[3].legend(loc='upper left')
    for ax in axs:
        for date in ['2026-09-21','2026-09-22']:
            ax.axvline(pd.Timestamp(date),color='#e6a23c',linestyle=':',lw=1)
    finish(fig,figdir/'market_breadth.png')

    f=index_tech.loc[index_tech['date'].ge('2026-05-01')]
    fig,axs=plt.subplots(3,1,figsize=(12,9),sharex=True,layout='constrained')
    axs[0].plot(f['date'],f['close'],color='#1d3557',label='上证指数日线')
    axs[0].fill_between(f['date'],f['cloud_a_assumed_shift22'],f['cloud_b_assumed_shift22'],color='#65a30d',alpha=.15,label='云层：移位 22 为显式假设')
    axs[0].legend(loc='upper left')
    axs[0].set_title('技术指标复现｜VW-MACD 按视频公式，云层移位为假设')
    axs[1].plot(f['date'],f['vw_dif'],color='#2563eb',label='DIF：VWMA12 − VWMA26')
    axs[1].plot(f['date'],f['vw_dea'],color='#d97706',label='DEA：EMA9(DIF)')
    axs[1].bar(f['date'],f['vw_histogram'],color=np.where(f['vw_histogram']>=0,'#d45656','#2c8e83'),alpha=.4,label='2 × (DIF − DEA)')
    axs[1].axhline(0,color='gray',lw=1)
    axs[1].legend(loc='upper left')
    axs[2].plot(f['date'],f['cci_14'],color='#7c3aed',label='CCI14')
    axs[2].axhline(100,color='gray',linestyle='--',lw=.8)
    axs[2].axhline(-100,color='gray',linestyle='--',lw=.8)
    axs[2].legend(loc='upper left')
    finish(fig,figdir/'technical.png')

    fig,axs=plt.subplots(2,1,figsize=(12,7),sharex=True,layout='constrained')
    for ex,color in [('SSE','#2563eb'),('SZSE','#d97706'),('SSE+SZSE','#176b55')]:
        f=pcr.loc[pcr['exchange'].eq(ex)&pcr['underlying'].eq('ALL')].copy()
        f['date']=pd.to_datetime(f['date'])
        axs[0].plot(f['date'],f['pcr_volume'],label=ex,color=color,alpha=.8)
        axs[1].plot(f['date'],f['pcr_oi'],label=ex,color=color,alpha=.8)
    axs[0].set_title('期权 PCR｜仅上交所、深交所 ETF 期权，不含中金所')
    axs[0].set_ylabel('成交量 PCR')
    axs[1].set_ylabel('持仓量 PCR')
    for ax in axs:
        ax.legend(loc='upper left')
    finish(fig,figdir/'pcr.png')

    fig,axs=plt.subplots(2,1,figsize=(12,7),sharex=True,layout='constrained')
    dates=pd.to_datetime(holders['month'])
    axs[0].bar(dates,holders['net_shares_10k']/10000,width=22,color=np.where(holders['net_shares_10k']>=0,'#c45a5a','#26897d'))
    axs[0].set_ylabel('亿股')
    axs[0].set_title('股东增减持候选统计｜按公告月；未与董监高表合并')
    axs[1].plot(dates,holders['candidate_sell_buy_shares_pct'],label='候选：减持股数 / 增持股数 × 100%',color='#b55220')
    axs[1].plot(dates,holders['candidate_sell_buy_events_pct'],label='候选：减持记录数 / 增持记录数 × 100%',color='#64748b')
    axs[1].set_ylabel('%')
    axs[1].legend(loc='upper left')
    finish(fig,figdir/'shareholders.png')

    if erp:
        fig,axs=plt.subplots(len(erp),1,figsize=(12,3.8*len(erp)),squeeze=False,layout='constrained')
        for ax,(name,frame) in zip(axs[:,0],erp.items()):
            ax.plot(frame['date'],frame['spread_pct_points'],label='候选：100/PE − 十年国债收益率',color='#2563eb')
            ax.plot(frame['date'],frame['upper'],label='12 个匹配观测点均值 + 2σ（候选）',color='#3b8e61')
            ax.plot(frame['date'],frame['lower'],label='12 个匹配观测点均值 − 2σ',color='#8b5cf6')
            ax.set_title(name+'｜PE 为稀疏/月度样本；没有填充成日频')
            ax.set_ylabel('百分点')
            ax.legend(loc='upper left')
        finish(fig,figdir/'equity_bond_candidates.png')


def executive_summary(rows):
    f=pd.DataFrame(rows)
    f['date']=pd.to_datetime(f['CHANGE_DATE'],errors='coerce')
    f['shares']=pd.to_numeric(f['CHANGE_SHARES'],errors='coerce')
    f['amount_yuan']=pd.to_numeric(f['CHANGE_AMOUNT'],errors='coerce')
    f['month']=f['date'].dt.to_period('M').astype(str)
    out=f.groupby('month',sort=True).agg(records=('shares','size'),net_shares=('shares','sum'),net_amount_yuan=('amount_yuan','sum')).reset_index()
    return out


def compare_natural_scopes(histories):
    selected=[]
    for history in histories:
        for value in history['klines']:
            if value.startswith(('2026-09-21,','2026-09-22,')):
                selected.append(value.split(',')+[history['security']['symbol'][:2]])
    f=pd.DataFrame(selected,columns=KLINE_COLUMNS+['board'])
    for c in KLINE_COLUMNS[1:]:
        f[c]=pd.to_numeric(f[c],errors='coerce')
    results=[]
    for name in ['SH+SZ+BJ current-list sample','SH+SZ current-list sample']:
        scoped=f if '+BJ' in name else f.loc[~f['board'].eq('bj')]
        for date,g in scoped.groupby('date'):
            results.append({'date':date,'scope':name,**market_metrics(g)})
    return results


def fmt(value,digits=2):
    return '未知' if value is None or pd.isna(value) else f'{value:,.{digits}f}'


def main():
    out=ROOT/'results'
    out.mkdir(exist_ok=True)
    snap=read('snapshot')
    hist=read('stock_histories')
    print('Calculating historical breadth...',flush=True)
    breadth,quality=market_history(hist['histories'],snap['rows'])
    summary=snapshot_metrics(snap['rows'])
    index=read('index')
    daily=parse_klines(index['daily'])
    daily_tech=technical(daily)
    weekly=parse_klines(index['weekly']) if index['weekly'] else weekly_bars(daily)
    weekly_tech=technical(weekly)
    pcr,pcr_issues=pcr_history(read('options')['days'])
    holder_data=read('shareholders')
    holders,holder_quality=shareholder_monthly(holder_data['rows'],snap['as_of'])
    executives=executive_summary(read('executives')['rows'])
    treasury=read('treasury')
    yf=pd.DataFrame(treasury['rows'])
    yf['date']=pd.to_datetime(yf['SOLAR_DATE']).dt.normalize()
    yf['yield_10y_pct']=pd.to_numeric(yf['EMM00166466'],errors='coerce')
    erp={}
    valuation=read('valuation') if (ROOT/'data'/'valuation.json').exists() else {'series':[],'errors':[{'reason':'not collected'}]}
    for series in valuation['series']:
        f=pd.DataFrame(series['rows'])
        if pd.api.types.is_numeric_dtype(f['date']):
            f['date']=pd.to_datetime(f['date'],unit='ms',utc=True).dt.tz_convert('Asia/Shanghai').dt.tz_localize(None).dt.normalize()
        else:
            f['date']=pd.to_datetime(f['date']).dt.normalize()
        f=f.loc[f['date'].le(snap['as_of'])].copy()
        f['pe_ttm']=pd.to_numeric(f[series['pe_field']],errors='coerce')
        # Actual free response is sparse/monthly, so do not pretend it is daily.
        # 12 matched observations is a disclosed demonstration window; not the video algorithm.
        erp[series['name']]=equity_bond_candidate(f,yf,window=12)
    checks=[]
    targets=[('2026-09-21','up_pct_all',80.0),('2026-09-21','down_pct_all',17.6),
             ('2026-09-21','down_amount_pct',27.0),('2026-09-21','trin_amount',1.69),
             ('2026-09-22','up_pct_all',43.7)]
    for date,metric,target in targets:
        f=breadth.loc[breadth['date'].eq(pd.Timestamp(date))]
        actual=None if f.empty else f.iloc[0][metric]
        checks.append({'date':date,'metric':metric,'video_value':target,'reproduced_value':actual,
                       'difference':None if actual is None else float(actual-target),
                       'scope':'Current Sina-list retrospective sample; Tencent adjusted-price direction; not proved to be original universe.'})
    save_json(out/'snapshot_metrics.json',summary)
    for name,frame in [('market_breadth',breadth),('technical_daily',daily_tech),('technical_weekly',weekly_tech),
                       ('pcr',pcr),('shareholder_monthly_candidates',holders),('executive_monthly',executives)]:
        save_json(out/(name+'.json'),records(frame))
    save_json(out/'equity_bond_candidates.json',{k:records(v) for k,v in erp.items()})
    save_json(out/'video_comparison.json',checks)
    scopes=compare_natural_scopes(hist['histories'])
    save_json(out/'natural_scope_comparison.json',scopes)
    q={'snapshot':snap['meta'],'history_requested':hist['requested'],'history_received':hist['received'],
       'history_errors':hist['errors'],'history_nonempty':sum(q['rows']>0 for q in quality),
       'volume_calibrated':sum(q.get('volume_factor') is not None for q in quality),
       'volume_calibrated_exact_cross_source':sum(q.get('volume_factor_method')=='same-date Sina share volume / Tencent raw volume' for q in quality),
       'volume_calibrated_approximate':sum(q.get('volume_factor_method','').startswith('amount /') for q in quality),
       'turnover_calibrated':sum(q['turnover_calibrated'] for q in quality),
       'pcr_issues':pcr_issues,'shareholder_quality':holder_quality,'valuation_errors':valuation['errors'],
       'assumptions':{'P20/P60':'percentage of eligible prices above MA20/MA60; hypothesis only',
                      'MCL':'19/39 EMA differences of net advances, plus ratio-adjusted variant; hypothesis only; EMA seeded with first observation',
                      'composite_score':'undefined, not generated','cloud_shift':22,'boll_sigma':2,'boll_std_ddof':0,
                      'equity_bond_spread':'100 / provider PE - 10y yield in percent; PE response is sparse/monthly; 12 matched observations rolling ±2 sigma; hypothesis only, 252-day bands unavailable',
                      'weekly_bar':'Last observed trading session, final group may be incomplete if collected midweek',
                      'returns':'Tencent qfq close changes, not original unrounded daily return flags'},
       'runtime':{'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__,'matplotlib':matplotlib.__version__}}
    save_json(out/'quality_report.json',q)
    print('Creating charts...',flush=True)
    charts(out,breadth,daily,daily_tech,pcr,holders,erp)
    labels={'up_pct_all':'上涨占比（含平盘分母）','down_pct_all':'下跌占比','down_amount_pct':'下跌股票成交额占比','trin_amount':'成交额 TRIN'}
    comparison='\n'.join(f"| {c['date']} | {labels[c['metric']]} | {fmt(c['video_value'])} | {fmt(c['reproduced_value'])} | {fmt(c['difference'])} |" for c in checks)
    latest_pcr=pcr.loc[pcr['date'].eq(snap['as_of'])&pcr['exchange'].eq('SSE+SZSE')&pcr['underlying'].eq('ALL')]
    pcr_v=None if latest_pcr.empty else latest_pcr.iloc[0]['pcr_volume']
    pcr_oi=None if latest_pcr.empty else latest_pcr.iloc[0]['pcr_oi']
    scope_rows='\n'.join(f"| {r['date']} | {r['scope']} | {r['active_count']:,} | {fmt(r['up_pct_all'])}% | {fmt(r['trin_amount'],4)} |" for r in scopes)
    report=f'''# 交易数据复现 v1：计算结果与口径

已完成可运行的公开数据版本。数据截至 {snap['as_of']}；历史股票数据从 {hist['start']} 开始。

这版实现了市场广度、成交额/成交量两种 TRIN、活跃度、PCR、增减持候选统计、股债收益率差候选，以及视频公式的 VW-MACD。P20/P60、MCL 和股债统计窗口属于显式假设；综合评分没有设置权重或生成曲线。

**实际数据覆盖**

- 新浪当前名册 {hist['requested']:,} 只；取得 {hist['received']:,} 只历史响应，其中 {q['history_nonempty']:,} 只有有效历史。请求失败 {len(hist['errors'])} 只，错误原文保存在质量报告。
- 较早取得的东财行情第一页报告市场总数为 5,925；两来源名册差异尚未核对完毕。因此，本版称为“当前新浪名册回溯样本”，不标作历史全市场精确全集。
- 成交量单位：{q['volume_calibrated_exact_cross_source']:,} 只通过同日跨源数量校准，{q['volume_calibrated_approximate']:,} 只采用金额和价格的近似单位校准；历史换手率对 {q['turnover_calibrated']:,} 只通过了同日跨源对照，未通过的不会当成 0。
- 股票历史回溯使用当前名册，存在退市股票缺失与存活偏差；前复权价格还可能有后续修订和小数舍入，涨跌方向并非交易所原始涨跌标志。
- 新浪快照只给时分秒，未给完整交易日期。快照归属抓取日，不能充当任意历史日期的快照。

**与视频数字直接比较**

百分比行的差值单位为百分点，TRIN 行为倍数差。视频数字本身有四舍五入；来源和名册尚未证明与原作者相同。

| 日期 | 观察量 | 视频口述 | 本版回算 | 差值 |
|---|---|---:|---:|---:|
{comparison}

这张表是匹配检验，没有为追求视频数字而调整参数。接近的数字可以支持计算逻辑；明显不符时应继续核对样本、复权、涨跌定义和时间点。

把是否包含北交所作为自然的口径对照，得到下面的结果；两种口径同时保留，没有择优删除不匹配的数字。

| 日期 | 样本口径 | 活跃样本数 | 上涨占比 | 成交额 TRIN |
|---|---|---:|---:|---:|
{scope_rows}

![市场内部结构回算](figures/market_breadth.png)

**当前快照的基础统计**

纳入 {summary['active_count']:,} 只活跃且字段完整的证券：上涨 {summary['up_count']:,} 只，下跌 {summary['down_count']:,} 只，平盘 {summary['flat_count']:,} 只。上涨占比 {fmt(summary['up_pct_all'])}%；成交额 TRIN 为 {fmt(summary['trin_amount'],4)}，成交量 TRIN 为 {fmt(summary['trin_volume'],4)}。

换手率严格大于 5% 的占比为 {fmt(summary['turnover_gt5_pct'])}%，分母为 {summary['turnover_valid_count']:,} 只换手率有效的活跃证券。没有把恰好 5% 或缺失换手率计入高换手组。

**公式与复现程度**

| 分析项 | 本版定义 | 与原作者的关系 |
|---|---|---|
| 红盘率 | 上涨家数 /（上涨＋下跌＋平盘家数） | 原理明确；股票范围和历史涨跌标志仍须对齐 |
| 成交额 TRIN |（上涨家数/下跌家数）/（上涨股票成交额/下跌股票成交额） | 与视频 4.6÷2.7 的推导吻合 |
| 成交量 TRIN | 同一结构，改用统一为股的成交量 | 标准 TRIN 口径；与成交额版本分别输出 |
| 活跃度 | 换手率＞5% 的数量 / 换手率有效数量 | 阈值来自视频；分母公开 |
| P20/P60 候选 | 前复权价格分别高于 20/60 日均价的有效样本占比 | 合理候选，未证明是原公式 |
| MCL 候选 | 净上涨家数 EMA19−EMA39；另算标准化版本 | 名称和参数不能从画面唯一确定 |
| PCR | 认沽量合计 / 认购量合计；持仓量另外计算 | 原视频标的与成交/持仓口径未公开 |
| 增减持候选 | 减持/增持股数比、记录数比、净股数 | 原图分母和去重规则未知，保留多个候选 |
| 股债差候选 | 100/PE−十年国债收益率，单位百分点 | 收益率定义、PE 范围与 12 个匹配观测点 ±2σ 均待对齐 |
| VW-MACD | SUM(C×V,12)/SUM(V,12) − SUM(C×V,26)/SUM(V,26)，DEA=EMA9 | 算式直接来自视频；初始值实现需与终端继续核对 |
| 综合评分 | 未定义 | 没有凭空设定权重 |

**PCR 已按两种口径输出**

{snap['as_of']} 上交所＋深交所 ETF 期权合计：成交量 PCR={fmt(pcr_v,4)}，持仓 PCR={fmt(pcr_oi,4)}。聚合使用总认沽除以总认购，没有对各标的 PCR 做简单平均。各交易所、各标的单列保存在结果 JSON；不含中金所指数期权。缺失交易所时，不生成假装完整的跨所汇总。

![PCR 历史序列](figures/pcr.png)

**增减持数据按两张表分别保留**

取得股东增减持明细 {len(holder_data['rows']):,} 条，董监高及相关人员明细 {len(read('executives')['rows']):,} 条。股东表按公告日过滤和分月；董监高表按变动日统计，因缺少已验证的历史公告时间，不能直接用作当时可知的回测输入。两张表可能有重叠事件，没有直接相加。

股东增减持的公告可能覆盖一段累计变动区间；本版只去除完全相同的事件键，尚未完成所有区间重叠审计。因此输出的是待对齐候选统计。

![增减持候选统计](figures/shareholders.png)

**技术与股债候选**

一目均衡表参数使用 7、22、44；云层移位暂设 22。布林带暂设 20 期、2 倍总体标准差。移位与倍数在原视频中未完整展示，均记录在质量报告；CCI 使用 14 期。没有把这些曲线自动转成买卖指令。

![技术指标](figures/technical.png)

股债候选分别保留上证市场平均 PE 与沪深 300 滚动 PE 的结果，避免把不同指数的估值序列混成一条。上证来源的盈利计算期未完全明确。实际取得的 PE 为月度/稀疏样本，没有填充成日频；因此不能提供可靠的 252 日统计带。图中仅演示 12 个匹配观测点的 ±2σ 候选，不声称与原图相同。

![股债差候选](figures/equity_bond_candidates.png)

**数据来源与使用**

行情字段按 [AKShare 官方股票文档](https://akshare.akfamily.xyz/data/stock/stock.html)及其 1.19.3 源码核对，使用新浪列表与腾讯历史行情；上证历史来自成功保存的东财响应。[上交所期权统计](https://www.sse.com.cn/assortment/options/date/)和[深交所期权统计](https://investor.szse.cn/market/option/day/index.html)提供 PCR 输入。[东财股东增减持](https://data.eastmoney.com/executive/gdzjc.html)、[董监高变动](https://data.eastmoney.com/executive/list.html)、[国债收益率](https://data.eastmoney.com/cjsj/zmgzsyl.html)分别保留来源。[乐咕乐股上证估值](https://legulegu.com/stockdata/shanghaiPE)和[指数估值](https://legulegu.com/stockdata/hs300-ttm-lyr)提供 PE 候选。

标准 [TRIN](https://chartschool.stockcharts.com/table-of-contents/market-indicators/arms-index-trin) 和 [McClellan Oscillator](https://chartschool.stockcharts.com/table-of-contents/market-indicators/mcclellan-oscillator) 定义仅作为明确标注的参照，未作为原作者隐藏算法的证据。

离线重新计算：安装 requirements.txt 后，在工具目录运行 `python analyze.py`。重新采集需运行 `python collect.py --as-of YYYY-MM-DD`，并运行可选估值采集；采集的是指定日期可取得的数据，当前名册和最新快照接口不能自动还原过去的全市场名册。

代码、标准化采集输入、计算结果、质量报告和请求来源清单均随工具包交付。请求清单保留来源与响应哈希；完整响应缓存保留于工作目录，没有重复塞入压缩包。收益、仓位和交易成本未建模，本次结果用于验证数据处理能否复现。
'''
    (out/'复现结果说明.md').write_text(report,encoding='utf-8')
    manifest=[]
    for path in sorted((ROOT/'cache').glob('*.json')):
        item=json.loads(path.read_text(encoding='utf-8'))
        manifest.append({'cache_file':path.name,'source_url':item['url'],'fetched_at':item['fetched_at'],
                         'response_sha256':item['payload_sha256']})
    inputs=[]
    for path in sorted((ROOT/'data').glob('*.json')):
        inputs.append({'file':'data/'+path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    save_json(out/'source_manifest.json',{'inputs':inputs,'requests':manifest,
              'raw_response_archive':'Original response envelopes retained during work; normalized inputs and their hashes are included in the deliverable.'})
    print('Snapshot:',json.dumps(summary,ensure_ascii=False),flush=True)
    print('Video comparison:',json.dumps(checks,ensure_ascii=False),flush=True)
    print('Quality:',q['history_received'],q['volume_calibrated'],q['turnover_calibrated'],'PCR issues',len(pcr_issues),flush=True)
    print('Analysis complete:',out,flush=True)


if __name__=='__main__':
    main()
