"""SQLite 기반 분석 이력 저장"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models import FinalSignal, PortfolioAdvice

DB_PATH = Path(__file__).parents[2] / "data" / "history.db"

_DB_INITIALIZED = False


def _ensure_dir():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _get_conn():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """테이블 생성 (앱 시작 시 1회만 실행)"""
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                name TEXT,
                analysis_date TEXT NOT NULL,
                current_price REAL,
                quant_score REAL,
                llm_score REAL,
                combined_score REAL,
                action TEXT,
                portfolio_action TEXT,
                pnl_pct REAL,
                analysis_summary TEXT,
                price_after_5d REAL,
                price_after_20d REAL
            );

            CREATE INDEX IF NOT EXISTS idx_signals_ticker_date
            ON signals(ticker, analysis_date);

            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL,
                total_value REAL,
                total_cost REAL,
                total_pnl REAL,
                pnl_pct REAL,
                details TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_date
            ON portfolio_snapshots(snapshot_date);

            CREATE TABLE IF NOT EXISTS news_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                crawl_date TEXT NOT NULL,
                title TEXT,
                summary TEXT,
                source TEXT,
                news_date TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_news_ticker_date
            ON news_cache(ticker, crawl_date);

            CREATE TABLE IF NOT EXISTS trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                name TEXT,
                trade_type TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                quantity INTEGER,
                buy_price REAL,
                sell_price REAL,
                pnl_amount REAL,
                pnl_pct REAL,
                currency TEXT DEFAULT 'KRW',
                notes TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_trade_ticker_date
            ON trade_history(ticker, trade_date);
        """)
    _DB_INITIALIZED = True


def save_signal(advice: PortfolioAdvice):
    """분석 시그널을 저장합니다."""
    init_db()
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO signals
            (ticker, name, analysis_date, current_price, quant_score, llm_score,
             combined_score, action, portfolio_action, pnl_pct, analysis_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                advice.ticker,
                advice.name,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                float(advice.current_price) if advice.current_price is not None else None,
                advice.signal.quant_score,
                advice.signal.llm_score,
                advice.signal.combined_score,
                advice.signal.action,
                advice.action,
                advice.pnl_pct,
                advice.signal.analysis_summary,
            )
        )


def save_portfolio_snapshot(advices: list[PortfolioAdvice]):
    """포트폴리오 일별 스냅샷을 저장합니다."""
    if not advices:
        return

    init_db()
    total_value = sum(a.eval_amount for a in advices)
    total_cost = sum(a.buy_price * a.quantity for a in advices)
    total_pnl = total_value - total_cost
    pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    details = [
        {
            "ticker": a.ticker,
            "name": a.name,
            "eval": int(a.eval_amount),
            "pnl_pct": round(float(a.pnl_pct), 2),
            "action": a.action,
        }
        for a in advices
    ]

    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO portfolio_snapshots
            (snapshot_date, total_value, total_cost, total_pnl, pnl_pct, details)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().strftime("%Y-%m-%d"),
                total_value, total_cost, total_pnl, pnl_pct,
                json.dumps(details, ensure_ascii=False),
            )
        )


def get_signal_history(ticker: str = None, days: int = 30) -> list[dict]:
    """과거 시그널 이력을 조회합니다."""
    init_db()
    with _get_conn() as conn:
        if ticker:
            rows = conn.execute(
                """SELECT * FROM signals
                WHERE ticker = ?
                ORDER BY analysis_date DESC LIMIT ?""",
                (ticker, days)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM signals
                ORDER BY analysis_date DESC LIMIT ?""",
                (days * 33,)  # 최대 33종목 x days
            ).fetchall()

    result = []
    for r in rows:
        row = dict(r)
        # numpy int64가 bytes로 저장된 경우 float으로 변환
        if isinstance(row.get("current_price"), bytes):
            import struct
            try:
                row["current_price"] = float(struct.unpack("<q", row["current_price"])[0])
            except Exception:
                row["current_price"] = None
        result.append(row)
    return result


def get_portfolio_snapshots(days: int = 90) -> list[dict]:
    """포트폴리오 스냅샷 이력을 조회합니다."""
    init_db()
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM portfolio_snapshots
            ORDER BY snapshot_date DESC LIMIT ?""",
            (days,)
        ).fetchall()
    return [dict(r) for r in rows]


def save_trade(
    ticker: str, name: str, trade_type: str,
    quantity: int, buy_price: float, sell_price: float,
    currency: str = "KRW", notes: str = "",
):
    """매도/매수 거래 이력을 저장합니다."""
    init_db()
    pnl_amount = (sell_price - buy_price) * quantity
    pnl_pct = ((sell_price - buy_price) / buy_price * 100) if buy_price > 0 else 0

    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO trade_history
            (ticker, name, trade_type, trade_date, quantity,
             buy_price, sell_price, pnl_amount, pnl_pct, currency, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticker, name, trade_type,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                quantity, buy_price, sell_price,
                round(pnl_amount, 2), round(pnl_pct, 2),
                currency, notes,
            )
        )


def get_trade_history(limit: int = 100) -> list[dict]:
    """거래 이력을 조회합니다."""
    init_db()
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM trade_history
            ORDER BY trade_date DESC LIMIT ?""",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
