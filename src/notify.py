"""Telegram 알림 모듈"""

import os
import requests


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def send_telegram(message: str) -> bool:
    """Telegram 봇으로 메시지를 전송합니다."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def notify_signals(advices: list) -> int:
    """매수/매도/손절/익절 신호가 있는 종목을 알림으로 전송합니다.
    반환: 전송된 알림 수
    """
    if not TELEGRAM_BOT_TOKEN:
        return 0

    alert_actions = {"손절검토", "익절검토", "추가매수", "물타기주의", "비중축소검토"}
    alerts = [a for a in advices if a.action in alert_actions]

    if not alerts:
        return 0

    lines = ["<b>📊 KRX 주식 AI 알림</b>\n"]
    for a in alerts:
        icon = {"손절검토": "🔴", "익절검토": "💰", "추가매수": "🟢",
                "물타기주의": "⚠️", "비중축소검토": "🔻"}.get(a.action, "●")
        lines.append(
            f"{icon} <b>{a.name}</b> ({a.ticker})\n"
            f"   조언: {a.action}\n"
            f"   수익률: {a.pnl_pct:+.1f}% | 종합: {a.signal.combined_score:+.2f}\n"
            f"   사유: {a.reasoning}\n"
        )

    lines.append("⚠️ 본 알림은 참고용이며, 투자 판단의 책임은 본인에게 있습니다.")
    message = "\n".join(lines)
    send_telegram(message)
    return len(alerts)


def notify_price_alert(name: str, ticker: str, current_price: float,
                       buy_price: float, pnl_pct: float, alert_type: str):
    """개별 종목 가격 알림"""
    icon = "📈" if pnl_pct > 0 else "📉"
    message = (
        f"{icon} <b>{name}</b> ({ticker})\n"
        f"현재가: {current_price:,.0f}원\n"
        f"매입가: {buy_price:,.0f}원\n"
        f"수익률: {pnl_pct:+.1f}%\n"
        f"알림: {alert_type}"
    )
    send_telegram(message)
