"""
ZVZO 벤더 관리자에 자동 로그인해서 화면 텍스트를 긁어오는 모듈.
(로그인 안정화 + 진단 버전)
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
    log = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(locale="ko-KR")
        page = await context.new_page()

        # 1) 로그인 페이지 열기
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1500)
        log.append(f"로그인페이지 접속 → {page.url}")

        # 2) 입력칸이 나타날 때까지 기다린 뒤, 클릭→비우고→한 글자씩 타이핑
        try:
            await page.wait_for_selector("input#email", timeout=15000)
            email = page.locator("input#email")
            await email.click()
            await email.fill("")
            await email.type(USERNAME, delay=40)

            pw = page.locator("input#password")
            await pw.click()
            await pw.fill("")
            await pw.type(PASSWORD, delay=40)

            # 입력이 실제로 들어갔는지 확인 (비번은 길이만)
            typed_email = await email.input_value()
            typed_pw = await pw.input_value()
            log.append(f"입력확인 → 이메일='{typed_email}', 비번길이={len(typed_pw)}")
        except Exception as e:
            log.append(f"입력 단계 실패: {e}")

        # 3) 로그인 버튼 클릭 (+ 안 되면 Enter)
        try:
            btn = page.locator("button:has-text('로그인')").first
            await btn.click()
            log.append("로그인 버튼 클릭")
        except Exception as e:
            log.append(f"버튼 클릭 실패({e}) → Enter 시도")
            try:
                await page.locator("input#password").press("Enter")
            except Exception as e2:
                log.append(f"Enter도 실패: {e2}")

        # 4) 로그인 결과 대기 (주소가 sign-in 을 벗어나는지)
        try:
            await page.wait_for_url(lambda u: "sign-in" not in u, timeout=15000)
            log.append(f"로그인 성공! 이동 → {page.url}")
            login_ok = True
        except Exception:
            log.append(f"로그인 후에도 sign-in 페이지에 머무름 → {page.url}")
            login_ok = False

        await page.wait_for_timeout(2000)

        # 로그인 실패 시: 화면에 뜬 에러/안내 문구를 잡아본다
        if not login_ok:
            try:
                body_now = await page.inner_text("body")
                # 흔한 에러 키워드 주변 텍스트 추출
                for kw in ["비밀번호", "이메일", "일치", "오류", "확인", "없는", "잘못"]:
                    idx = body_now.find(kw)
                    if idx != -1:
                        log.append(f"화면문구('{kw}' 부근): ...{body_now[max(0,idx-20):idx+40]}...")
                        break
            except Exception as e:
                log.append(f"에러문구 읽기 실패: {e}")

        # 5) 각 화면 텍스트 수집
        for name, url in TARGET_PAGES.items():
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(2500)
                log.append(f"[{name}] 도착주소: {page.url}")
                results[name] = await page.inner_text("body")
            except Exception as e:
                results[name] = f"(이 화면 수집 실패: {e})"

        await browser.close()

    results["_진단"] = "\n".join(log)
    return results
