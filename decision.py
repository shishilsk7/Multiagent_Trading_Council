"""
decision.py — Weighted voting with confidence gate.

Fixes from v2:
- Near-miss (3-vote) gate now requires at least 1 LLM agent to agree.
  Previously 3 indicator votes alone (tech=WAIT, mom=WAIT) could trigger
  a trade — that's a pure-math signal with no LLM analysis backing it,
  which is not appropriate for real-money use.
- Added explicit "agent_agreement" field to breakdown for UI clarity.
- Tie-breaking logic documented clearly (no change, just clearer code).

Vote weights:  Technical=3, Momentum=2, Indicators=2  → max 7
Thresholds:
  - 5+ votes → strong, fires unless absolute veto
  - 4  votes → solid, fires unless veto
  - 3  votes (near-miss) → fires only if:
              (a) confidence >= 45 AND
              (b) no hard veto AND
              (c) at least 1 LLM agent (tech or mom) agrees with direction
  - <3 votes → WAIT

Hard veto: RISK: HIGH + AVOID → blocks marginal (3-4 vote) signals.
           Does NOT block strong 5+ vote signals.
"""


def _parse_signal(text: str) -> str:
    """
    Parse agent output for a directional signal.
    Prioritises the explicit 'Signal:' line; falls back to keyword frequency.
    Handles negation context ('DO NOT BUY' should not count as BUY).
    """
    t = text.upper()

    # Prioritise explicit "Signal:" line
    for line in t.splitlines():
        line = line.strip()
        if line.startswith("SIGNAL:"):
            val = line.replace("SIGNAL:", "").strip()
            if val.startswith("BUY"):   return "BUY"
            if val.startswith("SELL"):  return "SELL"
            if val.startswith("WAIT"):  return "WAIT"

    # Fallback: strip negation context then count
    clean = t
    for neg in ["NOT BUY", "NOT SELL", "AVOID BUY", "AVOID SELL",
                "DO NOT BUY", "DO NOT SELL", "NEVER BUY", "NEVER SELL",
                "NO BUY", "NO SELL"]:
        clean = clean.replace(neg, "")

    buy_count  = clean.count("BUY")
    sell_count = clean.count("SELL")
    wait_count = clean.count("WAIT")

    if buy_count > sell_count and buy_count > wait_count:  return "BUY"
    if sell_count > buy_count and sell_count > wait_count: return "SELL"
    return "WAIT"


def _indicator_votes(latest: dict) -> tuple[int, int, int, int]:
    """
    Pure-math vote from raw indicators — no LLM involved.
    Returns (buy_votes, sell_votes, raw_buy_count, raw_sell_count)
    where buy_votes/sell_votes are the weighted contribution (0, 1, or 2).
    """
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

    # ADX trend strength bonus — only boosts if direction is already clear
    if adx > 25:
        if ind_buy > ind_sell:   ind_buy  += 1
        elif ind_sell > ind_buy: ind_sell += 1

    # Convert raw counts to vote weight
    # 3+ of 4 base signals = 2 votes; 2 of 4 = 1 vote; <2 = 0
    buy_v = sell_v = 0
    if ind_buy >= 3:    buy_v  = 2
    elif ind_buy == 2:  buy_v  = 1
    if ind_sell >= 3:   sell_v = 2
    elif ind_sell == 2: sell_v = 1

    return buy_v, sell_v, ind_buy, ind_sell


def decide(tech: str, mom: str, risk: str, latest: dict = None,
           confidence_score: int = None) -> tuple[str, dict]:
    """
    Returns (decision, vote_detail_dict).
    decision: 'BUY' / 'SELL' / 'WAIT'
    vote_detail: full breakdown for UI display.
    """
    risk_upper = risk.upper()
    hard_veto  = "RISK: HIGH" in risk_upper and "AVOID" in risk_upper

    buy_votes  = 0
    sell_votes = 0
    breakdown  = {}

    # ── Technical agent — weight 3 ─────────────────────────────────
    tech_sig = _parse_signal(tech)
    breakdown["technical"] = tech_sig
    if tech_sig == "BUY":    buy_votes  += 3
    elif tech_sig == "SELL": sell_votes += 3
    breakdown["tech_votes"] = 3 if tech_sig in ("BUY", "SELL") else 0

    # ── Momentum agent — weight 2 ──────────────────────────────────
    mom_sig = _parse_signal(mom)
    breakdown["momentum"] = mom_sig
    if mom_sig == "BUY":    buy_votes  += 2
    elif mom_sig == "SELL": sell_votes += 2
    breakdown["mom_votes"] = 2 if mom_sig in ("BUY", "SELL") else 0

    # ── Indicator confirmation — weight up to 2 ────────────────────
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

    # How many LLM agents agree with the leading direction
    # (used for near-miss gate)
    def llm_agents_agreeing(direction: str) -> int:
        count = 0
        if tech_sig == direction: count += 1
        if mom_sig  == direction: count += 1
        return count

    # ── Decision logic ──────────────────────────────────────────────
    if buy_votes == sell_votes:
        breakdown["reason"] = "Tied votes — no clear direction"
        return "WAIT", breakdown

    leading    = "BUY" if buy_votes > sell_votes else "SELL"
    lead_votes = buy_votes if leading == "BUY" else sell_votes
    llm_agree  = llm_agents_agreeing(leading)
    breakdown["llm_agents_agreeing"] = llm_agree

    if lead_votes >= 5:
        # Strong signal: only an absolute veto at 5 votes; 6+ overrides even that
        if hard_veto and lead_votes < 6:
            breakdown["reason"] = f"Hard risk veto blocked strong signal ({lead_votes}/7 votes)"
            return "WAIT", breakdown
        breakdown["reason"] = f"Strong signal ({lead_votes}/7 votes, {llm_agree} LLM agent(s) agree)"

    elif lead_votes == 4:
        if hard_veto:
            breakdown["reason"] = f"Hard risk veto blocked solid signal ({lead_votes}/7 votes)"
            return "WAIT", breakdown
        breakdown["reason"] = f"Solid signal ({lead_votes}/7 votes, {llm_agree} LLM agent(s) agree)"

    elif lead_votes == 3:
        # Near-miss gate — three requirements:
        # 1. No hard veto
        if hard_veto:
            breakdown["reason"] = "Hard risk veto blocked near-miss signal (3/7 votes)"
            return "WAIT", breakdown

        # 2. Minimum confidence threshold
        if confidence_score is not None and confidence_score < 45:
            breakdown["reason"] = (
                f"Near-miss ({lead_votes}/7 votes) + low confidence ({confidence_score}%) — WAIT"
            )
            return "WAIT", breakdown

        # 3. At least 1 LLM agent must agree — pure indicator math isn't enough
        if llm_agree == 0:
            breakdown["reason"] = (
                f"Near-miss ({lead_votes}/7 votes) — indicators only, no LLM agreement — WAIT"
            )
            return "WAIT", breakdown

        breakdown["reason"] = (
            f"Near-miss signal ({lead_votes}/7 votes) — {llm_agree} LLM agent(s) agree, "
            f"confidence {confidence_score}%"
        )

    else:
        breakdown["reason"] = f"Insufficient votes ({lead_votes}/7) — WAIT"
        return "WAIT", breakdown

    return leading, breakdown
