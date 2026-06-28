"""
목록 + 셀러별 상세(article 단위 상품 텍스트+썸네일)를 분석해 JSON으로 추출.
썸네일 URL은 코드가 이미 정확히 잡았으므로 그대로 보존하고,
Claude는 각 상품 텍스트에서 상품명/가격/커미션만 정리한다.
"""

import os
import json
import datetime
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


def _parse_one_detail(title, products):
    """한 셀러의 상품 텍스트들을 Claude로 정리. thumb는 코드값 유지."""
    if not products:
        return []
    listing = []
    for idx, pr in enumerate(products):
        listing.append(f"[상품 {idx}] (thumb 보존됨)\n{pr.get('raw_text','')}")
    joined = "\n\n".join(listing)

    system = (
        "ZVZO 상품 카드 텍스트에서 정보를 추출해 순수 JSON 배열만 출력(설명/코드펜스 금지).\n"
        "입력의 [상품 N] 순서를 그대로 유지해 같은 개수의 배열을 만든다.\n"
        '각 원소: {"idx":N,"name":"상품명","original_price":"자사몰 판매가",'
        '"zvzo_discount":"ZVZO 할인","final_price":"최종 판매가","commission":"커미션"}\n'
        "값이 없으면 빈 문자열. 가격은 '109,900원'처럼 원문 표기 유지."
    )
    msg = client.messages.create(
        model=MODEL, max_tokens=3000, system=system,
        messages=[{"role": "user", "content": f"셀러: {title}\n\n{joined[:12000]}"}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text: text = text.split("\n", 1)[1]
        if text.startswith("json"): text = text[4:]
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = []
    # thumb를 코드가 잡은 값으로 다시 붙임
    out = []
    for idx, pr in enumerate(products):
        info = next((x for x in parsed if x.get("idx") == idx), None) or {}
        out.append({
            "name": info.get("name", ""),
            "original_price": info.get("original_price", ""),
            "zvzo_discount": info.get("zvzo_discount", ""),
            "final_price": info.get("final_price", ""),
            "commission": info.get("commission", ""),
            "thumb": pr.get("thumb", ""),
        })
    return out


def extract_items(scraped_data: dict) -> list:
    list_text = scraped_data.get("진행목록", "")
    details = scraped_data.get("상세", []) or []
    today = datetime.date.today().isoformat()

    # 1) 목록을 항목으로 (셀러/기간/상태/금액/할인/상품수/부스트)
    system = (
        "ZVZO 협업 목록 텍스트에서 각 협업 행을 추출해 순수 JSON 배열만 출력(설명/코드펜스 금지).\n"
        '각 항목: {"seller":"셀러명(아이디)","status":"진행중|진행예정|기타",'
        '"period_start":"YYYY-MM-DD","period_end":"YYYY-MM-DD","amount":"판매금액 텍스트",'
        '"product_count":"상품개수","discount_rate":"할인율","discount_type":"할인종류","boost":true/false}\n'
        "boost는 'ZVZO 부스트 참여' 표기가 있으면 true. 없는 값은 빈 문자열."
    )
    msg = client.messages.create(
        model=MODEL, max_tokens=4000, system=system,
        messages=[{"role": "user", "content": f"오늘:{today}\n\n{list_text[:15000]}"}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text: text = text.split("\n", 1)[1]
        if text.startswith("json"): text = text[4:]
    try:
        items = json.loads(text)
    except Exception:
        items = []

    # 2) 상세(상품)들을 셀러별로 정리
    parsed_details = []  # (title, products[])
    for d in details:
        title = d.get("title", "") if isinstance(d, dict) else ""
        prods = d.get("products", []) if isinstance(d, dict) else []
        parsed_details.append((title, _parse_one_detail(title, prods)))

    # 3) 제목의 셀러명으로 목록 항목과 매칭해 products 부착
    def korean_name(s):
        # '빅토리사 (victorisa)' / '빅토리사 추천 상품' 등에서 한글 앞부분 추출
        s = s or ""
        for cut in ["(", "추천", " "]:
            if cut in s:
                s = s.split(cut)[0]
        return s.strip()

    for it in items:
        it["products"] = []
    used = [False] * len(parsed_details)
    for it in items:
        key = korean_name(it.get("seller", ""))
        for di, (title, prods) in enumerate(parsed_details):
            if used[di]:
                continue
            if key and key in (title or ""):
                it["products"] = prods
                used[di] = True
                break

    return items
