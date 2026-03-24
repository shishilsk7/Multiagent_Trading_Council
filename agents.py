def technical_agent(latest, patterns, sr, volume, trend_str, memory):
    return f"""You are a professional technical analyst. Give a precise signal.

Recent decisions:
{memory}

--- INDICATORS ---
Price:       ${latest['Close']:.2f}
RSI(14):     {latest['rsi']:.1f}  (oversold<30, overbought>70)
MACD Hist:   {latest['macd_hist']:.4f}  (positive=bullish momentum)
EMA Trend:   {"Bullish (EMA9>EMA20>EMA50)" if latest['ema9']>latest['ema20']>latest['ema50'] else "Bearish (EMA9<EMA20<EMA50)" if latest['ema9']<latest['ema20']<latest['ema50'] else "Mixed EMAs"}
ADX:         {latest['adx']:.1f}  (>25=trending, <20=ranging)
Stoch K/D:   {latest['stoch_k']:.1f} / {latest['stoch_d']:.1f}
BB Width:    {latest['bb_width']:.4f}
ATR:         {latest['atr']:.2f}
S/R Zone:    {sr}
Volume:      {volume}
Trend:       {trend_str}
Patterns:    {', '.join(patterns)}

--- RULES ---
Only respond with:
Signal: BUY / SELL / WAIT
Reason: (one concise line mentioning the strongest indicator)
Confidence: high / medium / low
"""


def momentum_agent(latest):
    macd_signal = "Bullish" if latest['macd_hist'] > 0 else "Bearish"
    stoch_signal = "Oversold" if latest['stoch_k'] < 20 else "Overbought" if latest['stoch_k'] > 80 else "Neutral"
    return f"""You are a momentum trader. Evaluate momentum signals.

RSI(14):    {latest['rsi']:.1f}
MACD Hist:  {latest['macd_hist']:.4f} ({macd_signal})
Stoch K:    {latest['stoch_k']:.1f} ({stoch_signal})
EMA9/20:    {"Bullish" if latest['ema9'] > latest['ema20'] else "Bearish"} crossover
OBV trend:  {latest['obv']:.0f}

Only respond with:
Signal: BUY / SELL / WAIT
Reason: (one concise line)
"""


def news_agent(headlines, ticker):
    headline_text = "\n".join(f"- {h}" for h in headlines) if headlines else "No recent headlines available."
    return f"""You are a market sentiment analyst for {ticker}.

Recent headlines:
{headline_text}

Analyze sentiment specifically for {ticker}. Only respond with:
Sentiment: Positive / Neutral / Negative
Impact: Bullish / Bearish / None
Key factor: (one line summary)
"""


def risk_agent(latest, volume, ticker):
    atr_pct = (latest['atr'] / latest['Close']) * 100
    return f"""You are a risk manager assessing {ticker}.

RSI:         {latest['rsi']:.1f}
ATR %:       {atr_pct:.2f}%  (volatility measure)
Volume:      {volume}
ADX:         {latest['adx']:.1f}
BB Width:    {latest['bb_width']:.4f}

High ATR% (>3%) = high volatility risk.
ADX < 15 = choppy/no trend = higher risk.

Only respond with:
Risk: High / Medium / Low
Action: Trade / Avoid
Reason: (one concise line)
"""
