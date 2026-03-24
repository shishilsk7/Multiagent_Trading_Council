def decide(tech, mom, risk, conf_score=50):
    """
    Weighted voting: Tech (3pts), Momentum (2pts), Risk veto.
    Requires majority to act — otherwise WAIT.
    """
    # Risk veto
    if "Avoid" in risk:
        return "WAIT"

    buy_votes = 0
    sell_votes = 0

    # Technical agent — weight 3
    tech_upper = tech.upper()
    if "SIGNAL: BUY" in tech_upper or tech_upper.count("BUY") > tech_upper.count("SELL"):
        buy_votes += 3
    elif "SIGNAL: SELL" in tech_upper or tech_upper.count("SELL") > tech_upper.count("BUY"):
        sell_votes += 3

    # Momentum agent — weight 2
    mom_upper = mom.upper()
    if "SIGNAL: BUY" in mom_upper or mom_upper.count("BUY") > mom_upper.count("SELL"):
        buy_votes += 2
    elif "SIGNAL: SELL" in mom_upper or mom_upper.count("SELL") > mom_upper.count("BUY"):
        sell_votes += 2

    # Need clear majority (>= 3 votes) to trigger a trade
    if buy_votes >= 3 and buy_votes > sell_votes:
        return "BUY"
    if sell_votes >= 3 and sell_votes > buy_votes:
        return "SELL"
    return "WAIT"
