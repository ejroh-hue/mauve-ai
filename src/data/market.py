"""pykrx + 네이버 금융 기반 KRX 시장 데이터 수집 + yfinance 미국 주식"""

from datetime import datetime, timedelta
from functools import lru_cache

import pandas as pd
import requests
from bs4 import BeautifulSoup
from pykrx import stock as pykrx


# ─── 미국 주식 / 환율 ─────────────────────────────────

@lru_cache(maxsize=1)
def get_usd_krw() -> float:
    """USD/KRW 환율 조회 (캐시 1회) — 네이버 우선, yfinance fallback"""
    # 1. 네이버 금융 환율
    try:
        resp = requests.get(
            "https://m.stock.naver.com/front-api/v1/marketIndex/productDetail",
            params={"category": "exchange", "reutersCode": "FX_USDKRW"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            price = data.get("result", {}).get("calcPrice")
            if price and float(price) > 0:
                return float(price)
    except Exception:
        pass
    # 2. yfinance fallback
    try:
        import yfinance as yf
        rate = yf.Ticker("USDKRW=X").fast_info.get("lastPrice")
        if rate and rate > 0:
            return float(rate)
    except Exception:
        pass
    # 3. exchangerate-api fallback (클라우드 환경 대응)
    try:
        resp = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=5,
        )
        if resp.status_code == 200:
            rate = resp.json().get("rates", {}).get("KRW")
            if rate and float(rate) > 0:
                return float(rate)
    except Exception:
        pass
    return 1450.0  # fallback (최근 환율 근사치)


def fetch_us_ohlcv(ticker: str, days: int = 120) -> pd.DataFrame:
    """yfinance로 미국 주식 OHLCV 조회 (USD 기준)"""
    import yfinance as yf
    period = f"{min(days, 365)}d"
    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"미국 주식 {ticker} 데이터를 가져올 수 없습니다.")
    # yfinance MultiIndex 컬럼 처리 (Price, Ticker) → 단일 컬럼으로
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index.name = "날짜"
    return df


@lru_cache(maxsize=256)
def get_us_stock_name(ticker: str) -> str:
    """미국 주식 종목명 조회"""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        return info.get("shortName") or info.get("longName") or ticker
    except Exception:
        return ticker


def is_us_ticker(ticker: str) -> bool:
    """미국 주식 티커 여부 판단 (숫자 6자리가 아니면 미국)"""
    return not (ticker.isdigit() and len(ticker) == 6)


@lru_cache(maxsize=1)
def get_latest_trading_date() -> str:
    """최근 거래일 반환 (비거래일 대응)"""
    for delta in range(7):
        date = (datetime.now() - timedelta(days=delta)).strftime("%Y%m%d")
        try:
            df = pykrx.get_market_ohlcv(date, date, "005930")
            if not df.empty:
                return date
        except Exception:
            continue
    return datetime.now().strftime("%Y%m%d")


def fetch_ohlcv(ticker: str, days: int = 120) -> pd.DataFrame:
    """pykrx에서 주가 OHLCV 데이터를 가져옵니다."""
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    df = pykrx.get_market_ohlcv(start_date, end_date, ticker)

    if df.empty:
        raise ValueError(f"종목 {ticker}의 데이터를 가져올 수 없습니다.")

    # pykrx 1.2.x returns: 시가, 고가, 저가, 종가, 거래량, 등락률
    df = df.rename(columns={
        "시가": "Open", "고가": "High", "저가": "Low",
        "종가": "Close", "거래량": "Volume", "등락률": "Change",
        # pykrx 구버전 호환
        "거래대금": "Value", "시가총액": "MarketCap", "상장주식수": "Shares",
    })
    return df


@lru_cache(maxsize=256)
def get_stock_name(ticker: str) -> str:
    """종목코드 → 종목명 변환 (pykrx 실패 시 네이버 API fallback)"""
    try:
        name = pykrx.get_market_ticker_name(ticker)
        if name and isinstance(name, str) and len(name) > 1:
            return name
    except Exception:
        pass
    # 네이버 실시간 API fallback (ETF 포함 모든 종목 지원)
    try:
        resp = requests.get(
            "https://polling.finance.naver.com/api/realtime",
            params={"query": f"SERVICE_ITEM:{ticker}"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        resp.raise_for_status()
        nm = resp.json()["result"]["areas"][0]["datas"][0].get("nm", "")
        if nm:
            return nm
    except Exception:
        pass
    return ticker


def get_realtime_price(ticker: str) -> float:
    """네이버 실시간 API에서 현재가를 가져옵니다. 실패 시 0 반환.
    한국 주식: polling API, 미국 주식: stock API (USD 기준)
    """
    if is_us_ticker(ticker):
        return _get_us_realtime_price(ticker)
    try:
        resp = requests.get(
            "https://polling.finance.naver.com/api/realtime",
            params={"query": f"SERVICE_ITEM:{ticker}"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()["result"]["areas"][0]["datas"][0]
        price = data.get("nv", 0) or data.get("sv", 0)
        return float(price) if price else 0.0
    except Exception:
        return 0.0


# 미국 주식 네이버 코드: 거래소 suffix 자동 탐색
_US_EXCHANGE_SUFFIXES = [".O", ".N", ".K", ".A", ""]


def _get_us_realtime_price(ticker: str) -> float:
    """네이버 해외주식 API에서 USD 현재가를 가져옵니다."""
    for suffix in _US_EXCHANGE_SUFFIXES:
        naver_code = f"{ticker}{suffix}"
        try:
            resp = requests.get(
                f"https://api.stock.naver.com/stock/{naver_code}/basic",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=3,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            price_str = data.get("closePrice") or data.get("lastPrice")
            if price_str:
                return float(str(price_str).replace(",", ""))
        except Exception:
            continue
    return 0.0


def _fetch_naver_market_cap(sosok: int, pages: int) -> list[str]:
    """네이버 금융에서 시가총액 상위 종목코드를 가져옵니다.
    sosok: 0=KOSPI, 1=KOSDAQ
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    tickers = []
    for page in range(1, pages + 1):
        url = (
            f"https://finance.naver.com/sise/sise_market_sum.naver"
            f"?sosok={sosok}&page={page}"
        )
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            for link in soup.select('a[href*="main.naver?code="]'):
                code = link["href"].split("code=")[1]
                if len(code) == 6 and code.isdigit():
                    tickers.append(code)
        except Exception:
            break
    return list(dict.fromkeys(tickers))


def get_top_market_cap(n: int = 10, market: str = "KOSPI") -> list[str]:
    """시가총액 상위 N개 종목코드 반환 (네이버 금융 기반)"""
    sosok = 0 if market == "KOSPI" else 1
    pages = max(1, (n + 49) // 50)  # 페이지당 50종목
    tickers = _fetch_naver_market_cap(sosok, pages)
    if tickers:
        return tickers[:n]
    return ["005930"]


def get_all_tickers(market: str = "ALL") -> list[str]:
    """전체 종목코드 목록 반환 (네이버 금융 기반)"""
    if market == "ALL":
        kospi = _fetch_naver_market_cap(0, 20)  # ~1000종목
        kosdaq = _fetch_naver_market_cap(1, 20)
        return kospi + kosdaq
    sosok = 0 if market == "KOSPI" else 1
    return _fetch_naver_market_cap(sosok, 20)


def get_investor_trading(ticker: str, days: int = 20) -> pd.DataFrame:
    """외국인/기관 순매수 데이터 조회 (네이버 금융)"""
    headers = {"User-Agent": "Mozilla/5.0"}
    all_rows = []
    pages_needed = max(1, (days + 9) // 10)  # ~10 rows per page

    for page in range(1, pages_needed + 1):
        url = (
            f"https://finance.naver.com/item/frgn.naver"
            f"?code={ticker}&page={page}"
        )
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = "euc-kr"
            soup = BeautifulSoup(resp.text, "html.parser")
            tables = soup.select("table.type2")
            if len(tables) < 2:
                break
            table = tables[1]
            for row in table.select("tr"):
                cols = row.select("td")
                if len(cols) >= 9:
                    date_text = cols[0].text.strip()
                    if not date_text or "." not in date_text:
                        continue
                    inst_text = cols[5].text.strip().replace(",", "")
                    frgn_text = cols[6].text.strip().replace(",", "")
                    try:
                        inst = int(inst_text)
                        frgn = int(frgn_text)
                        all_rows.append({
                            "날짜": date_text,
                            "기관": inst,
                            "외국인": frgn,
                        })
                    except ValueError:
                        continue
        except Exception:
            break

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["날짜"] = pd.to_datetime(df["날짜"], format="%Y.%m.%d")
    df = df.sort_values("날짜").reset_index(drop=True)
    return df.tail(days)


def get_market_cap_data(market: str = "KOSPI") -> pd.DataFrame:
    """시가총액 데이터 (종목 발굴용)"""
    date = get_latest_trading_date()
    try:
        return pykrx.get_market_cap(date, market=market)
    except Exception:
        return pd.DataFrame()


@lru_cache(maxsize=256)
def fetch_fundamentals(ticker: str) -> dict:
    """네이버 실시간 API에서 PER/PBR/배당수익률을 가져옵니다.
    반환: {"per": float, "pbr": float, "div_yield": float, "eps": float, "bps": float}
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(
            "https://polling.finance.naver.com/api/realtime",
            params={"query": f"SERVICE_ITEM:{ticker}"},
            headers=headers,
            timeout=8,
        )
        resp.raise_for_status()
        item = resp.json()["result"]["areas"][0]["datas"][0]

        price = item.get("nv", 0) or item.get("sv", 0)
        eps = item.get("eps", 0) or 0
        bps = item.get("bps", 0) or 0
        div = item.get("dv", 0) or 0

        per = round(price / eps, 2) if eps and eps > 0 else None
        pbr = round(price / bps, 2) if bps and bps > 0 else None
        div_yield = round(div / price * 100, 2) if div and price > 0 else 0.0

        roe = round(eps / bps * 100, 2) if eps and bps and bps > 0 else None

        return {
            "per": per, "pbr": pbr, "div_yield": div_yield,
            "eps": eps, "bps": bps, "roe": roe,
        }
    except Exception:
        return {"per": None, "pbr": None, "div_yield": 0.0, "eps": 0, "bps": 0, "roe": None}


@lru_cache(maxsize=256)
def fetch_income_growth(ticker: str) -> dict:
    """네이버 증권 재무요약 API에서 영업이익 성장률을 가져옵니다.
    반환: {"op_growth_1y": float, "op_latest": int, "revenue_latest": int}
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(
            f"https://m.stock.naver.com/api/stock/{ticker}/finance/summary",
            headers=headers,
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        annual = data.get("chartIncomeStatement", {}).get("annual", {})
        cols = annual.get("columns", [])

        op_row = next((c for c in cols if c and c[0] == "영업이익"), None)
        if not op_row or len(op_row) < 3:
            return {"op_growth_1y": None, "op_latest": None, "revenue_latest": None}

        # 최근 2개 연도 (컨센서스 제외한 실적값)
        titles = cols[0][1:]  # ["2023.12.", "2024.12.", "2025.12.", "2026.12."]
        op_vals = [int(v) if v and v != "0" else None for v in op_row[1:]]

        # 실적만 사용 (컨센서스 제외) — trTitleList로 판단
        tr_titles = annual.get("trTitleList", [])
        actual_indices = [i for i, t in enumerate(tr_titles) if t.get("isConsensus") == "N"]

        actual_ops = [op_vals[i] for i in actual_indices if i < len(op_vals) and op_vals[i]]

        op_growth = None
        if len(actual_ops) >= 2 and actual_ops[-2] and actual_ops[-2] > 0:
            op_growth = round((actual_ops[-1] - actual_ops[-2]) / actual_ops[-2] * 100, 1)

        rev_row = next((c for c in cols if c and c[0] == "매출액"), None)
        rev_latest = None
        if rev_row:
            rev_vals = [int(v) if v and v != "0" else None for v in rev_row[1:]]
            rev_actual = [rev_vals[i] for i in actual_indices if i < len(rev_vals) and rev_vals[i]]
            rev_latest = rev_actual[-1] if rev_actual else None

        return {
            "op_growth_1y": op_growth,
            "op_latest": actual_ops[-1] if actual_ops else None,
            "revenue_latest": rev_latest,
        }
    except Exception:
        return {"op_growth_1y": None, "op_latest": None, "revenue_latest": None}


def get_sector_info(ticker: str) -> str:
    """종목의 업종 정보 반환"""
    return "미분류"


def get_etf_list() -> list[str]:
    """주요 ETF 종목 목록 반환 (거래량 상위 ETF)"""
    # pykrx ETF API가 불안정하여 주요 ETF 직접 관리
    major_etfs = [
        "069500",  # KODEX 200
        "229200",  # KODEX 코스닥150
        "091160",  # KODEX 반도체
        "091170",  # KODEX 은행
        "091180",  # KODEX 자동차
        "117700",  # KODEX 건설
        "117680",  # KODEX 철강
        "102110",  # TIGER 코스피대형주
        "278530",  # KODEX 2차전지산업
        "091230",  # TIGER 반도체
        "305720",  # KODEX 2차전지
        "364970",  # KODEX 2차전지TOP10
        "139260",  # TIGER 200IT
        "261070",  # KODEX 방산
        "140710",  # KODEX 운송
        "266370",  # KODEX AI반도체핵심장비
        "455850",  # TIGER 미국S&P500
        "381170",  # TIGER 미국나스닥100
        "143850",  # TIGER 미국S&P500선물(H)
        "252670",  # KODEX 200선물인버스2X
        "122630",  # KODEX 레버리지
        "114800",  # KODEX 인버스
        "251340",  # KODEX 코스닥150레버리지
        "161510",  # ARIRANG 고배당주
        "211560",  # TIGER 배당성장
        "449170",  # KODEX 배당가치
        "371460",  # TIGER 차이나전기차SOLACTIVE
        "395160",  # TIGER 미국필라델피아반도체나스닥
    ]
    return major_etfs


_ETF_TAB_NAMES = {
    1: "국내주식",
    2: "섹터/테마",
    3: "레버리지/인버스",
    4: "해외주식",
    5: "채권",
    6: "원자재",
    7: "부동산",
    8: "배당",
}


@lru_cache(maxsize=1)
def _fetch_all_etf_info() -> dict:
    """네이버 ETF 전체 리스트 (NAV, 3개월수익률, 순자산, 분류) — 1회 캐시"""
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/etf/"}
    result = {}
    try:
        resp = requests.get(
            "https://finance.naver.com/api/sise/etfItemList.nhn",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("result", {}).get("etfItemList", [])
        for item in items:
            code = item.get("itemcode", "")
            nav = item.get("nav")
            price = item.get("nowVal")
            tracking_diff = (
                round((price - nav) / nav * 100, 2)
                if nav and nav > 0 and price
                else None
            )
            result[code] = {
                "nav": nav,
                "tracking_diff": tracking_diff,
                "three_month_return": item.get("threeMonthEarnRate"),
                "aum": item.get("marketSum"),    # 억원
                "etf_category": _ETF_TAB_NAMES.get(item.get("etfTabCode"), "기타"),
            }
    except Exception:
        pass
    return result


def get_etf_info(ticker: str) -> dict:
    """ETF 종목의 NAV, 괴리율, 3개월수익률, 순자산, 분류 반환"""
    return _fetch_all_etf_info().get(ticker, {})


def get_etf_ohlcv(ticker: str, days: int = 120) -> pd.DataFrame:
    """ETF OHLCV 데이터 조회"""
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    try:
        df = pykrx.get_etf_ohlcv_by_date(start_date, end_date, ticker)
        if not df.empty:
            return df
    except Exception:
        pass

    # ETF가 아닌 경우 일반 OHLCV로 fallback
    return fetch_ohlcv(ticker, days)
