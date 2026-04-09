"""포트폴리오 로더 — Supabase 우선, YAML fallback"""

from pathlib import Path
from typing import Optional

import yaml

from src.models import PortfolioHolding

_PROJECT_ROOT = Path(__file__).parents[2]


def _load_from_cloud() -> list[PortfolioHolding]:
    """Supabase에서 포트폴리오 로드."""
    try:
        from src.storage.cloud_db import get_cloud_portfolio, is_cloud_db_available
        if not is_cloud_db_available():
            return []
        rows = get_cloud_portfolio()
        if not rows:
            return []
        holdings = []
        for item in rows:
            q = item.get("quantity", 0)
            bp = item.get("buy_price", 0)
            if not q or not bp:
                continue
            holdings.append(PortfolioHolding(
                ticker=str(item["ticker"]),
                name=item.get("name", ""),
                quantity=int(q),
                buy_price=float(bp),
                account=item.get("account", "default"),
                asset_type=item.get("asset_type", "stock"),
                currency=item.get("currency", "KRW"),
            ))
        return holdings
    except Exception:
        return []


def _load_from_yaml(config_path=None) -> list[PortfolioHolding]:
    """YAML 파일에서 포트폴리오 로드."""
    if config_path is None:
        config_path = _PROJECT_ROOT / "config" / "portfolio.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    holdings = []
    for item in data.get("holdings", []):
        quantity = item.get("quantity", 0)
        buy_price = item.get("buy_price", 0)
        if not quantity or not buy_price:
            continue
        holdings.append(PortfolioHolding(
            ticker=str(item["ticker"]),
            name=item.get("name", ""),
            quantity=int(quantity),
            buy_price=float(buy_price),
            account=item.get("account", "default"),
            asset_type=item.get("type", "stock"),
            currency=item.get("currency", "KRW"),
            buy_date=item.get("buy_date"),
            notes=item.get("notes"),
        ))
    return holdings


def load_portfolio(config_path: Optional[str] = None) -> list[PortfolioHolding]:
    """포트폴리오 로드 — Supabase 우선, YAML fallback."""
    cloud = _load_from_cloud()
    if cloud:
        return cloud
    return _load_from_yaml(config_path)


def load_settings(config_path: Optional[str] = None) -> dict:
    """settings.yaml에서 설정을 로드합니다."""
    if config_path is None:
        config_path = _PROJECT_ROOT / "config" / "settings.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_portfolio_tickers(holdings: list[PortfolioHolding]) -> list[str]:
    """보유 종목 코드 리스트 반환"""
    return [h.ticker for h in holdings]


def get_holdings_by_account(
    holdings: list[PortfolioHolding], account: str
) -> list[PortfolioHolding]:
    """특정 계좌의 보유 종목만 반환"""
    return [h for h in holdings if h.account == account]


def get_total_cost(holdings: list[PortfolioHolding]) -> float:
    """총 매입금액"""
    return sum(h.total_cost for h in holdings)
