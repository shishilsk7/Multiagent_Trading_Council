"""
trade_levels.py — ATR-aware, asset-class-adaptive trade sizing
- Targets and stops are based on ATR, not fixed percentages
- Entry zones adapted to volatility
- Full INR + USD output
- Risk/reward enforced minimum
"""

import requests
import time
import math

_cached_rate = None
_cached_rate_ts = 0.0
_RATE_TTL = 3600  # refresh every 1 hour


def get_usd_inr():
    global _cached_rate, _cached_rate_ts
    if _cached_rate is not None and (time.time() - _cached_rate_ts) < _RATE_TTL:
        return _cached_rate
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=3)
        if r.status_code == 200:
            _cached_rate = r.json()["rates"]["INR"]
            _cached_rate_ts = time.time()
            return _cached_rate
    except Exception:
        pass
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=3)
        if r.status_code == 200:
            _cached_rate = r.json()["rates"]["INR"]
            _cached_rate_ts = time.time()
            return _cached_rate
    except Exception:
        pass
    return _cached_rate if _cached_rate is not None else 84.0


def inr(usd_amount, rate):
    return f"₹{usd_amount * rate:,.0f}"


def _asset_atr_multiplier(ticker: str):
    """
    Returns (stop_atr_mult, target_atr_mult) based on asset class.
    Crypto is more volatile — needs wider stops but also bigger targets.
    Indian stocks are tighter.
    """
    t = ticker.upper()
    if any(x in t for x in ["BTC", "ETH", "SOL", "BNB", "XRP"]):
        return 1.5, 3.0   # crypto: 1.5x ATR stop, 3x ATR target → R:R = 2
    elif t.endswith(".NS") or t.endswith(".BO"):
        return 1.2, 2.4   # Indian stocks: tighter
    elif any(x in t for x in ["GC=F", "SI=F", "GLD", "SLV"]):
        return 1.3, 2.6   # commodities
    else:
        return 1.2, 2.4   # US stocks: standard


def _timeframe_profile(interval: str):
    interval = (interval or "").lower()
    profiles = {
        "1m": {"entry": 0.10, "stop": 0.80, "target": 0.90, "min_rr": 1.2},
        "5m": {"entry": 0.14, "stop": 0.90, "target": 0.95, "min_rr": 1.25},
        "15m": {"entry": 0.18, "stop": 0.95, "target": 1.00, "min_rr": 1.35},
        "1h": {"entry": 0.28, "stop": 1.00, "target": 1.00, "min_rr": 1.5},
        "1d": {"entry": 0.35, "stop": 1.10, "target": 1.10, "min_rr": 1.5},
    }
    return profiles.get(interval, {"entry": 0.25, "stop": 1.0, "target": 1.0, "min_rr": 1.4})


def _fib_confluence(latest, decision):
    fib_500 = latest.get("fib_500")
    fib_618 = latest.get("fib_618")
    if fib_500 is None or fib_618 is None:
        return None, None
    try:
        f500 = float(fib_500)
        f618 = float(fib_618)
    except (ValueError, TypeError):
        return None, None

    if f500 == 0 or f618 == 0 or str(f500).lower() == "nan" or str(f618).lower() == "nan":
        return None, None

    price = float(latest["Close"])
    min_fib = min(f500, f618)
    max_fib = max(f500, f618)
    trend_up = float(latest.get("fib_trend", 1)) >= 0

    # Zone check
    if not (min_fib <= price <= max_fib):
        return None, None

    if decision == "BUY":
        anchor = min_fib
        label = "Fib 0.5-0.618 pullback zone" if trend_up else "Counter-trend Fib 0.5-0.618 zone support"
        return anchor, label

    if decision == "SELL":
        anchor = max_fib
        label = "Fib 0.5-0.618 retracement zone" if not trend_up else "Counter-trend Fib 0.5-0.618 zone resistance"
        return anchor, label

    return None, None


def calculate_entry_zone(latest, sr_zone, decision, ticker="", interval=""):
    price      = float(latest["Close"])
    support    = float(latest["support"])
    resistance = float(latest["resistance"])
    atr        = float(latest.get("atr", price * 0.01))

    stop_mult, target_mult = _asset_atr_multiplier(ticker)
    tf = _timeframe_profile(interval)

    # Entry zone scales with timeframe; shorter intervals need tighter pullbacks.
    entry_buffer = atr * tf["entry"]
    fib_anchor, fib_label = _fib_confluence(latest, decision)

    if decision == "BUY":
        anchor = fib_anchor if fib_anchor and fib_anchor < price else price
        entry_low  = round(min(price, anchor) - entry_buffer, 4)
        entry_high = round(anchor + entry_buffer * 0.5, 4)
        stop       = round(anchor - (atr * stop_mult * tf["stop"]), 4)
        target     = round(anchor + (atr * target_mult * tf["target"]), 4)

        # Respect S/R: don't place stop above support if near it
        if sr_zone == "Near Support" and support < price:
            stop = round(min(stop, support * 0.997), 4)
        if fib_anchor and fib_anchor < price:
            entry_low = round(min(entry_low, fib_anchor - entry_buffer * 0.5), 4)
            entry_high = round(max(entry_high, fib_anchor + entry_buffer * 0.5), 4)

        if sr_zone == "Near Support":
            timing = f"Buy near support zone (${support:,.2f}). Dip to entry low is ideal."
        elif fib_anchor:
            timing = f"Buy on Fibonacci pullback near ${fib_anchor:,.2f}. Wait for confirmation candle."
        elif sr_zone == "Near Resistance":
            timing = f"Wait for breakout above resistance (${resistance:,.2f}) before entering."
        elif sr_zone == "Below BB Lower (Oversold)":
            timing = "Oversold bounce setup. Enter on first green candle."
        else:
            timing = "Enter on slight pullback or current price."

    elif decision == "SELL":
        anchor = fib_anchor if fib_anchor and fib_anchor > price else price
        entry_low  = round(anchor - entry_buffer * 0.5, 4)
        entry_high = round(max(price, anchor) + entry_buffer, 4)
        stop       = round(anchor + (atr * stop_mult * tf["stop"]), 4)
        target     = round(anchor - (atr * target_mult * tf["target"]), 4)

        # Respect S/R
        if sr_zone == "Near Resistance" and resistance > price:
            stop = round(max(stop, resistance * 1.003), 4)
        if fib_anchor and fib_anchor > price:
            entry_low = round(min(entry_low, fib_anchor - entry_buffer * 0.5), 4)
            entry_high = round(max(entry_high, fib_anchor + entry_buffer * 0.5), 4)

        if sr_zone == "Near Resistance":
            timing = f"Sell near resistance zone (${resistance:,.2f}). Ideal short entry."
        elif fib_anchor:
            timing = f"Sell on Fibonacci retracement near ${fib_anchor:,.2f}. Wait for rejection candle."
        elif sr_zone == "Near Support":
            timing = f"Breakdown below support (${support:,.2f}) confirms sell. Wait for close below."
        elif sr_zone == "Above BB Upper (Overbought)":
            timing = "Overbought reversal setup. Enter on first red candle."
        else:
            timing = "Sell at current price or on bounce."
    else:
        return None

    # Safety: ensure stop and target make sense relative to entry bounds
    if decision == "BUY" and stop >= entry_low:
        stop = round(entry_low * 0.985, 4)
    if decision == "BUY" and target <= entry_high:
        target = round(entry_high * 1.02, 4)
    if decision == "SELL" and stop <= entry_high:
        stop = round(entry_high * 1.015, 4)
    if decision == "SELL" and target >= entry_low:
        target = round(entry_low * 0.98, 4)

    return {
        "entry_low":  entry_low,
        "entry_high": entry_high,
        "stop":       stop,
        "target":     target,
        "timing":     timing,
        "atr_used":   round(atr, 4),
        "fib_anchor": round(fib_anchor, 4) if fib_anchor else None,
        "fib_label":  fib_label,
    }


def calculate_position_size(capital_usd, risk_percent, entry, stop, ticker=""):
    risk_amount = capital_usd * (risk_percent / 100)
    price_risk  = abs(entry - stop)
    if price_risk == 0:
        return 0
    raw_position = risk_amount / price_risk

    # Check if crypto
    from stocks import UNIVERSE
    is_crypto = False
    if ticker in UNIVERSE:
        is_crypto = UNIVERSE[ticker][1] == "Crypto"
    else:
        is_crypto = any(x in ticker.upper() for x in ["BTC", "ETH", "SOL", "BNB", "XRP"])

    if is_crypto:
        return round(raw_position, 6)
    else:
        return math.floor(raw_position)


def calculate_expected_outcome(position, entry, target, stop):
    entry_cost      = position * entry
    target_value    = position * target
    stop_value      = position * stop
    expected_profit = target_value - entry_cost
    max_loss        = abs(entry_cost - stop_value)
    risk_reward     = abs(expected_profit / max_loss) if max_loss != 0 else 0

    return {
        "entry_cost":      round(entry_cost, 2),
        "target_value":    round(target_value, 2),
        "stop_value":      round(stop_value, 2),
        "expected_profit": round(expected_profit, 2),
        "max_loss":        round(max_loss, 2),
        "profit_pct":      round(expected_profit / entry_cost * 100, 2) if entry_cost else 0,
        "loss_pct":        round(max_loss / entry_cost * 100, 2) if entry_cost else 0,
        "risk_reward":     round(risk_reward, 2),
    }


def get_tif_for_asset(ticker: str, interval: str) -> dict:
    """
    Returns the correct Time-In-Force and order-type metadata for TradingView
    based on asset class and timeframe.

    TradingView rules:
    - NSE/BSE (India): only DAY orders supported via most connected brokers
    - Crypto (Binance/exchange): GTC is valid; also supports DAY
    - US stocks/ETFs: DAY or GTC (GTC preferred for swing, DAY for intraday)
    - Futures (GC=F, SI=F): GTC; futures expire so GTD is risky — use GTC
    - For 1m/5m intervals (intraday scalp), always use DAY regardless of asset
    """
    t = ticker.upper()
    intraday = interval in ("1m", "5m", "15m")

    if t.endswith(".NS") or t.endswith(".BO") or t in ("^NSEI", "^BSESN"):
        # NSE/BSE: brokers (Zerodha, Fyers) only support DAY on TradingView
        return {
            "tif": "DAY",
            "tif_note": "NSE/BSE only supports DAY orders. Order expires at market close (~15:30 IST). Re-enter next session if unfilled.",
            "order_type": "LIMIT",
            "expiry_note": "Expires: today 15:30 IST",
        }
    elif any(x in t for x in ["BTC", "ETH", "SOL", "BNB", "XRP"]):
        # Crypto: 24/7 market — GTC makes sense; DAY also fine for intraday
        tif = "DAY" if intraday else "GTC"
        return {
            "tif": tif,
            "tif_note": "Crypto trades 24/7. GTC keeps your limit live until filled or you cancel.",
            "order_type": "LIMIT",
            "expiry_note": "GTC: no expiry (cancel manually)" if tif == "GTC" else "DAY: expires at midnight UTC",
        }
    elif any(x in t for x in ["GC=F", "SI=F"]):
        # Futures: GTC is safest; avoid GTD which requires a calendar date
        return {
            "tif": "GTC",
            "tif_note": "Futures: GTC recommended. Be aware of contract rollover/expiry dates.",
            "order_type": "LIMIT",
            "expiry_note": "GTC: active until filled or cancelled (watch contract expiry)",
        }
    else:
        # US equities / ETFs
        tif = "DAY" if intraday else "GTC"
        return {
            "tif": tif,
            "tif_note": "US equities: GTC for swing trades (active across sessions), DAY for intraday.",
            "order_type": "LIMIT",
            "expiry_note": "GTC: active until filled or cancelled" if tif == "GTC" else "DAY: expires at market close 16:00 ET",
        }


def validate_trade_setup(decision: str, confidence: int, trade: dict) -> tuple[bool, list[str]]:
    """
    Validates whether the current setup is actionable.
    Returns (is_valid: bool, errors: list[str])
    """
    errors = []

    if decision not in ("BUY", "SELL"):
        errors.append(f"Signal is {decision}, not BUY or SELL — no trade to open.")

    if confidence < 50:
        errors.append(f"Confidence is {confidence}% (minimum 50% required).")
    elif confidence < 60:
        errors.append(f"Confidence is {confidence}% — low confidence, trade at your own risk.")

    if trade is None:
        errors.append("No trade plan computed — run analysis first.")
        return False, errors

    rr = trade.get("risk_reward_ratio", 0)
    if rr < 1.0:
        errors.append(f"R:R is 1:{rr:.2f} — below 1:1, not worth trading.")
    elif rr < 1.2:
        errors.append(f"R:R is 1:{rr:.2f} — marginal, consider skipping.")

    if trade.get("is_hypothetical"):
        errors.append("Setup is HYPOTHETICAL (Council says WAIT) — you are overriding the signal.")

    is_valid = decision in ("BUY", "SELL") and trade is not None and rr >= 1.0
    return is_valid, errors


def levels(latest, decision, sr_zone_label,
           capital: float = 10_000.0, risk_percent: float = 1.0,
           ticker: str = "", interval: str = "", usd_inr_rate: float = None):

    if usd_inr_rate is None:
        usd_inr_rate = get_usd_inr()

    price      = float(latest["Close"])
    entry_data = calculate_entry_zone(latest, sr_zone_label, decision, ticker=ticker, interval=interval)
    if not entry_data:
        return None

    # Capital in INR → convert to USD for sizing
    capital_usd = capital / usd_inr_rate
    entry_mid   = (entry_data["entry_low"] + entry_data["entry_high"]) / 2
    position    = calculate_position_size(capital_usd, risk_percent, entry_mid, entry_data["stop"], ticker=ticker)
    price_risk  = abs(entry_mid - entry_data["stop"])
    position_raw = round((capital_usd * (risk_percent / 100)) / price_risk, 6) if price_risk != 0 else 0
    if position == 0:
        return None

    outcome = calculate_expected_outcome(
        position, entry_mid, entry_data["target"], entry_data["stop"]
    )
    rate = usd_inr_rate

    rr = outcome["risk_reward"]
    min_rr = _timeframe_profile(interval)["min_rr"]
    if rr < 1.0:
        rr_verdict = "❌ Poor R:R — skip this trade"
        rr_color   = "red"
    elif rr < min_rr:
        rr_verdict = "⚠️ Below average R:R — trade small or skip"
        rr_color   = "orange"
    elif rr < 2.0:
        rr_verdict = "✅ Acceptable R:R — proceed with normal size"
        rr_color   = "yellow"
    else:
        rr_verdict = "🟢 Good R:R — solid setup"
        rr_color   = "green"

    return {
        "decision":            decision,
        "current_price":       round(price, 4),
        "sr_zone":             sr_zone_label,
        "entry_zone_low":      entry_data["entry_low"],
        "entry_zone_high":     entry_data["entry_high"],
        "stop_loss":           entry_data["stop"],
        "target_price":        entry_data["target"],
        "timing":              entry_data["timing"],
        "atr_used":            entry_data["atr_used"],
        "fib_anchor":          entry_data["fib_anchor"],
        "fib_label":           entry_data["fib_label"],
        "timeframe":           interval or "1h",

        # INR fields
        "capital_inr":         round(capital, 2),
        "capital_usd":         round(capital_usd, 2),
        "usd_inr_rate":        round(rate, 2),
        "risk_percent":        risk_percent,
        "max_risk_inr":        round(capital * risk_percent / 100, 2),

        "position_size_raw":   position_raw,
        "position_size":       position,
        "entry_cost_inr":      round(outcome["entry_cost"] * rate, 2),
        "expected_profit_inr": round(outcome["expected_profit"] * rate, 2),
        "max_loss_inr":        round(outcome["max_loss"] * rate, 2),
        "target_value_inr":    round(outcome["target_value"] * rate, 2),

        "profit_pct":          outcome["profit_pct"],
        "loss_pct":            outcome["loss_pct"],
        "risk_reward_ratio":   rr,
        "rr_verdict":          rr_verdict,
        "rr_color":            rr_color,
    }
