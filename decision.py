def _parse_signal(text):
    """Extract BUY/SELL/WAIT from LLM response robustly."""
    t = text.upper()
    
    # Look for explicit "Signal: BUY" format first
    for line in t.splitlines():
        line = line.strip()
        if line.startswith("SIGNAL:"):
            val = line.replace("SIGNAL:", "").strip()
            if "BUY" in val:   return "BUY"
            if "SELL" in val:  return "SELL"
            if "WAIT" in val:  return "WAIT"
    
    # Fallback: count occurrences
    buy_count  = t.count("BUY")
    sell_count = t.count("SELL")
    wait_count = t.count("WAIT")
    
    if buy_count > sell_count and buy_count > wait_count:
        return "BUY"
    if sell_count > buy_count and sell_count > wait_count:
        return "SELL"
    return "WAIT"


def decide(tech, mom, risk, latest=None):
    """
    Indicator-aware voting system.
    
    Votes:  Technical=3, Momentum=2, Indicators=2
    Threshold: >= 4 votes to trigger BUY/SELL (majority of 7 possible)
    Risk: only vetoes on VERY high risk (both High risk AND Avoid)
    """

    # Risk veto — only block if BOTH "High" risk AND "Avoid" present
    risk_upper = risk.upper()
    hard_veto = "RISK: HIGH" in risk_upper and "AVOID" in risk_upper

    buy_votes  = 0
    sell_votes = 0

    # Technical agent — weight 3
    tech_sig = _parse_signal(tech)
    if tech_sig == "BUY":   buy_votes  += 3
    elif tech_sig == "SELL": sell_votes += 3

    # Momentum agent — weight 2
    mom_sig = _parse_signal(mom)
    if mom_sig == "BUY":   buy_votes  += 2
    elif mom_sig == "SELL": sell_votes += 2

    # Indicator confirmation — weight 2 (direct math, no LLM)
    if latest is not None:
        rsi       = latest.get("rsi", 50)
        macd_hist = latest.get("macd_hist", 0)
        ema9      = latest.get("ema9",  0)
        ema20     = latest.get("ema20", 0)
        ema50     = latest.get("ema50", 0)
        stoch_k   = latest.get("stoch_k", 50)

        ind_buy  = 0
        ind_sell = 0

        # RSI
        if rsi < 40:   ind_buy  += 1
        elif rsi > 60: ind_sell += 1

        # MACD histogram direction
        if macd_hist > 0: ind_buy  += 1
        else:             ind_sell += 1

        # EMA alignment
        if ema9 > ema20 > ema50:   ind_buy  += 1
        elif ema9 < ema20 < ema50: ind_sell += 1

        # Stochastic
        if stoch_k < 30:   ind_buy  += 1
        elif stoch_k > 70: ind_sell += 1

        # Indicator score: award 2 votes if 3+ of 4 sub-indicators agree
        if ind_buy >= 3:   buy_votes  += 2
        elif ind_sell >= 3: sell_votes += 2
        # Award 1 vote if 2 agree
        elif ind_buy == 2:   buy_votes  += 1
        elif ind_sell == 2:  sell_votes += 1

    # Apply hard veto AFTER calculating votes (so we can show reason)
    if hard_veto and (buy_votes >= 4 or sell_votes >= 4):
        return "WAIT"  # risk manager blocked a marginal trade

    # Threshold: need 4+ votes out of max 7
    if buy_votes >= 4 and buy_votes > sell_votes:
        return "BUY"
    if sell_votes >= 4 and sell_votes > buy_votes:
        return "SELL"

    # Near-miss: 3 votes but no veto — still trade with lower confidence
    if buy_votes == 3 and buy_votes > sell_votes and not hard_veto:
        return "BUY"
    if sell_votes == 3 and sell_votes > buy_votes and not hard_veto:
        return "SELL"

    return "WAIT"