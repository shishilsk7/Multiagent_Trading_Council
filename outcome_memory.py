"""
Outcome Memory — stores past trade signals and tracks actual results.

Flow:
1. When a BUY/SELL signal fires, save it with entry price + targets
2. On next analysis of same ticker, check if previous signal hit target/stop
3. Surface the outcome to users: "Last time RSI<35 + MACD>0 on NVDA → BUY → +2.1% in 6h"
"""

import json
import os
from datetime import datetime, timezone

FILE = "outcome_memory.json"


def _load():
    if not os.path.exists(FILE):
        return {}
    try:
        return json.load(open(FILE))
    except Exception:
        return {}


def _save(data):
    try:
        json.dump(data, open(FILE, "w"), indent=2)
    except Exception:
        pass


def record_signal(ticker, decision, entry_price, stop_loss, target_price,
                  confidence, rsi, adx, macd_hist, sr_zone):
    """Save a new signal when BUY/SELL is triggered."""
    if decision == "WAIT":
        return

    data = _load()
    if ticker not in data:
        data[ticker] = []

    record = {
        "id":           datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "decision":     decision,
        "entry_price":  round(entry_price, 4),
        "stop_loss":    round(stop_loss, 4),
        "target_price": round(target_price, 4),
        "confidence":   confidence,
        "indicators": {
            "rsi":      round(rsi, 1),
            "adx":      round(adx, 1),
            "macd_hist": round(macd_hist, 6),
            "sr_zone":  sr_zone,
        },
        "outcome":      None,   # filled in later
        "outcome_pct":  None,
        "outcome_time": None,
    }

    # Keep last 20 records per ticker
    data[ticker].append(record)
    data[ticker] = data[ticker][-20:]
    _save(data)


def update_outcome(ticker, current_price):
    """
    Check pending signals for ticker and mark outcome if target/stop hit.
    Called automatically at the start of each analysis.
    """
    data = _load()
    if ticker not in data:
        return

    changed = False
    for rec in data[ticker]:
        if rec["outcome"] is not None:
            continue  # already resolved

        entry  = rec["entry_price"]
        target = rec["target_price"]
        stop   = rec["stop_loss"]
        dec    = rec["decision"]

        hit_target = (dec == "BUY"  and current_price >= target) or \
                     (dec == "SELL" and current_price <= target)
        hit_stop   = (dec == "BUY"  and current_price <= stop)   or \
                     (dec == "SELL" and current_price >= stop)

        if hit_target:
            pct = ((target - entry) / entry * 100) if dec == "BUY" \
                  else ((entry - target) / entry * 100)
            rec["outcome"]      = "TARGET HIT ✅"
            rec["outcome_pct"]  = round(pct, 2)
            rec["outcome_time"] = datetime.now(timezone.utc).isoformat()
            changed = True
        elif hit_stop:
            pct = ((stop - entry) / entry * 100) if dec == "BUY" \
                  else ((entry - stop) / entry * 100)
            rec["outcome"]      = "STOP HIT ❌"
            rec["outcome_pct"]  = round(pct, 2)
            rec["outcome_time"] = datetime.now(timezone.utc).isoformat()
            changed = True

    if changed:
        _save(data)


def get_similar_past_signals(ticker, decision, rsi, macd_hist, sr_zone, n=3):
    """
    Find past signals with similar conditions and return their outcomes.
    Used to show users: 'Last time this happened, result was X'
    """
    data = _load()
    records = data.get(ticker, [])

    # Only look at resolved records
    resolved = [r for r in records if r["outcome"] is not None]
    if not resolved:
        return []

    # Score similarity
    scored = []
    for r in resolved:
        if r["decision"] != decision:
            continue
        score = 0
        # RSI in same zone
        r_rsi = r["indicators"].get("rsi", 50)
        if abs(r_rsi - rsi) < 10:    score += 2
        if abs(r_rsi - rsi) < 5:     score += 1
        # MACD same direction
        r_macd = r["indicators"].get("macd_hist", 0)
        if (macd_hist > 0) == (r_macd > 0): score += 2
        # Same SR zone
        if r["indicators"].get("sr_zone") == sr_zone: score += 2

        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:n] if _ >= 2]  # only return meaningful matches


def get_ticker_stats(ticker):
    """Win rate and average return for a ticker."""
    data = _load()
    records = [r for r in data.get(ticker, []) if r["outcome"] is not None]

    if not records:
        return None

    wins   = [r for r in records if "TARGET" in r["outcome"]]
    losses = [r for r in records if "STOP"   in r["outcome"]]

    win_rate   = len(wins) / len(records) * 100
    avg_win    = sum(r["outcome_pct"] for r in wins)   / len(wins)   if wins   else 0
    avg_loss   = sum(r["outcome_pct"] for r in losses) / len(losses) if losses else 0

    return {
        "total":    len(records),
        "wins":     len(wins),
        "losses":   len(losses),
        "win_rate": round(win_rate, 1),
        "avg_win":  round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
    }