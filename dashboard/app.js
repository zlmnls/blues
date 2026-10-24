'use strict';
// Dashboard front end: reads data/index.json and one dated JSON, renders tables and ECharts.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? '—' : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (v) => (v === null || v === undefined ? '—' : (v > 0 ? '+' : '') + fmt(v, 2) + '%');
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
let DATA = null, CUR = null, TF = 'daily', charts = [];

async function getJSON(u) { const r = await fetch(u, { cache: 'no-cache' }); if (!r.ok) throw new Error(u + ' ' + r.status); return r.json(); }

async function init() {
  let idx = { dates: [], latest: null };
  try { idx = await getJSON('data/index.json'); } catch (e) { /* first run */ }
  const sel = $('#datePick');
  sel.innerHTML = '<option value="latest">最新</option>' + idx.dates.map((d) => `<option value="${d}">${d}</option>`).join('');
  const want = new URLSearchParams(location.search).get('date');
  if (want && idx.dates.includes(want)) sel.value = want;
  sel.onchange = () => { const u = new URL(location); if (sel.value === 'latest') u.searchParams.delete('date'); else u.searchParams.set('date', sel.value); history.replaceState(null, '', u); load(sel.value); };
  load(sel.value);
}

async function load(which) {
  try { DATA = await getJSON(which === 'latest' ? 'data/latest.json' : `data/archive/${which}.json`); }
  catch (e) { $('#updated').textContent = '数据读取失败：' + e.message; return; }
  $('#updated').textContent = `生成于北京时间 ${DATA.generated_at_beijing}｜A 股数据日 ${DATA.a_share_date || '—'}｜纽约金数据日 ${DATA.gold_date || '—'}（纽约时间）`;
  const p = DATA.params; $('#params').textContent = `一目均衡表 ${p.ichimoku}｜VW-MACD ${p.vw_macd}｜BOLL ${p.boll}｜CCI ${p.cci}`;
  $('#disclaimer').textContent = DATA.disclaimer;
  const keys = Object.keys(DATA.instruments);
  if (!CUR || !keys.includes(CUR)) CUR = new URLSearchParams(location.search).get('i') || keys[0];
  if (!keys.includes(CUR)) CUR = keys[0];
  $('#tabs').innerHTML = keys.map((k) => `<button data-k="${k}" class="${k === CUR ? 'on' : ''}">${esc(DATA.instruments[k].name)}</button>`).join('') + '<button data-k="#obs">数据观察点</button>';
  $('#tabs').querySelectorAll('button').forEach((b) => b.onclick = () => { if (b.dataset.k === '#obs') { $('#obs').scrollIntoView({ behavior: 'smooth' }); return; } CUR = b.dataset.k; renderInst(); $('#tabs').querySelectorAll('button').forEach((x) => x.classList.toggle('on', x.dataset.k === CUR)); });
  renderInst(); renderObs(); renderMisc();
}

function signalTag(text, side) { return `<span class="tag ${side}">${esc(text)}</span>`; }

function renderInst() {
  charts.forEach((c) => c.dispose()); charts = [];
  const I = DATA.instruments[CUR];
  if (!I || I.status === '无数据') { $('#lede').textContent = ''; $('#inst').innerHTML = `<div class="card">${esc(I?.name)}：无数据（${esc(I?.reason)}）</div>`; return; }
  const L = I.daily.latest, dc = I.daily.cloud, wc = I.weekly.cloud;
  const chg = L.change_pct;
  $('#lede').innerHTML = `${esc(I.name)} ${esc(L.date)} 收盘 <b>${fmt(L.close)}</b> <span class="${chg >= 0 ? 'up' : 'down'}">${pct(chg)}</span>。日线在<b>${dc.position}</b>，周线在<b>${wc.position}</b>，周线方向${I.weekly_bias || '—'}。`;
  let h = '';
  // signals
  const act = I.rules.filter((r) => r.active);
  h += `<div class="card"><h3>买卖信号</h3><ul class="signals">`;
  if (act.length) act.forEach((r) => { h += `<li>${signalTag('卖出/看空', 'sell')} ${r.tf === 'weekly' ? '周线' : '日线'}：${esc(r.label)}${r.last_date ? `（自 ${r.last_date}）` : ''} — ${esc(r.detail)} <span class="src">出处 ${esc(r.source)}</span>${r.applies_note ? ` <span class="src">${esc(r.applies_note)}</span>` : ''}</li>`; });
  else h += `<li>${signalTag('今天没有博主规则触发', 'none')}</li>`;
  (I.levels || []).filter((l) => l.owner === 'blogger' && (l.crossed_today || l.touched_today)).forEach((l) => { h += `<li>${signalTag('博主点位', 'warn')} 今天${l.crossed_today ? '收盘' + (l.last_cross ? l.last_cross.direction : '穿过') : '盘中触及'} ${esc(l.label)}：${esc(l.action)} <span class="src">出处 ${esc(l.source)}</span></li>`; });
  h += `<li>${signalTag('买入', 'none')} ${esc(I.buy_rule_note)}</li>`;
  if (I.gold_plan) {
    I.gold_plan.batches.forEach((b) => { const on = /已触发|候选/.test(b.status) && !/未触发/.test(b.status); h += `<li>${signalTag((b.side === 'buy' ? '买入 ' : '卖出 ') + b.name, on ? b.side : 'none')} ${esc(b.status)} — ${esc(b.rule)}。${esc(b.detail)} <span class="src">${esc(I.gold_plan.source)}</span></li>`; });
  }
  h += `</ul></div>`;
  // cloud
  h += `<div class="card"><h3>出云 / 入云点位</h3><div class="tablewrap"><table><tr><th>周期</th><th>当前位置</th><th>云上沿</th><th>云下沿</th><th>关键价</th><th>距现价</th><th>下一根 K 线的云</th></tr>`;
  [['日线', dc], ['周线', wc]].forEach(([n, c]) => { c.lines.forEach((ln, i) => { h += `<tr>${i === 0 ? `<td rowspan="2">${n}</td><td rowspan="2">${c.position}<br><span class="small">${esc(c.cloud_color)}</span></td><td rowspan="2" class="num">${fmt(c.cloud_top)}</td><td rowspan="2" class="num">${fmt(c.cloud_bottom)}</td>` : ''}<td>${esc(ln.label)}<br><b class="num">${fmt(ln.price)}</b></td><td class="num">${pct(ln.distance_pct)}</td>${i === 0 ? `<td rowspan="2" class="num">上 ${fmt(c.next_cloud_top)}<br>下 ${fmt(c.next_cloud_bottom)}</td>` : ''}</tr>`; }); });
  h += `</table></div><div class="tablewrap"><table><tr><th>最近一次</th><th>日线</th><th>周线（周末日期）</th></tr>`;
  dc.last_events.forEach((e, i) => { const w = wc.last_events[i]; const cell = (x) => x.date ? `${x.date}<br><span class="small">收 ${fmt(x.close)}，云 ${fmt(x.cloud_bottom)}～${fmt(x.cloud_top)}</span>` : '<span class="small">数据范围内没有</span>'; h += `<tr><td>${esc(e.label)}</td><td class="num">${cell(e)}</td><td class="num">${cell(w)}</td></tr>`; });
  h += `</table></div><p class="small">云的上下沿是先行 A/B 中较高/较低的一条；按收盘价判断。周线最后一根${I.weekly.last_week_complete ? '已收完' : '<b>还没收完（本周未结束）</b>'}。</p></div>`;
  // chart
  h += `<div class="card"><div class="seg"><button data-tf="daily" class="${TF === 'daily' ? 'on' : ''}">日线</button><button data-tf="weekly" class="${TF === 'weekly' ? 'on' : ''}">周线</button></div><div id="mainChart" class="chart"></div><p class="small">灰色带是云（先行 A 实线、先行 B 虚线），右侧 +1～+22 是已知的未来云。水平线是博主（或你的计划）的点位，只画离现价 20% 以内的。标记：入/出 = 入云/出云，败 = 出云失败，卖 = 博主组合看空信号。</p></div>`;
  // levels
  h += `<div class="card"><h3>${I.gold_plan ? '观测点位（博主没讲过黄金，下面是你的计划点位）' : '博主观测点位'}</h3>`;
  if (!I.levels.length) h += `<p>${esc(I.levels_note)}</p>`;
  else {
    h += `<div class="tablewrap"><table><tr><th>点位</th><th>价位</th><th>现价距离</th><th>位置</th><th>最近一次收盘穿越</th><th>博主怎么说 / 买卖含义</th></tr>`;
    I.levels.forEach((l) => { h += `<tr><td>${esc(l.label)}</td><td class="num">${fmt(l.price)}</td><td class="num">${fmt(l.distance)}<br>${pct(l.distance_pct)}</td><td>${esc(l.side)}${l.crossed_today ? '<br><b>今天穿过</b>' : ''}</td><td class="num">${l.last_cross ? `${l.last_cross.date}<br>${l.last_cross.direction}` : '数据范围内没有'}</td><td>${esc(l.action || (l.owner === 'plan' ? '你的计划点位' : '博主未给出买卖规则'))}<div class="src">${esc(l.source || '')}</div></td></tr>`; });
    h += `</table></div>`;
    if (I.gold_plan) { const ck = I.gold_plan.checks; h += `<p class="small">有效突破/跌破按你的规则：连续 3 个收盘在另一侧，或收盘超过 1%。` + Object.entries(ck).map(([k, v]) => `${k}：连续 ${v.consecutive_closes_beyond} 天、超出 ${fmt(v.beyond_pct)}%，${v.valid ? '<b>已成立</b>' : '未成立'}`).join('；') + `。MA10 ${fmt(I.gold_plan.ma10, 1)}，MA20 ${fmt(I.gold_plan.ma20, 1)}。</p>`; }
  }
  h += `</div>`;
  // indicator table
  const W = I.weekly.latest;
  const rows = [['收盘', 'close', 2], ['转换线（7）', 'tenkan', 2], ['基准线（22）', 'kijun', 2], ['先行 A', 'cloud_a', 2], ['先行 B', 'cloud_b', 2], ['VW-MACD DIF', 'vw_dif', 3], ['VW-MACD DEA', 'vw_dea', 3], ['VW-MACD 柱', 'vw_hist', 3], ['BOLL 上轨', 'boll_upper', 2], ['BOLL 中轨', 'boll_mid', 2], ['BOLL 下轨', 'boll_lower', 2], ['CCI(14)', 'cci', 1]];
  h += `<div class="card"><h3>指标最新值</h3><div class="tablewrap"><table><tr><th>指标</th><th>日线 ${esc(L.date)}</th><th>周线 ${esc(W.date)}</th></tr>` + rows.map(([n, k, d]) => `<tr><td>${n}</td><td class="num">${fmt(L[k], d)}</td><td class="num">${fmt(W[k], d)}</td></tr>`).join('') + `</table></div><p class="small">数据源：${esc(I.source)}。${(I.notes || []).map(esc).join('；')}</p></div>`;
  // rules
  h += `<div class="card"><h3>博主的技术规则（第 21 集）</h3><div class="tablewrap"><table><tr><th>规则</th><th>今天</th><th>最近一次</th><th>出处</th></tr>` + I.rules.map((r) => `<tr><td>${r.tf === 'weekly' ? '周线' : '日线'}：${esc(r.label)}<div class="small">${esc(r.detail)}</div></td><td>${r.active ? signalTag('卖出/看空', 'sell') : signalTag('未触发', 'none')}</td><td class="num">${r.last_date || '—'}</td><td class="src">${esc(r.source)}</td></tr>`).join('') + `</table></div><p class="small">${esc(I.buy_rule_note)}${CUR !== 'sh000001' ? ' 博主只对上证指数讲过这套规则，套用到本标的是延伸。' : ''}</p></div>`;
  $('#inst').innerHTML = h;
  $('#inst').querySelectorAll('.seg button').forEach((b) => b.onclick = () => { TF = b.dataset.tf; renderInst(); });
  drawMain(I);
}

function drawMain(I) {
  const S = I[TF].series, C = I[TF].cloud, up = css('--up') || '#C0392B', down = css('--down') || '#1E8449', ink = css('--ink') || '#141414', muted = css('--muted') || '#6E6C68', rule = css('--rule') || '#DCDAD5';
  const n = S.date.length, fut = S.future_cloud_a.map((_, i) => '+' + (i + 1));
  const x = S.date.concat(fut), pad = (a) => a.concat(fut.map(() => null));
  const ca = S.cloud_a.concat(S.future_cloud_a), cb = S.cloud_b.concat(S.future_cloud_b);
  const lo = ca.map((v, i) => (v == null || cb[i] == null ? null : Math.min(v, cb[i])));
  const band = ca.map((v, i) => (v == null || cb[i] == null ? null : Math.abs(v - cb[i])));
  const k = S.date.map((_, i) => [S.open[i], S.close[i], S.low[i], S.high[i]]);
  const last = S.close[n - 1], hi = Math.max(...S.high.filter((v) => v != null)), lw = Math.min(...S.low.filter((v) => v != null));
  const lv = (I.levels || []).filter((l) => Math.abs(l.price / last - 1) <= 0.2);
  const markLines = lv.map((l) => ({ yAxis: l.price, name: l.label, lineStyle: { color: l.owner === 'plan' ? muted : ink, type: l.owner === 'plan' ? 'dotted' : 'dashed', width: 1 }, label: { formatter: `${l.label}`, position: 'insideEndTop', color: l.owner === 'plan' ? muted : ink, fontSize: 10 } }));
  const pos = new Map(S.date.map((d, i) => [d, i]));
  const pts = [];
  const short = { enter_from_above: '入', enter_from_below: '入', exit_up: '出', exit_down: '出', exit_fail: '败' };
  (C.marks || []).forEach((m) => { const i = pos.get(m.date); if (i === undefined) return; const above = m.type === 'exit_fail' || m.type === 'enter_from_above' || m.type === 'exit_down'; pts.push({ coord: [m.date, above ? S.high[i] : S.low[i]], value: short[m.type], name: m.label + ' ' + m.date, symbol: 'pin', symbolSize: 26, symbolRotate: above ? 0 : 180, itemStyle: { color: m.type === 'exit_up' || m.type === 'enter_from_below' ? up : (m.type === 'exit_fail' ? ink : down) }, label: { fontSize: 10, color: '#fff', offset: [0, above ? 0 : 6] } }); });
  ((S.flags || {}).short_risk_signal || []).forEach((d) => { const i = pos.get(d); if (i === undefined) return; pts.push({ coord: [d, S.high[i]], value: '卖', name: '博主组合看空信号 ' + d, symbol: 'pin', symbolSize: 32, itemStyle: { color: down }, label: { color: '#fff', fontSize: 11 } }); });
  (I.blogger_dates || []).filter((b) => b.tf === TF).forEach((b) => { let i = pos.get(b.date); if (i === undefined && TF === 'weekly') { i = S.date.findIndex((d) => d >= b.date); } if (i === undefined || i < 0) return; pts.push({ coord: [S.date[i], S.high[i]], value: '博', name: b.label + '（' + b.source + '）', symbol: 'roundRect', symbolSize: [20, 16], symbolOffset: [0, -22], itemStyle: { color: ink }, label: { color: css('--ground') || '#fff', fontSize: 10 } }); });
  const series = [
    { name: 'K线', type: 'candlestick', data: k, xAxisIndex: 0, yAxisIndex: 0, itemStyle: { color: up, color0: down, borderColor: up, borderColor0: down }, markLine: { symbol: 'none', silent: true, data: markLines }, markPoint: { data: pts, tooltip: { formatter: (p) => p.name } } },
    { name: '云底', type: 'line', data: lo, stack: 'cloud', symbol: 'none', lineStyle: { opacity: 0 }, tooltip: { show: false }, silent: true },
    { name: '云', type: 'line', data: band, stack: 'cloud', symbol: 'none', lineStyle: { opacity: 0 }, areaStyle: { color: muted, opacity: 0.22 }, silent: true },
    { name: '先行A', type: 'line', data: ca, symbol: 'none', lineStyle: { width: 1, color: muted } },
    { name: '先行B', type: 'line', data: cb, symbol: 'none', lineStyle: { width: 1, color: muted, type: 'dashed' } },
    { name: 'BOLL上', type: 'line', data: pad(S.boll_upper), symbol: 'none', lineStyle: { width: 1, color: '#8E44AD' } },
    { name: 'BOLL中', type: 'line', data: pad(S.boll_middle_20), symbol: 'none', lineStyle: { width: 1, color: '#B9770E' } },
    { name: 'BOLL下', type: 'line', data: pad(S.boll_lower), symbol: 'none', lineStyle: { width: 1, color: '#2471A3' } },
    { name: 'VW柱', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: pad(S.vw_histogram.map((v) => ({ value: v, itemStyle: { color: v >= 0 ? up : down } }))) },
    { name: 'DIF', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: pad(S.vw_dif), symbol: 'none', lineStyle: { width: 1, color: ink } },
    { name: 'DEA', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: pad(S.vw_dea), symbol: 'none', lineStyle: { width: 1, color: '#B9770E' } },
    { name: 'CCI', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: pad(S.cci), symbol: 'none', lineStyle: { width: 1, color: ink }, markLine: { symbol: 'none', silent: true, lineStyle: { color: rule, type: 'dashed' }, label: { show: false }, data: [{ yAxis: 100 }, { yAxis: -100 }] },
      markPoint: { symbol: 'pin', symbolSize: 22, data: ((S.flags || {}).cci_top_divergence || []).filter((d) => pos.has(d)).map((d) => ({ coord: [d, S.cci[pos.get(d)]], value: '背', name: 'CCI 顶背离 ' + d, itemStyle: { color: down } })), label: { fontSize: 9, color: '#fff' } } },
  ];
  if (TF === 'daily' && S.plan_channel) {
    [['ch_upper', '通道上轨'], ['ch_mid', '通道中轨'], ['ch_lower', '通道下轨']].forEach(([key, nm]) => { const arr = S.plan_channel[key].slice(-n); series.push({ name: nm, type: 'line', data: pad(arr.map((v, i) => (i >= n - 60 ? v : null))), symbol: 'none', lineStyle: { width: 1, color: muted, type: 'dotted' } }); });
  }
  const el = document.getElementById('mainChart'); const ch = echarts.init(el); charts.push(ch);
  const start = Math.max(0, 100 - (TF === 'daily' ? 130 : 90) / x.length * 100);
  ch.setOption({
    animation: false, textStyle: { fontFamily: css('--sans') },
    legend: { top: 0, textStyle: { color: muted, fontSize: 11 }, data: ['K线', '先行A', '先行B', 'BOLL上', 'BOLL中', 'BOLL下'] },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, confine: true, valueFormatter: (v) => (v == null ? '—' : Array.isArray(v) ? v.join(' / ') : Number(v).toFixed(2)) },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [{ left: 56, right: 12, top: 34, height: '54%' }, { left: 56, right: 12, top: '66%', height: '12%' }, { left: 56, right: 12, top: '82%', height: '11%' }],
    xAxis: [0, 1, 2].map((g) => ({ type: 'category', data: x, gridIndex: g, boundaryGap: true, axisLine: { lineStyle: { color: rule } }, axisLabel: { show: g === 2, color: muted, fontSize: 10 }, axisTick: { show: false } })),
    yAxis: [{ scale: true, gridIndex: 0, splitLine: { lineStyle: { color: rule } }, axisLabel: { color: muted, fontSize: 10 }, min: (v) => Math.min(v.min, lw), max: (v) => Math.max(v.max, hi) },
      { scale: true, gridIndex: 1, splitNumber: 2, splitLine: { show: false }, axisLabel: { color: muted, fontSize: 9 }, name: 'VW-MACD', nameTextStyle: { color: muted, fontSize: 10, align: 'left' } },
      { scale: true, gridIndex: 2, splitNumber: 2, splitLine: { show: false }, axisLabel: { color: muted, fontSize: 9 }, name: 'CCI', nameTextStyle: { color: muted, fontSize: 10, align: 'left' } }],
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1, 2], start, end: 100 }, { type: 'slider', xAxisIndex: [0, 1, 2], start, end: 100, height: 16, bottom: 2 }],
    series,
  });
}

function obsCard(title, o, body, chartId) {
  const ok = o && o.status === 'ok';
  let h = `<div class="card"><h3>${title}</h3>`;
  h += ok ? body : `<p><b>无数据</b>：${esc(o?.reason || '没有拿到')}</p>`;
  if (chartId && ok) h += `<div id="${chartId}" class="mini"></div>`;
  if (o?.rule) h += `<p class="small"><b>博主：</b>${esc(o.rule)}${o.has_rule ? '' : ''}<br><span class="src">出处 ${esc(o.video_source || '')}</span></p>`;
  if (ok) h += `<p class="small">${o.note ? esc(o.note) + '<br>' : ''}数据源：${esc(o.source)}${o.date ? '｜数据日 ' + esc(o.date) : ''}</p>`;
  return h + '</div>';
}

function renderObs() {
  const O = DATA.observations; let h = '';
  const p = O.pcr; h += obsCard('期权 PCR（上交所）', p, p.status === 'ok' ? `<p class="big">${fmt(p.pcr_volume, 3)}</p><p>${p.touch_upper ? signalTag('风险提示（看空）', 'sell') : signalTag(p.signal, 'none')} 上轨 ${fmt(p.upper, 3)}，中轨 ${fmt(p.middle, 3)}；持仓 PCR ${fmt(p.pcr_oi, 3)}。最近一次触及上轨：${p.last_touch_upper || '近 90 天没有'}</p>` : '', 'm_pcr');
  const e = O.equity_bond; h += obsCard('股债利差（沪深300）', e, e.status === 'ok' ? `<p class="big">${fmt(e.spread, 2)} <span class="small">百分点</span></p><p>${e.touch_upper ? signalTag('潜在底部证据', 'warn') : signalTag(e.signal, 'none')} PE ${fmt(e.pe_ttm)}，10 年国债 ${fmt(e.yield_10y, 3)}%；上轨 ${fmt(e.upper)}、中轨 ${fmt(e.middle)}、下轨 ${fmt(e.lower)}，现在在${esc(e.zone)}。最近一次触及上轨：${e.last_touch_upper || '近一年没有'}</p>` : '', 'm_eb');
  const q = O.equal_pe; h += obsCard('估值 PE（博主“等权 PE”）', q, q.status === 'ok' ? `<p class="big">${fmt(q.csi300_pe)}</p><p>沪深300 市盈率（${esc(q.csi300_pe_date || '')}），对照博主阈值：<b>${esc(q.zone_vs_blogger || '—')}</b>（机会值 11.61 / 危险值 14.18）。${signalTag('博主未给出买卖规则', 'none')}<br>全市场 PE 中位数（PE>0，${q.n_median || '—'} 只）：${fmt(q.median_positive)}</p>` : '');
  const b = O.breadth; h += obsCard('市场宽度与阿姆氏指标', b, b.status === 'ok' ? `<p class="big">涨 ${b.up} / 跌 ${b.down}</p><p>平 ${b.flat}，净上涨 ${b.net_advances}，上涨占比 ${fmt(b.up_pct, 1)}%；涨跌成交额比 ${fmt(b.amount_ratio)}；TRIN（成交额）${fmt(b.trin_amount)}，TRIN（成交量）${fmt(b.trin_volume)}；换手率>5% 占比 ${fmt(b.turnover_gt5_pct)}%；全市场成交额 ${fmt(b.total_amount_100m, 0)} 亿元。${b.mcl_candidate != null ? '麦克莱兰指标（候选）' + fmt(b.mcl_candidate, 1) : esc(b.mcl_note || '')}</p>` : '');
  const v = O.etf_volume; h += obsCard('沪深300ETF（510300）成交量', v, v.status === 'ok' ? `<p class="big">${fmt(v.volume_lots / 1e4, 1)} <span class="small">万手</span></p><p>是 5 日均量的 ${fmt(v.vs_5d_avg)} 倍，20 日均量的 ${fmt(v.vs_20d_avg)} 倍，今年最大量（${v.ytd_peak_date}）的 ${fmt(v.vs_ytd_max)} 倍。${signalTag('博主未给出买卖规则', 'none')}</p>` : '', 'm_etf');
  const f = O.basis; h += obsCard('股指期货升贴水（IF 当月）', f, f.status === 'ok' ? `<p class="big">${fmt(f.basis, 2)} <span class="small">点，${f.state}</span></p><p>期货 ${fmt(f.futures_close, 1)}，沪深300 ${fmt(f.spot_close)}；基差率 ${fmt(f.basis_pct, 3)}%，年化 ${fmt(f.annualized_pct)}%（距到期约 ${f.days_to_expiry} 天）。${signalTag('博主未给出买卖规则', 'none')}</p>` : '', 'm_basis');
  const i = O.iv; h += obsCard('期权隐含波动率与 Greeks（300ETF）', i, i.status === 'ok' ? `<p class="big">${fmt(i.atm_iv_pct)}%</p><p>平值行权价 ${i.strike}，到期 ${esc(i.expiry)}（${i.days_to_expiry} 天），510300 ${i.underlying_price}。</p><div class="tablewrap"><table><tr><th></th><th>价格</th><th>IV</th><th>Delta</th><th>Gamma</th><th>Vega/1%</th><th>Theta/日</th></tr>` + ['call', 'put'].map((kk) => { const z = i[kk]; return `<tr><td>${esc(z.contract)}</td><td class="num">${fmt(z.price, 4)}</td><td class="num">${fmt(z.iv_pct)}%</td><td class="num">${fmt(z.delta, 3)}</td><td class="num">${fmt(z.gamma, 3)}</td><td class="num">${fmt(z.vega_per_pt, 4)}</td><td class="num">${fmt(z.theta_per_day, 4)}</td></tr>`; }).join('') + '</table></div>' : '');
  const c = O.cap_gdp; h += obsCard('总市值 / GDP', c, c.status === 'ok' ? `<p class="big">${fmt(c.value_pct, 1)}%</p><p>A 股总市值 ${fmt(c.market_cap_100m / 1e4, 1)} 万亿元，滚动 GDP ${fmt(c.gdp_ttm_100m / 1e4, 1)} 万亿元（${esc(c.gdp_basis)}）。${signalTag('博主未给出买卖规则', 'none')}</p>` : '');
  const hd = O.holdings; h += obsCard('汇金披露持股家数', hd, hd.status === 'ok' ? `<div class="tablewrap"><table><tr><th>报告期</th><th>汇金投资</th><th>汇金资管</th><th>合计去重</th></tr>` + hd.table.map((r) => `<tr><td class="num">${r.period}</td><td class="num">${r.huijin_invest}</td><td class="num">${r.huijin_asset_mgmt}</td><td class="num">${r.total_unique}</td></tr>`).join('') + '</table></div>' : '');
  const s = O.insider; h += obsCard('股东增减持', s, s.status === 'ok' ? `<div class="tablewrap"><table><tr>` + Object.keys(s.months[0] || {}).map((kk) => `<th>${esc(kk)}</th>`).join('') + '</tr>' + s.months.map((r) => '<tr>' + Object.values(r).map((vv) => `<td class="num">${esc(vv)}</td>`).join('') + '</tr>').join('') + '</table></div>' : '');
  $('#obsCards').innerHTML = h;
  const mini = (id, x, ser) => { const el = document.getElementById(id); if (!el) return; const ch = echarts.init(el); charts.push(ch); ch.setOption({ animation: false, grid: { left: 44, right: 8, top: 8, bottom: 22 }, tooltip: { trigger: 'axis', confine: true }, xAxis: { type: 'category', data: x, axisLabel: { fontSize: 9, color: css('--muted') } }, yAxis: { scale: true, splitLine: { lineStyle: { color: css('--rule') } }, axisLabel: { fontSize: 9, color: css('--muted') } }, series: ser }); };
  const ln = (name, data, color, type = 'solid') => ({ name, type: 'line', data, symbol: 'none', lineStyle: { width: 1, color, type } });
  if (p.status === 'ok') mini('m_pcr', p.history.date, [{ name: 'PCR', type: 'bar', data: p.history.value, itemStyle: { color: css('--muted') } }, ln('上轨', p.history.upper, css('--down'), 'dashed'), ln('中轨', p.history.middle, css('--ink'), 'dotted')]);
  if (e.status === 'ok') mini('m_eb', e.history.date, [ln('利差', e.history.spread, css('--ink')), ln('上轨', e.history.upper, css('--up'), 'dashed'), ln('中轨', e.history.middle, css('--muted'), 'dotted'), ln('下轨', e.history.lower, css('--down'), 'dashed')]);
  if (v.status === 'ok') mini('m_etf', v.history.date, [{ name: '成交量', type: 'bar', data: v.history.volume, itemStyle: { color: css('--muted') } }]);
  if (f.status === 'ok') mini('m_basis', f.history.date, [ln('基差率%', f.history.basis_pct, css('--ink'))]);
}

function renderMisc() {
  $('#unavail').innerHTML = DATA.unavailable.map((u) => `<li><b>${esc(u.name)}</b>：${esc(u.reason)}</li>`).join('');
  $('#errors').innerHTML = DATA.errors && DATA.errors.length ? `<div class="card err"><h3>本次更新的数据源问题</h3><ul>${DATA.errors.map((e) => `<li>${esc(e.item)}：${esc(e.error)}</li>`).join('')}</ul></div>` : '';
}

window.addEventListener('resize', () => charts.forEach((c) => c.resize()));
init();
