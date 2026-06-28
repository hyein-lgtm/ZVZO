"""
긁어온 화면 텍스트를 Claude에게 주고, 사용자의 질문에 답하게 하는 모듈.
(이 파일은 수정할 필요 거의 없습니다.)
"""

import os
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


def answer(question: str, scraped_data: dict) -> str:
    # 화면별 텍스트를 하나로 합침 (너무 길면 화면당 8000자로 자름)
    context_text = "\n\n".join(
        f"===== {name} 화면 =====\n{text[:8000]}"
        for name, text in scraped_data.items()
    )

    system = (
        "너는 ZVZO 벤더 관리자 화면에서 긁어온 텍스트를 읽고 질문에 답하는 비서다.\n"
        "- 주어진 화면 데이터 안의 사실만 사용한다.\n"
        "- 데이터에 없는 내용은 지어내지 말고 '화면 데이터에서 확인되지 않음'이라고 답한다.\n"
        "- 숫자(매출, 주문건수, 날짜 등)는 정확히 인용한다.\n"
        "- 표로 보여주는 게 명확하면 표로 정리한다.\n"
        "- 한국어로 간결하게 답한다."
    )

    msg = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=system,
        messages=[{
            "role": "user",
            "content": f"[수집된 화면 데이터]\n{context_text}\n\n[질문]\n{question}",
        }],
    )
    return msg.content[0].text
