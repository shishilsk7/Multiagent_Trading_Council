"""
Market calendar helpers.

Indian market status uses NSE weekdays + holiday calendar.
Other non-crypto assets are treated as weekday-only for now so the app
does not generate live trades on obvious closed sessions.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, time
from functools import lru_cache
import re

import requests

from stocks import UNIVERSE, is_indian

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
    EST = ZoneInfo("America/New_York")
except Exception:
    IST = timezone(timedelta(hours=5, minutes=30))
    EST = timezone(timedelta(hours=-5))


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
    return category == "Crypto" or any(x in ticker.upper() for x in ["BTC", "ETH", "SOL", "BNB", "XRP"])


def _next_open_ist(now_ist: datetime):
    probe = now_ist.date() + timedelta(days=1)
    for _ in range(14):
        if probe.weekday() < 5 and probe not in _nse_holidays(probe.year):
            return probe
        probe += timedelta(days=1)
    return probe


def _is_us_holiday(d: date) -> bool:
    year = d.year
    month = d.month
    day = d.day
    
    if year == 2026:
        holidays = {
            (1, 1),    # New Year's Day
            (1, 19),   # MLK Day
            (2, 16),   # Presidents' Day
            (4, 3),    # Good Friday
            (5, 25),   # Memorial Day
            (6, 19),   # Juneteenth
            (7, 3),    # Independence Day (observed)
            (9, 7),    # Labor Day
            (11, 26),  # Thanksgiving
            (12, 25),  # Christmas
        }
        return (month, day) in holidays
    elif year == 2027:
        holidays = {
            (1, 1),    # New Year's Day
            (1, 18),   # MLK Day
            (2, 15),   # Presidents' Day
            (3, 26),   # Good Friday
            (5, 31),   # Memorial Day
            (6, 18),   # Juneteenth (observed)
            (7, 5),    # Independence Day (observed)
            (9, 6),    # Labor Day
            (11, 25),  # Thanksgiving
            (12, 24),  # Christmas (observed)
        }
        return (month, day) in holidays
        
    if (month == 1 and day == 1) or (month == 7 and day == 4) or (month == 12 and day == 25):
        return True
    return False


def _is_commodity_futures_open(now_ny: datetime) -> tuple[bool, str, str]:
    wd = now_ny.weekday()
    t = now_ny.time()
    
    if wd == 5:  # Saturday
        return False, "COMEX weekend closure", "COMEX futures closed on weekends"
    if wd == 6 and t < time(18, 0):  # Sunday before 6 PM ET
        return False, "COMEX weekend closure", "COMEX futures closed until Sunday 6:00 PM ET"
    if wd == 4 and t >= time(17, 0):  # Friday after 5 PM ET
        return False, "COMEX weekend closure", "COMEX futures closed until Sunday 6:00 PM ET"
        
    if time(17, 0) <= t < time(18, 0):
        return False, "COMEX daily maintenance", "COMEX futures closed for daily maintenance (5:00 PM - 6:00 PM ET)"
        
    return True, "", ""


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
        
        # 1. Check weekends
        if now_ist.weekday() >= 5:
            next_open = _next_open_ist(now_ist)
            return {
                "is_open": False,
                "closed": True,
                "reason": "NSE weekend closure",
                "message": "NSE closed — reopens Monday 9:15 AM IST" if now_ist.weekday() == 5 else "NSE closed — reopens next trading session at 9:15 AM IST",
                "next_open": next_open,
                "asset_class": category,
            }
            
        # 2. Check holidays
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
            
        # 3. Check hours
        t = now_ist.time()
        if not (time(9, 15) <= t <= time(15, 30)):
            if t < time(9, 15):
                next_open = now_ist.date()
            else:
                next_open = _next_open_ist(now_ist)
            return {
                "is_open": False,
                "closed": True,
                "reason": "NSE outside trading hours",
                "message": "NSE closed — trading hours are 9:15 AM to 3:30 PM IST",
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

    # Commodity Futures (GC=F, SI=F)
    if ticker in ("GC=F", "SI=F"):
        now_ny = now_utc.astimezone(EST)
        is_open, reason, msg = _is_commodity_futures_open(now_ny)
        if not is_open:
            return {
                "is_open": False,
                "closed": True,
                "reason": reason,
                "message": msg,
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

    # For US equities / ETFs (US Stocks, GLD, SLV)
    now_ny = now_utc.astimezone(EST)
    
    # 1. Check weekends
    if now_ny.weekday() >= 5:
        return {
            "is_open": False,
            "closed": True,
            "reason": "US market weekend closure",
            "message": "US markets closed — reopens Monday 9:30 AM ET",
            "next_open": None,
            "asset_class": category,
        }
        
    # 2. Check holidays
    if _is_us_holiday(now_ny.date()):
        return {
            "is_open": False,
            "closed": True,
            "reason": f"US market holiday on {now_ny.date().isoformat()}",
            "message": "US markets closed today for a trading holiday — reopens next trading session at 9:30 AM ET",
            "next_open": None,
            "asset_class": category,
        }
        
    # 3. Check hours
    t = now_ny.time()
    if not (time(9, 30) <= t <= time(16, 0)):
        return {
            "is_open": False,
            "closed": True,
            "reason": "US market outside trading hours",
            "message": "US markets closed — trading hours are 9:30 AM to 4:00 PM ET",
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


def get_next_trade_date(ticker: str, now: datetime | None = None):
    """
    Return the next valid session date for the asset class.
    Useful for GTD expiry on manual order tickets.
    """
    now_utc = now or datetime.now(timezone.utc)
    if _is_crypto(ticker):
        return (now_utc.date() + timedelta(days=1)).isoformat()

    if is_indian(ticker):
        now_ist = now_utc.astimezone(IST)
        probe = now_ist.date() + timedelta(days=1)
        for _ in range(14):
            if probe.weekday() < 5 and probe not in _nse_holidays(probe.year):
                return probe.isoformat()
            probe += timedelta(days=1)
        return probe.isoformat()

    probe = now_utc.date() + timedelta(days=1)
    while probe.weekday() >= 5:
        probe += timedelta(days=1)
    return probe.isoformat()
