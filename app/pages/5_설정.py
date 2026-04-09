"""설정 페이지 — 포트폴리오 종목 관리 (폼 방식)"""

import sys, os, io
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ["PYTHONIOENCODING"] = "utf-8"

import streamlit as st
st.set_page_config(page_title="설정", page_icon="⚙️", layout="wide")


# Auth check
try:
    _pw = st.secrets["APP_PASSWORD"]
    if not st.session_state.get("authenticated", False):
        st.warning("메인 페이지에서 로그인해주세요.")
        st.stop()
except (FileNotFoundError, KeyError):
    pass

import yaml

st.title("⚙️ 설정")

portfolio_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config", "portfolio.yaml"
)
settings_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config", "settings.yaml"
)


def load_portfolio_yaml():
    with open(portfolio_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_portfolio_yaml(data):
    with open(portfolio_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False)
    st.cache_data.clear()


# ─── 탭 구성 ───────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📋 종목 관리", "⚖️ 분석 설정", "🔑 API 키"])

# ══════════════════════════════════════════
# TAB 1: 종목 관리
# ══════════════════════════════════════════
with tab1:

    try:
        pf = load_portfolio_yaml()
        holdings = pf.get("holdings", [])
    except Exception as e:
        st.error(f"portfolio.yaml 로드 실패: {e}")
        st.stop()

    # ── 현재 보유 종목 테이블 ──
    st.subheader("현재 보유 종목")

    if holdings:
        # 편집 가능한 테이블
        col_headers = st.columns([2, 3, 1.5, 2.5, 2.5, 1, 2, 1])
        col_headers[0].markdown("**종목코드**")
        col_headers[1].markdown("**종목명**")
        col_headers[2].markdown("**수량**")
        col_headers[3].markdown("**매입단가**")
        col_headers[4].markdown("**총 매입금액**")
        col_headers[5].markdown("**통화**")
        col_headers[6].markdown("**계좌**")
        col_headers[7].markdown("**삭제**")

        st.divider()

        updated_holdings = []
        delete_indices = []

        for i, h in enumerate(holdings):
            is_us = h.get("currency") == "USD" or h.get("type") == "us_stock"
            currency_label = "$" if is_us else "₩"
            step = 0.01 if is_us else 100.0

            cols = st.columns([2, 3, 1.5, 2.5, 2.5, 1, 2, 1])
            ticker = cols[0].text_input("코드", h.get("ticker", ""), key=f"ticker_{i}", label_visibility="collapsed")
            name   = cols[1].text_input("이름", h.get("name", ""), key=f"name_{i}", label_visibility="collapsed")
            qty    = cols[2].number_input("수량", value=int(h.get("quantity", 0)), min_value=0, key=f"qty_{i}", label_visibility="collapsed")
            price  = cols[3].number_input("단가", value=float(h.get("buy_price", 0)), min_value=0.0, step=step, key=f"price_{i}", label_visibility="collapsed")
            total_cost = qty * price
            if is_us:
                cols[4].markdown(f"**${total_cost:,.2f}**")
            else:
                cols[4].markdown(f"**{total_cost:,.0f}원**")
            cols[5].markdown(f"**{currency_label}**")
            acct   = cols[6].selectbox("계좌", ["kiwoom", "other"], index=0 if h.get("account") == "kiwoom" else 1, key=f"acct_{i}", label_visibility="collapsed")
            do_del = cols[7].checkbox("✕", key=f"del_{i}", label_visibility="collapsed")

            if do_del:
                delete_indices.append(i)
            else:
                entry = {
                    "ticker": ticker,
                    "name": name,
                    "quantity": qty,
                    "buy_price": price,
                    "account": acct,
                    "type": h.get("type", "stock"),
                }
                if is_us:
                    entry["currency"] = "USD"
                updated_holdings.append(entry)

        st.divider()

        if st.button("💾 변경사항 저장", type="primary"):
            pf["holdings"] = updated_holdings
            save_portfolio_yaml(pf)
            deleted = len(delete_indices)
            st.success(f"저장 완료! (총 {len(updated_holdings)}개 종목" + (f", {deleted}개 삭제됨" if deleted else "") + ")")
            st.rerun()

    # ── 종목 추가 ──
    st.divider()
    st.subheader("➕ 종목 추가")

    with st.form("add_stock_form"):
        cols = st.columns([2, 3, 2, 3, 2, 2])
        new_ticker = cols[0].text_input("종목코드/티커", placeholder="005930 또는 NVDA")
        new_name   = cols[1].text_input("종목명", placeholder="삼성전자 또는 엔비디아")
        new_qty    = cols[2].number_input("수량", min_value=1, value=1)
        new_price  = cols[3].number_input("매입단가", min_value=0.0, step=0.01, value=0.0,
                                           help="한국주식: 원, 미국주식: 달러(USD)")
        new_acct   = cols[4].selectbox("계좌", ["kiwoom", "other"])
        new_market = cols[5].selectbox("시장", ["한국 (KRW)", "미국 (USD)"])

        submitted = st.form_submit_button("추가", type="primary")

        if submitted:
            is_us = new_market == "미국 (USD)"
            if not new_ticker:
                st.error("종목코드를 입력하세요.")
            elif not is_us and (len(new_ticker) != 6 or not new_ticker.isdigit()):
                st.error("한국 종목코드는 6자리 숫자여야 합니다. (예: 005930)")
            elif not new_name:
                st.error("종목명을 입력하세요.")
            elif new_price <= 0:
                st.error("매입단가를 입력하세요.")
            else:
                existing = [h["ticker"] for h in holdings]
                ticker_key = new_ticker.upper() if is_us else new_ticker
                if ticker_key in existing:
                    st.error(f"{ticker_key}는 이미 보유 중입니다. 수량/단가 변경은 위 테이블에서 하세요.")
                else:
                    entry = {
                        "ticker": ticker_key,
                        "name": new_name,
                        "quantity": new_qty,
                        "buy_price": new_price,
                        "account": new_acct,
                        "type": "us_stock" if is_us else "stock",
                    }
                    if is_us:
                        entry["currency"] = "USD"
                    holdings.append(entry)
                    pf["holdings"] = holdings
                    save_portfolio_yaml(pf)
                    unit = "USD" if is_us else "원"
                    st.success(f"✅ {new_name}({ticker_key}) 매입단가 ${new_price:.2f}{unit} 추가 완료!")
                    st.rerun()

    # ── 추가 매수 ──
    st.divider()
    st.subheader("📥 추가 매수")

    if holdings:
        buy_options = [f"{h['name']} ({h['ticker']})" for h in holdings]
        buy_selected = st.selectbox("추가 매수할 종목", buy_options, key="buy_select")
        buy_idx = buy_options.index(buy_selected)
        buy_h = holdings[buy_idx]

        buy_is_us = buy_h.get("currency") == "USD" or buy_h.get("type") == "us_stock"
        buy_sym = "$" if buy_is_us else "원"

        bc1, bc2, bc3 = st.columns(3)
        bp = buy_h["buy_price"]
        bq = buy_h.get("quantity", 0)
        if buy_is_us:
            bc1.metric("현재 매입단가", f"${bp:,.2f}")
            bc3.metric("현재 총 매입금액", f"${bp * bq:,.2f}")
        else:
            bc1.metric("현재 매입단가", f"{bp:,.0f}원")
            bc3.metric("현재 총 매입금액", f"{bp * bq:,.0f}원")
        bc2.metric("현재 보유수량", f"{bq}주")

        with st.form("add_buy_form"):
            abc1, abc2 = st.columns(2)
            add_qty = abc1.number_input("추가 매수 수량", min_value=1, value=1, key="add_buy_qty")
            add_price = abc2.number_input(
                f"추가 매수 단가 ({buy_sym})",
                min_value=0.0,
                value=float(buy_h["buy_price"]),
                step=0.01 if buy_is_us else 100.0,
                key="add_buy_price",
            )

            # 평균 매입단가 미리보기
            old_qty = buy_h.get("quantity", 0)
            old_price = buy_h.get("buy_price", 0)
            new_total_qty = old_qty + add_qty
            new_avg_price = (old_price * old_qty + add_price * add_qty) / new_total_qty if new_total_qty > 0 else 0

            if buy_is_us:
                st.info(f"변경 후: **{new_total_qty}주** × 평균 **${new_avg_price:,.2f}** = 총 **${new_avg_price * new_total_qty:,.2f}**")
            else:
                st.info(f"변경 후: **{new_total_qty}주** × 평균 **{new_avg_price:,.0f}원** = 총 **{new_avg_price * new_total_qty:,.0f}원**")

            add_buy_submitted = st.form_submit_button("추가 매수 확정", type="primary")

            if add_buy_submitted:
                if add_price <= 0:
                    st.error("매수 단가를 입력하세요.")
                else:
                    holdings[buy_idx]["quantity"] = new_total_qty
                    holdings[buy_idx]["buy_price"] = round(new_avg_price, 2)
                    pf["holdings"] = holdings
                    save_portfolio_yaml(pf)

                    if buy_is_us:
                        st.success(f"추가 매수 완료! {buy_h['name']} +{add_qty}주 × ${add_price:,.2f} → 평균 ${new_avg_price:,.2f} × {new_total_qty}주")
                    else:
                        st.success(f"추가 매수 완료! {buy_h['name']} +{add_qty}주 × {add_price:,.0f}원 → 평균 {new_avg_price:,.0f}원 × {new_total_qty}주")
                    st.rerun()

    # ── 매도 처리 ──
    st.divider()
    st.subheader("📤 매도 처리")

    if holdings:
        from src.data.market import get_realtime_price, is_us_ticker
        from src.storage.db import save_trade, get_trade_history

        sell_options = [f"{h['name']} ({h['ticker']})" for h in holdings]
        selected = st.selectbox("매도할 종목", sell_options)
        sel_idx = sell_options.index(selected)
        sel_h = holdings[sel_idx]

        sel_is_us = sel_h.get("currency") == "USD" or sel_h.get("type") == "us_stock"
        cur_symbol = "$" if sel_is_us else "원"

        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("매입단가", f"{cur_symbol}{sel_h['buy_price']:,.2f}" if sel_is_us else f"{sel_h['buy_price']:,.0f}{cur_symbol}")
        sc2.metric("보유수량", f"{sel_h.get('quantity', 0)}주")

        # 실시간 현재가 표시
        rt_price = get_realtime_price(sel_h["ticker"])
        if rt_price > 0:
            pnl_pct = (rt_price - sel_h["buy_price"]) / sel_h["buy_price"] * 100
            sc3.metric("현재가", f"{cur_symbol}{rt_price:,.2f}" if sel_is_us else f"{rt_price:,.0f}{cur_symbol}", f"{pnl_pct:+.2f}%")

        with st.form("sell_form"):
            fc1, fc2 = st.columns(2)
            sell_qty = fc1.number_input("매도 수량", min_value=1, max_value=sel_h.get("quantity", 1), value=sel_h.get("quantity", 1))
            sell_price = fc2.number_input(
                f"매도 단가 ({cur_symbol})",
                min_value=0.0,
                value=float(rt_price) if rt_price > 0 else float(sel_h["buy_price"]),
                step=0.01 if sel_is_us else 100.0,
            )

            sell_date = st.date_input("매도 일자", value=datetime.now().date())

            # 수수료/세금
            fc3, fc4 = st.columns(2)
            sell_fee = fc3.number_input("수수료", min_value=0.0, value=0.0, step=1.0,
                                        help="증권사 수수료")
            sell_tax = fc4.number_input("세금", min_value=0.0, value=0.0, step=1.0,
                                        help="거래세 등")

            # 손익 미리보기 (수수료/세금 차감)
            gross_pnl = (sell_price - sel_h["buy_price"]) * sell_qty
            net_pnl = gross_pnl - sell_fee - sell_tax
            pnl_pct_preview = (sell_price - sel_h["buy_price"]) / sel_h["buy_price"] * 100 if sel_h["buy_price"] > 0 else 0
            if sel_is_us:
                st.info(f"예상 손익: **${net_pnl:+,.2f}** ({pnl_pct_preview:+.2f}%) — 수수료 ${sell_fee:,.2f} / 세금 ${sell_tax:,.2f}")
            else:
                st.info(f"예상 손익: **{net_pnl:+,.0f}원** ({pnl_pct_preview:+.2f}%) — 수수료 {sell_fee:,.0f}원 / 세금 {sell_tax:,.0f}원")

            sell_submitted = st.form_submit_button("매도 확정", type="primary")

            if sell_submitted:
                # 거래 이력 저장 (수수료/세금 차감된 실제 손익)
                save_trade(
                    ticker=sel_h["ticker"],
                    name=sel_h["name"],
                    trade_type="sell",
                    quantity=sell_qty,
                    buy_price=sel_h["buy_price"],
                    sell_price=sell_price,
                    currency="USD" if sel_is_us else "KRW",
                    notes=f"수수료:{sell_fee:.0f}/세금:{sell_tax:.0f}" if (sell_fee or sell_tax) else "",
                    trade_date=datetime.combine(sell_date, datetime.min.time()),
                )

                # 포트폴리오에서 제거 또는 수량 차감
                remaining = sel_h.get("quantity", 0) - sell_qty
                if remaining <= 0:
                    holdings.pop(sel_idx)
                else:
                    holdings[sel_idx]["quantity"] = remaining

                pf["holdings"] = holdings
                save_portfolio_yaml(pf)

                if sel_is_us:
                    st.success(f"매도 완료! {sel_h['name']} {sell_qty}주 × ${sell_price:,.2f} = 실현손익 ${net_pnl:+,.2f}")
                else:
                    st.success(f"매도 완료! {sel_h['name']} {sell_qty}주 × {sell_price:,.0f}원 = 실현손익 {net_pnl:+,.0f}원 (수수료 {sell_fee:,.0f} + 세금 {sell_tax:,.0f})")
                st.rerun()

    # ── 거래 이력 ──
    st.divider()
    st.subheader("📋 매도 이력")

    # 기간 필터
    from src.storage.db import get_trade_history
    fc_period = st.selectbox("조회 기간", ["전체", "오늘", "최근 1주", "최근 1개월", "최근 3개월", "최근 1년"], index=0)
    period_map = {"전체": 9999, "오늘": 1, "최근 1주": 7, "최근 1개월": 30, "최근 3개월": 90, "최근 1년": 365}
    trades = get_trade_history(limit=500)

    # 기간 필터링
    if fc_period != "전체" and trades:
        cutoff = (datetime.now() - timedelta(days=period_map[fc_period])).isoformat()
        trades = [t for t in trades if t.get("trade_date", "") >= cutoff]

    if trades:
        import pandas as pd
        trade_rows = []
        for t in trades:
            is_us = t.get("currency") == "USD"
            sym = "$" if is_us else "원"
            # 날짜 형식 정리
            td = t.get("trade_date", "")
            if "T" in td:
                td = td[:16].replace("T", " ")
            trade_rows.append({
                "매도일": td,
                "종목명": t["name"],
                "종목코드": t["ticker"],
                "수량": t["quantity"],
                "매입단가": f"${t['buy_price']:,.2f}" if is_us else f"{t['buy_price']:,.0f}{sym}",
                "매도단가": f"${t['sell_price']:,.2f}" if is_us else f"{t['sell_price']:,.0f}{sym}",
                "손익": f"${t['pnl_amount']:+,.2f}" if is_us else f"{t['pnl_amount']:+,.0f}{sym}",
                "수익률": f"{t['pnl_pct']:+.2f}%",
                "비고": t.get("notes", ""),
            })
        st.dataframe(pd.DataFrame(trade_rows), use_container_width=True, hide_index=True)

        # 총 실현 손익
        total_krw = sum(t["pnl_amount"] for t in trades if t.get("currency") != "USD")
        total_usd = sum(t["pnl_amount"] for t in trades if t.get("currency") == "USD")
        tc1, tc2 = st.columns(2)
        tc1.metric("총 실현 손익 (KRW)", f"{total_krw:+,.0f}원")
        if total_usd != 0:
            tc2.metric("총 실현 손익 (USD)", f"${total_usd:+,.2f}")
    else:
        st.info("해당 기간의 매도 이력이 없습니다.")


# ══════════════════════════════════════════
# TAB 2: 분석 설정
# ══════════════════════════════════════════
with tab2:
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = yaml.safe_load(f)

        analysis = settings.get("analysis", {})
        portfolio_s = settings.get("portfolio", {})

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**분석 가중치**")
            quant_w = st.slider("퀀트 가중치 (%)", 0, 100,
                                int(analysis.get("quant_weight", 0.6) * 100))
            llm_w = 100 - quant_w
            st.caption(f"LLM 가중치: {llm_w}%")

            buy_th = st.slider("매수 임계값", 0.0, 1.0,
                               analysis.get("buy_threshold", 0.3), 0.05)
            sell_th = st.slider("매도 임계값", -1.0, 0.0,
                                analysis.get("sell_threshold", -0.3), 0.05)

        with col2:
            st.markdown("**포트폴리오 임계값**")
            cut_loss = st.slider("손절 기준 (%)", -50.0, 0.0,
                                 portfolio_s.get("cut_loss_threshold", -15.0), 1.0)
            take_profit = st.slider("익절 기준 (%)", 0.0, 100.0,
                                    portfolio_s.get("take_profit_threshold", 20.0), 1.0)
            max_pos = st.slider("단일종목 최대 비중 (%)", 5.0, 50.0,
                                portfolio_s.get("max_position_pct", 15.0), 1.0)

        if st.button("💾 설정 저장"):
            settings["analysis"]["quant_weight"] = quant_w / 100
            settings["analysis"]["llm_weight"] = llm_w / 100
            settings["analysis"]["buy_threshold"] = buy_th
            settings["analysis"]["sell_threshold"] = sell_th
            settings["portfolio"]["cut_loss_threshold"] = cut_loss
            settings["portfolio"]["take_profit_threshold"] = take_profit
            settings["portfolio"]["max_position_pct"] = max_pos

            with open(settings_path, "w", encoding="utf-8") as f:
                yaml.dump(settings, f, allow_unicode=True, default_flow_style=False)
            st.success("설정이 저장되었습니다.")

    except Exception as e:
        st.error(f"설정 로드 오류: {e}")


# ══════════════════════════════════════════
# TAB 3: API 키
# ══════════════════════════════════════════
with tab3:
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
    )

    current_key = os.environ.get("ANTHROPIC_API_KEY", "")
    dart_key = os.environ.get("DART_API_KEY", "")

    st.markdown("**Claude API 키**")
    if current_key:
        st.success(f"설정됨: {current_key[:12]}...{current_key[-4:]}")
    else:
        st.warning("API 키 미설정 — 퀀트 분석만 가능합니다.")

    st.markdown("**DART API 키**")
    if dart_key:
        st.success(f"설정됨: {dart_key[:8]}...{dart_key[-4:]}")
    else:
        st.warning("DART API 키 미설정 — 공시 데이터 사용 불가")

    st.divider()
    st.markdown("`.env` 파일을 직접 수정하거나 아래에서 입력하세요.")

    with st.form("api_key_form"):
        new_anthropic = st.text_input("Claude API 키", type="password",
                                       placeholder="sk-ant-...")
        new_dart = st.text_input("DART API 키", type="password",
                                  placeholder="opendart 인증키")

        if st.form_submit_button("💾 API 키 저장"):
            lines = []
            if new_anthropic:
                lines.append(f"ANTHROPIC_API_KEY={new_anthropic}")
            elif current_key:
                lines.append(f"ANTHROPIC_API_KEY={current_key}")
            if new_dart:
                lines.append(f"DART_API_KEY={new_dart}")
            elif dart_key:
                lines.append(f"DART_API_KEY={dart_key}")

            with open(env_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            st.success("저장 완료! 앱을 다시 시작하면 반영됩니다.")
