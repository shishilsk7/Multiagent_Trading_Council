"""
Stock / crypto / commodity universe — US + India + Gold/Silver
"""

UNIVERSE = {
    # ── Crypto ──────────────────────────────────────────────────────
    "BTC-USD":  ("Bitcoin",          "Crypto"),
    "ETH-USD":  ("Ethereum",         "Crypto"),
    "SOL-USD":  ("Solana",           "Crypto"),
    "BNB-USD":  ("BNB",              "Crypto"),
    "XRP-USD":  ("XRP",              "Crypto"),

    # ── Commodities ──────────────────────────────────────────────────
    "GC=F":     ("Gold Futures",     "Commodities"),
    "SI=F":     ("Silver Futures",   "Commodities"),
    "GLD":      ("SPDR Gold ETF",    "Commodities"),
    "SLV":      ("iShares Silver ETF","Commodities"),

    # ── US Tech / AI ─────────────────────────────────────────────────
    "NVDA":     ("NVIDIA",           "US Tech/AI"),
    "MSFT":     ("Microsoft",        "US Tech/AI"),
    "AAPL":     ("Apple",            "US Tech/AI"),
    "GOOGL":    ("Alphabet",         "US Tech/AI"),
    "META":     ("Meta",             "US Tech/AI"),
    "AMZN":     ("Amazon",           "US Tech/AI"),
    "TSLA":     ("Tesla",            "US Tech/AI"),

    # ── US Growth ────────────────────────────────────────────────────
    "PLTR":     ("Palantir",         "US Growth"),
    "ARM":      ("ARM Holdings",     "US Growth"),
    "CRWD":     ("CrowdStrike",      "US Growth"),
    "MSTR":     ("MicroStrategy",    "US Growth"),

    # ── US Finance ───────────────────────────────────────────────────
    "JPM":      ("JPMorgan",         "US Finance"),
    "GS":       ("Goldman Sachs",    "US Finance"),

    # ── India Large Cap ──────────────────────────────────────────────
    "RELIANCE.NS": ("Reliance Industries", "India Large Cap"),
    "TCS.NS":      ("TCS",                 "India Large Cap"),
    "HDFCBANK.NS": ("HDFC Bank",           "India Large Cap"),
    "INFY.NS":     ("Infosys",             "India Large Cap"),
    "ICICIBANK.NS":("ICICI Bank",          "India Large Cap"),
    "HINDUNILVR.NS":("Hindustan Unilever", "India Large Cap"),
    "ITC.NS":      ("ITC",                 "India Large Cap"),
    "SBIN.NS":     ("State Bank of India", "India Large Cap"),
    "BHARTIARTL.NS":("Bharti Airtel",      "India Large Cap"),
    "KOTAKBANK.NS": ("Kotak Mahindra Bank","India Large Cap"),

    # ── India Mid Cap / Growth ───────────────────────────────────────
    "TATAMOTORS.NS":("Tata Motors",        "India Growth"),
    "WIPRO.NS":     ("Wipro",              "India Growth"),
    "ADANIENT.NS":  ("Adani Enterprises",  "India Growth"),
    "BAJFINANCE.NS":("Bajaj Finance",      "India Growth"),
    "ZOMATO.NS":    ("Zomato",             "India Growth"),
    "NYKAA.NS":     ("Nykaa",              "India Growth"),
    "PAYTM.NS":     ("Paytm",              "India Growth"),

    # ── India Indices (ETFs) ─────────────────────────────────────────
    "^NSEI":    ("Nifty 50 Index",    "India Index"),
    "^BSESN":   ("Sensex Index",      "India Index"),
}

CATEGORIES = sorted(set(v[1] for v in UNIVERSE.values()))

# Which assets are Indian (priced in ₹ natively)
INDIAN_TICKERS = {t for t, (_, cat) in UNIVERSE.items() if "India" in cat}


def ticker_label(ticker):
    name, cat = UNIVERSE.get(ticker, (ticker, ""))
    return f"{ticker} – {name} ({cat})"


def get_news_query(ticker):
    name, cat = UNIVERSE.get(ticker, (ticker, ""))
    if "India" in cat:
        return f"{name} NSE BSE India stock"
    elif cat == "Crypto":
        return f"{name} {ticker.replace('-USD','')} crypto price"
    elif cat == "Commodities":
        return f"{name} price today"
    else:
        return f"{name} {ticker} stock"


def is_indian(ticker):
    return ticker in INDIAN_TICKERS


def currency_label(ticker):
    """Returns ₹ for Indian stocks, $ for everything else."""
    return "₹" if is_indian(ticker) else "$"