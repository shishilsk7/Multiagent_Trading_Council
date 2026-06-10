"""
memory.py — Short-term decision memory (last 10 decisions).
Upgraded to SQLite for thread-safe concurrent writes.
"""

import sqlite3
import os
from datetime import datetime

DB_FILE = "mtc.db"


def _get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS decision_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT,
            decision TEXT,
            price REAL,
            confidence INTEGER
        )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"memory.py: Failed to initialize database: {e}")


# Initialize database
init_db()


def load():
    """Load the last 10 decisions from the database."""
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT time, decision, price, confidence 
        FROM decision_memory 
        ORDER BY id DESC LIMIT 10
        """)
        rows = cursor.fetchall()
        conn.close()
        
        # Return in chronological order (oldest to newest) to match old list behavior
        mem = []
        for r in reversed(rows):
            mem.append({
                "time":       r["time"],
                "decision":   r["decision"],
                "price":      r["price"],
                "confidence": r["confidence"],
            })
        return mem
    except Exception as e:
        print(f"memory.py: Failed to load decision memory: {e}")
        return []


def add(mem, decision, price, confidence):
    """Add a new decision to the memory and keep size limited to 100 entries."""
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        cursor.execute("""
        INSERT INTO decision_memory (time, decision, price, confidence) 
        VALUES (?, ?, ?, ?)
        """, (time_str, decision, round(price, 4), confidence))
        
        # Limit rows to 100 to avoid DB growing infinitely
        cursor.execute("""
        DELETE FROM decision_memory 
        WHERE id NOT IN (
            SELECT id FROM decision_memory ORDER BY id DESC LIMIT 100
        )
        """)
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"memory.py: Failed to save decision: {e}")
        
    # Append to local mem list parameter to keep in-memory sync'd
    mem.append({
        "time":       datetime.now().strftime("%Y-%m-%d %H:%M"),
        "decision":   decision,
        "price":      round(price, 4),
        "confidence": confidence,
    })


def summarize(mem):
    """Summarize the last 5 decisions."""
    if not mem:
        return "No recent decisions."
    lines = [
        f"{m['time']} → {m['decision']} @ ${m['price']:,.2f} ({m['confidence']}% conf)"
        for m in mem[-5:]
    ]
    return "\n".join(lines)
