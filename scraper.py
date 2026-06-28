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


async def _grab_report(page, log):
    """매출 통계 페이지에서 '이번 달 1일 ~ 오늘' 일자별 매출 텍스트 수집."""
    try:
        await page.goto(REPORT_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2500)
        # 페이지 전체 텍스트를 가져와서 agent가 '날짜 + 주문합계'를 파싱
        text = await page.inner_text("body")
        log.append(f"매출 통계 수집 ({len(text)}자)")
        return text
    except Exception as e:
        log.append(f"매출 통계 실패: {str(e)[:60]}")
        return ""


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

        # (3) 매출 통계
        results["매출통계"] = await _grab_report(page, log)

        await browser.close()

    log.append(f"상세 {len(details)}건")
    results["_진단"] = "\n".join(log)
    return results
