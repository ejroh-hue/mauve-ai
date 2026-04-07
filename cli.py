"""KRX 주식 AI 에이전트 — CLI 진입점"""

import argparse
import sys
import io
import os
from datetime import datetime

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, os.path.dirname(__file__))

# Windows에서 한글 출력 인코딩 오류 방지 (CLI 전용)
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

from src.agent import analyze_portfolio, analyze_single
from src.data.portfolio import load_portfolio, load_settings
from src.analysis.screener import run_full_screen, print_screen_report
from src.models import PortfolioAdvice


# 조언별 이모지/컬러 매핑
ACTION_ICONS = {
    "손절검토": "🔴",
    "익절검토": "💰",
    "추가매수": "🟢",
    "물타기주의": "⚠️",
    "추세유지": "📈",
    "보유유지": "🟡",
    "비중축소검토": "🔻",
    "벤치마크추적": "📊",
}


def print_portfolio_report(advices: list[PortfolioAdvice]):
    """포트폴리오 분석 결과를 콘솔에 출력합니다."""
    if not advices:
        print("\n분석 결과가 없습니다.")
        return

    total_eval = sum(a.eval_amount for a in advices)
    total_cost = sum(a.buy_price * a.quantity for a in advices)
    total_pnl = total_eval - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    settings = load_settings()
    q_weight = settings.get("analysis", {}).get("quant_weight", 0.6)
    l_weight = settings.get("analysis", {}).get("llm_weight", 0.4)

    print("\n" + "=" * 70)
    print("  📈 KRX 주식 AI 에이전트 — 포트폴리오 리포트")
    print(f"  📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  ⚖️  가중치: 퀀트 {q_weight*100:.0f}% / LLM {l_weight*100:.0f}%")
    print("=" * 70)

    # 포트폴리오 요약
    print(f"\n  💰 총 평가금액: {total_eval:>14,.0f}원")
    print(f"  💵 총 매입금액: {total_cost:>14,.0f}원")
    pnl_sign = "+" if total_pnl >= 0 else ""
    print(f"  📊 총 손익:     {pnl_sign}{total_pnl:>13,.0f}원 ({pnl_sign}{total_pnl_pct:.2f}%)")

    # 계좌별 분리
    accounts = {}
    for a in advices:
        acc = a.signal.ticker  # placeholder; use holding's account
        accounts.setdefault("all", []).append(a)

    # 조언별 그룹핑
    action_groups = {}
    for a in advices:
        action_groups.setdefault(a.action, []).append(a)

    # 긴급 조언 먼저 출력
    priority_order = [
        "손절검토", "익절검토", "추가매수", "물타기주의",
        "비중축소검토", "추세유지", "보유유지", "벤치마크추적"
    ]

    for action_name in priority_order:
        group = action_groups.get(action_name, [])
        if not group:
            continue

        icon = ACTION_ICONS.get(action_name, "●")
        print(f"\n  {'─' * 60}")
        print(f"  {icon} {action_name} ({len(group)}종목)")
        print(f"  {'─' * 60}")

        # 손익률 절대값 내림차순 정렬
        group.sort(key=lambda x: abs(x.pnl_pct), reverse=True)

        for a in group:
            pnl_sign = "+" if a.pnl_pct >= 0 else ""
            etf_tag = " [ETF]" if a.signal.action == "HOLD" and "벤치마크" in a.action else ""
            print(
                f"    {a.name:<12s} ({a.ticker})  "
                f"현재가: {a.current_price:>9,.0f}  "
                f"매입가: {a.buy_price:>9,.0f}  "
                f"수익률: {pnl_sign}{a.pnl_pct:>6.1f}%  "
                f"비중: {a.weight_pct:>4.1f}%{etf_tag}"
            )
            print(f"      퀀트: {a.signal.quant_score:+.2f}  →  {a.reasoning}")

    # 전체 종목 요약 테이블
    print(f"\n{'=' * 70}")
    print(f"  📋 전체 종목 요약 (종합점수 내림차순)")
    print(f"{'=' * 70}")
    print(f"  {'종목명':<12s} {'현재가':>9s} {'수익률':>8s} {'퀀트':>6s} {'판단':>8s} {'조언'}")
    print(f"  {'─' * 64}")

    advices_sorted = sorted(advices, key=lambda x: x.signal.combined_score, reverse=True)
    for a in advices_sorted:
        pnl_sign = "+" if a.pnl_pct >= 0 else ""
        signal_icon = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(a.signal.action, "●")
        action_icon = ACTION_ICONS.get(a.action, "●")
        print(
            f"  {a.name:<12s} {a.current_price:>9,.0f} {pnl_sign}{a.pnl_pct:>6.1f}% "
            f"{a.signal.quant_score:>+5.2f}  {signal_icon} {a.signal.action:<4s}  "
            f"{action_icon} {a.action}"
        )

    print(f"\n{'=' * 70}")
    print("  ⚠️  본 분석은 참고용이며, 투자 판단의 책임은 본인에게 있습니다.")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="KRX 주식 AI 에이전트")
    parser.add_argument("--ticker", type=str, help="단일 종목 분석 (종목코드)")
    parser.add_argument("--screen", action="store_true",
                        help="종목 발굴 (미보유 유망 종목/ETF 추천)")
    args = parser.parse_args()

    if args.screen:
        # 종목 발굴
        holdings = load_portfolio()
        settings = load_settings().get("screener", {})
        results = run_full_screen(holdings, settings)
        print_screen_report(results)
    elif args.ticker:
        # 단일 종목 분석
        signal = analyze_single(args.ticker)
        if signal:
            icon = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(signal.action, "●")
            print(f"\n{signal.name} ({signal.ticker})")
            print(f"  현재가: {signal.current_price:,.0f}원")
            print(f"  퀀트: {signal.quant_score:+.2f}  LLM: {signal.llm_score:+.2f}")
            print(f"  종합: {signal.combined_score:+.2f}  → {icon} {signal.action}")
            print(f"  {signal.analysis_summary}")
    else:
        # 포트폴리오 전체 분석
        advices = analyze_portfolio()
        print_portfolio_report(advices)


if __name__ == "__main__":
    main()
