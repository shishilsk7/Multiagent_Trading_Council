import pandas as pd
import yfinance as yf
import numpy as np
import requests


def fetch_ticker_timeframe(ticker: str, period: str = "1d", interval: str = "5m"):
    """
    Fetch OHLCV for any ticker (stock or crypto) with multi-source fallback.
    For non-BTC crypto, only yfinance is tried; for stocks, yfinance is primary.
    """

    # Method 1: yfinance (works for stocks AND crypto via Yahoo suffixes)
    for t in [ticker, ticker.upper()]:
        try:
            df = yf.Ticker(t).history(period=period, interval=interval, timeout=15)
            if not df.empty:
                df = df.rename(columns=str)
                df.dropna(inplace=True)
                if not df.empty:
                    df.attrs["source"] = "yfinance"
                    df.attrs["ticker"] = ticker
                    return df
        except Exception as e:
            print(f"yfinance {t} failed: {e}")

    # Method 2: Binance API — only for BTC/ETH/SOL/BNB/XRP crypto pairs
    BINANCE_MAP = {
        "BTC-USD": "BTCUSDT",
        "ETH-USD": "ETHUSDT",
        "SOL-USD": "SOLUSDT",
        "BNB-USD": "BNBUSDT",
        "XRP-USD": "XRPUSDT",
    }
    if ticker in BINANCE_MAP:
        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {"symbol": BINANCE_MAP[ticker], "interval": interval.replace("m", "m"), "limit": 200}
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                df = pd.DataFrame(data, columns=[
                    "timestamp", "Open", "High", "Low", "Close", "Volume",
                    "close_time", "quote_volume", "trades",
                    "taker_buy_base", "taker_buy_quote", "ignore"
                ])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                df.set_index("timestamp", inplace=True)
                df.index.name = "Datetime"
                df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
                df.attrs["source"] = "binance"
                df.attrs["ticker"] = ticker
                return df
        except Exception as e:
            print(f"Binance fallback failed: {e}")

    # Method 3: Mock data (last resort)
    print(f"WARNING: All sources failed for {ticker}, generating mock data")
    periods = 150
    base = 100
    ts = pd.date_range(end=pd.Timestamp.now(), periods=periods, freq="5min")
    prices = base + np.cumsum(np.random.normal(0, 0.5, periods))
    df = pd.DataFrame({
        "Open":   prices + np.random.uniform(-0.2, 0.2, periods),
        "High":   prices + np.random.uniform(0.2, 0.8, periods),
        "Low":    prices - np.random.uniform(0.2, 0.8, periods),
        "Close":  prices,
        "Volume": np.random.randint(1_000_000, 5_000_000, periods),
    }, index=ts)
    df.index.name = "Datetime"
    df.attrs["source"] = "mock"
    df.attrs["ticker"] = ticker
    return df


# Backward-compatible wrappers
def fetch_btc(period="1d", interval="5m"):
    return fetch_ticker_timeframe("BTC-USD", period, interval)

def fetch_btc_timeframe(period="1d", interval="5m"):
    return fetch_ticker_timeframe("BTC-USD", period, interval)
