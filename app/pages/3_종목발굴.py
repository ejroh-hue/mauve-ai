"""종목 발굴 페이지"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import streamlit as st
st.set_page_config(page_title="종목발굴", page_icon="🔎", layout="wide")


import streamlit as _st_auth
try:
    correct_pw = _st_auth.secrets["APP_PASSWORD"]
    if not _st_auth.session_state.get("authenticated", False):
        _st_auth.warning("로그인이 필요합니다. 메인 페이지에서 로그인해주세요.")
        _st_auth.stop()
except (FileNotFoundError, KeyError):
    pass

import pandas as pd

st.title("🔎 종목 발굴")
st.markdown("포트폴리오에 없는 유망 종목/ETF를 스크리닝합니다.")

from src.data.portfolio import load_portfolio, load_settings
from src.analysis.screener import (
    screen_by_quant, screen_by_flow, screen_etf, screen_by_dividend, run_full_screen,
)

holdings = load_portfolio()
settings = load_settings().get("screener", {})


def _show_etf_results(items):
    if not items:
        st.info("조건에 맞는 ETF가 없습니다.")
        return

    rows = []
    for r in items:
        # 괴리율 표시
        td = r.tracking_diff
        td_str = f"{td:+.2f}%" if td is not None else "-"
        # 순자산
        aum = r.aum
        if aum is None:
            aum_str = "-"
        elif aum >= 10000:
            aum_str = f"{aum/10000:.1f}조"
        else:
            aum_str = f"{aum:,.0f}억"
        # 수익률
        ret3 = r.three_month_return
        ret3_str = f"{ret3:+.1f}%" if ret3 is not None else "-"
        ret1 = r.one_month_return
        ret1_str = f"{ret1:+.1f}%" if ret1 is not None else "-"

        rows.append({
            "분류": r.etf_category or "-",
            "ETF명": r.name,
            "종목코드": r.ticker,
            "현재가": f"{r.current_price:,.0f}",
            "NAV": f"{r.nav:,.0f}" if r.nav else "-",
            "괴리율": td_str,
            "1개월수익률": ret1_str,
            "3개월수익률": ret3_str,
            "순자산": aum_str,
            "종합점수": round(r.quant_score, 2),
            "추천 이유": r.reason,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # 괴리율 주의 안내
    high_td = [r for r in items if r.tracking_diff is not None and abs(r.tracking_diff) > 0.5]
    if high_td:
        names = ", ".join(r.name for r in high_td[:3])
        st.warning(f"⚠️ 괴리율 0.5% 초과 ETF: {names} — 현재 NAV 대비 가격이 크게 벗어나 있습니다.")


def _show_results(items, category):
    if not items:
        st.info("조건에 맞는 종목이 없습니다.")
        return

    rows = []
    for r in items:
        row = {
            "종목명": r.name,
            "종목코드": r.ticker,
            "현재가": f"{r.current_price:,.0f}",
        }
        # 퀀트 추천: 재무 컬럼 추가
        if category == "quant":
            row["ROE"] = f"{r.roe:.1f}%" if r.roe else "-"
            row["PBR"] = f"{r.pbr:.2f}배" if r.pbr else "-"
            row["PER"] = f"{r.per:.1f}배" if r.per else "-"
        row["종합점수"] = round(r.quant_score, 2)
        # 수급 추천: 외국인/기관 컬럼
        if r.foreign_net is not None:
            row["외국인(억)"] = f"{r.foreign_net:+.0f}"
        if r.inst_net is not None:
            row["기관(억)"] = f"{r.inst_net:+.0f}"
        row["추천 이유"] = r.reason
        rows.append(row)

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _show_dividend_results(items):
    if not items:
        st.info("조건에 맞는 배당주가 없습니다.")
        return

    rows = []
    for r in items:
        rows.append({
            "종목명": r.name,
            "종목코드": r.ticker,
            "현재가": f"{r.current_price:,.0f}",
            "배당수익률": f"{r.div_yield:.1f}%" if r.div_yield else "-",
            "ROE": f"{r.roe:.1f}%" if r.roe else "-",
            "PBR": f"{r.pbr:.2f}배" if r.pbr else "-",
            "PER": f"{r.per:.1f}배" if r.per else "-",
            "종합점수": round(r.quant_score, 2),
            "선정 이유": r.reason,
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("배당수익률은 최근 배당 기준 추정치입니다. 실제 배당은 결산 후 확정됩니다.")


# 스크리닝 옵션
col1, col2, col3 = st.columns(3)
with col1:
    screen_type = st.selectbox("스크리닝 방식", [
        "전체 스크리닝", "퀀트 점수 Top", "수급 우수 (외국인+기관)", "ETF 추천", "배당주 추천"
    ])
with col2:
    market = st.selectbox("시장", ["KOSPI", "KOSDAQ"])
with col3:
    top_n = st.slider("추천 종목 수", 5, 20, 10)

# 배당주 전용 옵션
min_div = 2.0
if screen_type == "배당주 추천":
    min_div = st.slider("최소 배당수익률 (%)", 1.0, 8.0, 2.0, step=0.5)

if st.button("🔍 스크리닝 실행", type="primary"):
    exclude = {h.ticker for h in holdings}

    with st.spinner("스크리닝 중... (잠시만 기다려주세요)"):
        try:
            if screen_type == "전체 스크리닝":
                results = run_full_screen(holdings, {**settings, "top_n": top_n})

                for category, label in [
                    ("quant", "🏆 퀀트 점수 Top"),
                    ("flow", "💰 외국인+기관 동반 매수"),
                    ("etf", "📈 ETF 추천"),
                ]:
                    items = results.get(category, [])
                    if items:
                        st.subheader(f"{label} ({len(items)}종목)")
                        rows = []
                        for r in items:
                            row = {
                                "종목명": r.name,
                                "종목코드": r.ticker,
                                "현재가": f"{r.current_price:,.0f}",
                                "퀀트": round(r.quant_score, 2),
                                "사유": r.reason,
                            }
                            if r.foreign_net is not None:
                                row["외국인(억)"] = f"{r.foreign_net:+.0f}"
                            if r.inst_net is not None:
                                row["기관(억)"] = f"{r.inst_net:+.0f}"
                            rows.append(row)
                        st.dataframe(
                            pd.DataFrame(rows),
                            use_container_width=True, hide_index=True,
                        )

            elif screen_type == "퀀트 점수 Top":
                items = screen_by_quant(50, top_n, exclude, market)
                _show_results(items, "퀀트")

            elif screen_type == "수급 우수 (외국인+기관)":
                items = screen_by_flow(50, top_n, exclude, market)
                _show_results(items, "수급")

            elif screen_type == "ETF 추천":
                items = screen_etf(top_n, exclude)
                _show_etf_results(items)

            elif screen_type == "배당주 추천":
                items = screen_by_dividend(
                    n_universe=100,
                    top_n=top_n,
                    exclude_tickers=exclude,
                    min_div_yield=min_div,
                    market=market,
                )
                st.subheader(f"💰 배당수익률 {min_div:.1f}% 이상 우량 배당주 ({len(items)}종목)")
                _show_dividend_results(items)

        except Exception as e:
            st.error(f"스크리닝 오류: {e}")
