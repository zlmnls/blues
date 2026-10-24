# 指标计算与实现状态

以下区分视频明确给出的计算、标准指标结构和未确认的候选定义。日线的 N 期为 N 根日 K，周线的 N 期为 N 根周 K；横截面占比按交易日分别统计。

## 市场内部结构

设 U、D、F 分别为上涨、下跌、平盘家数；AU、AD 分别为上涨、下跌组的成交额；VU、VD 为统一单位后的成交量。

```text
红盘率（含平盘） = U / (U + D + F) × 100%
红盘率（剔除平盘） = U / (U + D) × 100%

成交额 TRIN = (U / D) / (AU / AD)
成交量 TRIN = (U / D) / (VU / VD)

活跃度 = 换手率严格大于 5% 的股票数量 / 换手率有效数量 × 100%
```

成交额 TRIN 也等于平均每只下跌股票的成交额除以平均每只上涨股票的成交额。它描述成交分布，不能直接识别机构账户的净流入或净流出。

统计中仅纳入价格、涨跌方向和成交额有效的活跃证券；缺失值不会填为 0。成交量 TRIN 的有效样本数另外输出，避免单位未知的记录悄悄混入。分母为零时返回未知，不输出无穷大。

## 技术指标

### VW-MACD（12、26、9）

这一算式直接来自视频公式画面：

```text
VWMA_N = SUM(C × V, N) / SUM(V, N)
DIF = VWMA_12 − VWMA_26
DEA = EMA_9(DIF)
柱状图 = 2 × (DIF − DEA)
```

C 为收盘价，V 为成交量。代码要求完整窗口；DEA 使用首个有效观察值启动递推，并保留预热期。早期初始化可能与终端不同，应继续对齐。快慢线穿越零轴与柱状图穿越零轴是不同条件；当前输出指标值，没有自动生成穿越信号。

### 一目均衡表（7、22、44）

```text
转换线 = (7期最高价 + 7期最低价) / 2
基准线 = (22期最高价 + 22期最低价) / 2
云 A = (转换线 + 基准线) / 2
云 B = (44期最高价 + 44期最低价) / 2
```

云层移位暂设 22，为显式假设。只使用当时已经产生的历史值构成当前云层；迟行带尚未实现。“入云”“反弹出云失败”的自动形态识别也尚未实现。

### 布林带与 CCI

```text
布林中轨 = MA_20(C)
布林上轨 = 中轨 + 2 × STD_20(C)
布林下轨 = 中轨 − 2 × STD_20(C)

TP = (H + L + C) / 3
CCI_14 = (TP − MA_14(TP)) / (0.015 × MAD_14(TP))
```

布林带暂用总体标准差（ddof=0），倍数 2 尚未由原视频确认。MAD 是同一窗口中各典型价格与该窗口均值之差的绝对值平均。CCI 顶背离识别尚未实现。

## PCR

```text
成交量 PCR = 认沽成交量合计 / 认购成交量合计
持仓 PCR = 认沽持仓量合计 / 认购持仓量合计
```

分别按交易所、标的和两所合计输出。合计值由数量先求和再相除，不是各个 PCR 的算术平均。某一交易所缺失时，暂不输出假装完整的跨所合计。原视频的期权标的和口径未公开。

## 自制指标的候选定义

| 标签 | 当前候选 | 未确认内容 |
|---|---|---|
| P20/P60 | 前复权价格高于 MA20/MA60 的有效股票占比 | 是否就是原作者定义、价格口径和股票范围 |
| MCL | 净上涨家数 EMA19−EMA39；另算按涨跌总家数标准化的版本 | 原算法、是否标准化、初始化方式 |
| MCL 展示值 | 50 + 0.1 × 原始候选 MCL | 原图有相应缩放标签，但不能证明候选本体正确 |
| 股东增减持比例 | 减持/增持股数比、减持/增持记录数比、减持记录占比 | 原图分母、去重和累计区间处理 |
| 股债收益率差 | 100/PE − 十年国债收益率（%） | 股票收益率定义、指数范围、窗口及标准差倍数 |
| 综合评分 | 未定义、未生成 | 所有组成、权重、平滑及触发阈值 |

MCL 候选的 EMA 使用首个观察值启动，前 39 个观察值作为预热。股债数据为稀疏/月度 PE，图中使用 12 个匹配观测点的均值 ±2σ，不能当作日频统计带或原作者算法。

## 参考定义

- [标准 TRIN](https://chartschool.stockcharts.com/table-of-contents/market-indicators/arms-index-trin)
- [McClellan Oscillator](https://chartschool.stockcharts.com/table-of-contents/market-indicators/mcclellan-oscillator)
- [一目均衡表](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/ichimoku-cloud)
- [布林带](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/bollinger-bands)
- [CCI](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/commodity-channel-index-cci)

这些标准定义用于解释指标，不作为原作者隐藏算法已经被确认的证据。
