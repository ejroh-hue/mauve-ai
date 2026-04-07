"""기술적 지표 기반 퀀트 분석"""

import pandas as pd
import ta

from src.models import QuantSignal
from src.data.market import get_stock_name, fetch_fundamentals, get_realtime_price, is_us_ticker
from src.analysis.buffett import analyze_buffett
from src.analysis.strategies import analyze_lynch, analyze_graham, analyze_templeton


def analyze_quant(ticker: str, df: pd.DataFrame) -> QuantSignal:
    """기술적 지표 기반 퀀트 점수를 계산합니다."""
    name = get_stock_name(ticker)
    close = df["Close"]
    volume = df["Volume"]
    # 네이버 실시간 가격 사용 (한국+미국 모두), 실패 시 종가 fallback
    realtime = get_realtime_price(ticker)
    current_price = realtime if realtime > 0 else float(close.iloc[-1])

    score = 0.0
    details = {}

    # RSI (14일)
    rsi_val = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
    if rsi_val < 30:
        score += 0.3
        details["rsi"] = f"과매도({rsi_val:.1f})"
    elif rsi_val > 70:
        score -= 0.3
        details["rsi"] = f"과매수({rsi_val:.1f})"
    else:
        details["rsi"] = f"중립({rsi_val:.1f})"

    # MACD
    macd_obj = ta.trend.MACD(close)
    macd_line = macd_obj.macd().iloc[-1]
    signal_line = macd_obj.macd_signal().iloc[-1]
    macd_prev = macd_obj.macd().iloc[-2]
    signal_prev = macd_obj.macd_signal().iloc[-2]

    if macd_prev < signal_prev and macd_line > signal_line:
        macd_signal = "bullish"
        score += 0.25
        details["macd"] = "골든크로스 발생"
    elif macd_prev > signal_prev and macd_line < signal_line:
        macd_signal = "bearish"
        score -= 0.25
        details["macd"] = "데드크로스 발생"
    else:
        macd_signal = "neutral"
        details["macd"] = "중립"

    # 볼린저밴드
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]

    if current_price < bb_lower:
        bb_position = "below_lower"
        score += 0.2
        details["bb"] = "하단 돌파 (반등 기대)"
    elif current_price > bb_upper:
        bb_position = "above_upper"
        score -= 0.2
        details["bb"] = "상단 돌파 (과열)"
    else:
        bb_position = "middle"
        details["bb"] = "밴드 내 정상"

    # 이동평균 (5일 vs 20일)
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()

    if ma5.iloc[-2] < ma20.iloc[-2] and ma5.iloc[-1] > ma20.iloc[-1]:
        ma_trend = "golden_cross"
        score += 0.25
        details["ma"] = "5/20 골든크로스"
    elif ma5.iloc[-2] > ma20.iloc[-2] and ma5.iloc[-1] < ma20.iloc[-1]:
        ma_trend = "dead_cross"
        score -= 0.25
        details["ma"] = "5/20 데드크로스"
    else:
        ma_trend = "neutral"
        trend_dir = "상승" if ma5.iloc[-1] > ma20.iloc[-1] else "하락"
        details["ma"] = f"추세 {trend_dir}"

    # 거래량 이상 감지
    vol_avg_20 = volume.rolling(20).mean().iloc[-1]
    vol_today = volume.iloc[-1]
    volume_spike = vol_today > vol_avg_20 * 2.0

    if volume_spike:
        spike_boost = 0.1 if score > 0 else -0.1
        score += spike_boost
        details["volume"] = f"거래량 급증 ({vol_today/vol_avg_20:.1f}배)"
    else:
        details["volume"] = "정상 거래량"

    # 펀더멘털 지표 (PER / PBR) — ETF는 스킵
    fund = fetch_fundamentals(ticker)
    per = fund["per"]
    pbr = fund["pbr"]
    fund_score = 0.0
    is_etf = (per is None and pbr is None and fund["eps"] == 0 and fund["bps"] == 0)

    if is_etf:
        pass  # ETF는 PER/PBR 없음 — details에 추가하지 않음
    elif per is not None:
        if per < 10:
            fund_score += 0.2
            details["per"] = f"저평가({per:.1f}배)"
        elif per < 15:
            fund_score += 0.1
            details["per"] = f"적정저({per:.1f}배)"
        elif per < 25:
            details["per"] = f"적정({per:.1f}배)"
        elif per < 40:
            fund_score -= 0.1
            details["per"] = f"고평가({per:.1f}배)"
        else:
            fund_score -= 0.2
            details["per"] = f"과열({per:.1f}배)"
    elif not is_etf:
        details["per"] = "적자/데이터 없음"

    if pbr is not None and not is_etf:
        if pbr < 0.5:
            fund_score += 0.15
            details["pbr"] = f"초저평가({pbr:.2f}배)"
        elif pbr < 1.0:
            fund_score += 0.1
            details["pbr"] = f"저평가({pbr:.2f}배)"
        elif pbr < 2.0:
            details["pbr"] = f"적정({pbr:.2f}배)"
        elif pbr < 4.0:
            fund_score -= 0.05
            details["pbr"] = f"고평가({pbr:.2f}배)"
        else:
            fund_score -= 0.1
            details["pbr"] = f"과열({pbr:.2f}배)"
    elif not is_etf:
        details["pbr"] = "데이터 없음"

    if fund["div_yield"] > 0 and not is_etf:
        details["div"] = f"배당수익률 {fund['div_yield']:.1f}%"

    # 펀더멘털 가중치: 기술적 지표의 25% 수준
    fund_score = max(-0.25, min(0.25, fund_score))
    score += fund_score

    # 전설적 투자자 전략 종합 점수 (ETF 제외, 가중치 15%)
    if not is_etf:
        try:
            buffett = analyze_buffett(ticker)
            lynch = analyze_lynch(ticker)
            graham = analyze_graham(ticker)
            templeton = analyze_templeton(ticker, df)

            # 버핏30% + 린치30% + 그레이엄25% + 템플턴15%
            strategy_score = (
                buffett["score"] * 0.30 +
                lynch["score"] * 0.30 +
                graham["score"] * 0.25 +
                templeton["score"] * 0.15
            )
            score += strategy_score * 0.15  # 전체 점수의 15% 반영

            # 가장 강한 신호 details에 표시
            best = max(
                [("버핏", buffett), ("린치", lynch), ("그레이엄", graham), ("템플턴", templeton)],
                key=lambda x: x[1]["score"]
            )
            worst = min(
                [("버핏", buffett), ("린치", lynch), ("그레이엄", graham), ("템플턴", templeton)],
                key=lambda x: x[1]["score"]
            )
            details["strategy"] = (
                f"전략종합({strategy_score:+.2f}) "
                f"▲{best[0]}:{best[1]['grade']} "
                f"▽{worst[0]}:{worst[1]['grade']}"
            )
            if "roe" in buffett["details"]:
                details["roe"] = buffett["details"]["roe"]
            if "op_growth" in lynch["details"]:
                details["op_growth"] = lynch["details"]["growth"]
        except Exception:
            pass

    score = max(-1.0, min(1.0, score))

    return QuantSignal(
        ticker=ticker,
        name=name,
        current_price=current_price,
        rsi=rsi_val,
        macd_signal=macd_signal,
        bb_position=bb_position,
        ma_trend=ma_trend,
        volume_spike=volume_spike,
        score=score,
        details=details,
    )
