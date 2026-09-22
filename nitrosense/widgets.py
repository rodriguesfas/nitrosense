"""Cairo widgets in the NitroSense Windows HUD style."""

from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

ORANGE = (1.0, 0.416, 0.0)
ORANGE_HOT = (1.0, 0.22, 0.12)
TRACK = (0.18, 0.18, 0.18)
WHITE = (0.96, 0.96, 0.96)
MUTED = (0.62, 0.62, 0.62)
NET = (0.35, 0.72, 1.0)
SWAP = (0.95, 0.55, 0.18)
DISK = (0.72, 0.52, 1.0)


def _rgb(cr, color, alpha: float = 1.0) -> None:
    cr.set_source_rgba(color[0], color[1], color[2], alpha)


def _font(cr, size: float, bold: bool = False) -> None:
    cr.select_font_face("Inter", 0, 1 if bold else 0)
    cr.set_font_size(size)


def _center_text(cr, text: str, x: float, y: float) -> None:
    ext = cr.text_extents(text)
    cr.move_to(x - ext.width / 2 - ext.x_bearing, y - ext.height / 2 - ext.y_bearing)
    cr.show_text(text)


class RingGauge(Gtk.DrawingArea):
    """Load ring with temperature in the centre — the classic NitroSense gauge."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.title = title
        self.temp: float | None = None
        self.load: float | None = None
        self.rpm: int | None = None
        self.hint = ""
        self.set_content_width(250)
        self.set_content_height(250)
        self.set_hexpand(False)
        self.set_draw_func(self._draw)

    def update(
        self,
        temp: float | None,
        load: float | None,
        rpm: int | None = None,
        hint: str = "",
    ) -> None:
        self.temp = temp
        self.load = load
        self.rpm = rpm
        self.hint = hint
        self.queue_draw()

    def _draw(self, _area, cr, width: int, height: int) -> None:
        cx, cy = width / 2, height / 2 + 6
        radius = min(width, height) * 0.32
        load = 0.0 if self.load is None else max(0.0, min(1.0, self.load / 100.0))
        hot = (self.temp or 0) >= 80

        cr.set_line_cap(1)  # ROUND
        cr.set_line_width(10)
        _rgb(cr, TRACK)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        start = -math.pi / 2
        cr.set_line_width(10)
        _rgb(cr, ORANGE_HOT if hot else ORANGE)
        cr.arc(cx, cy, radius, start, start + 2 * math.pi * load)
        cr.stroke()

        cr.set_line_width(1.6)
        _rgb(cr, ORANGE, 0.4)
        cr.arc(cx, cy, radius + 12, 0, 2 * math.pi)
        cr.stroke()

        _font(cr, 12, bold=True)
        _rgb(cr, ORANGE)
        _center_text(cr, self.title, cx, cy - radius - 18)

        temp_txt = "—" if self.temp is None else f"{self.temp:.0f}"
        _rgb(cr, WHITE)
        _font(cr, 40, bold=True)
        _center_text(cr, temp_txt, cx, cy - 6)
        _font(cr, 11, bold=False)
        _rgb(cr, MUTED)
        _center_text(cr, "°C", cx, cy + 20)

        bits: list[str] = []
        if self.load is not None:
            bits.append(f"{self.load:.0f}%")
        if self.rpm is not None:
            bits.append(f"{self.rpm} RPM")
        if bits:
            _font(cr, 11)
            _rgb(cr, MUTED)
            _center_text(cr, "   ".join(bits), cx, cy + radius + 20)


class LaptopHero(Gtk.DrawingArea):
    """Laptop silhouette with orange glow for the active mode (stands in for the 3D avatar)."""

    def __init__(self) -> None:
        super().__init__()
        self.mode = "balanced"
        self.angle = 0.0
        self.rpm = 0.0
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_draw_func(self._draw)

    def tick(self, rpm: float | None) -> None:
        self.rpm = 0.0 if rpm is None else float(rpm)
        speed = 0.04 + min(self.rpm, 8000) / 8000.0 * 0.45
        self.angle = (self.angle + speed) % (2 * math.pi)
        self.queue_draw()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.queue_draw()

    def _draw(self, _area, cr, width: int, height: int) -> None:
        glow = {
            "quiet": 0.22,
            "balanced": 0.45,
            "performance": 0.85,
        }.get(self.mode, 0.4)

        cr.set_source_rgb(0.03, 0.03, 0.03)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # HUD grid
        cr.set_line_width(1)
        _rgb(cr, ORANGE, 0.04)
        step = 28
        for x in range(0, width, step):
            cr.move_to(x, 0)
            cr.line_to(x, height)
            cr.stroke()
        for y in range(0, height, step):
            cr.move_to(0, y)
            cr.line_to(width, y)
            cr.stroke()

        cx, cy = width / 2, height / 2 - 28
        screen_w, screen_h = min(420, width * 0.72), min(240, height * 0.48)
        x0, y0 = cx - screen_w / 2, cy - screen_h / 2 - 36

        # glow
        cr.set_line_width(18)
        _rgb(cr, ORANGE, glow * 0.25)
        _round_rect(cr, x0 - 8, y0 - 8, screen_w + 16, screen_h + 70, 18)
        cr.stroke()

        # lid
        cr.set_line_width(2.5)
        _rgb(cr, ORANGE, 0.35 + glow * 0.5)
        _round_rect(cr, x0, y0, screen_w, screen_h, 14)
        cr.stroke()
        _rgb(cr, (0.07, 0.07, 0.08))
        _round_rect(cr, x0 + 8, y0 + 8, screen_w - 16, screen_h - 16, 8)
        cr.fill()

        _font(cr, 22, bold=True)
        _rgb(cr, ORANGE, 0.9)
        _center_text(cr, "NITRO", cx, y0 + screen_h / 2 - 6)
        _font(cr, 11)
        _rgb(cr, WHITE, 0.55)
        _center_text(cr, "SENSE", cx, y0 + screen_h / 2 + 16)

        # deck
        deck_y = y0 + screen_h + 6
        _rgb(cr, (0.1, 0.1, 0.11))
        _round_rect(cr, x0 + 20, deck_y, screen_w - 40, 44, 6)
        cr.fill()
        _rgb(cr, ORANGE, 0.4)
        cr.set_line_width(1.5)
        _round_rect(cr, x0 + 20, deck_y, screen_w - 40, 44, 6)
        cr.stroke()

        self._fan(cr, x0 + 70, deck_y + 22, 14)
        self._fan(cr, x0 + screen_w - 70, deck_y + 22, 14)

    def _fan(self, cr, x: float, y: float, r: float) -> None:
        _rgb(cr, TRACK)
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.fill()
        cr.set_line_width(1)
        _rgb(cr, ORANGE, 0.8)
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.stroke()
        for i in range(3):
            a = self.angle + i * 2 * math.pi / 3
            cr.save()
            cr.translate(x, y)
            cr.rotate(a)
            cr.move_to(0, 0)
            cr.curve_to(r * 0.2, -r * 0.15, r * 0.7, -r * 0.35, r * 0.85, 0)
            cr.curve_to(r * 0.7, r * 0.15, r * 0.2, r * 0.2, 0, 0)
            _rgb(cr, ORANGE, 0.9)
            cr.fill()
            cr.restore()


class HudBar(Gtk.DrawingArea):
    """Compact HUD bar — RAM / SWAP / NET / DISK in the footer."""

    def __init__(self, title: str, accent=ORANGE, width: int = 400) -> None:
        super().__init__()
        self.title = title
        self.accent = accent
        self.right = "—"
        self.pct: float | None = None
        self.set_content_width(width)
        self.set_content_height(36)
        self.set_hexpand(False)
        self.set_draw_func(self._draw)

    def update(self, right: str, pct: float | None) -> None:
        self.right = right
        self.pct = pct
        self.queue_draw()

    def _draw(self, _area, cr, width: int, height: int) -> None:
        cr.set_source_rgb(0.07, 0.07, 0.08)
        _round_rect(cr, 0, 0, width, height, 4)
        cr.fill()
        _rgb(cr, self.accent, 0.35)
        cr.set_line_width(1)
        _round_rect(cr, 0.5, 0.5, width - 1, height - 1, 4)
        cr.stroke()

        _font(cr, 11, bold=True)
        _rgb(cr, self.accent)
        cr.move_to(10, height / 2 + 4)
        cr.show_text(self.title)
        title_w = cr.text_extents(self.title).width

        label = self.right or "—"
        _font(cr, 11, bold=True)
        _rgb(cr, WHITE)
        label_w = cr.text_extents(label).width
        cr.move_to(width - label_w - 10, height / 2 + 4)
        cr.show_text(label)

        bar_x = 10 + title_w + 8
        bar_right = width - label_w - 18
        bar_w = max(24, bar_right - bar_x)
        bar_h = 8
        bar_y = height / 2 - bar_h / 2
        _rgb(cr, TRACK)
        _round_rect(cr, bar_x, bar_y, bar_w, bar_h, 3)
        cr.fill()
        fill = 0.0 if self.pct is None else max(0.0, min(1.0, self.pct / 100.0))
        hot = fill >= 0.9
        _rgb(cr, ORANGE_HOT if hot else self.accent)
        if fill > 0:
            _round_rect(cr, bar_x, bar_y, max(bar_w * fill, 3), bar_h, 3)
            cr.fill()


class CoreStrip(Gtk.DrawingArea):
    """Per-core CPU bars, same idea as GNOME Resources."""

    def __init__(self) -> None:
        super().__init__()
        self.cores: list[float] = []
        self.set_content_height(64)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def update(self, cores: list[float]) -> None:
        self.cores = list(cores)
        self.queue_draw()

    def _draw(self, _area, cr, width: int, height: int) -> None:
        cr.set_source_rgb(0.07, 0.07, 0.08)
        _round_rect(cr, 0, 0, width, height, 4)
        cr.fill()
        _font(cr, 11, bold=True)
        _rgb(cr, ORANGE)
        cr.move_to(10, 16)
        cr.show_text("CPU CORES")
        n = len(self.cores) or 1
        gap = 3
        x0, y0, bar_h = 10, 24, height - 32
        bar_w = max(4, (width - 20 - gap * (n - 1)) / n)
        for i, load in enumerate(self.cores):
            x = x0 + i * (bar_w + gap)
            _rgb(cr, TRACK)
            _round_rect(cr, x, y0, bar_w, bar_h, 2)
            cr.fill()
            fill = max(0.0, min(1.0, load / 100.0))
            if fill > 0:
                h = max(2, bar_h * fill)
                _rgb(cr, ORANGE_HOT if fill >= 0.9 else ORANGE)
                _round_rect(cr, x, y0 + bar_h - h, bar_w, h, 2)
                cr.fill()


class Sparkline(Gtk.DrawingArea):
    def __init__(self, title: str, unit: str, color=ORANGE) -> None:
        super().__init__()
        self.title = title
        self.unit = unit
        self.color = color
        self.points: list[float] = []
        self.set_content_height(120)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def push(self, value: float | None) -> None:
        if value is None:
            return
        self.points.append(float(value))
        self.points = self.points[-1800:]
        self.queue_draw()

    def _draw(self, _area, cr, width: int, height: int) -> None:
        cr.set_source_rgb(0.07, 0.07, 0.08)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        _font(cr, 12, bold=True)
        _rgb(cr, MUTED)
        cr.move_to(12, 18)
        cr.show_text(self.title)
        if not self.points:
            return
        last = self.points[-1]
        _rgb(cr, WHITE)
        _font(cr, 16, bold=True)
        cr.move_to(width - 118, 20)
        if self.unit in {"GB", "Mbps", "MB/s"}:
            cr.show_text(f"{last:.1f} {self.unit}")
        else:
            cr.show_text(f"{last:.0f} {self.unit}")

        lo, hi = min(self.points), max(self.points)
        if hi - lo < 1:
            hi = lo + 1
        pad_t, pad_b, pad_x = 36, 14, 12
        usable_h = height - pad_t - pad_b
        usable_w = width - 2 * pad_x
        n = max(1, len(self.points) - 1)
        cr.set_line_width(2)
        _rgb(cr, self.color)
        for i, val in enumerate(self.points):
            x = pad_x + usable_w * i / n
            y = pad_t + usable_h * (1 - (val - lo) / (hi - lo))
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()


class ModeIcon(Gtk.DrawingArea):
    def __init__(self, kind: str) -> None:
        super().__init__()
        self.kind = kind
        self.set_content_width(42)
        self.set_content_height(42)
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr, width: int, height: int) -> None:
        cx, cy = width / 2, height / 2
        _rgb(cr, WHITE)
        cr.set_line_width(2.2)
        cr.set_line_cap(1)
        cr.set_line_join(1)
        kind = self.kind
        if kind == "quiet":
            cr.arc(cx, cy, 12, 0.45 * math.pi, 1.55 * math.pi)
            cr.stroke()
            cr.move_to(cx + 4, cy - 10)
            cr.line_to(cx + 4, cy + 10)
            cr.stroke()
        elif kind == "balanced":
            cr.move_to(cx, cy + 12)
            cr.line_to(cx, cy - 4)
            cr.stroke()
            cr.move_to(cx - 14, cy - 2)
            cr.line_to(cx + 14, cy - 2)
            cr.stroke()
            cr.move_to(cx - 14, cy - 2)
            cr.line_to(cx - 8, cy + 6)
            cr.move_to(cx + 14, cy - 2)
            cr.line_to(cx + 8, cy + 6)
            cr.stroke()
        elif kind == "performance":
            cr.move_to(cx + 2, cy - 14)
            cr.line_to(cx - 6, cy + 1)
            cr.line_to(cx + 2, cy + 1)
            cr.line_to(cx - 2, cy + 14)
            cr.line_to(cx + 8, cy - 1)
            cr.line_to(cx - 1, cy - 1)
            cr.close_path()
            cr.fill()
        elif kind == "auto":
            cr.arc(cx, cy, 11, 0.15 * math.pi, 1.65 * math.pi)
            cr.stroke()
            cr.move_to(cx + 8, cy - 8)
            cr.line_to(cx + 2, cy - 2)
            cr.stroke()
        elif kind == "max":
            for i in range(3):
                a = i * 2 * math.pi / 3
                cr.move_to(cx, cy)
                cr.line_to(cx + 12 * math.cos(a), cy + 12 * math.sin(a))
                cr.stroke()
            cr.arc(cx, cy, 3, 0, 2 * math.pi)
            cr.fill()
        else:
            cr.move_to(cx - 12, cy - 6)
            cr.line_to(cx + 12, cy - 6)
            cr.move_to(cx - 12, cy + 6)
            cr.line_to(cx + 12, cy + 6)
            cr.stroke()
            cr.arc(cx - 4, cy - 6, 3, 0, 2 * math.pi)
            cr.fill()
            cr.arc(cx + 5, cy + 6, 3, 0, 2 * math.pi)
            cr.fill()


def _round_rect(cr, x, y, w, h, r) -> None:
    cr.new_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
