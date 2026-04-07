"""시그널 히스토리 페이지"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import streamlit as st
st.set_page_config(page_title="시그널 히스토리", page_icon="📜", layout="wide")

from app.auth import require_login
require_login()

import pandas as pd
import plotly.express as px

st.title("📜 시그널 히스토리")

from src.storage.db import get_signal_history, get_portfolio_snapshots
from src.data.portfolio import load_portfolio


def _build_buy_price_map() -> dict:
    """포트폴리오에서 현재 매입단가 맵 생성."""
    pf = load_portfolio()
    return {
        h.ticker: h.buy_price
        for h in pf
    }


# 시그널 이력
st.subheader("📊 분석 시그널 이력")

days = st.slider("조회 기간 (일)", 7, 90, 30)
history = get_signal_history(days=days)

if history:
    df = pd.DataFrame(history)

    # 현재 매입단가 기준으로 수익률 재계산
    buy_prices = _build_buy_price_map()
    for idx, row in df.iterrows():
        ticker = row.get("ticker", "")
        price = row.get("current_price")
        bp = buy_prices.get(ticker)
        if bp and bp > 0 and price and price > 0:
            df.at[idx, "pnl_pct"] = round((price - bp) / bp * 100, 2)

    display_cols = [
        "analysis_date", "name", "ticker", "current_price",
        "quant_score", "llm_score", "combined_score",
        "action", "portfolio_action", "pnl_pct"
    ]
    available_cols = [c for c in display_cols if c in df.columns]
    df_display = df[available_cols].copy()

    col_rename = {
        "analysis_date": "분석일시",
        "name": "종목명",
        "ticker": "종목코드",
        "current_price": "분석시 가격",
        "quant_score": "퀀트",
        "llm_score": "LLM",
        "combined_score": "종합",
        "action": "신호",
        "portfolio_action": "조언",
        "pnl_pct": "수익률(%)",
    }
    df_display = df_display.rename(columns=col_rename)

    # 필터
    col1, col2 = st.columns(2)
    with col1:
        action_filter = st.multiselect(
            "신호 필터",
            options=df_display["신호"].unique().tolist(),
            default=df_display["신호"].unique().tolist(),
        )
    with col2:
        advice_filter = st.multiselect(
            "조언 필터",
            options=df_display["조언"].dropna().unique().tolist(),
            default=df_display["조언"].dropna().unique().tolist(),
        )

    filtered = df_display[
        df_display["신호"].isin(action_filter) &
        df_display["조언"].isin(advice_filter)
    ]
    st.dataframe(filtered, use_container_width=True, hide_index=True)

    # 시그널 분포
    st.divider()
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("신호 분포")
        fig = px.pie(df_display, names="신호", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
    with col_r:
        st.subheader("조언 분포")
        fig = px.pie(df_display, names="조언", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("아직 분석 이력이 없습니다. 포트폴리오 분석을 먼저 실행하세요.")

# 포트폴리오 스냅샷
st.divider()
st.subheader("📈 포트폴리오 자산 추이")

snapshots = get_portfolio_snapshots(days=90)
if snapshots:
    snap_df = pd.DataFrame(snapshots)
    # bytes 타입 데이터 float 변환
    for col in ["total_value", "total_cost", "total_pnl", "pnl_pct"]:
        if col in snap_df.columns:
            snap_df[col] = pd.to_numeric(snap_df[col], errors="coerce")

    fig = px.line(
        snap_df, x="snapshot_date", y="total_value",
        title="총 평가금액 추이",
        labels={"snapshot_date": "날짜", "total_value": "평가금액(원)"},
    )
    st.plotly_chart(fig, use_container_width=True)

    fig2 = px.line(
        snap_df, x="snapshot_date", y="pnl_pct",
        title="포트폴리오 수익률 추이",
        labels={"snapshot_date": "날짜", "pnl_pct": "수익률(%)"},
    )
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("포트폴리오 스냅샷이 없습니다. 분석을 실행하면 자동으로 기록됩니다.")
