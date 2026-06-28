"""
ZVZO 수집기: (1) 협업 목록 (2) 셀러별 상세 모달(article 상품) (3) 일자별 매출 통계.
"""

import os
import datetime
from playwright.async_api import async_playwright

LOGIN_URL = os.environ.get("ZVZO_LOGIN_URL", "https://store.zvzo.shop/sign-in/")
USERNAME = os.environ["ZVZO_USERNAME"]
PASSWORD = os.environ["ZVZO_PASSWORD"]

LIST_URL = "https://store.zvzo.shop/creator/cowork/?type=in-progress&page=1"
FINISHED_URL = "https://store.zvzo.shop/creator/cowork/?type=finished&page=1"
REPORT_URL = "https://store.zvzo.shop/report-pay/report/"
MAX_SELLERS = int(os.environ.get("ZVZO_MAX_SELLERS", "8"))
SETTINGS_BTN = "button:has-text('설정')"


async def _login(page, log):
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(1500)
    await page.wait_for_selector("input#email", timeout=15000)
    email = page.locator("input#email")
    await email.click(); await email.fill(""); await email.type(USERNAME, delay=40)
    pw = page.locator("input#password")
    await pw.click(); await pw.fill(""); await pw.type(PASSWORD, delay=40)
    await page.locator("button:has-text('로그인')").first.click()
    try:
        await page.wait_for_url(lambda u: "sign-in" not in u, timeout=15000)
        log.append(f"로그인 성공 → {page.url}")
        return True
    except Exception:
        log.append(f"로그인 실패 → {page.url}")
        return False


async def _robust_click(page, locator, log, tag):
    try:
        await locator.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass
    for fn in [lambda: locator.click(timeout=4000),
               lambda: locator.click(force=True, timeout=4000)]:
        try:
            await fn(); return True
        except Exception:
            continue
    try:
        h = await locator.element_handle()
        if h:
            await page.evaluate("(el)=>el.click()", h)
            log.append(f"{tag} JS클릭"); return True
    except Exception as e:
        log.append(f"{tag} 클릭실패: {str(e)[:50]}")
    return False


async def _grab_products(page):
    for _ in range(10):
        cnt = await page.locator("article").count()
        body = await page.inner_text("body")
        if cnt > 0 and ("판매가" in body or "최종" in body or "커미션" in body):
            break
        await page.wait_for_timeout(800)
    title = ""
    try:
        t = page.locator("text=추천 상품").first
        if await t.count() > 0:
            title = (await t.inner_text()).strip()
    except Exception:
        pass
    products = []
    arts = page.locator("article")
    for j in range(await arts.count()):
        art = arts.nth(j)
        try:
            txt = await art.inner_text()
        except Exception:
            txt = ""
        if not any(k in txt for k in ["판매가", "커미션", "원"]):
            continue
        thumb = ""
        try:
            imgs = await art.locator("img").evaluate_all(
                "els => els.map(e=>e.src).filter(s=>s && !s.startsWith('data:'))")
            if imgs: thumb = imgs[0]
        except Exception:
            pass
        products.append({"raw_text": txt[:1500], "thumb": thumb})
    return title, products


async def _extract_table(page):
    return await page.evaluate(r"""
    () => {
      const table = document.querySelector('table');
      if (table) {
        const ths = Array.from(table.querySelectorAll('thead th, thead td')).map(e=>e.innerText.trim());
        const rows = Array.from(table.querySelectorAll('tbody tr')).map(tr =>
          Array.from(tr.querySelectorAll('td,th')).map(td=>td.innerText.trim()));
        return { headers: ths, rows };
      }
      const rowsEl = Array.from(document.querySelectorAll('[role=row]'));
      if (rowsEl.length) {
        const all = rowsEl.map(r =>
          Array.from(r.querySelectorAll('[role=cell],[role=gridcell],[role=columnheader],th,td')).map(c=>c.innerText.trim())
        ).filter(a=>a.length);
        return { headers: all[0]||[], rows: all.slice(1) };
      }
      return { headers: [], rows: [], text: document.body.innerText };
    }
    """)


async def _grab_report(page, log):
    """
    매출 통계: 1일~오늘 전체 수집.
    1) URL 쿼리로 기간 지정 시도(여러 파라미터명 후보) → 행 다수면 채택
    2) 안 되면 달력 위젯 직접 입력 + 검색
    3) 페이지네이션이 있으면 끝까지 넘기며 누적
    """
    today = datetime.date.today()
    start_str = today.replace(day=1).isoformat()
    end_str = today.isoformat()

    async def collect_all_pages():
        merged_headers = []
        merged_rows = []
        seen = set()
        for _ in range(15):  # 최대 15페이지
            d = await _extract_table(page)
            if d.get("headers"):
                merged_headers = d["headers"]
            for r in d.get("rows", []):
                key = "|".join(r)
                if key not in seen:
                    seen.add(key); merged_rows.append(r)
            # 다음 페이지 버튼 시도
            moved = False
            for sel in ["button[aria-label*='다음']", "button:has-text('다음')",
                        "a[aria-label*='Next']", "li.next button", "button[aria-label='Next page']"]:
                nxt = page.locator(sel).first
                try:
                    if await nxt.count() > 0 and await nxt.is_enabled():
                        await nxt.click()
                        await page.wait_for_timeout(1500)
                        moved = True
                        break
                except Exception:
                    continue
            if not moved:
                break
        return {"headers": merged_headers, "rows": merged_rows}

    # ---- 1) URL 쿼리 시도 (ZVZO 정확한 파라미터: startDate/endDate/page/perPage) ----
    best = {"headers": [], "rows": []}
    seen = set()
    merged_headers = []
    merged_rows = []
    try:
        for pg in range(1, 16):  # 최대 15페이지
            q = f"?page={pg}&perPage=200&startDate={start_str}&endDate={end_str}"
            await page.goto(REPORT_URL + q, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(2000)
            d = await _extract_table(page)
            if d.get("headers"):
                merged_headers = d["headers"]
            new_count = 0
            for r in d.get("rows", []):
                key = "|".join(r)
                if key not in seen:
                    seen.add(key); merged_rows.append(r); new_count += 1
            log.append(f"page={pg} → 신규행 {new_count} (누적 {len(merged_rows)})")
            if new_count == 0:
                break  # 더 이상 새 데이터 없음
        best = {"headers": merged_headers, "rows": merged_rows}
        days1 = [c for row in merged_rows for c in row if start_str in c]
        log.append(f"URL수집 완료: 행 {len(merged_rows)}, 1일포함 {bool(days1)}")
        if merged_rows:
            log.append(f"헤더={merged_headers}")
            return best
    except Exception as e:
        log.append(f"URL수집 실패: {str(e)[:50]}")

    # ---- 2) 달력 위젯 직접 입력 + 검색 ----
    try:
        await page.goto(REPORT_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2500)
        ins = page.locator("input")
        filled = 0
        for k in range(await ins.count()):
            try:
                v = await ins.nth(k).input_value()
            except Exception:
                v = ""
            if v and "-" in v and len(v) >= 8:  # 날짜형 input
                target = start_str if filled == 0 else end_str
                await ins.nth(k).click()
                await ins.nth(k).fill("")
                await ins.nth(k).type(target, delay=30)
                await page.keyboard.press("Escape")
                filled += 1
                if filled >= 2:
                    break
        if filled:
            log.append(f"달력 직접입력 {filled}칸")
        btn = page.locator("button:has-text('검색')").first
        if await btn.count() > 0:
            await btn.click()
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            log.append("검색 클릭(달력방식)")
        d = await collect_all_pages()
        log.append(f"달력방식 결과 행 {len(d['rows'])}")
        if len(d["rows"]) > len(best["rows"]):
            best = d
    except Exception as e:
        log.append(f"달력방식 실패: {str(e)[:50]}")

    log.append(f"매출 최종 행 {len(best['rows'])}, 헤더={best.get('headers', [])}")
    return best


async def scrape_all() -> dict:
    results = {}
    log = []
    details = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await (await browser.new_context(locale="ko-KR")).new_page()
        page.set_default_timeout(20000)

        ok = await _login(page, log)
        if not ok:
            await browser.close()
            results["_진단"] = "\n".join(log)
            return results

        # (1) 협업 목록
        await page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2500)
        results["진행목록"] = await page.inner_text("body")

        total = await page.locator(SETTINGS_BTN).count()
        n = min(total, MAX_SELLERS)
        log.append(f"'설정' {total}개 → {n}개 시도")

        # (2) 셀러별 상세
        for i in range(n):
            try:
                btn = page.locator(SETTINGS_BTN).nth(i)
                if not await _robust_click(page, btn, log, f"#{i+1}"):
                    details.append({"title": "", "products": []}); continue
                try:
                    await page.wait_for_selector("text=상품 관리", timeout=8000)
                except Exception:
                    await page.wait_for_timeout(1500)
                title, products = await _grab_products(page)
                details.append({"title": title, "products": products})
                log.append(f"#{i+1} '{title[:18]}' 상품 {len(products)}개")
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)
                if await page.locator("article").count() > 0 and "상품 관리" in (await page.inner_text("body")):
                    await page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
                    await page.wait_for_timeout(1500)
            except Exception as e:
                details.append({"title": "", "products": []})
                log.append(f"#{i+1} 예외: {str(e)[:50]}")
                try:
                    await page.goto(LIST_URL, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(1000)
                except Exception:
                    pass
        results["상세"] = details

        # (2-b) 진행완료 목록 (커미션 평균/카드에 반영). 상품 상세는 생략(텍스트만).
        try:
            await page.goto(FINISHED_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(2500)
            results["완료목록"] = await page.inner_text("body")
            log.append("진행완료 목록 수집")
        except Exception as e:
            results["완료목록"] = ""
            log.append(f"진행완료 목록 실패: {str(e)[:50]}")

        # (3) 매출 통계
        results["매출통계"] = await _grab_report(page, log)

        await browser.close()

    log.append(f"상세 {len(details)}건")
    results["_진단"] = "\n".join(log)
    return results
