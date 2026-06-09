"""
trade_levels.py — ATR-aware, asset-class-adaptive trade sizing
- Targets and stops are based on ATR, not fixed percentages
- Entry zones adapted to volatility
- Full INR + USD output
- Risk/reward enforced minimum
"""

import requests
import time

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


def calculate_entry_zone(latest, sr_zone, decision, ticker=""):
    price      = float(latest["Close"])
    support    = float(latest["support"])
    resistance = float(latest["resistance"])
    atr        = float(latest.get("atr", price * 0.01))

    stop_mult, target_mult = _asset_atr_multiplier(ticker)

    # Entry zone = ±0.5 ATR from current price (tight but realistic)
    entry_buffer = atr * 0.3

    if decision == "BUY":
        entry_low  = round(price - entry_buffer, 4)
        entry_high = round(price + entry_buffer * 0.5, 4)
        stop       = round(price - (atr * stop_mult), 4)
        target     = round(price + (atr * target_mult), 4)

        # Respect S/R: don't place stop above support if near it
        if sr_zone == "Near Support" and support < price:
            stop = round(min(stop, support * 0.997), 4)

        if sr_zone == "Near Support":
            timing = f"Buy near support zone (${support:,.2f}). Dip to entry low is ideal."
        elif sr_zone == "Near Resistance":
            timing = f"Wait for breakout above resistance (${resistance:,.2f}) before entering."
        elif sr_zone == "Below BB Lower (Oversold)":
            timing = "Oversold bounce setup. Enter on first green candle."
        else:
            timing = "Enter on slight pullback or current price."

    elif decision == "SELL":
        entry_low  = round(price - entry_buffer * 0.5, 4)
        entry_high = round(price + entry_buffer, 4)
        stop       = round(price + (atr * stop_mult), 4)
        target     = round(price - (atr * target_mult), 4)

        # Respect S/R
        if sr_zone == "Near Resistance" and resistance > price:
            stop = round(max(stop, resistance * 1.003), 4)

        if sr_zone == "Near Resistance":
            timing = f"Sell near resistance zone (${resistance:,.2f}). Ideal short entry."
        elif sr_zone == "Near Support":
            timing = f"Breakdown below support (${support:,.2f}) confirms sell. Wait for close below."
        elif sr_zone == "Above BB Upper (Overbought)":
            timing = "Overbought reversal setup. Enter on first red candle."
        else:
            timing = "Sell at current price or on bounce."
    else:
        return None

    # Safety: ensure stop and target make sense
    if decision == "BUY" and stop >= price:
        stop = round(price * 0.985, 4)
    if decision == "BUY" and target <= price:
        target = round(price * 1.02, 4)
    if decision == "SELL" and stop <= price:
        stop = round(price * 1.015, 4)
    if decision == "SELL" and target >= price:
        target = round(price * 0.98, 4)

    return {
        "entry_low":  entry_low,
        "entry_high": entry_high,
        "stop":       stop,
        "target":     target,
        "timing":     timing,
        "atr_used":   round(atr, 4),
    }


def calculate_position_size(capital_usd, risk_percent, entry, stop):
    risk_amount = capital_usd * (risk_percent / 100)
    price_risk  = abs(entry - stop)
    if price_risk == 0:
        return 0
    return round(risk_amount / price_risk, 6)


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


def levels(latest, decision, sr_zone_label,
           capital: float = 10_000.0, risk_percent: float = 1.0,
           ticker: str = "", usd_inr_rate: float = None):

    if decision == "WAIT":
        return None

    if usd_inr_rate is None:
        usd_inr_rate = get_usd_inr()

    price      = float(latest["Close"])
    entry_data = calculate_entry_zone(latest, sr_zone_label, decision, ticker=ticker)
    if not entry_data:
        return None

    # Capital in INR → convert to USD for sizing
    capital_usd = capital / usd_inr_rate
    entry_mid   = (entry_data["entry_low"] + entry_data["entry_high"]) / 2
    position    = calculate_position_size(capital_usd, risk_percent, entry_mid, entry_data["stop"])
    if position == 0:
        return None

    outcome = calculate_expected_outcome(
        position, entry_mid, entry_data["target"], entry_data["stop"]
    )
    rate = usd_inr_rate

    rr = outcome["risk_reward"]
    if rr < 1.0:
        rr_verdict = "❌ Poor R:R — skip this trade"
        rr_color   = "red"
    elif rr < 1.5:
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

        # INR fields
        "capital_inr":         round(capital, 2),
        "capital_usd":         round(capital_usd, 2),
        "usd_inr_rate":        round(rate, 2),
        "risk_percent":        risk_percent,
        "max_risk_inr":        round(capital * risk_percent / 100, 2),

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
