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
LATEST_QUOTE_API = "https://d.10jqka.com.cn/v6/line/hs_{code}/01/today.js"
REALTIME_VALUATION_API = "https://d.10jqka.com.cn/v2/realhead/hs_{code}/last.js"

HTML = r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>A股财务望远镜</title><style>
:root{--bg:#07111f;--panel:#0e1b2d;--panel2:#13243b;--line:#263a55;--text:#edf4ff;--muted:#8fa5c2;--blue:#5ca8ff;--cyan:#64dfdf;--green:#65d6a6;--red:#ff7a90;--amber:#ffc857}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px Arial,"PingFang SC",sans-serif}button,input{font:inherit}.shell{min-height:100vh;display:grid;grid-template-columns:260px 1fr}.side{border-right:1px solid var(--line);padding:24px 18px;background:#091525}.brand{font-size:20px;font-weight:700}.tag{color:var(--muted);font-size:12px;margin:6px 0 28px}.side h3{font-size:12px;letter-spacing:.12em;color:var(--muted);margin:20px 8px 10px}.listrow{display:grid;grid-template-columns:1fr 28px;gap:3px;align-items:center}.fav{width:100%;display:flex;justify-content:space-between;align-items:center;padding:11px 8px 11px 12px;border:0;border-radius:8px;color:var(--text);background:transparent;cursor:pointer;text-align:left;min-width:0}.fav:hover,.fav.active{background:var(--panel2)}.fav small{color:var(--muted);margin-left:6px}.remove{border:0;background:transparent;color:var(--muted);width:28px;height:28px;border-radius:6px;cursor:pointer;font-size:18px;line-height:1}.remove:hover{background:#3a1d2a;color:var(--red)}.empty{color:var(--muted);padding:12px}.main{padding:16px 22px;overflow:hidden}.top{display:flex;gap:12px;align-items:center}.searchbox{position:relative;flex:1;max-width:700px}.searchbox input{width:100%;background:var(--panel);border:1px solid var(--line);color:var(--text);padding:13px 16px;border-radius:9px;outline:none}.searchbox input:focus{border-color:var(--blue)}.results{position:absolute;z-index:9;top:49px;left:0;right:0;background:var(--panel2);border:1px solid var(--line);border-radius:8px;overflow:hidden}.result{padding:11px 14px;cursor:pointer;display:flex;justify-content:space-between}.result:hover{background:#1b3352}.btn{border:1px solid var(--line);background:var(--panel2);color:var(--text);padding:11px 14px;border-radius:8px;cursor:pointer}.btn:hover{border-color:var(--blue)}.btn.primary{background:var(--blue);border-color:var(--blue);color:#051120;font-weight:700}.status{min-height:20px;color:var(--muted);padding:7px 2px}.hero{display:flex;justify-content:space-between;align-items:flex-end;margin:8px 0 10px}.company h1{font-size:26px;margin:0 0 4px}.company p{color:var(--muted);margin:0;font-size:12px}.badge{padding:5px 9px;border-radius:20px;background:#17324d;color:var(--cyan);font-size:12px}.cards{display:grid;grid-template-columns:repeat(9,minmax(92px,1fr));gap:7px}.card{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:11px 12px;min-width:0}.card .label{color:var(--muted);font-size:11px;display:flex;align-items:center;gap:5px;white-space:nowrap}.card .value{font-size:20px;font-weight:700;margin:7px 0 3px;white-space:nowrap}.card .year{color:var(--muted);font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.info{display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;border:1px solid var(--line);border-radius:50%;font-size:10px;color:var(--cyan);cursor:help;flex:none}.workspace{margin-top:9px;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:11px 14px}.toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:7px}.tabs{display:flex;gap:5px;flex-wrap:wrap}.tab{padding:5px 8px;border:1px solid var(--line);color:var(--muted);background:transparent;border-radius:6px;cursor:pointer;font-size:11px}.tab.active{color:#061525;background:var(--cyan);border-color:var(--cyan)}svg{width:100%;height:285px;display:block}.axis{stroke:#38506d;stroke-width:1}.grid{stroke:#203650;stroke-width:1}.line{fill:none;stroke:var(--cyan);stroke-width:3}.dot{fill:var(--cyan)}.chart-label{fill:var(--muted);font-size:11px}.tooltip{position:fixed;display:none;background:#06101d;border:1px solid var(--line);padding:8px;border-radius:6px;pointer-events:none}.tablewrap{overflow:auto;max-height:420px}.data-table{border-collapse:collapse;width:100%;min-width:800px}.data-table th,.data-table td{border-bottom:1px solid var(--line);padding:9px 10px;text-align:right;white-space:nowrap}.data-table th:first-child,.data-table td:first-child{text-align:left;position:sticky;left:0;background:var(--panel)}.data-table th{color:var(--muted);font-weight:400}.footer{color:var(--muted);font-size:12px;margin-top:14px}.hidden{display:none!important}@media(max-width:900px){.shell{grid-template-columns:1fr}.side{border:0;border-bottom:1px solid var(--line)}.main{padding:20px}.cards{grid-template-columns:repeat(2,1fr)}}
</style></head><body><div class="shell"><aside class="side"><div class="brand">A股财务望远镜</div><div class="tag">30年核心指标 · 本地持久缓存</div><h3>收藏股票</h3><div id="favorites"></div><h3>已缓存</h3><div id="cached"></div></aside><main class="main"><div class="top"><div class="searchbox"><input id="search" placeholder="输入股票名称或6位代码，如：泸州老窖 / 000568" autocomplete="off"><div id="results" class="results hidden"></div></div><button id="refresh" class="btn">重新拉取</button><button id="favoriteBtn" class="btn primary">收藏</button></div><div id="status" class="status">搜索股票开始查看。输入代码时可直接回车。</div><section id="content" class="hidden"><div class="hero"><div class="company"><h1 id="name"></h1><p><span id="code"></span> · 数据来源：同花顺F10 · <span id="updated"></span></p></div><span id="cacheBadge" class="badge"></span></div><div id="cards" class="cards"></div><div class="workspace"><div class="toolbar"><strong>年度趋势</strong><div id="tabs" class="tabs"></div></div><svg id="chart" viewBox="0 0 1000 340" preserveAspectRatio="none"></svg><div id="tip" class="tooltip"></div></div><div class="workspace"><div class="toolbar"><strong>核心指标明细</strong><span style="color:var(--muted)">最近30个完整年度 + 最新报告期</span></div><div class="tablewrap"><table id="table" class="data-table"></table></div></div><div class="footer">本工具仅供研究与数据查看，不构成投资建议。公开接口可能调整，刷新失败时会优先保留本地缓存。</div></section></main></div><script>
const $=s=>document.querySelector(s);let current=null,metric='revenue';const meta={revenue:['营业总收入','亿元'],revenue_growth:['营业收入增速','%'],net_profit:['归母净利润','亿元'],net_profit_growth:['净利润增速','%'],deducted_profit:['扣非净利润','亿元'],gross_margin:['销售毛利率','%'],net_margin:['销售净利率','%'],roe:['净资产收益率','%'],operating_cash_flow:['每股经营现金流','元/股'],debt_ratio:['资产负债率','%'],dividend_yield:['股息率（最新期TTM）','%']};const help={revenue:'公司在报告期内取得的营业总收入；中报/季报为年初至期末累计值。',revenue_growth:'营业总收入相对上年同期的增长率。',net_profit:'归属于母公司股东的净利润；中报/季报为累计值。',net_profit_growth:'归母净利润相对上年同期的增长率。',deducted_profit:'扣除非经常性损益后的归母净利润。',gross_margin:'（营业收入－营业成本）÷营业收入。',net_margin:'净利润÷营业总收入。',roe:'净资产收益率，衡量股东权益的盈利效率。',operating_cash_flow:'每股经营活动现金流；中报/季报为累计值。',debt_ratio:'负债合计÷资产合计。',dividend_yield:'完整年度沿用同花顺税前分红率；最新报告期按最近365天已实施每股现金分红合计÷同花顺最新收盘价。',dynamic_pe:'同花顺动态市盈率原始值：总市值÷按最新报告期推算的全年净利润。',total_return_cagr:'以后复权月线首末收盘价计算，近似反映现金分红和送转再投资后的上市以来复合年化总回报。'};const info=k=>`<span class="info" title="${help[k]||''}">?</span>`;
function status(t,bad=false){$('#status').textContent=t;$('#status').style.color=bad?'var(--red)':'var(--muted)'}function fmt(v,k){if(v==null)return'—';return (['revenue_growth','net_profit_growth','gross_margin','net_margin','roe','debt_ratio','dividend_yield'].includes(k)?(v*100).toFixed(2):Number(v).toFixed(2))+meta[k][1]}
async function api(url,opt){const r=await fetch(url,opt);const x=await r.json();if(!r.ok)throw Error(x.error||'请求失败');return x}
async function refreshLists(){const [f,c]=await Promise.all([api('/api/favorites'),api('/api/cached')]);$('#favorites').innerHTML=f.length?f.map(x=>`<div class="listrow"><button class="fav" onclick="loadStock('${x.code}')"><span>${x.name||x.code}</span><small>${x.code}</small></button><button class="remove" title="移除收藏" onclick="removeFavorite('${x.code}')">×</button></div>`).join(''):'<div class="empty">暂无收藏</div>';$('#cached').innerHTML=c.length?c.map(x=>`<div class="listrow"><button class="fav" onclick="loadStock('${x.code}')"><span>${x.name||x.code}</span><small>${x.code}</small></button><button class="remove" title="删除本地缓存" onclick="removeCache('${x.code}')">×</button></div>`).join(''):'<div class="empty">暂无缓存</div>'}
async function removeFavorite(code){if(!confirm('移除该收藏股票？'))return;try{await api('/api/favorites/'+code,{method:'DELETE'});if(current?.code===code){current.is_favorite=false;$('#favoriteBtn').textContent='收藏'}await refreshLists();status('已移除收藏。')}catch(e){status(e.message,true)}}
async function removeCache(code){if(!confirm('删除该股票的本地缓存？下次查看时会重新联网获取。'))return;try{await api('/api/cached/'+code,{method:'DELETE'});await refreshLists();if(current?.code===code)status('当前股票的本地缓存已删除；页面数据仍保留，重新打开时将联网获取。')}catch(e){status(e.message,true)}}
let timer;$('#search').addEventListener('input',e=>{clearTimeout(timer);const q=e.target.value.trim();if(!q){$('#results').classList.add('hidden');return}timer=setTimeout(()=>search(q),250)});$('#search').addEventListener('keydown',e=>{if(e.key==='Enter'){const q=e.target.value.trim();if(/^\d{6}$/.test(q))loadStock(q)}});async function search(q){try{const xs=await api('/api/search?q='+encodeURIComponent(q));$('#results').innerHTML=xs.map(x=>`<div class="result" onclick="loadStock('${x.code}')"><span>${x.name}</span><small>${x.code} · ${x.market}</small></div>`).join('')||'<div class="empty">未找到A股</div>';$('#results').classList.remove('hidden')}catch(e){status(e.message,true)}}
async function loadStock(code,force=false){$('#results').classList.add('hidden');status(force?'正在重新拉取同花顺数据…':'正在读取本地缓存或拉取数据…');try{current=await api('/api/financials/'+code+(force?'?refresh=1':''));render();refreshLists();status(current.warning|| (current.from_cache?'已从本地SQLite缓存读取。':'已从同花顺拉取并保存到本地SQLite。'),Boolean(current.warning))}catch(e){status(e.message,true)}}
function render(){const d=current;$('#content').classList.remove('hidden');$('#name').textContent=d.name;$('#code').textContent=d.code;$('#updated').textContent='更新于 '+d.updated_at;$('#cacheBadge').textContent=d.from_cache?'本地缓存':'网络更新';const last=d.years.length-1;const ks=['revenue','revenue_growth','net_profit','net_profit_growth','gross_margin','roe','dividend_yield'];let cards=ks.map(k=>`<div class="card"><div class="label">${meta[k][0]}${info(k)}</div><div class="value">${fmt(d.metrics[k]?.[last],k)}</div><div class="year">${d.years[last]||'—'}${/^\d{4}$/.test(d.years[last]||'')?' 年':''}</div></div>`).join('');cards+=`<div class="card"><div class="label">动态市盈率${info('dynamic_pe')}</div><div class="value">${d.dynamic_pe==null?'—':Number(d.dynamic_pe).toFixed(2)+'倍'}</div><div class="year">同花顺实时估值 · ${d.quote_time||'最新'}</div></div>`;const p=d.total_return_period||[];cards+=`<div class="card"><div class="label">总回报CAGR${info('total_return_cagr')}</div><div class="value">${d.total_return_cagr==null?'—':(d.total_return_cagr*100).toFixed(2)+'%'}</div><div class="year">${p[0]&&p[1]?p[0]+' 至 '+p[1]:'全周期'}</div></div>`;$('#cards').innerHTML=cards;renderTabs();renderChart();renderTable();$('#favoriteBtn').textContent=d.is_favorite?'取消收藏':'收藏'}function renderTabs(){$('#tabs').innerHTML=Object.keys(meta).map(k=>`<button class="tab ${k===metric?'active':''}" onclick="metric='${k}';renderTabs();renderChart()">${meta[k][0]}</button>`).join('')}
function renderChart(){const svg=$('#chart'),vals=current.metrics[metric],pts=vals.map((v,i)=>v==null?null:{v:Number(v),i}).filter(Boolean);if(!pts.length){svg.innerHTML='<text x="500" y="170" text-anchor="middle" class="chart-label">暂无数据</text>';return}let min=Math.min(...pts.map(p=>p.v)),max=Math.max(...pts.map(p=>p.v));if(max===min){max+=1;min-=1}const x=i=>55+i*(920/Math.max(1,vals.length-1)),y=v=>285-(v-min)*(240/(max-min));let h='';for(let i=0;i<5;i++){let yy=45+i*60,val=max-(max-min)*i/4;h+=`<line class="grid" x1="55" y1="${yy}" x2="975" y2="${yy}"/><text class="chart-label" x="48" y="${yy+4}" text-anchor="end">${(['revenue_growth','net_profit_growth','gross_margin','net_margin','roe','debt_ratio','dividend_yield'].includes(metric)?val*100:val).toFixed(1)}</text>`}h+=`<line class="axis" x1="55" y1="285" x2="975" y2="285"/>`;let parts=[],seg=[];vals.forEach((v,i)=>{if(v==null){if(seg.length)parts.push(seg),seg=[]}else seg.push(`${x(i)},${y(v)}`)});if(seg.length)parts.push(seg);parts.forEach(p=>h+=`<polyline class="line" points="${p.join(' ')}"/>`);vals.forEach((v,i)=>{if(v!=null)h+=`<circle class="dot" cx="${x(i)}" cy="${y(v)}" r="4"><title>${current.years[i]}：${fmt(v,metric)}</title></circle>`;if(i%Math.ceil(vals.length/10)===0||i===vals.length-1)h+=`<text class="chart-label" x="${x(i)}" y="310" text-anchor="middle">${current.years[i]}</text>`});svg.innerHTML=h}
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


def total_return_cagr(code):
    """以后复权月线首末收盘价估算含分红再投资的上市以来CAGR。"""
    prefix = "sh" if code.startswith(("60", "68")) else "sz"
    symbol = prefix + code
    raw = json.loads(fetch(TOTAL_RETURN_API.format(symbol=symbol)))
    block = (raw.get("data") or {}).get(symbol) or {}
    rows = block.get("hfqmonth") or []
    if len(rows) < 2:
        return None, None, None
    first, last = rows[0], rows[-1]
    start, end = datetime.strptime(first[0], "%Y-%m-%d"), datetime.strptime(last[0], "%Y-%m-%d")
    start_price, end_price = float(first[2]), float(last[2])
    years = (end - start).days / 365.2425
    if years <= 0 or start_price <= 0 or end_price <= 0 or not all(map(math.isfinite, (years, start_price, end_price))):
        return None, first[0], last[0]
    value = (end_price / start_price) ** (1 / years) - 1
    return (value if math.isfinite(value) else None), first[0], last[0]


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
    cache_current = cached_payload and cached_payload.get("schema_version") == 6
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
                cagr, cagr_start, cagr_end = total_return_cagr(code)
            except Exception:
                cagr = old_payload.get("total_return_cagr")
                cagr_start, cagr_end = (old_payload.get("total_return_period") or [None, None])[:2]
            try:
                latest_dynamic_pe = dynamic_pe(code)
            except Exception:
                latest_dynamic_pe = old_payload.get("dynamic_pe")
            # 独立行情接口单项失败时沿用已有缓存，不清空有效历史数据。
            payload = {"schema_version": 6, "code": code, "name": name, "years": periods, "report_dates": report_dates, "metrics": metrics,
                       "latest_price": latest_price, "quote_time": quote_time, "dynamic_pe": latest_dynamic_pe,
                       "total_return_cagr": cagr, "total_return_period": [cagr_start, cagr_end],
                       "metric_notes": {"operating_cash_flow": "每股经营现金流（元/股）；中报/季报为年初至报告期末累计值",
                                        "dividend_yield": "完整年度沿用同花顺税前分红率；最新报告期按最新交易日前365天内已实施现金分红合计÷同花顺最新收盘价计算",
                                        "total_return_cagr": "后复权月线首末收盘价计算，近似反映现金分红与送转再投资后的上市以来年化总回报",
                                        "dynamic_pe": "同花顺实时估值原始字段2942；总市值÷按最新报告期推算的全年净利润"},
                       "source": THS_PAGE.format(code=code)}
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
