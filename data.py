"""
data.py — OHLCV data fetcher via yfinance + advanced fetch_news.

Returns a DataFrame with attrs["source"] set to:
  "yfinance" — live data fetched successfully
  "mock"     — all sources failed (blocked by core.py)
"""

import pandas as pd
import numpy as np

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False


# Period fallback chain: if narrow period returns too few candles, try wider ones
_PERIOD_FALLBACKS = {
    "1d":  ["2d", "5d", "7d"],
    "3d":  ["5d", "7d", "10d"],
    "7d":  ["7d", "10d", "14d"],
    "30d": ["30d", "60d"],
}

_MIN_CANDLES = 50  # EMA50 needs 50, ADX14 needs 14 — 50 covers both


def fetch_ticker_timeframe(ticker: str, period: str = "1d", interval: str = "5m") -> pd.DataFrame:
    """
    Fetch OHLCV data for a ticker with automatic period-widening retry.

    Indian stocks (.NS/.BO) on sub-15m intervals frequently return sparse data
    from yfinance — retries with progressively wider periods until we get
    at least _MIN_CANDLES candles.

    attrs["source"] = "yfinance" | "mock"
    """
    if not _YF_AVAILABLE:
        df = _mock_df()
        df.attrs["source"] = "mock"
        return df

    # Always try the requested period first, then fallbacks
    periods_to_try = [period] + [p for p in _PERIOD_FALLBACKS.get(period, []) if p != period]

    for p in periods_to_try:
        try:
            df = yf.download(
                ticker,
                period=p,
                interval=interval,
                auto_adjust=True,
                progress=False,
                threads=False,
            )

            # Flatten MultiIndex columns (yfinance quirk)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            if df.empty:
                continue

            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.dropna(inplace=True)

            if len(df) >= _MIN_CANDLES:
                df.attrs["source"] = "yfinance"
                return df

        except Exception as e:
            print(f"data.py: yfinance failed for {ticker} period={p}: {e}")
            continue

    # Last resort: try a daily interval with 60d period — works for almost all assets
    try:
        df = yf.download(
            ticker,
            period="60d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.dropna(inplace=True)
            if len(df) >= _MIN_CANDLES:
                df.attrs["source"] = "yfinance"
                return df
    except Exception as e:
        print(f"data.py: fallback 60d/1d failed for {ticker}: {e}")

    df = _mock_df()
    df.attrs["source"] = "mock"
    return df


def _mock_df() -> pd.DataFrame:
    """Minimal mock — core.py blocks this from being used for real decisions."""
    import datetime
    now    = datetime.datetime.now()
    times  = [now - datetime.timedelta(minutes=5 * i) for i in range(60, 0, -1)]
    rng    = np.random.default_rng(42)
    closes = 100.0 + np.cumsum(rng.normal(0, 0.5, 60))
    return pd.DataFrame({
        "Open":   closes * 0.999,
        "High":   closes * 1.002,
        "Low":    closes * 0.998,
        "Close":  closes,
        "Volume": rng.integers(1000, 5000, 60).astype(float),
    }, index=times)



# ══════════════════════════════════════════════════════════════════════
# Advanced fetch_news — relevance-scored, deduplicated, source-tagged
# ══════════════════════════════════════════════════════════════════════

import re
import time
from datetime import datetime, timedelta, timezone
import feedparser

_CRYPTO_KEYWORDS = {
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "bnb", "xrp",
    "ripple", "crypto", "blockchain", "defi", "altcoin", "stablecoin",
    "coinbase", "binance", "sec", "etf", "halving", "on-chain",
}
_GOLD_KEYWORDS = {
    "gold", "silver", "gld", "slv", "bullion", "precious metal",
    "comex", "spot price", "safe haven", "inflation", "fed",
}
_INDIA_KEYWORDS = {
    "nse", "bse", "nifty", "sensex", "sebi", "rbi", "rupee", "inr",
    "india", "indian", "mumbai", "delhi", "quarter", "q1", "q2", "q3", "q4",
}
_US_TECH_KEYWORDS = {
    "nasdaq", "s&p", "earnings", "revenue", "guidance", "ai", "chips",
    "semiconductor", "cloud", "quarter", "beat", "miss", "forecast",
}


def _build_keyword_set(query: str) -> set:
    query_lower = query.lower()
    tokens = set(re.findall(r'\w+', query_lower))
    tokens -= {"stock", "price", "today", "india", "nse", "bse", "crypto"}
    if any(c in query_lower for c in ["btc", "eth", "sol", "bnb", "xrp", "crypto"]):
        tokens |= _CRYPTO_KEYWORDS
    if any(c in query_lower for c in ["gold", "silver", "gld", "slv"]):
        tokens |= _GOLD_KEYWORDS
    if any(c in query_lower for c in ["nse", "bse", "india"]):
        tokens |= _INDIA_KEYWORDS
    if any(c in query_lower for c in ["nvda", "aapl", "msft", "googl", "meta", "amzn", "tsla"]):
        tokens |= _US_TECH_KEYWORDS
    return tokens


def _relevance_score(title: str, keywords: set) -> int:
    return len(set(re.findall(r'\w+', title.lower())) & keywords)


def _normalise_title(title: str) -> str:
    title = re.sub(r'\s*[-–]\s*[^-–]{3,40}$', '', title)
    return re.sub(r'[^\w\s]', '', title.lower()).strip()


def _is_duplicate(title: str, seen: list, threshold: float = 0.65) -> bool:
    words_a = set(_normalise_title(title).split())
    if not words_a:
        return False
    for seen_title in seen:
        words_b = set(seen_title.split())
        if not words_b:
            continue
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        if union > 0 and intersection / union >= threshold:
            return True
    return False


def _entry_is_fresh(entry, max_age_hours: int) -> bool:
    published = getattr(entry, "published_parsed", None)
    if not published:
        return False
    try:
        published_dt = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
        return datetime.now(timezone.utc) - published_dt <= timedelta(hours=max_age_hours)
    except Exception:
        return False


def _format_entry(entry) -> str:
    title = entry.title.strip()
    source_match = re.search(r'[-–]\s*([^-–]{3,40})$', title)
    source = source_match.group(1).strip() if source_match else "Unknown"
    published = getattr(entry, "published_parsed", None)
    if published:
        try:
            dt = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
            stamp = dt.strftime("%b %d %H:%M UTC")
        except Exception:
            stamp = "recent"
    else:
        stamp = "recent"
    clean_title = re.sub(r'\s*[-–]\s*[^-–]{3,40}$', '', title).strip()
    return f"{clean_title} ({source}, {stamp})"


def fetch_news(
    query: str = "bitcoin crypto",
    max_items: int = 6,
    max_age_hours: int = 24,
    min_relevance: int = 1,
) -> list:
    """
    Fetch relevant, deduplicated, source-tagged headlines.
    Returns [] on any failure — never raises.
    """
    feed_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(feed_url, request_headers={"User-Agent": "Mozilla/5.0"})
    except Exception as e:
        print(f"data.py: feedparser failed for '{query}': {e}")
        return []

    if not feed.entries:
        return []

    keywords = _build_keyword_set(query)
    seen_normalised: list = []
    results: list = []

    for entry in feed.entries:
        if len(results) >= max_items * 3:
            break
        title = getattr(entry, "title", "").strip()
        if not title or len(title) < 10:
            continue
        if not _entry_is_fresh(entry, max_age_hours):
            continue
        score = _relevance_score(title, keywords)
        if score < min_relevance:
            continue
        norm = _normalise_title(title)
        if _is_duplicate(norm, seen_normalised):
            continue
        seen_normalised.append(norm)
        results.append((score, _format_entry(entry)))

    results.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in results[:max_items]]
