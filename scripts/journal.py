import os
import json
import sys
from datetime import datetime
from pathlib import Path

JOURNAL_DIR = Path(__file__).parent.parent / "journal"


def journal_path(date_str=None):
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    return JOURNAL_DIR / f"{date_str}.md"


def write_journal(date_str, portfolio, research, trades, closed, reflection):
    """
    Write a structured journal entry to journal/YYYY-MM-DD.md.

    Args:
        date_str:   "YYYY-MM-DD"
        portfolio:  {"cash": float, "total_value": float, "positions": [{"symbol": str, "qty": int, "avg_price": float}]}
        research:   {symbol: {"sma20": float, "sma50": float, "news": str, "notes": str}}
        trades:     [{"time": str, "symbol": str, "action": str, "qty": int, "price": float, "reasoning": str}]
        closed:     [str]  — list of symbols closed today, or empty
        reflection: str    — end-of-day paragraph
    """
    JOURNAL_DIR.mkdir(exist_ok=True)
    path = journal_path(date_str)

    lines = []

    # Header
    lines.append(f"# Trade Journal — {date_str}\n")

    # Portfolio status
    lines.append("## Portfolio Status")
    positions_str = ", ".join(
        f"{p['symbol']} ({p['qty']} shares @ ${p['avg_price']:.2f})"
        for p in portfolio.get("positions", [])
    ) or "None"
    lines.append(f"- Cash: ${portfolio['cash']:,.2f}")
    lines.append(f"- Positions: {positions_str}")
    lines.append(f"- Total Value: ${portfolio['total_value']:,.2f}")
    lines.append("")

    # Market research
    lines.append("## Market Research")
    for symbol, data in research.items():
        lines.append(f"### {symbol}")
        sma20 = f"${data['sma20']:.2f}" if data.get("sma20") else "N/A"
        sma50 = f"${data['sma50']:.2f}" if data.get("sma50") else "N/A"
        trend = data.get("trend", "")
        lines.append(f"- 20-day MA: {sma20} | 50-day MA: {sma50}{' — ' + trend if trend else ''}")
        if data.get("news"):
            lines.append(f"- News: {data['news']}")
        if data.get("notes"):
            lines.append(f"- Decision: {data['notes']}")
        lines.append("")

    # Trades executed
    lines.append("## Trades Executed")
    if trades:
        lines.append("| Time | Symbol | Action | Qty | Price | Reasoning |")
        lines.append("|------|--------|--------|-----|-------|-----------|")
        for t in trades:
            lines.append(
                f"| {t['time']} | {t['symbol']} | {t['action']} | {t['qty']} | ${t['price']:.2f} | {t['reasoning']} |"
            )
    else:
        lines.append("No trades placed today.")
    lines.append("")

    # Positions closed
    lines.append("## Positions Closed")
    lines.append(", ".join(closed) if closed else "None today.")
    lines.append("")

    # Reflection
    lines.append("## End-of-Day Reflection")
    lines.append(reflection)
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Journal written: {path}")
    return str(path)


def read_recent(n=5):
    """Return the last n journal entries as a combined string for context."""
    JOURNAL_DIR.mkdir(exist_ok=True)
    files = sorted(JOURNAL_DIR.glob("*.md"), reverse=True)[:n]
    if not files:
        return "No prior journal entries found."
    return "\n\n---\n\n".join(f.read_text(encoding="utf-8") for f in files)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "read"

    if action == "read":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        print(read_recent(n))
    elif action == "demo":
        # Write a sample entry to verify formatting
        write_journal(
            date_str=datetime.now().strftime("%Y-%m-%d"),
            portfolio={
                "cash": 12450.00,
                "total_value": 23891.80,
                "positions": [
                    {"symbol": "NVDA", "qty": 42, "avg_price": 845.20},
                    {"symbol": "SPY",  "qty": 15, "avg_price": 521.00},
                ],
            },
            research={
                "NVDA": {
                    "sma20": 838.50, "sma50": 812.00,
                    "trend": "bullish trend intact",
                    "news": "Positive analyst upgrade from Morgan Stanley, +8% PT increase",
                    "notes": "Earnings 3 weeks out — potential catalyst",
                },
                "AAPL": {
                    "sma20": 195.20, "sma50": 198.80,
                    "trend": "short-term weakness",
                    "news": "Supply chain concerns in Taiwan Strait reporting",
                    "notes": "No action, watch for stabilization",
                },
            },
            trades=[
                {"time": "10:03", "symbol": "NVDA", "action": "BUY", "qty": 5, "price": 847.50,
                 "reasoning": "MA trend + analyst upgrade = entry"},
            ],
            closed=[],
            reflection="NVDA trade aligned with thesis. Held off on AAPL given macro uncertainty in news.\nTomorrow: Watch AAPL for reversal signal, check MSFT earnings preview.",
        )
