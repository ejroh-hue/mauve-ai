"""개별 종목 상세 분석 페이지"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import streamlit as st
st.set_page_config(page_title="종목분석", page_icon="🔍", layout="wide")


# Auth check
try:
    _pw = st.secrets["APP_PASSWORD"]
    if not st.session_state.get("authenticated", False):
        st.warning("메인 페이지에서 로그인해주세요.")
        st.stop()
except (FileNotFoundError, KeyError):
    pass

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import ta

st.title("🔍 종목 상세 분석")

from src.data.portfolio import load_portfolio
from src.data.market import fetch_ohlcv, get_stock_name, is_us_ticker
from src.data.news import get_news
from src.analysis.quant import analyze_quant
from src.analysis.investor_flow import analyze_investor_flow
from src.analysis.strategies import get_combined_strategy_score

# 종목 선택
holdings = load_portfolio()
ticker_options = {f"{h.name} ({h.ticker})": h.ticker for h in holdings}

col1, col2 = st.columns([3, 1])
with col1:
    selected = st.selectbox("보유 종목 선택", list(ticker_options.keys()))
with col2:
    manual = st.text_input("또는 종목코드 직접 입력", placeholder="005930 또는 NVDA")

ticker = manual.strip().upper() if manual else ticker_options.get(selected, "005930")
us_stock = is_us_ticker(ticker)
name = get_stock_name(ticker) if not us_stock else ticker

st.subheader(f"{name} ({ticker})")

if st.button("분석 실행", type="primary"):
    with st.spinner(f"{name} 분석 중..."):
        try:
            # 데이터 수집
            if us_stock:
                from src.data.market import fetch_us_ohlcv, get_us_stock_name
                df = fetch_us_ohlcv(ticker, days=120)
                name = get_us_stock_name(ticker)
            else:
                df = fetch_ohlcv(ticker, days=120)
            quant = analyze_quant(ticker, df)
            flow = analyze_investor_flow(ticker) if not us_stock else None
            news_items = get_news(ticker, name)

            # 차트: 캔들스틱 + 볼린저밴드 + 거래량
            bb = ta.volatility.BollingerBands(df["Close"], window=20, window_dev=2)
            ma5 = df["Close"].rolling(5).mean()
            ma20 = df["Close"].rolling(20).mean()

            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=[0.7, 0.3],
            )

            # 캔들스틱
            fig.add_trace(go.Candlestick(
                x=df.index, open=df["Open"], high=df["High"],
                low=df["Low"], close=df["Close"], name="가격",
            ), row=1, col=1)

            # 볼린저밴드
            fig.add_trace(go.Scatter(
                x=df.index, y=bb.bollinger_hband(), name="BB 상단",
                line=dict(color="rgba(173,216,230,0.5)", dash="dot"),
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=df.index, y=bb.bollinger_lband(), name="BB 하단",
                line=dict(color="rgba(173,216,230,0.5)", dash="dot"),
                fill="tonexty", fillcolor="rgba(173,216,230,0.1)",
            ), row=1, col=1)

            # 이동평균
            fig.add_trace(go.Scatter(
                x=df.index, y=ma5, name="MA5",
                line=dict(color="orange", width=1),
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=df.index, y=ma20, name="MA20",
                line=dict(color="purple", width=1),
            ), row=1, col=1)

            # 거래량
            colors = ["red" if c < o else "green"
                      for c, o in zip(df["Close"], df["Open"])]
            fig.add_trace(go.Bar(
                x=df.index, y=df["Volume"], name="거래량",
                marker_color=colors, opacity=0.5,
            ), row=2, col=1)

            fig.update_layout(
                height=600, xaxis_rangeslider_visible=False,
                title=f"{name} 주가 차트 (120일)",
            )
            st.plotly_chart(fig, use_container_width=True)

            # 지표 카드
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("퀀트 점수", f"{quant.score:+.2f}")
            col2.metric("RSI (14)", f"{quant.rsi:.1f}")
            col3.metric("MACD", quant.details.get("macd", "N/A"))
            if flow:
                col4.metric("수급 점수", f"{flow.score:+.2f}")
            else:
                col4.metric("수급 점수", "N/A (미국주식)")

            # 상세 지표
            st.divider()
            det_col1, det_col2 = st.columns(2)

            with det_col1:
                st.subheader("📊 기술적 지표")
                for key, val in quant.details.items():
                    st.write(f"**{key.upper()}**: {val}")

            with det_col2:
                st.subheader("💰 수급 현황")
                if flow:
                    st.write(f"**외국인 5일**: {flow.foreign_net_5d:+.1f}억원")
                    st.write(f"**외국인 20일**: {flow.foreign_net_20d:+.1f}억원")
                    st.write(f"**기관 5일**: {flow.inst_net_5d:+.1f}억원")
                    st.write(f"**기관 20일**: {flow.inst_net_20d:+.1f}억원")
                    st.write(f"**요약**: {flow.summary}")
                else:
                    st.info("미국 주식은 수급(외국인/기관) 데이터를 제공하지 않습니다.")

            # 전략 점수 (한국 주식만)
            if not us_stock:
                st.divider()
                st.subheader("🏆 전설적 투자자 전략 분석")
                with st.spinner("전략 점수 계산 중..."):
                    strategy_result = get_combined_strategy_score(ticker, df)

                combined = strategy_result["combined"]
                buffett = strategy_result["buffett"]
                lynch = strategy_result["lynch"]
                graham = strategy_result["graham"]
                templeton = strategy_result["templeton"]

                # 종합 점수
                grade_color = "🟢" if combined >= 0.3 else "🔴" if combined <= -0.1 else "🟡"
                st.metric("종합 전략 점수", f"{combined:+.2f}", f"{grade_color} {'매력적' if combined>=0.3 else '주의' if combined<=-0.1 else '보통'}")

                st.markdown("")

                strat_cols = st.columns(4)

                GRADE_ICON = {"매력적": "🟢", "보통": "🟡", "비매력적": "🔴",
                              "성장주 매력": "🟢", "비매력": "🔴",
                              "가치주 매력": "🟢", "역발상 매수": "🟢", "관망": "🟡"}

                def strategy_card(col, title, result):
                    icon = GRADE_ICON.get(result.get("grade", ""), "⚪")
                    col.markdown(f"**{title}**")
                    col.markdown(f"{icon} **{result['grade']}** ({result['score']:+.2f})")
                    for val in result.get("details", {}).values():
                        col.caption(f"• {val}")

                strategy_card(strat_cols[0], "🏦 워런 버핏", buffett)
                strategy_card(strat_cols[1], "📈 피터 린치", lynch)
                strategy_card(strat_cols[2], "📐 벤저민 그레이엄", graham)
                strategy_card(strat_cols[3], "🌏 존 템플턴", templeton)

            # 뉴스
            st.divider()
            st.subheader("📰 최근 뉴스")
            if news_items:
                for item in news_items:
                    st.write(f"- **{item.title}** ({item.source}, {item.date})")
                    if item.summary:
                        st.caption(f"  {item.summary}")
            else:
                st.info("관련 뉴스가 없습니다.")

            # 보유 정보 (포트폴리오에 있는 경우)
            holding = next((h for h in holdings if h.ticker == ticker), None)
            if holding:
                st.divider()
                st.subheader("📋 내 보유 현황")
                pnl_pct = ((quant.current_price - holding.buy_price) / holding.buy_price) * 100
                pnl_amt = (quant.current_price - holding.buy_price) * holding.quantity
                hc1, hc2, hc3, hc4 = st.columns(4)
                if us_stock:
                    hc1.metric("매입가", f"${holding.buy_price:,.2f}")
                    hc2.metric("보유수량", f"{holding.quantity}주")
                    hc3.metric("수익률", f"{pnl_pct:+.1f}%")
                    hc4.metric("평가손익", f"${pnl_amt:+,.2f}")
                else:
                    hc1.metric("매입가", f"{holding.buy_price:,.0f}원")
                    hc2.metric("보유수량", f"{holding.quantity}주")
                    hc3.metric("수익률", f"{pnl_pct:+.1f}%")
                    hc4.metric("평가손익", f"{pnl_amt:+,.0f}원")

        except Exception as e:
            st.error(f"분석 오류: {e}")
