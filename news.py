import feedparser
from datetime import datetime, timedelta, timezone
import time


def _entry_is_fresh(entry, max_age_hours: int) -> bool:
    published = getattr(entry, "published_parsed", None)
    if not published:
        return False
    published_dt = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
    return datetime.now(timezone.utc) - published_dt <= timedelta(hours=max_age_hours)


def fetch_news(query: str = "bitcoin crypto", max_items: int = 6, max_age_hours: int = 24):
    """
    Fetch recent headlines for any query (ticker name, company, etc.)
    """
    feed_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}"
    try:
        feed = feedparser.parse(feed_url)
    except Exception:
        return []

    fresh = []
    for entry in feed.entries:
        if _entry_is_fresh(entry, max_age_hours):
            published = getattr(entry, "published_parsed", None)
            if published:
                dt = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
                stamp = dt.strftime("%Y-%m-%d %H:%M UTC")
                fresh.append(f"{entry.title} ({stamp})")
            else:
                fresh.append(entry.title)
        if len(fresh) >= max_items:
            break

    return fresh
