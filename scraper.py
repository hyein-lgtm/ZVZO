"""
ZVZO 협업(코워크) 목록 + 셀러별 상세 모달까지 긁어오는 모듈. (방식 B - 속도개선)

개선점:
 - 셀러마다 목록을 reload 하지 않고, 모달만 Escape로 닫고 다음으로 진행 (훨씬 빠름)
 - 모달이 안 닫히면 그때만 reload (안전장치)
 - 각 셀러 단계마다 진단 로그를 남겨, 어디서 막히는지 보이게 함
 - 처음엔 적은 수(기본 8)만 처리하도록 상한
"""

import os
from playwright.async_api import async_playwright

LOGIN_URL = os.environ.get("ZVZO_LOGIN_URL", "https://store.zvzo.shop/sign-in/")
USERNAME = os.environ["ZVZO_USERNAME"]
PASSWORD = os.environ["ZVZO_PASSWORD"]

LIST_URL = "https://store.zvzo.shop/creator/cowork/?type=in-progress&page=1"

# 처음엔 적게! 잘 되면 Railway 변수 ZVZO_MAX_SELLERS 를 늘리세요.
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


async def _grab_modal_text(page):
    dlg = page.locator("[role=dialog]")
    if await dlg.count() > 0:
        return await dlg.first.inner_text()
    return await page.inner_text("body")


async def scrape_all() -> dict:
    results = {}
    log = []
    details = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await (await browser.new_context(locale="ko-KR")).new_page()
        # 페이지 기본 타임아웃을 짧게 (무한대기 방지)
        page.set_default_timeout(20000)

        ok = await _login(page, log)
        if not ok:
            await browser.close()
            results["_진단"] = "\n".join(log)
            return results

        await page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2500)
        results["진행목록"] = await page.inner_text("body")

        total = await page.locator(SETTINGS_BTN).count()
        n = min(total, MAX_SELLERS)
        log.append(f"'설정' 버튼 {total}개 발견 → {n}개 상세 수집(상한 {MAX_SELLERS})")

        for i in range(n):
            try:
                btn = page.locator(SETTINGS_BTN).nth(i)
                await btn.scroll_into_view_if_needed()
                await btn.click(timeout=10000)

                try:
                    await page.wait_for_selector("text=상품 관리", timeout=8000)
                except Exception:
                    await page.wait_for_timeout(1500)
                await page.wait_for_timeout(800)

                txt = await _grab_modal_text(page)
                details.append(txt)
                log.append(f"#{i+1} 모달 수집 OK ({len(txt)}자)")

                # 모달 닫기
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(400)

                # 안 닫혔으면 그때만 reload
                if await page.locator("[role=dialog]").count() > 0:
                    await page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
                    await page.wait_for_timeout(1500)
                    log.append(f"#{i+1} 모달 안닫혀서 reload")
            except Exception as e:
                details.append(f"(상세 #{i+1} 실패: {e})")
                log.append(f"#{i+1} 실패: {str(e)[:80]}")
                # 다음을 위해 목록 상태 복구
                try:
                    await page.goto(LIST_URL, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(1200)
                except Exception:
                    pass

        results["상세"] = details
        await browser.close()

    log.append(f"상세 {len(details)}건 수집 완료")
    results["_진단"] = "\n".join(log)
    return results
