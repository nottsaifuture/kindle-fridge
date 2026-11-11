"""Fetch the weather and calendar data shown on the dashboard."""

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "kindle-fridge-dashboard/1.0"


def _get(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


# ---------------------------------------------------------------- weather


@dataclass
class Hour:
    time: datetime
    temp: float
    code: int
    rain: int
    is_day: bool


@dataclass
class Day:
    date: date
    code: int
    t_max: float
    t_min: float
    rain: int
    sunrise: datetime
    sunset: datetime


@dataclass
class Weather:
    temp: float
    feels: float
    humidity: int
    wind: float
    code: int
    is_day: bool
    hours: list
    days: list


RAIN_CODE, DRIZZLE_CODE = 61, 51  # WMO "slight rain", "light drizzle"


def _with_rain(code, chance, mm, min_mm, cfg):
    """Show rain in the icon when rain is likely, even if the forecast code is
    only cloudy (Open-Meteo's code describes the sky, so a cloudy hour with a
    60% chance of rain would otherwise show plain clouds).

    - rain icon: chance >= "rain_icon_percent" (default 60) or at least
      min_mm of rain forecast
    - light-rain (drizzle) icon: chance >= "drizzle_icon_percent" (default 30)
    """
    if code >= 51:  # already drizzle, rain, snow, showers or thunder
        return code
    chance, mm = chance or 0, mm or 0
    if chance >= cfg.get("rain_icon_percent", 60) or mm >= min_mm:
        return RAIN_CODE
    if chance >= cfg.get("drizzle_icon_percent", 30):
        return DRIZZLE_CODE
    return code


def fetch_weather(cfg, now):
    params = {
        "latitude": cfg["latitude"],
        "longitude": cfg["longitude"],
        "timezone": cfg["timezone"],
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
        "weather_code,wind_speed_10m,is_day,precipitation",
        "hourly": "temperature_2m,weather_code,precipitation_probability,precipitation,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max,precipitation_sum,sunrise,sunset",
        "forecast_days": 4,
        "wind_speed_unit": "kmh",
    }
    raw = json.loads(_get(OPEN_METEO_URL + "?" + urllib.parse.urlencode(params)))
    tz = ZoneInfo(cfg["timezone"])

    def local(text):
        return datetime.fromisoformat(text).replace(tzinfo=tz)

    current = raw["current"]
    hourly = raw["hourly"]
    daily = raw["daily"]

    # Every third hour after now, for the strip under the current weather.
    hours = []
    for i, stamp in enumerate(hourly["time"]):
        t = local(stamp)
        if t <= now or (t - now).total_seconds() % (3 * 3600) >= 3600:
            continue
        hours.append(
            Hour(
                time=t,
                temp=hourly["temperature_2m"][i],
                code=_with_rain(hourly["weather_code"][i],
                                hourly["precipitation_probability"][i],
                                hourly["precipitation"][i], 0.2, cfg),
                rain=hourly["precipitation_probability"][i] or 0,
                is_day=bool(hourly["is_day"][i]),
            )
        )
        if len(hours) == 5:
            break

    days = [
        Day(
            date=date.fromisoformat(daily["time"][i]),
            # A whole day needs more than a passing drop (1 mm) to count as rainy.
            code=_with_rain(daily["weather_code"][i],
                            daily["precipitation_probability_max"][i],
                            daily["precipitation_sum"][i], 1.0, cfg),
            t_max=daily["temperature_2m_max"][i],
            t_min=daily["temperature_2m_min"][i],
            rain=daily["precipitation_probability_max"][i] or 0,
            sunrise=local(daily["sunrise"][i]),
            sunset=local(daily["sunset"][i]),
        )
        for i in range(len(daily["time"]))
    ]

    return Weather(
        temp=current["temperature_2m"],
        feels=current["apparent_temperature"],
        humidity=current["relative_humidity_2m"],
        wind=current["wind_speed_10m"],
        # Raining right now (any measurable rain) beats the sky description.
        code=_with_rain(current["weather_code"], 0, current["precipitation"], 0.1, cfg),
        is_day=bool(current["is_day"]),
        hours=hours,
        days=days,
    )


# --------------------------------------------------------------- calendar


@dataclass
class Event:
    day: date
    title: str
    start: datetime = None  # None for all-day events


def fetch_events(urls, tz, now, days):
    """Return events from today up to `days` days ahead, sorted for display.

    Each URL is a Google Calendar "secret address in iCal format".
    Returns (events, number_of_calendars_that_failed).
    """
    today = now.date()
    last_day = today + timedelta(days=days - 1)
    window_start = datetime.combine(today, time.min, tz)
    window_end = window_start + timedelta(days=days)

    events, failed, seen = [], 0, set()
    for url in urls:
        try:
            calendar = icalendar.Calendar.from_ical(_get(url))
            occurrences = recurring_ical_events.of(calendar).between(window_start, window_end)
        except Exception as error:  # one broken calendar shouldn't blank the screen
            print(f"Calendar failed: {error}")
            failed += 1
            continue

        for item in occurrences:
            if str(item.get("STATUS", "")).upper() == "CANCELLED":
                continue
            title = str(item.get("SUMMARY", "")).strip() or "（無標題）"
            start = item.decoded("DTSTART")

            if isinstance(start, datetime):
                start = start.astimezone(tz) if start.tzinfo else start.replace(tzinfo=tz)
                found = [Event(day=max(start.date(), today), title=title, start=start)]
            else:
                # All-day events end on the day *after* their last day.
                end = item.decoded("DTEND") if "DTEND" in item else start + timedelta(days=1)
                found = []
                day = max(start, today)
                while day < end and day <= last_day:
                    found.append(Event(day=day, title=title))
                    day += timedelta(days=1)

            for event in found:
                key = (event.day, event.title, event.start)
                if key not in seen:
                    seen.add(key)
                    events.append(event)

    events.sort(key=lambda e: (e.day, e.start is not None, e.start or window_start))
    return events, failed


def demo_events(tz, now):
    """Sample events for previewing the layout without a real calendar."""
    today = now.date()
    tomorrow = today + timedelta(days=1)

    def at(day, hh, mm):
        return datetime.combine(day, time(hh, mm), tz)

    return [
        Event(day=today, title="倒垃圾日"),
        Event(day=today, title="團隊會議", start=at(today, 9, 30)),
        Event(day=today, title="同朋友食晏", start=at(today, 13, 0)),
        Event(day=today, title="接小朋友放學", start=at(today, 15, 30)),
        Event(day=today, title="超級市場買嘢", start=at(today, 18, 0)),
        Event(day=tomorrow, title="睇牙醫", start=at(tomorrow, 10, 0)),
        Event(day=tomorrow, title="游水班", start=at(tomorrow, 17, 30)),
    ]


# ------------------------------------------------------------ school lunch


@dataclass
class Lunch:
    day: date
    main: str
    dessert: str


def load_lunches(path, today):
    """School lunches for today and tomorrow from the Fire dashboard's menus.json.

    The file holds {"menus": [{"weekOf": "<Monday>", "days": [5 x {main, sides,
    dessert}]}]}. Days with no menu (weekends, missing weeks) are left out, and
    a missing or unreadable file simply gives no lunches.
    """
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as f:
            menus = json.load(f)["menus"]
    except (OSError, ValueError, KeyError, TypeError):
        return []

    by_day = {}
    for menu in menus:  # later entries for the same week win
        try:
            monday = date.fromisoformat(menu["weekOf"])
            for i, item in enumerate(menu["days"][:5]):
                by_day[monday + timedelta(days=i)] = item
        except (KeyError, TypeError, ValueError):
            continue

    lunches = []
    for day in (today, today + timedelta(days=1)):
        item = by_day.get(day)
        if isinstance(item, dict) and str(item.get("main", "")).strip():
            lunches.append(Lunch(day, str(item["main"]).strip(),
                                 str(item.get("dessert", "")).strip()))
    return lunches


# ------------------------------------------------------------- bin collection

BIN_PATTERN = re.compile(r"\b(green|black)\s+bin\b", re.IGNORECASE)


@dataclass
class Bin:
    day: date
    colour: str  # "green" or "black"


def bin_calendar_url(value):
    """Accept a public Google Calendar ID or a full iCal link."""
    value = value.strip()
    if not value or value.startswith("https://"):
        return value
    return ("https://calendar.google.com/calendar/ical/"
            + urllib.parse.quote(value, safe="") + "/public/basic.ics")


def fetch_next_bin(calendar, tz, today, days=7):
    """Next bin collection within `days` days, from the same public calendar the
    Fire dashboard uses: all-day events titled "... Green bin ..." or
    "... Black bin ...". Returns None if there is none, or on any error."""
    url = bin_calendar_url(calendar)
    if not url:
        return None
    start = datetime.combine(today, time.min, tz)
    try:
        cal = icalendar.Calendar.from_ical(_get(url))
        items = recurring_ical_events.of(cal).between(start, start + timedelta(days=days))
    except Exception as error:
        print(f"Bin calendar failed: {type(error).__name__}")
        return None

    found = []
    for item in items:
        if str(item.get("STATUS", "")).upper() == "CANCELLED":
            continue
        match = BIN_PATTERN.search(str(item.get("SUMMARY", "")))
        if not match:
            continue
        day = item.decoded("DTSTART")
        day = day.astimezone(tz).date() if isinstance(day, datetime) else day
        if day >= today:
            found.append(Bin(day, match.group(1).lower()))
    found.sort(key=lambda b: (b.day, b.colour))
    return found[0] if found else None
