"""
Outcome Memory — stores past trade signals and tracks actual results.
Upgraded to SQLite for thread-safe concurrent writes during parallel scans.
"""

import sqlite3
import os
from datetime import datetime, timezone, timedelta

DB_FILE = "mtc.db"


def _get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        # Create signals table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS outcome_signals (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            ticker TEXT,
            decision TEXT,
            entry_price REAL,
            stop_loss REAL,
            target_price REAL,
            confidence INTEGER,
            rsi REAL,
            adx REAL,
            macd_hist REAL,
            sr_zone TEXT,
            outcome TEXT,
            outcome_pct REAL,
            outcome_time TEXT
        )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"outcome_memory.py: Failed to initialize database: {e}")


# Proactively initialize database
init_db()


def record_signal(ticker, decision, entry_price, stop_loss, target_price,
                  confidence, rsi, adx, macd_hist, sr_zone):
    """Save a new signal when BUY/SELL is triggered."""
    if decision == "WAIT":
        return

    try:
        conn = _get_conn()
        cursor = conn.cursor()
        
        record_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        timestamp = datetime.now(timezone.utc).isoformat()
        
        cursor.execute("""
        INSERT INTO outcome_signals (
            id, timestamp, ticker, decision, entry_price, stop_loss, target_price,
            confidence, rsi, adx, macd_hist, sr_zone, outcome, outcome_pct, outcome_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
        """, (
            record_id, timestamp, ticker, decision, round(entry_price, 4),
            round(stop_loss, 4), round(target_price, 4), confidence,
            round(rsi, 1), round(adx, 1), round(macd_hist, 6), sr_zone
        ))
        
        # Enforce keeping last 20 records per ticker to prevent DB bloating
        cursor.execute("""
        DELETE FROM outcome_signals 
        WHERE ticker = ? AND id NOT IN (
            SELECT id FROM outcome_signals WHERE ticker = ? ORDER BY id DESC LIMIT 20
        )
        """, (ticker, ticker))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"outcome_memory.py: Failed to record signal: {e}")


PENDING_EXPIRY_DAYS = 7


def update_outcome(ticker, current_price, expiry_days=PENDING_EXPIRY_DAYS):
    """
    Check pending signals for ticker and mark outcome if target/stop hit.
    Also expires signals older than expiry_days that never hit target or stop.
    """
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        
        # Get all pending signals for this ticker
        cursor.execute("""
        SELECT id, timestamp, decision, entry_price, target_price, stop_loss 
        FROM outcome_signals 
        WHERE ticker = ? AND outcome IS NULL
        """, (ticker,))
        
        pending = cursor.fetchall()
        if not pending:
            conn.close()
            return

        now = datetime.now(timezone.utc)
        
        for row in pending:
            rec_id = row["id"]
            recorded_at_str = row["timestamp"]
            dec = row["decision"]
            entry = row["entry_price"]
            target = row["target_price"]
            stop = row["stop_loss"]
            
            # Expire stale pending signals
            try:
                recorded_at = datetime.fromisoformat(recorded_at_str)
                age_days = (now - recorded_at).days
            except Exception:
                age_days = 0
                
            if age_days >= expiry_days:
                cursor.execute("""
                UPDATE outcome_signals 
                SET outcome = ?, outcome_pct = 0.0, outcome_time = ? 
                WHERE id = ?
                """, (f"EXPIRED ⏰ ({age_days}d — no hit)", now.isoformat(), rec_id))
                continue
                
            hit_target = (dec == "BUY"  and current_price >= target) or \
                         (dec == "SELL" and current_price <= target)
            hit_stop   = (dec == "BUY"  and current_price <= stop)   or \
                         (dec == "SELL" and current_price >= stop)
                         
            if hit_target:
                pct = ((target - entry) / entry * 100) if dec == "BUY" else ((entry - target) / entry * 100)
                cursor.execute("""
                UPDATE outcome_signals 
                SET outcome = 'TARGET HIT ✅', outcome_pct = ?, outcome_time = ? 
                WHERE id = ?
                """, (round(pct, 2), now.isoformat(), rec_id))
            elif hit_stop:
                pct = ((stop - entry) / entry * 100) if dec == "BUY" else ((entry - stop) / entry * 100)
                cursor.execute("""
                UPDATE outcome_signals 
                SET outcome = 'STOP HIT ❌', outcome_pct = ?, outcome_time = ? 
                WHERE id = ?
                """, (round(pct, 2), now.isoformat(), rec_id))
                
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"outcome_memory.py: Failed to update outcomes: {e}")


def get_similar_past_signals(ticker, decision, rsi, macd_hist, sr_zone, n=3):
    """
    Find past signals with similar conditions and return their outcomes.
    Used to show users: 'Last time this happened, result was X'
    """
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
        SELECT id, timestamp, decision, entry_price, target_price, stop_loss, 
               confidence, rsi, adx, macd_hist, sr_zone, outcome, outcome_pct, outcome_time
        FROM outcome_signals 
        WHERE ticker = ? AND decision = ? AND outcome IS NOT NULL
        """, (ticker, decision))
        
        resolved = cursor.fetchall()
        conn.close()
        
        if not resolved:
            return []
            
        scored = []
        for r in resolved:
            score = 0
            r_rsi = r["rsi"] if r["rsi"] is not None else 50
            if abs(r_rsi - rsi) < 10:    score += 2
            if abs(r_rsi - rsi) < 5:     score += 1
            
            r_macd = r["macd_hist"] if r["macd_hist"] is not None else 0
            if (macd_hist > 0) == (r_macd > 0): score += 2
            
            if r["sr_zone"] == sr_zone: score += 2
            
            record_dict = {
                "id":           r["id"],
                "timestamp":    r["timestamp"],
                "decision":     r["decision"],
                "entry_price":  r["entry_price"],
                "stop_loss":    r["stop_loss"],
                "target_price": r["target_price"],
                "confidence":   r["confidence"],
                "indicators": {
                    "rsi":       r["rsi"],
                    "adx":       r["adx"],
                    "macd_hist":  r["macd_hist"],
                    "sr_zone":   r["sr_zone"],
                },
                "outcome":      r["outcome"],
                "outcome_pct":  r["outcome_pct"],
                "outcome_time": r["outcome_time"],
            }
            scored.append((score, record_dict))
            
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for score, r in scored[:n] if score >= 2]
    except Exception as e:
        print(f"outcome_memory.py: Failed to get similar past signals: {e}")
        return []


def get_ticker_stats(ticker):
    """Win rate and average return for a ticker. Excludes expired signals."""
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
        SELECT outcome, outcome_pct 
        FROM outcome_signals 
        WHERE ticker = ? AND outcome IS NOT NULL
        """, (ticker,))
        
        records = cursor.fetchall()
        conn.close()
        
        if not records:
            return None
            
        resolved = [r for r in records if "EXPIRED" not in r["outcome"]]
        wins     = [r for r in resolved if "TARGET" in r["outcome"]]
        losses   = [r for r in resolved if "STOP"   in r["outcome"]]
        expired  = [r for r in records  if "EXPIRED" in r["outcome"]]
        
        win_rate = len(wins) / len(resolved) * 100 if resolved else 0
        avg_win  = sum(r["outcome_pct"] for r in wins)   / len(wins)   if wins   else 0
        avg_loss = sum(r["outcome_pct"] for r in losses) / len(losses) if losses else 0
        
        return {
            "total":    len(resolved),
            "wins":     len(wins),
            "losses":   len(losses),
            "expired":  len(expired),
            "win_rate": round(win_rate, 1),
            "avg_win":  round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
        }
    except Exception as e:
        print(f"outcome_memory.py: Failed to get ticker stats: {e}")
        return None