"""워런 버핏 전략 점수 계산

버핏 핵심 기준:
1. ROE >= 15% — 지속적 고수익
2. PBR < 1.5 — 합리적 가격
3. PER < 25 — 과열 아님
4. 영업이익 성장률 > 0% — 성장 중
5. 배당수익률 > 0 — 주주환원
"""

from src.data.market import fetch_fundamentals, fetch_income_growth


def analyze_buffett(ticker: str) -> dict:
    """버핏 전략 점수를 계산합니다.

    반환:
        score: -1.0 ~ +1.0
        details: 각 항목별 평가 문자열
        grade: "매력적" / "보통" / "비매력적"
    """
    fund = fetch_fundamentals(ticker)
    growth = fetch_income_growth(ticker)

    per = fund.get("per")
    pbr = fund.get("pbr")
    roe = fund.get("roe")
    div_yield = fund.get("div_yield", 0)
    op_growth = growth.get("op_growth_1y")

    score = 0.0
    details = {}
    passed = 0
    total = 0

    # 1. ROE (가중치: 30%)
    total += 1
    if roe is not None:
        if roe >= 20:
            score += 0.30
            details["roe"] = f"우수({roe:.1f}%)"
            passed += 1
        elif roe >= 15:
            score += 0.20
            details["roe"] = f"양호({roe:.1f}%)"
            passed += 1
        elif roe >= 10:
            score += 0.05
            details["roe"] = f"보통({roe:.1f}%)"
        elif roe >= 0:
            score -= 0.10
            details["roe"] = f"저조({roe:.1f}%)"
        else:
            score -= 0.20
            details["roe"] = f"적자({roe:.1f}%)"
    else:
        details["roe"] = "데이터 없음"

    # 2. PER (가중치: 20%)
    total += 1
    if per is not None:
        if per < 10:
            score += 0.20
            details["per_b"] = f"저평가({per:.1f}배)"
            passed += 1
        elif per < 15:
            score += 0.15
            details["per_b"] = f"적정({per:.1f}배)"
            passed += 1
        elif per < 25:
            score += 0.05
            details["per_b"] = f"보통({per:.1f}배)"
        elif per < 40:
            score -= 0.10
            details["per_b"] = f"고평가({per:.1f}배)"
        else:
            score -= 0.20
            details["per_b"] = f"과열({per:.1f}배)"
    else:
        details["per_b"] = "데이터 없음(적자)"

    # 3. PBR (가중치: 20%)
    total += 1
    if pbr is not None:
        if pbr < 1.0:
            score += 0.20
            details["pbr_b"] = f"저평가({pbr:.2f}배)"
            passed += 1
        elif pbr < 1.5:
            score += 0.15
            details["pbr_b"] = f"양호({pbr:.2f}배)"
            passed += 1
        elif pbr < 3.0:
            details["pbr_b"] = f"보통({pbr:.2f}배)"
        else:
            score -= 0.10
            details["pbr_b"] = f"고평가({pbr:.2f}배)"
    else:
        details["pbr_b"] = "데이터 없음"

    # 4. 영업이익 성장률 (가중치: 20%)
    total += 1
    if op_growth is not None:
        if op_growth >= 20:
            score += 0.20
            details["op_growth"] = f"고성장({op_growth:+.1f}%)"
            passed += 1
        elif op_growth >= 5:
            score += 0.10
            details["op_growth"] = f"성장({op_growth:+.1f}%)"
            passed += 1
        elif op_growth >= 0:
            details["op_growth"] = f"정체({op_growth:+.1f}%)"
        else:
            score -= 0.10
            details["op_growth"] = f"이익감소({op_growth:+.1f}%)"
    else:
        details["op_growth"] = "데이터 없음"

    # 5. 배당수익률 (가중치: 10%)
    total += 1
    if div_yield >= 3.0:
        score += 0.10
        details["div_b"] = f"고배당({div_yield:.1f}%)"
        passed += 1
    elif div_yield >= 1.0:
        score += 0.05
        details["div_b"] = f"배당({div_yield:.1f}%)"
    elif div_yield > 0:
        details["div_b"] = f"소액배당({div_yield:.1f}%)"
    else:
        details["div_b"] = "무배당"

    score = max(-1.0, min(1.0, score))

    if score >= 0.4:
        grade = "매력적"
    elif score >= 0.1:
        grade = "보통"
    else:
        grade = "비매력적"

    return {
        "score": score,
        "details": details,
        "grade": grade,
        "passed": passed,
        "total": total,
    }


def format_buffett_summary(result: dict) -> str:
    """버핏 점수를 한 줄 요약으로 변환합니다."""
    score = result["score"]
    grade = result["grade"]
    passed = result["passed"]
    total = result["total"]
    items = " | ".join(result["details"].values())
    return f"버핏전략 {grade}({score:+.2f}, {passed}/{total}개 충족) — {items}"
