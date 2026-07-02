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


def _ensure_column(cursor, table_name: str, column_name: str, column_type: str):
    existing = {row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})")}
    if column_name not in existing:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


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
            entry_low REAL,
            entry_high REAL,
            interval TEXT,
            fill_status TEXT,
            filled_time TEXT,
            expiry_time TEXT,
            outcome TEXT,
            outcome_pct REAL,
            outcome_time TEXT
        )
        """)
        _ensure_column(cursor, "outcome_signals", "entry_low", "REAL")
        _ensure_column(cursor, "outcome_signals", "entry_high", "REAL")
        _ensure_column(cursor, "outcome_signals", "interval", "TEXT")
        _ensure_column(cursor, "outcome_signals", "fill_status", "TEXT")
        _ensure_column(cursor, "outcome_signals", "filled_time", "TEXT")
        _ensure_column(cursor, "outcome_signals", "expiry_time", "TEXT")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"outcome_memory.py: Failed to initialize database: {e}")


def _parse_utc(ts: str):
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _yfinance_interval(interval: str) -> str:
    interval = (interval or "").lower()
    return interval if interval in ("1m", "5m", "15m", "1h", "1d") else "1h"


def _fetch_price_path(ticker: str, start_ts: str, end_ts: datetime, interval: str):
    try:
        import yfinance as yf
    except Exception:
        return None

    try:
        start_dt = _parse_utc(start_ts)
        df = yf.download(
            ticker,
            start=start_dt.replace(tzinfo=None),
            end=end_ts.replace(tzinfo=None),
            interval=_yfinance_interval(interval),
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if df is None or df.empty:
            return None
        if getattr(df.columns, "nlevels", 1) > 1:
            df.columns = df.columns.get_level_values(0)
        cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        if len(cols) < 4:
            return None
        return df[cols].dropna()
    except Exception as e:
        print(f"outcome_memory.py: price path fetch failed for {ticker}: {e}")
        return None


def _price_touched_entry(row, entry_low, entry_high, decision):
    high = float(row["High"])
    low = float(row["Low"])
    if entry_low is None or entry_high is None:
        entry_low = entry_high = float(row.get("entry_price", 0))
    return high >= entry_low and low <= entry_high


def _entry_window(entry_price, entry_low, entry_high):
    low = entry_low if entry_low is not None else entry_price
    high = entry_high if entry_high is not None else entry_price
    return float(low), float(high)


# Proactively initialize database
init_db()


PENDING_EXPIRY_DAYS = 7


def record_signal(ticker, decision, entry_price, stop_loss, target_price,
                  confidence, rsi, adx, macd_hist, sr_zone,
                  entry_low=None, entry_high=None, interval=None, expiry_days=PENDING_EXPIRY_DAYS):
    """Save a new signal when BUY/SELL is triggered."""
    if decision == "WAIT":
        return

    try:
        conn = _get_conn()
        cursor = conn.cursor()
        
        record_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        timestamp = datetime.now(timezone.utc).isoformat()
        expiry_time = (datetime.now(timezone.utc) + timedelta(days=expiry_days)).isoformat()
        low, high = _entry_window(entry_price, entry_low, entry_high)
        
        cursor.execute("""
        INSERT INTO outcome_signals (
            id, timestamp, ticker, decision, entry_price, stop_loss, target_price,
            confidence, rsi, adx, macd_hist, sr_zone, entry_low, entry_high, interval,
            fill_status, filled_time, expiry_time, outcome, outcome_pct, outcome_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
        """, (
            record_id, timestamp, ticker, decision, round(entry_price, 4),
            round(stop_loss, 4), round(target_price, 4), confidence,
            round(rsi, 1), round(adx, 1), round(macd_hist, 6), sr_zone,
            round(low, 4) if low is not None else None,
            round(high, 4) if high is not None else None,
            interval,
            "PENDING",
            None,
            expiry_time,
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


def update_outcome(ticker, current_price, expiry_days=PENDING_EXPIRY_DAYS):
    """
    Check pending signals for ticker and mark fill + outcome status.
    Distinguishes:
    - EXPIRED_UNFILLED: price never touched the entry zone
    - EXPIRED_FILLED_NO_RESOLUTION: entry was filled, but neither stop nor target hit before expiry
    """
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        
        # Get all pending signals for this ticker
        cursor.execute("""
        SELECT id, timestamp, decision, entry_price, entry_low, entry_high, target_price, stop_loss, interval, fill_status 
        FROM outcome_signals 
        WHERE ticker = ? AND outcome IS NULL
        """, (ticker,))
        
        pending = cursor.fetchall()
        if not pending:
            conn.close()
            return

        now = datetime.now(timezone.utc)
        path_cache = {}
        
        for row in pending:
            rec_id = row["id"]
            recorded_at_str = row["timestamp"]
            dec = row["decision"]
            entry = row["entry_price"]
            entry_low = row["entry_low"]
            entry_high = row["entry_high"]
            target = row["target_price"]
            stop = row["stop_loss"]
            interval = row["interval"] or "1h"
            fill_status = row["fill_status"] or "PENDING"
            
            # Expire stale pending signals
            try:
                recorded_at = _parse_utc(recorded_at_str)
                age_days = (now - recorded_at).days
            except Exception:
                age_days = 0

            if interval not in path_cache:
                path_cache[interval] = _fetch_price_path(ticker, recorded_at_str, now, interval)

            bars = path_cache[interval]
            touched = False
            fill_time = None
            final_outcome = None
            outcome_pct = None

            if bars is not None and not bars.empty:
                # Walk the actual OHLC path once so fill and final outcome can be separated.
                for ts, bar in bars.iterrows():
                    bar_low = float(bar["Low"])
                    bar_high = float(bar["High"])
                    low, high = _entry_window(entry, entry_low, entry_high)
                    if not touched and bar_high >= low and bar_low <= high:
                        touched = True
                        fill_time = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                        fill_status = "FILLED"

                    if touched:
                        hit_target = (dec == "BUY" and bar_high >= target) or (dec == "SELL" and bar_low <= target)
                        hit_stop = (dec == "BUY" and bar_low <= stop) or (dec == "SELL" and bar_high >= stop)
                        if hit_target:
                            outcome_pct = round(((target - entry) / entry * 100) if dec == "BUY" else ((entry - target) / entry * 100), 2)
                            final_outcome = "TARGET HIT ✅"
                            break
                        if hit_stop:
                            outcome_pct = round(((stop - entry) / entry * 100) if dec == "BUY" else ((entry - stop) / entry * 100), 2)
                            final_outcome = "STOP HIT ❌"
                            break

            if final_outcome:
                cursor.execute("""
                UPDATE outcome_signals
                SET fill_status = ?, filled_time = COALESCE(filled_time, ?),
                    outcome = ?, outcome_pct = ?, outcome_time = ?
                WHERE id = ?
                """, (fill_status, fill_time, final_outcome, outcome_pct, now.isoformat(), rec_id))
                continue

            if age_days >= expiry_days:
                low, high = _entry_window(entry, entry_low, entry_high)
                if touched or (current_price >= low and current_price <= high):
                    fill_status = "FILLED" if touched or fill_status == "FILLED" else "PENDING"
                    cursor.execute("""
                    UPDATE outcome_signals
                    SET fill_status = ?, filled_time = COALESCE(filled_time, ?),
                        outcome = ?, outcome_pct = 0.0, outcome_time = ?
                    WHERE id = ?
                    """, (fill_status, fill_time, "EXPIRED_FILLED_NO_RESOLUTION", now.isoformat(), rec_id))
                else:
                    cursor.execute("""
                    UPDATE outcome_signals
                    SET fill_status = 'UNFILLED', outcome = ?, outcome_pct = 0.0, outcome_time = ?
                    WHERE id = ?
                    """, ("EXPIRED_UNFILLED", now.isoformat(), rec_id))
                
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
        SELECT outcome, outcome_pct, fill_status
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
        filled   = [r for r in records if (r["fill_status"] or "") == "FILLED"]
        unfilled = [r for r in records if r["outcome"] == "EXPIRED_UNFILLED"]
        expired_filled = [r for r in records if r["outcome"] == "EXPIRED_FILLED_NO_RESOLUTION"]
        
        win_rate = len(wins) / len(resolved) * 100 if resolved else 0
        fill_rate = len(filled) / len(records) * 100 if records else 0
        avg_win  = sum(r["outcome_pct"] for r in wins)   / len(wins)   if wins   else 0
        avg_loss = sum(r["outcome_pct"] for r in losses) / len(losses) if losses else 0
        
        return {
            "total":    len(resolved),
            "wins":     len(wins),
            "losses":   len(losses),
            "expired":  len(expired),
            "filled":   len(filled),
            "unfilled": len(unfilled),
            "expired_filled_no_resolution": len(expired_filled),
            "win_rate": round(win_rate, 1),
            "fill_rate": round(fill_rate, 1),
            "avg_win":  round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
        }
    except Exception as e:
        print(f"outcome_memory.py: Failed to get ticker stats: {e}")
        return None