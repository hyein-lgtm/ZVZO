"""
긁어온 목록 텍스트에서 셀러별 협업 정보를 구조화(JSON)해 뽑아내는 모듈.
"""

import os
import json
import datetime
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


def extract_items(scraped_data: dict) -> list:
    """목록 텍스트 → 셀러별 항목 리스트(dict)로 변환."""
    raw = scraped_data.get("진행목록", "")
    today = datetime.date.today().isoformat()

    system = (
        "너는 ZVZO 협업(코워크) 목록 화면에서 긁어온 텍스트를 분석하는 도구다.\n"
        "각 협업 행에서 아래 정보를 추출해 JSON 배열로만 출력한다. 설명/마크다운 금지, 순수 JSON만.\n"
        "각 항목 형식:\n"
        '{"seller":"셀러명(아이디)","status":"진행중|진행예정|기타","period_start":"YYYY-MM-DD",'
        '"period_end":"YYYY-MM-DD","amount":"판매금액 텍스트(예: 8,206,985원 또는 판매예정)",'
        '"product_count":"상품개수(예: 7개)","discount_rate":"할인율(예: 17%)",'
        '"discount_type":"최저가 보장|단독제공|없음 등","boost": true/false }\n'
        "boost는 'ZVZO 부스트 참여' 표기가 있으면 true.\n"
        "데이터에 없는 값은 빈 문자열로 둔다. 목록에 없는 항목은 만들지 않는다."
    )

    msg = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=system,
        messages=[{
            "role": "user",
            "content": f"오늘 날짜: {today}\n\n[목록 화면 텍스트]\n{raw[:20000]}",
        }],
    )
    text = msg.content[0].text.strip()
    # 혹시 코드펜스가 붙으면 제거
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        # 파싱 실패 시 원문 일부를 에러로 반환
        return [{"seller": "(분석 실패)", "status": "", "amount": text[:200]}]
