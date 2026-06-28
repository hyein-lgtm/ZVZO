"""
ZVZO 협업 목록 + 셀러별 상세 모달 수집. (방식 B - 모달 내용 로딩 대기 강화 + 썸네일)

핵심:
 - 모달을 연 뒤 '상품 관리' + 실제 상품 카드가 그려질 때까지 기다림
 - 모달 텍스트가 너무 짧으면(=아직 로딩 중) 더 기다렸다가 다시 긁음
 - 모달 안 상품 썸네일 이미지 URL도 함께 수집
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
    try:
        await locator.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass
    for how, fn in [
        ("일반", lambda: locator.click(timeout=4000)),
        ("force", lambda: locator.click(force=True, timeout=4000)),
    ]:
        try:
            await fn()
            return True
        except Exception:
            continue
    try:
        h = await locator.element_handle()
        if h:
            await page.evaluate("(el)=>el.click()", h)
            log.append(f"{tag} JS클릭")
            return True
    except Exception as e:
        log.append(f"{tag} 클릭실패: {str(e)[:50]}")
    return False


async def _grab_modal(page):
    """모달 내용이 충분히 로딩될 때까지 기다린 뒤 텍스트 + 썸네일 수집."""
    # 1) 상품 관리 + 가격 텍스트가 보일 때까지 시도
    for _ in range(8):  # 최대 ~8초 추가 대기
        # role=dialog 우선
        dlg = page.locator("[role=dialog]")
        target = dlg.first if await dlg.count() > 0 else page.locator("body")
        try:
            txt = await target.inner_text()
        except Exception:
            txt = ""
        # '판매가' 또는 '원' 가격 신호가 충분하면 완료로 간주
        if len(txt) > 400 and ("판매가" in txt or "최종" in txt or "커미션" in txt):
            # 썸네일 이미지 URL 수집 (모달 범위 내 img)
            try:
                imgs = await target.locator("img").evaluate_all(
                    "els => els.map(e => e.src).filter(s => s && !s.startsWith('data:'))"
                )
            except Exception:
                imgs = []
            return txt, imgs
        await page.wait_for_timeout(1000)
    # 끝까지 부족하면 마지막으로 가진 것 반환
    return txt, []


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
        log.append(f"'설정' {total}개 → {n}개 시도")

        for i in range(n):
            try:
                btn = page.locator(SETTINGS_BTN).nth(i)
                if not await _robust_click(page, btn, log, f"#{i+1}"):
                    details.append({"text": f"(#{i+1} 클릭실패)", "imgs": []})
                    continue

                try:
                    await page.wait_for_selector("text=상품 관리", timeout=8000)
                except Exception:
                    await page.wait_for_timeout(1500)

                txt, imgs = await _grab_modal(page)
                details.append({"text": txt, "imgs": imgs})
                log.append(f"#{i+1} 모달 {len(txt)}자, 이미지 {len(imgs)}개")

                await page.keyboard.press("Escape")
                await page.wait_for_timeout(400)
                if await page.locator("[role=dialog]").count() > 0:
                    await page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
                    await page.wait_for_timeout(1500)
            except Exception as e:
                details.append({"text": f"(#{i+1} 실패: {e})", "imgs": []})
                log.append(f"#{i+1} 예외: {str(e)[:50]}")
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
