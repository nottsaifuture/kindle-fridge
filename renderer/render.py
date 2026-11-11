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
from icons import BLACK, GREY, LIGHT, WHITE, describe, draw_icon

# The Kindle 4 screen is 600x800 portrait. The dashboard is drawn landscape
# (800x600) and turned a quarter so it reads correctly with the Kindle on its
# side. eips can't offset images on the K4, so the battery level is printed
# as text by the Kindle; it lands in the blank strip at the right edge.
WIDTH, HEIGHT = 800, 600
MARGIN = 24
SPLIT = 400  # weather on the left, calendar on the right
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
HERE = Path(__file__).resolve().parent

# (path, preferred face) — the first one that exists wins. Noto Sans CJK is
# installed on GitHub Actions; the macOS fonts are only for local previews.
FONTS = {
    "regular": [
        (str(HERE.parent / "fonts" / "NotoSansHK-Regular.otf"), None),  # GitHub Actions
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "HK"),
        ("/System/Library/Fonts/STHeiti Light.ttc", None),
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", None),
    ],
    "bold": [
        (str(HERE.parent / "fonts" / "NotoSansHK-Bold.otf"), None),  # GitHub Actions
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


def wrap(text, f, max_width, max_lines):
    """Split text into at most max_lines lines (by word), ellipsis on the last."""
    words, lines = text.split(), []
    while words and len(lines) < max_lines:
        line = words.pop(0)
        while words and text_width(line + " " + words[0], f) <= max_width:
            line += " " + words.pop(0)
        lines.append(line)
    if words:
        lines[-1] = fit(lines[-1] + " " + " ".join(words), f, max_width)
    return [fit(line, f, max_width) for line in lines]


# Every word on the dashboard, per language ("language" in config.json).
TEXT = {
    "en": {
        "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "date": lambda d: f"{d.day} {d:%b}",
        "today": "Today", "tomorrow": "Tomorrow",
        "details": lambda w, t: [
            (f"High {deg(t.t_max)}  Low {deg(t.t_min)}", f"Feels like {deg(w.feels)}"),
            (f"Rain {t.rain}%", f"Humidity {w.humidity}%"),
            (f"Wind {round(w.wind)} km/h", f"Sun {t.sunrise:%H:%M}–{t.sunset:%H:%M}"),
        ],
        "rain": lambda p: f"Rain {p}%",
        "cal_today": "Today", "no_events": "No events",
        "more": lambda n: f"…{n} more", "all_day": "All day",
        "lunch": lambda label: f"{label}'s lunch", "dessert": "Dessert: ",
        "no_calendar": "Calendar not set up (ICAL_URLS)",
        "calendar_failed": "Calendar unavailable right now",
        "updated": lambda d: f"Updated {d.day} {d:%b} {d:%H:%M}",
        "bin": lambda colour, when: f"{colour.title()} bin · {when}",
    },
    "zh-HK": {
        "weekdays": WEEKDAYS,
        "date": lambda d: f"{d.month}月{d.day}日",
        "today": "今日", "tomorrow": "明日",
        "details": lambda w, t: [
            (f"最高 {deg(t.t_max)}  最低 {deg(t.t_min)}", f"體感 {deg(w.feels)}  濕度 {w.humidity}%"),
            (f"降雨機會 {t.rain}%", f"風速 {round(w.wind)} km/h"),
            (f"日出 {t.sunrise:%H:%M}", f"日落 {t.sunset:%H:%M}"),
        ],
        "rain": lambda p: f"雨{p}%",
        "cal_today": "今日行程", "no_events": "冇行程",
        "more": lambda n: f"…仲有 {n} 項", "all_day": "全日",
        "lunch": lambda label: f"{label}午餐", "dessert": "甜品：",
        "no_calendar": "未設定日曆（ICAL_URLS）",
        "calendar_failed": "日曆暫時讀取唔到",
        "updated": lambda d: f"更新於 {d.month}月{d.day}日 {d:%H:%M}",
        "bin": lambda colour, when: f"{'綠色' if colour == 'green' else '黑色'}垃圾桶 · {when}",
    },
}
T = TEXT["en"]  # set from config in render()


def day_label(day, today):
    if day == today:
        return T["today"]
    if day == today + timedelta(days=1):
        return T["tomorrow"]
    return T["weekdays"][day.weekday()]


def deg(value):
    return f"{round(value)}°"


# ------------------------------------------------------------------ layout


def render(cfg, weather, events, calendar_note, now, lunches=(), next_bin=None):
    global T
    lang = cfg.get("language", "en")
    T = TEXT.get(lang, TEXT["en"])
    img = Image.new("L", (WIDTH, HEIGHT), WHITE)
    d = ImageDraw.Draw(img)
    today = now.date()
    right = WIDTH - MARGIN
    left_end = SPLIT - 12  # right edge of the weather column

    # Header across the top: date, weekday, place.
    # Placed by baseline ("ls" anchor) so Noto and the Mac preview fonts line up.
    date_text = T["date"](now)
    d.text((MARGIN, 68), date_text, font=font(58, "bold"), fill=BLACK, anchor="ls")
    date_w = text_width(date_text, font(58, "bold"))
    d.text((MARGIN + date_w + 16, 66), T["weekdays"][now.weekday()], font=font(34), fill=BLACK, anchor="ls")
    if next_bin:
        _draw_bin(d, next_bin, today, right)
    d.line([(MARGIN, 82), (right, 82)], fill=BLACK, width=2)
    d.line([(SPLIT, 92), (SPLIT, HEIGHT - 20)], fill=GREY, width=1)

    # --- Left column: weather. Description sits under the icon so the
    # temperature can be big.
    today_forecast = weather.days[0]
    draw_icon(d, weather.code, MARGIN + 56, 140, 104, night=not weather.is_day)
    # Description under the icon, shrunk until it fits beside the temperature.
    desc = describe(weather.code, lang)
    for size in (26, 22, 20, 18, 16):
        desc_font = font(size, "bold")
        if text_width(desc, desc_font) <= 128:
            break
    _centred(d, MARGIN + 56, 186 + (26 - size) // 2, fit(desc, desc_font, 128), desc_font, BLACK)
    d.text((158, 204), deg(weather.temp), font=font(128, "bold"), fill=BLACK, anchor="ls")

    half = (left_end - MARGIN) / 2
    for i, pair in enumerate(T["details"](weather, today_forecast)):
        for j, line in enumerate(pair):
            d.text((MARGIN + 4 + j * half, 234 + i * 26), fit(line, font(18), half - 8),
                   font=font(18), fill=BLACK)

    d.line([(MARGIN, 318), (left_end, 318)], fill=GREY, width=1)

    # Next hours, every three hours.
    col_w = (left_end - MARGIN) / max(1, len(weather.hours))
    for i, hour in enumerate(weather.hours):
        cx = MARGIN + col_w * (i + 0.5)
        _centred(d, cx, 324, f"{hour.time:%H:%M}", font(16), GREY)
        draw_icon(d, hour.code, cx, 368, 44, night=not hour.is_day)
        _centred(d, cx, 392, deg(hour.temp), font(19), BLACK)
        _centred(d, cx, 416, T["rain"](hour.rain), font(15), GREY)

    d.line([(MARGIN, 446), (left_end, 446)], fill=GREY, width=1)

    # Next three days: label on top, icon below, temperatures beside it.
    upcoming = weather.days[1:4]
    col_w = (left_end - MARGIN) / max(1, len(upcoming))
    for i, day in enumerate(upcoming):
        x = MARGIN + col_w * i
        _centred(d, x + col_w / 2, 452, day_label(day.date, today), font(19, "bold"), BLACK)
        draw_icon(d, day.code, x + col_w / 2, 506, 46)
        _centred(d, x + col_w / 2, 532, f"{deg(day.t_max)} / {deg(day.t_min)}", font(18), BLACK)
        _centred(d, x + col_w / 2, 556, T["rain"](day.rain), font(15), GREY)

    # --- Right column: calendar, then school lunch (only if there is a menu).
    col_left = SPLIT + 14
    lunch_h = _lunch_height(lunches, right - col_left)
    cal_bottom = 556 - lunch_h - (14 if lunches else 0)
    _draw_calendar(d, events, calendar_note, today,
                   left=col_left, right=right, top=94, bottom=cal_bottom)
    if lunches:
        top = cal_bottom + 6
        d.line([(col_left, top), (right, top)], fill=GREY, width=1)
        _draw_lunches(d, lunches, today, col_left, right, top + 8)

    # Footer under the calendar. The strip right of MARGIN is left blank:
    # the Kindle prints its battery level there, sideways.
    stamp = f"{cfg['location_name']} · {T['updated'](now)}"
    d.text((right - text_width(stamp, font(15)), 572), stamp, font=font(15), fill=GREY)

    # Turn it to the Kindle's portrait frame. With the buttons on the right the
    # picture turns clockwise; with them on the left, anticlockwise.
    if cfg.get("kindle_buttons", "right") == "left":
        img = img.transpose(Image.Transpose.ROTATE_90)
    else:
        img = img.transpose(Image.Transpose.ROTATE_270)

    # The Kindle 4 shows 16 shades of grey; snap to them for crisp text.
    return img.point(lambda v: min(255, (v + 8) // 17 * 17))


def _centred(d, cx, y, text, f, fill):
    d.text((cx - text_width(text, f) / 2, y), text, font=f, fill=fill)


def _draw_bin(d, next_bin, today, right):
    """Badge in the header's top-right corner: a wheelie bin and its day.
    Black bin: white on black. Green bin: black on light grey (no colour on
    e-ink, so the word says which)."""
    label = T["bin"](next_bin.colour, day_label(next_bin.day, today))
    f = font(22, "bold")
    black = next_bin.colour == "black"
    bg, fg = (BLACK, WHITE) if black else (LIGHT, BLACK)
    top, bottom = 16, 70
    left = right - (text_width(label, f) + 70)
    d.rounded_rectangle([left, top, right, bottom], radius=12, fill=bg,
                        outline=BLACK, width=2)
    # Wheelie bin: lid, tapered body, wheel.
    bx, by = left + 14, top + 10
    d.rectangle([bx - 2, by, bx + 26, by + 5], fill=fg)
    d.polygon([(bx, by + 8), (bx + 24, by + 8), (bx + 21, by + 34), (bx + 3, by + 34)], fill=fg)
    d.ellipse([bx + 15, by + 30, bx + 25, by + 40], fill=fg, outline=bg, width=2)
    d.text((left + 50, (top + bottom) / 2), label, font=f, fill=fg, anchor="lm")


LUNCH_HEAD, LUNCH_MAIN, LUNCH_DESSERT = 28, 24, 22  # line heights


def _lunch_lines(lunch, width):
    main = wrap(lunch.main, font(19), width, 2)
    dessert = [fit(T["dessert"] + lunch.dessert, font(17), width)] if lunch.dessert else []
    return main, dessert


def _lunch_height(lunches, width):
    total = 0
    for lunch in lunches:
        main, dessert = _lunch_lines(lunch, width - 6)
        total += LUNCH_HEAD + LUNCH_MAIN * len(main) + LUNCH_DESSERT * len(dessert) + 6
    return total


def _draw_lunches(d, lunches, today, left, right, y):
    for lunch in lunches:
        main, dessert = _lunch_lines(lunch, right - left - 6)
        d.text((left, y), T["lunch"](day_label(lunch.day, today)), font=font(20, "bold"), fill=BLACK)
        y += LUNCH_HEAD
        for line in main:
            d.text((left + 6, y), line, font=font(19), fill=BLACK)
            y += LUNCH_MAIN
        for line in dessert:
            d.text((left + 6, y), line, font=font(17), fill=GREY)
            y += LUNCH_DESSERT
        y += 6


def _draw_calendar(d, events, note, today, left, right, top, bottom):
    row_h = 30
    title_font, time_font, heading_font = font(22), font(20, "bold"), font(22, "bold")
    # Titles start after the widest time label ("09:30" or "All day").
    title_x = round(max(text_width("00:00", time_font), text_width(T["all_day"], time_font))) + 18
    y = top

    if note:
        d.text((left, y + 4), T[note], font=font(20), fill=GREY)
        return

    days = sorted({e.day for e in events} | {today})
    for day in days:
        todays = [e for e in events if e.day == day]
        if y + row_h > bottom:
            break

        heading = T["cal_today"] if day == today else day_label(day, today)
        d.text((left, y), heading, font=heading_font, fill=BLACK)
        if day != today:
            d.text((left + text_width(heading, heading_font) + 10, y + 3),
                   T["date"](day), font=font(18), fill=GREY)
        y += row_h

        if not todays:
            d.text((left + 6, y), T["no_events"], font=font(20), fill=GREY)
            y += row_h
            continue

        for i, event in enumerate(todays):
            remaining = len(todays) - i
            if y + row_h > bottom or (remaining > 1 and y + 2 * row_h > bottom):
                d.text((left + 6, y), T["more"](remaining), font=font(20), fill=GREY)
                return
            when = T["all_day"] if event.start is None else f"{event.start:%H:%M}"
            d.text((left + 6, y + 2), when, font=time_font, fill=BLACK)
            d.text((left + title_x, y), fit(event.title, title_font, right - left - title_x),
                   font=title_font, fill=BLACK)
            y += row_h
        y += 8


# -------------------------------------------------------------------- main


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=HERE / "config.json")
    parser.add_argument("--out", default=HERE.parent / "out" / "dashboard.png")
    parser.add_argument("--demo-calendar", action="store_true",
                        help="show sample events instead of reading ICAL_URLS")
    parser.add_argument("--menus", default=os.environ.get("MENUS_JSON", ""),
                        help="school lunch menus.json (from the Fire dashboard); optional")
    parser.add_argument("--demo-bin", choices=["green", "black"],
                        help="show a sample bin collection instead of reading BIN_CALENDAR_ID")
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
            note = "no_calendar"
        elif failed == len(urls):
            note = "calendar_failed"

    lunches = data.load_lunches(args.menus, now.date())
    if args.demo_bin:
        next_bin = data.Bin(now.date() + timedelta(days=2), args.demo_bin)
    else:
        next_bin = data.fetch_next_bin(os.environ.get("BIN_CALENDAR_ID", ""), tz, now.date())
    image = render(cfg, weather, events, note, now, lunches, next_bin)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, optimize=True)
    print(f"Saved {out} ({len(events)} events, {len(lunches)} lunches)")


if __name__ == "__main__":
    main()
