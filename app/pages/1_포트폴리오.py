"""포트폴리오 현황 페이지"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import streamlit as st
st.set_page_config(page_title="포트폴리오", page_icon="💼", layout="wide")


# --- Auth ---
def _check_auth():
    import streamlit as _st
    try:
        correct_pw = _st.secrets["APP_PASSWORD"]
    except (FileNotFoundError, KeyError):
        return
    if _st.session_state.get("authenticated", False):
        return
    _st.title("🔒 로그인")
    pw = _st.text_input("비밀번호를 입력하세요", type="password")
    if _st.button("로그인"):
        if pw == correct_pw:
            _st.session_state["authenticated"] = True
            _st.rerun()
        else:
            _st.error("비밀번호가 틀렸습니다.")
    _st.stop()
_check_auth()

import pandas as pd
import plotly.express as px
st.title("💼 포트폴리오 현황")


from src.data.market import is_us_ticker, get_usd_krw, get_realtime_price, fetch_ohlcv, fetch_us_ohlcv
from src.data.portfolio import load_portfolio
from src.analysis.quant import analyze_quant
from src.models import PortfolioAdvice, FinalSignal


@st.cache_data(ttl=300)
def run_analysis():
    from src.agent import analyze_portfolio
    return analyze_portfolio()


@st.cache_data(ttl=300)
def run_price_only():
    """가격+퀀트 업데이트 — AI 분석 없이 실시간 가격/손익/퀀트 점수 계산"""
    holdings = load_portfolio()
    usd_krw_rate = get_usd_krw()

    # 총 평가액 계산
    prices = {}
    quant_signals = {}
    for h in holdings:
        p = get_realtime_price(h.ticker)
        if p > 0:
            prices[h.ticker] = p
        else:
            prices[h.ticker] = h.buy_price

        # 퀀트 점수 계산
        try:
            if is_us_ticker(h.ticker):
                df = fetch_us_ohlcv(h.ticker, days=120)
            else:
                df = fetch_ohlcv(h.ticker, days=120)
            quant_signals[h.ticker] = analyze_quant(h.ticker, df)
        except Exception:
            quant_signals[h.ticker] = None

    total_eval = sum(
        prices[h.ticker] * h.quantity * (usd_krw_rate if is_us_ticker(h.ticker) else 1)
        for h in holdings
    )

    advices = []
    for h in holdings:
        cur_price = prices[h.ticker]
        us = is_us_ticker(h.ticker)
        eval_amount = cur_price * h.quantity * (usd_krw_rate if us else 1)
        cost_amount = h.buy_price * h.quantity * (usd_krw_rate if us else 1)
        pnl_amount = eval_amount - cost_amount
        pnl_pct = ((cur_price - h.buy_price) / h.buy_price * 100) if h.buy_price > 0 else 0
        weight_pct = (eval_amount / total_eval * 100) if total_eval > 0 else 0

        q = quant_signals.get(h.ticker)
        q_score = q.score if q else 0

        signal = FinalSignal(
            ticker=h.ticker, name=h.name, action="HOLD",
            combined_score=q_score, quant_score=q_score, llm_score=0,
            current_price=cur_price, analysis_summary="퀀트만 분석 (AI 미포함)",
        )
        advices.append(PortfolioAdvice(
            ticker=h.ticker, name=h.name,
            current_price=cur_price, buy_price=h.buy_price,
            quantity=h.quantity, eval_amount=eval_amount,
            pnl_amount=pnl_amount, pnl_pct=pnl_pct,
            weight_pct=weight_pct, signal=signal,
            action="—", reasoning="퀀트만 분석",
        ))
    return advices


# 분석 모드 선택
col_btn1, col_btn2 = st.columns(2)
btn_price = col_btn1.button("💰 가격 업데이트", help="실시간 가격/손익만 (~5초, 무료)")
btn_full = col_btn2.button("🔄 전체 분석", type="primary", help="가격 + 퀀트 + AI 분석 (~2분, 무료)")

if btn_full:
    st.cache_data.clear()
    st.session_state["analysis_mode"] = "full"
elif btn_price:
    st.session_state["analysis_mode"] = "price"

mode = st.session_state.get("analysis_mode", "price")

if mode == "full":
    with st.spinner("전체 분석 중... (약 2~3분 소요)"):
        try:
            advices = run_analysis()
        except Exception as e:
            st.error(f"분석 오류: {e}")
            st.stop()
    st.caption("모드: 전체 분석 (퀀트 + AI)")
else:
    with st.spinner("가격 + 퀀트 분석 중... (약 30초~1분)"):
        try:
            advices = run_price_only()
        except Exception as e:
            st.error(f"가격 조회 오류: {e}")
            st.stop()
    st.caption("모드: 가격만 업데이트 (전체 분석은 '전체 분석' 버튼 클릭)")

if not advices:
    st.warning("분석 결과가 없습니다. config/portfolio.yaml을 확인하세요.")
    st.stop()
kr_advices = [a for a in advices if not is_us_ticker(a.ticker)]
us_advices = [a for a in advices if is_us_ticker(a.ticker)]
usd_krw = get_usd_krw()

ACTION_COLORS = {
    "손절검토": "🔴", "익절검토": "💰", "추가매수": "🟢",
    "물타기주의": "⚠️", "추세유지": "📈", "보유유지": "🟡",
    "비중축소검토": "🔻", "벤치마크추적": "📊",
}


def make_rows(advices_list, is_us=False, full_mode=True):
    rows = []
    for a in advices_list:
        if is_us:
            price_str = f"${a.current_price:,.2f}"
            buy_str   = f"${a.buy_price:,.2f}"
            pnl_str   = f"${a.pnl_amount/usd_krw:+,.0f}"
        else:
            price_str = f"{a.current_price:,.0f}원"
            buy_str   = f"{a.buy_price:,.0f}원"
            pnl_str   = f"{a.pnl_amount:+,.0f}원"
        row = {
            "종목명": a.name,
            "티커": a.ticker,
            "현재가": price_str,
            "매입가": buy_str,
            "수익률(%)": round(a.pnl_pct, 1),
            "평가손익": pnl_str,
            "비중(%)": round(a.weight_pct, 1),
            "퀀트": round(a.signal.quant_score, 2),
        }
        if full_mode:
            icon = ACTION_COLORS.get(a.action, "●")
            row["LLM"] = round(a.signal.llm_score, 2)
            row["종합"] = round(a.signal.combined_score, 2)
            row["신호"] = a.signal.action
            row["조언"] = f"{icon} {a.action}"
        rows.append(row)
    return pd.DataFrame(rows)


def summary_cards(advices_list, is_us=False):
    """요약 카드 4개"""
    total_eval = sum(a.eval_amount for a in advices_list)
    total_cost = sum(
        (a.buy_price * a.quantity * usd_krw) if is_us else (a.buy_price * a.quantity)
        for a in advices_list
    )
    total_pnl = total_eval - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    if is_us:
        c1.metric("총 평가금액", f"${total_eval/usd_krw:,.0f}  ({total_eval:,.0f}원)")
        c2.metric("총 매입금액", f"${total_cost/usd_krw:,.0f}  ({total_cost:,.0f}원)")
    else:
        c1.metric("총 평가금액", f"{total_eval:,.0f}원")
        c2.metric("총 매입금액", f"{total_cost:,.0f}원")
    c3.metric("총 손익", f"{total_pnl:+,.0f}원", f"{total_pnl_pct:+.2f}%")
    c4.metric("보유 종목", f"{len(advices_list)}개")
    return total_eval


def stock_tabs(df):
    """전체/긴급/수익/손실 탭"""
    sort_col = "종합" if "종합" in df.columns else "퀀트"
    has_advice = "조언" in df.columns
    t1, t2, t3, t4 = st.tabs(["전체 종목", "긴급 조언", "수익 종목", "손실 종목"])
    with t1:
        st.dataframe(df.sort_values(sort_col, ascending=False),
                     use_container_width=True, hide_index=True)
    with t2:
        if has_advice:
            urgent = df[df["조언"].str.contains("손절|익절|물타기|비중축소")]
            if not urgent.empty:
                st.dataframe(urgent, use_container_width=True, hide_index=True)
            else:
                st.success("긴급 조언 대상 종목이 없습니다.")
        else:
            st.info("전체 분석을 실행하면 긴급 조언을 확인할 수 있습니다.")
    with t3:
        st.dataframe(df[df["수익률(%)"] > 0].sort_values("수익률(%)", ascending=False),
                     use_container_width=True, hide_index=True)
    with t4:
        st.dataframe(df[df["수익률(%)"] < 0].sort_values("수익률(%)"),
                     use_container_width=True, hide_index=True)


def charts(advices_list, title_suffix=""):
    cl, cr = st.columns(2)
    with cl:
        st.subheader(f"📊 포트폴리오 비중{title_suffix}")
        pie = pd.DataFrame([{"종목": a.name, "평가금액": a.eval_amount} for a in advices_list])
        fig = px.pie(pie, values="평가금액", names="종목", hole=0.4)
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    with cr:
        st.subheader(f"📈 종목별 수익률{title_suffix}")
        bar = pd.DataFrame([{"종목": a.name, "수익률": a.pnl_pct} for a in advices_list]
                           ).sort_values("수익률")
        fig = px.bar(bar, x="수익률", y="종목", orientation="h",
                     color="수익률",
                     color_continuous_scale=["red", "gray", "green"],
                     color_continuous_midpoint=0)
        fig.update_layout(height=max(400, len(advices_list) * 24))
        st.plotly_chart(fig, use_container_width=True)


# ── 전체 요약 ──────────────────────────────────────────
total_eval_all = sum(a.eval_amount for a in advices)
total_cost_all = sum(
    (a.buy_price * a.quantity * usd_krw) if is_us_ticker(a.ticker) else (a.buy_price * a.quantity)
    for a in advices
)
total_pnl_all = total_eval_all - total_cost_all
total_pnl_pct_all = (total_pnl_all / total_cost_all * 100) if total_cost_all > 0 else 0

st.markdown(f"**전체 포트폴리오** — 총 {len(advices)}개 종목 (🇰🇷 {len(kr_advices)}개 + 🇺🇸 {len(us_advices)}개) &nbsp;|&nbsp; 환율 **{usd_krw:,.0f}원/USD**")

# 실현 손익 조회
from src.storage.db import get_trade_history
trades = get_trade_history(limit=500)
realized_krw = sum(t["pnl_amount"] for t in trades if t.get("currency") != "USD")
realized_usd = sum(t["pnl_amount"] for t in trades if t.get("currency") == "USD")
realized_total = realized_krw + (realized_usd * usd_krw)
total_combined = total_pnl_all + realized_total

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("총 평가금액", f"{total_eval_all:,.0f}원")
c2.metric("총 매입금액", f"{total_cost_all:,.0f}원")
c3.metric("미실현 손익", f"{total_pnl_all:+,.0f}원", f"{total_pnl_pct_all:+.2f}%")
if trades:
    c4.metric("실현 손익", f"{realized_total:+,.0f}원", f"{len(trades)}건 매도")
else:
    c4.metric("실현 손익", "0원", "매도 이력 없음")
c5.metric("총 손익", f"{total_combined:+,.0f}원")

st.divider()

# ── 나라별 탭 ──────────────────────────────────────────
tab_kr, tab_us = st.tabs(["🇰🇷 한국 주식", "🇺🇸 미국 주식"])

with tab_kr:
    if kr_advices:
        summary_cards(kr_advices, is_us=False)
        st.divider()
        stock_tabs(make_rows(kr_advices, is_us=False, full_mode=(mode == "full")))
        st.divider()
        charts(kr_advices, " (한국)")
    else:
        st.info("한국 주식 보유 종목이 없습니다.")

with tab_us:
    if us_advices:
        summary_cards(us_advices, is_us=True)
        st.caption(f"* 평가금액은 현재 환율 {usd_krw:,.0f}원/USD 기준 원화 환산")
        st.divider()
        stock_tabs(make_rows(us_advices, is_us=True, full_mode=(mode == "full")))
        st.divider()
        charts(us_advices, " (미국)")
    else:
        st.info("미국 주식 보유 종목이 없습니다.")
