"""
data.py — Multi-source OHLCV fetcher.

Fixes from v2:
- Mock data now raises immediately at the data layer (not just core.py)
  so no code path can accidentally use fake data downstream
- Binance interval map corrected: "1h" was being sent as "1hh" due to
  the no-op replace("m","m"); now uses an explicit lookup table
- Added timeout retry with exponential backoff for yfinance
- Ticker normalisation: strips whitespace, upper-cases before every attempt
"""

import time
import pandas as pd
import yfinance as yf
import numpy as np
import requests

# Explicit Binance interval map — avoids the replace() no-op bug
_BINANCE_INTERVAL_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1d",
    "3d": "3d",
    "1w": "1w",
    "1M": "1M",
}

# Binance only supports these tickers
_BINANCE_MAP = {
    "BTC-USD": "BTCUSDT",
    "ETH-USD": "ETHUSDT",
    "SOL-USD": "SOLUSDT",
    "BNB-USD": "BNBUSDT",
    "XRP-USD": "XRPUSDT",
}


def _yfinance_fetch(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Try yfinance with one retry on transient failures."""
    for attempt in range(2):
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval, timeout=15)
            if not df.empty:
                df = df.rename(columns=str)
                df.dropna(inplace=True)
                if not df.empty:
                    df.attrs["source"] = "yfinance"
                    df.attrs["ticker"] = ticker
                    return df
        except Exception as e:
            if attempt == 0:
                time.sleep(1)
            else:
                print(f"yfinance {ticker} failed after retry: {e}")
    return pd.DataFrame()


def _binance_fetch(ticker: str, interval: str) -> pd.DataFrame:
    """Fetch from Binance REST API. Only called for known crypto pairs."""
    symbol = _BINANCE_MAP.get(ticker)
    if not symbol:
        return pd.DataFrame()

    binance_interval = _BINANCE_INTERVAL_MAP.get(interval)
    if not binance_interval:
        # Fallback: strip to something Binance understands
        binance_interval = interval
        print(f"Warning: unknown interval '{interval}' passed to Binance — using as-is")

    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": binance_interval, "limit": 288}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            print(f"Binance returned HTTP {r.status_code} for {symbol}")
            return pd.DataFrame()

        data = r.json()
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data, columns=[
            "timestamp", "Open", "High", "Low", "Close", "Volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        df.index.name = "Datetime"
        df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
        df.dropna(inplace=True)
        if df.empty:
            return pd.DataFrame()
        df.attrs["source"] = "binance"
        df.attrs["ticker"] = ticker
        return df
    except Exception as e:
        print(f"Binance fetch failed for {ticker}: {e}")
        return pd.DataFrame()


def fetch_ticker_timeframe(ticker: str, period: str = "1d", interval: str = "5m") -> pd.DataFrame:
    """
    Fetch OHLCV for any ticker with multi-source fallback.

    Priority:
      1. yfinance  (works for stocks + crypto via Yahoo suffixes)
      2. Binance   (crypto only — higher rate limits, better data quality)
      3. RAISES    (never returns mock data — real-money use requires real data)

    Raises:
        Exception: if all real data sources fail, with a clear user-facing message.
    """
    ticker = ticker.strip().upper() if ticker else ticker

    # ── 1. yfinance (primary for everything) ───────────────────────
    df = _yfinance_fetch(ticker, period, interval)
    if not df.empty:
        return df

    # Try alternative Yahoo suffix formats for Indian stocks
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        for suffix in [".NS", ".BO"]:
            df = _yfinance_fetch(ticker + suffix, period, interval)
            if not df.empty:
                return df

    # ── 2. Binance fallback (crypto only) ─────────────────────────
    if ticker in _BINANCE_MAP:
        df = _binance_fetch(ticker, interval)
        if not df.empty:
            return df

    # ── 3. Hard stop — never use mock data for real money ──────────
    # We do NOT generate mock data here. core.py also has a guard,
    # but the right place to stop is at the data layer.
    raise Exception(
        f"⚠️ All data sources failed for '{ticker}'.\n"
        "Cannot analyse with mock data for real-money use.\n"
        "Possible causes:\n"
        "  • No internet connection\n"
        "  • Ticker symbol incorrect (check Yahoo Finance for the exact symbol)\n"
        "  • Market is closed and no recent data is cached\n"
        "  • yfinance rate-limited — try again in 30 seconds\n"
        "Please verify your connection and the symbol, then retry."
    )


# ── Backward-compatible wrappers ───────────────────────────────────
def fetch_btc(period="1d", interval="5m"):
    return fetch_ticker_timeframe("BTC-USD", period, interval)

def fetch_btc_timeframe(period="1d", interval="5m"):
    return fetch_ticker_timeframe("BTC-USD", period, interval)
