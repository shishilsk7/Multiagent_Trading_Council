# Live USD to INR rate fetch (falls back to fixed rate if offline)
import requests

_cached_rate = None

def get_usd_inr():
    global _cached_rate
    if _cached_rate is not None:
        return _cached_rate
    try:
        r = requests.get(
            "https://api.exchangerate-api.com/v4/latest/USD",
            timeout=3  # short timeout so it never hangs
        )
        if r.status_code == 200:
            _cached_rate = r.json()["rates"]["INR"]
            return _cached_rate
    except Exception:
        pass
    return 84.0  # fallback fixed rate — never blocks


def inr(usd_amount, rate):
    """Convert USD amount to INR string."""
    return f"₹{usd_amount * rate:,.0f}"


def calculate_entry_zone(latest, sr_zone, decision):
    price      = latest["Close"]
    support    = latest["support"]
    resistance = latest["resistance"]

    if decision == "BUY":
        if sr_zone == "Near Support":
            entry_low  = round(support * 1.001, 2)
            entry_high = round(support * 1.003, 2)
            timing = "Wait for dip near support zone"
        elif sr_zone == "Near Resistance":
            entry_low  = round(resistance * 1.002, 2)
            entry_high = round(resistance * 1.005, 2)
            timing = "Wait for breakout above resistance"
        else:
            entry_low  = round(price * 0.997, 2)
            entry_high = round(price * 0.999, 2)
            timing = "Enter on slight pullback"
        stop   = round(support * 0.995, 2)
        target = round(price * 1.015, 2)

    elif decision == "SELL":
        if sr_zone == "Near Resistance":
            entry_low  = round(resistance * 0.997, 2)
            entry_high = round(resistance * 0.999, 2)
            timing = "Exit near resistance zone"
        elif sr_zone == "Near Support":
            entry_low  = round(support * 0.995, 2)
            entry_high = round(support * 0.998, 2)
            timing = "Exit if breakdown below support"
        else:
            entry_low  = round(price * 1.001, 2)
            entry_high = round(price * 1.003, 2)
            timing = "Exit on bounce"
        stop   = round(resistance * 1.005, 2)
        target = round(price * 0.985, 2)
    else:
        return None

    return {
        "entry_low":  entry_low,
        "entry_high": entry_high,
        "stop":       stop,
        "target":     target,
        "timing":     timing,
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
    max_loss        = entry_cost - stop_value
    risk_reward     = abs(expected_profit / max_loss) if max_loss != 0 else 0

    return {
        "entry_cost":      round(entry_cost, 2),
        "target_value":    round(target_value, 2),
        "stop_value":      round(stop_value, 2),
        "expected_profit": round(expected_profit, 2),
        "max_loss":        round(max_loss, 2),
        "profit_pct":      round(expected_profit / entry_cost * 100, 2),
        "loss_pct":        round(max_loss / entry_cost * 100, 2),
        "risk_reward":     round(risk_reward, 2),
    }


def levels(latest, decision, sr_zone,
           capital: float = 10_000.0, risk_percent: float = 1.0,
           usd_inr_rate: float = None):

    if decision == "WAIT":
        return None

    if usd_inr_rate is None:
        usd_inr_rate = get_usd_inr()

    price      = latest["Close"]
    entry_data = calculate_entry_zone(latest, sr_zone, decision)
    if not entry_data:
        return None

    # capital is stored in INR — convert to USD for position sizing
    capital_usd = capital / usd_inr_rate
    entry_mid   = (entry_data["entry_low"] + entry_data["entry_high"]) / 2
    position    = calculate_position_size(capital_usd, risk_percent, entry_mid, entry_data["stop"])
    if position == 0:
        return None

    outcome = calculate_expected_outcome(position, entry_mid, entry_data["target"], entry_data["stop"])
    rate    = usd_inr_rate

    return {
        "decision":          decision,
        "current_price":     round(price, 2),
        "sr_zone":           sr_zone,
        "entry_zone_low":    entry_data["entry_low"],
        "entry_zone_high":   entry_data["entry_high"],
        "stop_loss":         entry_data["stop"],
        "target_price":      entry_data["target"],
        "timing":            entry_data["timing"],

        # ── INR money fields ──────────────────────────────────────
        "capital_inr":       round(capital, 2),
        "capital_usd":       round(capital_usd, 2),
        "usd_inr_rate":      round(rate, 2),
        "risk_percent":      risk_percent,
        "max_risk_inr":      round(capital * risk_percent / 100, 2),

        "position_size":     position,   # units (BTC, shares, etc.)
        "entry_cost_inr":    round(outcome["entry_cost"] * rate, 2),
        "expected_profit_inr": round(outcome["expected_profit"] * rate, 2),
        "max_loss_inr":      round(outcome["max_loss"] * rate, 2),
        "target_value_inr":  round(outcome["target_value"] * rate, 2),

        "profit_pct":        outcome["profit_pct"],
        "loss_pct":          outcome["loss_pct"],
        "risk_reward_ratio": outcome["risk_reward"],
    }