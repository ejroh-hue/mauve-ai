"""Supabase 클라우드 DB — 매도이력/시그널/스냅샷 영구 저장"""

import os
from datetime import datetime
from typing import Optional

try:
    from supabase import create_client
except ImportError:
    create_client = None

# Streamlit secrets 또는 환경변수에서 읽기
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not SUPABASE_URL or not SUPABASE_KEY or create_client is None:
        return None
    _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def is_cloud_db_available() -> bool:
    return _get_client() is not None


# ── 매도 이력 ──────────────────────────────────────

def save_trade(
    ticker: str, name: str, trade_type: str,
    quantity: int, buy_price: float, sell_price: float,
    currency: str = "KRW", notes: str = "",
):
    client = _get_client()
    if not client:
        return
    gross_pnl = (sell_price - buy_price) * quantity
    # notes에서 수수료/세금 파싱: "수수료:430/세금:3742"
    fee = 0.0
    tax = 0.0
    if notes:
        for part in notes.split("/"):
            if "수수료:" in part:
                try: fee = float(part.split(":")[1])
                except: pass
            elif "세금:" in part:
                try: tax = float(part.split(":")[1])
                except: pass
    pnl_amount = gross_pnl - fee - tax
    pnl_pct = (pnl_amount / (buy_price * quantity) * 100) if buy_price > 0 else 0

    client.table("trade_history").insert({
        "ticker": ticker,
        "name": name,
        "trade_type": trade_type,
        "trade_date": datetime.now().isoformat(),
        "quantity": quantity,
        "buy_price": round(buy_price, 2),
        "sell_price": round(sell_price, 2),
        "pnl_amount": round(pnl_amount, 2),
        "pnl_pct": round(pnl_pct, 2),
        "currency": currency,
        "notes": notes,
    }).execute()


def get_trade_history(limit: int = 100) -> list[dict]:
    client = _get_client()
    if not client:
        return []
    resp = client.table("trade_history") \
        .select("*") \
        .order("trade_date", desc=True) \
        .limit(limit) \
        .execute()
    return resp.data if resp.data else []


# ── 시그널 이력 ──────────────────────────────────────

def save_signal(advice):
    client = _get_client()
    if not client:
        return
    client.table("signals").insert({
        "ticker": advice.ticker,
        "name": advice.name,
        "analysis_date": datetime.now().isoformat(),
        "current_price": float(advice.current_price) if advice.current_price is not None else None,
        "quant_score": advice.signal.quant_score,
        "llm_score": advice.signal.llm_score,
        "combined_score": advice.signal.combined_score,
        "action": advice.signal.action,
        "portfolio_action": advice.action,
        "pnl_pct": round(float(advice.pnl_pct), 2),
        "analysis_summary": advice.signal.analysis_summary,
    }).execute()


def get_signal_history(ticker: str = None, days: int = 30) -> list[dict]:
    client = _get_client()
    if not client:
        return []
    query = client.table("signals").select("*").order("analysis_date", desc=True)
    if ticker:
        query = query.eq("ticker", ticker).limit(days)
    else:
        query = query.limit(days * 33)
    resp = query.execute()
    return resp.data if resp.data else []


# ── 포트폴리오 스냅샷 ────────────────────────────────

def save_portfolio_snapshot(advices: list):
    import json
    client = _get_client()
    if not client or not advices:
        return
    total_value = sum(a.eval_amount for a in advices)
    total_cost = sum(a.buy_price * a.quantity for a in advices)
    total_pnl = total_value - total_cost
    pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    details = [
        {
            "ticker": a.ticker, "name": a.name,
            "eval": int(a.eval_amount),
            "pnl_pct": round(float(a.pnl_pct), 2),
            "action": a.action,
        }
        for a in advices
    ]
    client.table("portfolio_snapshots").insert({
        "snapshot_date": datetime.now().strftime("%Y-%m-%d"),
        "total_value": total_value,
        "total_cost": total_cost,
        "total_pnl": total_pnl,
        "pnl_pct": round(pnl_pct, 2),
        "details": json.dumps(details, ensure_ascii=False),
    }).execute()


def get_portfolio_snapshots(days: int = 90) -> list[dict]:
    client = _get_client()
    if not client:
        return []
    resp = client.table("portfolio_snapshots") \
        .select("*") \
        .order("snapshot_date", desc=True) \
        .limit(days) \
        .execute()
    return resp.data if resp.data else []
