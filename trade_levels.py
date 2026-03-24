def calculate_entry_zone(latest, sr_zone, decision):
    """Calculate optimal entry zone based on support/resistance"""
    price = latest["Close"]
    support = latest["support"]
    resistance = latest["resistance"]
    
    if decision == "BUY":
        if sr_zone == "Near Support":
            # Buy at support with small buffer
            entry_low = round(support * 1.001, 2)
            entry_high = round(support * 1.003, 2)
            timing = "Wait for dip near support zone"
        elif sr_zone == "Near Resistance":
            # Breakout buy - wait for confirmation
            entry_low = round(resistance * 1.002, 2)
            entry_high = round(resistance * 1.005, 2)
            timing = "Wait for breakout above resistance"
        else:
            # Middle zone - conservative entry
            entry_low = round(price * 0.997, 2)
            entry_high = round(price * 0.999, 2)
            timing = "Enter on slight pullback"
        
        stop = round(support * 0.995, 2)  # Stop below support
        target = round(price * 1.015, 2)   # 1.5% target
        
    elif decision == "SELL":
        if sr_zone == "Near Resistance":
            # Sell at resistance with buffer
            entry_low = round(resistance * 0.997, 2)
            entry_high = round(resistance * 0.999, 2)
            timing = "Exit near resistance zone"
        elif sr_zone == "Near Support":
            # Breakdown sell - wait for confirmation
            entry_low = round(support * 0.995, 2)
            entry_high = round(support * 0.998, 2)
            timing = "Exit if breakdown below support"
        else:
            # Middle zone - conservative exit
            entry_low = round(price * 1.001, 2)
            entry_high = round(price * 1.003, 2)
            timing = "Exit on bounce"
        
        stop = round(resistance * 1.005, 2)  # Stop above resistance
        target = round(price * 0.985, 2)      # 1.5% target
    else:
        return None
    
    return {
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop": stop,
        "target": target,
        "timing": timing
    }


def calculate_position_size(capital, risk_percent, entry, stop):
    """Calculate position size based on capital and risk tolerance"""
    risk_amount = capital * (risk_percent / 100)
    price_risk = abs(entry - stop)
    
    if price_risk == 0:
        return 0
    
    # Position size in BTC
    position = risk_amount / price_risk
    return round(position, 6)


def calculate_expected_outcome(position, entry, target, stop):
    """Calculate expected profit/loss"""
    entry_cost = position * entry
    target_value = position * target
    stop_value = position * stop
    
    expected_profit = target_value - entry_cost
    max_loss = entry_cost - stop_value
    
    risk_reward = abs(expected_profit / max_loss) if max_loss != 0 else 0
    
    return {
        "entry_cost": round(entry_cost, 2),
        "target_value": round(target_value, 2),
        "stop_value": round(stop_value, 2),
        "expected_profit": round(expected_profit, 2),
        "max_loss": round(max_loss, 2),
        "profit_pct": round((expected_profit / entry_cost * 100), 2),
        "loss_pct": round((max_loss / entry_cost * 100), 2),
        "risk_reward": round(risk_reward, 2)
    }


def levels(latest, decision, sr_zone, capital: float = 10000.0, risk_percent: float = 1.0):
    """Generate complete trading plan with entry zones, sizing, and outcomes"""
    if decision == "WAIT":
        return None
    
    price = latest["Close"]
    
    # Layer 1: Entry timing logic
    entry_data = calculate_entry_zone(latest, sr_zone, decision)
    if not entry_data:
        return None
    
    # Use mid-point of entry zone for calculations
    entry_mid = (entry_data["entry_low"] + entry_data["entry_high"]) / 2
    
    # Layer 2: Position sizing
    position = calculate_position_size(capital, risk_percent, entry_mid, entry_data["stop"])
    
    if position == 0:
        return None
    
    # Layer 3: Expected outcomes
    outcome = calculate_expected_outcome(position, entry_mid, entry_data["target"], entry_data["stop"])
    
    return {
        "decision": decision,
        "current_price": round(price, 2),
        "sr_zone": sr_zone,
        "entry_zone_low": entry_data["entry_low"],
        "entry_zone_high": entry_data["entry_high"],
        "stop_loss": entry_data["stop"],
        "target_price": entry_data["target"],
        "timing": entry_data["timing"],
        "capital_allocated": capital,
        "risk_percent": risk_percent,
        "position_size_btc": position,
        "entry_cost": outcome["entry_cost"],
        "expected_profit": outcome["expected_profit"],
        "max_loss": outcome["max_loss"],
        "profit_pct": outcome["profit_pct"],
        "loss_pct": outcome["loss_pct"],
        "risk_reward_ratio": outcome["risk_reward"],
        "target_value": outcome["target_value"]
    }
