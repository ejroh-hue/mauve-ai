"""AI 주식 상담 페이지 — Gemini 기반 포트폴리오 맞춤 상담"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import streamlit as st
st.set_page_config(page_title="AI 상담", page_icon="💬", layout="wide")

import streamlit as _st_auth
try:
    correct_pw = _st_auth.secrets["APP_PASSWORD"]
    if not _st_auth.session_state.get("authenticated", False):
        _st_auth.warning("로그인이 필요합니다. 메인 페이지에서 로그인해주세요.")
        _st_auth.stop()
except (FileNotFoundError, KeyError):
    pass

st.title("💬 AI 주식 상담")
st.caption("포트폴리오 데이터 기반 Gemini AI 상담 (무료)")

import google.generativeai as genai
from src.data.portfolio import load_portfolio
from src.data.market import get_realtime_price, fetch_ohlcv, is_us_ticker, fetch_us_ohlcv
from src.analysis.quant import analyze_quant

# Gemini 설정
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_KEY:
    st.error("Gemini API 키가 설정되지 않았습니다.")
    st.stop()

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


@st.cache_data(ttl=600)
def get_portfolio_context():
    """포트폴리오 데이터를 AI에 전달할 컨텍스트로 변환"""
    holdings = load_portfolio()
    lines = []
    total_eval = 0
    total_cost = 0

    for h in holdings:
        try:
            cur = get_realtime_price(h.ticker)
            if cur <= 0:
                cur = h.buy_price
            pnl_pct = (cur - h.buy_price) / h.buy_price * 100 if h.buy_price > 0 else 0
            eval_amt = cur * h.quantity
            cost_amt = h.buy_price * h.quantity

            # 퀀트 분석
            try:
                if is_us_ticker(h.ticker):
                    df = fetch_us_ohlcv(h.ticker, days=60)
                else:
                    df = fetch_ohlcv(h.ticker, days=60)
                q = analyze_quant(h.ticker, df)
                quant_score = q.score
                quant_details = " / ".join(f"{k}:{v}" for k, v in q.details.items()
                                           if "중립" not in v and "정상" not in v)
            except Exception:
                quant_score = 0
                quant_details = ""

            us = is_us_ticker(h.ticker)
            currency = "USD" if us else "KRW"
            total_eval += eval_amt
            total_cost += cost_amt

            line = (
                f"- {h.name}({h.ticker}): "
                f"매입가 {h.buy_price:,.0f}{currency} × {h.quantity}주, "
                f"현재가 {cur:,.0f}{currency}, "
                f"수익률 {pnl_pct:+.1f}%, "
                f"퀀트 {quant_score:+.2f}"
            )
            if quant_details:
                line += f" [{quant_details}]"
            lines.append(line)
        except Exception:
            lines.append(f"- {h.name}({h.ticker}): 데이터 조회 실패")

    total_pnl_pct = (total_eval - total_cost) / total_cost * 100 if total_cost > 0 else 0

    header = (
        f"포트폴리오 요약: 총 {len(holdings)}종목, "
        f"총 평가금액 {total_eval:,.0f}원, "
        f"총 매입금액 {total_cost:,.0f}원, "
        f"총 수익률 {total_pnl_pct:+.1f}%\n\n"
        "보유 종목 상세:\n"
    )
    return header + "\n".join(lines)


SYSTEM_PROMPT = """당신은 한국 개인 투자자를 위한 주식 AI 상담사입니다.

역할:
- 사용자의 포트폴리오 데이터를 기반으로 투자 상담
- 퀀트 점수, 수익률, 재무 지표를 활용한 분석
- 매수/매도/보유 판단에 대한 의견 제공
- 한국어로 친절하게 답변

규칙:
- 반드시 포트폴리오 데이터를 참고하여 답변
- 구체적인 숫자(수익률, 퀀트 점수 등)를 포함
- 모든 조언 끝에 "투자 판단의 책임은 본인에게 있습니다" 안내
- 퀀트 점수: +1.0(강한 매수) ~ -1.0(강한 매도), 0은 중립
- 짧고 핵심적으로 답변 (3~5문장)
"""

# 채팅 기록 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 포트폴리오 데이터 로드
with st.spinner("포트폴리오 데이터 로딩 중..."):
    portfolio_context = get_portfolio_context()

# 사이드바에 포트폴리오 요약
with st.sidebar:
    st.subheader("📊 현재 포트폴리오")
    st.text(portfolio_context[:500] + "..." if len(portfolio_context) > 500 else portfolio_context)
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()

# 예시 질문
st.markdown("**예시 질문:**")
example_cols = st.columns(3)
examples = [
    "손절 급한 종목 알려줘",
    "SK하이닉스 지금 팔아야 해?",
    "포트폴리오 전체 평가 해줘",
]
for col, ex in zip(example_cols, examples):
    if col.button(ex, use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": ex})

st.divider()

# 채팅 기록 표시
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 사용자 입력
if prompt := st.chat_input("주식 관련 질문을 입력하세요..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

# AI 응답 생성
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    with st.chat_message("assistant"):
        with st.spinner("AI 분석 중..."):
            try:
                # Gemini에 보낼 전체 프롬프트
                chat_history = "\n".join(
                    f"{'사용자' if m['role'] == 'user' else 'AI'}: {m['content']}"
                    for m in st.session_state.messages[-6:]  # 최근 6개 대화만
                )
                full_prompt = (
                    f"{SYSTEM_PROMPT}\n\n"
                    f"[포트폴리오 데이터]\n{portfolio_context}\n\n"
                    f"[대화 기록]\n{chat_history}\n\n"
                    f"위 데이터를 기반으로 사용자의 마지막 질문에 답변하세요."
                )
                response = model.generate_content(full_prompt)
                answer = response.text
            except Exception as e:
                answer = f"죄송합니다. AI 응답 생성 중 오류가 발생했습니다: {e}"

        st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
