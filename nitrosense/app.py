"""GUI GTK4 — visual alinhado ao NitroSense Windows (Nitro V)."""

from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from nitrosense.hardware import NITRO_MODES, Hardware
from nitrosense.sensors import Sensors, read_sensors
from nitrosense.widgets import LaptopHero, ModeIcon, RamBar, RingGauge, Sparkline

ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = Path(__file__).with_name("style.css")
SETUP = ROOT / "setup.sh"


def _tile(kind: str, title: str, css: str, callback, *cb_args) -> Gtk.Button:
    btn = Gtk.Button()
    btn.add_css_class(css)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER)
    box.append(ModeIcon(kind))
    lab = Gtk.Label(label=title)
    lab.add_css_class("muted")
    box.append(lab)
    btn.set_child(box)
    btn.connect("clicked", callback, *cb_args)
    return btn


class NitroWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app, title="NitroSense")
        self.set_default_size(1280, 800)
        self.add_css_class("nitrosense")
        self.hw = Hardware()
        self._busy = False
        self._fan_mode = "auto"
        self.cpu_gauge = RingGauge("CPU")
        self.gpu_gauge = RingGauge("GPU")
        self.hero = LaptopHero()
        self.mode_buttons: dict[str, Gtk.Button] = {}
        self.fan_buttons: dict[str, Gtk.Button] = {}
        self.cpu_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.gpu_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.limit_switch = Gtk.Switch()
        self.timeout_switch = Gtk.Switch()
        self.lcd_switch = Gtk.Switch()
        self.boot_switch = Gtk.Switch()
        self.usb_values = (0, 10, 20, 30)
        self.usb_drop = Gtk.DropDown.new_from_strings(
            ["Off", "Until 10%", "Until 20%", "Until 30%"]
        )
        self.calibrate_btn = Gtk.Button(label="Start battery calibration")
        self._banner = Gtk.Label(wrap=True, xalign=0)
        self._banner.add_css_class("warn-banner")
        self._banner.set_visible(False)
        self._status = Gtk.Label(xalign=0)
        self._status.add_css_class("ns-status")
        self._chip = Gtk.Label(label="AC")
        self._chip.add_css_class("ns-chip")
        self.chart_cpu_t = Sparkline("CPU temperature", "°C")
        self.chart_gpu_t = Sparkline("GPU temperature", "°C", color=(0.3, 0.7, 1.0))
        self.chart_cpu_l = Sparkline("CPU loading", "%")
        self.chart_gpu_l = Sparkline("GPU loading", "%", color=(0.3, 0.7, 1.0))
        self.chart_ram_p = Sparkline("RAM loading", "%", color=(0.2, 0.85, 0.55))
        self.chart_ram_g = Sparkline("RAM used", "GB", color=(0.2, 0.85, 0.55))
        self.ram_bar = RamBar()
        self._ram_chip = Gtk.Label(label="RAM")
        self._ram_chip.add_css_class("ns-chip")
        self._rpm_visual = 1800.0
        self._fan_scale_to = None
        self._fan_user = False
        self._build()
        GLib.timeout_add(1000, self._tick)
        GLib.timeout_add(40, self._spin)
        GLib.idle_add(self._tick)

    def _build(self) -> None:
        brand = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        n = Gtk.Label(label="NITRO")
        n.add_css_class("ns-brand-nitro")
        s = Gtk.Label(label="SENSE")
        s.add_css_class("ns-brand-sense")
        brand.append(n)
        brand.append(s)

        header = Adw.HeaderBar()
        header.add_css_class("ns-top")
        header.set_title_widget(brand)
        header.pack_end(self._chip)
        header.pack_end(self._ram_chip)

        tabs = Gtk.Stack()
        tabs.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        tabs.set_vexpand(True)
        tabs.add_titled(self._page_home(), "home", "HOME")
        tabs.add_titled(self._page_scenario(), "scenario", "SCENARIO")
        tabs.add_titled(self._page_monitoring(), "monitoring", "MONITORING")
        tabs.add_titled(self._page_lighting(), "lighting", "LIGHTING")
        tabs.add_titled(self._page_settings(), "settings", "SETTINGS")

        switcher = Gtk.StackSwitcher(stack=tabs, hexpand=True)
        switcher.add_css_class("ns-nav")
        switcher.set_halign(Gtk.Align.CENTER)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.append(switcher)
        outer.append(self._banner)
        outer.append(tabs)
        ram_wrap = Gtk.Box(halign=Gtk.Align.CENTER)
        ram_wrap.set_margin_top(4)
        ram_wrap.set_margin_bottom(6)
        ram_wrap.append(self.ram_bar)
        outer.append(ram_wrap)
        outer.append(self._status)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(outer)
        self.set_content(toolbar)

    def _page_home(self) -> Gtk.Widget:
        overlay = Gtk.Overlay()
        overlay.set_child(self.hero)
        overlay.set_vexpand(True)

        left = Gtk.Box(halign=Gtk.Align.START, valign=Gtk.Align.START)
        left.set_margin_start(36)
        left.set_margin_top(48)
        left.append(self.cpu_gauge)
        overlay.add_overlay(left)

        right = Gtk.Box(halign=Gtk.Align.END, valign=Gtk.Align.START)
        right.set_margin_end(36)
        right.set_margin_top(48)
        right.append(self.gpu_gauge)
        overlay.add_overlay(right)

        dock = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        dock.set_halign(Gtk.Align.CENTER)
        dock.set_valign(Gtk.Align.END)
        dock.set_margin_bottom(12)

        modes = Gtk.Box(spacing=12, homogeneous=True)
        mapping = (
            ("quiet", "quiet", "Quiet"),
            ("balanced", "balanced", "Default"),
            ("performance", "performance", "Performance"),
        )
        for key, icon, title in mapping:
            btn = _tile(icon, title, "mode-tile", self._on_mode, key)
            self.mode_buttons[key] = btn
            modes.append(btn)

        fans = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        for key, icon, title in (
            ("auto", "auto", "Auto"),
            ("max", "max", "Max"),
            ("custom", "custom", "Custom"),
        ):
            btn = _tile(icon, title, "fan-pill", self._on_fan_mode, key)
            self.fan_buttons[key] = btn
            fans.append(btn)

        self.custom_box = Gtk.Box(spacing=16)
        self.custom_box.set_halign(Gtk.Align.CENTER)
        for scale, label in ((self.cpu_scale, "CPU fan"), (self.gpu_scale, "GPU fan")):
            scale.set_hexpand(True)
            scale.set_size_request(220, -1)
            scale.set_draw_value(True)
            scale.set_value(50)
            scale.connect("value-changed", self._on_fan_scale)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            lab = Gtk.Label(label=label, xalign=0)
            lab.add_css_class("muted")
            col.append(lab)
            col.append(scale)
            self.custom_box.append(col)
        self.custom_reveal = Gtk.Revealer(child=self.custom_box)
        self.custom_reveal.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)

        dock.append(modes)
        dock.append(fans)
        dock.append(self.custom_reveal)
        overlay.add_overlay(dock)
        overlay.set_clip_overlay(dock, False)
        overlay.set_measure_overlay(dock, True)
        return overlay

    def _card(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.add_css_class("panel")
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(24)
        box.set_margin_end(24)
        return box

    def _page_scenario(self) -> Gtk.Widget:
        note = Gtk.Label(
            label="Scenario — the same three operating modes and Auto / Max / Custom fans as Windows NitroSense. Use HOME for the live view.",
            wrap=True,
            xalign=0,
        )
        note.add_css_class("muted")
        card = self._card()
        card.append(note)
        return card

    def _page_monitoring(self) -> Gtk.Widget:
        grid = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
        grid.attach(self.chart_cpu_t, 0, 0, 1, 1)
        grid.attach(self.chart_gpu_t, 1, 0, 1, 1)
        grid.attach(self.chart_cpu_l, 0, 1, 1, 1)
        grid.attach(self.chart_gpu_l, 1, 1, 1, 1)
        grid.attach(self.chart_ram_p, 0, 2, 1, 1)
        grid.attach(self.chart_ram_g, 1, 2, 1, 1)
        hint = Gtk.Label(
            label="Last ~30 minutes (1 Hz). Same idea as Windows NitroSense monitoring.",
            wrap=True,
            xalign=0,
        )
        hint.add_css_class("muted")
        card = self._card()
        card.append(grid)
        card.append(hint)
        return card

    def _page_lighting(self) -> Gtk.Widget:
        self.timeout_switch.connect("state-set", self._on_flag, "backlight_timeout")
        row = Gtk.Box(spacing=12)
        row.append(Gtk.Label(label="Backlight timeout (30 s idle)", xalign=0, hexpand=True))
        row.append(self.timeout_switch)
        note = Gtk.Label(
            label="ANV15-51 ships with a single-color keyboard. 4-zone RGB controls appear here only if four_zoned_kb shows up in sysfs.",
            wrap=True,
            xalign=0,
        )
        note.add_css_class("muted")
        self._kb_rgb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        modes = Gtk.Box(spacing=8)
        for idx, name in enumerate(
            ("Static", "Breathing", "Neon", "Wave", "Shifting", "Zoom", "Meteor", "Twinkling")
        ):
            btn = Gtk.Button(label=name)
            btn.connect("clicked", self._on_rgb_mode, idx)
            modes.append(btn)
        self._kb_rgb_box.append(Gtk.Label(label="Four-zone RGB", xalign=0))
        self._kb_rgb_box.append(modes)
        card = self._card()
        card.append(row)
        card.append(note)
        card.append(self._kb_rgb_box)
        return card

    def _page_settings(self) -> Gtk.Widget:
        self.limit_switch.connect("state-set", self._on_flag, "battery_limiter")
        self.lcd_switch.connect("state-set", self._on_flag, "lcd_override")
        self.boot_switch.connect("state-set", self._on_flag, "boot_animation_sound")
        self.usb_drop.connect("notify::selected", self._on_usb)
        self.calibrate_btn.connect("clicked", self._on_calibrate)
        self._drv_label = Gtk.Label(xalign=0, wrap=True)

        def row(label: str, widget: Gtk.Widget) -> Gtk.Box:
            box = Gtk.Box(spacing=12)
            lab = Gtk.Label(label=label, xalign=0, hexpand=True)
            box.append(lab)
            box.append(widget)
            return box

        setup_btn = Gtk.Button(label="Install Linuwu driver (setup.sh)")
        setup_btn.connect("clicked", self._on_setup_help)
        card = self._card()
        card.append(self._drv_label)
        card.append(row("Battery charge limit 80%", self.limit_switch))
        card.append(row("USB charging while off", self.usb_drop))
        card.append(self.calibrate_btn)
        card.append(row("LCD override", self.lcd_switch))
        card.append(row("Boot animation / sound", self.boot_switch))
        card.append(setup_btn)
        return card

    def _spin(self) -> bool:
        self.hero.tick(self._rpm_visual)
        return True

    def _tick(self) -> bool:
        self.hw.refresh_paths()
        snap = self.hw.snapshot()
        sensors = read_sensors()
        if snap.fan_cpu_rpm is not None or snap.fan_gpu_rpm is not None:
            vals = [v for v in (snap.fan_cpu_rpm, snap.fan_gpu_rpm) if v]
            if vals:
                self._rpm_visual = sum(vals) / len(vals)
        self.cpu_gauge.update(
            sensors.cpu_temp, sensors.cpu_load, snap.fan_cpu_rpm, sensors.cpu_name or ""
        )
        self.gpu_gauge.update(
            sensors.gpu_temp, sensors.gpu_load, snap.fan_gpu_rpm, sensors.gpu_name or ""
        )
        self.chart_cpu_t.push(sensors.cpu_temp)
        self.chart_gpu_t.push(sensors.gpu_temp)
        self.chart_cpu_l.push(sensors.cpu_load)
        self.chart_gpu_l.push(sensors.gpu_load)
        self.chart_ram_p.push(sensors.ram_pct)
        self.chart_ram_g.push(sensors.ram_used_gb)
        self.ram_bar.update(sensors.ram_used_gb, sensors.ram_total_gb, sensors.ram_pct)
        self._apply_hw(snap, sensors)
        return True

    def _apply_hw(self, snap, sensors: Sensors) -> None:
        caps = snap.caps
        # Aviso de driver só na barra de estado — o Windows não tem banner laranja.

        current_mode = None
        for key, _label, fw in NITRO_MODES:
            btn = self.mode_buttons[key]
            on = snap.profile == fw
            if on:
                current_mode = key
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")
        if current_mode:
            self.hero.set_mode(current_mode)

        if not self._fan_user:
            if snap.fan_auto:
                self._fan_mode = "auto"
            elif (snap.fan_cpu_pct or 0) >= 99 and (snap.fan_gpu_pct or 0) >= 99:
                self._fan_mode = "max"
            elif not snap.fan_auto and (snap.fan_cpu_pct or snap.fan_gpu_pct):
                self._fan_mode = "custom"
        for key, btn in self.fan_buttons.items():
            if key == self._fan_mode:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")
        self.custom_reveal.set_reveal_child(self._fan_mode == "custom")

        self._busy = True
        if snap.fan_cpu_pct is not None and abs(self.cpu_scale.get_value() - snap.fan_cpu_pct) >= 1:
            self.cpu_scale.set_value(snap.fan_cpu_pct)
        if snap.fan_gpu_pct is not None and abs(self.gpu_scale.get_value() - snap.fan_gpu_pct) >= 1:
            self.gpu_scale.set_value(snap.fan_gpu_pct)
        self._set_switch(self.limit_switch, caps.battery_limiter, snap.battery_limiter)
        self._set_switch(self.timeout_switch, caps.backlight_timeout, snap.backlight_timeout)
        self._set_switch(self.lcd_switch, caps.lcd_override, snap.lcd_override)
        self._set_switch(self.boot_switch, caps.boot_animation, snap.boot_animation)
        self.usb_drop.set_sensitive(caps.usb_charging)
        if snap.usb_charging in self.usb_values:
            self.usb_drop.set_selected(self.usb_values.index(snap.usb_charging))
        self.calibrate_btn.set_sensitive(caps.battery_calibration)
        self._kb_rgb_box.set_visible(caps.rgb_keyboard)
        self._busy = False

        if sensors.ram_used_gb is not None and sensors.ram_total_gb is not None:
            self._ram_chip.set_text(
                f"RAM  {sensors.ram_used_gb:.1f}/{sensors.ram_total_gb:.0f} GB"
            )
        if sensors.on_ac:
            self._chip.set_text("AC  ·  " + (f"{sensors.battery_pct}%" if sensors.battery_pct is not None else "—"))
        else:
            self._chip.set_text(
                "BATTERY  ·  " + (f"{sensors.battery_pct}%" if sensors.battery_pct is not None else "—")
            )
        drv = {"linuwu": "Linuwu Sense", "acer_wmi": "acer_wmi", "none": "no fan driver"}[caps.driver]
        self._status.set_text(
            f"{drv}   ·   {snap.profile or 'no profile'}   ·   {sensors.cpu_name or 'CPU'}   ·   {sensors.gpu_name or 'GPU'}"
        )
        self._drv_label.set_markup(
            f"<b>Driver</b>  {drv}\n"
            f"<b>Firmware profile</b>  {snap.profile or '—'}\n"
            f"<b>Choices</b>  {' '.join(snap.profile_choices) or '—'}"
        )

    def _set_switch(self, widget: Gtk.Switch, enabled: bool, value: bool | None) -> None:
        widget.set_sensitive(enabled)
        if value is not None:
            widget.set_active(value)

    def _toast(self, message: str) -> None:
        self._status.set_text(message)

    def _run(self, fn, *args) -> None:
        try:
            fn(*args)
        except Exception as exc:  # noqa: BLE001
            self._toast(str(exc))

    def _on_mode(self, _btn, key: str) -> None:
        fw = next(item[2] for item in NITRO_MODES if item[0] == key)
        self.hero.set_mode(key)
        self._run(self.hw.set_profile, fw)

    def _on_fan_mode(self, _btn, key: str) -> None:
        self._fan_user = True
        self._fan_mode = key
        for name, btn in self.fan_buttons.items():
            if name == key:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")
        self.custom_reveal.set_reveal_child(key == "custom")
        if key == "auto":
            self._run(self.hw.set_fans, 0, 0, True)
        elif key == "max":
            self._run(self.hw.set_fans, 100, 100, False)
        else:
            cpu = max(1, int(self.cpu_scale.get_value()))
            gpu = max(1, int(self.gpu_scale.get_value()))
            self._run(self.hw.set_fans, cpu, gpu, False)

    def _on_fan_scale(self, _scale: Gtk.Scale) -> None:
        if self._busy or self._fan_mode != "custom":
            return
        if self._fan_scale_to is not None:
            GLib.source_remove(self._fan_scale_to)
        self._fan_scale_to = GLib.timeout_add(280, self._flush_fan_scale)

    def _flush_fan_scale(self) -> bool:
        self._fan_scale_to = None
        if self._fan_mode != "custom" or self._busy:
            return False
        self._run(
            self.hw.set_fans,
            max(1, int(self.cpu_scale.get_value())),
            max(1, int(self.gpu_scale.get_value())),
            False,
        )
        return False

    def _on_flag(self, switch: Gtk.Switch, state: bool, name: str) -> bool:
        if self._busy:
            return False
        self._run(self.hw.set_flag, name, state)
        return False

    def _on_usb(self, drop: Gtk.DropDown, _pspec) -> None:
        if self._busy:
            return
        idx = int(drop.get_selected())
        if 0 <= idx < len(self.usb_values):
            self._run(self.hw.set_usb_charging, self.usb_values[idx])

    def _on_calibrate(self, _btn) -> None:
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Calibrate battery?",
            body="Full cycle 100→0→100. Keep AC plugged in.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "Start")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_calibrate_resp)
        dialog.present()

    def _on_calibrate_resp(self, _dialog, response: str) -> None:
        if response == "ok":
            self._run(self.hw.set_flag, "battery_calibration", True)

    def _on_rgb_mode(self, _btn, mode: int) -> None:
        self._run(self.hw.set_rgb_mode, mode, 5, 100, 1, 255, 106, 0)

    def _on_setup_help(self, _btn) -> None:
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Install driver",
            body=f"In a terminal:\n\n{SETUP}\n\nNeeds sudo. Nitro key stays with Alfred.",
        )
        dialog.add_response("ok", "OK")
        dialog.present()


class NitroSenseApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id="org.alfred.nitrosense")
        self.window: NitroWindow | None = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        if CSS_PATH.is_file():
            provider = Gtk.CssProvider()
            provider.load_from_path(str(CSS_PATH))
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def do_activate(self) -> None:
        if self.window is None:
            self.window = NitroWindow(self)
        self.window.present()


def main(argv: list[str] | None = None) -> int:
    GLib.set_prgname("NitroSense")
    GLib.set_application_name("NitroSense")
    app = NitroSenseApplication()
    return app.run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
