"""Weather icons drawn with simple shapes, so no icon font is needed."""

import math

BLACK = 0
GREY = 136
LIGHT = 221
WHITE = 255

# WMO weather code -> (Cantonese description, icon kind)
WMO = {
    0: ("天晴", "clear"),
    1: ("大致天晴", "partly"),
    2: ("間中多雲", "partly"),
    3: ("密雲", "cloudy"),
    45: ("有霧", "fog"),
    48: ("有霧", "fog"),
    51: ("微毛毛雨", "drizzle"),
    53: ("毛毛雨", "drizzle"),
    55: ("密毛毛雨", "drizzle"),
    56: ("凍毛毛雨", "drizzle"),
    57: ("凍毛毛雨", "drizzle"),
    61: ("微雨", "rain"),
    63: ("有雨", "rain"),
    65: ("大雨", "rain"),
    66: ("凍雨", "rain"),
    67: ("凍雨", "rain"),
    71: ("小雪", "snow"),
    73: ("有雪", "snow"),
    75: ("大雪", "snow"),
    77: ("雪粒", "snow"),
    80: ("驟雨", "showers"),
    81: ("驟雨", "showers"),
    82: ("大驟雨", "showers"),
    85: ("陣雪", "snow"),
    86: ("陣雪", "snow"),
    95: ("雷暴", "thunder"),
    96: ("雷暴夾冰雹", "thunder"),
    99: ("雷暴夾冰雹", "thunder"),
}


def describe(code):
    return WMO.get(code, ("—", "cloudy"))[0]


def draw_icon(draw, code, cx, cy, size, night=False):
    """Draw the icon for a WMO code centred on (cx, cy), about `size` px wide."""
    kind = WMO.get(code, ("", "cloudy"))[1]
    s = size / 100  # every shape below is laid out on a 100 x 100 grid
    lw = max(2, round(size / 22))

    if kind == "clear":
        (_moon if night else _sun)(draw, cx, cy, 30 * s, lw)
        return

    cloud_x, cloud_y = cx + 4 * s, (cy + 4 * s if kind in ("partly", "cloudy") else cy - 12 * s)
    if kind in ("partly", "showers"):
        # Sun peeking out from behind the top-right of the cloud.
        cloud_x -= 6 * s
        (_moon if night else _sun)(draw, cx + 20 * s, cloud_y - 30 * s, 17 * s, lw)

    shade = LIGHT if kind in ("rain", "showers", "thunder") else WHITE
    _cloud(draw, cloud_x, cloud_y, s, lw, shade)

    below = cloud_y + 26 * s
    if kind in ("rain", "showers"):
        for dx in (-18, 0, 18):
            x = cx + dx * s
            draw.line([(x + 4 * s, below), (x - 4 * s, below + 18 * s)], fill=BLACK, width=lw)
    elif kind == "drizzle":
        for dx, dy in ((-18, 4), (0, 12), (18, 4), (-9, 22), (9, 22)):
            r = lw * 0.9
            x, y = cx + dx * s, below + dy * s
            draw.ellipse([x - r, y - r, x + r, y + r], fill=BLACK)
    elif kind == "snow":
        for dx, dy in ((-18, 8), (6, 6), (-6, 24), (18, 22)):
            _flake(draw, cx + dx * s, below + dy * s, 6 * s, max(1, lw - 1))
    elif kind == "thunder":
        bolt = [(4, -2), (-10, 22), (0, 22), (-6, 40), (14, 12), (3, 12), (10, -2)]
        draw.polygon([(cx + x * s, below + y * s) for x, y in bolt], fill=BLACK)
    elif kind == "fog":
        for i, dy in enumerate((6, 16, 26)):
            inset = 6 * s if i == 1 else 0
            draw.line([(cx - 32 * s + inset, below + dy * s), (cx + 36 * s - inset, below + dy * s)],
                      fill=BLACK, width=lw)


def _sun(draw, cx, cy, r, lw):
    for i in range(8):
        a = i * math.pi / 4
        inner, outer = r * 1.3, r * 1.65
        draw.line([(cx + inner * math.cos(a), cy + inner * math.sin(a)),
                   (cx + outer * math.cos(a), cy + outer * math.sin(a))], fill=BLACK, width=lw)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE, outline=BLACK, width=lw)


def _moon(draw, cx, cy, r, lw):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BLACK)
    o = r * 0.55
    draw.ellipse([cx - r + o, cy - r - o * 0.4, cx + r + o, cy + r - o * 0.4], fill=WHITE)


def _cloud(draw, cx, cy, s, lw, shade):
    """A cloud made of overlapping circles: draw them all a bit bigger in black
    first, then all of them again in the fill colour, which leaves one outline."""
    parts = [
        ("ellipse", -36, -2, 18),
        ("ellipse", -14, -14, 22),
        ("ellipse", 14, -8, 20),
        ("ellipse", 30, 4, 14),
        ("rect", -36, 4, 66, 16),
    ]
    for grow, colour in ((lw, BLACK), (0, shade)):
        for kind, x, y, a, *rest in parts:
            if kind == "ellipse":
                r = a * s + grow
                px, py = cx + x * s, cy + y * s
                draw.ellipse([px - r, py - r, px + r, py + r], fill=colour)
            else:
                w, h = a, rest[0]
                draw.rectangle([cx + x * s - grow, cy + y * s - grow,
                                cx + (x + w) * s + grow, cy + (y + h) * s + grow], fill=colour)


def _flake(draw, cx, cy, r, lw):
    for i in range(3):
        a = i * math.pi / 3
        dx, dy = r * math.cos(a), r * math.sin(a)
        draw.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], fill=BLACK, width=lw)
