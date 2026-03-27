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
from outcome_memory import (
    record_signal, update_outcome,
    get_similar_past_signals, get_ticker_stats
)


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
        potential_loss = "2–4% if entering too early"

    if latest.get("ema20", 0) < latest.get("ema50", 0):
        reasons.append("Bearish EMA alignment (EMA20 < EMA50)")
        risk_factors.append("Counter-trend trade risk")
        waiting_for.append("EMA crossover or confirmed support bounce")

    if adx < 15:
        reasons.append("ADX < 15 — choppy, no clear trend")
        risk_factors.append("False signals likely in ranging market")
        waiting_for.append("ADX above 20 for trend confirmation")

    if "AVOID" in risk_text.upper():
        reasons.append("Risk agent flagged high volatility")
        risk_factors.append("ATR and ADX conditions unfavorable")
        waiting_for.append("Market stabilization")

    if "BEARISH" in news_text.upper() or "NEGATIVE" in news_text.upper():
        reasons.append("Negative news sentiment")
        risk_factors.append("Bearish headlines in play")
        waiting_for.append("Sentiment improvement")
        next_check = "12–24 hours"

    if rsi > 70 or rsi < 30:
        next_check = "2–4 hours"

    if not reasons:
        reasons.append("Mixed signals — agents don't agree on direction")
        risk_factors.append("Unclear direction increases loss risk")
        waiting_for.append("Stronger consensus among agents")

    recommendation = (
        "Hold off — multiple risk factors. Patience is an edge."
        if len(risk_factors) > 2
        else "Monitor closely. A clearer setup may form within a few hours."
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
    capital: float = 50_000.0,
    risk_percent: float = 1.0,
):
    df = fetch_ticker_timeframe(ticker, period=period, interval=interval)
    if df.empty:
        raise Exception(f"Failed to fetch data for {ticker}")

    df = add_indicators(df)
    if df.empty:
        raise Exception("Failed to calculate indicators")

    latest      = df.iloc[-1]
    data_source = df.attrs.get("source", "unknown")
    current_price = float(latest["Close"])

    # Check + update outcomes for any pending signals before new analysis
    update_outcome(ticker, current_price)

    mem         = load()
    mem_summary = summarize(mem)

    patterns  = interpret_patterns(latest)
    sr        = sr_zone(latest)
    vol       = volume_state(latest)
    trend_str = trend_strength(latest)
    headlines = fetch_news(query=get_news_query(ticker))

    tech      = ask_llm("technical", technical_agent(latest, patterns, sr, vol, trend_str, mem_summary))
    mom       = ask_llm("momentum",  momentum_agent(latest))
    news_text = ask_llm("news",      news_agent(headlines, ticker))
    risk      = ask_llm("risk",      risk_agent(latest, vol, ticker))

    decision = decide(tech, mom, risk, latest=dict(latest))
    conf     = confidence(tech, mom, news_text, risk, latest=dict(latest))

    trade         = None
    wait_analysis = None

    if decision == "WAIT":
        wait_analysis = analyze_wait_scenario(latest, tech, mom, news_text, risk)
    else:
        trade = levels(latest, decision, sr, capital=capital, risk_percent=risk_percent)
        # Save signal to outcome memory
        if trade:
            record_signal(
                ticker=ticker, decision=decision,
                entry_price=current_price,
                stop_loss=trade["stop_loss"],
                target_price=trade["target_price"],
                confidence=conf,
                rsi=float(latest.get("rsi", 50)),
                adx=float(latest.get("adx", 0)),
                macd_hist=float(latest.get("macd_hist", 0)),
                sr_zone=sr,
            )

    # Fetch similar past signals for context
    past_signals = get_similar_past_signals(
        ticker=ticker, decision=decision,
        rsi=float(latest.get("rsi", 50)),
        macd_hist=float(latest.get("macd_hist", 0)),
        sr_zone=sr,
    )
    ticker_stats = get_ticker_stats(ticker)

    add(mem, decision, current_price, conf)

    return {
        "ticker":        ticker,
        "decision":      decision,
        "confidence":    conf,
        "trade":         trade,
        "wait_analysis": wait_analysis,
        "technical":     tech,
        "momentum":      mom,
        "news":          news_text,
        "headlines":     headlines,
        "risk":          risk,
        "memory":        mem,
        "sr_zone":       sr,
        "trend_str":     trend_str,
        "current_price": current_price,
        "data_source":   data_source,
        "data_points":   len(df),
        "atr":           float(latest.get("atr", 0)),
        "adx":           float(latest.get("adx", 0)),
        "rsi":           float(latest.get("rsi", 50)),
        "macd_hist":     float(latest.get("macd_hist", 0)),
        "past_signals":  past_signals,
        "ticker_stats":  ticker_stats,
    }


def run():
    result = run_enhanced_analysis()
    return (
        result["decision"], result["confidence"], result["trade"],
        result["technical"], result["momentum"], result["news"],
        result["risk"], result["memory"], result["sr_zone"],
    )