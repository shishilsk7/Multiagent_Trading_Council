import ta
import pandas as pd
import numpy as np


def add_indicators(df):
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # --- Trend ---
    df["ema9"]  = ta.trend.EMAIndicator(close, 9).ema_indicator()
    df["ema20"] = ta.trend.EMAIndicator(close, 20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(close, 50).ema_indicator()

    # MACD
    macd = ta.trend.MACD(close)
    df["macd"]        = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"]   = macd.macd_diff()

    # ADX (trend strength)
    adx_ind = ta.trend.ADXIndicator(high, low, close, window=14)
    df["adx"]     = adx_ind.adx()
    df["adx_pos"] = adx_ind.adx_pos()
    df["adx_neg"] = adx_ind.adx_neg()

    # --- Momentum ---
    df["rsi"] = ta.momentum.RSIIndicator(close, window=14).rsi()

    stoch = ta.momentum.StochasticOscillator(high, low, close)
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    # --- Volatility ---
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"]   = bb.bollinger_mavg()
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    df["atr"] = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()

    # --- Support / Resistance ---
    df["support"]    = low.rolling(20).min()
    df["resistance"] = high.rolling(20).max()

    # --- Volume ---
    df["vol_ma"]    = volume.rolling(20).mean()
    df["vol_ratio"] = volume / df["vol_ma"]
    df["obv"]       = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()

    # Candlestick logic
    prev_close = close.shift(1)
    prev_open = df["Open"].shift(1)
    curr_open = df["Open"]
    curr_close = close

    # Bullish Engulfing
    df["engulfing"] = np.where(
        (prev_close < prev_open) & 
        (curr_close > curr_open) & 
        (curr_open <= prev_close) & 
        (curr_close >= prev_open), 1, 0
    )

    # Hammer
    body = abs(curr_close - curr_open)
    lower_shadow = np.minimum(curr_close, curr_open) - low
    upper_shadow = high - np.maximum(curr_close, curr_open)
    
    df["hammer"] = np.where(
        (lower_shadow > 2 * body) & 
        (upper_shadow < 0.2 * body) & 
        (body > 0), 1, 0
    )

    df.dropna(inplace=True)
    return df


def interpret_patterns(latest):
    p = []
    if latest.get("engulfing", 0) > 0:
        p.append("Bullish Engulfing")
    if latest.get("hammer", 0) > 0:
        p.append("Hammer")
    if latest.get("bb_width", 1) < 0.02:
        p.append("BB Squeeze (breakout imminent)")
    hist = latest.get("macd_hist", 0)
    if hist > 0:
        p.append("MACD Bullish Histogram")
    elif hist < 0:
        p.append("MACD Bearish Histogram")
    sk = latest.get("stoch_k", 50)
    if sk < 20:
        p.append("Stochastic Oversold")
    elif sk > 80:
        p.append("Stochastic Overbought")
    return p if p else ["No clear pattern"]


def sr_zone(latest):
    price = latest["Close"]
    if abs(price - latest["support"]) / price < 0.005:
        return "Near Support"
    if abs(price - latest["resistance"]) / price < 0.005:
        return "Near Resistance"
    if price > latest.get("bb_upper", price * 1.1):
        return "Above BB Upper (Overbought)"
    if price < latest.get("bb_lower", price * 0.9):
        return "Below BB Lower (Oversold)"
    return "Middle"


def volume_state(latest):
    ratio = latest.get("vol_ratio", 1.0)
    if ratio > 2.0:
        return "Very High Volume"
    if ratio > 1.5:
        return "High Volume"
    if ratio < 0.5:
        return "Very Low Volume"
    if ratio < 0.7:
        return "Low Volume"
    return "Normal Volume"


def trend_strength(latest):
    adx = latest.get("adx", 0)
    if adx > 40:
        return "Very Strong Trend"
    if adx > 25:
        return "Strong Trend"
    if adx > 20:
        return "Moderate Trend"
    return "Weak/No Trend (ranging)"
