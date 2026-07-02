"""
Market calendar helpers.

Indian market status uses NSE weekdays + holiday calendar.
Other non-crypto assets are treated as weekday-only for now so the app
does not generate live trades on obvious closed sessions.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import re

import requests

from stocks import UNIVERSE, is_indian

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))


_NSE_HOLIDAY_URL = "https://www.nseindia.com/api/holiday-master?type=trading&year={year}"


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(value[:10], fmt).date()
            except Exception:
                pass
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except Exception:
                return None
    return None


def _walk_dates(payload):
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in ("tradingdate", "date"):
                parsed = _parse_date(value)
                if parsed:
                    yield parsed
            yield from _walk_dates(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_dates(item)
    elif isinstance(payload, str):
        parsed = _parse_date(payload)
        if parsed:
            yield parsed


@lru_cache(maxsize=8)
def _nse_holidays(year: int):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://www.nseindia.com/",
    }
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=5)
        response = session.get(_NSE_HOLIDAY_URL.format(year=year), headers=headers, timeout=8)
        response.raise_for_status()
        payload = response.json()
        return set(_walk_dates(payload))
    except Exception:
        return set()


def _is_crypto(ticker: str) -> bool:
    name, category = UNIVERSE.get(ticker, (ticker, ""))
    return category == "Crypto"


def _next_open_ist(now_ist: datetime):
    probe = now_ist.date() + timedelta(days=1)
    for _ in range(14):
        if probe.weekday() < 5 and probe not in _nse_holidays(probe.year):
            return probe
        probe += timedelta(days=1)
    return probe


def get_market_status(ticker: str, now: datetime | None = None):
    """
    Return a normalized market-status dict for the asset.
    """
    now_utc = now or datetime.now(timezone.utc)
    name, category = UNIVERSE.get(ticker, (ticker, ""))

    if _is_crypto(ticker):
        return {
            "is_open": True,
            "closed": False,
            "reason": "",
            "message": "",
            "next_open": None,
            "asset_class": category,
        }

    if is_indian(ticker):
        now_ist = now_utc.astimezone(IST)
        holiday_dates = _nse_holidays(now_ist.year)
        if now_ist.weekday() >= 5:
            next_open = _next_open_ist(now_ist)
            return {
                "is_open": False,
                "closed": True,
                "reason": "NSE weekend closure",
                "message": f"NSE closed — reopens Monday 9:15 AM IST" if now_ist.weekday() == 5 else "NSE closed — reopens next trading session at 9:15 AM IST",
                "next_open": next_open,
                "asset_class": category,
            }
        if now_ist.date() in holiday_dates:
            next_open = _next_open_ist(now_ist)
            return {
                "is_open": False,
                "closed": True,
                "reason": f"NSE holiday on {now_ist.date().isoformat()}",
                "message": "NSE closed today for a trading holiday — reopens next trading session at 9:15 AM IST",
                "next_open": next_open,
                "asset_class": category,
            }
        return {
            "is_open": True,
            "closed": False,
            "reason": "",
            "message": "",
            "next_open": None,
            "asset_class": category,
        }

    # For non-crypto, non-Indian assets: avoid obvious weekend trading signals.
    if now_utc.weekday() >= 5:
        return {
            "is_open": False,
            "closed": True,
            "reason": "Weekend closure",
            "message": "Market closed — reopens next trading session",
            "next_open": None,
            "asset_class": category,
        }

    return {
        "is_open": True,
        "closed": False,
        "reason": "",
        "message": "",
        "next_open": None,
        "asset_class": category,
    }
