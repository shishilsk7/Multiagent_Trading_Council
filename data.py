"""
news.py — Relevant, deduplicated headline fetcher.

Fixes from v2:
- Relevance scoring: headlines are ranked by how many asset-specific
  keywords they contain. Unrelated articles are filtered out entirely.
- Deduplication: same story from multiple outlets gets collapsed into one
  using normalised title similarity (word overlap ratio).
- Source tagging: each headline carries its outlet name so the LLM can
  weight reputable sources vs tabloids.
- Recency window still enforced (default 24h) — stale articles excluded.
- Graceful fallback: returns [] on any network/parse error (never raises).
"""

import re
import time
from datetime import datetime, timedelta, timezone
import feedparser


# ── Keyword sets per asset class ───────────────────────────────────
# Any headline containing at least one of these passes the relevance gate.
# Keys map to what get_news_query() returns (loose match on the query words).

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


def _build_keyword_set(query: str) -> set[str]:
    """
    Build a relevance keyword set from the news query string.
    We extract the company/asset name tokens and supplement with class keywords.
    """
    query_lower = query.lower()
    tokens = set(re.findall(r'\w+', query_lower))

    # Remove generic filler words that appear in every query
    filler = {"stock", "price", "today", "india", "nse", "bse", "crypto"}
    tokens -= filler

    # Merge with class-specific keywords
    if any(c in query_lower for c in ["btc", "eth", "sol", "bnb", "xrp", "crypto"]):
        tokens |= _CRYPTO_KEYWORDS
    if any(c in query_lower for c in ["gold", "silver", "gld", "slv"]):
        tokens |= _GOLD_KEYWORDS
    if any(c in query_lower for c in ["nse", "bse", "india"]):
        tokens |= _INDIA_KEYWORDS
    if any(c in query_lower for c in ["nvda", "aapl", "msft", "googl", "meta", "amzn", "tsla"]):
        tokens |= _US_TECH_KEYWORDS

    return tokens


def _relevance_score(title: str, keywords: set[str]) -> int:
    """
    Count how many keywords appear in the headline title.
    Returns 0 for completely unrelated articles.
    """
    title_words = set(re.findall(r'\w+', title.lower()))
    return len(title_words & keywords)


def _normalise_title(title: str) -> str:
    """Strip punctuation, lowercase, remove source attribution."""
    # Google News appends " - Source Name" — remove it
    title = re.sub(r'\s*[-–]\s*[^-–]{3,40}$', '', title)
    return re.sub(r'[^\w\s]', '', title.lower()).strip()


def _is_duplicate(title: str, seen: list[str], threshold: float = 0.65) -> bool:
    """
    Check if this title is substantially similar to any already-seen title.
    Uses word-overlap Jaccard similarity.
    """
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
    """Format a feed entry as 'Headline (Source, timestamp)'."""
    title = entry.title.strip()

    # Extract source from Google News title format "Story — Source"
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

    # Remove source from title for clean display
    clean_title = re.sub(r'\s*[-–]\s*[^-–]{3,40}$', '', title).strip()
    return f"{clean_title} ({source}, {stamp})"


def fetch_news(
    query: str = "bitcoin crypto",
    max_items: int = 6,
    max_age_hours: int = 24,
    min_relevance: int = 1,
) -> list[str]:
    """
    Fetch relevant, deduplicated headlines for a given query.

    Args:
        query:         Search query (from get_news_query)
        max_items:     Maximum number of headlines to return
        max_age_hours: Only include headlines this fresh
        min_relevance: Minimum keyword hits required (1 = at least 1 match)

    Returns:
        List of formatted headline strings, empty list on failure.
    """
    feed_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"

    try:
        feed = feedparser.parse(feed_url, request_headers={"User-Agent": "Mozilla/5.0"})
    except Exception as e:
        print(f"news.py: feedparser failed for query '{query}': {e}")
        return []

    if not feed.entries:
        return []

    keywords = _build_keyword_set(query)
    seen_normalised: list[str] = []
    results: list[tuple[int, str]] = []  # (relevance_score, formatted_headline)

    for entry in feed.entries:
        if len(results) >= max_items * 3:  # fetch extra for dedup/filter
            break

        title = getattr(entry, "title", "").strip()
        if not title or len(title) < 10:
            continue

        # Recency gate
        if not _entry_is_fresh(entry, max_age_hours):
            continue

        # Relevance gate
        score = _relevance_score(title, keywords)
        if score < min_relevance:
            continue

        # Deduplication gate
        norm = _normalise_title(title)
        if _is_duplicate(norm, seen_normalised):
            continue

        seen_normalised.append(norm)
        results.append((score, _format_entry(entry)))

    # Sort by relevance (highest first), return top N
    results.sort(key=lambda x: x[0], reverse=True)
    return [headline for _, headline in results[:max_items]]
