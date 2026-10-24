"""[O23-PD 2026-10-23] The partner's day review as a PDF.

The review page has a "Download PDF" button (GET /partner/review/pdf). This
module prints what the page shows for one day (partner_lessons.day_review),
in the page's order: the day in one line with the rules kept, the one rule
to focus on tomorrow (newest day only), the lesson of the day, what went
well, every other lesson with all its examples (the page folds them), the
rules with what each one means, every trade with its checks, price chart,
what the option did, its timeline and result, the day's orders, the cards
not taken and the data notes. Nothing is recomputed: every sentence comes
from the engine, and numbers are formatted as the page formats them (Indian
digit grouping, a true minus sign).

Fonts: DejaVu Sans from the engine image (Debian fonts-dejavu-core) has ₹,
the true minus and ✓ ✗. Without it the built-in Helvetica is used and each
character it cannot show is replaced by a plain one (₹ -> "Rs "), so no text
is ever dropped. Pure: no DB, no network; nothing here places an order.
"""
from __future__ import annotations

import hashlib
import io
import math
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Optional
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import CondPageBreak, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Regular and bold, tried in order. The engine image installs fonts-dejavu-core.
FONT_PAIRS = (
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
)
# A character the font cannot show becomes one it can (else "?"); nothing is dropped.
SUBSTITUTES = {"₹": "Rs ", "−": "-", "✓": "+", "✗": "x", "●": "*", "≈": "~", "…": "...", "—": "-", "–": "-",
               "“": '"', "”": '"', "‘": "'", "’": "'", "×": "x", "·": "|", "•": "*"}
FOOTER = "Coaching only. Nothing here places an order."
PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
FRAME_W = PAGE_W - 2 * MARGIN
PAD = 7.0                    # inside a box
CHART_H = 96.0
SECTION_ROOM = 130.0        # a section starts on a new page with less room than this
GAP = "&nbsp;&nbsp;&nbsp;"   # paragraphs collapse plain spaces

INK = colors.HexColor("#111827")
MUTED = colors.HexColor("#4B5563")
FAINT = colors.HexColor("#6B7280")
RULE = colors.HexColor("#E5E7EB")
PANEL = colors.HexColor("#F9FAFB")
GREEN = colors.HexColor("#047857")
RED = colors.HexColor("#B91C1C")
AMBER = colors.HexColor("#B45309")
AMBER_DARK = colors.HexColor("#92400E")
AMBER_BG = colors.HexColor("#FFFBEB")
AMBER_LINE = colors.HexColor("#F59E0B")
TEAL = colors.HexColor("#0F766E")
TEAL_BG = colors.HexColor("#F0FDFA")
SKY = colors.HexColor("#0369A1")
LEVEL_COLOURS = {"stop": RED, "target": GREEN, "limit": SKY, "your_stop": AMBER}

# Section titles: the page's words, and "that day" on an earlier day.
TITLES = {
    "lesson": ("Your lesson for today", "Your lesson from that day"),
    "more": ("More to learn from today", "More to learn from that day"),
    "rules": ("Rules kept today", "Rules kept that day"),
    "orders": ("Your orders today", "Your orders that day"),
}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")

_LOCK = threading.Lock()     # font registration and the build: reportlab keeps module state
_FONTS: dict = {}


# ---------------------------------------------------------------------------
# fonts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Fonts:
    regular: str
    bold: str
    covers: Callable[[str], bool]
    embedded: bool


def _winansi(char: str) -> bool:
    try:
        char.encode("cp1252")
    except UnicodeEncodeError:
        return False
    return True


def _load_fonts() -> Fonts:
    for regular, bold in FONT_PAIRS:
        if not (os.path.isfile(regular) and os.path.isfile(bold)):
            continue
        tag = hashlib.sha1(f"{regular}|{bold}".encode()).hexdigest()[:8]
        names = (f"ReviewSans-{tag}", f"ReviewSans-Bold-{tag}")
        if names[0] not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(names[0], regular))
            pdfmetrics.registerFont(TTFont(names[1], bold))
            pdfmetrics.registerFontFamily(names[0], normal=names[0], bold=names[1], italic=names[0],
                                          boldItalic=names[1])
        regular_cmap = pdfmetrics.getFont(names[0]).face.charToGlyph
        bold_cmap = pdfmetrics.getFont(names[1]).face.charToGlyph
        return Fonts(names[0], names[1], lambda c: ord(c) in regular_cmap and ord(c) in bold_cmap, True)
    return Fonts("Helvetica", "Helvetica-Bold", _winansi, False)


def fonts() -> Fonts:
    """The fonts for this FONT_PAIRS, registered once."""
    with _LOCK:
        if FONT_PAIRS not in _FONTS:
            _FONTS[FONT_PAIRS] = _load_fonts()
        return _FONTS[FONT_PAIRS]


def plain(text, covers: Callable[[str], bool]) -> str:
    """The text with every character the font cannot show replaced."""
    out = []
    for char in str(text):
        if char in "\n\r\t":
            out.append(" ")
        elif covers(char):
            out.append(char)
        else:
            out.append(SUBSTITUTES.get(char, "?"))
    return "".join(out)


# ---------------------------------------------------------------------------
# numbers, as the page formats them (utils/partnerCoach.js, partnerReview.js)
# ---------------------------------------------------------------------------

def _finite(value) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _group_in(digits: str) -> str:
    """Indian grouping: 159587 -> 1,59,587."""
    if len(digits) <= 3:
        return digits
    head, groups = digits[:-3], [digits[-3:]]
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + groups)


def _number_in(value: float, places: int) -> str:
    """|value| rounded half away from zero (as toLocaleString), Indian
    grouping, trailing zeros dropped."""
    exact = Decimal(abs(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    whole, _, fraction = f"{exact:f}".partition(".")
    fraction = fraction.rstrip("0")
    return _group_in(whole) + (f".{fraction}" if fraction else "")


def format_rs(value, signed: bool = True) -> str:
    """formatRs: "+₹6,135", "−₹1,261", "₹0"; unsigned keeps a minus."""
    amount = _finite(value)
    if amount is None:
        return "n/a"
    body = f"₹{_number_in(amount, 0)}"
    if not signed:
        return f"−{body}" if amount < 0 else body
    if amount == 0:
        return body
    return f"−{body}" if amount < 0 else f"+{body}"


def format_price(value) -> str:
    price = _finite(value)
    return "?" if price is None else f"₹{_number_in(price, 2)}"


def signed_percent(value, digits: int = 1) -> str:
    number = _finite(value)
    if number is None:
        return "n/a"
    number *= 100
    body = f"{Decimal(abs(number)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP):f}%"
    if Decimal(body[:-1]) == 0:
        return body
    return f"−{body}" if number < 0 else f"+{body}"


def minutes_label(minutes) -> str:
    value = _finite(minutes)
    if value is None:
        return "n/a"
    total = math.floor(value + 0.5)
    if total < 60:
        return f"{total} min"
    rest = total % 60
    return f"{total // 60} h {rest} min" if rest else f"{total // 60} h"


def long_day(day: str) -> str:
    """"2026-10-23" -> "Friday 23 October 2026"."""
    try:
        value = date.fromisoformat(day)
    except (TypeError, ValueError):
        return str(day or "")
    return f"{WEEKDAYS[value.weekday()]} {value.day} {MONTHS[value.month - 1]} {value.year}"


def short_day(day: str) -> str:
    """"2026-10-23" -> "Fri 23 Oct 2026"."""
    try:
        value = date.fromisoformat(day)
    except (TypeError, ValueError):
        return str(day or "")
    return f"{WEEKDAYS[value.weekday()][:3]} {value.day} {MONTHS[value.month - 1][:3]} {value.year}"


def _tone(value):
    number = _finite(value)
    if number is None or number == 0:
        return INK
    return GREEN if number > 0 else RED


def _score_tone(pct):
    number = _finite(pct)
    if number is None:
        return INK
    return GREEN if number >= 80 else AMBER if number >= 50 else RED


def _hex(colour) -> str:
    return "#" + colour.hexval()[2:]


# ---------------------------------------------------------------------------
# chart: the page's chartGeometry, drawn as vectors
# ---------------------------------------------------------------------------

def chart_geometry(chart: Optional[dict], width: float, height: float, pad_x: float = 6.0,
                   pad_y: float = 10.0) -> Optional[dict]:
    """The page's chartGeometry (utils/partnerReview.js) with y pointing up:
    a level widens the price range only when it is near the prices; the
    others are listed as off the chart."""
    chart = chart or {}
    points = []
    for point in chart.get("points") or []:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            t, price = _finite(point[0]), _finite(point[1])
            if t is not None and price is not None:
                points.append((t, price))
    if len(points) < 2:
        return None
    marks = [m for m in chart.get("marks") or []
             if isinstance(m, dict) and _finite(m.get("t")) is not None and _finite(m.get("price")) is not None]
    levels = [lv for lv in chart.get("levels") or [] if isinstance(lv, dict) and _finite(lv.get("price")) is not None]
    prices = [p for _, p in points] + [_finite(m["price"]) for m in marks]
    lo, hi = min(prices), max(prices)
    span = max(hi - lo, hi * 0.02, 0.5)
    near = [lv for lv in levels if lo - span * 0.5 <= _finite(lv["price"]) <= hi + span * 0.5]
    lo = min([lo] + [_finite(lv["price"]) for lv in near])
    hi = max([hi] + [_finite(lv["price"]) for lv in near])
    pad = (hi - lo) * 0.08 or 1.0
    lo, hi = lo - pad, hi + pad
    times = [t for t, _ in points] + [_finite(m["t"]) for m in marks]
    t0, t1 = min(times), max(times)

    def x(t: float) -> float:
        return pad_x + (t - t0) / max(t1 - t0, 1) * (width - 2 * pad_x)

    def y(price: float) -> float:
        return pad_y + (price - lo) / (hi - lo) * (height - 2 * pad_y)

    top = max(points, key=lambda p: p[1])
    bottom = min(points, key=lambda p: p[1])
    return {
        "points": [(x(t), y(p)) for t, p in points],
        "marks": [{**m, "x": x(_finite(m["t"])), "y": y(_finite(m["price"]))} for m in marks],
        "levels": [{**lv, "y": y(_finite(lv["price"]))} for lv in near],
        "hidden": [lv for lv in levels if not any(lv is n for n in near)],
        "high": {"price": top[1], "x": x(top[0]), "y": y(top[1])},
        "low": {"price": bottom[1], "x": x(bottom[0]), "y": y(bottom[1])},
        "start": chart.get("start") or "", "end": chart.get("end") or "",
    }


def _place(drawing: Drawing, placed: list, text: str, spots, font: str, size: float, colour, width: float,
           low: float, high: float) -> bool:
    """Draw ``text`` at the first spot (x, y of its left baseline) that stays
    in the box and clear of what is already placed, on a small panel so the
    price line never runs through it. A label with no free spot is left out
    (the timeline lists every price)."""
    w = pdfmetrics.stringWidth(text, font, size)
    for lx, ly in spots:
        lx = min(max(lx, 1.5), width - w - 1.5)
        box = (lx - 1, ly - 1.8, lx + w + 1, ly + size * 0.8)
        if low <= box[1] and box[3] <= high and not any(
                box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in placed):
            placed.append(box)
            drawing.add(Rect(box[0], box[1], box[2] - box[0], box[3] - box[1], fillColor=PANEL, strokeColor=None))
            drawing.add(String(lx, ly, text, fontName=font, fontSize=size, fillColor=colour))
            return True
    return False


def price_chart(chart: Optional[dict], f: Fonts, width: float) -> Optional[Drawing]:
    """The option's price around the trade: the line, your buys (green) and
    sells (red) with their prices, the card's and your levels dashed, the
    line's high and low, and the time span and legend underneath."""
    caption = 13.0
    geo = chart_geometry(chart, width, CHART_H)
    if geo is None:
        return None
    text = lambda s: plain(s, f.covers)  # noqa: E731
    drawing = Drawing(width, CHART_H + caption)
    top = caption + CHART_H
    drawing.add(Rect(0, caption, width, CHART_H, fillColor=PANEL, strokeColor=RULE, strokeWidth=0.6))
    for level in geo["levels"]:
        y = caption + level["y"]
        drawing.add(Line(0, y, width, y, strokeColor=LEVEL_COLOURS.get(level.get("kind"), FAINT), strokeWidth=0.7,
                         strokeDashArray=[3, 2]))
    flat = []
    for px, py in geo["points"]:
        flat += [px, caption + py]
    drawing.add(PolyLine(flat, strokeColor=INK, strokeWidth=1.1, strokeLineJoin=1))
    placed: list = []
    for mark in geo["marks"]:
        cx, cy = mark["x"], caption + mark["y"]
        drawing.add(Circle(cx, cy, 3.2, fillColor=GREEN if mark.get("kind") == "buy" else RED,
                           strokeColor=colors.white, strokeWidth=0.8))
        placed.append((cx - 3.6, cy - 3.6, cx + 3.6, cy + 3.6))
    # Labels last, each on its own small panel: the levels at the right edge,
    # then the buy and sell prices, then the line's high and low.
    for level in geo["levels"]:
        colour = LEVEL_COLOURS.get(level.get("kind"), FAINT)
        y = caption + level["y"]
        label = text(f"{level.get('label', '')} {format_price(level['price'])}")
        lw = pdfmetrics.stringWidth(label, f.regular, 6.5)
        _place(drawing, placed, label, ((width - lw - 3, y + 2), (width - lw - 3, y - 7.5)), f.regular, 6.5, colour,
               width, caption, top)
    for mark in geo["marks"]:
        colour = GREEN if mark.get("kind") == "buy" else RED
        cx, cy = mark["x"], caption + mark["y"]
        label = text(format_price(mark["price"]))
        lw = pdfmetrics.stringWidth(label, f.regular, 6.5)
        _place(drawing, placed, label, ((cx + 5, cy + 3), (cx + 5, cy - 8.5), (cx - 5 - lw, cy + 3),
                                        (cx - 5 - lw, cy - 8.5)), f.regular, 6.5, colour, width, caption, top)
    for key, dy in (("high", 4.0), ("low", -9.0)):
        point = geo[key]
        label = text(format_price(point["price"]))
        lw = pdfmetrics.stringWidth(label, f.regular, 6)
        _place(drawing, placed, label, ((point["x"] - lw / 2, caption + point["y"] + dy),), f.regular, 6, FAINT,
               width, caption, top)
    drawing.add(String(0, 3, text(geo["start"]), fontName=f.regular, fontSize=6.5, fillColor=FAINT))
    drawing.add(String(width, 3, text(geo["end"]), fontName=f.regular, fontSize=6.5, fillColor=FAINT,
                       textAnchor="end"))
    hidden = ", ".join(f"{lv.get('label', '')} {format_price(lv['price'])}" for lv in geo["hidden"])
    parts = [(GREEN, text("your buy")), (RED, text("your sell"))]
    tail = text(f"· off the chart: {hidden}") if hidden else ""
    total = sum(9 + pdfmetrics.stringWidth(label, f.regular, 6.5) + 8 for _, label in parts)
    total += pdfmetrics.stringWidth(tail, f.regular, 6.5)
    x = (width - total) / 2
    for colour, label in parts:
        drawing.add(Circle(x + 3, 5.2, 2.6, fillColor=colour, strokeColor=None))
        drawing.add(String(x + 9, 3, label, fontName=f.regular, fontSize=6.5, fillColor=FAINT))
        x += 9 + pdfmetrics.stringWidth(label, f.regular, 6.5) + 8
    if tail:
        drawing.add(String(x, 3, tail, fontName=f.regular, fontSize=6.5, fillColor=FAINT))
    return drawing


# ---------------------------------------------------------------------------
# the document
# ---------------------------------------------------------------------------

class _Writer:
    """Styles and text helpers bound to one font set."""

    def __init__(self, f: Fonts):
        self.f = f
        self.base = ParagraphStyle("base", fontName=f.regular, fontSize=9.5, leading=13, textColor=INK)
        self.small = ParagraphStyle("small", parent=self.base, fontSize=8.3, leading=11, textColor=MUTED)
        self.tiny = ParagraphStyle("tiny", parent=self.base, fontSize=7.6, leading=10, textColor=FAINT)
        self.label = ParagraphStyle("label", parent=self.base, fontName=f.bold, fontSize=6.8, leading=9,
                                    textColor=FAINT)
        self.h1 = ParagraphStyle("h1", parent=self.base, fontName=f.bold, fontSize=18, leading=22)
        self.h2 = ParagraphStyle("h2", parent=self.base, fontName=f.bold, fontSize=12.5, leading=16)
        self.h3 = ParagraphStyle("h3", parent=self.base, fontName=f.bold, fontSize=10.5, leading=14)
        self.big = ParagraphStyle("big", parent=self.base, fontName=f.bold, fontSize=22, leading=26)
        self.score = ParagraphStyle("score", parent=self.big, fontSize=18, leading=22, alignment=2)
        self.right = ParagraphStyle("right", parent=self.base, alignment=2)
        self.made = ParagraphStyle("made", parent=self.tiny, alignment=2)
        self.label_right = ParagraphStyle("label_right", parent=self.label, alignment=2)

    def t(self, text) -> str:
        """Escaped, font-safe text for paragraph markup."""
        return escape(plain("" if text is None else text, self.f.covers))

    def c(self, text, colour, bold: bool = False) -> str:
        body = f"<b>{self.t(text)}</b>" if bold else self.t(text)
        return f'<font color="{_hex(colour)}">{body}</font>'

    def p(self, markup: str, style: Optional[ParagraphStyle] = None) -> Paragraph:
        return Paragraph(markup, style or self.base)

    def chips(self, items: list, width: float) -> Paragraph:
        """(text, colour) items in rows that break only between items, so a
        rule like "Size within the account" is never split."""
        style, gap = self.small, pdfmetrics.stringWidth("   ", self.f.regular, self.small.fontSize)
        lines: list = [[]]
        used = 0.0
        for text, colour in items:
            size = pdfmetrics.stringWidth(plain(text, self.f.covers), self.f.regular, style.fontSize)
            if lines[-1] and used + gap + size > width - 4:
                lines.append([])
                used = 0.0
            used += (gap if lines[-1] else 0.0) + size
            lines[-1].append(self.c(text, colour))
        return self.p("<br/>".join(GAP.join(line) for line in lines), style)


def _box(rows: list, background, border, width: float = FRAME_W) -> Table:
    table = Table([[row] for row in rows], colWidths=[width])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background), ("BOX", (0, 0), (-1, -1), 0.8, border),
        ("LEFTPADDING", (0, 0), (-1, -1), PAD), ("RIGHTPADDING", (0, 0), (-1, -1), PAD),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, 0), PAD), ("BOTTOMPADDING", (0, -1), (-1, -1), PAD),
    ]))
    return table


def _pair(left, right, right_width: float, width: float) -> Table:
    table = Table([[left, right]], colWidths=[width - right_width, right_width])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return table


def _line(width: float, colour=RULE) -> Table:
    rule = Table([[""]], colWidths=[width], rowHeights=[3])
    rule.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.6, colour)]))
    return rule


def _section(w: _Writer, title: str, body: list, keep_first: bool = False) -> list:
    """A titled section. With ``keep_first`` the title stays with the first
    box, kept whole; otherwise the section starts on this page when there is
    room for the title and the start of its body (a long box then runs on,
    row by row), else on the next page."""
    head = [w.p(w.t(title), w.h2), _line(FRAME_W), Spacer(1, 5)]
    if keep_first and body:
        return [Spacer(1, 10), KeepTogether(head + body[:1])] + body[1:]
    return [CondPageBreak(SECTION_ROOM), Spacer(1, 10)] + head + body


def _boxes(items: list) -> tuple[list, bool]:
    """(box, keep whole) pairs as a section body, 6 pt apart, and whether the
    section keeps its title with the first box."""
    body: list = []
    for index, (box, keep) in enumerate(items):
        if index:
            body += [Spacer(1, 6), KeepTogether([box]) if keep else box]
        else:
            body.append(box)
    return body, bool(items) and items[0][1]


def _labeled(w: _Writer, label: str, text, colour=INK) -> list:
    if not text:
        return []
    return [w.p(w.t(label.upper()), w.label), w.p(w.c(text, colour)), Spacer(1, 3)]


def _example(w: _Writer, example: dict, why_shown: bool = False) -> list:
    out = []
    if example.get("option"):
        out.append(w.p(w.t(f"{example.get('time') or ''} · {example['option']}"), w.small))
    out += _labeled(w, "What happened", example.get("what"))
    if not why_shown:
        out += _labeled(w, "Why it matters", example.get("why"))
    out += _labeled(w, "What would have been better", example.get("better"), GREEN)
    return out


def _lesson_head(w: _Writer, lesson: dict, width: float) -> Table:
    count = lesson.get("count") or 0
    title = f"{lesson.get('title', '')}{f' · {count} times' if count > 1 else ''}"
    impact = lesson.get("impact_rs")
    right = w.p(w.c(format_rs(impact), _tone(impact), bold=True), w.right) if impact is not None else ""
    return _pair(w.p(w.c(title, AMBER_DARK, bold=True), w.h3), right, 80, width)


def _examples(w: _Writer, lesson: dict, inner: float, divider) -> list:
    rows: list = []
    seen: set = set()
    for index, example in enumerate(lesson.get("examples") or []):
        if index:
            rows += [_line(inner, divider), Spacer(1, 4)]
        # [O24-SR] A "why" already told in this lesson is not printed again (Oct 23: nine stops moved down).
        rows += _example(w, example, why_shown=example.get("why") in seen)
        seen.add(example.get("why"))
    return rows


def _lesson(w: _Writer, lesson: dict) -> list:
    inner = FRAME_W - 2 * PAD
    rows: list = [_lesson_head(w, lesson, inner), Spacer(1, 4)] + _examples(w, lesson, inner, AMBER_LINE)
    if lesson.get("also"):
        rows += [_line(inner, AMBER_LINE), Spacer(1, 2), w.p(w.t("ALSO ON THIS TRADE"), w.label)]
        for also in lesson["also"]:
            rows.append(w.p(f"{w.c(also.get('title', '') + '.', AMBER_DARK, bold=True)} {w.t(also.get('what'))} "
                            f"{w.c(also.get('better') or '', GREEN)}"))
        rows.append(Spacer(1, 4))
    rows.append(_box([w.p(w.c(f"Next time: {lesson.get('rule', '')}", TEAL, bold=True))], TEAL_BG, TEAL, inner))
    return [_box(rows, AMBER_BG, AMBER_LINE)]


def _more(w: _Writer, lesson: dict) -> tuple:
    """One more lesson with every example; kept whole up to two examples."""
    inner = FRAME_W - 2 * PAD
    rows: list = [_lesson_head(w, lesson, inner), Spacer(1, 3)] + _examples(w, lesson, inner, RULE)
    rows.append(w.p(w.c(f"Next time: {lesson.get('rule', '')}", TEAL)))
    return _box(rows, colors.white, RULE), len(lesson.get("examples") or []) <= 2


def _headline(w: _Writer, document: dict, review: dict) -> list:
    inner = FRAME_W - 2 * PAD
    headline = review.get("headline") or {}
    score, stats, account = review.get("score"), review.get("stats"), review.get("account")
    source = " · from your Zerodha orders" if review.get("source") == "ZERODHA" else ""
    rows: list = [w.p(w.t(long_day(document.get("day")) + source), w.small)]
    pnl = headline.get("pnl")
    left = w.p(w.c(format_rs(pnl), _tone(pnl), bold=True), w.big) if pnl is not None else ""
    right = ""
    if score:
        right = [w.p(w.c(f"{score.get('kept')}/{score.get('of')}", _score_tone(score.get("pct")), bold=True),
                     w.score), w.p(w.t("RULES KEPT"), w.label_right)]
    if left or right:
        rows.append(_pair(left, right, 110, inner))
    rows.append(w.p(w.t(headline.get("text") or "")))
    bits = []
    if stats:
        wins, losses = stats.get("wins", 0), stats.get("losses", 0)
        bits.append(w.t(f"{wins} win{'' if wins == 1 else 's'} · {losses} loss{'' if losses == 1 else 'es'}"))
        if stats.get("charges") is not None:
            bits.append(w.t(f"Charges {format_rs(stats['charges'], signed=False)}"))
        if stats.get("time_in_market_min") is not None:
            bits.append(w.t(f"In the market {minutes_label(stats['time_in_market_min'])}"))
    if account and account.get("pnl_pct") is not None:
        bits.append(w.c(f"{signed_percent(account['pnl_pct'])} of your account", _tone(account["pnl_pct"])))
    if bits:
        rows.append(w.p(GAP.join(bits), w.small))
    return [_box(rows, PANEL, RULE)]


def _focus(w: _Writer, focus: Optional[dict]) -> list:
    if not focus:
        return []
    return [Spacer(1, 8), _box([w.p(w.c("TOMORROW, FOCUS ON ONE THING", TEAL, bold=True), w.label),
                                w.p(w.c(focus.get("rule", ""), TEAL, bold=True), w.h3),
                                w.p(w.t(focus.get("text", "")), w.small)], TEAL_BG, TEAL)]


def _well_done(w: _Writer, well: list) -> list:
    rows = []
    for good in well:
        option = f" ({good['option']})" if good.get("option") else ""
        rows.append(w.p(f"{w.c('✓ ' + good.get('title', ''), GREEN, bold=True)}{w.c(option, GREEN)}: "
                        f"{w.c(good.get('reason', ''), MUTED)}"))
    return _section(w, "What you did well", rows)


def _rules_as_of(score: dict) -> str:
    """[O24-SB] " Rules of 24 Oct 2026.": the rules this day was checked with."""
    try:
        return f" Rules of {datetime.fromisoformat(score['rules_version']).strftime('%d %b %Y')}."
    except (KeyError, TypeError, ValueError):
        return ""


def _rules(w: _Writer, score: Optional[dict], past: bool) -> list:
    if not score:
        return []
    rows = []
    for rule in score.get("rules") or []:
        kept = rule.get("kept") == rule.get("of")
        name = w.c(f"{'✓' if kept else '✗'} {rule.get('name', '')}", GREEN if kept else AMBER, bold=True)
        means = f"<br/>{w.c(rule['means'], FAINT)}" if rule.get("means") else ""
        rows.append([w.p(name + means, w.small), w.p(w.t(f"{rule.get('kept')}/{rule.get('of')}"), w.right)])
    table = Table(rows, colWidths=[FRAME_W - 50, 50])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
                               ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                               ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]))
    intro = w.p(w.t("Each trade is checked against the same rules. This counts how you traded, not whether it "
                    f"made money.{_rules_as_of(score)}"), w.small)
    return _section(w, TITLES["rules"][past], [intro, Spacer(1, 3), table])


def _trade(w: _Writer, story: dict) -> tuple:
    """One trade as the page tells it; kept whole on one page."""
    inner = FRAME_W - 2 * PAD
    label = " · bought again on the card" if story.get("reentry") else ("" if story.get("on_card") else " · no card")
    head = w.p(w.t(f"{story.get('time', '')} · {story.get('option', '')}{label}"), w.h3)
    pnl = story.get("pnl")
    right = w.p(w.c(format_rs(pnl), _tone(pnl), bold=True), w.right) if pnl is not None else ""
    rows: list = [_pair(head, right, 80, inner)]
    checks = story.get("checks") or []
    if checks:
        rows.append(w.chips([(f"{'✓' if c.get('kept') else '✗'} {c.get('name', '')}", GREEN if c.get("kept") else RED)
                             for c in checks], inner))
    drawing = price_chart(story.get("chart"), w.f, inner)
    if drawing is not None:
        rows += [Spacer(1, 3), drawing, Spacer(1, 2)]
    for line in story.get("option_lines") or []:
        rows.append(w.p(w.t(f"• {line}"), w.small))
    timeline = [[w.p(w.t(event.get("at", "")), w.tiny),
                 w.p(w.c(event.get("text", ""), SKY) if event.get("who") == "card" else
                     w.c(event.get("text", ""), TEAL) if event.get("who") == "assistant" else w.t(event.get("text", "")),
                     w.small)]
                for event in story.get("timeline") or []]
    if timeline:
        table = Table(timeline, colWidths=[34, inner - 34])
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (0, -1), 0),
                                   ("LEFTPADDING", (1, 0), (1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                   ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                                   ("LINEBEFORE", (1, 0), (1, -1), 0.6, RULE)]))
        rows += [Spacer(1, 3), table]
    if story.get("result"):
        rows += [Spacer(1, 3), w.p(w.t(story["result"]), w.small)]
    marks = [(f"• {title}", AMBER) for title in story.get("mistakes") or []] + \
            [(f"✓ {title}", GREEN) for title in story.get("good") or []]
    if marks:
        rows.append(w.chips(marks, inner))
    return _box(rows, colors.white, RULE), True


def _orders(w: _Writer, orders: Optional[dict], past: bool) -> list:
    if not orders:
        return []
    rejected = orders.get("rejected") or []
    line = (f"{orders.get('placed', 0)} placed · {orders.get('filled', 0)} filled · {len(rejected)} refused · "
            f"{orders.get('cancelled_unfilled', 0)} cancelled unfilled")
    if orders.get("modified"):
        line += f" · {orders['modified']} changed after placing"
    if orders.get("market"):
        line += f" · {orders['market']} at market price"
    body: list = [w.p(w.t(line))]
    for order in rejected:
        side = "Buy" if order.get("side") == "BUY" else "Sell"
        # [O24-RF] The plain reason first; Zerodha's own words under it.
        said = order.get("plain") or order.get("reason")
        reason = f": {said}" if said else ""
        refused = f"{side} {order.get('quantity', '')} {order.get('tradingsymbol', '')} refused{reason}"
        body.append(w.p(f"{w.c(order.get('at', ''), FAINT)}{GAP}{w.c(refused, RED)}", w.small))
        if order.get("plain") and order.get("reason"):
            body.append(w.p(w.c(f"Zerodha: {order['reason']}", FAINT), w.small))
    return _section(w, TITLES["orders"][past], body)


def _untaken(w: _Writer, untaken: dict) -> list:
    cards = untaken.get("cards") or []
    if not cards:
        return []
    body: list = [w.p(w.t(untaken.get("text", "")), w.small)]
    for card in cards:
        markup = f"{w.c(card.get('time', ''), FAINT)}{GAP}{w.t(card.get('option', ''))} · {w.t(card.get('status', ''))}"
        if card.get("plan_pnl") is not None:
            markup += f"{GAP}{w.c(format_rs(card['plan_pnl']) + ' on 1 lot', _tone(card['plan_pnl']))}"
        if card.get("note"):
            markup += f"{GAP}{w.c('— ' + str(card['note']), FAINT)}"
        body.append(w.p(markup, w.small))
    return _section(w, "Cards you did not take", body)


def build_story(document: dict, f: Fonts) -> list:
    """The flowables for one day's review, in the page's order."""
    w = _Writer(f)
    review = document.get("review") or {}
    day, today = document.get("day") or "", document.get("today") or ""
    past = bool(today) and day < today
    made = ""
    try:
        made = f"Made {datetime.fromisoformat(document['as_of']).strftime('%d %b %Y, %H:%M')} IST"
    except (KeyError, TypeError, ValueError):
        pass
    story: list = [_pair(w.p(w.t("Your trading review"), w.h1), w.p(w.t(made), w.made), 160, FRAME_W),
                   Spacer(1, 6)]
    story += _headline(w, document, review)
    story += _focus(w, document.get("focus"))
    if review.get("lesson"):
        story += _section(w, TITLES["lesson"][past], _lesson(w, review["lesson"]))
    if review.get("well_done"):
        story += _well_done(w, review["well_done"])
    more = review.get("more_lessons") or []
    if more:
        body, keep = _boxes([_more(w, lesson) for lesson in more])
        story += _section(w, TITLES["more"][past], body, keep_first=keep)
    story += _rules(w, review.get("score"), past)
    trades = review.get("trades") or []
    if trades:
        body, keep = _boxes([_trade(w, t) for t in trades])
        story += _section(w, "Your trades, step by step", body, keep_first=keep)
    story += _orders(w, review.get("orders"), past)
    story += _untaken(w, review.get("untaken") or {})
    notes = review.get("notes") or []
    if notes:
        story += [Spacer(1, 10)] + [w.p(w.t(note), w.tiny) for note in notes]
    return story


class _PagedCanvas(rl_canvas.Canvas):
    """Adds "Page n of m", the footer and, after page 1, the day."""

    def __init__(self, *args, heading: str = "", font: str = "Helvetica", **kwargs):
        super().__init__(*args, **kwargs)
        self._pages: list = []
        self._heading = heading
        self._font = font

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self.setFont(self._font, 7.5)
            self.setFillColor(FAINT)
            self.drawString(MARGIN, 9 * mm, FOOTER)
            self.drawRightString(PAGE_W - MARGIN, 9 * mm, f"Page {self._pageNumber} of {total}")
            if self._pageNumber > 1:
                self.drawString(MARGIN, PAGE_H - 9 * mm, self._heading)
            super().showPage()
        super().save()


def render_review_pdf(document: dict, *, compress: bool = True) -> bytes:
    """One day's review as PDF bytes. ``document``: day, today, review (a
    partner_lessons.day_review), focus (or None), as_of."""
    f = fonts()
    story = build_story(document, f)
    heading = plain(f"Your trading review · {short_day(document.get('day') or '')}", f.covers)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=15 * mm, bottomMargin=16 * mm,
        title=f"Trading review {document.get('day') or ''}", author="Trading Sentinel", subject=FOOTER,
        pageCompression=1 if compress else 0)
    with _LOCK:
        doc.build(story, canvasmaker=lambda *a, **k: _PagedCanvas(*a, heading=heading, font=f.regular, **k))
    return buffer.getvalue()
