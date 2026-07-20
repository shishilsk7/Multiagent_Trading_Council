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


_TRADINGVIEW_SYMBOLS = {
    # Crypto
    "BTC-USD": "BINANCE:BTCUSDT",
    "ETH-USD": "BINANCE:ETHUSDT",
    "SOL-USD": "BINANCE:SOLUSDT",
    "BNB-USD": "BINANCE:BNBUSDT",
    "XRP-USD": "BINANCE:XRPUSDT",
    # Commodities / ETFs
    "GC=F": "COMEX:GC1!",
    "SI=F": "COMEX:SI1!",
    "GLD": "NYSEARCA:GLD",
    "SLV": "NYSEARCA:SLV",
    # US stocks
    "NVDA": "NASDAQ:NVDA",
    "MSFT": "NASDAQ:MSFT",
    "AAPL": "NASDAQ:AAPL",
    "GOOGL": "NASDAQ:GOOGL",
    "META": "NASDAQ:META",
    "AMZN": "NASDAQ:AMZN",
    "TSLA": "NASDAQ:TSLA",
    "PLTR": "NYSE:PLTR",
    "ARM": "NASDAQ:ARM",
    "CRWD": "NASDAQ:CRWD",
    "MSTR": "NASDAQ:MSTR",
    "JPM": "NYSE:JPM",
    "GS": "NYSE:GS",
    # India stocks
    "RELIANCE.NS": "NSE:RELIANCE",
    "TCS.NS": "NSE:TCS",
    "HDFCBANK.NS": "NSE:HDFCBANK",
    "INFY.NS": "NSE:INFY",
    "ICICIBANK.NS": "NSE:ICICIBANK",
    "HINDUNILVR.NS": "NSE:HINDUNILVR",
    "ITC.NS": "NSE:ITC",
    "SBIN.NS": "NSE:SBIN",
    "BHARTIARTL.NS": "NSE:BHARTIARTL",
    "KOTAKBANK.NS": "NSE:KOTAKBANK",
    "TATAMOTORS.NS": "NSE:TATAMOTORS",
    "WIPRO.NS": "NSE:WIPRO",
    "ADANIENT.NS": "NSE:ADANIENT",
    "BAJFINANCE.NS": "NSE:BAJFINANCE",
    "ZOMATO.NS": "NSE:ZOMATO",
    "NYKAA.NS": "NSE:NYKAA",
    "PAYTM.NS": "NSE:PAYTM",
    "^NSEI": "NSE:NIFTY",
    "^BSESN": "BSE:SENSEX",
}


def get_tradingview_symbol(ticker):
    if ticker in _TRADINGVIEW_SYMBOLS:
        return _TRADINGVIEW_SYMBOLS[ticker]

    # Safe fallback parsing for unmapped tickers
    t = ticker.upper()
    if t.endswith(".NS"):
        return f"NSE:{t[:-3]}"
    if t.endswith(".BO"):
        return f"BSE:{t[:-3]}"
    if t.endswith("-USD"):
        base = t[:-4]
        return f"BINANCE:{base}USDT"
    if t.startswith("^"):
        return t[1:]

    return ticker