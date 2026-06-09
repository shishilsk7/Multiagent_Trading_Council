"""
decision.py — Weighted voting with confidence gate.

Votes:  Technical=3, Momentum=2, Indicators=2  → max 7
Threshold:
  - 5+ votes → strong signal, always fires
  - 4  votes → fires
  - 3  votes (near-miss) → only fires if confidence >= 45 AND no hard veto
  - <3 votes → WAIT

Hard veto: RISK: HIGH + AVOID in risk text → blocks any marginal (3-vote) trade
           Does NOT block a strong 5+ vote signal (risk agent is just one input)
"""


def _parse_signal(text):
    t = text.upper()

    for line in t.splitlines():
        line = line.strip()
        if line.startswith("SIGNAL:"):
            val = line.replace("SIGNAL:", "").strip()
            if "BUY" in val:   return "BUY"
            if "SELL" in val:  return "SELL"
            if "WAIT" in val:  return "WAIT"

    buy_count  = t.count("BUY")
    sell_count = t.count("SELL")
    wait_count = t.count("WAIT")

    if buy_count > sell_count and buy_count > wait_count:
        return "BUY"
    if sell_count > buy_count and sell_count > wait_count:
        return "SELL"
    return "WAIT"


def _indicator_votes(latest):
    """Pure math vote from raw indicators — no LLM involved."""
    rsi       = latest.get("rsi", 50)
    macd_hist = latest.get("macd_hist", 0)
    ema9      = latest.get("ema9",  0)
    ema20     = latest.get("ema20", 0)
    ema50     = latest.get("ema50", 0)
    stoch_k   = latest.get("stoch_k", 50)
    adx       = latest.get("adx", 0)

    ind_buy  = 0
    ind_sell = 0

    # RSI
    if rsi < 40:   ind_buy  += 1
    elif rsi > 60: ind_sell += 1

    # MACD histogram direction
    if macd_hist > 0: ind_buy  += 1
    else:             ind_sell += 1

    # EMA full alignment
    if ema9 > ema20 > ema50:   ind_buy  += 1
    elif ema9 < ema20 < ema50: ind_sell += 1

    # Stochastic
    if stoch_k < 30:   ind_buy  += 1
    elif stoch_k > 70: ind_sell += 1

    # Bonus: ADX confirms trend strength — give extra weight to direction
    if adx > 25:
        if ind_buy > ind_sell:   ind_buy  += 1
        elif ind_sell > ind_buy: ind_sell += 1

    # Score to votes: 3+ of 4 base = 2 votes; 2 of 4 = 1 vote
    buy_v = sell_v = 0
    if ind_buy >= 3:    buy_v  = 2
    elif ind_buy == 2:  buy_v  = 1
    if ind_sell >= 3:   sell_v = 2
    elif ind_sell == 2: sell_v = 1

    return buy_v, sell_v, ind_buy, ind_sell


def decide(tech, mom, risk, latest=None, confidence_score=None):
    """
    Returns (decision, vote_detail_dict)
    decision: BUY / SELL / WAIT
    vote_detail: breakdown for UI display
    """
    risk_upper = risk.upper()
    hard_veto  = "RISK: HIGH" in risk_upper and "AVOID" in risk_upper

    buy_votes  = 0
    sell_votes = 0
    breakdown  = {}

    # Technical agent — weight 3
    tech_sig = _parse_signal(tech)
    breakdown["technical"] = tech_sig
    if tech_sig == "BUY":    buy_votes  += 3
    elif tech_sig == "SELL": sell_votes += 3
    breakdown["tech_votes"] = 3 if tech_sig in ("BUY", "SELL") else 0

    # Momentum agent — weight 2
    mom_sig = _parse_signal(mom)
    breakdown["momentum"] = mom_sig
    if mom_sig == "BUY":    buy_votes  += 2
    elif mom_sig == "SELL": sell_votes += 2
    breakdown["mom_votes"] = 2 if mom_sig in ("BUY", "SELL") else 0

    # Indicator confirmation — weight up to 2
    ind_buy_v = ind_sell_v = 0
    if latest is not None:
        ind_buy_v, ind_sell_v, raw_buy, raw_sell = _indicator_votes(latest)
        buy_votes  += ind_buy_v
        sell_votes += ind_sell_v
        breakdown["ind_raw_buy"]  = raw_buy
        breakdown["ind_raw_sell"] = raw_sell
    breakdown["ind_buy_votes"]  = ind_buy_v
    breakdown["ind_sell_votes"] = ind_sell_v

    breakdown["total_buy"]  = buy_votes
    breakdown["total_sell"] = sell_votes
    breakdown["hard_veto"]  = hard_veto

    # ── Decision logic ──────────────────────────────────────────────
    direction = None
    votes_needed = buy_votes if buy_votes > sell_votes else sell_votes
    leading = "BUY" if buy_votes > sell_votes else ("SELL" if sell_votes > buy_votes else None)

    if leading is None:
        breakdown["reason"] = "Tied votes"
        return "WAIT", breakdown

    lead_votes = buy_votes if leading == "BUY" else sell_votes

    if lead_votes >= 5:
        # Strong signal — only blocked by absolute veto
        if hard_veto and lead_votes < 6:
            breakdown["reason"] = "Hard risk veto blocked 5-vote signal"
            return "WAIT", breakdown
        direction = leading
        breakdown["reason"] = f"Strong signal ({lead_votes}/7 votes)"

    elif lead_votes == 4:
        if hard_veto:
            breakdown["reason"] = "Hard risk veto blocked 4-vote signal"
            return "WAIT", breakdown
        direction = leading
        breakdown["reason"] = f"Solid signal ({lead_votes}/7 votes)"

    elif lead_votes == 3:
        # Near-miss: only fire if confidence is reasonable and no veto
        if hard_veto:
            breakdown["reason"] = "Hard risk veto blocked near-miss signal"
            return "WAIT", breakdown
        if confidence_score is not None and confidence_score < 45:
            breakdown["reason"] = f"Near-miss ({lead_votes}/7 votes) but low confidence ({confidence_score}%) — WAIT"
            return "WAIT", breakdown
        direction = leading
        breakdown["reason"] = f"Near-miss signal ({lead_votes}/7 votes) — lower confidence"

    else:
        breakdown["reason"] = f"Insufficient votes ({lead_votes}/7)"
        return "WAIT", breakdown

    return direction, breakdown
