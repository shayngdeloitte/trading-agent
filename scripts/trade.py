import os
import requests
import json
import sys
from dotenv import load_dotenv

load_dotenv()

ALPACA_KEY = os.getenv("APCA_API_KEY_ID")
ALPACA_SECRET = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = os.getenv("APCA_BASE_URL")


def validate_order(symbol, qty, side, current_price, account_value, current_positions, watchlist=None):
    """
    Pre-flight checks before placing any order.
    Returns (True, "Order validated") or (False, reason).
    """
    if side == "sell":
        return True, "Sell order — skipping buy-side allocation checks"

    order_value = float(qty) * float(current_price)
    allocation_pct = (order_value / account_value) * 100

    # Per-symbol cap: use watchlist max_allocation_pct if available, else 10%
    max_alloc = 10.0
    if watchlist:
        for item in watchlist:
            if item["symbol"] == symbol:
                max_alloc = item.get("max_allocation_pct", 10.0)
                break

    if allocation_pct > max_alloc:
        return False, f"Order exceeds {max_alloc}% allocation limit for {symbol}: {allocation_pct:.1f}%"

    # Total exposure check: existing positions + this order must stay under 80%
    total_invested = sum(float(p.get("market_value", 0)) for p in current_positions)
    if (total_invested + order_value) / account_value > 0.80:
        return False, "Order would violate 20% cash reserve requirement"

    return True, "Order validated"


def place_order(symbol, qty, side, limit_price=None, current_price=None,
                account_value=None, current_positions=None, watchlist=None):
    """Place a buy or sell order, with pre-flight validation on buys."""
    if side == "buy" and current_price and account_value is not None:
        positions = current_positions or []
        ok, reason = validate_order(symbol, qty, side, current_price,
                                    account_value, positions, watchlist)
        if not ok:
            return {"error": "validation_failed", "reason": reason}

    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
        "Content-Type": "application/json",
    }

    order_data = {
        "symbol": symbol,
        "qty": qty,
        "side": side,
        "type": "limit" if limit_price else "market",
        "time_in_force": "day",
    }

    if limit_price:
        order_data["limit_price"] = str(limit_price)

    url = f"{BASE_URL}/orders"
    response = requests.post(url, headers=headers, json=order_data)
    return response.json()


def cancel_all_orders():
    """Cancel all open orders."""
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
    }
    url = f"{BASE_URL}/orders"
    response = requests.delete(url, headers=headers)
    return response.status_code


def get_market_status():
    """Check if the market is open."""
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
    }
    url = f"{BASE_URL}/clock"
    response = requests.get(url, headers=headers)
    return response.json()


if __name__ == "__main__":
    action = sys.argv[1]

    if action == "status":
        print(json.dumps(get_market_status()))
    elif action == "order":
        symbol = sys.argv[2]
        qty = sys.argv[3]
        side = sys.argv[4]
        limit_price = sys.argv[5] if len(sys.argv) > 5 else None
        print(json.dumps(place_order(symbol, qty, side, limit_price)))
    elif action == "cancel":
        print(cancel_all_orders())
    elif action == "validate":
        # python scripts/trade.py validate NVDA 5 buy 850.00 100000
        symbol = sys.argv[2]
        qty = float(sys.argv[3])
        side = sys.argv[4]
        price = float(sys.argv[5])
        acct_value = float(sys.argv[6])
        ok, reason = validate_order(symbol, qty, side, price, acct_value, [])
        print(json.dumps({"valid": ok, "reason": reason}))
