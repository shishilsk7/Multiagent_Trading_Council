"""
core.py — Main orchestrator.

Upgrades from v1:
- All 4 LLM calls run in PARALLEL (asyncio + ThreadPoolExecutor) → ~75% faster
- Mock data raises exception instead of silently continuing
- confidence_score passed into decide() for near-miss gate
- ticker passed into levels() for ATR multiplier selection
- Decision now returns (decision, breakdown) tuple
"""

import concurrent.futures
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
    next_check = "4–6 hours"
    potential_loss = None

    rsi  = latest.get("rsi", 50)
    adx  = latest.get("adx", 0)
    atr  = latest.get("atr", 0)
    price = float(latest.get("Close", 1))
    atr_pct = (atr / price * 100) if price > 0 else 0

    if rsi > 72:
        reasons.append(f"RSI strongly overbought ({rsi:.1f} > 72)")
        risk_factors.append(f"High pullback risk — ATR suggests ±${atr:.2f} swing possible")
        waiting_for.append("RSI below 65 before entering")
        potential_loss = f"${atr * 1.5:.2f} downside ({atr_pct * 1.5:.1f}%) if entered now"
        next_check = "2–4 hours"
    elif rsi > 65:
        reasons.append(f"RSI overbought ({rsi:.1f})")
        risk_factors.append("Moderate pullback risk")
        waiting_for.append("RSI cooling below 60")
        potential_loss = f"${atr:.2f} downside ({atr_pct:.1f}%) risk"
    elif rsi < 28:
        reasons.append(f"RSI strongly oversold ({rsi:.1f} < 28)")
        risk_factors.append("Momentum still declining — knife-catch risk")
        waiting_for.append("RSI reversal above 35 + green candle confirmation")
        potential_loss = f"${atr * 1.5:.2f} further downside if no reversal"
        next_check = "2–4 hours"
    elif rsi < 35:
        reasons.append(f"RSI oversold ({rsi:.1f})")
        risk_factors.append("May fall further before bouncing")
        waiting_for.append("RSI stabilization above 35")

    if latest.get("ema20", 0) < latest.get("ema50", 0):
        reasons.append("Bearish EMA alignment (EMA20 < EMA50)")
        risk_factors.append("Counter-trend trade — higher failure rate")
        waiting_for.append("EMA20 crosses back above EMA50")

    if adx < 15:
        reasons.append(f"ADX {adx:.1f} — choppy, no clear trend")
        risk_factors.append("False breakouts common in ranging markets")
        waiting_for.append("ADX above 20 for trend confirmation")

    if atr_pct > 5:
        reasons.append(f"Very high volatility (ATR = {atr_pct:.1f}% of price)")
        risk_factors.append(f"Stop could be hit on normal noise — need ${atr * 1.5:.2f} buffer")
        waiting_for.append("Volatility settles (ATR < 3% of price)")

    if "AVOID" in risk_text.upper() and "RISK: HIGH" in risk_text.upper():
        reasons.append("Risk agent: High risk + Avoid flag triggered")
        risk_factors.append("ATR and ADX combination unfavorable for entries")
        waiting_for.append("Market stabilization — check in 4–6 hours")

    if "BEARISH" in news_text.upper() or "NEGATIVE" in news_text.upper():
        reasons.append("Negative news sentiment active")
        risk_factors.append("Bearish headlines can accelerate downside")
        waiting_for.append("Sentiment improvement or news cycle passes")
        next_check = "12–24 hours"

    if not reasons:
        reasons.append("Agent signals conflict — no clear directional consensus")
        risk_factors.append("Unclear direction increases loss probability")
        waiting_for.append("Stronger consensus — at least 3 agents agreeing on direction")

    recommendation = (
        "Multiple compounding risk factors — stay out. Patience protects capital."
        if len(risk_factors) >= 3
        else "One or two flags — monitor closely. Setup may resolve within hours."
    )

    return {
        "reason":        " | ".join(reasons),
        "risk_factors":  risk_factors,
        "waiting_for":   waiting_for,
        "next_check":    next_check,
        "recommendation": recommendation,
        "potential_loss": potential_loss,
    }


def _run_llm_agents_parallel(latest, patterns, sr, vol, trend_str, mem_summary, headlines, ticker):
    """Run all 4 LLM agents in parallel using threads."""
    current_price = float(latest["Close"])
    support       = float(latest.get("support", 0)) or None
    resistance    = float(latest.get("resistance", 0)) or None

    prompts = {
        "technical": technical_agent(latest, patterns, sr, vol, trend_str, mem_summary),
        "momentum":  momentum_agent(latest),
        "news":      news_agent(headlines, ticker,
                                current_price=current_price,
                                sr_zone=sr,
                                support=support,
                                resistance=resistance),
        "risk":      risk_agent(latest, vol, ticker),
    }

    results  = {}
    failures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(ask_llm, role, prompt): role
            for role, prompt in prompts.items()
        }
        for future in concurrent.futures.as_completed(futures):
            role = futures[future]
            try:
                results[role] = future.result()
            except Exception as e:
                failures[role] = str(e)
                results[role] = "WAIT"

    if failures:
        import streamlit as st
        failed_list = ", ".join(f"{r} ({e})" for r, e in failures.items())
        try:
            st.warning(f"⚠️ {len(failures)} agent(s) failed — results degraded: {failed_list}")
        except Exception:
            print(f"[AGENT ERROR] {len(failures)} agent(s) failed: {failed_list}")

    return (
        results.get("technical", "WAIT"),
        results.get("momentum",  "WAIT"),
        results.get("news",      "WAIT"),
        results.get("risk",      "WAIT"),
    )


def run_enhanced_analysis(
    ticker: str   = "BTC-USD",
    period: str   = "1d",
    interval: str = "5m",
    capital: float = 50_000.0,
    risk_percent: float = 1.0,
):
    # ── 1. Fetch data ───────────────────────────────────────────────
    df = fetch_ticker_timeframe(ticker, period=period, interval=interval)
    if df.empty:
        raise Exception(f"Failed to fetch data for {ticker}")

    data_source = df.attrs.get("source", "unknown")

    # Hard block on mock data — never make real-money decisions on fake data
    if data_source == "mock":
        raise Exception(
            f"⚠️ All data sources failed for {ticker}. "
            "Cannot analyse with mock data for real-money use. "
            "Check your internet connection or try a different asset."
        )

    # ── 2. Indicators ───────────────────────────────────────────────
    df = add_indicators(df)
    if df.empty:
        raise Exception("Failed to calculate indicators — not enough candle data")

    latest        = df.iloc[-1]
    current_price = float(latest["Close"])

    # ── 3. Update outcomes for pending signals ──────────────────────
    update_outcome(ticker, current_price)

    # ── 4. Build context ────────────────────────────────────────────
    mem         = load()
    mem_summary = summarize(mem)
    patterns    = interpret_patterns(latest)
    sr          = sr_zone(latest)
    vol         = volume_state(latest)
    trend_str   = trend_strength(latest)
    headlines   = fetch_news(query=get_news_query(ticker))

    # ── 5. Run all agents in PARALLEL ──────────────────────────────
    tech, mom, news_text, risk = _run_llm_agents_parallel(
        latest, patterns, sr, vol, trend_str, mem_summary, headlines, ticker
    )

    # ── 6. Confidence first (needed for near-miss gate in decide) ──
    conf = confidence(tech, mom, news_text, risk, latest=dict(latest))

    # ── 7. Decision with confidence gate ────────────────────────────
    decision, vote_breakdown = decide(tech, mom, risk, latest=dict(latest), confidence_score=conf)

    # ── 8. Trade plan or WAIT analysis ──────────────────────────────
    trade         = None
    wait_analysis = None

    if decision == "WAIT":
        wait_analysis = analyze_wait_scenario(latest, tech, mom, news_text, risk)
    else:
        trade = levels(
            latest, decision, sr,
            capital=capital,
            risk_percent=risk_percent,
            ticker=ticker,
        )
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

    # ── 9. Historical context ────────────────────────────────────────
    past_signals = get_similar_past_signals(
        ticker=ticker, decision=decision,
        rsi=float(latest.get("rsi", 50)),
        macd_hist=float(latest.get("macd_hist", 0)),
        sr_zone=sr,
    )
    ticker_stats = get_ticker_stats(ticker)

    add(mem, decision, current_price, conf)

    return {
        "ticker":         ticker,
        "decision":       decision,
        "confidence":     conf,
        "vote_breakdown": vote_breakdown,
        "trade":          trade,
        "wait_analysis":  wait_analysis,
        "technical":      tech,
        "momentum":       mom,
        "news":           news_text,
        "headlines":      headlines,
        "risk":           risk,
        "memory":         mem,
        "sr_zone":        sr,
        "trend_str":      trend_str,
        "current_price":  current_price,
        "data_source":    data_source,
        "data_points":    len(df),
        "atr":            float(latest.get("atr", 0)),
        "adx":            float(latest.get("adx", 0)),
        "rsi":            float(latest.get("rsi", 50)),
        "macd_hist":      float(latest.get("macd_hist", 0)),
        "past_signals":   past_signals,
        "ticker_stats":   ticker_stats,
        "patterns":       patterns,
        "vol_state":      vol,
    }


def run():
    """Legacy wrapper."""
    result = run_enhanced_analysis()
    return (
        result["decision"], result["confidence"], result["trade"],
        result["technical"], result["momentum"], result["news"],
        result["risk"], result["memory"], result["sr_zone"],
    )
