"""오케스트레이터 — 데이터 수집 → 분석 → 조언 파이프라인"""

import sys
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from src.models import (
    PortfolioHolding, PortfolioAdvice, FinalSignal, QuantSignal, LLMSignal,
)
from src.data.market import (
    fetch_ohlcv, get_stock_name, get_etf_ohlcv,
    fetch_us_ohlcv, get_us_stock_name, is_us_ticker, get_usd_krw,
)
from src.data.portfolio import load_portfolio, load_settings, get_total_cost
from src.data.news import get_news
from src.analysis.quant import analyze_quant
from src.analysis.llm import analyze_llm
from src.analysis.investor_flow import analyze_investor_flow
from src.analysis.portfolio_advisor import advise
from src.storage.db import save_signal, save_portfolio_snapshot


def combine_signals(
    quant: QuantSignal,
    llm: Optional[LLMSignal] = None,
    quant_weight: float = 0.6,
    llm_weight: float = 0.4,
    buy_threshold: float = 0.3,
    sell_threshold: float = -0.3,
) -> FinalSignal:
    """퀀트 + LLM 점수를 가중 합산하여 최종 매매 신호를 결정합니다."""
    if llm is None:
        llm = LLMSignal("neutral", 0.0, "LLM 분석 미실행", "N/A")
        # LLM 없으면 퀀트에 100% 가중
        combined = quant.score
    else:
        combined = quant.score * quant_weight + llm.score * llm_weight

    if combined >= buy_threshold:
        action = "BUY"
    elif combined <= sell_threshold:
        action = "SELL"
    else:
        action = "HOLD"

    summary_parts = []
    for key, val in quant.details.items():
        summary_parts.append(f"[{key.upper()}] {val}")
    if llm.reasoning and llm.reasoning != "LLM 분석 미실행":
        summary_parts.append(f"[LLM] {llm.reasoning}")

    return FinalSignal(
        ticker=quant.ticker,
        name=quant.name,
        action=action,
        combined_score=combined,
        quant_score=quant.score,
        llm_score=llm.score,
        current_price=quant.current_price,
        analysis_summary=" | ".join(summary_parts),
    )


def analyze_single(
    ticker: str,
    name: str = "",
    asset_type: str = "stock",
    holding: Optional[PortfolioHolding] = None,
    settings: Optional[dict] = None,
) -> Optional[FinalSignal]:
    """단일 종목 분석 (퀀트 + 뉴스 + LLM)"""
    if settings is None:
        settings = load_settings().get("analysis", {})

    try:
        us_stock = is_us_ticker(ticker)
        if not name:
            name = get_us_stock_name(ticker) if us_stock else get_stock_name(ticker)
        print(f"\n  [{name} ({ticker})] 분석 중..." + (" [US]" if us_stock else ""))

        # 1. 데이터 수집
        usd_krw = 1.0
        if us_stock:
            df = fetch_us_ohlcv(ticker, days=settings.get("lookback_days", 120))
            usd_krw = get_usd_krw()
            # USD → KRW 환산 (손익률 계산용, holding.buy_price는 USD)
        elif asset_type == "etf":
            df = get_etf_ohlcv(ticker)
        else:
            df = fetch_ohlcv(ticker, days=settings.get("lookback_days", 120))

        # 2. 퀀트 분석
        quant = analyze_quant(ticker, df)
        quant.name = name
        print(f"    퀀트: {quant.score:+.2f}")

        # 3. 수급 분석 (ETF는 스킵)
        flow = None
        if asset_type != "etf":
            flow = analyze_investor_flow(ticker)
            if flow.score != 0.0:
                print(f"    수급: {flow.score:+.2f} ({flow.summary})")

        # 4. 뉴스 수집 + LLM 분석 (ETF는 스킵)
        llm = None
        if asset_type != "etf":
            news_items = get_news(ticker, name)
            if news_items:
                print(f"    뉴스: {len(news_items)}건 수집")
            llm = analyze_llm(ticker, name, quant, news_items, holding)
            if llm.score != 0.0 or llm.sentiment != "neutral":
                print(f"    LLM:  {llm.score:+.2f} ({llm.sentiment})")

        # 수급 점수를 퀀트에 합산
        if flow and flow.score != 0.0:
            quant.score = max(-1.0, min(1.0, quant.score + flow.score))
            quant.details["flow"] = flow.summary

        # 5. 신호 통합
        final = combine_signals(
            quant,
            llm=llm,
            quant_weight=settings.get("quant_weight", 0.6),
            llm_weight=settings.get("llm_weight", 0.4),
            buy_threshold=settings.get("buy_threshold", 0.3),
            sell_threshold=settings.get("sell_threshold", -0.3),
        )

        return final

    except Exception as e:
        print(f"    [오류] {ticker} 분석 실패: {e}")
        return None


def analyze_portfolio() -> list[PortfolioAdvice]:
    """전체 포트폴리오 분석"""
    holdings = load_portfolio()
    settings = load_settings()
    analysis_settings = settings.get("analysis", {})
    portfolio_settings = settings.get("portfolio", {})

    if not holdings:
        print("포트폴리오가 비어 있습니다. config/portfolio.yaml을 확인하세요.")
        return []

    # 1차: 전 종목 현재가 수집 → 총 평가액 계산
    signals: dict[str, FinalSignal] = {}
    print(f"총 {len(holdings)}개 종목 분석 시작...\n")

    def _analyze(holding: PortfolioHolding):
        return holding.ticker, analyze_single(
            ticker=holding.ticker,
            name=holding.name,
            asset_type=holding.asset_type,
            holding=holding,
            settings=analysis_settings,
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_analyze, h): h for h in holdings}
        for future in as_completed(futures):
            ticker, signal = future.result()
            if signal:
                signals[ticker] = signal

    # 총 평가액 계산 (미국 주식은 USD → KRW 환산)
    usd_krw_rate = get_usd_krw()
    total_eval = sum(
        signals[h.ticker].current_price * h.quantity * (usd_krw_rate if is_us_ticker(h.ticker) else 1)
        for h in holdings if h.ticker in signals
    )

    # 포트폴리오 조언 생성
    advices = []
    for holding in holdings:
        if holding.ticker not in signals:
            continue

        advice = advise(
            holding=holding,
            signal=signals[holding.ticker],
            total_portfolio_value=total_eval,
            settings=portfolio_settings,
        )
        advices.append(advice)

    # 시그널 및 스냅샷 저장
    for advice in advices:
        save_signal(advice)
    save_portfolio_snapshot(advices)
    print(f"\n  [저장] {len(advices)}개 시그널 + 포트폴리오 스냅샷 저장 완료")

    # Telegram 알림 전송
    try:
        from src.notify import notify_signals
        sent = notify_signals(advices)
        if sent:
            print(f"  [알림] Telegram으로 {sent}건 알림 전송 완료")
    except Exception:
        pass

    return advices
