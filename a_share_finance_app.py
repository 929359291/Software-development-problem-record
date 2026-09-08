#!/usr/bin/env python3
"""A股30年核心财务指标本地看板。

启动：python a_share_finance_app.py
访问：http://127.0.0.1:8765
数据：同花顺F10公开页面；缓存：同目录下 a_share_finance.db（SQLite）。
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "a_share_finance.db"
DB_LOCK = threading.Lock()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140 Safari/537.36"
THS_PAGE = "https://basic.10jqka.com.cn/{code}/finance.html"
THS_API = "https://basic.10jqka.com.cn/api/stock/finance/{code}_{kind}.json"
SEARCH_API = "https://searchapi.eastmoney.com/api/suggest/get?input={query}&type=14&token=D43BF722C8E33BDC906FB84D85E326E8"
TOTAL_RETURN_API = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},month,1990-01-01,2099-12-31,1000,hfq"
HISTORICAL_PRICE_API = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={symbol},month,1990-01-01,2099-12-31,1000"
UNADJUSTED_PRICE_API = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={symbol},month,1990-01-01,2099-12-31,1000"
LATEST_QUOTE_API = "https://d.10jqka.com.cn/v6/line/hs_{code}/01/today.js"
REALTIME_VALUATION_API = "https://d.10jqka.com.cn/v2/realhead/hs_{code}/last.js"
COMPANY_SURVEY_API = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax?code={market_code}"

HTML = r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>A股财务望远镜</title><style>
:root{--bg:#07111f;--panel:#0e1b2d;--panel2:#13243b;--line:#263a55;--text:#edf4ff;--muted:#8fa5c2;--blue:#5ca8ff;--cyan:#64dfdf;--green:#65d6a6;--red:#ff7a90;--amber:#ffc857}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px Arial,"PingFang SC",sans-serif}button,input{font:inherit}.shell{min-height:100vh;display:grid;grid-template-columns:260px 1fr}.side{border-right:1px solid var(--line);padding:24px 18px;background:#091525}.brand{font-size:20px;font-weight:700}.tag{color:var(--muted);font-size:12px;margin:6px 0 28px}.side h3{font-size:12px;letter-spacing:.12em;color:var(--muted);margin:20px 8px 10px}.listrow{display:grid;grid-template-columns:1fr 28px;gap:3px;align-items:center}.fav{width:100%;display:flex;justify-content:space-between;align-items:center;padding:11px 8px 11px 12px;border:0;border-radius:8px;color:var(--text);background:transparent;cursor:pointer;text-align:left;min-width:0}.fav:hover,.fav.active{background:var(--panel2)}.fav small{color:var(--muted);margin-left:6px}.remove{border:0;background:transparent;color:var(--muted);width:28px;height:28px;border-radius:6px;cursor:pointer;font-size:18px;line-height:1}.remove:hover{background:#3a1d2a;color:var(--red)}.empty{color:var(--muted);padding:12px}.main{padding:16px 22px;overflow:hidden}.top{display:flex;gap:12px;align-items:center}.searchbox{position:relative;flex:1;max-width:700px}.searchbox input{width:100%;background:var(--panel);border:1px solid var(--line);color:var(--text);padding:13px 16px;border-radius:9px;outline:none}.searchbox input:focus{border-color:var(--blue)}.results{position:absolute;z-index:9;top:49px;left:0;right:0;background:var(--panel2);border:1px solid var(--line);border-radius:8px;overflow:hidden}.result{padding:11px 14px;cursor:pointer;display:flex;justify-content:space-between}.result:hover{background:#1b3352}.btn{border:1px solid var(--line);background:var(--panel2);color:var(--text);padding:11px 14px;border-radius:8px;cursor:pointer}.btn:hover{border-color:var(--blue)}.btn.primary{background:var(--blue);border-color:var(--blue);color:#051120;font-weight:700}.status{min-height:20px;color:var(--muted);padding:7px 2px}.hero{display:flex;justify-content:space-between;align-items:flex-end;margin:8px 0 10px}.company h1{font-size:26px;margin:0 0 4px}.company p{color:var(--muted);margin:0;font-size:12px}.badge{padding:5px 9px;border-radius:20px;background:#17324d;color:var(--cyan);font-size:12px}.cards{display:grid;grid-template-columns:repeat(10,minmax(88px,1fr));gap:7px}.card{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:11px 12px;min-width:0}.card .label{color:var(--muted);font-size:11px;display:flex;align-items:center;gap:5px;white-space:nowrap}.card .value{font-size:20px;font-weight:700;margin:7px 0 3px;white-space:nowrap}.card .year{color:var(--muted);font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.info{display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;border:1px solid var(--line);border-radius:50%;font-size:10px;color:var(--cyan);cursor:help;flex:none}.workspace{margin-top:9px;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:11px 14px}.toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:7px}.tabs{display:flex;gap:5px;flex-wrap:wrap}.tab{padding:5px 8px;border:1px solid var(--line);color:var(--muted);background:transparent;border-radius:6px;cursor:pointer;font-size:11px}.tab.active{color:#061525;background:var(--cyan);border-color:var(--cyan)}svg{width:100%;height:285px;display:block}.axis{stroke:#38506d;stroke-width:1}.grid{stroke:#203650;stroke-width:1}.line{fill:none;stroke:var(--cyan);stroke-width:3}.dot{fill:var(--cyan)}.price-line{fill:none;stroke:var(--amber);stroke-width:2.5}.price-dot{fill:var(--amber)}.legend{display:inline-flex;align-items:center;gap:10px;color:var(--muted);font-size:11px}.legend i{display:inline-block;width:18px;height:3px;border-radius:2px}.chart-label{fill:var(--muted);font-size:11px}.tooltip{position:fixed;display:none;background:#06101d;border:1px solid var(--line);padding:8px;border-radius:6px;pointer-events:none}.profile{margin-top:9px;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:0 14px}.profile summary{cursor:pointer;padding:11px 0;font-weight:700;list-style:none;display:flex;justify-content:space-between;align-items:center}.profile summary::-webkit-details-marker{display:none}.profile summary:after{content:'展开';color:var(--cyan);font-size:11px;font-weight:400}.profile[open] summary:after{content:'收起'}.profile-body{border-top:1px solid var(--line);padding:12px 0 14px;line-height:1.75}.profile-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.profile-item{background:var(--panel2);border-radius:7px;padding:10px 12px}.profile-item strong{display:block;color:var(--cyan);font-size:12px;margin-bottom:4px}.profile-meta{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;margin-top:10px}.profile-refresh{border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:6px;padding:4px 8px;cursor:pointer}.profile-refresh:hover{color:var(--text);border-color:var(--blue)}.address-line{display:grid;grid-template-columns:110px 1fr;gap:8px;margin:3px 0}.address-line span:first-child{color:var(--muted)}.holder-wrap{overflow:auto;margin-top:10px}.holder-table{width:100%;border-collapse:collapse;min-width:820px}.holder-table th,.holder-table td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;font-size:12px}.holder-table th{color:var(--muted);font-weight:400}.holder-table th:first-child,.holder-table td:first-child{text-align:left;white-space:normal;min-width:260px}.forecast{margin-top:9px;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:11px 14px}.forecast-summary{color:var(--muted);font-size:11px;line-height:1.7;margin-bottom:8px}.forecast-table{width:100%;border-collapse:collapse;margin-top:8px}.forecast-table th,.forecast-table td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;font-size:12px}.forecast-table th{color:var(--muted);font-weight:400}.forecast-table th:first-child,.forecast-table td:first-child{text-align:left}.fc-opt{color:var(--green)}.fc-neu{color:var(--cyan)}.fc-pes{color:var(--red)}.tablewrap{overflow:auto;max-height:420px}.data-table{border-collapse:collapse;width:100%;min-width:800px}.data-table th,.data-table td{border-bottom:1px solid var(--line);padding:9px 10px;text-align:right;white-space:nowrap}.data-table th:first-child,.data-table td:first-child{text-align:left;position:sticky;left:0;background:var(--panel)}.data-table th{color:var(--muted);font-weight:400}.footer{color:var(--muted);font-size:12px;margin-top:14px}.hidden{display:none!important}@media(max-width:900px){.shell{grid-template-columns:1fr}.side{border:0;border-bottom:1px solid var(--line)}.main{padding:20px}.cards{grid-template-columns:repeat(2,1fr)}}
</style></head><body><div class="shell"><aside class="side"><div class="brand">A股财务望远镜</div><div class="tag">30年核心指标 · 本地持久缓存</div><h3>收藏股票</h3><div id="favorites"></div><h3>已缓存</h3><div id="cached"></div></aside><main class="main"><div class="top"><div class="searchbox"><input id="search" placeholder="输入股票名称或6位代码，如：泸州老窖 / 000568" autocomplete="off"><div id="results" class="results hidden"></div></div><button id="refresh" class="btn">重新拉取</button><button id="favoriteBtn" class="btn primary">收藏</button></div><div id="status" class="status">搜索股票开始查看。输入代码时可直接回车。</div><section id="content" class="hidden"><div class="hero"><div class="company"><h1 id="name"></h1><p><span id="code"></span> · 数据来源：同花顺F10 · <span id="updated"></span></p></div><span id="cacheBadge" class="badge"></span></div><div id="cards" class="cards"></div><div class="workspace"><div class="toolbar"><div><strong>年度趋势</strong><span class="legend"><span><i style="background:var(--cyan)"></i>财务指标</span><span><i style="background:var(--amber)"></i>股价（右轴）</span></span></div><div id="tabs" class="tabs"></div></div><svg id="chart" viewBox="0 0 1000 340" preserveAspectRatio="none"></svg><div id="tip" class="tooltip"></div></div><div id="forecastBox" class="forecast hidden"></div><details id="profileBox" class="profile"><summary>公司与主业介绍</summary><div id="profileContent" class="profile-body"><div class="empty">正在加载公司介绍…</div></div></details><div class="workspace"><div class="toolbar"><strong>核心指标明细</strong><span style="color:var(--muted)">最近30个完整年度 + 最新报告期</span></div><div class="tablewrap"><table id="table" class="data-table"></table></div></div><div class="footer">本工具仅供研究与数据查看，不构成投资建议。公开接口可能调整，刷新失败时会优先保留本地缓存。</div></section></main></div><script>
const $=s=>document.querySelector(s);let current=null,metric='revenue';const meta={revenue:['营业总收入','亿元'],revenue_growth:['营业收入增速','%'],net_profit:['归母净利润','亿元'],net_profit_growth:['净利润增速','%'],deducted_profit:['扣非净利润','亿元'],gross_margin:['销售毛利率','%'],net_margin:['销售净利率','%'],roe:['净资产收益率','%'],operating_cash_flow:['每股经营现金流','元/股'],debt_ratio:['资产负债率','%'],dividend_yield:['股息率（最新期TTM）','%']};const help={revenue:'公司在报告期内取得的营业总收入；中报/季报为年初至期末累计值。',revenue_growth:'营业总收入相对上年同期的增长率。',net_profit:'归属于母公司股东的净利润；中报/季报为累计值。',net_profit_growth:'归母净利润相对上年同期的增长率。',deducted_profit:'扣除非经常性损益后的归母净利润。',gross_margin:'（营业收入－营业成本）÷营业收入。',net_margin:'净利润÷营业总收入。',roe:'净资产收益率，衡量股东权益的盈利效率。',operating_cash_flow:'每股经营活动现金流；中报/季报为累计值。',debt_ratio:'负债合计÷资产合计。',dividend_yield:'完整年度沿用同花顺税前分红率；最新报告期按最近365天已实施每股现金分红合计÷同花顺最新收盘价。',dynamic_pe:'同花顺动态市盈率原始值：总市值÷按最新报告期推算的全年净利润。',total_return_cagr:'以后复权月线首末收盘价计算，近似反映现金分红和送转再投资后的上市以来复合年化总回报。',historical_total_return:'以后复权期末值÷期初值－1，反映上市以来含现金分红和送转影响的累计总回报。'};const info=k=>`<span class="info" title="${help[k]||''}">?</span>`;
function status(t,bad=false){$('#status').textContent=t;$('#status').style.color=bad?'var(--red)':'var(--muted)'}function fmt(v,k){if(v==null)return'—';return (['revenue_growth','net_profit_growth','gross_margin','net_margin','roe','debt_ratio','dividend_yield'].includes(k)?(v*100).toFixed(2):Number(v).toFixed(2))+meta[k][1]}
async function api(url,opt){const r=await fetch(url,opt);const x=await r.json();if(!r.ok)throw Error(x.error||'请求失败');return x}
async function refreshLists(){const [f,c]=await Promise.all([api('/api/favorites'),api('/api/cached')]);$('#favorites').innerHTML=f.length?f.map(x=>`<div class="listrow"><button class="fav" onclick="loadStock('${x.code}')"><span>${x.name||x.code}</span><small>${x.code}</small></button><button class="remove" title="移除收藏" onclick="removeFavorite('${x.code}')">×</button></div>`).join(''):'<div class="empty">暂无收藏</div>';$('#cached').innerHTML=c.length?c.map(x=>`<div class="listrow"><button class="fav" onclick="loadStock('${x.code}')"><span>${x.name||x.code}</span><small>${x.code}</small></button><button class="remove" title="删除本地缓存" onclick="removeCache('${x.code}')">×</button></div>`).join(''):'<div class="empty">暂无缓存</div>'}
async function removeFavorite(code){if(!confirm('移除该收藏股票？'))return;try{await api('/api/favorites/'+code,{method:'DELETE'});if(current?.code===code){current.is_favorite=false;$('#favoriteBtn').textContent='收藏'}await refreshLists();status('已移除收藏。')}catch(e){status(e.message,true)}}
async function removeCache(code){if(!confirm('删除该股票的本地缓存？下次查看时会重新联网获取。'))return;try{await api('/api/cached/'+code,{method:'DELETE'});await refreshLists();if(current?.code===code)status('当前股票的本地缓存已删除；页面数据仍保留，重新打开时将联网获取。')}catch(e){status(e.message,true)}}
let timer;$('#search').addEventListener('input',e=>{clearTimeout(timer);const q=e.target.value.trim();if(!q){$('#results').classList.add('hidden');return}timer=setTimeout(()=>search(q),250)});$('#search').addEventListener('keydown',e=>{if(e.key==='Enter'){const q=e.target.value.trim();if(/^\d{6}$/.test(q))loadStock(q)}});async function search(q){try{const xs=await api('/api/search?q='+encodeURIComponent(q));$('#results').innerHTML=xs.map(x=>`<div class="result" onclick="loadStock('${x.code}')"><span>${x.name}</span><small>${x.code} · ${x.market}</small></div>`).join('')||'<div class="empty">未找到A股</div>';$('#results').classList.remove('hidden')}catch(e){status(e.message,true)}}
async function loadStock(code,force=false){$('#results').classList.add('hidden');status(force?'正在重新拉取同花顺数据…':'正在读取本地缓存或拉取数据…');try{current=await api('/api/financials/'+code+(force?'?refresh=1':''));render();loadProfile(code,false);refreshLists();status(current.warning|| (current.from_cache?'已从本地SQLite缓存读取。':'已从同花顺拉取并保存到本地SQLite。'),Boolean(current.warning))}catch(e){status(e.message,true)}}
function esc(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function loadProfile(code,force=false){const box=$('#profileContent');box.innerHTML='<div class="empty">正在联网获取公司介绍、地址与股东信息…</div>';try{const p=await api('/api/company-profile/'+code+(force?'?refresh=1':''));const rows=(p.top_shareholders||[]).map((h,i)=>`<tr><td>${i+1}. ${esc(h.name)}</td><td>${esc(h.shares)}</td><td>${esc(h.ratio)}</td><td>${esc(h.change)}</td><td>${esc(h.change_ratio)}</td></tr>`).join('');box.innerHTML=`<div>${esc(p.summary||p.introduction||'暂无介绍')}</div><div class="profile-grid"><div class="profile-item"><strong>主营业务</strong>${esc(p.business||'暂无')}</div><div class="profile-item"><strong>主要产品 / 业务类别</strong>${esc(p.products||'暂无')}</div><div class="profile-item"><strong>总部与注册地址</strong><div class="address-line"><span>注册地址</span><span>${esc(p.registered_address||'暂未披露')}</span></div><div class="address-line"><span>办公地址</span><span>${esc(p.office_address||'暂未披露')}</span></div><div class="address-line"><span>所属地区 / 官网</span><span>${esc(p.region||'—')} · ${esc(p.website||'—')}</span></div></div><div class="profile-item"><strong>经营现状 · ${esc(p.analysis_period||'最新报告期')}</strong>${esc(p.current_status||'暂无')}</div><div class="profile-item"><strong>未来发展前景</strong>${esc(p.outlook||'暂无')}</div><div class="profile-item"><strong>主要风险</strong>${esc(p.risks||'暂无')}<div style="color:var(--muted);font-size:11px;margin-top:5px">${esc(p.analysis_note||'')}</div></div><div class="profile-item" style="grid-column:1/-1"><strong>最新十大股东 · ${esc(p.shareholder_period||'最新报告期')}</strong><div style="color:var(--muted);font-size:11px">${esc(p.shareholder_summary||'')}</div><div class="holder-wrap"><table class="holder-table"><thead><tr><th>股东名称</th><th>持股数量</th><th>持股比例</th><th>持股变化</th><th>变动比例</th></tr></thead><tbody>${rows||'<tr><td colspan="5">暂无数据</td></tr>'}</tbody></table></div></div></div><div class="profile-meta"><span>来源：同花顺公司资料、股东研究及公开公司概况 · 更新于 ${esc(p.updated_at)}</span><button class="profile-refresh" onclick="loadProfile('${code}',true)">联网刷新分析</button></div>`;if(p.warning)status(p.warning,true)}catch(e){box.innerHTML=`<div class="empty">公司分析获取失败：${esc(e.message)}</div>`}}
function render(){const d=current;$('#content').classList.remove('hidden');$('#name').textContent=d.name;$('#code').textContent=d.code;$('#updated').textContent='更新于 '+d.updated_at;$('#cacheBadge').textContent=d.from_cache?'本地缓存':'网络更新';const last=d.years.length-1;const ks=['revenue','revenue_growth','net_profit','net_profit_growth','gross_margin','roe','dividend_yield'];let cards=ks.map(k=>`<div class="card"><div class="label">${meta[k][0]}${info(k)}</div><div class="value">${fmt(d.metrics[k]?.[last],k)}</div><div class="year">${d.years[last]||'—'}${/^\d{4}$/.test(d.years[last]||'')?' 年':''}</div></div>`).join('');cards+=`<div class="card"><div class="label">动态市盈率${info('dynamic_pe')}</div><div class="value">${d.dynamic_pe==null?'—':Number(d.dynamic_pe).toFixed(2)+'倍'}</div><div class="year">同花顺实时估值 · ${d.quote_time||'最新'}</div></div>`;const p=d.total_return_period||[];cards+=`<div class="card"><div class="label">复合年化总收益率${info('total_return_cagr')}</div><div class="value">${d.total_return_cagr==null?'—':(d.total_return_cagr*100).toFixed(2)+'%'}</div><div class="year">${p[0]&&p[1]?p[0]+' 至 '+p[1]:'全周期'}</div></div>`;cards+=`<div class="card"><div class="label">历史累计总收益率${info('historical_total_return')}</div><div class="value">${d.historical_total_return==null?'—':(d.historical_total_return*100).toFixed(0)+'%'}</div><div class="year">${p[0]&&p[1]?p[0]+' 至 '+p[1]:'全周期'}</div></div>`;$('#cards').innerHTML=cards;renderTabs();renderChart();renderForecast();renderTable();$('#favoriteBtn').textContent=d.is_favorite?'取消收藏':'收藏'}function renderTabs(){$('#tabs').innerHTML=Object.keys(meta).map(k=>`<button class="tab ${k===metric?'active':''}" onclick="metric='${k}';renderTabs();renderChart()">${meta[k][0]}</button>`).join('')}
function renderChart(){
 const svg=$('#chart'),vals=current.metrics[metric]||[],prices=(current.report_prices||[]).slice(0,vals.length);
 const pts=vals.map((v,i)=>v==null?null:{v:Number(v),i}).filter(Boolean),pricePts=prices.map((v,i)=>v==null?null:{v:Number(v),i}).filter(Boolean);
 if(!pts.length&&!pricePts.length){svg.innerHTML='<text x="500" y="170" text-anchor="middle" class="chart-label">暂无数据</text>';return}
 let min=pts.length?Math.min(...pts.map(p=>p.v)):0,max=pts.length?Math.max(...pts.map(p=>p.v)):1,pmin=pricePts.length?Math.min(...pricePts.map(p=>p.v)):0,pmax=pricePts.length?Math.max(...pricePts.map(p=>p.v)):1;
 if(max===min){max+=1;min-=1}if(pmax===pmin){pmax+=1;pmin=Math.max(0,pmin-1)}
 const x=i=>65+i*(870/Math.max(1,vals.length-1)),y=v=>285-(v-min)*(240/(max-min)),py=v=>285-(v-pmin)*(240/(pmax-pmin));
 const isPct=['revenue_growth','net_profit_growth','gross_margin','net_margin','roe','debt_ratio','dividend_yield'].includes(metric);let h='';
 for(let i=0;i<5;i++){let yy=45+i*60,val=max-(max-min)*i/4,pval=pmax-(pmax-pmin)*i/4;h+=`<line class="grid" x1="65" y1="${yy}" x2="935" y2="${yy}"/><text class="chart-label" x="57" y="${yy+4}" text-anchor="end">${(isPct?val*100:val).toFixed(1)}</text><text x="943" y="${yy+4}" fill="var(--amber)" font-size="11">${pval.toFixed(2)}</text>`}
 h+=`<line class="axis" x1="65" y1="285" x2="935" y2="285"/><text class="chart-label" x="65" y="18">${meta[metric][0]}（${meta[metric][1]}）</text><text x="935" y="18" text-anchor="end" fill="var(--amber)" font-size="11">不复权收盘价（元）</text>`;
 const drawSegments=(series,yfn,cls)=>{let parts=[],seg=[];series.forEach((v,i)=>{if(v==null){if(seg.length)parts.push(seg),seg=[]}else seg.push(`${x(i)},${yfn(Number(v))}`)});if(seg.length)parts.push(seg);parts.forEach(p=>h+=`<polyline class="${cls}" points="${p.join(' ')}"/>`)};
 drawSegments(vals,y,'line');drawSegments(prices,py,'price-line');
 vals.forEach((v,i)=>{if(v!=null)h+=`<circle class="dot" cx="${x(i)}" cy="${y(Number(v))}" r="3.5"><title>${current.years[i]}：${fmt(v,metric)}</title></circle>`});
 prices.forEach((v,i)=>{if(v!=null)h+=`<circle class="price-dot" cx="${x(i)}" cy="${py(Number(v))}" r="3"><title>${current.years[i]}：不复权股价 ${Number(v).toFixed(2)}元（${current.price_dates?.[i]||'报告期末'}）</title></circle>`});
 vals.forEach((_,i)=>{if(i%Math.ceil(vals.length/10)===0||i===vals.length-1)h+=`<text class="chart-label" x="${x(i)}" y="310" text-anchor="middle">${current.years[i]}</text>`});svg.innerHTML=h
}
function renderForecast(){
 const box=$('#forecastBox'),fc=current.price_forecast;if(!fc||!fc.methods){box.classList.add('hidden');return}box.classList.remove('hidden');
 const yrs=fc.years||[],methods=fc.methods||{},composite=fc.composite||[],actual=fc.latest_actual_price||((current.report_prices||[]).filter(Boolean).slice(-1)[0]);
 const methodKeys=['pe','peg','dividend','dcf','trend'];
 const colors={pe:'var(--cyan)',peg:'var(--green)',dividend:'var(--amber)',dcf:'#b794f4',trend:'var(--red)'};
 const allPrices=methodKeys.flatMap(k=>(methods[k]||{}).prices||[]).filter(v=>v!=null);
 if(!allPrices.length){box.classList.add('hidden');return}
 let min=Math.min(...allPrices),max=Math.max(...allPrices);if(actual){min=Math.min(min,actual);max=Math.max(max,actual)}if(max===min){max+=1;min-=1}
 const labels=['最新实际',...yrs],total=labels.length,x=i=>65+i*(870/Math.max(1,total-1)),y=v=>285-(v-min)*(240/(max-min));let h='';
 for(let i=0;i<5;i++){let yy=45+i*60,val=max-(max-min)*i/4;h+=`<line class="grid" x1="65" y1="${yy}" x2="935" y2="${yy}"/><text class="chart-label" x="57" y="${yy+4}" text-anchor="end">${val.toFixed(0)}</text>`}
 h+=`<line class="axis" x1="65" y1="285" x2="935" y2="285"/>`;
 if(actual)h+=`<circle cx="${x(0)}" cy="${y(actual)}" r="4" fill="var(--amber)"><title>最新实际不复权股价 ${actual.toFixed(2)}元</title></circle>`;
 methodKeys.forEach(k=>{const m=methods[k];if(!m)return;const pts=[];if(actual)pts.push(`${x(0)},${y(actual)}`);m.prices.forEach((v,i)=>pts.push(`${x(i+1)},${y(v)}`));h+=`<polyline fill="none" stroke="${colors[k]}" stroke-width="2.5" points="${pts.join(' ')}"/>`;m.prices.forEach((v,i)=>{h+=`<circle cx="${x(i+1)}" cy="${y(v)}" r="3.5" fill="${colors[k]}"><title>${yrs[i]}：${m.name} ${v.toFixed(2)}元</title></circle>`})});
 labels.forEach((lb,i)=>h+=`<text class="chart-label" x="${x(i)}" y="310" text-anchor="middle">${lb}</text>`);
 h+=`<text x="65" y="18" font-size="11" fill="var(--muted)">未来5年股价多模型预测</text><text x="935" y="18" text-anchor="end" font-size="11" fill="var(--amber)">不复权股价（元）</text>`;
 const legend=methodKeys.map(k=>`<span><i style="background:${colors[k]}"></i>${methods[k]?.name||k}</span>`).join('');
 const f2=n=>n==null?'—':Number(n).toFixed(2);
 const rows=yrs.map((yr,i)=>`<tr><td>${yr}</td>${methodKeys.map(k=>`<td>${f2(methods[k]?.prices?.[i])}</td>`).join('')}<td>${f2(composite[i]?.low)} - ${f2(composite[i]?.high)}</td><td>${f2(composite[i]?.median)}</td></tr>`).join('');
 const assumptions=methodKeys.map(k=>`${methods[k]?.name||k}：${esc(methods[k]?.assumption||'')}`).join('；');
 box.innerHTML=`<div class="toolbar"><strong>未来5年股价预测</strong><span class="legend">${legend}</span></div><svg id="forecastSvg" viewBox="0 0 1000 340" preserveAspectRatio="none" style="width:100%;height:285px;display:block"></svg><div class="forecast-summary">${esc(fc.method)}<br>基准EPS ${fc.current_eps}元 · 近5年净利润CAGR ${fc.base_cagr}% · 最新实际不复权股价 ${f2(actual)}元<br>${esc(assumptions)}<br><span style="color:var(--red)">${esc(fc.disclaimer)}</span></div><div class="holder-wrap"><table class="forecast-table"><thead><tr><th>年度</th>${methodKeys.map(k=>`<th>${methods[k]?.name||k}</th>`).join('')}<th>综合区间</th><th>综合中位</th></tr></thead><tbody>${rows}</tbody></table></div>`;
 const svg=$('#forecastSvg');if(svg)svg.innerHTML=h
}
function renderTable(){const ks=Object.keys(meta);let h='<thead><tr><th>报告期</th>'+ks.map(k=>`<th>${meta[k][0]}</th>`).join('')+'</tr></thead><tbody>';for(let i=current.years.length-1;i>=0;i--)h+='<tr><td>'+current.years[i]+'</td>'+ks.map(k=>`<td>${fmt(current.metrics[k][i],k)}</td>`).join('')+'</tr>';$('#table').innerHTML=h+'</tbody>'}
$('#refresh').onclick=()=>current&&loadStock(current.code,true);$('#favoriteBtn').onclick=async()=>{if(!current)return;try{await api('/api/favorites/'+current.code,{method:current.is_favorite?'DELETE':'POST'});current.is_favorite=!current.is_favorite;render();refreshLists()}catch(e){status(e.message,true)}};refreshLists();
</script></body></html>'''


def db_conn():
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with DB_LOCK, db_conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS stocks(code TEXT PRIMARY KEY,name TEXT NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS favorites(code TEXT PRIMARY KEY,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS company_profiles(code TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
        """)


def fetch(url, encoding="utf-8"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://basic.10jqka.com.cn/"})
    with urllib.request.urlopen(req, timeout=18) as r:
        return r.read().decode(encoding, errors="replace")


def parse_number(value):
    if value is False or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    s = str(value).replace(",", "").strip()
    if s.endswith("%"):
        return float(s[:-1]) / 100
    for unit, factor in (("万亿", 10000), ("亿", 1), ("万", 0.0001)):
        if s.endswith(unit):
            return float(s[:-len(unit)]) * factor
    try:
        return float(s)
    except ValueError:
        return None


def extract_main(code):
    page = fetch(THS_PAGE.format(code=code), "gb18030")
    m = re.search(r'<[^>]+id=["\']main["\'][^>]*>(.*?)</[^>]+>', page, re.S | re.I)
    if not m:
        raise ValueError("同花顺页面未返回财务数据，股票代码可能无效或接口暂时受限")
    text = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
    data = json.loads(text)
    title_m = re.search(r'<title>\s*(.*?)\((\d{6})\)', page, re.S | re.I)
    name = html.unescape(title_m.group(1).strip()) if title_m else code
    return name, data


def clean_html_text(fragment):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")).split())


def extract_company_profile(code):
    """提取公司简介、主营业务、注册地址与办公地址。"""
    page = fetch(f"https://basic.10jqka.com.cn/{code}/company.html", "gb18030")
    def after_label(label, tag="span"):
        m = re.search(rf"{re.escape(label)}.*?<{tag}[^>]*>(.*?)</{tag}>", page, re.S | re.I)
        return clean_html_text(m.group(1)) if m else ""
    business = after_label("主营业务：")
    products = after_label("产品名称：")
    office_address = after_label("办公地址：")
    region = after_label("所属地域：")
    website = after_label("公司网址：")
    intro_m = re.search(r"公司简介：</strong>\s*<p[^>]*>(.*?)</p>", page, re.S | re.I)
    intro = clean_html_text(intro_m.group(1)) if intro_m else ""
    registered_address = ""
    try:
        prefix = "SH" if code.startswith(("60", "68")) else "SZ"
        survey = json.loads(fetch(COMPANY_SURVEY_API.format(market_code=prefix + code)))
        basic = (survey.get("jbzl") or [{}])[0]
        registered_address = clean_html_text(basic.get("REG_ADDRESS", ""))
        office_address = office_address or clean_html_text(basic.get("ADDRESS", ""))
        region = region or clean_html_text(basic.get("PROVINCE", ""))
        website = website or clean_html_text(basic.get("ORG_WEB", ""))
    except Exception:
        pass
    if not any((business, products, intro)):
        raise ValueError("未能从公开资料获取公司介绍")
    summary_parts = []
    if business: summary_parts.append(f"公司主营{business.rstrip('。')}。")
    if products: summary_parts.append(f"主要产品或业务类别包括：{products.rstrip('。')}。")
    if intro and intro not in business: summary_parts.append(intro)
    return {"business": business, "products": products, "introduction": intro,
            "registered_address": registered_address, "office_address": office_address,
            "region": region, "website": website, "summary": "".join(summary_parts),
            "source": f"https://basic.10jqka.com.cn/{code}/company.html"}


def extract_top_shareholders(code):
    """从同花顺股东研究页提取最新报告期十大股东。"""
    page = fetch(f"https://basic.10jqka.com.cn/{code}/holder.html", "gb18030")
    section = re.search(r'<div[^>]+id=["\']tenholder["\'][^>]*>([\s\S]*?)<div[^>]+id=["\']holder_pop_up["\']', page, re.I)
    scope = section.group(1) if section else page
    period_m = re.search(r'<a[^>]*class=["\'][^"\']*tdates[^"\']*["\'][^>]*>(\d{4}-\d{2}-\d{2})</a>', scope, re.I)
    table_m = re.search(r'<div[^>]+id=["\']ther_1["\'][^>]*>[\s\S]*?<table[^>]*>([\s\S]*?)</table>', scope, re.I)
    if not period_m or not table_m:
        raise ValueError("未能获取最新十大股东")
    table = table_m.group(1)
    caption_m = re.search(r'<caption[^>]*>([\s\S]*?)</caption>', table, re.I)
    summary = clean_html_text(caption_m.group(1)) if caption_m else ""
    holders = []
    tbody_m = re.search(r'<tbody[^>]*>([\s\S]*?)</tbody>', table, re.I)
    for row in re.findall(r'<tr[^>]*>([\s\S]*?)</tr>', tbody_m.group(1) if tbody_m else "", re.I):
        cells = re.findall(r'<(?:th|td)[^>]*>([\s\S]*?)</(?:th|td)>', row, re.I)
        values = [clean_html_text(c) for c in cells]
        if len(values) >= 5:
            change_ratio = values[4]
            share_type = values[5] if len(values) > 5 else ""
            if change_ratio.startswith("新进 ") and not share_type:
                change_ratio, share_type = "新进", change_ratio[3:].strip()
            elif change_ratio.startswith("新进 ") and share_type == "点击查看":
                change_ratio, share_type = "新进", change_ratio[3:].strip()
            holders.append({"name": values[0], "shares": values[1], "change": values[2],
                            "ratio": values[3], "change_ratio": change_ratio,
                            "share_type": share_type})
    return {"shareholder_period": period_m.group(1), "shareholder_summary": summary,
            "top_shareholders": holders[:10],
            "shareholder_source": f"https://basic.10jqka.com.cn/{code}/holder.html"}


def pct_text(value):
    return "未披露" if value is None else f"{value * 100:.2f}%"


def build_company_analysis(profile, financials):
    """结合最新报告期财务数据和主营业务，生成规则透明的现状与前景分析。"""
    periods = financials.get("years") or []
    metrics = financials.get("metrics") or {}
    index = len(periods) - 1
    def latest(key):
        values = metrics.get(key) or []
        return values[index] if 0 <= index < len(values) else None
    period = periods[index] if periods else "最新报告期"
    revenue, revenue_growth = latest("revenue"), latest("revenue_growth")
    profit, profit_growth = latest("net_profit"), latest("net_profit_growth")
    gross_margin, net_margin, roe = latest("gross_margin"), latest("net_margin"), latest("roe")
    debt_ratio, dividend_yield = latest("debt_ratio"), latest("dividend_yield")
    status_bits = []
    if revenue is not None: status_bits.append(f"营业总收入{revenue:.2f}亿元，同比{pct_text(revenue_growth)}")
    if profit is not None: status_bits.append(f"归母净利润{profit:.2f}亿元，同比{pct_text(profit_growth)}")
    if gross_margin is not None: status_bits.append(f"销售毛利率{pct_text(gross_margin)}")
    if net_margin is not None: status_bits.append(f"销售净利率{pct_text(net_margin)}")
    if roe is not None: status_bits.append(f"净资产收益率{pct_text(roe)}")
    if debt_ratio is not None: status_bits.append(f"资产负债率{pct_text(debt_ratio)}")
    if revenue_growth is not None and profit_growth is not None:
        if revenue_growth >= 0 and profit_growth >= 0:
            trend = "收入与利润保持同比增长，经营动能整体偏正。"
        elif revenue_growth < 0 and profit_growth < 0:
            trend = "收入与利润均同比下降，短期经营处于调整或承压阶段。"
        elif revenue_growth >= 0 > profit_growth:
            trend = "收入增长但利润下降，盈利能力和费用投入值得重点跟踪。"
        else:
            trend = "收入下降但利润改善，可能存在产品结构、成本或费用端优化。"
    else:
        trend = "部分同比指标暂未披露，需结合后续定期报告继续观察。"
    current_status = f"截至{period}，" + "；".join(status_bits) + "。" + trend

    text = " ".join((profile.get("business", ""), profile.get("products", ""), profile.get("introduction", "")))
    if any(k in text for k in ("白酒", "酒类", "酿酒")):
        drivers = ["核心品牌与产品结构升级能否持续提升吨价和盈利质量", "渠道库存、批价及终端动销能否改善", "全国化市场拓展与数字化渠道建设的成效", "消费需求和行业集中度变化对头部品牌的影响"]
        risks = ["白酒消费需求恢复不及预期", "渠道库存和价格体系波动", "行业竞争加剧及食品安全风险"]
    elif any(k in text for k in ("银行", "贷款", "存款")):
        drivers = ["净息差企稳与资产规模增长", "财富管理和中间业务收入提升", "资产质量及拨备覆盖水平改善"]
        risks = ["净息差继续收窄", "信用成本上升", "区域经济与房地产相关风险"]
    elif any(k in text for k in ("医药", "药品", "医疗", "生物")):
        drivers = ["核心产品放量与新品获批", "研发管线兑现和商业化效率", "渠道覆盖及海外市场拓展"]
        risks = ["研发和审批不确定性", "集采降价与医保控费", "产品竞争和合规风险"]
    elif any(k in text for k in ("半导体", "软件", "芯片", "信息技术", "电子")):
        drivers = ["行业需求复苏与国产替代进程", "研发投入向新产品和客户订单转化", "产品结构升级与规模效应释放"]
        risks = ["技术迭代和研发失败", "下游需求波动", "供应链与行业竞争风险"]
    else:
        drivers = ["核心产品或服务的需求增长", "产品结构、渠道和客户覆盖持续优化", "成本费用控制与经营现金流改善", "新业务投入能否形成可持续收入"]
        risks = ["行业需求波动", "竞争加剧导致价格或毛利率承压", "新项目执行和现金流回收不及预期"]
    if revenue_growth is not None and revenue_growth < 0:
        drivers.insert(0, "主营收入恢复及低基数后的增长拐点")
    if revenue_growth is not None and profit_growth is not None and profit_growth < revenue_growth:
        risks.insert(0, "利润增速弱于收入、盈利能力继续下滑")
    outlook = "未来发展取决于：" + "；".join(drivers) + "。"
    if dividend_yield is not None:
        outlook += f"按最新口径股息率约为{pct_text(dividend_yield)}，股东回报仍需结合盈利持续性和后续分红方案判断。"
    risk_text = "；".join(dict.fromkeys(risks)) + "。"
    return {"analysis_period": period, "current_status": current_status,
            "outlook": outlook, "risks": risk_text,
            "analysis_note": "以上为基于公开公司资料与最新财务指标的规则化分析，不代表盈利预测或投资建议。"}


def get_company_profile(code, force=False):
    if not valid_code(code):
        raise ValueError("请输入有效的6位A股代码")
    cached = None
    with DB_LOCK, db_conn() as con:
        row = con.execute("SELECT payload,updated_at FROM company_profiles WHERE code=?", (code,)).fetchone()
        if row: cached = dict(row)
    cached_payload = json.loads(cached["payload"]) if cached else None
    if cached_payload and cached_payload.get("profile_version") == 3 and not force:
        result = cached_payload; result.update(from_cache=True, updated_at=cached["updated_at"]); return result
    try:
        result = extract_company_profile(code)
        result.update(extract_top_shareholders(code))
        financials = get_financials(code, False)
        result.update(build_company_analysis(result, financials))
        result["profile_version"] = 3
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        with DB_LOCK, db_conn() as con:
            con.execute("INSERT INTO company_profiles(code,payload,updated_at) VALUES(?,?,?) ON CONFLICT(code) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at", (code,json.dumps(result,ensure_ascii=False),now))
        result.update(from_cache=False, updated_at=now); return result
    except Exception:
        if cached:
            result=json.loads(cached["payload"]); result.update(from_cache=True,updated_at=cached["updated_at"],warning="联网刷新失败，已返回旧介绍"); return result
        raise


def report_label(report_date):
    year, month, day = report_date.split("-")
    suffix = {"03-31": "一季报", "06-30": "中报", "09-30": "三季报", "12-31": "年报"}.get(f"{month}-{day}", report_date)
    return f"{year}{suffix}"


def latest_quote(code):
    raw = fetch(LATEST_QUOTE_API.format(code=code))
    m = re.search(r"\((.*)\)\s*$", raw)
    data = json.loads(m.group(1)) if m else {}
    row = data.get(f"hs_{code}", {})
    price = float(row["11"]) if row.get("11") else None
    quote_time = row.get("1")
    return price, quote_time


def dynamic_pe(code):
    """读取同花顺实时估值中的动态市盈率原始值（字段2942）。"""
    raw = fetch(REALTIME_VALUATION_API.format(code=code))
    m = re.search(r"\((.*)\)\s*$", raw)
    data = json.loads(m.group(1)) if m else {}
    value = (data.get("items") or {}).get("2942")
    number = float(value) if value not in (None, "", "--") else None
    return number if number is None or math.isfinite(number) else None


def dividend_data(code, labels):
    """读取同花顺分红融资页；年报用原始税前分红率，最新期按现金分红/最新价计算。"""
    page = fetch(f"https://basic.10jqka.com.cn/{code}/bonus.html", "gb18030")
    rows = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I):
        cells = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)]
        if cells:
            rows[cells[0]] = cells
    yields = []
    try:
        latest_price, quote_time = latest_quote(code)
    except Exception:
        latest_price = quote_time = None
    for label in labels:
        cells = rows.get(label)
        if not cells:
            yields.append(None); continue
        if label.endswith("年报"):
            match = re.fullmatch(r"(-?\d+(?:\.\d+)?)%", cells[-1])
            yields.append(float(match.group(1)) / 100 if match else None)
        else:
            # 最新报告期股息率采用TTM口径：最新行情日前365天内已经实施的现金分红合计÷最新价。
            if not latest_price or not quote_time:
                yields.append(None); continue
            end_date = datetime.strptime(quote_time[:8], "%Y%m%d")
            start_date = end_date - timedelta(days=365)
            cash_per_share = 0.0
            for dividend_cells in rows.values():
                if len(dividend_cells) < 9 or dividend_cells[8] != "实施方案":
                    continue
                cash = re.search(r"10派\s*([\d.]+)元", dividend_cells[4])
                date_match = re.fullmatch(r"\d{4}-\d{2}-\d{2}", dividend_cells[6])
                if not cash or not date_match:
                    continue
                ex_date = datetime.strptime(dividend_cells[6], "%Y-%m-%d")
                if start_date < ex_date <= end_date:
                    cash_per_share += float(cash.group(1)) / 10
            yields.append(cash_per_share / latest_price)
    return yields, latest_price, quote_time


def historical_closes(code, report_dates):
    """按报告期匹配当日或之前最近交易日的不复权月末收盘价。"""
    prefix = "sh" if code.startswith(("60", "68")) else "sz"
    symbol = prefix + code
    raw = json.loads(fetch(HISTORICAL_PRICE_API.format(symbol=symbol)))
    rows = ((raw.get("data") or {}).get(symbol) or {}).get("month") or []
    observations = []
    for row in rows:
        try:
            observations.append((datetime.strptime(row[0], "%Y-%m-%d"), float(row[2])))
        except (ValueError, TypeError, IndexError):
            continue
    observations.sort(key=lambda x: x[0])
    values, actual_dates = [], []
    for report_date in report_dates:
        target = datetime.strptime(report_date, "%Y-%m-%d")
        eligible = [(d, v) for d, v in observations if d <= target]
        if eligible:
            d, v = eligible[-1]
            values.append(v if math.isfinite(v) else None)
            actual_dates.append(d.strftime("%Y-%m-%d"))
        else:
            values.append(None); actual_dates.append(None)
    return values, actual_dates


def total_return_metrics(code):
    """以后复权月线计算上市以来年化总收益率和历史累计总收益率。"""
    prefix = "sh" if code.startswith(("60", "68")) else "sz"
    symbol = prefix + code
    raw = json.loads(fetch(TOTAL_RETURN_API.format(symbol=symbol)))
    block = (raw.get("data") or {}).get(symbol) or {}
    rows = block.get("hfqmonth") or []
    if len(rows) < 2:
        return None, None, None, None
    first, last = rows[0], rows[-1]
    start, end = datetime.strptime(first[0], "%Y-%m-%d"), datetime.strptime(last[0], "%Y-%m-%d")
    start_price, end_price = float(first[2]), float(last[2])
    years = (end - start).days / 365.2425
    if years <= 0 or start_price <= 0 or end_price <= 0 or not all(map(math.isfinite, (years, start_price, end_price))):
        return None, None, first[0], last[0]
    cumulative = end_price / start_price - 1
    cagr = (end_price / start_price) ** (1 / years) - 1
    return (cagr if math.isfinite(cagr) else None), (cumulative if math.isfinite(cumulative) else None), first[0], last[0]


def build_price_forecast(financials):
    """基于PE估值法预测未来5年股价区间。

    方法：
    1. 取近5个完整年度归母净利润，计算历史CAGR作为基准增速；
    2. 按年衰减因子模拟增速回归长期趋势；
    3. 用最新报告期年化净利润作为起点，逐年推算乐观/中性/悲观三档EPS；
    4. 用历史后复权PE分位数（中位数、25%分位、75%分位）作为估值锚；
    5. 预测股价 = EPS × PE分位值。
    """
    periods = financials.get("years") or []
    metrics = financials.get("metrics") or {}
    prices = financials.get("report_prices") or []
    dynamic_pe = financials.get("dynamic_pe")
    report_dates = financials.get("report_dates") or []
    annual_indices = [i for i, d in enumerate(report_dates) if d and d.endswith("12-31")][-5:]
    annual_profits = [metrics.get("net_profit", [None] * len(periods))[i] for i in annual_indices if i < len(metrics.get("net_profit", []))]
    annual_profits = [p for p in annual_profits if p is not None and p > 0]
    if len(annual_profits) < 2:
        return None
    base_cagr = (annual_profits[-1] / annual_profits[0]) ** (1 / (len(annual_profits) - 1)) - 1
    base_cagr = max(-0.3, min(0.5, base_cagr))

    latest_period = periods[-1] if periods else "最新"
    latest_profit = metrics.get("net_profit", [None] * len(periods))
    latest_profit_val = latest_profit[-1] if latest_profit and latest_profit[-1] is not None else annual_profits[-1]
    latest_report_date = report_dates[-1] if report_dates else ""
    if latest_report_date.endswith("12-31"):
        annualized_profit = latest_profit_val
    else:
        annual_profits_all = [metrics.get("net_profit", [None]*len(periods))[i] for i, d in enumerate(report_dates) if d and d.endswith("12-31")]
        last_annual = annual_profits_all[-1] if annual_profits_all else latest_profit_val
        annualized_profit = last_annual
    shares = 14.72
    try:
        prefix = "SH" if (financials.get("code", "")).startswith(("60", "68")) else "SZ"
        survey = json.loads(fetch(COMPANY_SURVEY_API.format(market_code=prefix + financials.get("code", ""))))
        basic = (survey.get("jbzl") or [{}])[0]
        shares = float(basic.get("REG_CAPITAL", 147190.1463)) / 10000 or 14.72
    except Exception:
        pass
    base_eps = annualized_profit / shares

    pe_samples = []
    unadj_prices = []
    try:
        prefix = "sh" if (financials.get("code", "")).startswith(("60", "68")) else "sz"
        symbol = prefix + financials.get("code", "")
        raw = json.loads(fetch(UNADJUSTED_PRICE_API.format(symbol=symbol)))
        rows = ((raw.get("data") or {}).get(symbol) or {}).get("month") or []
        observations = []
        for row in rows:
            try: observations.append((datetime.strptime(row[0], "%Y-%m-%d"), float(row[2])))
            except: continue
        observations.sort(key=lambda x: x[0])
        for rd in report_dates:
            target = datetime.strptime(rd, "%Y-%m-%d")
            eligible = [(d, v) for d, v in observations if d <= target]
            unadj_prices.append(eligible[-1][1] if eligible and math.isfinite(eligible[-1][1]) else None)
        unadj_prices = (unadj_prices + [None] * len(prices))[:len(prices)]
    except Exception:
        unadj_prices = [None] * len(prices)
    for i in range(min(len(unadj_prices), len(latest_profit))):
        p, profit_i = unadj_prices[i], latest_profit[i]
        if p and profit_i and profit_i > 0:
            annualized_i = profit_i
            rd = report_dates[i] if i < len(report_dates) else ""
            if rd.endswith("06-30"): annualized_i = profit_i * 2
            elif rd.endswith("09-30"): annualized_i = profit_i * 4 / 3
            elif rd.endswith("03-31"): annualized_i = profit_i * 4
            if annualized_i > 0:
                pe_samples.append(p / (annualized_i / shares))
    pe_samples = [x for x in pe_samples if x and math.isfinite(x) and x > 0]
    if len(pe_samples) < 3:
        if dynamic_pe and math.isfinite(dynamic_pe):
            pe_samples = [dynamic_pe]
        else:
            return None
    pe_recent = pe_samples[-5:] if len(pe_samples) >= 5 else pe_samples
    pe_recent.sort()
    pe_median = pe_recent[len(pe_recent) // 2]
    pe_low = pe_recent[0]
    pe_high = pe_recent[-1]
    if pe_low == pe_median:
        pe_low = pe_median * 0.7
    if pe_high == pe_median:
        pe_high = pe_median * 1.3

    scenarios = {
        "optimistic": {"growth": max(base_cagr, base_cagr * 1.2 + 0.02), "pe": pe_high},
        "neutral": {"growth": base_cagr * 0.7, "pe": pe_median},
        "pessimistic": {"growth": min(base_cagr * 0.5, base_cagr - 0.05), "pe": pe_low},
    }
    current_year = int(latest_period[:4]) if latest_period[:4].isdigit() else datetime.now().year
    forecast_years = [str(current_year + i) for i in range(1, 6)]
    forecast = {"years": forecast_years, "scenarios": {}}
    for label, params in scenarios.items():
        eps_list, price_list = [], []
        eps = base_eps
        for _ in forecast_years:
            eps = eps * (1 + params["growth"])
            eps_list.append(round(eps, 4))
            price_list.append(round(eps * params["pe"], 2))
        forecast["scenarios"][label] = {"eps": eps_list, "prices": price_list, "pe": round(params["pe"], 2), "growth": round(params["growth"] * 100, 2)}
    # 其余主流估值方法均使用中性EPS路径，以便不同模型可以横向比较。
    neutral_eps = forecast["scenarios"]["neutral"]["eps"]
    neutral_growth_pct = max(0.0, forecast["scenarios"]["neutral"]["growth"])

    # PEG：目标PEG取1.0，目标PE等于盈利增速百分数，并设置8-35倍的合理边界。
    peg_pe = max(8.0, min(35.0, neutral_growth_pct))
    peg_prices = [round(eps * peg_pe, 2) for eps in neutral_eps]

    # 股息率法：假设分红率60%，目标股息率取近5个完整年度股息率中位数，并限制在2%-8%。
    dividend_series = metrics.get("dividend_yield") or []
    annual_dividends = [dividend_series[i] for i in annual_indices if i < len(dividend_series) and dividend_series[i] is not None and dividend_series[i] > 0]
    target_yield = sorted(annual_dividends)[len(annual_dividends) // 2] if annual_dividends else 0.04
    target_yield = max(0.02, min(0.08, target_yield))
    payout_ratio = 0.60
    dividend_prices = [round(eps * payout_ratio / target_yield, 2) for eps in neutral_eps]

    # 简化DCF：以EPS作为股东自由现金流代理，折现率10%、永续增长率3%。
    discount_rate, terminal_growth = 0.10, 0.03
    dcf_multiple = (1 + terminal_growth) / (discount_rate - terminal_growth)
    dcf_prices = [round(eps * dcf_multiple, 2) for eps in neutral_eps]

    # 历史趋势法：按最近5年不复权价格CAGR外推，并将年增速限制在-25%至+25%。
    recent_prices = [p for p in unadj_prices[-6:] if p is not None and p > 0]
    latest_actual_price = recent_prices[-1] if recent_prices else (financials.get("latest_price") or 0)
    if len(recent_prices) >= 2:
        history_years = max(1, len(recent_prices) - 1)
        price_cagr = (recent_prices[-1] / recent_prices[0]) ** (1 / history_years) - 1
    else:
        price_cagr = 0.0
    price_cagr = max(-0.25, min(0.25, price_cagr))
    trend_prices = [round(latest_actual_price * (1 + price_cagr) ** i, 2) for i in range(1, 6)]

    methods = {
        "pe": {"name": "PE估值法", "prices": forecast["scenarios"]["neutral"]["prices"], "assumption": f"PE={pe_median:.2f}倍"},
        "peg": {"name": "PEG估值法", "prices": peg_prices, "assumption": f"PEG=1，目标PE={peg_pe:.2f}倍"},
        "dividend": {"name": "股息率法", "prices": dividend_prices, "assumption": f"分红率={payout_ratio*100:.0f}%，目标股息率={target_yield*100:.2f}%"},
        "dcf": {"name": "简化DCF法", "prices": dcf_prices, "assumption": f"折现率={discount_rate*100:.0f}%，永续增长率={terminal_growth*100:.0f}%"},
        "trend": {"name": "历史趋势法", "prices": trend_prices, "assumption": f"近5年不复权股价CAGR={price_cagr*100:.2f}%"},
    }
    composite = []
    for i in range(5):
        vals = sorted(m["prices"][i] for m in methods.values() if m["prices"][i] is not None)
        composite.append({"low": round(vals[0], 2), "high": round(vals[-1], 2), "median": round(vals[len(vals)//2], 2)})
    forecast["methods"] = methods
    forecast["composite"] = composite
    forecast["latest_actual_price"] = round(latest_actual_price, 2) if latest_actual_price else None
    forecast["current_eps"] = round(base_eps, 4)
    forecast["pe_median"] = round(pe_median, 2)
    forecast["pe_low"] = round(pe_low, 2)
    forecast["pe_high"] = round(pe_high, 2)
    forecast["base_cagr"] = round(base_cagr * 100, 2)
    forecast["shares"] = round(shares, 2)
    forecast["method"] = "采用PE、PEG、目标股息率、简化DCF和历史趋势五种方法。PE/PEG/股息率/DCF共用中性EPS路径；历史趋势法按近5年不复权股价CAGR外推。"
    forecast["disclaimer"] = "模型基于历史数据和固定假设，仅用于情景推演，不构成盈利预测或投资建议；DCF以EPS近似股东自由现金流，结果对假设高度敏感。"
    return forecast


def report_series(data):
    dates = data["report"][0]
    annual = [(d, i) for i, d in enumerate(dates) if re.fullmatch(r"\d{4}-12-31", str(d))]
    annual = sorted(annual)[-30:]
    latest_date = max((d for d in dates if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d))), default=None)
    selected = list(annual)
    if latest_date and latest_date > annual[-1][0]:
        selected.append((latest_date, dates.index(latest_date)))
    titles = [x[0] if isinstance(x, list) else x for x in data["title"][1:]]
    rows = data["report"][1:]
    mapped = {t: [parse_number(rows[n][i]) for _, i in selected] for n, t in enumerate(titles)}
    labels = [d[:4] if d.endswith("12-31") else report_label(d) for d, _ in selected]
    return labels, [d for d, _ in selected], mapped


def valid_code(code):
    return bool(re.fullmatch(r"(?:00|30|60|68|83|87|92)\d{4}", code or ""))


def get_financials(code, force=False):
    if not valid_code(code):
        raise ValueError("请输入有效的6位A股代码")
    cached = None
    with DB_LOCK, db_conn() as con:
        row = con.execute("SELECT * FROM stocks WHERE code=?", (code,)).fetchone()
        if row:
            cached = dict(row)
    cached_payload = json.loads(cached["payload"]) if cached else None
    cache_current = cached_payload and cached_payload.get("schema_version") == 11
    if cache_current and not force:
        payload = cached_payload
        payload.update(from_cache=True, updated_at=cached["updated_at"])
    else:
        try:
            name, data = extract_main(code)
            periods, report_dates, m = report_series(data)
            keys = {
                "revenue": "营业总收入", "revenue_growth": "营业总收入同比增长率",
                "net_profit": "净利润", "net_profit_growth": "净利润同比增长率", "deducted_profit": "扣非净利润",
                "gross_margin": "销售毛利率", "net_margin": "销售净利率", "roe": "净资产收益率",
                "operating_cash_flow": "每股经营现金流", "debt_ratio": "资产负债率"
            }
            metrics = {k: m.get(v, [None] * len(periods)) for k, v in keys.items()}
            old_payload = json.loads(cached["payload"]) if cached else {}
            latest_price = quote_time = None
            try:
                dividend_labels = [f"{d[:4]}年报" if d.endswith("12-31") else report_label(d) for d in report_dates]
                metrics["dividend_yield"], latest_price, quote_time = dividend_data(code, dividend_labels)
            except Exception:
                old = old_payload.get("metrics", {}).get("dividend_yield", [])
                metrics["dividend_yield"] = (old + [None] * len(periods))[:len(periods)]
            try:
                cagr, cumulative_return, cagr_start, cagr_end = total_return_metrics(code)
            except Exception:
                cagr = old_payload.get("total_return_cagr")
                cumulative_return = old_payload.get("historical_total_return")
                cagr_start, cagr_end = (old_payload.get("total_return_period") or [None, None])[:2]
            try:
                latest_dynamic_pe = dynamic_pe(code)
            except Exception:
                latest_dynamic_pe = old_payload.get("dynamic_pe")
            try:
                report_prices, price_dates = historical_closes(code, report_dates)
            except Exception:
                report_prices = old_payload.get("report_prices", [None] * len(periods))
                price_dates = old_payload.get("price_dates", [None] * len(periods))
            # 独立行情接口单项失败时沿用已有缓存，不清空有效历史数据。
            interim_payload = {"schema_version": 11, "code": code, "name": name, "years": periods, "report_dates": report_dates, "metrics": metrics,
                       "report_prices": report_prices, "price_dates": price_dates,
                       "latest_price": latest_price, "quote_time": quote_time, "dynamic_pe": latest_dynamic_pe,
                       "total_return_cagr": cagr, "historical_total_return": cumulative_return, "total_return_period": [cagr_start, cagr_end],
                       "metric_notes": {"operating_cash_flow": "每股经营现金流（元/股）；中报/季报为年初至报告期末累计值",
                                        "dividend_yield": "完整年度沿用同花顺税前分红率；最新报告期按最新交易日前365天内已实施现金分红合计÷同花顺最新收盘价计算",
                                        "total_return_cagr": "后复权月线首末收盘价计算，近似反映现金分红与送转再投资后的上市以来年化总回报",
                                        "dynamic_pe": "同花顺实时估值原始字段2942；总市值÷按最新报告期推算的全年净利润"},
                       "source": THS_PAGE.format(code=code)}
            try:
                forecast = build_price_forecast(interim_payload)
                if forecast: interim_payload["price_forecast"] = forecast
            except Exception:
                pass
            payload = interim_payload
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            with DB_LOCK, db_conn() as con:
                con.execute("INSERT INTO stocks(code,name,payload,updated_at) VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET name=excluded.name,payload=excluded.payload,updated_at=excluded.updated_at", (code, name, json.dumps(payload, ensure_ascii=False), now))
            payload.update(from_cache=False, updated_at=now)
        except Exception:
            if not cached:
                raise
            payload = json.loads(cached["payload"])
            payload.update(from_cache=True, updated_at=cached["updated_at"], warning="网络刷新失败，已返回旧缓存")
    with DB_LOCK, db_conn() as con:
        payload["is_favorite"] = bool(con.execute("SELECT 1 FROM favorites WHERE code=?", (code,)).fetchone())
    return payload


def search_stocks(query):
    q = query.strip()
    if re.fullmatch(r"\d{6}", q):
        if not valid_code(q):
            return []
        with DB_LOCK, db_conn() as con:
            r = con.execute("SELECT code,name FROM stocks WHERE code=?", (q,)).fetchone()
        if r:
            return [{"code": q, "name": r["name"], "market": "A股"}]
        raw = json.loads(fetch(SEARCH_API.format(query=urllib.parse.quote(q))))
        items = (raw.get("QuotationCodeTable") or {}).get("Data") or []
        return [{"code": str(x.get("Code")), "name": x.get("Name") or q, "market": x.get("SecurityTypeName") or "A股"}
                for x in items if str(x.get("Code")) == q and x.get("Classify") == "AStock"][:1]
    raw = json.loads(fetch(SEARCH_API.format(query=urllib.parse.quote(q))))
    items = (raw.get("QuotationCodeTable") or {}).get("Data") or []
    out = []
    for x in items:
        code = str(x.get("Code", ""))
        if re.fullmatch(r"\d{6}", code) and x.get("Classify") == "AStock":
            out.append({"code": code, "name": x.get("Name") or code, "market": x.get("SecurityTypeName") or "A股"})
    return out[:10]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path); path = p.path
        try:
            if path == "/":
                b = HTML.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            elif path == "/api/search":
                self.send_json(search_stocks(urllib.parse.parse_qs(p.query).get("q", [""])[0]))
            elif path.startswith("/api/financials/"):
                code = path.rsplit("/", 1)[-1]; force = urllib.parse.parse_qs(p.query).get("refresh") == ["1"]
                self.send_json(get_financials(code, force))
            elif path.startswith("/api/company-profile/"):
                code = path.rsplit("/", 1)[-1]; force = urllib.parse.parse_qs(p.query).get("refresh") == ["1"]
                self.send_json(get_company_profile(code, force))
            elif path == "/api/favorites":
                with DB_LOCK, db_conn() as con:
                    rows = con.execute("SELECT f.code,COALESCE(s.name,f.code) name FROM favorites f LEFT JOIN stocks s ON s.code=f.code ORDER BY f.created_at DESC").fetchall()
                self.send_json([dict(r) for r in rows])
            elif path == "/api/cached":
                with DB_LOCK, db_conn() as con:
                    rows = con.execute("SELECT code,name,updated_at FROM stocks ORDER BY updated_at DESC").fetchall()
                self.send_json([dict(r) for r in rows])
            else: self.send_json({"error": "未找到"}, 404)
        except Exception as e: self.send_json({"error": str(e)}, 502)

    def do_POST(self):
        try:
            if self.path.startswith("/api/favorites/"):
                code = self.path.rsplit("/", 1)[-1]
                if not valid_code(code):
                    raise ValueError("无效的A股代码")
                with DB_LOCK, db_conn() as con:
                    stock = con.execute("SELECT 1 FROM stocks WHERE code=?", (code,)).fetchone()
                    if not stock:
                        raise ValueError("请先加载该股票的财务数据，再进行收藏")
                    con.execute("INSERT OR IGNORE INTO favorites(code,created_at) VALUES(?,?)", (code, datetime.now().isoformat()))
                self.send_json({"ok": True})
            else: self.send_json({"error": "未找到"}, 404)
        except Exception as e: self.send_json({"error": str(e)}, 400)

    def do_DELETE(self):
        try:
            code = self.path.rsplit("/", 1)[-1]
            if not valid_code(code):
                raise ValueError("无效的A股代码")
            if self.path.startswith("/api/favorites/"):
                with DB_LOCK, db_conn() as con: con.execute("DELETE FROM favorites WHERE code=?", (code,))
                self.send_json({"ok": True})
            elif self.path.startswith("/api/cached/"):
                with DB_LOCK, db_conn() as con:
                    con.execute("DELETE FROM favorites WHERE code=?", (code,))
                    con.execute("DELETE FROM stocks WHERE code=?", (code,))
                    con.execute("DELETE FROM company_profiles WHERE code=?", (code,))
                self.send_json({"ok": True})
            else: self.send_json({"error": "未找到"}, 404)
        except Exception as e: self.send_json({"error": str(e)}, 400)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--port", type=int, default=DEFAULT_PORT); parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(); init_db(); server = ThreadingHTTPServer((HOST, args.port), Handler)
    url = f"http://{HOST}:{args.port}"; print(f"A股财务望远镜已启动：{url}\n数据库：{DB_PATH}\n按 Ctrl+C 停止。")
    if not args.no_browser: threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: print("\n已停止。")
    finally: server.server_close()

if __name__ == "__main__": main()
