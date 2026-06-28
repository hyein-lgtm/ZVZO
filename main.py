"""
ZVZO 진행 현황 대시보드.
접속하면 자동으로 로그인→목록 긁기→오늘 기준 진행 현황을 카드로 보여준다.
"""

import time
import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from scraper import scrape_all
from agent import extract_items

app = FastAPI()

_cache = {"items": None, "ts": 0.0, "diag": ""}
CACHE_SECONDS = 300  # 5분


async def get_items(force: bool = False):
    now = time.time()
    if force or _cache["items"] is None or (now - _cache["ts"]) > CACHE_SECONDS:
        data = await scrape_all()
        _cache["items"] = extract_items(data)
        _cache["diag"] = data.get("_진단", "")
        _cache["ts"] = now
    return _cache["items"], _cache["diag"]


@app.get("/", response_class=HTMLResponse)
def home():
    return PAGE_HTML


@app.get("/data")
async def data(refresh: int = 0):
    try:
        items, diag = await get_items(force=bool(refresh))
        return JSONResponse({
            "today": datetime.date.today().isoformat(),
            "items": items,
            "diag": diag,
        })
    except Exception as e:
        return JSONResponse({"error": str(e), "items": []})


PAGE_HTML = """
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZVZO 진행 현황</title>
<style>
  :root { --bg:#fff; --line:#ececf0; --muted:#6b7280; --ink:#16181d;
          --blue:#2d6cdf; --green:#0f9d58; --amber:#b8860b; --chip:#eef2fb; }
  * { box-sizing: border-box; }
  body { font-family:-apple-system,system-ui,"Apple SD Gothic Neo",sans-serif;
         margin:0; background:#f7f8fa; color:var(--ink); }
  .wrap { max-width:1100px; margin:0 auto; padding:24px 16px 60px; }
  header { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
  h1 { font-size:20px; margin:0; }
  .date { color:var(--muted); font-size:14px; }
  button { padding:9px 16px; border:0; border-radius:10px; background:var(--blue);
           color:#fff; font-size:14px; cursor:pointer; }
  button:disabled { background:#9bb6e8; }
  .summary { display:flex; gap:12px; flex-wrap:wrap; margin:18px 0; }
  .stat { background:#fff; border:1px solid var(--line); border-radius:14px;
          padding:14px 18px; min-width:140px; }
  .stat .n { font-size:24px; font-weight:700; }
  .stat .l { font-size:13px; color:var(--muted); margin-top:2px; }
  .section-title { font-size:15px; font-weight:700; margin:22px 0 10px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:12px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:14px; padding:16px; }
  .card .top { display:flex; align-items:center; justify-content:space-between; gap:8px; }
  .seller { font-weight:700; font-size:15px; }
  .badge { font-size:11px; padding:3px 8px; border-radius:999px; background:var(--chip); color:var(--blue); }
  .badge.run { background:#e7f6ee; color:var(--green); }
  .badge.soon { background:#fef3e2; color:var(--amber); }
  .row { display:flex; justify-content:space-between; font-size:13px; margin-top:8px; color:#333; }
  .row .k { color:var(--muted); }
  .amount { font-weight:700; }
  .boost { display:inline-block; font-size:11px; color:#7c3aed; margin-top:6px; }
  #loading { text-align:center; color:var(--muted); padding:50px 0; }
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
    <button id="refresh" onclick="load(true)">새로고침</button>
  </header>

  <div id="loading">불러오는 중... (로그인→목록 수집, 10~20초) ⏳</div>
  <div id="content" style="display:none">
    <div class="summary" id="summary"></div>
    <div class="section-title">🟢 진행중</div>
    <div class="grid" id="running"></div>
    <div class="section-title">🟡 진행예정</div>
    <div class="grid" id="soon"></div>
    <div class="section-title" id="otherTitle" style="display:none">기타</div>
    <div class="grid" id="other"></div>
  </div>

  <details>
    <summary>진단 정보 (문제 있을 때만 펼쳐보세요)</summary>
    <pre id="diag"></pre>
  </details>
</div>

<script>
function card(it){
  const st = (it.status||"").includes("진행중") ? "run"
           : (it.status||"").includes("진행예정") ? "soon" : "";
  return `<div class="card">
    <div class="top">
      <span class="seller">${it.seller||"-"}</span>
      <span class="badge ${st}">${it.status||"-"}</span>
    </div>
    ${it.boost ? '<span class="boost">⚡ ZVZO 부스트 참여</span>' : ''}
    <div class="row"><span class="k">기간</span><span>${it.period_start||"?"} ~ ${it.period_end||"?"}</span></div>
    <div class="row"><span class="k">판매금액</span><span class="amount">${it.amount||"-"}</span></div>
    <div class="row"><span class="k">상품</span><span>${it.product_count||"-"}</span></div>
    <div class="row"><span class="k">할인</span><span>${it.discount_rate||"-"} · ${it.discount_type||"-"}</span></div>
  </div>`;
}

async function load(refresh){
  const btn = document.getElementById('refresh');
  btn.disabled = true;
  document.getElementById('loading').style.display = 'block';
  document.getElementById('content').style.display = 'none';
  try {
    const res = await fetch('/data?refresh=' + (refresh?1:0));
    const d = await res.json();
    document.getElementById('date').textContent = '오늘: ' + (d.today||'');
    document.getElementById('diag').textContent = d.diag || d.error || '(없음)';
    const items = d.items || [];

    const running = items.filter(x => (x.status||"").includes("진행중"));
    const soon    = items.filter(x => (x.status||"").includes("진행예정"));
    const other   = items.filter(x => !(x.status||"").includes("진행중") && !(x.status||"").includes("진행예정"));

    document.getElementById('summary').innerHTML =
      `<div class="stat"><div class="n">${items.length}</div><div class="l">전체 협업</div></div>
       <div class="stat"><div class="n">${running.length}</div><div class="l">진행중</div></div>
       <div class="stat"><div class="n">${soon.length}</div><div class="l">진행예정</div></div>`;

    document.getElementById('running').innerHTML = running.map(card).join('') || '<div class="card">없음</div>';
    document.getElementById('soon').innerHTML = soon.map(card).join('') || '<div class="card">없음</div>';
    if (other.length){
      document.getElementById('otherTitle').style.display = 'block';
      document.getElementById('other').innerHTML = other.map(card).join('');
    }
    document.getElementById('loading').style.display = 'none';
    document.getElementById('content').style.display = 'block';
  } catch(e){
    document.getElementById('loading').textContent = '오류: ' + e;
  } finally {
    btn.disabled = false;
  }
}
load(false);
</script>
</body>
</html>
"""
