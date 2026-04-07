"""전설적 투자자 전략 점수 계산

- 피터 린치: PEG 비율 중심 성장주 발굴
- 벤저민 그레이엄: 안전마진 중심 가치투자
- 존 템플턴: 역발상 투자 (52주 저점 활용)
"""

import math
import pandas as pd

from src.data.market import fetch_fundamentals, fetch_income_growth


def analyze_lynch(ticker: str) -> dict:
    """피터 린치 전략 — PEG 비율 중심 성장주 발굴.

    핵심: PEG = PER / 영업이익성장률
    PEG < 1이면 성장 대비 저평가 (매수 신호)
    """
    fund = fetch_fundamentals(ticker)
    growth = fetch_income_growth(ticker)

    per = fund.get("per")
    roe = fund.get("roe")
    op_growth = growth.get("op_growth_1y")

    score = 0.0
    details = {}
    passed = 0

    # 1. PEG 비율 (핵심, 가중치 40%)
    if per and op_growth and op_growth > 0:
        peg = per / op_growth
        details["peg"] = f"PEG {peg:.2f}"
        if peg < 0.5:
            score += 0.40
            details["peg"] = f"PEG 초저평가({peg:.2f})"
            passed += 1
        elif peg < 1.0:
            score += 0.25
            details["peg"] = f"PEG 저평가({peg:.2f})"
            passed += 1
        elif peg < 1.5:
            score += 0.05
            details["peg"] = f"PEG 적정({peg:.2f})"
        else:
            score -= 0.15
            details["peg"] = f"PEG 고평가({peg:.2f})"
    elif op_growth and op_growth <= 0:
        score -= 0.20
        details["peg"] = f"이익 감소({op_growth:+.1f}%)"
    elif per and per > 30:
        score -= 0.10
        details["peg"] = f"고PER+성장률 미확인({per:.1f}배)"
    else:
        details["peg"] = "PEG 산출 불가"

    # 2. 영업이익 성장률 (가중치 30%)
    if op_growth is not None:
        if op_growth >= 25:
            score += 0.30
            details["growth"] = f"급성장({op_growth:+.1f}%)"
            passed += 1
        elif op_growth >= 15:
            score += 0.20
            details["growth"] = f"고성장({op_growth:+.1f}%)"
            passed += 1
        elif op_growth >= 5:
            score += 0.10
            details["growth"] = f"성장({op_growth:+.1f}%)"
        elif op_growth >= 0:
            details["growth"] = f"정체({op_growth:+.1f}%)"
        else:
            score -= 0.15
            details["growth"] = f"역성장({op_growth:+.1f}%)"
    else:
        details["growth"] = "성장률 미확인"

    # 3. ROE (가중치 30%)
    if roe is not None:
        if roe >= 20:
            score += 0.30
            details["roe_l"] = f"ROE 우수({roe:.1f}%)"
            passed += 1
        elif roe >= 15:
            score += 0.15
            details["roe_l"] = f"ROE 양호({roe:.1f}%)"
            passed += 1
        elif roe >= 0:
            details["roe_l"] = f"ROE 보통({roe:.1f}%)"
        else:
            score -= 0.15
            details["roe_l"] = f"ROE 적자({roe:.1f}%)"
    else:
        details["roe_l"] = "ROE 미확인"

    score = max(-1.0, min(1.0, score))
    grade = "성장주 매력" if score >= 0.4 else "보통" if score >= 0.1 else "비매력"

    return {"score": score, "details": details, "grade": grade, "passed": passed}


def analyze_graham(ticker: str) -> dict:
    """벤저민 그레이엄 전략 — 안전마진 중심 가치투자.

    핵심: Graham Number = sqrt(22.5 × EPS × BPS)
    현재가 < Graham Number 이면 안전마진 확보
    """
    fund = fetch_fundamentals(ticker)

    per = fund.get("per")
    pbr = fund.get("pbr")
    eps = fund.get("eps", 0)
    bps = fund.get("bps", 0)
    div_yield = fund.get("div_yield", 0)

    score = 0.0
    details = {}
    passed = 0

    # 1. 그레이엄 넘버 (핵심, 가중치 35%)
    if eps and eps > 0 and bps and bps > 0:
        graham_num = math.sqrt(22.5 * eps * bps)
        details["graham_num"] = f"그레이엄넘버 {graham_num:,.0f}원"

        # 현재가와 비교 (현재가 = EPS × PER)
        current_price = eps * per if per else None
        if current_price:
            margin = (graham_num - current_price) / graham_num * 100
            if margin >= 30:
                score += 0.35
                details["margin"] = f"안전마진 {margin:.0f}%"
                passed += 1
            elif margin >= 10:
                score += 0.20
                details["margin"] = f"안전마진 {margin:.0f}%"
                passed += 1
            elif margin >= 0:
                score += 0.05
                details["margin"] = f"소폭안전({margin:.0f}%)"
            else:
                score -= 0.15
                details["margin"] = f"안전마진 부족({margin:.0f}%)"
    else:
        details["graham_num"] = "적자기업(그레이엄넘버 산출불가)"
        score -= 0.20

    # 2. PER < 15 (가중치 25%)
    if per is not None:
        if per < 10:
            score += 0.25
            details["per_g"] = f"PER 저평가({per:.1f}배)"
            passed += 1
        elif per < 15:
            score += 0.15
            details["per_g"] = f"PER 양호({per:.1f}배)"
            passed += 1
        elif per < 20:
            details["per_g"] = f"PER 보통({per:.1f}배)"
        else:
            score -= 0.10
            details["per_g"] = f"PER 고평가({per:.1f}배)"
    else:
        details["per_g"] = "PER 없음(적자)"
        score -= 0.15

    # 3. PBR < 1.5 (가중치 25%)
    if pbr is not None:
        if pbr < 0.75:
            score += 0.25
            details["pbr_g"] = f"PBR 초저평가({pbr:.2f}배)"
            passed += 1
        elif pbr < 1.5:
            score += 0.15
            details["pbr_g"] = f"PBR 저평가({pbr:.2f}배)"
            passed += 1
        elif pbr < 3.0:
            details["pbr_g"] = f"PBR 보통({pbr:.2f}배)"
        else:
            score -= 0.10
            details["pbr_g"] = f"PBR 고평가({pbr:.2f}배)"
    else:
        details["pbr_g"] = "PBR 미확인"

    # 4. 배당 (가중치 15%)
    if div_yield >= 2.0:
        score += 0.15
        details["div_g"] = f"배당 {div_yield:.1f}%"
        passed += 1
    elif div_yield > 0:
        score += 0.05
        details["div_g"] = f"소액배당 {div_yield:.1f}%"
    else:
        details["div_g"] = "무배당"

    score = max(-1.0, min(1.0, score))
    grade = "가치주 매력" if score >= 0.4 else "보통" if score >= 0.1 else "비매력"

    return {"score": score, "details": details, "grade": grade, "passed": passed}


def analyze_templeton(ticker: str, df: pd.DataFrame) -> dict:
    """존 템플턴 전략 — 역발상 투자 (극도의 비관론 속 매수).

    핵심: 52주 최저점 근처 + 저PER/PBR = 역발상 매수 기회
    """
    fund = fetch_fundamentals(ticker)

    per = fund.get("per")
    pbr = fund.get("pbr")

    score = 0.0
    details = {}
    passed = 0

    # 1. 52주 저점 대비 현재가 위치 (핵심, 가중치 40%)
    if df is not None and not df.empty and len(df) >= 20:
        close = df["Close"]
        current = float(close.iloc[-1])
        high_52w = float(close.tail(252).max()) if len(close) >= 252 else float(close.max())
        low_52w = float(close.tail(252).min()) if len(close) >= 252 else float(close.min())

        range_52w = high_52w - low_52w
        if range_52w > 0:
            position = (current - low_52w) / range_52w  # 0=저점, 1=고점
            details["52w"] = f"52주 위치 {position*100:.0f}%(저점기준)"

            if position <= 0.15:
                score += 0.40
                details["52w"] = f"52주 저점권({position*100:.0f}%) — 역발상 매수"
                passed += 1
            elif position <= 0.30:
                score += 0.20
                details["52w"] = f"52주 저점 근처({position*100:.0f}%)"
                passed += 1
            elif position >= 0.85:
                score -= 0.20
                details["52w"] = f"52주 고점권({position*100:.0f}%) — 주의"
            else:
                details["52w"] = f"52주 중간({position*100:.0f}%)"
    else:
        details["52w"] = "가격 데이터 부족"

    # 2. PER 저평가 (가중치 30%)
    if per is not None:
        if per < 8:
            score += 0.30
            details["per_t"] = f"극저평가 PER({per:.1f}배)"
            passed += 1
        elif per < 12:
            score += 0.20
            details["per_t"] = f"저평가 PER({per:.1f}배)"
            passed += 1
        elif per < 20:
            score += 0.05
            details["per_t"] = f"PER 보통({per:.1f}배)"
        else:
            score -= 0.10
            details["per_t"] = f"PER 높음({per:.1f}배)"
    else:
        details["per_t"] = "PER 없음(적자)"
        score -= 0.10

    # 3. PBR 저평가 (가중치 30%)
    if pbr is not None:
        if pbr < 0.5:
            score += 0.30
            details["pbr_t"] = f"극저평가 PBR({pbr:.2f}배)"
            passed += 1
        elif pbr < 1.0:
            score += 0.20
            details["pbr_t"] = f"저평가 PBR({pbr:.2f}배)"
            passed += 1
        elif pbr < 2.0:
            score += 0.05
            details["pbr_t"] = f"PBR 보통({pbr:.2f}배)"
        else:
            score -= 0.10
            details["pbr_t"] = f"PBR 높음({pbr:.2f}배)"
    else:
        details["pbr_t"] = "PBR 미확인"

    score = max(-1.0, min(1.0, score))
    grade = "역발상 매수" if score >= 0.4 else "관망" if score >= 0.1 else "비매력"

    return {"score": score, "details": details, "grade": grade, "passed": passed}


def get_combined_strategy_score(
    ticker: str,
    df: pd.DataFrame,
    buffett_result: dict = None,
) -> dict:
    """버핏 + 린치 + 그레이엄 + 템플턴 종합 전략 점수."""
    from src.analysis.buffett import analyze_buffett

    if buffett_result is None:
        buffett_result = analyze_buffett(ticker)

    lynch = analyze_lynch(ticker)
    graham = analyze_graham(ticker)
    templeton = analyze_templeton(ticker, df)

    # 가중 평균: 버핏30% + 린치30% + 그레이엄25% + 템플턴15%
    combined = (
        buffett_result["score"] * 0.30 +
        lynch["score"] * 0.30 +
        graham["score"] * 0.25 +
        templeton["score"] * 0.15
    )
    combined = max(-1.0, min(1.0, combined))

    return {
        "combined": combined,
        "buffett": buffett_result,
        "lynch": lynch,
        "graham": graham,
        "templeton": templeton,
    }
