"""
목록 + 셀러별 상세 모달 텍스트를 분석해, 셀러별 협업 정보(+상품/할인가)를
구조화된 JSON으로 뽑아내는 모듈. (방식 B)
"""

import os
import json
import datetime
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


def extract_items(scraped_data: dict) -> list:
    list_text = scraped_data.get("진행목록", "")
    details = scraped_data.get("상세", []) or []
    today = datetime.date.today().isoformat()

    detail_block = "\n\n".join(
        f"--- 상세모달 #{i+1} ---\n{t[:4000]}" for i, t in enumerate(details)
    )

    system = (
        "너는 ZVZO 협업(코워크) 화면 데이터를 정리하는 도구다. 순수 JSON 배열만 출력한다(설명/마크다운 금지).\n"
        "입력은 (1) 협업 목록 텍스트와 (2) 셀러별 상세모달 텍스트들이다.\n"
        "목록의 각 협업 행을 한 항목으로 만들고, 상세모달의 정보가 있으면 해당 셀러 항목의 products에 채운다.\n"
        "상세모달은 보통 '<셀러명> 추천 상품' 제목으로 시작하므로, 그 셀러명을 목록의 셀러명과 매칭한다.\n"
        "각 항목 형식:\n"
        '{"seller":"셀러명(아이디)","status":"진행중|진행예정|기타",'
        '"period_start":"YYYY-MM-DD","period_end":"YYYY-MM-DD",'
        '"amount":"판매금액 텍스트","product_count":"상품개수","discount_rate":"할인율",'
        '"discount_type":"최저가 보장|단독제공|없음 등","boost":true/false,'
        '"products":[{"name":"상품명","original_price":"자사몰 판매가","zvzo_discount":"ZVZO 할인",'
        '"final_price":"최종 판매가","commission":"커미션"}] }\n'
        "상세모달이 없는 셀러는 products를 빈 배열로 둔다. 없는 값은 빈 문자열. 목록에 없는 항목은 만들지 않는다."
    )

    msg = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=system,
        messages=[{
            "role": "user",
            "content": (
                f"오늘 날짜: {today}\n\n[협업 목록 텍스트]\n{list_text[:15000]}\n\n"
                f"[셀러별 상세모달]\n{detail_block[:60000]}"
            ),
        }],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        return [{"seller": "(분석 실패)", "status": "", "amount": text[:200], "products": []}]
