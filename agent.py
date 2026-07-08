"""
agent.py — Main entry point for the trading agent.
Runs one full session: research → trade decisions → journal → notify.

Usage:
  python agent.py research   # 9:45 AM ET — pull data, write Research section
  python agent.py trade      # 10:00 AM ET — evaluate and place orders
  python agent.py journal    # 4:15 PM ET — complete journal, send digest
  python agent.py smoke      # verify Alpaca connection and credentials
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "scripts"))

from research import get_bars, get_account, get_positions, get_news, compute_signals
from trade import place_order, get_market_status, validate_order
from journal import write_journal, read_recent, journal_path
from notify import write_heartbeat, send_digest


WATCHLIST_PATH = ROOT / "watchlist.json"


def load_watchlist():
    with open(WATCHLIST_PATH) as f:
        data = json.load(f)
    return data["watchlist"], data.get("cash_reserve_pct", 20)


def today():
    return datetime.now().strftime("%Y-%m-%d")


def check_market():
    status = get_market_status()
    is_open = status.get("is_open", False)
    next_open = status.get("next_open", "unknown")
    return is_open, next_open


# ---------------------------------------------------------------------------
# Phase 1: Research (9:45 AM ET)
# ---------------------------------------------------------------------------

def run_research():
    print("=== RESEARCH PHASE ===")
    is_open, next_open = check_market()
    if not is_open:
        msg = f"Market closed. Next open: {next_open}. Skipping research."
        print(msg)
        write_heartbeat(status="skipped", note=msg)
        return

    watchlist, _ = load_watchlist()
    account = get_account()
    positions = get_positions()
    positions_map = {p["symbol"]: p for p in positions}

    portfolio = {
        "cash": float(account.get("cash", 0)),
        "total_value": float(account.get("portfolio_value", 0)),
        "positions": [
            {
                "symbol": p["symbol"],
                "qty": int(p["qty"]),
                "avg_price": float(p["avg_entry_price"]),
            }
            for p in positions
        ],
    }

    research = {}
    for item in watchlist:
        sym = item["symbol"]
        print(f"  Researching {sym}...")
        bars_data = get_bars(sym, limit=60)
        signals = compute_signals(bars_data)
        news_data = get_news(sym)
        headlines = "; ".join(
            n.get("headline", "") for n in news_data.get("news", [])[:3]
        )
        trend = ""
        if signals.get("above_sma20") and signals.get("above_sma50"):
            trend = "bullish — above both MAs"
        elif not signals.get("above_sma20") and not signals.get("above_sma50"):
            trend = "bearish — below both MAs"
        else:
            trend = "mixed — between MAs"

        research[sym] = {
            "sma20": signals.get("sma20"),
            "sma50": signals.get("sma50"),
            "last_close": signals.get("last_close"),
            "pct_change": signals.get("pct_change"),
            "trend": trend,
            "news": headlines or "No recent news",
            "notes": "",
            "position": positions_map.get(sym),
        }

    # Save research to journal (partial entry — trades/reflection added later)
    date_str = today()
    write_journal(
        date_str=date_str,
        portfolio=portfolio,
        research=research,
        trades=[],
        closed=[],
        reflection="[Pending — to be completed at end of day]",
    )

    # Cache research data for trade phase
    cache_path = ROOT / "journal" / f"{date_str}_research_cache.json"
    cache_path.write_text(
        json.dumps({"portfolio": portfolio, "research": research}, indent=2),
        encoding="utf-8",
    )

    write_heartbeat(status="ok", note="Research complete")
    print(f"Research complete. Journal written for {date_str}.")


# ---------------------------------------------------------------------------
# Phase 2: Trade (10:00 AM ET)
# ---------------------------------------------------------------------------

def run_trade():
    print("=== TRADE PHASE ===")
    is_open, next_open = check_market()
    if not is_open:
        msg = f"Market closed. Next open: {next_open}. No trades placed."
        print(msg)
        write_heartbeat(status="skipped", note=msg)
        return

    date_str = today()
    cache_path = ROOT / "journal" / f"{date_str}_research_cache.json"
    if not cache_path.exists():
        print("No research cache found — run 'python agent.py research' first.")
        sys.exit(1)

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    portfolio = cache["portfolio"]
    research = cache["research"]
    account_value = portfolio["total_value"]
    current_positions = portfolio["positions"]

    watchlist, cash_reserve_pct = load_watchlist()
    trades_placed = []
    closed = []

    account = get_account()
    positions = get_positions()
    positions_map = {p["symbol"]: p for p in positions}

    for item in watchlist:
        sym = item["symbol"]
        data = research.get(sym, {})
        last_close = data.get("last_close")
        sma20 = data.get("sma20")
        sma50 = data.get("sma50")
        pct_change = data.get("pct_change", 0)

        if not last_close:
            print(f"  {sym}: No price data, skipping.")
            continue

        # Stop loss check — close if down >8% from entry
        pos = positions_map.get(sym)
        if pos:
            entry = float(pos.get("avg_entry_price", last_close))
            unrealized_pct = (last_close - entry) / entry * 100
            if unrealized_pct <= -8:
                print(f"  {sym}: Stop loss triggered ({unrealized_pct:.1f}%) — closing position.")
                from trade import cancel_all_orders
                result = place_order(sym, pos["qty"], "sell",
                                     limit_price=round(last_close * 0.998, 2))
                closed.append(sym)
                trades_placed.append({
                    "time": datetime.now().strftime("%H:%M"),
                    "symbol": sym,
                    "action": "SELL",
                    "qty": int(pos["qty"]),
                    "price": round(last_close * 0.998, 2),
                    "reasoning": f"Stop loss triggered: {unrealized_pct:.1f}% from entry",
                })
                continue

        # Buy signal: price above both MAs, no existing position
        if sma20 and sma50 and last_close > sma20 and last_close > sma50 and not pos:
            max_alloc = item.get("max_allocation_pct", 8) / 100
            max_dollars = account_value * max_alloc
            qty = max(1, int(max_dollars / last_close))
            limit_price = round(last_close * 1.002, 2)  # within 0.2% of ask

            ok, reason = validate_order(
                sym, qty, "buy", last_close, account_value, current_positions, watchlist
            )
            if ok:
                print(f"  {sym}: BUY signal — placing limit order {qty} @ ${limit_price}")
                result = place_order(sym, qty, "buy", limit_price=limit_price,
                                     current_price=last_close, account_value=account_value,
                                     current_positions=current_positions, watchlist=watchlist)
                trades_placed.append({
                    "time": datetime.now().strftime("%H:%M"),
                    "symbol": sym,
                    "action": "BUY",
                    "qty": qty,
                    "price": limit_price,
                    "reasoning": f"Above SMA20 (${sma20}) and SMA50 (${sma50}), pct_change={pct_change:.2f}%",
                })
            else:
                print(f"  {sym}: BUY blocked — {reason}")
                research[sym]["notes"] = f"Buy blocked: {reason}"

        # Sell signal: price crossed below SMA20, has position
        elif sma20 and last_close < sma20 and pos:
            qty = int(pos["qty"])
            limit_price = round(last_close * 0.998, 2)
            print(f"  {sym}: SELL signal — placing limit order {qty} @ ${limit_price}")
            result = place_order(sym, qty, "sell", limit_price=limit_price)
            closed.append(sym)
            trades_placed.append({
                "time": datetime.now().strftime("%H:%M"),
                "symbol": sym,
                "action": "SELL",
                "qty": qty,
                "price": limit_price,
                "reasoning": f"Price ${last_close} crossed below SMA20 ${sma20}",
            })

        else:
            decision = "Hold — no signal"
            if pos:
                decision = "Hold — position open, no exit signal"
            elif sma20 and last_close < sma20:
                decision = "Hold — below SMA20, no entry"
            research[sym]["notes"] = decision
            print(f"  {sym}: {decision}")

    # Update journal with trades
    write_journal(
        date_str=date_str,
        portfolio=portfolio,
        research=research,
        trades=trades_placed,
        closed=closed,
        reflection="[Pending — to be completed at end of day]",
    )

    # Update cache with trade results
    cache["trades"] = trades_placed
    cache["closed"] = closed
    cache["research"] = research
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    write_heartbeat(status="ok", note=f"Trade phase complete. {len(trades_placed)} orders placed.")
    print(f"Trade phase complete. {len(trades_placed)} orders placed.")


# ---------------------------------------------------------------------------
# Phase 3: End of Day Journal (4:15 PM ET)
# ---------------------------------------------------------------------------

def run_journal():
    print("=== END OF DAY JOURNAL ===")
    date_str = today()
    cache_path = ROOT / "journal" / f"{date_str}_research_cache.json"

    portfolio = {"cash": 0, "total_value": 0, "positions": []}
    research = {}
    trades = []
    closed = []

    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        portfolio = cache.get("portfolio", portfolio)
        research = cache.get("research", research)
        trades = cache.get("trades", trades)
        closed = cache.get("closed", closed)

    # Refresh final account state from Alpaca
    try:
        account = get_account()
        positions = get_positions()
        portfolio["cash"] = float(account.get("cash", portfolio["cash"]))
        portfolio["total_value"] = float(account.get("portfolio_value", portfolio["total_value"]))
        portfolio["positions"] = [
            {"symbol": p["symbol"], "qty": int(p["qty"]), "avg_price": float(p["avg_entry_price"])}
            for p in positions
        ]
    except Exception as e:
        print(f"Warning: could not refresh account data — {e}")

    # Build reflection
    if trades:
        symbols_traded = ", ".join(t["symbol"] for t in trades)
        reflection = (
            f"Placed {len(trades)} order(s) today: {symbols_traded}. "
            f"Portfolio value: ${portfolio['total_value']:,.2f}. "
            f"Review open positions tomorrow and watch for stop loss levels."
        )
    else:
        reflection = (
            f"No trades placed today. Portfolio value: ${portfolio['total_value']:,.2f}. "
            f"Conditions did not meet entry criteria. Continue monitoring watchlist."
        )

    write_journal(
        date_str=date_str,
        portfolio=portfolio,
        research=research,
        trades=trades,
        closed=closed,
        reflection=reflection,
    )

    # Send email digest if configured
    notify_email = os.getenv("NOTIFY_EMAIL")
    sendgrid_key = os.getenv("SENDGRID_API_KEY")
    if notify_email and sendgrid_key and sendgrid_key != "your_sendgrid_api_key_here":
        try:
            send_digest(str(journal_path(date_str)))
        except Exception as e:
            print(f"Email digest failed: {e}")
    else:
        print("Email digest skipped — SENDGRID_API_KEY not configured.")

    write_heartbeat(status="ok", note="End of day journal complete")
    print(f"Journal complete for {date_str}.")


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def run_smoke():
    print("=== SMOKE TEST ===")
    print("Checking Alpaca connection...")
    try:
        account = get_account()
        print(f"  Account: {account.get('id', 'unknown')}")
        print(f"  Portfolio value: ${float(account.get('portfolio_value', 0)):,.2f}")
        print(f"  Cash: ${float(account.get('cash', 0)):,.2f}")
        print(f"  Status: {account.get('status', 'unknown')}")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    print("Checking market status...")
    try:
        is_open, next_open = check_market()
        print(f"  Market open: {is_open}")
        print(f"  Next open: {next_open}")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    print("Checking watchlist...")
    watchlist, cash_reserve = load_watchlist()
    print(f"  Symbols: {[s['symbol'] for s in watchlist]}")
    print(f"  Cash reserve: {cash_reserve}%")

    print("\nSmoke test passed. Agent is ready.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "smoke"

    if phase == "research":
        run_research()
    elif phase == "trade":
        run_trade()
    elif phase == "journal":
        run_journal()
    elif phase == "smoke":
        run_smoke()
    else:
        print(f"Unknown phase: {phase}")
        print("Usage: python agent.py [research|trade|journal|smoke]")
        sys.exit(1)
