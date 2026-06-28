"""
목록 + 셀러별 상세모달(텍스트+이미지)을 분석해 셀러별 협업/상품 정보를 JSON으로 추출.
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

    blocks = []
    for i, d in enumerate(details):
        if isinstance(d, dict):
            t = d.get("text", "")
            imgs = d.get("imgs", []) or []
        else:  # 옛 형식 호환
            t, imgs = str(d), []
        img_line = "\n[이 모달의 이미지 URL들]\n" + "\n".join(imgs[:20]) if imgs else ""
        blocks.append(f"--- 상세모달 #{i+1} ---\n{t[:4000]}{img_line}")
    detail_block = "\n\n".join(blocks)

    system = (
        "너는 ZVZO 협업 화면 데이터를 정리하는 도구다. 순수 JSON 배열만 출력(설명/마크다운/코드펜스 금지).\n"
        "입력: (1) 협업 목록 텍스트 (2) 셀러별 상세모달(텍스트+이미지URL).\n"
        "목록의 각 행을 한 항목으로, 상세모달 정보가 있으면 해당 셀러 항목의 products에 채운다.\n"
        "상세모달은 보통 '<셀러명> 추천 상품' 제목으로 시작 → 그 셀러명으로 목록과 매칭.\n"
        "상품 썸네일은 상세모달의 이미지URL 중 상품 이미지로 보이는 것을 순서대로 product의 thumb에 넣는다(프로필/로고/아이콘은 제외).\n"
        "각 항목 형식:\n"
        '{"seller":"셀러명(아이디)","status":"진행중|진행예정|기타","period_start":"","period_end":"",'
        '"amount":"","product_count":"","discount_rate":"","discount_type":"","boost":false,'
        '"products":[{"name":"상품명","original_price":"자사몰 판매가","zvzo_discount":"ZVZO 할인",'
        '"final_price":"최종 판매가","commission":"커미션","thumb":"썸네일 이미지 URL"}] }\n'
        "상세모달이 없거나 상품을 못 찾으면 products는 빈 배열. 없는 값은 빈 문자열. 목록에 없는 항목은 만들지 않는다."
    )

    msg = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=system,
        messages=[{
            "role": "user",
            "content": (
                f"오늘 날짜: {today}\n\n[협업 목록]\n{list_text[:15000]}\n\n"
                f"[셀러별 상세모달]\n{detail_block[:80000]}"
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
