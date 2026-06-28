"""
ZVZO 협업(코워크) 목록 + 셀러별 상세 모달까지 긁어오는 모듈. (방식 B)

흐름:
 1) 로그인
 2) 진행 목록 페이지 텍스트 수집 (개요용)
 3) 각 행의 '설정' 버튼을 눌러 모달을 열고, 상품/할인가/커미션 텍스트 수집
"""

import os
from playwright.async_api import async_playwright

LOGIN_URL = os.environ.get("ZVZO_LOGIN_URL", "https://store.zvzo.shop/sign-in/")
USERNAME = os.environ["ZVZO_USERNAME"]
PASSWORD = os.environ["ZVZO_PASSWORD"]

LIST_URL = "https://store.zvzo.shop/creator/cowork/?type=in-progress&page=1"

# 한 번에 상세까지 긁을 최대 셀러 수 (너무 많으면 느려져서 상한)
MAX_SELLERS = int(os.environ.get("ZVZO_MAX_SELLERS", "30"))

# 목록에서 각 행의 '설정' 버튼
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
        log.append(f"로그인 실패(주소 그대로) → {page.url}")
        return False


async def _grab_modal_text(page):
    """열린 모달의 텍스트를 최대한 정확히 가져온다."""
    dlg = page.locator("[role=dialog]")
    if await dlg.count() > 0:
        return await dlg.first.inner_text()
    # role=dialog 가 없으면 body 전체에서 가져옴 (목록 텍스트 섞일 수 있음)
    return await page.inner_text("body")


async def scrape_all() -> dict:
    results = {}
    log = []
    details = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await (await browser.new_context(locale="ko-KR")).new_page()

        ok = await _login(page, log)
        if not ok:
            await browser.close()
            results["_진단"] = "\n".join(log)
            return results

        # 목록 페이지 로드 + 개요 텍스트
        await page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        results["진행목록"] = await page.inner_text("body")

        total_btn = await page.locator(SETTINGS_BTN).count()
        n = min(total_btn, MAX_SELLERS)
        log.append(f"'설정' 버튼 {total_btn}개 발견 → {n}개 상세 수집 시도")

        for i in range(n):
            try:
                # 매 회 목록 상태를 깨끗이 (모달 잔여물 방지)
                if i > 0:
                    await page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
                    await page.wait_for_timeout(1800)

                btn = page.locator(SETTINGS_BTN).nth(i)
                await btn.scroll_into_view_if_needed()
                await btn.click()

                # 모달 내용(상품 관리)이 뜰 때까지 대기
                try:
                    await page.wait_for_selector("text=상품 관리", timeout=12000)
                except Exception:
                    await page.wait_for_timeout(2000)
                await page.wait_for_timeout(1200)

                txt = await _grab_modal_text(page)
                details.append(txt)

                # 모달 닫기
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)
            except Exception as e:
                details.append(f"(상세 #{i+1} 수집 실패: {e})")

        results["상세"] = details
        await browser.close()

    log.append(f"상세 {len(details)}건 수집")
    results["_진단"] = "\n".join(log)
    return results
