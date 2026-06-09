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


# Minimum candles needed for all indicators (EMA50 + ADX14)
_MIN_CANDLES = 20  # hard floor — RSI/ADX need at least 14 periods to be valid

# How many candles per day each interval produces (conservative estimate for NSE)
_CANDLES_PER_DAY = {
    "1m":  370,   # 6.25h × 60 = 375, minus gaps
    "5m":  74,    # 6.25h × 12
    "15m": 25,    # 6.25h × 4
    "1h":  6,     # 6.25h
    "1d":  1,
}

# yfinance max period allowed per interval
_MAX_PERIOD = {
    "1m":  "7d",
    "5m":  "60d",
    "15m": "60d",
    "1h":  "730d",
    "1d":  "max",
}


def _days_needed(interval: str) -> int:
    """Calculate how many days needed to get _MIN_CANDLES candles."""
    cpd = _CANDLES_PER_DAY.get(interval, 10)
    # Add 40% buffer for weekends/holidays/gaps
    return int((_MIN_CANDLES / cpd) * 1.4) + 1


def fetch_ticker_timeframe(ticker: str, period: str = "1d", interval: str = "5m") -> pd.DataFrame:
    """
    Fetch OHLCV with guaranteed minimum candles.
    If requested period gives too few candles, automatically widens until
    we have enough — without changing the interval (preserving signal quality).
    """
    if not _YF_AVAILABLE:
        df = _mock_df()
        df.attrs["source"] = "mock"
        return df

    # Build period candidates: requested first, then widen to guarantee enough candles
    days_req  = _days_needed(interval)
    max_p     = _MAX_PERIOD.get(interval, "60d")

    # Parse requested period into days
    _p_days = {"1d": 1, "2d": 2, "3d": 3, "5d": 5, "7d": 7, "10d": 10,
               "14d": 14, "30d": 30, "60d": 60}
    req_days = _p_days.get(period, 1)

    # Candidate periods: start from max(requested, needed), step up
    candidates = []
    for p, d in sorted(_p_days.items(), key=lambda x: x[1]):
        if d >= req_days and d >= max(req_days, 1):
            candidates.append(p)
        if len(candidates) >= 5:
            break
    # Always include max as final fallback
    if max_p not in candidates:
        candidates.append(max_p)
    # Deduplicate preserving order
    seen = set()
    periods_to_try = [p for p in candidates if not (p in seen or seen.add(p))]

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
            print(f"data.py: {ticker} period={p} interval={interval} failed: {e}")
            continue

    # Nuclear fallback: daily candles always work
    try:
        df = yf.download(ticker, period="60d", interval="1d",
                         auto_adjust=True, progress=False, threads=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.dropna(inplace=True)
            if len(df) >= _MIN_CANDLES:
                df.attrs["source"] = "yfinance"
                return df
    except Exception as e:
        print(f"data.py: nuclear fallback failed for {ticker}: {e}")

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
