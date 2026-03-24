import json
import os
from datetime import datetime


FILE = "decision_memory.json"


def load():
    if not os.path.exists(FILE):
        return []
    return json.load(open(FILE))


def save(mem):
    json.dump(mem[-10:], open(FILE, "w"), indent=2)


def add(mem, decision, price, confidence):
    mem.append(
        {
            "time": datetime.now().strftime("%H:%M"),
            "decision": decision,
            "price": price,
            "confidence": confidence,
        }
    )
    save(mem)


def summarize(mem):
    return (
        "\n".join(
            [f"{m['time']} {m['decision']} ({m['confidence']}%)" for m in mem[-5:]]
        )
        if mem
        else "None"
    )
import json, os
from datetime import datetime

FILE = "decision_memory.json"

def load():
    if not os.path.exists(FILE): return []
    return json.load(open(FILE))

def save(mem):
    json.dump(mem[-10:], open(FILE, "w"), indent=2)

def add(mem, decision, price, confidence):
    mem.append({
        "time": datetime.now().strftime("%H:%M"),
        "decision": decision,
        "price": price,
        "confidence": confidence
    })
    save(mem)

def summarize(mem):
    return "\n".join(
        [f"{m['time']} {m['decision']} ({m['confidence']}%)" for m in mem[-5:]]
    ) if mem else "None"

