"""
웹 서버 본체. 브라우저로 접속하면 질문 입력창이 뜨고,
질문하면 ZVZO 화면을 긁어 Claude가 답해준다.

성능을 위해 한 번 긁은 데이터는 5분간 재사용(캐시)한다.
'새로고침' 체크하면 즉시 다시 긁는다.
"""

import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from scraper import scrape_all
from agent import answer

app = FastAPI()

_cache = {"data": None, "ts": 0.0}
CACHE_SECONDS = 300  # 5분


async def get_data(force: bool = False) -> dict:
    now = time.time()
    if force or _cache["data"] is None or (now - _cache["ts"]) > CACHE_SECONDS:
        _cache["data"] = await scrape_all()
        _cache["ts"] = now
    return _cache["data"]


@app.get("/", response_class=HTMLResponse)
def home():
    return PAGE_HTML


@app.post("/ask")
async def ask(request: Request):
    body = await request.json()
    question = (body.get("question") or "").strip()
    force = bool(body.get("refresh"))
    if not question:
        return JSONResponse({"reply": "질문을 입력해 주세요."})
    try:
        data = await get_data(force=force)
        reply = answer(question, data)
    except Exception as e:
        reply = f"오류가 발생했어요: {e}"
    return JSONResponse({"reply": reply})


PAGE_HTML = """
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZVZO 판매 비서</title>
<style>
  body { font-family: -apple-system, system-ui, "Apple SD Gothic Neo", sans-serif;
         max-width: 720px; margin: 40px auto; padding: 0 16px; color: #1a1a1a; }
  h1 { font-size: 20px; }
  textarea { width: 100%; height: 70px; padding: 12px; font-size: 15px;
             border: 1px solid #ccc; border-radius: 10px; box-sizing: border-box; }
  .row { display: flex; gap: 10px; align-items: center; margin-top: 10px; }
  button { padding: 10px 18px; font-size: 15px; border: 0; border-radius: 10px;
           background: #2d6cdf; color: #fff; cursor: pointer; }
  button:disabled { background: #9bb6e8; cursor: default; }
  label { font-size: 14px; color: #555; }
  #reply { white-space: pre-wrap; margin-top: 20px; padding: 16px;
           background: #f6f7f9; border-radius: 12px; min-height: 40px; line-height: 1.6; }
  .hint { color: #888; font-size: 13px; margin-top: 6px; }
</style>
</head>
<body>
  <h1>🛍️ ZVZO 판매 비서</h1>
  <textarea id="q" placeholder="예) 오늘 판매 현황 요약해줘 / 이번 주 셀러 일정 알려줘"></textarea>
  <div class="row">
    <button id="send" onclick="ask()">물어보기</button>
    <label><input type="checkbox" id="refresh"> 최신으로 새로고침</label>
  </div>
  <p class="hint">처음 질문이나 새로고침 시 화면을 긁느라 10~20초 걸릴 수 있어요.</p>
  <div id="reply"></div>

<script>
async function ask() {
  const q = document.getElementById('q').value;
  const refresh = document.getElementById('refresh').checked;
  const btn = document.getElementById('send');
  const out = document.getElementById('reply');
  if (!q.trim()) { out.textContent = "질문을 입력해 주세요."; return; }
  btn.disabled = true; out.textContent = "데이터를 확인하는 중... ⏳";
  try {
    const res = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ question: q, refresh })
    });
    const data = await res.json();
    out.textContent = data.reply;
  } catch (e) {
    out.textContent = "요청 실패: " + e;
  } finally {
    btn.disabled = false;
  }
}
</script>
</body>
</html>
"""
