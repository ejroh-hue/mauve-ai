"""외국인/기관 수급 분석"""

import pandas as pd

from src.models import InvestorFlowSignal
from src.data.market import get_investor_trading


def analyze_investor_flow(ticker: str, days: int = 20) -> InvestorFlowSignal:
    """외국인/기관 순매수 데이터를 분석하여 수급 점수를 산출합니다."""
    df = get_investor_trading(ticker, days)

    if df.empty:
        return InvestorFlowSignal(
            ticker=ticker,
            foreign_net_5d=0, foreign_net_20d=0,
            inst_net_5d=0, inst_net_20d=0,
            score=0.0, summary="수급 데이터 없음",
        )

    # 네이버 금융 기반: 컬럼명 '기관', '외국인' (순매매량, 주 단위)
    foreign_col = None
    inst_col = None
    for col in df.columns:
        if "외국인" in col:
            foreign_col = col
        if "기관" in col:
            inst_col = col

    if foreign_col is None or inst_col is None:
        return InvestorFlowSignal(
            ticker=ticker,
            foreign_net_5d=0, foreign_net_20d=0,
            inst_net_5d=0, inst_net_20d=0,
            score=0.0, summary="수급 컬럼 매칭 실패",
        )

    # 순매매량 (만주 단위로 변환)
    foreign_5d = df[foreign_col].tail(5).sum() / 1e4
    foreign_20d = df[foreign_col].tail(20).sum() / 1e4
    inst_5d = df[inst_col].tail(5).sum() / 1e4
    inst_20d = df[inst_col].tail(20).sum() / 1e4

    # 수급 점수 산출
    score = 0.0
    summary_parts = []

    # 외국인 수급 (만주 기준)
    if foreign_5d > 10:
        score += 0.15
        summary_parts.append(f"외국인 5일 순매수 {foreign_5d:+.0f}만주")
    elif foreign_5d < -10:
        score -= 0.15
        summary_parts.append(f"외국인 5일 순매도 {foreign_5d:+.0f}만주")

    # 기관 수급
    if inst_5d > 10:
        score += 0.10
        summary_parts.append(f"기관 5일 순매수 {inst_5d:+.0f}만주")
    elif inst_5d < -10:
        score -= 0.10
        summary_parts.append(f"기관 5일 순매도 {inst_5d:+.0f}만주")

    # 외국인+기관 동반 매수/매도 시 가중
    if foreign_5d > 5 and inst_5d > 5:
        score += 0.10
        summary_parts.append("외국인+기관 동반 매수")
    elif foreign_5d < -5 and inst_5d < -5:
        score -= 0.10
        summary_parts.append("외국인+기관 동반 매도")

    # 20일 추세
    if foreign_20d > 50:
        score += 0.05
    elif foreign_20d < -50:
        score -= 0.05

    score = max(-0.5, min(0.5, score))

    if not summary_parts:
        summary_parts.append("수급 중립")

    return InvestorFlowSignal(
        ticker=ticker,
        foreign_net_5d=round(foreign_5d, 1),
        foreign_net_20d=round(foreign_20d, 1),
        inst_net_5d=round(inst_5d, 1),
        inst_net_20d=round(inst_20d, 1),
        score=score,
        summary=" / ".join(summary_parts),
    )
