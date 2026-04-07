"""LLM 감성분석 — Gemini(무료) 또는 Claude API 선택 사용"""

import json
import os
from typing import Optional

from dotenv import load_dotenv

from src.models import LLMSignal, QuantSignal, NewsItem, PortfolioHolding
from src.data.news import get_news, format_news_for_prompt

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def _build_prompt(
    ticker: str,
    name: str,
    quant: QuantSignal,
    news_text: str,
    portfolio_context: str,
    has_holding: bool,
) -> str:
    return f"""당신은 한국 주식 시장 전문 애널리스트입니다.

[종목 정보]
종목명: {name} ({ticker})
현재가: {quant.current_price:,.0f}원

[기술적 분석 결과]
{json.dumps(quant.details, ensure_ascii=False, indent=2)}
퀀트 점수: {quant.score:+.2f} (-1.0~+1.0)
{portfolio_context}
[최근 뉴스]
{news_text}

위 정보를 종합하여 단기(1~2주) 투자 관점의 감성분석을 수행하세요.

분석 시 고려 사항:
1. 뉴스의 긍정/부정 감성과 시장 영향력
2. 기술적 분석 결과와의 일관성
3. 업종 전반의 흐름
{"4. 현재 보유자의 매입가 대비 손익 상황" if has_holding else ""}

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "sentiment": "positive" | "negative" | "neutral",
  "score": -1.0에서 1.0 사이 숫자,
  "reasoning": "판단 근거 (2~3문장)",
  "news_summary": "주요 이슈 요약 (1~2문장)"
}}"""


def _parse_response(text: str) -> LLMSignal:
    json_str = _extract_json(text)
    data = json.loads(json_str)
    return LLMSignal(
        sentiment=data.get("sentiment", "neutral"),
        score=max(-1.0, min(1.0, float(data.get("score", 0)))),
        reasoning=data.get("reasoning", ""),
        news_summary=data.get("news_summary", ""),
    )


def _analyze_with_gemini(prompt: str, news_count: int) -> LLMSignal:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
    print(f"    [LLM] Gemini 감성분석 중... (뉴스 {news_count}건)")
    response = model.generate_content(prompt)
    return _parse_response(response.text.strip())


def _analyze_with_claude(prompt: str, news_count: int) -> LLMSignal:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    print(f"    [LLM] Claude 감성분석 중... (뉴스 {news_count}건)")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_response(response.content[0].text.strip())


def analyze_llm(
    ticker: str,
    name: str,
    quant: QuantSignal,
    news_items: Optional[list[NewsItem]] = None,
    holding: Optional[PortfolioHolding] = None,
) -> LLMSignal:
    """Gemini(우선) 또는 Claude로 뉴스 기반 감성분석을 수행합니다.
    GEMINI_API_KEY가 있으면 Gemini(무료), 없으면 Claude 사용.
    둘 다 없으면 퀀트 분석만 수행.
    """
    if not GEMINI_API_KEY and not ANTHROPIC_API_KEY:
        print("    [LLM] API 키 미설정 — 퀀트 분석만 수행")
        print("    [LLM] Gemini 무료 키: https://aistudio.google.com/apikey")
        return LLMSignal("neutral", 0.0, "API 키 미설정", "N/A")

    if news_items is None:
        news_items = get_news(ticker, name)

    news_text = format_news_for_prompt(news_items)

    portfolio_context = ""
    if holding:
        pnl_pct = ((quant.current_price - holding.buy_price) / holding.buy_price) * 100
        portfolio_context = f"""
[보유 현황]
- 평균 매입가: {holding.buy_price:,.0f}원
- 보유 수량: {holding.quantity}주
- 현재 수익률: {pnl_pct:+.1f}%
- 평가손익: {(quant.current_price * holding.quantity - holding.total_cost):+,.0f}원
"""

    prompt = _build_prompt(ticker, name, quant, news_text, portfolio_context, holding is not None)

    try:
        if GEMINI_API_KEY:
            return _analyze_with_gemini(prompt, len(news_items))
        else:
            return _analyze_with_claude(prompt, len(news_items))

    except Exception as e:
        print(f"    [LLM] 분석 오류: {e}")
        return LLMSignal("neutral", 0.0, f"LLM 오류: {str(e)}", "N/A")


def _extract_json(text: str) -> str:
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return text[start:end]
    return text
