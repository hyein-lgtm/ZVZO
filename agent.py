"""
목록 + 셀러별 상세(article 상품)를 분석해 JSON으로 추출.
- 상품 매칭은 '긁은 순서'(설정 버튼 순서 = 목록 순서)로 1:1 연결 → 동명이인 문제 해결.
- 판매금액을 합산해 매출 요약(총/진행중) 제공.
"""

import os
import re
import json
import datetime
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


def _strip_fence(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
        if text.startswith("json"):
            text = text[4:]
    return text


def _parse_one_detail(title, products):
    if not products:
        return []
    listing = [f"[상품 {i}]\n{pr.get('raw_text','')}" for i, pr in enumerate(products)]
    joined = "\n\n".join(listing)
    system = (
        "ZVZO 상품 카드 텍스트에서 정보를 추출해 순수 JSON 배열만 출력(설명/코드펜스 금지).\n"
        "입력의 [상품 N] 순서를 유지해 같은 개수의 배열을 만든다.\n"
        '각 원소: {"idx":N,"name":"상품명","original_price":"자사몰 판매가",'
        '"zvzo_discount":"ZVZO 할인","final_price":"최종 판매가","commission":"커미션"}\n'
        "값이 없으면 빈 문자열. 가격은 원문 표기 유지."
    )
    msg = client.messages.create(
        model=MODEL, max_tokens=3000, system=system,
        messages=[{"role": "user", "content": f"셀러:{title}\n\n{joined[:12000]}"}],
    )
    try:
        parsed = json.loads(_strip_fence(msg.content[0].text))
    except Exception:
        parsed = []
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


def _won_to_int(text):
    """'8,206,985 원' → 8206985. 숫자 없으면 0."""
    if not text:
        return 0
    nums = re.findall(r"[\d,]+", text)
    if not nums:
        return 0
    return int(nums[0].replace(",", ""))


def extract_items(scraped_data: dict) -> dict:
    list_text = scraped_data.get("진행목록", "")
    details = scraped_data.get("상세", []) or []
    today = datetime.date.today().isoformat()

    # 1) 목록 → 항목 (순서 보존)
    system = (
        "ZVZO 협업 목록 텍스트에서 각 협업 행을 화면에 나타난 순서 그대로 추출해 순수 JSON 배열만 출력.\n"
        '각 항목: {"seller":"셀러명(아이디)","status":"진행중|진행예정|기타",'
        '"period_start":"YYYY-MM-DD","period_end":"YYYY-MM-DD","amount":"판매금액 텍스트",'
        '"product_count":"상품개수","discount_rate":"할인율","discount_type":"할인종류","boost":true/false}\n'
        "boost는 'ZVZO 부스트 참여'면 true. 설명/코드펜스 금지. 없는 값은 빈 문자열."
    )
    msg = client.messages.create(
        model=MODEL, max_tokens=4000, system=system,
        messages=[{"role": "user", "content": f"오늘:{today}\n\n{list_text[:15000]}"}],
    )
    try:
        items = json.loads(_strip_fence(msg.content[0].text))
    except Exception:
        items = []

    # 2) 상세를 순서대로 파싱
    parsed_products = []
    for d in details:
        if isinstance(d, dict):
            parsed_products.append(_parse_one_detail(d.get("title", ""), d.get("products", [])))
        else:
            parsed_products.append([])

    # 3) 순서 기반 1:1 매칭 (목록 i번째 ↔ 상세 i번째)
    for i, it in enumerate(items):
        it["products"] = parsed_products[i] if i < len(parsed_products) else []

    # 4) 협업 판매금액(누적) 합산 - 보조지표
    total = sum(_won_to_int(it.get("amount", "")) for it in items)
    running_total = sum(
        _won_to_int(it.get("amount", "")) for it in items if "진행중" in (it.get("status", ""))
    )

    # 5) 매출 통계(일자별) 파싱 → 일자별/월별 실매출
    daily = _parse_report(scraped_data.get("매출통계", ""))
    monthly = {}
    for day, info in daily.items():
        m = day[:7]
        b = monthly.setdefault(m, {"sales": 0, "orders": 0})
        b["sales"] += info["sales"]
        b["orders"] += info["orders"]

    return {
        "items": items,
        "summary": {
            "total_sales": total,
            "running_sales": running_total,
            "total_count": len(items),
            "running_count": sum(1 for it in items if "진행중" in (it.get("status", ""))),
            "soon_count": sum(1 for it in items if "진행예정" in (it.get("status", ""))),
        },
        "daily_sales": daily,       # {"2026-06-28": {"sales":530838,"orders":22}, ...}
        "monthly_sales": monthly,   # {"2026-06": {"sales":..., "orders":...}, ...}
    }


def _parse_report(report_text):
    """
    매출 통계 페이지 텍스트에서 (날짜, 주문합계, 주문수)를 추출.
    행 패턴: '2026-06-28  345  62  22  24  530838  다운로드' 같이
    날짜 뒤에 숫자들이 이어진다. 마지막 큰 숫자를 '주문합계(매출)'로,
    주문수는 LLM 없이 휴리스틱으로 잡는다.
    반환: {"YYYY-MM-DD": {"sales": int, "orders": int}}
    """
    import re
    result = {}
    if not report_text:
        return result
    # 날짜로 시작하는 토막을 찾기 위해, 날짜 위치 기준으로 분할
    # 한 줄에 날짜+숫자들이 공백/줄바꿈으로 섞여 있을 수 있어 정규식으로 처리
    # 날짜 + 그 뒤 첫 6개 숫자(상품조회,쇼핑몰조회,주문수,품목수,주문합계) 가정
    pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2})\s+"
        r"([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)"
    )
    for m in pattern.finditer(report_text):
        day = m.group(1)
        try:
            orders = int(m.group(4).replace(",", ""))     # 주문 수
            sales = int(m.group(6).replace(",", ""))      # 주문 합계(매출)
        except Exception:
            continue
        result[day] = {"sales": sales, "orders": orders}
    return result
