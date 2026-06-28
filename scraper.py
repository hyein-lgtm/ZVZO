"""
ZVZO 벤더 관리자에 자동 로그인해서 화면 텍스트를 긁어오는 모듈.

★ 당신이 만질 곳은 아래 '설정' 부분뿐입니다.
   - ZVZO_LOGIN_URL : 로그인 페이지 주소
   - TARGET_PAGES   : 보고 싶은 화면들의 주소
   (아이디/비번은 코드에 적지 않고 환경변수로 넣습니다 - 안전)
"""

import os
from playwright.sync_api import sync_playwright

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


def _try_fill(page, selectors, value):
    """여러 후보 셀렉터 중 처음 잡히는 입력칸에 값을 넣는다."""
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() > 0:
            loc.fill(value)
            return True
    return False


def _try_click(page, selectors):
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() > 0:
            loc.click()
            return True
    return False


def scrape_all() -> dict:
    """로그인 후 TARGET_PAGES의 화면 텍스트를 모아서 dict로 반환."""
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_context(locale="ko-KR").new_page()

        # 1) 로그인 페이지 열기
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)

        # 2) 아이디/비밀번호 입력 (대부분 이 셀렉터들로 자동으로 잡힙니다)
        _try_fill(page, [
            "input[type=email]",
            "input[name*='user' i]",
            "input[name*='id' i]",
            "input[type=text]",
        ], USERNAME)
        _try_fill(page, ["input[type=password]"], PASSWORD)

        # 3) 로그인 버튼 클릭
        _try_click(page, [
            "button:has-text('로그인')",
            "button[type=submit]",
            "input[type=submit]",
            "a:has-text('로그인')",
        ])
        page.wait_for_load_state("networkidle", timeout=60000)
        page.wait_for_timeout(1500)  # 화면 그려질 시간

        # 4) 각 화면 텍스트 수집
        for name, url in TARGET_PAGES.items():
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(2000)
                results[name] = page.inner_text("body")
            except Exception as e:
                results[name] = f"(이 화면 수집 실패: {e})"

        browser.close()
    return results


# 직접 실행해서 테스트할 때: python scraper.py
if __name__ == "__main__":
    data = scrape_all()
    for k, v in data.items():
        print(f"\n===== {k} =====")
        print(v[:1000])
