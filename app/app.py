"""MAUVE 주식 AI 에이전트 — Streamlit 대시보드"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# Streamlit Cloud: expose secrets as environment variables for existing code
import streamlit as st

try:
    for key in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "SUPABASE_URL", "SUPABASE_KEY",
                "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        if key not in os.environ and key in st.secrets:
            os.environ[key] = st.secrets[key]
except FileNotFoundError:
    pass  # no secrets file (local dev with .env)

st.set_page_config(
    page_title="MAUVE 주식 AI 에이전트",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Password Protection ---
def check_password() -> bool:
    """Return True if the user entered the correct password."""
    # 환경변수 우선, st.secrets fallback (Render/Streamlit Cloud 모두 지원)
    correct_pw = os.environ.get("APP_PASSWORD", "")
    if not correct_pw:
        try:
            correct_pw = st.secrets["APP_PASSWORD"]
        except (FileNotFoundError, KeyError):
            return True  # 로컬 개발 환경 — 비밀번호 없으면 통과

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return True

    st.title("🔒 로그인")
    password = st.text_input("비밀번호를 입력하세요", type="password")
    if st.button("로그인"):
        if password == correct_pw:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False


if not check_password():
    st.stop()

st.title("📈 MAUVE 주식 AI 에이전트")
st.markdown("퀀트 분석 + 뉴스 감성분석 + 수급 분석 기반 포트폴리오 관리")

# 사이드바
with st.sidebar:
    st.header("📊 빠른 요약")

    try:
        from src.data.portfolio import load_portfolio, load_settings

        holdings = load_portfolio()
        settings = load_settings()

        if holdings:
            kr_holdings = [h for h in holdings if h.asset_type != "us_stock"]
            us_holdings = [h for h in holdings if h.asset_type == "us_stock"]
            kr_cost = sum(h.buy_price * h.quantity for h in kr_holdings)
            us_cost = sum(h.buy_price * h.quantity for h in us_holdings)

            st.metric("보유 종목", f"총 {len(holdings)}개 (🇰🇷{len(kr_holdings)} / 🇺🇸{len(us_holdings)})")
            st.metric("한국 매입금액", f"{kr_cost:,.0f}원")
            if us_holdings:
                st.metric("미국 매입금액", f"${us_cost:,.2f}")
            st.divider()

        # API 키 상태
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        claude_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if gemini_key:
            st.success("Gemini AI: 연결됨 (무료)")
        elif claude_key:
            st.success("Claude API: 연결됨")
        else:
            st.warning("AI API: 미설정 (퀀트 분석만 가능)")

    except Exception as e:
        st.error(f"설정 로드 오류: {e}")

    st.divider()
    st.caption("⚠️ 본 분석은 참고용이며, 투자 판단의 책임은 본인에게 있습니다.")

# 메인 페이지 안내
st.markdown("""
### 사용법

왼쪽 사이드바에서 페이지를 선택하세요:

| 페이지 | 설명 |
|--------|------|
| **1_포트폴리오** | 전체 보유 종목 현황 + AI 조언 |
| **2_종목분석** | 개별 종목 상세 분석 (차트 + 뉴스 + 수급) |
| **3_종목발굴** | 미보유 유망 종목/ETF 추천 |
| **4_시그널히스토리** | 과거 분석 이력 + 적중률 |
| **5_설정** | 포트폴리오 편집 + 가중치 조정 |
""")
