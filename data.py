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
_MIN_CANDLES = 120  # Warmed-up floor to ensure EMA50 and ADX14 calculate without NaNs

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
    _p_days = {
        "1d": 1, "2d": 2, "3d": 3, "5d": 5, "7d": 7, "10d": 10, "14d": 14, "30d": 30, "60d": 60,
        "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "max": 9999
    }
    req_days = _p_days.get(period, 1)
    target_days = max(req_days, days_req)

    # Candidate periods: start from target_days and step up
    candidates = []
    for p, d in sorted(_p_days.items(), key=lambda x: x[1]):
        if d >= target_days:
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
import calendar
import concurrent.futures
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
import feedparser
import requests

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

_RSS_TIMEOUT_SECONDS = 5
_OFFICIAL_INDIA_SOURCES = {"SEBI", "RBI Press Releases", "RBI Notifications"}


def _is_crypto_query(query: str) -> bool:
    query_lower = query.lower()
    return any(term in query_lower for term in ["bitcoin", "btc", "ethereum", "eth", "solana", "sol", "bnb", "xrp", "crypto"])


def _is_india_query(query: str) -> bool:
    query_lower = query.lower()
    return any(term in query_lower for term in [" nse", " bse", "india", "nifty", "sensex", ".ns"])


def _news_sources(query: str) -> list[tuple[str, str, bool]]:
    """Return public RSS sources appropriate to the requested asset category."""
    is_india = _is_india_query(query)
    google_region = "IN" if is_india else "US"
    sources = [(
        "Google News",
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=en-{google_region}&gl={google_region}&ceid={google_region}:en",
        True,
    )]

    if _is_crypto_query(query):
        sources.append(("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", False))
    if is_india:
        sources.extend([
            ("SEBI", "https://www.sebi.gov.in/sebirss.xml", False),
            ("RBI Press Releases", "https://rbi.org.in/pressreleases_rss.xml", False),
            ("RBI Notifications", "https://rbi.org.in/notifications_rss.xml", False),
        ])
    return sources


def _fetch_feed(source: str, url: str, strip_title_source: bool) -> tuple[str, bool, list]:
    """Fetch one public RSS feed with a bounded timeout; failures are non-fatal."""
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Multiagent-Trading-Council/1.0 (+RSS reader)"},
            timeout=_RSS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return source, strip_title_source, feedparser.parse(response.content).entries
    except Exception as e:
        print(f"data.py: RSS source {source} failed for '{url}': {e}")
        return source, strip_title_source, []


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


def _entry_datetime(entry):
    published = getattr(entry, "published_parsed", None)
    if not published:
        return None
    try:
        # RSS parsers return a UTC struct_time. calendar.timegm preserves that
        # timezone instead of interpreting it as the host machine's local time.
        return datetime.fromtimestamp(calendar.timegm(published), tz=timezone.utc)
    except Exception:
        return None


def _entry_is_fresh(published_dt, max_age_hours: int) -> bool:
    if not published_dt:
        return False
    age = datetime.now(timezone.utc) - published_dt
    return timedelta(0) <= age <= timedelta(hours=max_age_hours)


def _format_entry(entry, source: str, published_dt, strip_title_source: bool) -> str:
    title = entry.title.strip()
    if strip_title_source:
        source_match = re.search(r'[-–]\s*([^-–]{3,40})$', title)
        source = source_match.group(1).strip() if source_match else source
        title = re.sub(r'\s*[-–]\s*[^-–]{3,40}$', '', title).strip()
    return f"{title} ({source}, {published_dt.strftime('%b %d %H:%M UTC')})"


def fetch_news(
    query: str = "bitcoin crypto",
    max_items: int = 6,
    max_age_hours: int = 24,
    min_relevance: int = 1,
) -> list:
    """
    Fetch relevant, recent, globally deduplicated, source-tagged headlines.
    Returns [] on any failure — never raises.
    """
    keywords = _build_keyword_set(query)
    source_specs = _news_sources(query)
    candidates: list[tuple[datetime, int, str, str, str]] = []

    # Source requests are independent. Parallel fetches avoid turning a slow
    # public RSS endpoint into cumulative latency for the analysis run.
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(source_specs)) as executor:
        futures = [executor.submit(_fetch_feed, *spec) for spec in source_specs]
        for future in concurrent.futures.as_completed(futures):
            source, strip_title_source, entries = future.result()
            for entry in entries:
                title = getattr(entry, "title", "").strip()
                if not title or len(title) < 10 or "sponsored" in title.lower():
                    continue
                published_dt = _entry_datetime(entry)
                if not _entry_is_fresh(published_dt, max_age_hours):
                    continue
                score = _relevance_score(title, keywords)
                if score < min_relevance:
                    continue
                candidates.append((
                    published_dt,
                    score,
                    _normalise_title(title),
                    source,
                    _format_entry(entry, source, published_dt, strip_title_source),
                ))

    # Timestamp is primary: the prompt's first headline is genuinely latest.
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    seen_normalised: list = []
    results: list[str] = []
    official_india_count = 0
    for _, _, norm, source, headline in candidates:
        if _is_duplicate(norm, seen_normalised):
            continue
        if source in _OFFICIAL_INDIA_SOURCES and official_india_count >= 2:
            continue
        seen_normalised.append(norm)
        results.append(headline)
        if source in _OFFICIAL_INDIA_SOURCES:
            official_india_count += 1
        if len(results) >= max_items:
            break
    return results
