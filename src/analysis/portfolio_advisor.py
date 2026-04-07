"""포트폴리오 기반 맞춤 조언"""

from src.models import PortfolioHolding, PortfolioAdvice, FinalSignal
from src.data.market import get_usd_krw, is_us_ticker


def advise(
    holding: PortfolioHolding,
    signal: FinalSignal,
    total_portfolio_value: float,
    settings: dict,
) -> PortfolioAdvice:
    """보유 종목에 대한 포트폴리오 맞춤 조언을 생성합니다."""
    cut_loss = settings.get("cut_loss_threshold", -15.0)
    take_profit = settings.get("take_profit_threshold", 20.0)
    max_position = settings.get("max_position_pct", 15.0)

    current_price = signal.current_price  # 미국 주식은 USD
    buy_price = holding.buy_price
    quantity = holding.quantity

    # 미국 주식은 USD 기준으로 손익 계산, 평가금액은 KRW 환산
    if is_us_ticker(holding.ticker):
        usd_krw = get_usd_krw()
        eval_amount = current_price * quantity * usd_krw
        cost_amount = buy_price * quantity * usd_krw
    else:
        usd_krw = 1.0
        eval_amount = current_price * quantity
        cost_amount = holding.total_cost

    pnl_amount = eval_amount - cost_amount
    pnl_pct = ((current_price - buy_price) / buy_price) * 100 if buy_price > 0 else 0
    weight_pct = (eval_amount / total_portfolio_value * 100) if total_portfolio_value > 0 else 0

    is_buy_signal = signal.combined_score >= 0.3
    is_sell_signal = signal.combined_score <= -0.3
    is_deep_loss = pnl_pct <= cut_loss
    is_profit = pnl_pct >= take_profit
    is_overweight = weight_pct >= max_position

    # ETF는 별도 로직
    if holding.asset_type == "etf":
        action = "벤치마크추적"
        reasoning = f"ETF 종목 — 현재 수익률 {pnl_pct:+.1f}%"
        if pnl_pct < -20:
            reasoning += " / 벤치마크 대비 하락폭 확인 필요"
        elif pnl_pct > 10:
            reasoning += " / 리밸런싱 시점 검토"
    # 손실 > 임계값 + 매도 신호
    elif is_deep_loss and is_sell_signal:
        action = "손절검토"
        reasoning = (
            f"손실 {pnl_pct:.1f}%로 손절 기준({cut_loss}%) 초과, "
            f"매도 신호(점수 {signal.combined_score:+.2f}) 동반"
        )
    # 손실 > 임계값 + 매수/중립 신호
    elif is_deep_loss and not is_sell_signal:
        action = "물타기주의"
        reasoning = (
            f"손실 {pnl_pct:.1f}%로 깊은 손실 구간, "
            f"기술적 반등 신호 있으나 추가 하락 가능성 주의"
        )
    # 수익 > 임계값 + 매도 신호
    elif is_profit and is_sell_signal:
        action = "익절검토"
        reasoning = (
            f"수익 {pnl_pct:.1f}%로 목표({take_profit}%) 도달, "
            f"매도 신호 동반 — 일부 또는 전량 익절 고려"
        )
    # 수익 > 임계값 + 매수 신호
    elif is_profit and is_buy_signal:
        action = "추세유지"
        reasoning = (
            f"수익 {pnl_pct:.1f}%이며 상승 추세 지속 — "
            f"비중 확대 가능하나 과도 집중 주의"
        )
    # 비중 과다
    elif is_overweight:
        action = "비중축소검토"
        reasoning = (
            f"포트폴리오 비중 {weight_pct:.1f}%로 "
            f"최대 비중({max_position}%) 초과 — 리밸런싱 고려"
        )
    # 매수 신호 + 소규모 포지션
    elif is_buy_signal and weight_pct < 5.0:
        action = "추가매수"
        reasoning = (
            f"매수 신호(점수 {signal.combined_score:+.2f}), "
            f"현재 비중 {weight_pct:.1f}%로 소규모 — 추가 매수 여력 있음"
        )
    # 기본
    else:
        action = "보유유지"
        reasoning = f"수익률 {pnl_pct:+.1f}%, 뚜렷한 매매 신호 없음 — 현 포지션 유지"

    return PortfolioAdvice(
        ticker=holding.ticker,
        name=holding.name,
        action=action,
        current_price=current_price,
        buy_price=buy_price,
        quantity=quantity,
        pnl_pct=pnl_pct,
        pnl_amount=pnl_amount,
        eval_amount=eval_amount,
        weight_pct=weight_pct,
        signal=signal,
        reasoning=reasoning,
    )
