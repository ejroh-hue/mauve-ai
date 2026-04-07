"""데이터 모델 정의"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QuantSignal:
    """퀀트 분석 결과"""
    ticker: str
    name: str
    current_price: float
    rsi: float
    macd_signal: str          # "bullish" / "bearish" / "neutral"
    bb_position: str          # "below_lower" / "above_upper" / "middle"
    ma_trend: str             # "golden_cross" / "dead_cross" / "neutral"
    volume_spike: bool
    score: float              # -1.0 ~ +1.0
    details: dict = field(default_factory=dict)


@dataclass
class InvestorFlowSignal:
    """외국인/기관 수급 분석 결과"""
    ticker: str
    foreign_net_5d: float     # 외국인 5일 순매수 (억원)
    foreign_net_20d: float    # 외국인 20일 순매수 (억원)
    inst_net_5d: float        # 기관 5일 순매수 (억원)
    inst_net_20d: float       # 기관 20일 순매수 (억원)
    score: float              # -1.0 ~ +1.0
    summary: str


@dataclass
class NewsItem:
    """뉴스 아이템"""
    title: str
    summary: str
    date: str
    source: str


@dataclass
class LLMSignal:
    """LLM 감성분석 결과"""
    sentiment: str            # "positive" / "negative" / "neutral"
    score: float              # -1.0 ~ +1.0
    reasoning: str
    news_summary: str


@dataclass
class FinalSignal:
    """최종 매매 신호"""
    ticker: str
    name: str
    action: str               # "BUY" / "SELL" / "HOLD"
    combined_score: float
    quant_score: float
    llm_score: float
    current_price: float
    analysis_summary: str


@dataclass
class PortfolioHolding:
    """포트폴리오 보유 종목"""
    ticker: str
    name: str
    quantity: int
    buy_price: float          # 평균 매입가
    account: str              # 증권사 계좌 ID
    asset_type: str           # "stock" / "etf" / "us_stock"
    currency: str = "KRW"   # "KRW" / "USD"
    buy_date: Optional[str] = None
    notes: Optional[str] = None

    @property
    def total_cost(self) -> float:
        return self.buy_price * self.quantity


@dataclass
class PortfolioAdvice:
    """포트폴리오 기반 종목별 조언"""
    ticker: str
    name: str
    action: str               # 손절검토 / 익절검토 / 추가매수 / 물타기주의 / 추세유지 / 보유유지 / 벤치마크추적
    current_price: float
    buy_price: float
    quantity: int
    pnl_pct: float            # 수익률 (%)
    pnl_amount: float         # 평가손익 (원)
    eval_amount: float        # 평가금액
    weight_pct: float         # 포트폴리오 내 비중 (%)
    signal: FinalSignal
    reasoning: str


@dataclass
class ScreenerResult:
    """종목 발굴 결과"""
    ticker: str
    name: str
    current_price: float
    quant_score: float
    foreign_net: Optional[float] = None
    inst_net: Optional[float] = None
    sector: Optional[str] = None
    reason: str = ""
    category: str = ""        # "quant" / "flow" / "sector" / "etf" / "theme"
    # ETF 전용 필드
    nav: Optional[float] = None          # 순자산가치 (NAV)
    tracking_diff: Optional[float] = None  # 괴리율 (%) = (가격-NAV)/NAV*100
    one_month_return: Optional[float] = None    # 1개월 수익률 (%)
    three_month_return: Optional[float] = None  # 3개월 수익률 (%)
    aum: Optional[float] = None          # 순자산 규모 (억원)
    etf_category: Optional[str] = None  # ETF 분류 (국내주식/해외/채권 등)
    # 배당주 전용 필드
    div_yield: Optional[float] = None   # 배당수익률 (%)
    per: Optional[float] = None         # PER
    pbr: Optional[float] = None         # PBR
    roe: Optional[float] = None         # ROE (%)
