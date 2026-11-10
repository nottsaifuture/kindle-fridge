"""Render the fridge dashboard (weather + Google Calendar) as a Kindle 4 PNG.

Usage:
    python render.py                    # writes out/dashboard.png
    python render.py --demo-calendar    # use sample events instead of ICAL_URLS
    python render.py --out site/x.png

Calendars come from the ICAL_URLS environment variable: one or more Google
Calendar "secret address in iCal format" links, separated by spaces or commas.
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

import data
from icons import BLACK, GREY, WHITE, describe, draw_icon

WIDTH, HEIGHT = 600, 800  # Kindle 4 screen, portrait
MARGIN = 24
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
HERE = Path(__file__).resolve().parent

# (path, preferred face) — the first one that exists wins. Noto Sans CJK is
# installed on GitHub Actions; the macOS fonts are only for local previews.
FONTS = {
    "regular": [
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "HK"),
        ("/System/Library/Fonts/STHeiti Light.ttc", None),
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", None),
    ],
    "bold": [
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "HK"),
        ("/System/Library/Fonts/STHeiti Medium.ttc", None),
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", None),
    ],
}
_font_cache = {}


def font(size, weight="regular"):
    key = (size, weight)
    if key not in _font_cache:
        _font_cache[key] = _load_font(size, weight)
    return _font_cache[key]


def _load_font(size, weight):
    for path, face in FONTS[weight]:
        if not os.path.exists(path):
            continue
        if face is None:
            return ImageFont.truetype(path, size)
        # A .ttc holds several faces (JP, KR, SC, TC, HK...); pick the HK one.
        for index in range(10):
            try:
                candidate = ImageFont.truetype(path, size, index=index)
            except OSError:
                break
            if face in candidate.getname()[0]:
                return candidate
        return ImageFont.truetype(path, size)
    raise SystemExit("No Chinese font found. On Linux: apt-get install fonts-noto-cjk")


# ----------------------------------------------------------------- helpers


def text_width(text, f):
    return f.getlength(text)


def fit(text, f, max_width):
    """Cut text with an ellipsis so it fits in max_width pixels."""
    if text_width(text, f) <= max_width:
        return text
    while text and text_width(text + "…", f) > max_width:
        text = text[:-1]
    return text + "…"


def day_label(day, today):
    if day == today:
        return "今日"
    if day == today + timedelta(days=1):
        return "明日"
    return WEEKDAYS[day.weekday()]


def deg(value):
    return f"{round(value)}°"


# ------------------------------------------------------------------ layout


def render(cfg, weather, events, calendar_note, now):
    img = Image.new("L", (WIDTH, HEIGHT), WHITE)
    d = ImageDraw.Draw(img)
    today = now.date()
    right = WIDTH - MARGIN

    # Header: date, weekday, place.
    d.text((MARGIN, 14), f"{now.month}月{now.day}日", font=font(46, "bold"), fill=BLACK)
    date_w = text_width(f"{now.month}月{now.day}日", font(46, "bold"))
    d.text((MARGIN + date_w + 14, 32), WEEKDAYS[now.weekday()], font=font(28), fill=BLACK)
    place = cfg["location_name"]
    d.text((right - text_width(place, font(22)), 38), place, font=font(22), fill=GREY)
    d.line([(MARGIN, 84), (right, 84)], fill=BLACK, width=2)

    # Current weather.
    today_forecast = weather.days[0]
    draw_icon(d, weather.code, MARGIN + 62, 160, 124, night=not weather.is_day)
    d.text((160, 88), deg(weather.temp), font=font(84, "bold"), fill=BLACK)
    d.text((166, 196), describe(weather.code), font=font(28, "bold"), fill=BLACK)

    details = [
        f"最高 {deg(today_forecast.t_max)}  最低 {deg(today_forecast.t_min)}",
        f"體感 {deg(weather.feels)}  濕度 {weather.humidity}%",
        f"降雨機會 {today_forecast.rain}%",
        f"風速 {round(weather.wind)} km/h",
        f"日出 {today_forecast.sunrise:%H:%M}  日落 {today_forecast.sunset:%H:%M}",
    ]
    for i, line in enumerate(details):
        f = font(19)
        d.text((right - text_width(line, f), 96 + i * 27), line, font=f, fill=BLACK)

    d.line([(MARGIN, 242), (right, 242)], fill=GREY, width=1)

    # Next hours, every three hours.
    col_w = (WIDTH - 2 * MARGIN) / max(1, len(weather.hours))
    for i, hour in enumerate(weather.hours):
        cx = MARGIN + col_w * (i + 0.5)
        _centred(d, cx, 248, f"{hour.time:%H:%M}", font(18), GREY)
        draw_icon(d, hour.code, cx, 292, 46, night=not hour.is_day)
        _centred(d, cx, 316, f"{deg(hour.temp)}  雨{hour.rain}%", font(18), BLACK)

    d.line([(MARGIN, 346), (right, 346)], fill=GREY, width=1)

    # Next three days: label on top, icon on the left, temperatures on the right.
    upcoming = weather.days[1:4]
    col_w = (WIDTH - 2 * MARGIN) / max(1, len(upcoming))
    for i, day in enumerate(upcoming):
        x = MARGIN + col_w * i
        d.text((x + 8, 352), day_label(day.date, today), font=font(20, "bold"), fill=BLACK)
        draw_icon(d, day.code, x + 34, 404, 48)
        d.text((x + 68, 380), f"{deg(day.t_max)} / {deg(day.t_min)}", font=font(20), fill=BLACK)
        d.text((x + 68, 406), f"雨 {day.rain}%", font=font(17), fill=GREY)

    d.line([(MARGIN, 440), (right, 440)], fill=BLACK, width=2)

    _draw_calendar(d, events, calendar_note, today, top=450, bottom=766)

    # Footer. The bottom-left corner stays empty: the Kindle prints its
    # battery level there after showing the image.
    stamp = f"更新於 {now.month}月{now.day}日 {now:%H:%M}"
    d.text((right - text_width(stamp, font(16)), 776), stamp, font=font(16), fill=GREY)

    # The Kindle 4 shows 16 shades of grey; snap to them for crisp text.
    return img.point(lambda v: min(255, (v + 8) // 17 * 17))


def _centred(d, cx, y, text, f, fill):
    d.text((cx - text_width(text, f) / 2, y), text, font=f, fill=fill)


def _draw_calendar(d, events, note, today, top, bottom):
    right = WIDTH - MARGIN
    row_h = 34
    title_font, time_font, heading_font = font(24), font(22, "bold"), font(22, "bold")
    y = top

    if note:
        d.text((MARGIN, y + 4), note, font=font(22), fill=GREY)
        return

    days = sorted({e.day for e in events} | {today})
    for day in days:
        todays = [e for e in events if e.day == day]
        if y + row_h > bottom:
            break

        heading = f"{day_label(day, today)}行程" if day == today else day_label(day, today)
        d.text((MARGIN, y), heading, font=heading_font, fill=BLACK)
        if day != today:
            d.text((MARGIN + text_width(heading, heading_font) + 10, y + 3),
                   f"{day.month}月{day.day}日", font=font(18), fill=GREY)
        y += row_h

        if not todays:
            d.text((MARGIN + 8, y), "冇行程", font=font(20), fill=GREY)
            y += row_h
            continue

        for i, event in enumerate(todays):
            remaining = len(todays) - i
            if y + row_h > bottom or (remaining > 1 and y + 2 * row_h > bottom):
                d.text((MARGIN + 8, y), f"…仲有 {remaining} 項", font=font(20), fill=GREY)
                return
            when = "全日" if event.start is None else f"{event.start:%H:%M}"
            d.text((MARGIN + 8, y + 2), when, font=time_font, fill=BLACK)
            d.text((MARGIN + 92, y), fit(event.title, title_font, right - MARGIN - 92),
                   font=title_font, fill=BLACK)
            y += row_h
        y += 6


# -------------------------------------------------------------------- main


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=HERE / "config.json")
    parser.add_argument("--out", default=HERE.parent / "out" / "dashboard.png")
    parser.add_argument("--demo-calendar", action="store_true",
                        help="show sample events instead of reading ICAL_URLS")
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.now(tz)

    weather = data.fetch_weather(cfg, now)

    note = ""
    if args.demo_calendar:
        events = data.demo_events(tz, now)
    else:
        urls = [u for u in re.split(r"[\s,]+", os.environ.get("ICAL_URLS", "")) if u]
        events, failed = data.fetch_events(urls, tz, now, cfg.get("calendar_days", 2))
        if not urls:
            note = "未設定日曆（ICAL_URLS）"
        elif failed == len(urls):
            note = "日曆暫時讀取唔到"

    image = render(cfg, weather, events, note, now)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, optimize=True)
    print(f"Saved {out} ({len(events)} events)")


if __name__ == "__main__":
    main()
