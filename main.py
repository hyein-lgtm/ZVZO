"""
ZVZO 진행 현황 대시보드 (월별 탭 + 시작일 정렬 + 백그라운드 자동갱신).
"""

import os
import asyncio
import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from scraper import scrape_all
from agent import extract_items

app = FastAPI()

REFRESH_MINUTES = int(os.environ.get("REFRESH_MINUTES", "30"))

_store = {
    "items": None, "summary": {}, "diag": "",
    "daily_sales": {}, "monthly_sales": {},
    "updated_at": None, "refreshing": False, "error": "",
}


async def _collect():
    if _store["refreshing"]:
        return
    _store["refreshing"] = True
    try:
        data = await scrape_all()
        result = extract_items(data)
        _store["items"] = result.get("items", [])
        _store["summary"] = result.get("summary", {})
        _store["daily_sales"] = result.get("daily_sales", {})
        _store["monthly_sales"] = result.get("monthly_sales", {})
        _store["diag"] = data.get("_진단", "")
        _store["updated_at"] = datetime.datetime.now()
        _store["error"] = ""
    except Exception as e:
        _store["error"] = str(e)
    finally:
        _store["refreshing"] = False


async def _loop():
    await _collect()
    while True:
        await asyncio.sleep(REFRESH_MINUTES * 60)
        await _collect()


@app.on_event("startup")
async def _startup():
    asyncio.create_task(_loop())


@app.get("/", response_class=HTMLResponse)
def home():
    return PAGE_HTML


@app.get("/data")
async def data():
    ua = _store["updated_at"]
    return JSONResponse({
        "today": datetime.date.today().isoformat(),
        "items": _store["items"] or [],
        "summary": _store["summary"] or {},
        "daily_sales": _store["daily_sales"] or {},
        "monthly_sales": _store["monthly_sales"] or {},
        "diag": _store["diag"],
        "error": _store["error"],
        "refreshing": _store["refreshing"],
        "updated_at": ua.strftime("%Y-%m-%d %H:%M") if ua else None,
        "ready": _store["items"] is not None,
    })


@app.post("/refresh")
async def refresh():
    if not _store["refreshing"]:
        asyncio.create_task(_collect())
    return JSONResponse({"started": True})


PAGE_HTML = """
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZVZO 진행 현황</title>
<style>
  :root { --line:#ececf0; --muted:#6b7280; --ink:#16181d; --blue:#2d6cdf;
          --green:#0f9d58; --amber:#b8860b; --chip:#eef2fb; }
  * { box-sizing:border-box; }
  body { font-family:-apple-system,system-ui,"Apple SD Gothic Neo",sans-serif; margin:0; background:#f7f8fa; color:var(--ink); }
  .wrap { max-width:1100px; margin:0 auto; padding:24px 16px 60px; }
  header { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
  h1 { font-size:20px; margin:0; }
  .date { color:var(--muted); font-size:13px; margin-top:4px; }
  .refresh { padding:9px 16px; border:0; border-radius:10px; background:var(--blue); color:#fff; font-size:14px; cursor:pointer; }
  .refresh:disabled { background:#9bb6e8; cursor:default; }
  .sales { display:flex; gap:12px; flex-wrap:wrap; margin:16px 0; }
  .scard { flex:1; min-width:200px; border-radius:16px; padding:18px 20px; color:#fff; }
  .scard.main { background:linear-gradient(135deg,#2d6cdf,#5b8def); }
  .scard.run { background:linear-gradient(135deg,#0f9d58,#3cbb7f); }
  .scard .l { font-size:13px; opacity:.9; }
  .scard .v { font-size:26px; font-weight:800; margin-top:4px; }
  .scard .s { font-size:12px; opacity:.85; margin-top:4px; }
  .tabs { display:flex; gap:8px; flex-wrap:wrap; margin:18px 0 6px; border-bottom:1px solid var(--line); padding-bottom:10px; }
  .tab { padding:8px 14px; border-radius:999px; border:1px solid var(--line); background:#fff;
         font-size:14px; cursor:pointer; color:#444; }
  .tab.active { background:var(--blue); color:#fff; border-color:var(--blue); font-weight:700; }
  .tab .cnt { font-size:12px; opacity:.8; margin-left:4px; }
  .mhead { font-size:14px; color:var(--muted); margin:14px 0 10px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:12px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:14px; padding:16px; }
  .card .top { display:flex; align-items:center; justify-content:space-between; gap:8px; }
  .seller { font-weight:700; font-size:15px; }
  .dday { font-size:11px; color:var(--muted); margin-left:6px; }
  .badge { font-size:11px; padding:3px 8px; border-radius:999px; background:var(--chip); color:var(--blue); white-space:nowrap; }
  .badge.run { background:#e7f6ee; color:var(--green); }
  .badge.soon { background:#fef3e2; color:var(--amber); }
  .row { display:flex; justify-content:space-between; font-size:13px; margin-top:8px; color:#333; }
  .row .k { color:var(--muted); }
  .amount { font-weight:700; }
  .boost { display:inline-block; font-size:11px; color:#7c3aed; margin-top:6px; }
  .products { margin-top:12px; border-top:1px dashed var(--line); padding-top:10px; }
  .prod { display:flex; gap:10px; align-items:flex-start; padding:8px 0; border-bottom:1px solid #f3f4f6; }
  .prod:last-child { border-bottom:0; }
  .thumb { width:46px; height:46px; border-radius:8px; object-fit:cover; flex:0 0 46px; background:#f1f2f4; }
  .thumb.noimg { background:#eef0f3; }
  .pinfo { flex:1; min-width:0; }
  .pname { font-size:13px; font-weight:600; }
  .price { font-size:12px; color:#444; margin-top:3px; }
  .strike { color:#9aa0a6; text-decoration:line-through; }
  .final { color:var(--blue); font-weight:700; }
  .comm { font-size:11px; color:var(--muted); margin-top:2px; }
  .banner { background:#fff8e6; border:1px solid #f0e0b0; color:#8a6d00; font-size:13px;
            border-radius:10px; padding:10px 14px; margin:14px 0; }
  #loading { text-align:center; color:var(--muted); padding:50px 0; line-height:1.7; }
  details { margin-top:24px; color:var(--muted); font-size:12px; }
  pre { white-space:pre-wrap; background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>📊 ZVZO 진행 현황</h1>
      <div class="date" id="date"></div>
    </div>
    <button class="refresh" id="refresh" onclick="doRefresh()">지금 새로고침</button>
  </header>

  <div id="banner" class="banner" style="display:none"></div>
  <div id="loading">최신 데이터를 준비하는 중입니다... 잠시만요 ⏳</div>

  <div id="content" style="display:none">
    <div class="sales" id="sales"></div>
    <div class="tabs" id="tabs"></div>
    <div class="mhead" id="mhead"></div>
    <div class="grid" id="grid"></div>
  </div>

  <details>
    <summary>진단 정보 (문제 있을 때만 펼쳐보세요)</summary>
    <pre id="diag"></pre>
  </details>
</div>

<script>
let DATA = { items: [], summary: {}, today: "" };
let activeMonth = null;

function won(n){ return (n||0).toLocaleString('ko-KR') + '원'; }

function monthOf(it){
  const s = (it.period_start||"").slice(0,7);  // YYYY-MM
  return /^\\d{4}-\\d{2}$/.test(s) ? s : "기타";
}
function monthLabel(m){
  if(m==="기타") return "날짜미정";
  const [y,mm] = m.split("-");
  return `${y}년 ${parseInt(mm)}월`;
}
function dday(it){
  const s = it.period_start;
  if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(s||"")) return "";
  const today = new Date(DATA.today);
  const start = new Date(s);
  const diff = Math.round((start - today)/86400000);
  if(diff>0) return `D-${diff}`;
  if(diff===0) return "오늘 시작";
  return "진행중";
}

function products(list){
  if(!list || !list.length) return '';
  const rows = list.map(p => `
    <div class="prod">
      ${p.thumb ? '<img class="thumb" src="'+p.thumb+'" alt="">' : '<div class="thumb noimg"></div>'}
      <div class="pinfo">
        <div class="pname">${p.name||'-'}</div>
        <div class="price">
          <span class="strike">${p.original_price||''}</span>
          ${p.zvzo_discount ? ' − '+p.zvzo_discount : ''}
          ${p.final_price ? ' → <span class="final">'+p.final_price+'</span>' : ''}
        </div>
        ${p.commission ? '<div class="comm">커미션 '+p.commission+'</div>' : ''}
      </div>
    </div>`).join('');
  return `<div class="products">${rows}</div>`;
}

function card(it){
  const st = (it.status||"").includes("진행중") ? "run"
           : (it.status||"").includes("진행예정") ? "soon" : "";
  return `<div class="card">
    <div class="top">
      <span><span class="seller">${it.seller||"-"}</span><span class="dday">${dday(it)}</span></span>
      <span class="badge ${st}">${it.status||"-"}</span>
    </div>
    ${it.boost ? '<span class="boost">⚡ ZVZO 부스트 참여</span>' : ''}
    <div class="row"><span class="k">기간</span><span>${it.period_start||"?"} ~ ${it.period_end||"?"}</span></div>
    <div class="row"><span class="k">판매금액</span><span class="amount">${it.amount||"-"}</span></div>
    <div class="row"><span class="k">상품</span><span>${it.product_count||"-"}</span></div>
    <div class="row"><span class="k">할인</span><span>${it.discount_rate||"-"} · ${it.discount_type||"-"}</span></div>
    ${products(it.products)}
  </div>`;
}

function wonToInt(text){
  if(!text) return 0;
  const m = (text.match(/[\\d,]+/g)||[]);
  if(!m.length) return 0;
  return parseInt(m[0].replace(/,/g,'')) || 0;
}

function renderMonth(){
  const grid = document.getElementById('grid');
  const list = DATA.items
    .filter(it => monthOf(it) === activeMonth)
    .sort((a,b) => (a.period_start||"").localeCompare(b.period_start||""));

  // 선택한 달 기준 실매출 (매출 통계 페이지 기반)
  const ms = (DATA.monthly_sales || {})[activeMonth] || null;
  const todaySales = (DATA.daily_sales || {})[DATA.today] || null;

  let salesHTML;
  if (ms){
    salesHTML =
    `<div class="scard main">
       <div class="l">${monthLabel(activeMonth)} 실매출</div>
       <div class="v">${won(ms.sales)}</div>
       <div class="s">주문 ${ (ms.orders||0).toLocaleString('ko-KR') }건 · 매출통계 기준(1일~)</div>
     </div>
     <div class="scard run">
       <div class="l">오늘 매출 (${DATA.today})</div>
       <div class="v">${ todaySales ? won(todaySales.sales) : '—' }</div>
       <div class="s">${ todaySales ? '주문 '+todaySales.orders+'건' : '오늘 데이터 없음' }</div>
     </div>`;
  } else {
    // 매출통계가 없으면 협업 누적합으로 폴백
    const monthSales = list.reduce((s,it)=> s + wonToInt(it.amount), 0);
    salesHTML =
    `<div class="scard main">
       <div class="l">${monthLabel(activeMonth)} 시작 협업 판매금액(누적)</div>
       <div class="v">${won(monthSales)}</div>
       <div class="s">매출 통계를 못 불러와 협업 누적합으로 표시 중</div>
     </div>`;
  }
  document.getElementById('sales').innerHTML = salesHTML;

  document.getElementById('mhead').textContent =
    `${monthLabel(activeMonth)}에 시작하는 협업 ${list.length}건 (시작일 빠른 순)`;
  grid.innerHTML = list.map(card).join('') || '<div class="card">해당 월에 시작하는 협업이 없습니다.</div>';
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.m === activeMonth);
  });
}

function render(d){
  DATA = d;
  document.getElementById('diag').textContent = d.diag || d.error || '(없음)';
  const items = d.items || [];
  const sm = d.summary || {};

  // 월 목록 만들기 (시작일 기준)
  const counts = {};
  items.forEach(it => { const m = monthOf(it); counts[m] = (counts[m]||0)+1; });
  const months = Object.keys(counts).sort();  // YYYY-MM 오름차순, '기타'는 뒤로

  // 기본 선택: 오늘이 속한 달 → 없으면 첫 달
  const curMonth = (d.today||"").slice(0,7);
  if(!activeMonth || !counts[activeMonth]){
    activeMonth = counts[curMonth] ? curMonth : (months[0] || "기타");
  }

  document.getElementById('tabs').innerHTML = months.map(m =>
    `<button class="tab" data-m="${m}" onclick="selectMonth('${m}')">${monthLabel(m)}<span class="cnt">${counts[m]}</span></button>`
  ).join('');

  renderMonth();
}

function selectMonth(m){
  activeMonth = m;
  renderMonth();
}

async function poll(){
  try {
    const d = await (await fetch('/data')).json();
    const btn = document.getElementById('refresh');
    const banner = document.getElementById('banner');
    document.getElementById('date').textContent =
      (d.updated_at ? '마지막 갱신: ' + d.updated_at : '아직 수집 전') + ' · 오늘 ' + (d.today||'');
    if (d.ready){
      render(d);
      document.getElementById('loading').style.display='none';
      document.getElementById('content').style.display='block';
    }
    if (d.refreshing){
      btn.disabled = true; btn.textContent = '수집 중...';
      banner.style.display='block';
      banner.textContent = d.ready
        ? '🔄 백그라운드에서 최신 데이터를 수집하는 중입니다. (기존 데이터 표시 중)'
        : '⏳ 첫 수집 중입니다. 1~3분 걸려요. 끝나면 자동으로 나타납니다.';
    } else {
      btn.disabled = false; btn.textContent = '지금 새로고침';
      banner.style.display='none';
      if (!d.ready && d.error){
        document.getElementById('loading').textContent = '오류: ' + d.error;
      }
    }
  } catch(e){}
}

async function doRefresh(){
  await fetch('/refresh', {method:'POST'});
  poll();
}

poll();
setInterval(poll, 2000);
</script>
</body>
</html>
"""
