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

    def __init__(self, title: str, size: int = 200) -> None:
        super().__init__()
        self.title = title
        self.temp: float | None = None
        self.load: float | None = None
        self.rpm: int | None = None
        self.hint = ""
        self.set_content_width(size)
        self.set_content_height(size)
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
        self.cpu_angle = 0.0
        self.gpu_angle = 0.8
        self.cpu_rpm = 0.0
        self.gpu_rpm = 0.0
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_content_height(360)
        self.set_draw_func(self._draw)

    def tick(self, cpu_rpm: float | None, gpu_rpm: float | None = None) -> None:
        self.cpu_rpm = 0.0 if cpu_rpm is None else float(cpu_rpm)
        self.gpu_rpm = self.cpu_rpm if gpu_rpm is None else float(gpu_rpm)
        cpu_speed = 0.05 + min(self.cpu_rpm, 8000) / 8000.0 * 0.5
        gpu_speed = 0.05 + min(self.gpu_rpm, 8000) / 8000.0 * 0.5
        self.cpu_angle = (self.cpu_angle + cpu_speed) % (2 * math.pi)
        self.gpu_angle = (self.gpu_angle + gpu_speed) % (2 * math.pi)
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

        cx = width / 2
        deck_h = 86
        gap = 10
        screen_w = min(520.0, width * 0.58)
        room = max(120.0, height - deck_h - gap - 16)
        screen_h = min(230.0, room * 0.9)
        total = screen_h + gap + deck_h
        y0 = max(8.0, (height - total) / 2)
        x0 = cx - screen_w / 2

        cr.set_line_width(18)
        _rgb(cr, ORANGE, glow * 0.25)
        _round_rect(cr, x0 - 8, y0 - 8, screen_w + 16, screen_h + deck_h + 22, 18)
        cr.stroke()

        cr.set_line_width(2.5)
        _rgb(cr, ORANGE, 0.35 + glow * 0.5)
        _round_rect(cr, x0, y0, screen_w, screen_h, 14)
        cr.stroke()
        _rgb(cr, (0.07, 0.07, 0.08))
        _round_rect(cr, x0 + 8, y0 + 8, screen_w - 16, screen_h - 16, 8)
        cr.fill()

        fan_r = max(28.0, min(42.0, screen_h * 0.28, (screen_w - 160) / 4))
        left = x0 + 18 + fan_r
        right = x0 + screen_w - 18 - fan_r
        cy_fan = y0 + screen_h / 2 + 6
        self._fan(cr, left, cy_fan, fan_r, self.cpu_angle)
        self._fan(cr, right, cy_fan, fan_r, self.gpu_angle)

        _font(cr, 20, bold=True)
        _rgb(cr, ORANGE, 0.95)
        _center_text(cr, "NITRO", cx, y0 + screen_h / 2 - 8)
        _font(cr, 11)
        _rgb(cr, WHITE, 0.55)
        _center_text(cr, "SENSE", cx, y0 + screen_h / 2 + 14)

        cpu_txt = f"{self.cpu_rpm:.0f} RPM" if self.cpu_rpm else "—"
        gpu_txt = f"{self.gpu_rpm:.0f} RPM" if self.gpu_rpm else "—"
        _font(cr, 10, bold=True)
        _rgb(cr, MUTED)
        _center_text(cr, "CPU", left, cy_fan - fan_r - 10)
        _center_text(cr, cpu_txt, left, cy_fan + fan_r + 12)
        _center_text(cr, "GPU", right, cy_fan - fan_r - 10)
        _center_text(cr, gpu_txt, right, cy_fan + fan_r + 12)

        deck_y = y0 + screen_h + gap
        _rgb(cr, (0.1, 0.1, 0.11))
        _round_rect(cr, x0 + 18, deck_y, screen_w - 36, deck_h, 8)
        cr.fill()
        _rgb(cr, ORANGE, 0.4)
        cr.set_line_width(1.5)
        _round_rect(cr, x0 + 18, deck_y, screen_w - 36, deck_h, 8)
        cr.stroke()
        _rgb(cr, ORANGE, 0.18)
        cr.set_line_width(1)
        vent_y = deck_y + 14
        for i in range(9):
            yy = vent_y + i * 6
            cr.move_to(x0 + 36, yy)
            cr.line_to(x0 + screen_w - 36, yy)
            cr.stroke()

    def _fan(self, cr, x: float, y: float, r: float, angle: float) -> None:
        _rgb(cr, (0.08, 0.08, 0.09))
        cr.arc(x, y, r + 3, 0, 2 * math.pi)
        cr.fill()
        _rgb(cr, TRACK)
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.fill()
        cr.set_line_width(2)
        _rgb(cr, ORANGE, 0.9)
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.stroke()
        blades = 5
        for i in range(blades):
            a = angle + i * 2 * math.pi / blades
            cr.save()
            cr.translate(x, y)
            cr.rotate(a)
            cr.move_to(0, 0)
            cr.curve_to(r * 0.18, -r * 0.22, r * 0.62, -r * 0.42, r * 0.9, -r * 0.08)
            cr.curve_to(r * 0.7, r * 0.28, r * 0.22, r * 0.18, 0, 0)
            cr.close_path()
            _rgb(cr, ORANGE, 0.95)
            cr.fill()
            cr.restore()
        _rgb(cr, WHITE)
        cr.arc(x, y, max(3.5, r * 0.16), 0, 2 * math.pi)
        cr.fill()
        _rgb(cr, ORANGE, 0.85)
        cr.set_line_width(1.2)
        cr.arc(x, y, max(3.5, r * 0.16), 0, 2 * math.pi)
        cr.stroke()


class KeyboardDeck(Gtk.DrawingArea):
    """Top-down keyboard with single-color orange glow (ANV15-51 has no RGB)."""

    def __init__(self) -> None:
        super().__init__()
        self.timeout_on = True
        self.pulse = 0.0
        self.set_content_height(168)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def tick(self) -> None:
        self.pulse = (self.pulse + 0.04) % (2 * math.pi)
        self.queue_draw()

    def set_timeout(self, enabled: bool) -> None:
        self.timeout_on = enabled
        self.queue_draw()

    def _draw(self, _area, cr, width: int, height: int) -> None:
        cr.set_source_rgb(0.04, 0.04, 0.04)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        kb_w = min(width - 32, 720)
        kb_h = min(height - 28, 128)
        x0 = (width - kb_w) / 2
        y0 = (height - kb_h) / 2
        _rgb(cr, (0.09, 0.09, 0.1))
        _round_rect(cr, x0, y0, kb_w, kb_h, 10)
        cr.fill()
        glow = 0.35 + 0.12 * (0.5 + 0.5 * math.sin(self.pulse))
        if self.timeout_on:
            glow *= 0.55
        cr.set_line_width(10)
        _rgb(cr, ORANGE, glow * 0.35)
        _round_rect(cr, x0 - 4, y0 - 4, kb_w + 8, kb_h + 8, 12)
        cr.stroke()
        rows = (14, 14, 13, 12, 3)
        gap = 4
        top = y0 + 12
        usable_h = kb_h - 24
        row_h = (usable_h - gap * (len(rows) - 1)) / len(rows)
        for r, count in enumerate(rows):
            row_w = kb_w - 24
            if count == 3:
                keys = (0.22, 0.56, 0.22)
            else:
                keys = tuple(1.0 / count for _ in range(count))
            x = x0 + 12
            y = top + r * (row_h + gap)
            for frac in keys:
                w = row_w * frac - gap
                _rgb(cr, (0.13, 0.13, 0.14))
                _round_rect(cr, x, y, w, row_h, 3)
                cr.fill()
                cr.set_line_width(1)
                _rgb(cr, ORANGE, 0.25 + glow)
                _round_rect(cr, x, y, w, row_h, 3)
                cr.stroke()
                x += w + gap

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

    def __init__(self, title: str, accent=ORANGE, width: int = 400, expand: bool = False) -> None:
        super().__init__()
        self.title = title
        self.accent = accent
        self.right = "—"
        self.pct: float | None = None
        self.set_content_width(width)
        self.set_content_height(36)
        self.set_hexpand(expand)
        if expand:
            self.set_halign(Gtk.Align.FILL)
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
    """Per-core CPU bars (compact fallback)."""

    def __init__(self, show_title: bool = True) -> None:
        super().__init__()
        self.cores: list[float] = []
        self.show_title = show_title
        self.set_content_height(108 if not show_title else 64)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def update(self, cores: list[float]) -> None:
        self.cores = list(cores)
        self.queue_draw()

    def _draw(self, _area, cr, width: int, height: int) -> None:
        cr.set_source_rgb(0.07, 0.07, 0.08)
        _round_rect(cr, 0, 0, width, height, 4)
        cr.fill()
        top = 8
        if self.show_title:
            _font(cr, 11, bold=True)
            _rgb(cr, ORANGE)
            cr.move_to(10, 16)
            cr.show_text("CPU CORES")
            top = 24
        n = len(self.cores) or 1
        gap = 4
        x0, bar_h = 10, height - top - (18 if n <= 16 else 8)
        bar_w = max(4, (width - 20 - gap * (n - 1)) / n)
        for i, load in enumerate(self.cores):
            x = x0 + i * (bar_w + gap)
            _rgb(cr, TRACK)
            _round_rect(cr, x, top, bar_w, bar_h, 2)
            cr.fill()
            fill = max(0.0, min(1.0, load / 100.0))
            if fill > 0:
                h = max(2, bar_h * fill)
                _rgb(cr, ORANGE_HOT if fill >= 0.9 else ORANGE)
                _round_rect(cr, x, top + bar_h - h, bar_w, h, 2)
                cr.fill()
            if bar_w >= 14:
                _font(cr, 8)
                _rgb(cr, MUTED)
                _center_text(cr, str(i), x + bar_w / 2, top + bar_h + 8)


def fmt_cpu_freq(ghz: float | None) -> str:
    if ghz is None:
        return "—"
    if ghz >= 1.0:
        return f"{ghz:.2f} GHz"
    return f"{ghz * 1000:.2f} MHz"


class MiniSpark(Gtk.DrawingArea):
    """Resources-style grid chart. `ceiling` is the Y max (100 for %); None autoscales from 0."""

    def __init__(
        self,
        color=ORANGE,
        ceiling: float | None = 100.0,
        height: int = 76,
        floor: float = 1.0,
    ) -> None:
        super().__init__()
        self.color = color
        self.ceiling = ceiling
        self.floor = floor
        self.points: list[float] = []
        self.set_content_height(height)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def push(self, value: float) -> None:
        val = max(0.0, float(value))
        if self.ceiling is not None:
            val = min(self.ceiling, val)
        self.points.append(val)
        self.points = self.points[-90:]
        self.queue_draw()

    def clear(self) -> None:
        self.points.clear()
        self.queue_draw()

    def _hi(self) -> float:
        if self.ceiling is not None:
            return self.ceiling
        return max(self.floor, max(self.points) if self.points else self.floor)

    def _draw(self, _area, cr, width: int, height: int) -> None:
        cr.set_source_rgb(0.055, 0.055, 0.055)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        cols, rows = 6, 4
        cr.set_line_width(1)
        cr.set_source_rgba(0.22, 0.22, 0.22, 0.9)
        for i in range(cols + 1):
            x = i * width / cols
            cr.move_to(x, 0)
            cr.line_to(x, height)
            cr.stroke()
        for i in range(rows + 1):
            y = i * height / rows
            cr.move_to(0, y)
            cr.line_to(width, y)
            cr.stroke()
        if not self.points:
            return
        hi = self._hi()
        n = max(1, len(self.points) - 1)
        xs: list[float] = []
        ys: list[float] = []
        for i, val in enumerate(self.points):
            xs.append(width * i / n if n else 0)
            ys.append(height * (1.0 - val / hi))
        cr.move_to(xs[0], height)
        for x, y in zip(xs, ys):
            cr.line_to(x, y)
        cr.line_to(xs[-1], height)
        cr.close_path()
        _rgb(cr, self.color, 0.22)
        cr.fill()
        cr.set_line_width(1.8)
        _rgb(cr, self.color)
        for i, (x, y) in enumerate(zip(xs, ys)):
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()


class CoreTile(Gtk.Box):
    """One logical/physical CPU card: sparkline, index, frequency, percent."""

    def __init__(self, index: int) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("ns-core-card")
        self.set_hexpand(True)
        self.set_size_request(150, -1)
        self.index = index
        self.spark = MiniSpark()
        self.caption = Gtk.Label(xalign=0)
        self.caption.add_css_class("muted")
        self.pct = Gtk.Label(xalign=0)
        self.pct.add_css_class("ns-core-pct")
        self.append(self.spark)
        self.append(self.caption)
        self.append(self.pct)
        self.update(0.0, None)

    def clear(self) -> None:
        self.spark.clear()

    def update(self, load: float, freq_ghz: float | None) -> None:
        self.spark.push(load)
        self.caption.set_text(f"CPU {self.index + 1}  ·  {fmt_cpu_freq(freq_ghz)}")
        self.pct.set_text(f"{load:.0f} %")


class MetricTile(Gtk.Box):
    """Processor-style card: sparkline, caption, live value."""

    def __init__(
        self,
        title: str,
        unit: str = "%",
        color=ORANGE,
        ceiling: float | None = 100.0,
        height: int = 88,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("ns-core-card")
        self.set_hexpand(True)
        self.set_size_request(160, -1)
        self.title = title
        self.unit = unit
        self.spark = MiniSpark(color=color, ceiling=ceiling, height=height)
        self.caption = Gtk.Label(label=title, xalign=0)
        self.caption.add_css_class("muted")
        self.value = Gtk.Label(label="—", xalign=0)
        self.value.add_css_class("ns-core-pct")
        self.append(self.spark)
        self.append(self.caption)
        self.append(self.value)

    def update(
        self,
        amount: float | None,
        *,
        caption: str | None = None,
        text: str | None = None,
    ) -> None:
        if amount is not None:
            self.spark.push(amount)
        self.caption.set_text(caption if caption is not None else self.title)
        if text is not None:
            self.value.set_text(text)
        elif amount is None:
            self.value.set_text("—")
        elif self.unit == "%":
            self.value.set_text(f"{amount:.0f} %")
        elif self.unit == "°C":
            self.value.set_text(f"{amount:.0f} °C")
        elif self.unit == "MHz":
            self.value.set_text(f"{amount:.0f} MHz")
        elif self.unit in {"Mb/s", "MB/s", "W", "GB", "RPM"}:
            self.value.set_text(f"{amount:.1f} {self.unit}" if self.unit != "RPM" else f"{amount:.0f} RPM")
        else:
            self.value.set_text(f"{amount:.1f} {self.unit}".strip())


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
    def __init__(self, kind: str, size: int = 44) -> None:
        super().__init__()
        self.kind = kind
        self.active = False
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_draw_func(self._draw)

    def set_active(self, active: bool) -> None:
        if self.active == active:
            return
        self.active = active
        self.queue_draw()

    def _draw(self, _area, cr, width: int, height: int) -> None:
        cx, cy = width / 2, height / 2
        color = ORANGE if self.active else WHITE
        _rgb(cr, color, 1.0 if self.active else 0.92)
        cr.set_line_width(2.15)
        cr.set_line_cap(1)
        cr.set_line_join(1)
        r = min(width, height) * 0.34
        kind = self.kind
        if kind == "quiet":
            cr.set_fill_rule(1)
            cr.arc(cx - r * 0.06, cy, r, 0, 2 * math.pi)
            cr.arc(cx + r * 0.46, cy - r * 0.22, r * 0.78, 0, 2 * math.pi)
            cr.fill()
        elif kind == "balanced":
            cr.arc(cx, cy - r * 0.08, r * 0.28, 0, 2 * math.pi)
            cr.stroke()
            cr.move_to(cx, cy + r * 0.18)
            cr.line_to(cx, cy + r * 0.95)
            cr.stroke()
            cr.move_to(cx - r * 1.05, cy + r * 0.22)
            cr.line_to(cx + r * 1.05, cy + r * 0.22)
            cr.stroke()
            cr.move_to(cx - r * 1.05, cy + r * 0.22)
            cr.line_to(cx - r * 0.62, cy + r * 0.82)
            cr.move_to(cx + r * 1.05, cy + r * 0.22)
            cr.line_to(cx + r * 0.62, cy + r * 0.82)
            cr.stroke()
        elif kind == "performance":
            s = r * 1.2
            cr.move_to(cx + s * 0.08, cy - s)
            cr.line_to(cx - s * 0.42, cy + s * 0.06)
            cr.line_to(cx + s * 0.04, cy + s * 0.06)
            cr.line_to(cx - s * 0.08, cy + s)
            cr.line_to(cx + s * 0.42, cy - s * 0.06)
            cr.line_to(cx - s * 0.04, cy - s * 0.06)
            cr.close_path()
            cr.fill()
        elif kind == "auto":
            cr.arc(cx, cy, r, 0.45 * math.pi, 1.95 * math.pi)
            cr.stroke()
            a = 0.45 * math.pi
            ex = cx + r * math.cos(a)
            ey = cy + r * math.sin(a)
            tx, ty = -math.sin(a), math.cos(a)
            cr.move_to(ex + tx * 5.5, ey + ty * 5.5)
            cr.line_to(ex - tx * 5.5, ey - ty * 5.5)
            cr.line_to(ex + math.cos(a) * 7, ey + math.sin(a) * 7)
            cr.close_path()
            cr.fill()
        elif kind == "max":
            blades = 5
            for i in range(blades):
                a = 0.35 + i * 2 * math.pi / blades
                cr.save()
                cr.translate(cx, cy)
                cr.rotate(a)
                cr.move_to(0, 0)
                cr.curve_to(r * 0.2, -r * 0.22, r * 0.7, -r * 0.38, r * 0.95, 0)
                cr.curve_to(r * 0.7, r * 0.28, r * 0.2, r * 0.16, 0, 0)
                cr.close_path()
                cr.fill()
                cr.restore()
            _rgb(cr, (0.08, 0.08, 0.08) if self.active else (0.12, 0.12, 0.12))
            cr.arc(cx, cy, max(2.8, r * 0.22), 0, 2 * math.pi)
            cr.fill()
            _rgb(cr, color)
            cr.set_line_width(1.2)
            cr.arc(cx, cy, max(2.8, r * 0.22), 0, 2 * math.pi)
            cr.stroke()
        else:
            for y_off, knob in ((-r * 0.42, -r * 0.28), (r * 0.42, r * 0.32)):
                cr.set_line_width(2.3)
                cr.move_to(cx - r, cy + y_off)
                cr.line_to(cx + r, cy + y_off)
                cr.stroke()
                cr.arc(cx + knob, cy + y_off, r * 0.28, 0, 2 * math.pi)
                cr.fill()


def _round_rect(cr, x, y, w, h, r) -> None:
    cr.new_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
