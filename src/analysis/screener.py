"""종목 발굴 — 주식 + ETF 스크리닝"""

from typing import Optional

from src.models import ScreenerResult, PortfolioHolding
from src.data.market import (
    get_top_market_cap, get_stock_name, fetch_ohlcv, get_etf_list,
    get_investor_trading, get_market_cap_data, get_etf_info,
    fetch_fundamentals,
)
from src.analysis.quant import analyze_quant
from src.analysis.investor_flow import analyze_investor_flow


def _quant_composite_score(tech_score: float, fund: dict) -> float:
    """퀀트 종합 점수 = 기술적 신호(40%) + 재무 건전성(60%).

    재무 항목:
    - ROE (25%): 수익성
    - PBR (20%): 저평가 여부
    - PER (15%): 이익 대비 가격
    """
    score = tech_score * 0.4

    # ROE 수익성 (25%)
    roe = fund.get("roe")
    if roe is not None:
        if roe >= 15:
            score += 0.25
        elif roe >= 10:
            score += 0.18
        elif roe >= 5:
            score += 0.1
        elif roe > 0:
            score += 0.03
        else:  # 적자
            score -= 0.15

    # PBR 저평가 (20%)
    pbr = fund.get("pbr")
    if pbr is not None:
        if pbr < 0.5:
            score += 0.2
        elif pbr < 1.0:
            score += 0.15
        elif pbr < 1.5:
            score += 0.08
        elif pbr < 3.0:
            pass
        else:
            score -= 0.1

    # PER 이익 대비 가격 (15%)
    per = fund.get("per")
    if per is not None and per > 0:
        if per < 8:
            score += 0.15
        elif per < 12:
            score += 0.1
        elif per < 20:
            score += 0.05
        elif per > 50:
            score -= 0.1

    return round(score, 3)


def _format_composite_reason(quant_details: dict, fund: dict) -> str:
    """퀀트+재무 종합 추천 이유."""
    parts = []

    # 재무 지표
    roe = fund.get("roe")
    if roe is not None:
        if roe >= 15:
            parts.append(f"ROE {roe:.1f}% (고수익)")
        elif roe >= 5:
            parts.append(f"ROE {roe:.1f}%")

    pbr = fund.get("pbr")
    if pbr is not None:
        if pbr < 1.0:
            parts.append(f"PBR {pbr:.2f}배 (저평가)")
        else:
            parts.append(f"PBR {pbr:.2f}배")

    per = fund.get("per")
    if per is not None and per > 0:
        if per < 10:
            parts.append(f"PER {per:.1f}배 (저평가)")
        else:
            parts.append(f"PER {per:.1f}배")

    # 기술적 신호 (의미 있는 것만)
    tech = {k: v for k, v in quant_details.items()
            if any(kw in v for kw in ["과매도", "골든크로스", "하단 돌파"])}
    if tech:
        parts.append(" / ".join(tech.values()))

    return " | ".join(parts) if parts else "기술적 신호 양호"


def screen_by_quant(
    n_universe: int = 200,
    top_n: int = 10,
    exclude_tickers: set[str] = None,
    market: str = "KOSPI",
) -> list[ScreenerResult]:
    """퀀트+재무 종합 점수 상위 종목 스크리닝"""
    if exclude_tickers is None:
        exclude_tickers = set()

    tickers = get_top_market_cap(n_universe, market)
    results = []

    for ticker in tickers:
        if ticker in exclude_tickers:
            continue
        try:
            df = fetch_ohlcv(ticker, days=120)
            quant = analyze_quant(ticker, df)
            fund = fetch_fundamentals(ticker)

            # 적자 기업 제외
            roe = fund.get("roe")
            if roe is not None and roe < 0:
                continue

            composite = _quant_composite_score(quant.score, fund)
            if composite > 0.1:
                results.append(ScreenerResult(
                    ticker=ticker,
                    name=quant.name,
                    current_price=quant.current_price,
                    quant_score=composite,
                    reason=_format_composite_reason(quant.details, fund),
                    category="quant",
                    per=fund.get("per"),
                    pbr=fund.get("pbr"),
                    roe=roe,
                    div_yield=fund.get("div_yield"),
                ))
        except Exception:
            continue

    results.sort(key=lambda x: x.quant_score, reverse=True)
    return results[:top_n]


def screen_by_flow(
    n_universe: int = 100,
    top_n: int = 10,
    exclude_tickers: set[str] = None,
    market: str = "KOSPI",
) -> list[ScreenerResult]:
    """외국인+기관 동반 순매수 종목 스크리닝"""
    if exclude_tickers is None:
        exclude_tickers = set()

    tickers = get_top_market_cap(n_universe, market)
    results = []

    for ticker in tickers:
        if ticker in exclude_tickers:
            continue
        try:
            flow = analyze_investor_flow(ticker)
            # 외국인+기관 동반 매수만
            if flow.foreign_net_5d > 0 and flow.inst_net_5d > 0:
                name = get_stock_name(ticker)
                df = fetch_ohlcv(ticker, days=60)
                current_price = df["Close"].iloc[-1]
                results.append(ScreenerResult(
                    ticker=ticker,
                    name=name,
                    current_price=current_price,
                    quant_score=flow.score,
                    foreign_net=flow.foreign_net_5d,
                    inst_net=flow.inst_net_5d,
                    reason=flow.summary,
                    category="flow",
                ))
        except Exception:
            continue

    results.sort(
        key=lambda x: (x.foreign_net or 0) + (x.inst_net or 0),
        reverse=True
    )
    return results[:top_n]


def _calc_one_month_return(df) -> float:
    """OHLCV 데이터에서 최근 1개월(20거래일) 수익률 계산."""
    if df is None or len(df) < 20:
        return 0.0
    close_now = df["Close"].iloc[-1]
    close_1m = df["Close"].iloc[-20]
    if close_1m <= 0:
        return 0.0
    return round((close_now - close_1m) / close_1m * 100, 2)


def _etf_composite_score(
    three_month_return: float,
    one_month_return: float,
    tracking_diff: float,
    aum: float,
    quant_score: float,
) -> float:
    """ETF 종합 점수 계산.
    - 3개월 수익률: 중기 추세 (25%)
    - 1개월 수익률: 최근 모멘텀 (15%)
    - 괴리율: NAV 대비 할인 여부 (20%)
    - 순자산 규모: 유동성·안전성 (20%)
    - 퀀트 기술적 신호: 보조 (20%)
    """
    score = 0.0

    # 3개월 수익률 (25%)
    r3 = three_month_return or 0
    if r3 >= 20:
        score += 0.25
    elif r3 >= 5:
        score += 0.15
    elif r3 >= 0:
        score += 0.05
    elif r3 >= -10:
        score -= 0.05
    else:
        score -= 0.2

    # 1개월 수익률 (15%)
    r1 = one_month_return or 0
    if r1 >= 10:
        score += 0.15
    elif r1 >= 3:
        score += 0.1
    elif r1 >= 0:
        score += 0.03
    elif r1 >= -5:
        score -= 0.05
    else:
        score -= 0.15

    # 괴리율 (낮을수록, 특히 음수면 NAV 대비 할인 매수) (20%)
    td = tracking_diff or 0
    if td <= -0.5:
        score += 0.2
    elif td <= 0:
        score += 0.1
    elif td <= 0.5:
        pass
    else:
        score -= 0.2

    # 순자산 규모 (억원) (20%)
    a = aum or 0
    if a >= 10000:    # 1조 이상
        score += 0.2
    elif a >= 3000:   # 3천억 이상
        score += 0.12
    elif a >= 1000:   # 1천억 이상
        score += 0.05
    elif a < 300:     # 300억 미만 — 상장폐지 위험
        score -= 0.3

    # 기술적 신호 (보조) (20%)
    score += quant_score * 0.2

    return round(score, 3)


def _format_etf_reason(
    three_month_return: float,
    one_month_return: float,
    tracking_diff: float,
    aum: float,
    quant_details: dict,
) -> str:
    """ETF 추천 이유를 의미 있는 문장으로 생성."""
    parts = []

    # 수익률 (3개월 + 1개월)
    r3 = three_month_return
    r1 = one_month_return
    if r3 is not None and r1 is not None:
        if r3 >= 10 and r1 >= 3:
            parts.append(f"3개월 {r3:+.1f}% / 1개월 {r1:+.1f}% (상승 지속)")
        elif r3 >= 0 and r1 < -3:
            parts.append(f"3개월 {r3:+.1f}% / 1개월 {r1:+.1f}% (최근 조정)")
        elif r3 < 0 and r1 >= 3:
            parts.append(f"3개월 {r3:+.1f}% / 1개월 {r1:+.1f}% (반등 신호)")
        else:
            parts.append(f"3개월 {r3:+.1f}% / 1개월 {r1:+.1f}%")
    elif r3 is not None:
        parts.append(f"3개월 {r3:+.1f}%")

    # 괴리율
    td = tracking_diff
    if td is not None:
        if td <= -0.5:
            parts.append(f"NAV 대비 {abs(td):.2f}% 할인 매수 기회")
        elif td <= 0:
            parts.append(f"NAV 근접 (괴리율 {td:+.2f}%)")
        else:
            parts.append(f"NAV 대비 {td:+.2f}% 프리미엄 주의")

    # 순자산
    a = aum
    if a is not None:
        if a >= 10000:
            parts.append(f"순자산 {a/10000:.1f}조 (대형)")
        elif a >= 1000:
            parts.append(f"순자산 {a:,.0f}억")
        elif a < 300:
            parts.append(f"순자산 {a:,.0f}억 ⚠️소형")

    # 기술적 신호 (의미 있는 것만)
    tech_signals = {k: v for k, v in quant_details.items()
                    if any(kw in v for kw in ["과매도", "골든크로스", "하단 돌파"])}
    if tech_signals:
        parts.append(" / ".join(tech_signals.values()))

    return " | ".join(parts) if parts else "조건 충족"


def screen_etf(
    top_n: int = 10,
    exclude_tickers: set[str] = None,
) -> list[ScreenerResult]:
    """ETF 스크리닝 — 순자산·괴리율·3개월수익률·기술적신호 종합 평가"""
    if exclude_tickers is None:
        exclude_tickers = set()

    etf_tickers = get_etf_list()
    results = []

    for ticker in etf_tickers:
        if ticker in exclude_tickers:
            continue
        try:
            df = fetch_ohlcv(ticker, days=60)
            if df.empty or len(df) < 20:
                continue

            avg_volume = df["Volume"].tail(20).mean()
            if avg_volume < 50000:  # 거래량 극히 적은 ETF 제외
                continue

            quant = analyze_quant(ticker, df)
            name = get_stock_name(ticker)
            etf = get_etf_info(ticker)

            aum = etf.get("aum")
            if aum is not None and aum < 300:  # 300억 미만 상장폐지 위험
                continue

            three_month_return = etf.get("three_month_return")
            tracking_diff = etf.get("tracking_diff")
            one_month_return = _calc_one_month_return(df)

            composite = _etf_composite_score(
                three_month_return=three_month_return or 0,
                one_month_return=one_month_return,
                tracking_diff=tracking_diff or 0,
                aum=aum or 0,
                quant_score=quant.score,
            )

            results.append(ScreenerResult(
                ticker=ticker,
                name=name,
                current_price=quant.current_price,
                quant_score=composite,  # 표시 점수 = ETF 종합점수
                reason=_format_etf_reason(
                    three_month_return, one_month_return,
                    tracking_diff, aum, quant.details,
                ),
                category="etf",
                nav=etf.get("nav"),
                tracking_diff=tracking_diff,
                one_month_return=one_month_return,
                three_month_return=three_month_return,
                aum=aum,
                etf_category=etf.get("etf_category"),
            ))
        except Exception:
            continue

    results.sort(key=lambda x: x.quant_score, reverse=True)
    return results[:top_n]


def screen_by_dividend(
    n_universe: int = 200,
    top_n: int = 10,
    exclude_tickers: set[str] = None,
    min_div_yield: float = 2.0,
    market: str = "KOSPI",
) -> list[ScreenerResult]:
    """배당주 스크리닝 — 배당수익률 + 수익성 + 안정성 종합 평가

    기준:
    - 배당수익률 min_div_yield% 이상
    - ROE > 0 (적자 기업 제외)
    - PBR < 3 (과도한 고평가 제외)
    정렬: 배당수익률(50%) + ROE 수익성(30%) + 기술적 신호(20%)
    """
    if exclude_tickers is None:
        exclude_tickers = set()

    tickers = get_top_market_cap(n_universe, market)
    results = []

    for ticker in tickers:
        if ticker in exclude_tickers:
            continue
        try:
            fund = fetch_fundamentals(ticker)
            div_yield = fund.get("div_yield") or 0
            per = fund.get("per")
            pbr = fund.get("pbr")
            roe = fund.get("roe")

            # 배당수익률 미달 제외
            if div_yield < min_div_yield:
                continue
            # 적자(ROE 없음) 제외
            if roe is None or roe <= 0:
                continue
            # PBR 과열 제외
            if pbr is not None and pbr > 3.0:
                continue

            df = fetch_ohlcv(ticker, days=60)
            if df.empty or len(df) < 20:
                continue

            quant = analyze_quant(ticker, df)
            name = get_stock_name(ticker)

            # 배당주 종합 점수
            score = 0.0
            # 배당수익률 (50%)
            if div_yield >= 6:
                score += 0.5
            elif div_yield >= 4:
                score += 0.4
            elif div_yield >= 3:
                score += 0.3
            else:
                score += 0.15

            # ROE 수익성 (30%)
            if roe >= 15:
                score += 0.3
            elif roe >= 10:
                score += 0.2
            elif roe >= 5:
                score += 0.1

            # PBR 저평가 여부 (추가 보너스)
            if pbr is not None:
                if pbr < 0.5:
                    score += 0.1
                elif pbr < 1.0:
                    score += 0.05

            # 기술적 신호 (20%)
            score += quant.score * 0.2

            # 이유 생성
            parts = [f"배당수익률 {div_yield:.1f}%"]
            if roe:
                parts.append(f"ROE {roe:.1f}%")
            if pbr:
                if pbr < 1.0:
                    parts.append(f"PBR {pbr:.2f}배 (저평가)")
                else:
                    parts.append(f"PBR {pbr:.2f}배")
            if per:
                parts.append(f"PER {per:.1f}배")
            tech = {k: v for k, v in quant.details.items()
                    if any(kw in v for kw in ["과매도", "골든크로스", "하단 돌파"])}
            if tech:
                parts.append(" / ".join(tech.values()))

            results.append(ScreenerResult(
                ticker=ticker,
                name=name,
                current_price=quant.current_price,
                quant_score=round(score, 3),
                reason=" | ".join(parts),
                category="dividend",
                div_yield=div_yield,
                per=per,
                pbr=pbr,
                roe=roe,
            ))
        except Exception:
            continue

    results.sort(key=lambda x: x.quant_score, reverse=True)
    return results[:top_n]


def screen_portfolio_gaps(
    holdings: list[PortfolioHolding],
    top_n: int = 5,
) -> list[ScreenerResult]:
    """포트폴리오 업종 갭 기반 추천 (간소화 버전)

    pykrx는 업종 분류가 제한적이므로, 시가총액 상위 종목 중
    미보유 종목을 퀀트 점수 기반으로 추천합니다.
    """
    held = {h.ticker for h in holdings}
    return screen_by_quant(
        n_universe=100,
        top_n=top_n,
        exclude_tickers=held,
        market="KOSPI",
    )


def run_full_screen(
    holdings: list[PortfolioHolding] = None,
    settings: dict = None,
) -> dict[str, list[ScreenerResult]]:
    """전체 스크리닝 실행"""
    if settings is None:
        settings = {}

    exclude = set()
    if holdings:
        exclude = {h.ticker for h in holdings}

    n_universe = settings.get("universe_size", 50)
    top_n = settings.get("top_n", 10)

    print("\n종목 발굴 스크리닝 시작...\n")

    print("  [1/3] 퀀트 스크리닝...")
    quant_results = screen_by_quant(n_universe, top_n, exclude)
    print(f"    → {len(quant_results)}개 발굴")

    print("  [2/3] 수급 스크리닝...")
    flow_results = screen_by_flow(n_universe, top_n, exclude)
    print(f"    → {len(flow_results)}개 발굴")

    print("  [3/3] ETF 스크리닝...")
    etf_results = screen_etf(top_n, exclude)
    print(f"    → {len(etf_results)}개 발굴")

    return {
        "quant": quant_results,
        "flow": flow_results,
        "etf": etf_results,
    }


def _format_quant_reason(details: dict) -> str:
    parts = []
    for key, val in details.items():
        if "중립" not in val and "정상" not in val:
            parts.append(val)
    return ", ".join(parts) if parts else "기술적 신호 양호"


def print_screen_report(results: dict[str, list[ScreenerResult]]):
    """스크리닝 결과를 콘솔에 출력합니다."""
    print("\n" + "=" * 70)
    print("  📋 종목 발굴 리포트 (포트폴리오 미보유)")
    print("=" * 70)

    # 퀀트 Top
    quant = results.get("quant", [])
    if quant:
        print(f"\n  🏆 퀀트 점수 Top {len(quant)}")
        print(f"  {'─' * 60}")
        for i, r in enumerate(quant, 1):
            print(
                f"    {i:>2}. {r.name:<14s} ({r.ticker})  "
                f"현재가: {r.current_price:>9,.0f}  "
                f"퀀트: {r.quant_score:+.2f}  "
                f"{r.reason}"
            )

    # 수급 Top
    flow = results.get("flow", [])
    if flow:
        print(f"\n  💰 외국인+기관 동반 매수 Top {len(flow)}")
        print(f"  {'─' * 60}")
        for i, r in enumerate(flow, 1):
            f_net = f"외국인 {r.foreign_net:+.0f}억" if r.foreign_net else ""
            i_net = f"기관 {r.inst_net:+.0f}억" if r.inst_net else ""
            print(
                f"    {i:>2}. {r.name:<14s} ({r.ticker})  "
                f"현재가: {r.current_price:>9,.0f}  "
                f"{f_net}  {i_net}"
            )

    # ETF Top
    etf = results.get("etf", [])
    if etf:
        print(f"\n  📈 ETF 추천 Top {len(etf)}")
        print(f"  {'─' * 60}")
        for i, r in enumerate(etf, 1):
            print(
                f"    {i:>2}. {r.name:<20s} ({r.ticker})  "
                f"현재가: {r.current_price:>9,.0f}  "
                f"퀀트: {r.quant_score:+.2f}"
            )

    print(f"\n{'=' * 70}")
    print("  ⚠️  본 추천은 참고용이며, 투자 판단의 책임은 본인에게 있습니다.")
    print("=" * 70 + "\n")
