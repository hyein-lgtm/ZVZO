"""
ZVZO 협업(코워크) 목록 + 셀러별 상세 모달 수집. (방식 B - 클릭 안정화)

개선점:
 - '설정' 버튼 클릭을 일반 클릭 → force 클릭 → JS dispatch 클릭 순으로 시도
 - 버튼을 화면 중앙으로 스크롤한 뒤 클릭
 - 각 셀러 단계 진단 로그 유지
"""

import os
from playwright.async_api import async_playwright

LOGIN_URL = os.environ.get("ZVZO_LOGIN_URL", "https://store.zvzo.shop/sign-in/")
USERNAME = os.environ["ZVZO_USERNAME"]
PASSWORD = os.environ["ZVZO_PASSWORD"]

LIST_URL = "https://store.zvzo.shop/creator/cowork/?type=in-progress&page=1"
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
    """일반 → force → JS dispatch 순으로 클릭 시도."""
    try:
        await locator.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass
    # 1) 일반 클릭
    try:
        await locator.click(timeout=4000)
        return True
    except Exception:
        pass
    # 2) force 클릭 (가림/안정성 무시)
    try:
        await locator.click(force=True, timeout=4000)
        log.append(f"{tag} force클릭")
        return True
    except Exception:
        pass
    # 3) JS로 직접 클릭
    try:
        handle = await locator.element_handle()
        if handle:
            await page.evaluate("(el) => el.click()", handle)
            log.append(f"{tag} JS클릭")
            return True
    except Exception as e:
        log.append(f"{tag} 모든클릭 실패: {str(e)[:60]}")
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
        log.append(f"'설정' 버튼 {total}개 → {n}개 시도")

        for i in range(n):
            try:
                btn = page.locator(SETTINGS_BTN).nth(i)
                clicked = await _robust_click(page, btn, log, f"#{i+1}")
                if not clicked:
                    details.append(f"(상세 #{i+1}: 클릭 실패)")
                    continue

                # 모달이 뜨는지 확인
                opened = False
                try:
                    await page.wait_for_selector("text=상품 관리", timeout=8000)
                    opened = True
                except Exception:
                    # 상품 관리 텍스트가 없을 수도 있으니 dialog 로도 확인
                    if await page.locator("[role=dialog]").count() > 0:
                        opened = True
                await page.wait_for_timeout(900)

                if opened:
                    txt = await _grab_modal_text(page)
                    details.append(txt)
                    log.append(f"#{i+1} 모달 OK ({len(txt)}자)")
                else:
                    details.append(f"(상세 #{i+1}: 모달 안뜸)")
                    log.append(f"#{i+1} 모달 안뜸")

                # 닫기
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(400)
                if await page.locator("[role=dialog]").count() > 0:
                    await page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
                    await page.wait_for_timeout(1500)
            except Exception as e:
                details.append(f"(상세 #{i+1} 실패: {e})")
                log.append(f"#{i+1} 예외: {str(e)[:60]}")
                try:
                    await page.goto(LIST_URL, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(1000)
                except Exception:
                    pass

        results["상세"] = details
        await browser.close()

    log.append(f"상세 {len(details)}건")
    results["_진단"] = "\n".join(log)
    return results
