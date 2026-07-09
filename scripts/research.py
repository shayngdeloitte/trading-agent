import os
import requests
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv

load_dotenv()

ALPACA_KEY = os.getenv("APCA_API_KEY_ID")
ALPACA_SECRET = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = os.getenv("APCA_BASE_URL")

def get_bars(symbol, timeframe="1Day", limit=60):
    """Fetch historical price bars for a symbol."""
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
    }
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
    start = (datetime.utcnow() - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "timeframe": timeframe,
        "limit": limit,
        "adjustment": "raw",
        "start": start,
        "feed": "iex",
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json()

def get_account():
    """Get current portfolio status."""
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
    }
    url = f"{BASE_URL}/account"
    response = requests.get(url, headers=headers)
    return response.json()

def get_positions():
    """Get all open positions."""
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
    }
    url = f"{BASE_URL}/positions"
    response = requests.get(url, headers=headers)
    return response.json()

def get_news(symbol):
    """Get recent news for a symbol."""
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
    }
    url = "https://data.alpaca.markets/v1beta1/news"
    params = {
        "symbols": symbol,
        "limit": 5,
        "sort": "desc"
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json()

def compute_signals(bars_data):
    """Compute SMA20, SMA50, and pct change from bar data."""
    bars = bars_data.get("bars", [])
    if not bars:
        return {}
    closes = [b["c"] for b in bars]
    last = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else last
    sma20 = round(sum(closes[-20:]) / min(20, len(closes)), 2) if len(closes) >= 20 else None
    sma50 = round(sum(closes[-50:]) / min(50, len(closes)), 2) if len(closes) >= 50 else None
    return {
        "last_close": round(last, 2),
        "prev_close": round(prev, 2),
        "pct_change": round((last - prev) / prev * 100, 2),
        "sma20": sma20,
        "sma50": sma50,
        "above_sma20": (last > sma20) if sma20 else None,
        "above_sma50": (last > sma50) if sma50 else None,
        "volume": bars[-1].get("v", 0),
        "bar_count": len(bars),
    }

if __name__ == "__main__":
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "account"
    symbol = sys.argv[2] if len(sys.argv) > 2 else None

    if action == "bars" and symbol:
        print(json.dumps(get_bars(symbol)))
    elif action == "signals" and symbol:
        print(json.dumps(compute_signals(get_bars(symbol))))
    elif action == "news" and symbol:
        print(json.dumps(get_news(symbol)))
    elif action == "positions":
        print(json.dumps(get_positions()))
    else:
        print(json.dumps(get_account()))
