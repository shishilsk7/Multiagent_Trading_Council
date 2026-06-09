"""
confidence.py — Symmetric, indicator-aware confidence scoring.

Fixes from v2:
- BUY/SELL direction flags are now mutually exclusive and correctly parsed.
  Previously "DO NOT BUY" set tech_buy=True because "BUY" is a substring.
  Now we parse the explicit "Signal:" line first, fall back to keyword counts.
- ADX penalty now also applies when the indicator vote is exactly split
  (no clear trend direction should lower confidence)
- Confidence cap remains 88 — never claim certainty for real-money use.
"""


def _parse_direction(text: str) -> str:
    """
    Extract the declared signal direction from agent text.
    Returns 'BUY', 'SELL', or 'WAIT'.
    Prioritises the explicit 'Signal:' line to avoid substring false-positives
    like 'DO NOT BUY' or 'AVOID SELL'.
    """
    for line in text.splitlines():
        stripped = line.strip().upper()
        if stripped.startswith("SIGNAL:"):
            val = stripped.replace("SIGNAL:", "").strip()
            if val.startswith("BUY"):   return "BUY"
            if val.startswith("SELL"):  return "SELL"
            if val.startswith("WAIT"):  return "WAIT"

    # Fallback: count occurrences but only in affirmative positions
    # Remove negation context before counting ("NOT BUY", "AVOID SELL", etc.)
    clean = text.upper()
    for neg in ["NOT BUY", "NOT SELL", "AVOID BUY", "AVOID SELL",
                "DO NOT BUY", "DO NOT SELL", "NEVER BUY", "NEVER SELL",
                "NO BUY", "NO SELL"]:
        clean = clean.replace(neg, "")

    buy_count  = clean.count("BUY")
    sell_count = clean.count("SELL")
    if buy_count > sell_count:   return "BUY"
    if sell_count > buy_count:   return "SELL"
    return "WAIT"


def confidence(tech, mom, news, risk, latest=None) -> int:
    """
    Returns confidence score 10–88.

    Symmetric scoring: a perfect SELL setup scores same as a perfect BUY setup.
    Direction is determined by unambiguous signal parsing, not substring search.
    """
    score = 50
    tech_u = tech.upper()
    mom_u  = mom.upper()
    news_u = news.upper()
    risk_u = risk.upper()

    # Parse declared directions cleanly
    tech_dir = _parse_direction(tech)
    mom_dir  = _parse_direction(mom)

    tech_buy  = (tech_dir == "BUY")
    tech_sell = (tech_dir == "SELL")
    mom_buy   = (mom_dir == "BUY")
    mom_sell  = (mom_dir == "SELL")

    # ── Agent signal boosts ────────────────────────────────────────
    # Technical agent: strongest signal (weight 3 in voting)
    if tech_dir in ("BUY", "SELL"):
        score += 12
        if "CONFIDENCE: HIGH" in tech_u: score += 4
    # WAIT from tech is a meaningful negative signal
    elif tech_dir == "WAIT":
        score -= 4

    # Momentum agreement with technical
    if mom_buy and tech_buy:
        score += 8   # same direction = agreement bonus
    elif mom_sell and tech_sell:
        score += 8
    elif mom_dir in ("BUY", "SELL") and not (mom_buy == tech_buy and mom_sell == tech_sell):
        # Momentum contradicts technical
        score -= 6
    # mom WAIT doesn't penalise much (momentum is often lagging)

    # ── News alignment ─────────────────────────────────────────────
    bullish_news = "BULLISH" in news_u or "POSITIVE" in news_u
    bearish_news = "BEARISH" in news_u or "NEGATIVE" in news_u

    if tech_buy  and bullish_news: score += 5
    if tech_sell and bearish_news: score += 5
    if tech_buy  and bearish_news: score -= 4   # contradiction
    if tech_sell and bullish_news: score -= 4

    # ── Risk level adjustments ─────────────────────────────────────
    if "RISK: HIGH" in risk_u:
        score -= 18
    elif "RISK: MEDIUM" in risk_u:
        score -= 7
    elif "RISK: LOW" in risk_u:
        score += 5

    # Hard veto from risk agent further penalises
    if "RISK: HIGH" in risk_u and "AVOID" in risk_u:
        score -= 8

    # ── Raw indicator boosts ───────────────────────────────────────
    if latest is not None:
        rsi       = latest.get("rsi", 50)
        adx       = latest.get("adx", 0)
        macd_hist = latest.get("macd_hist", 0)
        atr       = latest.get("atr", 0)
        price     = latest.get("Close", 1)
        bb_width  = latest.get("bb_width", 0.05)
        atr_pct   = (atr / price * 100) if price > 0 else 0

        # Strong trend = signals more reliable
        if adx > 35:   score += 7
        elif adx > 25: score += 4
        elif adx < 15: score -= 10  # choppy market, signals unreliable
        # Extra penalty if direction is split AND trend is weak
        elif adx < 20 and tech_dir == "WAIT":
            score -= 4

        # RSI extremes confirm direction
        if   rsi < 30 and tech_buy:    score += 7
        elif rsi > 70 and tech_sell:   score += 7
        elif rsi < 40 and tech_buy:    score += 3
        elif rsi > 60 and tech_sell:   score += 3
        # Overbought on BUY signal = less reliable
        elif rsi > 70 and tech_buy:    score -= 5
        elif rsi < 30 and tech_sell:   score -= 5

        # MACD agreement
        if   macd_hist > 0 and tech_buy:   score += 4
        elif macd_hist < 0 and tech_sell:  score += 4
        elif macd_hist > 0 and tech_sell:  score -= 3  # macd contradicts
        elif macd_hist < 0 and tech_buy:   score -= 3

        # High volatility = less predictable targets/stops
        if   atr_pct > 5: score -= 8
        elif atr_pct > 3: score -= 3

        # Bollinger squeeze = pre-breakout uncertainty (direction unknown)
        if bb_width < 0.02: score -= 5

    return max(10, min(88, score))
