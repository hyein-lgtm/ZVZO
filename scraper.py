"""
ZVZO 벤더 관리자에 자동 로그인해서 화면 텍스트를 긁어오는 모듈. (비동기 버전)

★ 당신이 만질 곳은 아래 '설정' 부분뿐입니다.
   - ZVZO_LOGIN_URL : 로그인 페이지 주소
   - TARGET_PAGES   : 보고 싶은 화면들의 주소
   (아이디/비번은 코드에 적지 않고 환경변수로 넣습니다 - 안전)
"""

import os
from playwright.async_api import async_playwright

# ─────────────────────────────────────────────
# 설정 (여기만 수정하세요)
# ─────────────────────────────────────────────
LOGIN_URL = os.environ.get("ZVZO_LOGIN_URL", "https://store.zvzo.shop/login")
USERNAME = os.environ["ZVZO_USERNAME"]   # Railway 환경변수에서 가져옴
PASSWORD = os.environ["ZVZO_PASSWORD"]   # Railway 환경변수에서 가져옴

# 긁어올 화면들: "이름": "주소"
# 판매현황 외에 셀러일정/상품관리 화면 주소도 알면 주석 풀고 추가하세요.
TARGET_PAGES = {
    "판매현황": "https://store.zvzo.shop/setting/vendor/",
    # "셀러일정": "https://store.zvzo.shop/여기에_셀러일정_화면_주소",
    # "상품관리": "https://store.zvzo.shop/여기에_상품관리_화면_주소",
}
# ─────────────────────────────────────────────


async def _try_fill(page, selectors, value):
    """여러 후보 셀렉터 중 처음 잡히는 입력칸에 값을 넣는다."""
    for sel in selectors:
        loc = page.locator(sel).first
        if await loc.count() > 0:
            await loc.fill(value)
            return True
    return False


async def _try_click(page, selectors):
    for sel in selectors:
        loc = page.locator(sel).first
        if await loc.count() > 0:
            await loc.click()
            return True
    return False


async def scrape_all() -> dict:
    """로그인 후 TARGET_PAGES의 화면 텍스트를 모아서 dict로 반환."""
    results = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(locale="ko-KR")
        page = await context.new_page()

        # 1) 로그인 페이지 열기
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)

        # 2) 아이디/비밀번호 입력 (대부분 이 셀렉터들로 자동으로 잡힙니다)
        await _try_fill(page, [
            "input[type=email]",
            "input[name*='user' i]",
            "input[name*='id' i]",
            "input[type=text]",
        ], USERNAME)
        await _try_fill(page, ["input[type=password]"], PASSWORD)

        # 3) 로그인 버튼 클릭
        await _try_click(page, [
            "button:has-text('로그인')",
            "button[type=submit]",
            "input[type=submit]",
            "a:has-text('로그인')",
        ])
        await page.wait_for_load_state("networkidle", timeout=60000)
        await page.wait_for_timeout(1500)  # 화면 그려질 시간

        # 4) 각 화면 텍스트 수집
        for name, url in TARGET_PAGES.items():
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(2000)
                results[name] = await page.inner_text("body")
            except Exception as e:
                results[name] = f"(이 화면 수집 실패: {e})"

        await browser.close()
    return results
