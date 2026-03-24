"""
Stock / crypto universe — top picks by category.
Each entry: (ticker, display_name, category)
"""

UNIVERSE = {
    # ── Crypto ──────────────────────────────────────────────────
    "BTC-USD":  ("Bitcoin",       "Crypto"),
    "ETH-USD":  ("Ethereum",      "Crypto"),
    "SOL-USD":  ("Solana",        "Crypto"),
    "BNB-USD":  ("BNB",           "Crypto"),
    "XRP-USD":  ("XRP",           "Crypto"),

    # ── US Tech / AI ─────────────────────────────────────────────
    "NVDA":     ("NVIDIA",        "Tech/AI"),
    "MSFT":     ("Microsoft",     "Tech/AI"),
    "AAPL":     ("Apple",         "Tech/AI"),
    "GOOGL":    ("Alphabet",      "Tech/AI"),
    "META":     ("Meta",          "Tech/AI"),
    "AMZN":     ("Amazon",        "Tech/AI"),
    "TSLA":     ("Tesla",         "Tech/AI"),

    # ── High-Growth / Momentum ────────────────────────────────────
    "PLTR":     ("Palantir",      "Growth"),
    "ARM":      ("ARM Holdings",  "Growth"),
    "SMCI":     ("Super Micro",   "Growth"),
    "CRWD":     ("CrowdStrike",   "Growth"),
    "MSTR":     ("MicroStrategy", "Growth"),

    # ── Finance ───────────────────────────────────────────────────
    "JPM":      ("JPMorgan",      "Finance"),
    "GS":       ("Goldman Sachs", "Finance"),
}

CATEGORIES = sorted(set(v[1] for v in UNIVERSE.values()))


def ticker_label(ticker):
    """Returns 'NVDA – NVIDIA (Tech/AI)'"""
    name, cat = UNIVERSE.get(ticker, (ticker, ""))
    return f"{ticker} – {name} ({cat})"


def get_news_query(ticker):
    """Better news search query per ticker."""
    name, _ = UNIVERSE.get(ticker, (ticker, ""))
    return f"{name} {ticker} stock price"
