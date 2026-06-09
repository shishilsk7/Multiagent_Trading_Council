"""
memory.py — Short-term decision memory (last 10 decisions).

Fixes from v1:
- Removed duplicate function definitions
- Added date stamp alongside time for cross-day context
"""

import json
import os
from datetime import datetime

FILE = "decision_memory.json"


def load():
    if not os.path.exists(FILE):
        return []
    try:
        return json.load(open(FILE))
    except Exception:
        return []


def save(mem):
    try:
        tmp = FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(mem[-10:], f, indent=2)
        os.replace(tmp, FILE)
    except Exception:
        pass


def add(mem, decision, price, confidence):
    mem.append({
        "time":       datetime.now().strftime("%Y-%m-%d %H:%M"),
        "decision":   decision,
        "price":      round(price, 4),
        "confidence": confidence,
    })
    save(mem)


def summarize(mem):
    if not mem:
        return "No recent decisions."
    lines = [
        f"{m['time']} → {m['decision']} @ ${m['price']:,.2f} ({m['confidence']}% conf)"
        for m in mem[-5:]
    ]
    return "\n".join(lines)
