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
        '"product_count":"상품개수","discount_rate":"할인율","discount_type":"할인종류",'
        '"commission":"커미션(예: 17%)","boost":true/false}\n'
        "commission은 목록 맨 오른쪽 '커미션' 컬럼 값(예: 17%, 12%). boost는 'ZVZO 부스트 참여'면 true.\n"
        "설명/코드펜스 금지. 없는 값은 빈 문자열."
    )
    msg = client.messages.create(
        model=MODEL, max_tokens=4000, system=system,
        messages=[{"role": "user", "content": f"오늘:{today}\n\n{list_text[:15000]}"}],
    )
    try:
        items = json.loads(_strip_fence(msg.content[0].text))
    except Exception:
        items = []

    # 1-b) 진행완료 목록도 동일 방식으로 파싱해서 합침 (status=진행완료)
    finished_text = scraped_data.get("완료목록", "")
    if finished_text:
        fsys = (
            "ZVZO '진행완료' 협업 목록 텍스트에서 각 행을 순수 JSON 배열로만 출력.\n"
            '각 항목: {"seller":"셀러명(아이디)","status":"진행완료",'
            '"period_start":"YYYY-MM-DD","period_end":"YYYY-MM-DD","amount":"판매성과 금액 텍스트",'
            '"product_count":"상품개수","discount_rate":"","discount_type":"할인타입",'
            '"commission":"커미션(예: 25%)","boost":true/false}\n'
            "commission은 '커미션' 컬럼 값(변경된 커미션이면 그 %). 설명/코드펜스 금지. 없는 값은 빈 문자열."
        )
        try:
            fmsg = client.messages.create(
                model=MODEL, max_tokens=4000, system=fsys,
                messages=[{"role": "user", "content": f"오늘:{today}\n\n{finished_text[:15000]}"}],
            )
            finished_items = json.loads(_strip_fence(fmsg.content[0].text))
            for fit in finished_items:
                fit["status"] = "진행완료"
                fit.setdefault("products", [])
            items = items + finished_items
        except Exception:
            pass

    # 2) 상세(진행 + 완료)를 파싱. seller 우선, 인스타 링크도 보존.
    details_all = (scraped_data.get("상세", []) or []) + (scraped_data.get("완료상세", []) or [])
    parsed_details = []  # [(name_source, [products], instagram)]
    for d in details_all:
        if isinstance(d, dict):
            name_src = d.get("seller") or d.get("title") or ""
            parsed_details.append((
                name_src,
                _parse_one_detail(d.get("title", ""), d.get("products", [])),
                d.get("instagram", "") or "",
            ))
        else:
            parsed_details.append(("", [], ""))

    # 3) 셀러 매칭: 아이디(괄호 안 영문) 정확일치 우선 → 없으면 이름 일치
    import re as _re

    def _id_of(s):
        m = _re.search(r"\(([a-zA-Z0-9._]+)\)", s or "")
        return m.group(1).strip().lower() if m else ""

    def _name_of(s):
        s = (s or "").split("(")[0]
        for junk in ["추천 상품", "추천상품", "진행중", "진행예정", "진행완료", "오늘 시작", "D-"]:
            s = s.replace(junk, "")
        return s.strip().lower()

    used = [False] * len(parsed_details)

    def take(pred):
        for di, (name_src, prods, insta) in enumerate(parsed_details):
            if used[di] or not prods:
                continue
            if pred(name_src):
                used[di] = True
                return prods, insta
        return None, ""

    for it in items:
        it["products"] = []
        sid = _id_of(it.get("seller", ""))
        sname = _name_of(it.get("seller", ""))

        prods, insta = None, ""
        if sid:
            prods, insta = take(lambda src: _id_of(src) == sid)
        if prods is None and sname:
            prods, insta = take(lambda src: _name_of(src) == sname)
        if prods is None and sname:
            prods, insta = take(lambda src: sname and (sname in _name_of(src) or _name_of(src) in sname))

        if prods is not None:
            it["products"] = prods

        # 인스타 링크: 모달에서 긁은 게 있으면 그것, 없으면 괄호 아이디로 생성
        if insta:
            it["instagram"] = insta
        elif sid:
            it["instagram"] = f"https://instagram.com/{sid}"
        else:
            it["instagram"] = ""

    # 4) 협업 판매금액(누적) 합산 - 보조지표
    total = sum(_won_to_int(it.get("amount", "")) for it in items)
    running_total = sum(
        _won_to_int(it.get("amount", "")) for it in items if "진행중" in (it.get("status", ""))
    )

    # 5) 매출 통계(일자별) 파싱 → 순매출(주문합계-취소) + 월별 수수료 추정
    daily = _parse_report(scraped_data.get("매출통계", ""))
    ZVZO_FIXED = 0.05  # ZVZO 고정 수수료 5%

    monthly = {}
    for day, info in daily.items():
        m = day[:7]
        b = monthly.setdefault(m, {"sales": 0, "cancel": 0, "orders": 0, "net": 0})
        b["sales"] += info.get("sales", 0)
        b["cancel"] += info.get("cancel", 0)
        b["orders"] += info.get("orders", 0)
        b["net"] += info.get("net", 0)

    # 월마다 '그 달에 진행한 셀러들의 평균 커미션' 으로 수수료 계산
    for m, b in monthly.items():
        avg_comm_m = _avg_commission(items, month=m)
        fee_rate_m = avg_comm_m + ZVZO_FIXED
        b["fee"] = round(b["net"] * fee_rate_m)
        b["avg_commission"] = round(avg_comm_m * 100, 1)
        b["fee_rate"] = round(fee_rate_m * 100, 1)

    # 전체 평균(요약 표시용)
    avg_comm_all = _avg_commission(items)

    return {
        "items": items,
        "summary": {
            "total_sales": total,
            "running_sales": running_total,
            "total_count": len(items),
            "running_count": sum(1 for it in items if "진행중" in (it.get("status", ""))),
            "soon_count": sum(1 for it in items if "진행예정" in (it.get("status", ""))),
            "avg_commission": round(avg_comm_all * 100, 1),
            "fee_rate": round((avg_comm_all + ZVZO_FIXED) * 100, 1),
        },
        "daily_sales": daily,
        "monthly_sales": monthly,   # {"2026-06": {sales,cancel,orders,net,fee,avg_commission,fee_rate}}
    }


def _commission_to_float(text):
    """'17%' -> 0.17 ; '-' or '' -> None"""
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if not m:
        return None
    try:
        return float(m.group(1)) / 100.0
    except Exception:
        return None


def _avg_commission(items, month=None):
    """
    선택한 달(month: 'YYYY-MM')과 판매기간이 겹치는 셀러들의 커미션 평균(소수).
    month가 없으면 전체 셀러 평균. 커미션 정보가 없으면 0.12 기본값.
    """
    def overlaps(it):
        if not month:
            return True
        ps = (it.get("period_start") or "")[:7]
        pe = (it.get("period_end") or "")[:7]
        if not ps and not pe:
            return False
        lo = ps or pe
        hi = pe or ps
        return lo <= month <= hi  # 시작월 ~ 종료월 사이에 해당 월이 들어오면 겹침

    rates = []
    for it in items:
        if not overlaps(it):
            continue
        r = _commission_to_float(it.get("commission", ""))
        if r is not None:
            rates.append(r)
    if not rates:
        return 0.12
    return sum(rates) / len(rates)


def _find_col(headers, *keywords):
    """헤더 목록에서 keyword가 포함된 컬럼 인덱스 반환. 없으면 -1."""
    for i, h in enumerate(headers):
        for kw in keywords:
            if kw in (h or ""):
                return i
    return -1


def _num(text):
    if not text:
        return 0
    m = re.findall(r"[\d,]+", str(text))
    if not m:
        return 0
    try:
        return int(m[0].replace(",", ""))
    except Exception:
        return 0


def _parse_report(report_data):
    """
    매출 통계(헤더+행)에서 일자별 {sales(주문합계), cancel(취소/환불), orders(주문수), net(순매출)} 추출.
    헤더 이름으로 컬럼을 찾아 순서가 달라도 정확히 매칭. 구조 추출 실패 시 텍스트 정규식 폴백.
    """
    result = {}
    if not isinstance(report_data, dict):
        report_data = {"headers": [], "rows": [], "text": str(report_data or "")}

    headers = report_data.get("headers", []) or []
    rows = report_data.get("rows", []) or []

    if headers and rows:
        i_date  = _find_col(headers, "날짜", "일자")
        i_sales = _find_col(headers, "주문 합계", "주문합계", "매출", "결제")
        i_cancel= _find_col(headers, "취소", "환불", "반품")
        i_order = _find_col(headers, "주문 수", "주문수")
        for r in rows:
            if i_date < 0 or i_date >= len(r):
                # 날짜 컬럼 못 찾으면 첫 셀이 날짜인지 검사
                day_cell = r[0] if r else ""
            else:
                day_cell = r[i_date]
            mday = re.search(r"\d{4}-\d{2}-\d{2}", day_cell or "")
            if not mday:
                continue
            day = mday.group(0)
            sales  = _num(r[i_sales])  if 0 <= i_sales  < len(r) else 0
            cancel = _num(r[i_cancel]) if 0 <= i_cancel < len(r) else 0
            orders = _num(r[i_order])  if 0 <= i_order  < len(r) else 0
            net = max(sales - cancel, 0)
            result[day] = {"sales": sales, "cancel": cancel, "orders": orders, "net": net}
        if result:
            return result

    # 폴백: 텍스트에서 날짜+숫자 패턴 (취소 컬럼 위치 불명 → net=sales)
    text = report_data.get("text", "") or ""
    pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2})\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)"
    )
    for mm in pattern.finditer(text):
        day = mm.group(1)
        orders = _num(mm.group(4))
        sales = _num(mm.group(6))
        result[day] = {"sales": sales, "cancel": 0, "orders": orders, "net": sales}
    return result
