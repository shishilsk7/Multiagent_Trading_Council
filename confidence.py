"""
confidence.py — Symmetric, indicator-aware confidence scoring.

Fixed issues from v1:
- BUY and SELL now get equal weighting (was biased toward BUY)
- ADX, ATR%, BB width all factor in
- Confidence is capped at 88 (never "certain") for real money use
"""


def confidence(tech, mom, news, risk, latest=None):
    """
    Returns confidence score 10–88.
    Symmetric: a perfect SELL setup scores same as a perfect BUY setup.
    """
    score = 50
    tech_u = tech.upper()
    mom_u  = mom.upper()
    news_u = news.upper()
    risk_u = risk.upper()

    # Detect dominant direction
    tech_buy  = "BUY"  in tech_u
    tech_sell = "SELL" in tech_u
    mom_buy   = "BUY"  in mom_u
    mom_sell  = "SELL" in mom_u

    # Agent agreement boosts (symmetric)
    if tech_buy:
        score += 12
        if "CONFIDENCE: HIGH" in tech_u: score += 4
    if tech_sell:
        score += 12   # same weight for SELL direction
        if "CONFIDENCE: HIGH" in tech_u: score += 4

    if mom_buy  and tech_buy:   score += 8   # agreement bonus
    if mom_sell and tech_sell:  score += 8

    # News alignment (smaller weight — it's shallow)
    if tech_buy  and ("BULLISH" in news_u or "POSITIVE" in news_u): score += 5
    if tech_sell and ("BEARISH" in news_u or "NEGATIVE" in news_u): score += 5
    # Contradiction penalty
    if tech_buy  and ("BEARISH" in news_u or "NEGATIVE" in news_u): score -= 4
    if tech_sell and ("BULLISH" in news_u or "POSITIVE" in news_u): score -= 4

    # Risk level adjustments
    if "RISK: HIGH" in risk_u:
        score -= 18
    elif "RISK: MEDIUM" in risk_u:
        score -= 7
    elif "RISK: LOW" in risk_u:
        score += 5

    # Raw indicator boosts
    if latest is not None:
        rsi       = latest.get("rsi", 50)
        adx       = latest.get("adx", 0)
        macd_hist = latest.get("macd_hist", 0)
        atr       = latest.get("atr", 0)
        price     = latest.get("Close", 1)
        bb_width  = latest.get("bb_width", 0.05)
        atr_pct   = (atr / price * 100) if price > 0 else 0

        # Strong trend = more reliable signals
        if adx > 35:   score += 7
        elif adx > 25: score += 4
        elif adx < 15: score -= 10  # ranging market, signals unreliable

        # RSI extremes confirm direction
        if rsi < 30 and tech_buy:   score += 7
        elif rsi > 70 and tech_sell: score += 7
        elif rsi < 40 and tech_buy:  score += 3
        elif rsi > 60 and tech_sell: score += 3

        # MACD agreement
        if macd_hist > 0 and tech_buy:   score += 4
        elif macd_hist < 0 and tech_sell: score += 4

        # High volatility = less reliable (harder to hit targets)
        if atr_pct > 5: score -= 8
        elif atr_pct > 3: score -= 3

        # Squeeze (low BB width) = pre-breakout uncertainty
        if bb_width < 0.02: score -= 5

    return max(10, min(88, score))
