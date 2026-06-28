"""
ZVZO 협업(코워크) 목록을 긁어오는 모듈. (방식 A - 목록 현황)

로그인 후 진행중/진행예정 목록 페이지의 텍스트를 긁어,
Claude가 셀러/기간/상태/금액/할인율 등을 정리하게 한다.
"""

import os
from playwright.async_api import async_playwright

LOGIN_URL = os.environ.get("ZVZO_LOGIN_URL", "https://store.zvzo.shop/sign-in/")
USERNAME = os.environ["ZVZO_USERNAME"]
PASSWORD = os.environ["ZVZO_PASSWORD"]

# 진행중/진행예정 협업 목록
LIST_URL = "https://store.zvzo.shop/creator/cowork/?type=in-progress&page=1"


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


async def scrape_all() -> dict:
    results = {}
    log = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await (await browser.new_context(locale="ko-KR")).new_page()

        ok = await _login(page, log)
        if ok:
            try:
                await page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(3000)
                log.append(f"목록 도착 → {page.url}")
                # 목록 영역 텍스트 (필요시 전체 body)
                results["진행목록"] = await page.inner_text("body")
            except Exception as e:
                results["진행목록"] = f"(목록 수집 실패: {e})"

        await browser.close()

    results["_진단"] = "\n".join(log)
    return results
