"""
agents.py — LLM prompt builders for all four specialist agents.

Fixes from v1:
- Risk agent no longer pre-answers itself (was just echoing suggested_risk back)
- All prompts include explicit WAIT conditions to prevent WAIT-phobia
- News agent gets recency-weighted headlines
- Technical agent gets multi-timeframe context hint
"""


def technical_agent(latest, patterns, sr, volume, trend_str, memory):
    ema_trend = (
        "Bullish (EMA9>EMA20>EMA50)" if latest['ema9'] > latest['ema20'] > latest['ema50']
        else "Bearish (EMA9<EMA20<EMA50)" if latest['ema9'] < latest['ema20'] < latest['ema50']
        else "Mixed / transitioning"
    )
    rsi = latest['rsi']
    if rsi < 30:
        rsi_note = "strongly oversold — high-probability BUY zone"
    elif rsi < 40:
        rsi_note = "oversold — lean BUY"
    elif rsi > 70:
        rsi_note = "strongly overbought — high-probability SELL zone"
    elif rsi > 60:
        rsi_note = "overbought — lean SELL"
    else:
        rsi_note = "neutral zone"

    macd_note = "bullish momentum building" if latest['macd_hist'] > 0 else "bearish momentum building"
    atr_pct = (latest['atr'] / latest['Close'] * 100) if latest['Close'] > 0 else 0

    return f"""You are a senior technical analyst making a real-money trading decision.

Recent decision history: {memory}

=== CURRENT INDICATORS ===
Price:       ${latest['Close']:.4f}
RSI(14):     {rsi:.1f}  [{rsi_note}]
MACD Hist:   {latest['macd_hist']:.6f}  [{macd_note}]
EMA Trend:   {ema_trend}
ADX:         {latest['adx']:.1f}  [{"strong trend >25" if latest['adx'] > 25 else "weak/ranging <25 — signals less reliable"}]
Stoch K/D:   {latest['stoch_k']:.1f} / {latest['stoch_d']:.1f}
BB Width:    {latest['bb_width']:.4f}  [{"squeeze — breakout imminent" if latest['bb_width'] < 0.02 else "normal"}]
ATR:         ${latest['atr']:.4f} ({atr_pct:.2f}% of price)
S/R Zone:    {sr}
Volume:      {volume}
Patterns:    {', '.join(patterns)}
Trend Str:   {trend_str}

=== DECISION RULES ===
BUY  when: RSI < 45 AND MACD > 0 AND (EMA bullish OR near support) AND ADX > 18
SELL when: RSI > 55 AND MACD < 0 AND (EMA bearish OR near resistance) AND ADX > 18
WAIT when: ADX < 15 (choppy market) OR signals directly conflict OR BB squeeze without direction

=== OUTPUT FORMAT — EXACTLY 3 LINES ===
Signal: BUY
Reason: [one specific line referencing actual indicator values]
Confidence: high
"""


def momentum_agent(latest):
    macd_dir  = "positive — bullish momentum" if latest['macd_hist'] > 0 else "negative — bearish momentum"
    stoch_dir = "oversold (<30) — bounce likely" if latest['stoch_k'] < 30 else (
                "overbought (>70) — pullback likely" if latest['stoch_k'] > 70 else "neutral")
    ema_cross = "bullish crossover" if latest['ema9'] > latest['ema20'] else "bearish crossover"
    rsi_dir   = "below 50 — momentum tilts bullish" if latest['rsi'] < 50 else "above 50 — momentum tilts bearish"

    # Count signals for clarity
    bullish = sum([
        latest['macd_hist'] > 0,
        latest['stoch_k'] < 50,
        latest['ema9'] > latest['ema20'],
        latest['rsi'] < 50,
    ])
    bearish = 4 - bullish

    return f"""You are a momentum trader. Assess trend strength and direction.

=== MOMENTUM DATA ===
RSI(14):    {latest['rsi']:.1f}  [{rsi_dir}]
MACD Hist:  {latest['macd_hist']:.6f}  [{macd_dir}]
Stoch K:    {latest['stoch_k']:.1f}  [{stoch_dir}]
EMA 9/20:   [{ema_cross}]

Bullish signals: {bullish}/4
Bearish signals: {bearish}/4

=== RULES ===
BUY  if bullish signals >= 3
SELL if bearish signals >= 3
WAIT if exactly 2 vs 2 split

=== OUTPUT FORMAT — EXACTLY 2 LINES ===
Signal: BUY
Reason: [one line citing the strongest 1-2 momentum signals]
"""


def news_agent(headlines, ticker):
    if headlines:
        # Format with recency indicator (first = most recent)
        headline_text = "\n".join(
            f"[{'LATEST' if i == 0 else f'#{i+1}'}] {h}"
            for i, h in enumerate(headlines)
        )
        count = len(headlines)
    else:
        headline_text = "No recent headlines found."
        count = 0

    return f"""You are a market sentiment analyst for {ticker}.

Analyse {count} recent headlines. Weight the LATEST headline most heavily.

=== HEADLINES ===
{headline_text}

=== RULES ===
- Positive: earnings beat, expansion, upgrade, product launch, regulatory approval
- Negative: earnings miss, investigation, downgrade, layoffs, ban, hack
- Neutral: routine updates, analyst price target adjustments within 5%
- If no headlines or purely routine: respond Neutral / Neutral

=== OUTPUT FORMAT — EXACTLY 3 LINES ===
Sentiment: Positive
Impact: Bullish
Key factor: [one line — cite the most impactful headline or "No significant news"]
"""


def risk_agent(latest, volume, ticker):
    """
    Real risk analysis — NOT pre-answered.
    The LLM must assess based on the data, not echo back a suggestion.
    """
    atr_pct  = (latest['atr'] / latest['Close'] * 100) if latest['Close'] > 0 else 0
    bb_width = latest.get('bb_width', 0.05)
    adx      = latest['adx']
    rsi      = latest['rsi']

    # Provide context only — no suggested answer
    volatility_context = (
        "Very high volatility — wide price swings expected" if atr_pct > 5
        else "Elevated volatility" if atr_pct > 3
        else "Normal volatility" if atr_pct > 1.5
        else "Low volatility — potential breakout building"
    )

    trend_context = (
        "Strong trend present — directional trades favored" if adx > 25
        else "Moderate trend" if adx > 18
        else "Weak/no trend — range-bound, higher false signal risk"
    )

    return f"""You are a risk manager assessing whether to allow a trade on {ticker}.

=== RISK DATA ===
ATR %:      {atr_pct:.2f}%  [{volatility_context}]
BB Width:   {bb_width:.4f}  [{"Squeeze — directional risk unclear" if bb_width < 0.02 else "Normal spread"}]
ADX:        {adx:.1f}  [{trend_context}]
RSI:        {rsi:.1f}  [{"Extreme — reversal risk" if rsi > 75 or rsi < 25 else "Normal range"}]
Volume:     {volume}

=== ASSESSMENT FRAMEWORK ===
HIGH risk (recommend AVOID) when ALL of:
  - ATR% > 5% AND ADX < 15 (volatile + no trend = chaos)
  OR
  - RSI extreme (>80 or <20) AND volume anomaly (very high or very low)

MEDIUM risk when:
  - ATR% 3-5% OR ADX 15-18 OR RSI 70-80/20-30

LOW risk when:
  - ATR% < 3% AND ADX > 20 AND RSI 35-65

Normal/moderate volatility is acceptable — do NOT default to AVOID for standard market conditions.

=== OUTPUT FORMAT — EXACTLY 3 LINES ===
Risk: Low
Action: Trade
Reason: [one line citing the 2 most relevant risk factors]
"""
