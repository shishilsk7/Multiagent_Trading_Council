def confidence(tech, mom, news, risk, latest=None):
    score = 50
    tech_u = tech.upper()
    mom_u  = mom.upper()
    news_u = news.upper()
    risk_u = risk.upper()

    buy_signals = 0
    sell_signals = 0

    if "BUY" in tech_u: buy_signals += 1
    if "SELL" in tech_u: sell_signals += 1
    if "BUY" in mom_u: buy_signals += 1
    if "SELL" in mom_u: sell_signals += 1
    if "BULLISH" in news_u or "POSITIVE" in news_u: buy_signals += 1
    if "BEARISH" in news_u or "NEGATIVE" in news_u: sell_signals += 1

    if buy_signals > sell_signals:
        score += 12 * buy_signals - 4 * sell_signals
        if "CONFIDENCE: HIGH" in tech_u: score += 5
    elif sell_signals > buy_signals:
        score += 12 * sell_signals - 4 * buy_signals
        if "CONFIDENCE: HIGH" in tech_u: score += 5

    if "RISK: HIGH" in risk_u:
        score -= 18
    elif "RISK: MEDIUM" in risk_u:
        score -= 8
    elif "RISK: LOW" in risk_u:
        score += 5

    if latest is not None:
        rsi = latest.get("rsi", 50)
        adx = latest.get("adx", 0)
        macd_hist = latest.get("macd_hist", 0)

        if adx > 30:
            score += 5
        if adx < 15:
            score -= 8

        if rsi < 35 and "BUY" in tech_u:
            score += 6
        elif rsi > 65 and "SELL" in tech_u:
            score += 6

        if macd_hist > 0 and "BUY" in tech_u:
            score += 4
        elif macd_hist < 0 and "SELL" in tech_u:
            score += 4

    return max(10, min(95, score))