"""
ZVZO 진행 현황 대시보드 (방식 B + 백그라운드 자동갱신).

- 서버가 켜지면 즉시 1회 수집하고, 이후 REFRESH_MINUTES 마다 백그라운드로 자동 수집.
- 사용자가 접속하면 '저장된 최신 결과'를 즉시 보여줌 (대기 0초).
- '새로고침' 버튼은 즉시 다시 긁기(1~3분 소요).
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

# 저장된 최신 결과
_store = {
    "items": None,
    "diag": "",
    "updated_at": None,   # datetime
    "refreshing": False,  # 수집 진행중 여부
    "error": "",
}


async def _collect():
    """실제 수집(느림). 결과를 _store에 저장."""
    if _store["refreshing"]:
        return
    _store["refreshing"] = True
    try:
        data = await scrape_all()
        _store["items"] = extract_items(data)
        _store["diag"] = data.get("_진단", "")
        _store["updated_at"] = datetime.datetime.now()
        _store["error"] = ""
    except Exception as e:
        _store["error"] = str(e)
    finally:
        _store["refreshing"] = False


async def _loop():
    """서버 켜지면 즉시 1회 + 주기적으로 자동 수집."""
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
        "diag": _store["diag"],
        "error": _store["error"],
        "refreshing": _store["refreshing"],
        "updated_at": ua.strftime("%Y-%m-%d %H:%M") if ua else None,
        "ready": _store["items"] is not None,
    })


@app.post("/refresh")
async def refresh():
    """지금 즉시 다시 긁기(백그라운드로 시작만 하고 바로 응답)."""
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
  .summary { display:flex; gap:12px; flex-wrap:wrap; margin:18px 0; }
  .stat { background:#fff; border:1px solid var(--line); border-radius:14px; padding:14px 18px; min-width:130px; }
  .stat .n { font-size:24px; font-weight:700; }
  .stat .l { font-size:13px; color:var(--muted); margin-top:2px; }
  .section-title { font-size:15px; font-weight:700; margin:22px 0 10px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:12px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:14px; padding:16px; }
  .card .top { display:flex; align-items:center; justify-content:space-between; gap:8px; }
  .seller { font-weight:700; font-size:15px; }
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
let pollTimer = null;

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
      <span class="seller">${it.seller||"-"}</span>
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

function render(d){
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
    document.getElementById('otherTitle').style.display='block';
    document.getElementById('other').innerHTML = other.map(card).join('');
  }
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
        ? '🔄 백그라운드에서 최신 데이터를 다시 수집하는 중입니다. (기존 데이터 표시 중)'
        : '⏳ 첫 수집 중입니다. 1~3분 정도 걸려요. 끝나면 자동으로 나타납니다.';
    } else {
      btn.disabled = false; btn.textContent = '지금 새로고침';
      banner.style.display='none';
      if (!d.ready && d.error){
        document.getElementById('loading').textContent = '오류: ' + d.error;
      }
    }
  } catch(e){
    // 무시하고 다음 폴링
  }
}

async function doRefresh(){
  await fetch('/refresh', {method:'POST'});
  poll();
}

// 2초마다 상태 확인 (수집 끝나면 자동 표시)
poll();
pollTimer = setInterval(poll, 2000);
</script>
</body>
</html>
"""
