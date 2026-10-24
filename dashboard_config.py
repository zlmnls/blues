"""Static inputs for the dashboard: instruments, the blogger's levels and rules, the gold plan.

Every level and rule carries its source. Video ids map to episodes of 《金融宝藏》:
21908 = 第20集, 21909 = 第21集, 21910 = 第18集(按内容推断), 21922 = 第16集(推断),
21923 = 第19集(推断), 21924 / 21925 = 第16集前后(推断). Timestamps come from the local
machine transcripts and may be off by a few seconds.
"""

INSTRUMENTS = [
    {'key': 'sh000001', 'name': '上证指数', 'market': 'cn', 'tencent': 'sh000001', 'sina': 'sh000001', 'yahoo': '000001.SS', 'digits': 2},
    {'key': 'sz399001', 'name': '深证成指', 'market': 'cn', 'tencent': 'sz399001', 'sina': 'sz399001', 'yahoo': '399001.SZ', 'digits': 2},
    {'key': 'sz399006', 'name': '创业板指', 'market': 'cn', 'tencent': 'sz399006', 'sina': 'sz399006', 'yahoo': '399006.SZ', 'digits': 2},
    {'key': 'gc', 'name': '纽约金（COMEX GC 连续）', 'market': 'gold', 'yahoo': 'GC=F', 'digits': 1},
]

EP = {'21908': '21908（第20集）', '21909': '21909（第21集）', '21910': '21910（第18集，推断）',
      '21922': '21922（第16集，推断）', '21923': '21923（第19集，推断）', '21924': '21924', '21925': '21925'}

# Price levels the blogger named in the videos. kind: target / resistance / mention.
# action is only filled where he tied a buy or sell view to the level.
BLOGGER_LEVELS = {
    'sh000001': [
        {'price': 4000, 'label': '4000 点', 'kind': 'resistance',
         'action': '卖出/看空参照：9 月 21 日“市场在冲击 4000 点”，他在 9 月 22 日发短期风险提示，称那里是最高点',
         'source': EP['21910'] + ' 03:45–03:49（225.5–229.3 秒）'},
        {'price': 3600, 'label': '3600 点', 'kind': 'mention',
         'action': '博主未给出买卖规则：10 月 22 日盘中口述“这么快就 3600”，只是描述下跌速度',
         'source': EP['21909'] + ' 04:10–04:26'},
        {'price': 3500, 'label': '3500 点', 'kind': 'target',
         'action': '看空目标：“3500 百分之一万守不住，还要往下”；击穿后再看是否企稳。不是买点，博主没有给出买入条件',
         'source': EP['21908'] + ' 00:21–00:37；' + EP['21909'] + ' 04:10–04:29'},
        {'price': 3400, 'label': '3400 点', 'kind': 'target',
         'action': '看空目标：“可能 3400，也可能 3500，但现在这个位置绝对不是低”。博主没有给出买入条件',
         'source': EP['21924'] + ' 04:40–04:45（280.8–285.7 秒）'},
    ],
}

# Dated chart notes the blogger pointed at (shown as markers when the date is on the chart).
BLOGGER_DATES = {
    'sh000001': [
        {'date': '2026-09-22', 'tf': 'daily', 'label': '博主 9/22 短期风险提示',
         'source': EP['21909'] + ' 02:56–03:56；' + EP['21910'] + ' 00:00–00:07'},
        {'date': '2026-08-20', 'tf': 'daily', 'label': '博主：出云失败①', 'source': EP['21909'] + ' 03:20–03:26'},
        {'date': '2026-09-08', 'tf': 'daily', 'label': '博主：出云失败②', 'source': EP['21909'] + ' 03:20–03:26'},
        {'date': '2026-07-24', 'tf': 'weekly', 'label': '博主：周线入云（趋势结束的开始）', 'source': EP['21909'] + ' 02:12–02:26'},
    ],
}

# The technical rules the blogger stated (episode 21). Only bearish rules were stated.
BLOGGER_RULES = [
    {'id': 'w_enter_cloud', 'tf': 'weekly', 'side': 'sell', 'label': '周线入云',
     'detail': '周线价格从云上方进入云层，“代表了趋势结束的开始”', 'source': EP['21909'] + ' 02:12–02:26'},
    {'id': 'w_vw_below_zero', 'tf': 'weekly', 'side': 'sell', 'label': '周线 VW-MACD 快慢线跌穿零轴',
     'detail': 'DIF 和 DEA 都在零轴下方', 'source': EP['21909'] + ' 02:12–02:26'},
    {'id': 'w_boll_upper_reject', 'tf': 'weekly', 'side': 'sell', 'label': '周线布林上轨未突破',
     'detail': '“在上轨顶部，没有突破上轨，意味着要失能了”', 'source': EP['21909'] + ' 02:26–02:56'},
    {'id': 'w_cci_top_div', 'tf': 'weekly', 'side': 'sell', 'label': '周线 CCI 顶背离',
     'detail': '价格向上、CCI 高点向下', 'source': EP['21909'] + ' 02:26–02:56'},
    {'id': 'd_cloud_exit_fail', 'tf': 'daily', 'side': 'sell', 'label': '日线出云失败',
     'detail': '跌破云后再出云，受压力回落；“三出”的位置“都是空的地方”', 'source': EP['21909'] + ' 02:56–03:26'},
    {'id': 'd_vw_below_zero', 'tf': 'daily', 'side': 'sell', 'label': '日线 VW-MACD 快慢线跌破零轴',
     'detail': '9 月 22 日快慢线跌破零轴，与资金分析吻合', 'source': EP['21909'] + ' 03:26–03:56'},
    {'id': 'd_boll_upper_reject', 'tf': 'daily', 'side': 'sell', 'label': '日线布林上轨',
     'detail': '“日线的布林带也是在上轨的地方，是放空的地方”', 'source': EP['21909'] + ' 03:56–04:26'},
    {'id': 'd_cci_top_div', 'tf': 'daily', 'side': 'sell', 'label': '日线 CCI 顶背离',
     'detail': '“把这几个高点连起来，也能发现它是一个顶背离”', 'source': EP['21909'] + ' 03:56–04:26'},
    {'id': 'combo_short', 'tf': 'daily', 'side': 'sell', 'label': '组合：周线偏空 + 日线出云失败 + 日线 VW-MACD 零轴下',
     'detail': '9 月 22 日的组合，他据此提示短期大风险。组合的判定条件是本仓库的工程化写法', 'source': EP['21909'] + ' 02:56–03:56'},
]

BUY_RULE_NOTE = '博主未给出买入规则：第 21 集只讲了看空/放空的用法。代码里的“云支撑恢复、布林下轨拒绝、CCI 底背离”是本仓库按对称做的镜像，不是博主说的，所以不标“买入”。'

# Data observation points: what the blogger said about each, and whether he gave a rule.
OBS_NOTES = {
    'pcr': {'rule': '风险提示（看空）：PCR 柱突然冲向统计带上轨时，他判断短期有风险；10 月 16 日那根“还没有到上轨”',
            'source': EP['21922'] + ' 01:58–02:47', 'has_rule': True},
    'equity_bond': {'rule': '潜在底部证据：股债利差触及标准差带上轨，对应 2024 年 9 月和 2025 年 4 月的低点；只越过中轨“还不是底”。他没有说触上轨就买入',
                    'source': EP['21924'] + ' 04:10–04:46', 'has_rule': False},
    'equal_pe': {'rule': '画面阈值：危险值 14.18、机会值 11.61；2026-10-16 画面读数 PE 13、点位 4170.61。博主未给出买卖规则，只称 13 是“高估”',
                 'source': EP['21922'] + ' 02:48–02:58', 'has_rule': False, 'danger': 14.18, 'opportunity': 11.61,
                 'note': '中证指数公司公布的沪深300 市盈率在 10/16 是 12.88、收盘 4170.61，和博主画面的 PE 13、点位 4170.61 对得上，所以推断他说的“等权 PE”就是这个口径，阈值用它来比。全市场 PE 中位数只作参考，口径不同，不套阈值'},
    'holdings': {'rule': '机构披露持股家数收缩（汇金 144 家→17 家）被他当作偏空背景。博主未给出买卖规则',
                 'source': EP['21922'] + ' 00:29–01:03', 'has_rule': False},
    'etf_volume': {'rule': '300ETF 量比上周/上月稍增，但远低于 7 月、1 月，他说“不是放量”。博主未给出买卖规则',
                   'source': EP['21924'] + ' 00:46–01:23', 'has_rule': False},
    'cap_gdp': {'rule': '只当估值约束提及。博主未给出阈值和买卖规则', 'source': EP['21924'] + ' 03:54–04:09', 'has_rule': False},
    'basis': {'rule': '只点名“升贴水”，没有展示算法、合约和阈值。博主未给出买卖规则', 'source': EP['21922'] + ' 02:58–03:03', 'has_rule': False},
    'iv': {'rule': '倾向在 IV 低时买认沽；IV 下降会侵蚀买方收益。没有给出“低”的数值。博主未给出可量化的买卖规则',
           'source': EP['21923'] + ' 03:53–04:09、04:55–05:03；' + EP['21925'] + ' 00:34–00:53', 'has_rule': False},
    'breadth': {'rule': '9 月 21、22 日的涨跌家数、成交额比和阿姆氏指标让他判断短期风险。没有给出固定阈值', 'source': EP['21910'], 'has_rule': False},
    'insider': {'rule': '高管、股东增减持比例偏向减持被当作看空依据之一。具体算法和阈值没公开', 'source': EP['21908'], 'has_rule': False},
}

# The user's own gold plan (set up on 2026-10-23 from the user's chart, not from the blogger).
# Channel lines move down about 4 USD per trading day from 2026-10-23.
GOLD_PLAN = {
    'source': '你的黄金分批计划（2026-10-23 按你的图测算），不是布鲁斯的观点',
    'anchor_date': '2026-10-23',
    'channel_step_per_day': -4.0,
    'channel': [
        {'id': 'ch_upper', 'label': '通道上轨', 'base': 4590.0},
        {'id': 'ch_mid', 'label': '通道中轨', 'base': 4048.0},
        {'id': 'ch_lower', 'label': '通道下轨', 'base': 3500.0},
    ],
    'fixed': [
        {'price': 4700, 'label': '九月反弹高点 约 4700', 'kind': 'resistance'},
        {'price': 4656, 'label': '38.2% 回撤 4656', 'kind': 'resistance'},
        {'price': 4356, 'label': '50% 回撤 4356', 'kind': 'resistance'},
        {'price': 4160, 'label': '日线 MA10/MA20 区上沿 4160（10/23 测算）', 'kind': 'trigger'},
        {'price': 4140, 'label': '日线 MA10/MA20 区下沿 4140（10/23 测算）', 'kind': 'trigger'},
        {'price': 4056, 'label': '61.8% 回撤 4056', 'kind': 'support'},
        {'price': 4000, 'label': '整数关口 4000', 'kind': 'support'},
        {'price': 3950, 'label': '夏天低点区上沿 3950', 'kind': 'support'},
        {'price': 3900, 'label': '夏天低点区下沿 3900', 'kind': 'support'},
        {'price': 3630, 'label': '78.6% 回撤 3630', 'kind': 'support'},
        {'price': 3086.1, 'label': '起涨点 3086.1（底线）', 'kind': 'support'},
    ],
    'fomc_result_date': '2026-10-29',
}
