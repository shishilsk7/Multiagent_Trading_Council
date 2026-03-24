def confidence(tech, mom, news, risk, latest=None):
    """
    More nuanced confidence scoring using indicator values.
    Base = 50. Scaled by signal agreement + indicator extremes.
    """
    score = 50
    tech_u = tech.upper()
    mom_u  = mom.upper()
    news_u = news.upper()
    risk_u = risk.upper()

    # Direction agreement
    if "BUY" in tech_u:
        score += 12
        if "CONFIDENCE: HIGH" in tech_u:
            score += 5
    if "BUY" in mom_u:
        score += 8
    if "BULLISH" in news_u:
        score += 7
    if "SENTIMENT: POSITIVE" in news_u:
        score += 5

    if "SELL" in tech_u:
        score -= 12
    if "SELL" in mom_u:
        score -= 8

    # Risk adjustments
    if "RISK: HIGH" in risk_u:
        score -= 18
    elif "RISK: MEDIUM" in risk_u:
        score -= 8
    elif "RISK: LOW" in risk_u:
        score += 5

    # Indicator-based boosts (if raw data passed)
    if latest is not None:
        rsi = latest.get("rsi", 50)
        adx = latest.get("adx", 0)
        macd_hist = latest.get("macd_hist", 0)

        # Strong trend = more confident
        if adx > 30:
            score += 5
        if adx < 15:
            score -= 8  # ranging market, less confidence

        # RSI extremes with trend confirmation = confidence boost
        if rsi < 35 and "BUY" in tech_u:
            score += 6
        elif rsi > 65 and "SELL" in tech_u:
            score += 6

        # MACD agreement
        if macd_hist > 0 and "BUY" in tech_u:
            score += 4
        elif macd_hist < 0 and "SELL" in tech_u:
            score += 4

    return max(10, min(95, score))
