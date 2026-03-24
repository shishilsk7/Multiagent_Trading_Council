from data import fetch_ticker_timeframe
from indicators import add_indicators, interpret_patterns, sr_zone, volume_state, trend_strength
from news import fetch_news
from llm import ask_llm
from agents import technical_agent, momentum_agent, news_agent, risk_agent
from decision import decide
from confidence import confidence
from trade_levels import levels
from memory import load, add, summarize
from stocks import get_news_query


def analyze_wait_scenario(latest, tech, mom, news_text, risk_text):
    reasons, risk_factors, waiting_for = [], [], []
    next_check = "4-6 hours"
    potential_loss = None

    rsi = latest.get("rsi", 50)
    adx = latest.get("adx", 0)

    if rsi > 70:
        reasons.append("RSI overbought (> 70)")
        risk_factors.append("High pullback risk")
        waiting_for.append("RSI below 65")
        potential_loss = "1–3% downside risk"
    elif rsi < 30:
        reasons.append("RSI oversold (< 30)")
        risk_factors.append("Momentum still declining")
        waiting_for.append("RSI reversal above 35")
        potential_loss = "2–4% downside risk if early"

    if latest.get("ema20", 0) < latest.get("ema50", 0):
        reasons.append("Bearish EMA alignment (EMA20 < EMA50)")
        risk_factors.append("Counter-trend trade")
        waiting_for.append("EMA crossover or confirmed support bounce")

    if adx < 15:
        reasons.append("ADX < 15 — market is ranging, no clear trend")
        risk_factors.append("Choppy price action increases false signals")
        waiting_for.append("ADX above 20 for trend confirmation")

    if "Avoid" in risk_text:
        reasons.append("Risk agent recommends avoiding")
        risk_factors.append("Volatility or ATR too high")
        waiting_for.append("Market stabilization")

    if "Bearish" in news_text or "Negative" in news_text:
        reasons.append("Negative news sentiment")
        risk_factors.append("Bearish headlines in play")
        waiting_for.append("Sentiment shift")
        next_check = "12–24 hours"

    if rsi > 70 or rsi < 30:
        next_check = "2–4 hours"

    if not reasons:
        reasons.append("No strong consensus among agents")
        risk_factors.append("Mixed signals — uncertain direction")
        waiting_for.append("Clearer directional signal")

    recommendation = (
        "Hold off — multiple risk factors present. Patience is an edge."
        if len(risk_factors) > 2
        else "Monitor closely. A setup may develop within the next few hours."
    )

    return {
        "reason": " | ".join(reasons),
        "risk_factors": risk_factors,
        "waiting_for": waiting_for,
        "next_check": next_check,
        "recommendation": recommendation,
        "potential_loss": potential_loss,
    }


def run_enhanced_analysis(
    ticker: str = "BTC-USD",
    period: str = "1d",
    interval: str = "5m",
    capital: float = 10_000.0,
    risk_percent: float = 1.0,
):
    df = fetch_ticker_timeframe(ticker, period=period, interval=interval)
    if df.empty:
        raise Exception(f"Failed to fetch data for {ticker}")

    df = add_indicators(df)
    if df.empty:
        raise Exception("Failed to calculate indicators")

    latest = df.iloc[-1]
    data_source = df.attrs.get("source", "unknown")

    mem = load()
    mem_summary = summarize(mem)

    patterns    = interpret_patterns(latest)
    sr          = sr_zone(latest)
    vol         = volume_state(latest)
    trend_str   = trend_strength(latest)
    news_query  = get_news_query(ticker)
    headlines   = fetch_news(query=news_query)

    # Run agents with richer prompts
    tech = ask_llm("technical", technical_agent(latest, patterns, sr, vol, trend_str, mem_summary))
    mom  = ask_llm("momentum",  momentum_agent(latest))
    news_text = ask_llm("news", news_agent(headlines, ticker))
    risk = ask_llm("risk",      risk_agent(latest, vol, ticker))

    # Decision + confidence
    decision = decide(tech, mom, risk)
    conf     = confidence(tech, mom, news_text, risk, latest=latest)

    trade        = None
    wait_analysis = None

    if decision == "WAIT":
        wait_analysis = analyze_wait_scenario(latest, tech, mom, news_text, risk)
    else:
        trade = levels(latest, decision, sr, capital=capital, risk_percent=risk_percent)

    add(mem, decision, float(latest["Close"]), conf)

    return {
        "ticker":       ticker,
        "decision":     decision,
        "confidence":   conf,
        "trade":        trade,
        "wait_analysis": wait_analysis,
        "technical":    tech,
        "momentum":     mom,
        "news":         news_text,
        "headlines":    headlines,
        "risk":         risk,
        "memory":       mem,
        "sr_zone":      sr,
        "trend_str":    trend_str,
        "current_price": float(latest["Close"]),
        "data_source":  data_source,
        "data_points":  len(df),
        "atr":          float(latest.get("atr", 0)),
        "adx":          float(latest.get("adx", 0)),
        "rsi":          float(latest.get("rsi", 50)),
    }


# Backward compat
def run():
    result = run_enhanced_analysis()
    return (
        result["decision"], result["confidence"], result["trade"],
        result["technical"], result["momentum"], result["news"],
        result["risk"], result["memory"], result["sr_zone"],
    )
