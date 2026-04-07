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
st.caption("한-미-터 주식 투자 전문가 | 포트폴리오 데이터 기반 Gemini AI 상담 (무료)")

import google.generativeai as genai
from src.data.portfolio import load_portfolio
from src.data.market import get_realtime_price, is_us_ticker

# Gemini 설정
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_KEY:
    st.error("Gemini API 키가 설정되지 않았습니다.")
    st.stop()

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")


@st.cache_data(ttl=600)
def get_portfolio_context():
    """포트폴리오 데이터를 AI에 전달할 컨텍스트로 변환 (경량 — Gemini 호출 없음)"""
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

            us = is_us_ticker(h.ticker)
            currency = "USD" if us else "KRW"
            total_eval += eval_amt
            total_cost += cost_amt

            line = (
                f"- {h.name}({h.ticker}): "
                f"매입가 {h.buy_price:,.0f}{currency} × {h.quantity}주, "
                f"현재가 {cur:,.0f}{currency}, "
                f"수익률 {pnl_pct:+.1f}%"
            )
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


SYSTEM_PROMPT = """당신은 "MAUVE 주식 AI 에이전트"의 전문 상담사이며, 20년 이상의 경력을 가진 수석 자산운용가(Fund Manager)이자 전문 트레이더입니다.

## 전문 분야
- 한국, 미국, 터키(튀르키예) 3국 주식 시장 전문가
- 철저한 펀더멘털 분석과 기술적 분석을 결합한 실전 투자 전략가
- 연평균 초고수익률 달성을 목표로 하는 공격적이면서도 치밀한 운용 전략 수립

## 분석 프레임워크
1. **시장 환경 분석**: 3국의 금리, 물가, 환율 현황 및 주식 시장에 미치는 핵심 변수 파악
2. **종목 분석**: 제공된 포트폴리오 데이터(퀀트 점수, 수익률, 재무 지표)를 기반으로 구체적 분석
3. **투자 전략**: 진입 가격(매수가), 목표가(익절가), 손절가 제시 및 비중 조절안 제공
4. **리스크 관리**: 환율 급변, 정책 변화 등 변동성 대응 시나리오 수립

## 답변 규칙
- 반드시 포트폴리오 데이터의 구체적 숫자(수익률, 퀀트 점수, PER, PBR, ROE 등)를 인용하며 답변
- 퀀트 점수: +1.0(강한 매수) ~ -1.0(강한 매도), 0은 중립
- 막연한 낙관론 지양, 반드시 손절 라인을 명시하여 자산 보호
- 데이터와 팩트 중심의 예리한 분석, 불필요한 수식어 배제
- 한국어 중심 (터키 시장 용어는 병기 가능)

## 어조와 스타일
- 자신감 있고 단호한 전문가적 어조 (확신에 찬 전문 트레이더의 말투)
- 실전 위주의 간결한 문체
- 예시: "현재 반도체 사이클과 연동된 SK하이닉스는 ROE 33.8%로 수익성은 탁월하나, PBR 5.25배는 과열 구간입니다. 단기 조정 시 85만원 부근에서 분할 매수 전략이 유효합니다."

## 제약 사항
- 법적 투자 책임은 본인에게 있음을 답변 말미에 간결히 명시
- 분석은 최고 수준으로 제공하되, 최종 판단은 투자자 본인의 몫
"""

# 채팅 기록 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 포트폴리오 데이터 로드
with st.spinner("포트폴리오 데이터 로딩 중..."):
    portfolio_context = get_portfolio_context()

# 사이드바에 포트폴리오 요약 (깔끔하게)
with st.sidebar:
    st.subheader("📊 포트폴리오 요약")
    holdings = load_portfolio()
    kr_cnt = sum(1 for h in holdings if not is_us_ticker(h.ticker))
    us_cnt = sum(1 for h in holdings if is_us_ticker(h.ticker))
    st.markdown(f"**총 {len(holdings)}종목** (KR {kr_cnt} / US {us_cnt})")
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()

# 예시 질문
st.markdown("**예시 질문:**")
examples = [
    "포트폴리오 긴급 리스크 진단해줘",
    "손절 급한 종목 TOP 3 분석",
    "200% 수익 가능한 종목 추천",
    "SK하이닉스 매수/매도 전략",
    "한-미 시장 매크로 분석",
    "포트폴리오 리밸런싱 전략",
]
row1 = st.columns(3)
row2 = st.columns(3)
for col, ex in zip(row1, examples[:3]):
    if col.button(ex, use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": ex})
for col, ex in zip(row2, examples[3:6]):
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
