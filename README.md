# blues

用公开数据复现视频中的市场分析指标，保留计算公式、样本范围和与原视频的差异。

目前完成的是**指标计算、图表生成和部分技术形态识别**：市场广度、阿姆氏指标、市场活跃度、期权 PCR、增减持统计，以及日线和周线技术指标。`signals.py` 提供出云失败、CCI 背离及周日线组合等研究信号。P20/P60、MCL、股债收益率差和形态阈值采用明确标注的候选定义；综合评分、仓位管理和策略回测尚未实现。

## 已实现哪些指标

| 指标 | 实现情况 | 需要注意的口径 |
|---|---|---|
| 涨跌家数、红盘率 | 已实现 | 同时输出含平盘分母和剔除平盘分母的比例 |
| 阿姆氏 TRIN | 已实现 | 成交额版、成交量版分别计算 |
| 换手率超过 5% 的占比 | 已实现 | 严格大于 5%；分母为换手率有效的活跃证券 |
| 期权 PCR | 已实现 | 分别计算成交量和持仓量；按交易所、标的及跨所汇总 |
| 股东、高管增减持 | 已实现候选统计 | 两张数据表分开；减持/增持股数比、记录数比等均保留 |
| VW-MACD（12、26、9） | 按视频公式实现 | 日线和周线分别计算 |
| CCI（14） | 指标值和顶/底背离候选已实现 | `signals.py` 使用确认后的摆动点；容差、间隔和阈值仍需对齐原作者 |
| 一目均衡表（7、22、44） | 转换线、基准线、云层（移位 22）、未来云、迟行带因果比较 | 移位 22 已与视频读数核对；入云/出云失败见 signals.py |
| 布林带（20） | 已实现 | 2 倍样本标准差（通达信 STD，ddof=1），已与视频读数核对 |
| P20/P60 | 候选算法已实现 | 暂定义为价格高于 MA20/MA60 的股票占比 |
| MCL | 候选算法已实现 | 净上涨家数 EMA19−EMA39，另有标准化版本 |
| 股债收益率差 | 候选算法已实现 | 暂用 100/PE−十年国债收益率；原公式未知 |
| 综合评分 | 未实现 | 组成、权重和阈值未公开 |

详细公式见 [指标说明](docs/INDICATORS.md)。上表中的“已实现”表示能计算出数值，不表示已经证明与原作者的隐藏算法完全一致。

## 原始视频素材

八个分析参考视频保存在 [materials/videos](materials/videos)，使用 Git LFS 管理：

| 文件 | 大小 |
|---|---:|
| [21908.mp4](materials/videos/21908.mp4) | 23.37 MiB |
| [21909.mp4](materials/videos/21909.mp4) | 74.58 MiB |
| [21910.mp4](materials/videos/21910.mp4) | 48.06 MiB |
| [21922.mp4](materials/videos/21922.mp4) | 44.03 MiB |
| [21923.mp4](materials/videos/21923.mp4) | 82.92 MiB |
| [21924.mp4](materials/videos/21924.mp4) | 76.95 MiB |
| [21925.mp4](materials/videos/21925.mp4) | 64.42 MiB |
| [21964.mp4](materials/videos/21964.mp4) | 46.85 MiB |

在 GitHub 文件页面点击下载可获取视频。克隆仓库前需安装 [Git LFS](https://git-lfs.com/)，已有克隆可在仓库目录运行：

```bash
git lfs install
git lfs pull
```

视频是复现分析的参考素材；计算公式、确认程度和实现边界以本项目文档为准。

2026-10-24 补充的四视频分析见 [分析报告](docs/video-analysis/2026-10-24/分析报告.md)和 [18 项指标提取表](docs/video-analysis/2026-10-24/指标提取表.csv)，附来源时码、关键图证、机器转写和视频 SHA-256。新材料涉及机构披露持仓、ETF 量能比较、等权 PE、市值/GDP、债券仓位、股债利差、基差及 IV/Greeks；报告逐项说明已实现、候选和未知口径。

## 已有示例

仓库提供了截至 **2026-10-23** 的[汇总结果和图表](examples/2026-10-23/README.md)。这次取得了新浪当前名册中 **5,576 只股票**的历史数据；当时有效样本数会随上市日期、停牌和缺失字段变化。

以下是**仅选沪深 A 股**回溯样本与视频口述的对照，保留原始差异，没有为了匹配视频调整参数：

| 日期 | 指标 | 视频口述 | 本版回算 |
|---|---|---:|---:|
| 2026-09-21 | 上涨家数 / 下跌家数 | 约 4.6 | 4.6116 |
| 2026-09-21 | 上涨股票成交额 / 下跌股票成交额 | 约 2.7 | 2.5056 |
| 2026-09-21 | 成交额 TRIN | 约 1.69 | 1.8405 |
| 2026-09-22 | 上涨股票占比 | 约 43.7% | 43.8448% |

图表的主样本包含沪深京；沪深和沪深京的案例结果都保留在 [natural_scope_comparison.json](examples/2026-10-23/natural_scope_comparison.json)。股票范围、涨跌定义、复权和数据来源仍可能与原视频不同。

![市场广度、TRIN 和 P20/P60 候选](examples/2026-10-23/figures/market_breadth.png)

## 安装与测试

建议使用 Python 3.12，在项目目录创建虚拟环境：

```bash
git clone https://github.com/zlmnls/blues.git
cd blues
python -m venv .venv
```

Windows PowerShell 激活环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux 激活环境：

```bash
source .venv/bin/activate
```

然后安装依赖、运行测试：

```bash
python -m pip install -r requirements.txt
python -m unittest test_indicators -v
```

本次验证环境为 Python 3.12.14、numpy 2.3.5、pandas 3.0.1、matplotlib 3.11.2。要使用这些精确依赖版本，可安装 `requirements-tested.txt`。

运行全部测试（目前 **37 项**）：

```bash
python -m unittest discover -v
```

测试覆盖分母与平盘处理、严格的 5% 阈值、缺失值、单位缩放、VW-MACD、时间因果性、周线日期、PCR 聚合和公告日过滤，以及样本标准差、云层移位、未完成周线、出云失败和 CCI 背离。测试使用构造数据，不联网，也不要求下载市场数据；通过测试不代表策略盈利已得到验证。

## 技术形态研究信号

对包含 `date,open,high,low,close,volume` 的日线 CSV，可运行：

```bash
python signals.py path/to/daily.csv --since 2026-01-01
```

脚本输出周线方向、日线形态、确认数量和组合信号。`analyze.py` 尚未自动调用此流程，需单独运行。触云容差、冷却期、背离间隔和组合条件属于仓库的工程化候选，不等于原作者已公开的完整交易规则。股票 CSV 的信号也不会直接选择期权合约或产生订单。

## 数据观察点候选（21922–21925）

`observation_points.py` 把 10 月 14–19 日四个视频提到的数据观察点写成可测试的候选计算。视频没有公开窗口、倍数、样本范围和阈值，这些都保留为参数，不代表原作者公式：

- `rolling_band` / `band_events`：通用的均值 ± k 倍标准差带（默认样本标准差），标记触及上轨、穿越中轨和所处区间。
- `equity_bond_bottom_signal`：股债利差触及上轨记为潜在底部候选，只越过中轨记为“半山腰”。`equity_bond_candidate()` 新增 `band_ddof` 参数，默认值不变。
- `pcr_spike`：PCR 相对统计带的位置，区分“上升但未触及上轨”和“触及上轨”。
- `disclosed_holdings_change` / `holdings_as_of`：机构每期披露持股家数及变化率，按最后公告日才可用。
- `volume_context`：ETF 成交量与前 5/20 日均量（不含当日）、年内此前最大量和指定参照日的比值。
- `equal_weight_pe` / `valuation_zone`：三种明确写出的等权 PE 构造，以及机会值/危险值分区。
- `market_cap_to_gdp` / `gdp_ttm_from_quarters`：总市值 / 滚动四季度名义 GDP，只用已公布的 GDP。
- `futures_basis`：基差、基差率和年化基差率。
- `bs_price` / `greeks` / `implied_vol` / `long_put_pnl`：欧式期权定价、五个 Greeks、IV 反解，以及把买入认沽的盈亏拆成“方向和时间”与“IV 变化”两部分。
- `bottom_checklist`：只报告各底部条件是否满足或未知，不给买卖结论。

这些函数目前没有接入 `analyze.py`，也没有对应的数据采集；需要自行准备输入表。

## 采集和重新计算

完整的逐股输入和请求缓存保存在本地，不随源码提交。仓库中的 `examples/` 可以直接查看；要重新计算全部结果，先运行采集：

```bash
# --as-of 默认是北京时间当天，--limit 0 表示整个当前数据源名册
python collect.py --start 2025-10-01 --workers 6

# 补充公开估值数据；失败会记录错误，不生成模拟数据
python collect_valuation.py

# 使用保存的输入计算指标和图表，此步骤不联网
python analyze.py

# 校验本地计算输入与生成的 SHA-256 清单
python verify_inputs.py
```

也可以显式设置 `--as-of YYYY-MM-DD`。最新行情接口不支持任意历史快照，新采集应使用抓取当天；过去日期需使用已保存的快照和缓存。非交易日要核对接口实际返回的行情日期。

采集会发起数千次只读请求，可能耗时数分钟。缓存支持中断后继续，接口不可用时可能需要稍后重试。腾讯单次历史接口最多返回 640 根 K 线，设置更早的开始日期并不能保证取得完整长历史。

参数说明：

| 参数 | 默认值 | 含义 |
|---|---|---|
| `--as-of` | 北京时间当天 | 截止日期；不等于接口一定能提供该日历史快照 |
| `--start` | `2025-10-01` | 个股历史和期权统计的开始日期 |
| `--workers` | `6` | 并发请求数 |
| `--limit` | `0` | `0` 为当前名册全部股票；正数仅用于有限样本调试 |
| `--offline` | 关闭 | 只读取已有请求缓存 |

`--limit` 的有限样本不能用于全市场结论。股东、高管及国债收益率采集的开始日期在当前版本中单独设为 `2023-01-01`。

## 项目结构

```text
blues/
├── collect.py                 # 行情、期权、增减持和国债数据采集
├── collect_valuation.py       # 公开 PE 数据采集
├── fetch_data.py              # 接口适配、分页、缓存和响应哈希
├── indicators.py              # 指标计算
├── signals.py                 # 技术形态和周日线组合候选
├── observation_points.py      # 资金、估值、PCR、期权等数据观察点候选
├── analyze.py                 # 离线计算、图表和结果说明
├── test_indicators.py         # 数值和时间信息测试
├── test_signals.py            # 形态、移位与因果性测试
├── test_observation_points.py # 观察点候选的数值与时间测试
├── verify_inputs.py           # 输入完整性校验
├── requirements.txt
├── requirements-tested.txt
├── docs/                      # 公式、数据口径和限制
├── examples/2026-10-23/        # 已生成的汇总示例
├── data/                      # 本地采集输入，不入库
├── cache/                     # 本地逐请求响应，不入库
└── results/                   # 本地计算输出，不入库
```

## 每日看板（GitHub Pages）

网址：https://zlmnls.github.io/blues/

- 标的：上证指数、深证成指、创业板指、纽约金（COMEX GC 连续），日线和周线。
- 指标：一目均衡表（7/22/44，云前移 22）、VW-MACD 12/26/9、BOLL(20，样本标准差)、CCI(14)，`signals.py` 里的博主规则，以及 `observation_points.py` 里能自动取数的观察点。
- 每只标的都标出：现价在云上/云中/云下、入云价和出云价（云上下沿）、下一根 K 线的云、最近一次入云/出云/出云失败的日期；博主点名的价位（上证 4000/3600/3500/3400）离现价多远、最近一次收盘穿越；纽约金另列你自己的分批计划点位和触发状态。
- 只有博主在视频里说过的规则才标“卖出/看空”，每条注明视频编号和时间；他没给买入规则，页面写“博主未给出买入规则”。
- 主站部署在腾讯云国内服务器：http://118.25.109.118:28473/ （nginx 独立 server 块，只读静态文件，根目录就是 `dashboard/`）。GitHub Pages（https://zlmnls.github.io/blues/）保留为备用页面。
- 更新：服务器 cron（`/etc/cron.d/blues-dashboard`）在北京时间周一到周六 16:30 和 19:00 运行 `deploy/update.sh`：跑 `build_dashboard.py`（失败 60 秒后重试一次），写 `dashboard/data/latest.json`，并按北京日期存档到 `dashboard/data/archive/YYYY-MM-DD.json`；然后把 `dashboard/data` 提交并推送到 GitHub 当备份（带超时和重试，推送失败不影响服务器上的看板）。日志在 `/var/log/blues/update.log`，按周轮转、超过 5 MB 也轮转。`.github/workflows/dashboard.yml` 已去掉定时，只能手动触发，避免两边同时写数据。部署文件在 `deploy/`。
- 数据源：A 股指数用腾讯证券（备用新浪、Yahoo），纽约金用东方财富 COMEX 黄金连续 GC00Y（含成交量；国内服务器访问 Yahoo 会被 429 限流，备用 Yahoo、新浪外盘），全市场快照用新浪，PCR 用上交所 + 深交所两所 ETF 期权合计，资金流向用东方财富大盘资金流（push2his），股债利差用中证指数公司 + 东方财富数据中心。深交所期权和东方财富 push2 只在国内服务器上能拿到；push2 对同一 IP 短时间多次请求会暂时断开，所以每次更新只请求两次。
- 本地生成：`python build_dashboard.py --out dashboard`，然后在 `dashboard/` 下 `python -m http.server` 打开。

## 数据与复现边界

- 当前股票名册回溯会遗漏已经退市的证券，不能直接视为历史全市场全集。
- 历史涨跌方向由腾讯前复权收盘价变化计算，可能受舍入和后续复权修订影响。
- 股东统计按公告日过滤；董监高明细尚缺经过验证的历史公告时间，两张表没有直接相加。
- PCR 目前覆盖上交所、深交所 ETF 期权，不含中金所指数期权。跨标的汇总使用总认沽除以总认购，不对各标的比例简单平均。
- 实际取得的 PE 是稀疏/月度样本，未填充成日频。股债图的统计带使用 12 个匹配观测点，只是候选展示。
- “顶/底背离”“出云失败”和部分技术组合信号已在 `signals.py` 中实现候选规则；机构持仓变化、等权 PE、市值/GDP、期货基差和期权 IV/Greeks 已在 `observation_points.py` 中有计算候选，但没有数据采集；债券仓位因口径不明仍未实现。当前版本没有交易执行和收益回测。
- 图表优先使用 Windows 微软雅黑。其他平台若中文显示异常，可修改 `analyze.py` 的 `setup_plot()`，指定本地中文字体。

数据来源、单位和时间可得性见 [数据说明](docs/DATA.md)。
