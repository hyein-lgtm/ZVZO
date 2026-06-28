"""
ZVZO 벤더 관리자에 자동 로그인해서 화면 텍스트를 긁어오는 모듈. (진단 버전)

이번 버전은 '어디서 막히는지'를 보여주기 위해 각 단계의 진단 정보를
'_진단' 항목으로 함께 반환합니다.
"""

import os
from playwright.async_api import async_playwright

LOGIN_URL = os.environ.get("ZVZO_LOGIN_URL", "https://store.zvzo.shop/sign-in/")
USERNAME = os.environ["ZVZO_USERNAME"]
PASSWORD = os.environ["ZVZO_PASSWORD"]

TARGET_PAGES = {
    "판매현황": "https://store.zvzo.shop/setting/vendor/",
}


async def scrape_all() -> dict:
    results = {}
    log = []  # 진단 로그

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(locale="ko-KR")
        page = await context.new_page()

        # 1) 로그인 페이지 열기
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        log.append(f"로그인페이지 접속 → 현재주소: {page.url}")

        # 2) 입력칸 존재 확인 + 입력
        email_cnt = await page.locator("input#email").count()
        pw_cnt = await page.locator("input#password").count()
        log.append(f"이메일칸 발견: {email_cnt}개, 비번칸 발견: {pw_cnt}개")

        if email_cnt > 0:
            await page.fill("input#email", USERNAME)
        if pw_cnt > 0:
            await page.fill("input#password", PASSWORD)

        # 3) 로그인 버튼 클릭
        btn = page.locator("button:has-text('로그인')")
        log.append(f"'로그인' 버튼 발견: {await btn.count()}개")
        try:
            await btn.first.click()
            log.append("로그인 버튼 클릭함")
        except Exception as e:
            log.append(f"로그인 버튼 클릭 실패: {e}")

        # 4) 로그인 처리 대기 (주소가 바뀌는지 확인)
        try:
            await page.wait_for_url(lambda u: "sign-in" not in u, timeout=15000)
            log.append(f"로그인 후 주소 이동됨 → {page.url}")
        except Exception:
            log.append(f"로그인 후 주소가 그대로임(로그인 실패 가능) → {page.url}")

        await page.wait_for_timeout(2500)

        # 로그인 직후 화면에 에러 메시지가 있는지 확인
        try:
            body_now = await page.inner_text("body")
            snippet = body_now[:400].replace("\n", " ")
            log.append(f"로그인 직후 화면 일부: {snippet}")
        except Exception as e:
            log.append(f"화면 읽기 실패: {e}")

        # 5) 각 화면 텍스트 수집
        for name, url in TARGET_PAGES.items():
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(2500)
                log.append(f"[{name}] 이동 후 주소: {page.url}")
                results[name] = await page.inner_text("body")
            except Exception as e:
                results[name] = f"(이 화면 수집 실패: {e})"

        await browser.close()

    results["_진단"] = "\n".join(log)
    return results
