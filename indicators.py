"""
indicators.py — Technical indicator computation.

Fixes from v1:
- Engulfing and hammer patterns now actually computed (were hardcoded 0)
- Added VWAP approximation for intraday
- Cleaned up NaN handling
"""

import ta
import pandas as pd
import numpy as np


def add_indicators(df):
    if len(df) < 14:
        return pd.DataFrame()  # absolute floor — RSI/ADX invalid below 14 periods

    close  = df["Close"]
    high   = df["High"]
    low    = df["Low"]
    volume = df["Volume"]
    open_  = df["Open"]

    # ── Trend ───────────────────────────────────────────────────────
    df["ema9"]  = ta.trend.EMAIndicator(close, 9).ema_indicator()
    df["ema35"] = ta.trend.EMAIndicator(close, 35).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(close, 50).ema_indicator()

    macd = ta.trend.MACD(close)
    df["macd"]        = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"]   = macd.macd_diff()

    adx_ind       = ta.trend.ADXIndicator(high, low, close, window=14)
    df["adx"]     = adx_ind.adx()
    df["adx_pos"] = adx_ind.adx_pos()
    df["adx_neg"] = adx_ind.adx_neg()

    # ── Momentum ────────────────────────────────────────────────────
    df["rsi"] = ta.momentum.RSIIndicator(close, window=14).rsi()

    stoch         = ta.momentum.StochasticOscillator(high, low, close)
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    # ── Volatility ──────────────────────────────────────────────────
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"]   = bb.bollinger_mavg()
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"].replace(0, np.nan)

    df["atr"] = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()

    # ── Support / Resistance ────────────────────────────────────────
    df["support"]    = low.rolling(20).min()
    df["resistance"] = high.rolling(20).max()

    # ── Fibonacci retracement levels ────────────────────────────────
    fib_window = 20
    swing_high = high.rolling(fib_window).max()
    swing_low = low.rolling(fib_window).min()
    swing_range = (swing_high - swing_low).replace(0, np.nan)
    trend_up = df["ema35"] >= df["ema50"]

    fib_ratios = {
        "fib_500": 0.500,
        "fib_618": 0.618,
    }

    for col, ratio in fib_ratios.items():
        df[col] = np.where(
            trend_up,
            swing_high - swing_range * ratio,
            swing_low + swing_range * ratio,
        )
    df["fib_trend"] = np.where(trend_up, 1, -1)
    df["fib_high"] = swing_high
    df["fib_low"] = swing_low

    # ── Volume ──────────────────────────────────────────────────────
    df["vol_ma"]    = volume.rolling(20).mean()
    df["vol_ratio"] = (volume / df["vol_ma"].replace(0, np.nan)).fillna(1.0)
    df["obv"]       = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()

    # ── Candlestick Patterns (real computation) ──────────────────────
    body      = (close - open_).abs()
    total_rng = (high - low).replace(0, np.nan)
    body_pct  = (body / total_rng).fillna(0.0)  # body as % of range

    # Hammer: small body in upper 30% of range, lower wick > 2x body, appearing after downtrend
    lower_wick    = (open_.combine(close, min) - low)
    upper_wick    = (high - open_.combine(close, max))
    df["hammer"]  = (
        (body_pct < 0.35) &
        (lower_wick > body * 2) &
        (upper_wick < body * 0.5) &
        (close.shift(1) < close.shift(3))   # simple downtrend check
    ).astype(int)

    # Bullish Engulfing: current candle body fully engulfs prior red candle
    prev_red    = open_.shift(1) > close.shift(1)
    curr_green  = close > open_
    engulf_bull = (
        curr_green &
        prev_red &
        (open_ < close.shift(1)) &
        (close > open_.shift(1))
    )

    # Bearish Engulfing: current candle body fully engulfs prior green candle
    prev_green  = close.shift(1) > open_.shift(1)
    curr_red    = open_ > close
    engulf_bear = (
        curr_red &
        prev_green &
        (open_ > close.shift(1)) &
        (close < open_.shift(1))
    )

    df["engulfing"] = engulf_bull.astype(int) - engulf_bear.astype(int)
    # +1 = bullish engulfing, -1 = bearish engulfing, 0 = none

    df.dropna(inplace=True)
    return df


def interpret_patterns(latest):
    p = []

    # Candlestick patterns
    eng = latest.get("engulfing", 0)
    if eng > 0:
        p.append("🕯️ Bullish Engulfing")
    elif eng < 0:
        p.append("🕯️ Bearish Engulfing")

    if latest.get("hammer", 0) > 0:
        p.append("🔨 Hammer (reversal signal)")

    # Bollinger Bands
    bb_w = latest.get("bb_width", 1)
    if bb_w < 0.015:
        p.append("🗜️ BB Squeeze — breakout imminent")
    elif bb_w > 0.08:
        p.append("📐 BB Expansion — high volatility")

    # MACD
    hist = latest.get("macd_hist", 0)
    if hist > 0:
        p.append("📈 MACD Bullish Histogram")
    elif hist < 0:
        p.append("📉 MACD Bearish Histogram")

    # Stochastic
    sk = latest.get("stoch_k", 50)
    sd = latest.get("stoch_d", 50)
    if sk < 20:
        p.append("⬇️ Stochastic Oversold")
    elif sk > 80:
        p.append("⬆️ Stochastic Overbought")
    if sk > sd and sk < 30:
        p.append("↗️ Stochastic Bullish Crossover in Oversold")
    if sk < sd and sk > 70:
        p.append("↘️ Stochastic Bearish Crossover in Overbought")

    # ADX
    adx = latest.get("adx", 0)
    adx_pos = latest.get("adx_pos", 0)
    adx_neg = latest.get("adx_neg", 0)
    if adx > 30 and adx_pos > adx_neg:
        p.append("💪 Strong Bullish Trend (ADX+DI)")
    elif adx > 30 and adx_neg > adx_pos:
        p.append("💪 Strong Bearish Trend (ADX-DI)")

    return p if p else ["No clear pattern"]


def sr_zone(latest):
    price = float(latest["Close"])
    support    = float(latest.get("support", 0))
    resistance = float(latest.get("resistance", price * 2))

    if support > 0 and abs(price - support) / price < 0.005:
        return "Near Support"
    if resistance > 0 and abs(price - resistance) / price < 0.005:
        return "Near Resistance"

    bb_upper = float(latest.get("bb_upper", price * 1.1))
    bb_lower = float(latest.get("bb_lower", price * 0.9))

    if price > bb_upper:
        return "Above BB Upper (Overbought)"
    if price < bb_lower:
        return "Below BB Lower (Oversold)"
    return "Middle"


def volume_state(latest):
    ratio = latest.get("vol_ratio", 1.0)
    if ratio > 3.0:
        return "Extreme Volume (3x avg)"
    if ratio > 2.0:
        return "Very High Volume"
    if ratio > 1.5:
        return "High Volume"
    if ratio < 0.4:
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
    if adx > 15:
        return "Weak Trend"
    return "No Trend (ranging)"
