"""
ZVZO 벤더 관리자에 자동 로그인해서 화면 텍스트를 긁어오는 모듈. (비동기 버전)

★ 당신이 만질 곳은 아래 '설정' 부분뿐입니다.
   - TARGET_PAGES : 보고 싶은 화면들의 주소
   (아이디/비번/로그인주소는 코드에 적지 않고 환경변수로 넣습니다 - 안전)
"""

import os
from playwright.async_api import async_playwright

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
# 로그인 주소: 기본값을 ZVZO 실제 주소(/sign-in/)로 지정.
# 환경변수 ZVZO_LOGIN_URL 이 있으면 그 값을 우선 사용함.
LOGIN_URL = os.environ.get("ZVZO_LOGIN_URL", "https://store.zvzo.shop/sign-in/")
USERNAME = os.environ["ZVZO_USERNAME"]   # 이메일
PASSWORD = os.environ["ZVZO_PASSWORD"]

# 긁어올 화면들: "이름": "주소"
TARGET_PAGES = {
    "판매현황": "https://store.zvzo.shop/setting/vendor/",
    # "셀러일정": "https://store.zvzo.shop/여기에_셀러일정_화면_주소",
    # "상품관리": "https://store.zvzo.shop/여기에_상품관리_화면_주소",
}
# ─────────────────────────────────────────────


async def scrape_all() -> dict:
    """로그인 후 TARGET_PAGES의 화면 텍스트를 모아서 dict로 반환."""
    results = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(locale="ko-KR")
        page = await context.new_page()

        # 1) 로그인 페이지 열기
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)

        # 2) 이메일 / 비밀번호 입력 (ZVZO 실제 구조에 맞춤)
        await page.fill("input#email", USERNAME)
        await page.fill("input#password", PASSWORD)

        # 3) '로그인' 버튼 클릭 (입점신청 버튼과 헷갈리지 않게 정확히 '로그인'만)
        await page.click("button:has-text('로그인')")

        # 4) 로그인 처리 대기
        await page.wait_for_load_state("networkidle", timeout=60000)
        await page.wait_for_timeout(2500)

        # 5) 각 화면 텍스트 수집
        for name, url in TARGET_PAGES.items():
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(2500)
                results[name] = await page.inner_text("body")
            except Exception as e:
                results[name] = f"(이 화면 수집 실패: {e})"

        await browser.close()
    return results
