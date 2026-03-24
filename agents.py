def technical_agent(latest, patterns, sr, volume, trend_str, memory):
    ema_trend = (
        "Bullish (EMA9>EMA20>EMA50)" if latest['ema9'] > latest['ema20'] > latest['ema50']
        else "Bearish (EMA9<EMA20<EMA50)" if latest['ema9'] < latest['ema20'] < latest['ema50']
        else "Mixed"
    )
    rsi = latest['rsi']
    rsi_note = "oversold - lean BUY" if rsi < 35 else ("overbought - lean SELL" if rsi > 65 else "neutral")

    return f"""You are a professional technical analyst. Analyse the indicators and give ONE clear signal.

Recent decisions: {memory}

INDICATORS:
- Price:      ${latest['Close']:.2f}
- RSI(14):    {rsi:.1f}  [{rsi_note}]
- MACD Hist:  {latest['macd_hist']:.4f}  [{"positive = bullish momentum" if latest['macd_hist'] > 0 else "negative = bearish momentum"}]
- EMA Trend:  {ema_trend}
- ADX:        {latest['adx']:.1f}  [{"strong trend" if latest['adx'] > 25 else "weak/ranging"}]
- Stoch K/D:  {latest['stoch_k']:.1f} / {latest['stoch_d']:.1f}
- BB Width:   {latest['bb_width']:.4f}
- ATR:        {latest['atr']:.2f}
- S/R Zone:   {sr}
- Volume:     {volume}
- Patterns:   {', '.join(patterns)}

DECISION GUIDE:
- BUY when: RSI < 45 AND MACD > 0 AND EMA bullish OR near support
- SELL when: RSI > 55 AND MACD < 0 AND EMA bearish OR near resistance  
- WAIT only when signals are truly conflicting

YOU MUST RESPOND IN EXACTLY THIS FORMAT (3 lines only):
Signal: BUY
Reason: [one line]
Confidence: high
"""


def momentum_agent(latest):
    macd_dir  = "positive (bullish)" if latest['macd_hist'] > 0 else "negative (bearish)"
    stoch_dir = "oversold" if latest['stoch_k'] < 30 else ("overbought" if latest['stoch_k'] > 70 else "neutral")
    ema_cross = "bullish" if latest['ema9'] > latest['ema20'] else "bearish"

    return f"""You are a momentum trader. Give a clear directional signal.

MOMENTUM DATA:
- RSI(14):   {latest['rsi']:.1f}  [{"bullish zone <50" if latest['rsi'] < 50 else "bearish zone >50"}]
- MACD Hist: {latest['macd_hist']:.4f} [{macd_dir}]
- Stoch K:   {latest['stoch_k']:.1f} [{stoch_dir}]
- EMA 9/20:  [{ema_cross} crossover]

RULES:
- BUY if 2+ signals are bullish
- SELL if 2+ signals are bearish
- WAIT only if exactly split

YOU MUST RESPOND IN EXACTLY THIS FORMAT (2 lines only):
Signal: BUY
Reason: [one line]
"""


def news_agent(headlines, ticker):
    headline_text = "\n".join(f"- {h}" for h in headlines) if headlines else "No recent headlines."
    return f"""You are a market sentiment analyst for {ticker}.

Headlines:
{headline_text}

YOU MUST RESPOND IN EXACTLY THIS FORMAT (3 lines only):
Sentiment: Positive
Impact: Bullish
Key factor: [one line]
"""


def risk_agent(latest, volume, ticker):
    atr_pct = (latest['atr'] / latest['Close']) * 100
    # Pre-calculate risk level so LLM has a clear anchor
    if atr_pct > 5 and latest['adx'] < 15:
        suggested_risk = "High"
        suggested_action = "Avoid"
    elif atr_pct > 3 or latest['adx'] < 18:
        suggested_risk = "Medium"
        suggested_action = "Trade"
    else:
        suggested_risk = "Low"
        suggested_action = "Trade"

    return f"""You are a risk manager for {ticker}.

RISK DATA:
- ATR %:    {atr_pct:.2f}%  [only HIGH risk if > 5%]
- Volume:   {volume}
- ADX:      {latest['adx']:.1f}  [only avoid if < 15 AND ATR high]
- RSI:      {latest['rsi']:.1f}
- BB Width: {latest['bb_width']:.4f}

NOTE: Medium/normal volatility is acceptable for trading. 
Only say Avoid if ATR > 5% AND ADX < 15 simultaneously.
Suggested assessment based on data: Risk={suggested_risk}, Action={suggested_action}

YOU MUST RESPOND IN EXACTLY THIS FORMAT (3 lines only):
Risk: {suggested_risk}
Action: {suggested_action}
Reason: [one line]
"""