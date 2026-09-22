"""GTK4 GUI — NitroSense Windows look for Acer Nitro V."""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from nitrosense.hardware import NITRO_MODES, Hardware
from nitrosense.sensors import ProcInfo, Sensors, read_sensors
from nitrosense.widgets import (
    DISK,
    CoreStrip,
    HudBar,
    LaptopHero,
    ModeIcon,
    NET,
    RingGauge,
    Sparkline,
    SWAP,
)

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
        self.set_default_size(1280, 860)
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
        self.chart_swap_p = Sparkline("SWAP loading", "%", color=SWAP)
        self.chart_swap_g = Sparkline("SWAP used", "GB", color=SWAP)
        self.chart_net_rx = Sparkline("Network down", "Mbps", color=NET)
        self.chart_net_tx = Sparkline("Network up", "Mbps", color=NET)
        self.chart_disk_r = Sparkline("Disk read", "MB/s", color=DISK)
        self.chart_disk_w = Sparkline("Disk write", "MB/s", color=DISK)
        self.ram_bar = HudBar("RAM", width=300)
        self.swap_bar = HudBar("SWAP", accent=SWAP, width=300)
        self.net_bar = HudBar("NET", accent=NET, width=300)
        self.disk_bar = HudBar("DISK", accent=DISK, width=300)
        self.core_strip = CoreStrip()
        self._proc_search = Gtk.SearchEntry()
        self._proc_search.set_placeholder_text("Filter processes")
        self._proc_search.connect("search-changed", self._on_proc_filter)
        self._proc_list = Gtk.ListBox()
        self._proc_list.add_css_class("boxed-list")
        self._proc_rows: list[ProcInfo] = []
        self._ram_chip = Gtk.Label(label="RAM")
        self._ram_chip.add_css_class("ns-chip")
        self._swap_chip = Gtk.Label(label="SWAP")
        self._swap_chip.add_css_class("ns-chip")
        self._net_chip = Gtk.Label(label="NET")
        self._net_chip.add_css_class("ns-chip")
        self._rpm_visual = 1800.0
        self._fan_scale_to = None
        self._fan_user = False
        self._proc_tick = 0
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
        header.pack_end(self._net_chip)
        header.pack_end(self._swap_chip)
        header.pack_end(self._ram_chip)

        tabs = Gtk.Stack()
        tabs.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        tabs.set_vexpand(True)
        tabs.add_titled(self._page_home(), "home", "HOME")
        tabs.add_titled(self._page_scenario(), "scenario", "SCENARIO")
        tabs.add_titled(self._page_monitoring(), "monitoring", "MONITORING")
        tabs.add_titled(self._page_resources(), "resources", "RESOURCES")
        tabs.add_titled(self._page_lighting(), "lighting", "LIGHTING")
        tabs.add_titled(self._page_settings(), "settings", "SETTINGS")

        switcher = Gtk.StackSwitcher(stack=tabs, hexpand=True)
        switcher.add_css_class("ns-nav")
        switcher.set_halign(Gtk.Align.CENTER)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.append(switcher)
        outer.append(self._banner)
        outer.append(tabs)
        foot = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        foot.set_margin_top(4)
        foot.set_margin_bottom(6)
        foot.append(self.ram_bar)
        foot.append(self.swap_bar)
        foot.append(self.net_bar)
        foot.append(self.disk_bar)
        outer.append(foot)
        outer.append(self._status)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(outer)
        self.set_content(toolbar)

    def _page_home(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
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

        modes = Gtk.Box(spacing=12, homogeneous=True, halign=Gtk.Align.CENTER)
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

        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        controls.set_margin_bottom(4)
        controls.append(modes)
        controls.append(fans)
        controls.append(self.custom_reveal)

        page.append(overlay)
        page.append(controls)
        return page

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
        grid.attach(self.chart_swap_p, 0, 3, 1, 1)
        grid.attach(self.chart_swap_g, 1, 3, 1, 1)
        grid.attach(self.chart_net_rx, 0, 4, 1, 1)
        grid.attach(self.chart_net_tx, 1, 4, 1, 1)
        grid.attach(self.chart_disk_r, 0, 5, 1, 1)
        grid.attach(self.chart_disk_w, 1, 5, 1, 1)
        hint = Gtk.Label(
            label="Last ~30 minutes (1 Hz). CPU, GPU, RAM, SWAP, network and disk I/O.",
            wrap=True,
            xalign=0,
        )
        hint.add_css_class("muted")
        card = self._card()
        card.append(grid)
        card.append(hint)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_child(card)
        return scrolled

    def _page_resources(self) -> Gtk.Widget:
        self._res_cpu = Gtk.Label(xalign=0, wrap=True)
        self._res_mem = Gtk.Label(xalign=0, wrap=True)
        self._res_net = Gtk.Label(xalign=0, wrap=True)
        self._res_disk = Gtk.Label(xalign=0, wrap=True)
        self._res_bat = Gtk.Label(xalign=0, wrap=True)
        for lab in (
            self._res_cpu,
            self._res_mem,
            self._res_net,
            self._res_disk,
            self._res_bat,
        ):
            lab.add_css_class("muted")

        proc_scroll = Gtk.ScrolledWindow()
        proc_scroll.set_min_content_height(280)
        proc_scroll.set_vexpand(True)
        proc_scroll.set_child(self._proc_list)

        card = self._card()
        card.append(Gtk.Label(label="Processor", xalign=0))
        card.append(self.core_strip)
        card.append(self._res_cpu)
        card.append(Gtk.Label(label="Memory / swap", xalign=0))
        card.append(self._res_mem)
        card.append(Gtk.Label(label="Network", xalign=0))
        card.append(self._res_net)
        card.append(Gtk.Label(label="Storage", xalign=0))
        card.append(self._res_disk)
        card.append(Gtk.Label(label="Battery", xalign=0))
        card.append(self._res_bat)
        card.append(Gtk.Label(label="Processes", xalign=0))
        card.append(self._proc_search)
        card.append(proc_scroll)
        hint = Gtk.Label(
            label="Same coverage as GNOME Resources: CPU cores, memory, GPU (HOME), NICs, disks, battery, and a process list with End.",
            wrap=True,
            xalign=0,
        )
        hint.add_css_class("muted")
        card.append(hint)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_child(card)
        return scrolled

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
        self.chart_swap_p.push(sensors.swap_pct)
        self.chart_swap_g.push(sensors.swap_used_gb)
        self.chart_net_rx.push(sensors.net_rx_mbps)
        self.chart_net_tx.push(sensors.net_tx_mbps)
        disk = sensors.disks[0] if sensors.disks else None
        if disk is not None:
            self.chart_disk_r.push(disk.read_mbps)
            self.chart_disk_w.push(disk.write_mbps)
            if disk.used_gb is not None and disk.total_gb is not None:
                disk_txt = f"{disk.used_gb:.0f}/{disk.total_gb:.0f} GB"
                if disk.pct is not None:
                    disk_txt += f"  {disk.pct:.0f}%"
                self.disk_bar.update(disk_txt, disk.pct)
            elif disk.read_mbps is not None:
                self.disk_bar.update(
                    f"↓{disk.read_mbps:.1f}  ↑{disk.write_mbps:.1f} MB/s",
                    None,
                )
        if sensors.ram_used_gb is not None and sensors.ram_total_gb is not None:
            ram_txt = f"{sensors.ram_used_gb:.1f}/{sensors.ram_total_gb:.0f} GB"
            if sensors.ram_pct is not None:
                ram_txt += f"  {sensors.ram_pct:.0f}%"
            self.ram_bar.update(ram_txt, sensors.ram_pct)
        if sensors.swap_total_gb is not None and sensors.swap_total_gb <= 0:
            self.swap_bar.update("off", 0.0)
        elif sensors.swap_used_gb is not None and sensors.swap_total_gb is not None:
            swap_txt = f"{sensors.swap_used_gb:.1f}/{sensors.swap_total_gb:.0f} GB"
            if sensors.swap_pct is not None:
                swap_txt += f"  {sensors.swap_pct:.0f}%"
            self.swap_bar.update(swap_txt, sensors.swap_pct)
        if sensors.net_iface:
            rx = sensors.net_rx_mbps
            tx = sensors.net_tx_mbps
            if rx is None or tx is None:
                net_txt = sensors.net_iface
            else:
                net_txt = f"↓{rx:.1f}  ↑{tx:.1f} Mb/s"
            self.net_bar.update(net_txt, sensors.net_pct)
        else:
            self.net_bar.update("—", None)
        self.core_strip.update(sensors.cpu_cores)
        self._proc_rows = sensors.processes
        self._proc_tick = getattr(self, "_proc_tick", 0) + 1
        if self._proc_tick % 2 == 0:
            self._refresh_proc_list()
        self._apply_hw(snap, sensors)
        return True

    def _apply_hw(self, snap, sensors: Sensors) -> None:
        caps = snap.caps
        # Driver warning stays in the status bar — Windows NitroSense has no orange banner.

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
        if sensors.swap_total_gb is not None and sensors.swap_total_gb <= 0:
            self._swap_chip.set_text("SWAP  off")
        elif sensors.swap_used_gb is not None and sensors.swap_total_gb is not None:
            self._swap_chip.set_text(
                f"SWAP  {sensors.swap_used_gb:.1f}/{sensors.swap_total_gb:.0f} GB"
            )
        if sensors.net_iface:
            kind = sensors.net_kind or "net"
            if sensors.net_rx_mbps is None:
                self._net_chip.set_text(f"{kind.upper()}  {sensors.net_iface}")
            else:
                ip = f"  {sensors.net_ipv4}" if sensors.net_ipv4 else ""
                self._net_chip.set_text(
                    f"{kind.upper()}  ↓{sensors.net_rx_mbps:.1f} ↑{sensors.net_tx_mbps:.1f}{ip}"
                )
        self._fill_resource_labels(sensors)
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
            body=f"In a terminal:\n\n{SETUP}\n\nNeeds sudo.",
        )
        dialog.add_response("ok", "OK")
        dialog.present()

    def _fill_resource_labels(self, sensors: Sensors) -> None:
        cores = len(sensors.cpu_cores)
        freq = f"{sensors.cpu_freq_ghz:.2f} GHz" if sensors.cpu_freq_ghz else "—"
        load = f"{sensors.cpu_load:.0f}%" if sensors.cpu_load is not None else "—"
        temp = f"{sensors.cpu_temp:.0f} °C" if sensors.cpu_temp is not None else "—"
        self._res_cpu.set_text(
            f"{sensors.cpu_name or 'CPU'}  ·  {cores} threads  ·  {freq}  ·  {load}  ·  {temp}"
        )
        ram = (
            f"RAM {sensors.ram_used_gb:.1f}/{sensors.ram_total_gb:.1f} GB ({sensors.ram_pct:.0f}%)"
            if sensors.ram_used_gb is not None and sensors.ram_total_gb
            else "RAM —"
        )
        if sensors.swap_total_gb:
            swap = (
                f"SWAP {sensors.swap_used_gb:.1f}/{sensors.swap_total_gb:.1f} GB "
                f"({sensors.swap_pct:.0f}%)"
            )
        else:
            swap = "SWAP off"
        gpu = sensors.gpu_name or "GPU —"
        if sensors.gpu_load is not None:
            gpu += f"  {sensors.gpu_load:.0f}%"
        if sensors.gpu_power_w is not None:
            gpu += f"  {sensors.gpu_power_w:.0f} W"
        self._res_mem.set_text(f"{ram}  ·  {swap}  ·  {gpu}")
        if sensors.net_iface:
            kind = (sensors.net_kind or "nic").upper()
            ip = sensors.net_ipv4 or "no IPv4"
            rx = "—" if sensors.net_rx_mbps is None else f"{sensors.net_rx_mbps:.1f}"
            tx = "—" if sensors.net_tx_mbps is None else f"{sensors.net_tx_mbps:.1f}"
            self._res_net.set_text(f"{kind} {sensors.net_iface}  {ip}  ↓{rx} ↑{tx} Mb/s")
        else:
            self._res_net.set_text("No default-route interface")
        if sensors.disks:
            bits = []
            for disk in sensors.disks:
                line = disk.name
                if disk.mount:
                    line += f" on {disk.mount}"
                if disk.used_gb is not None and disk.total_gb is not None:
                    line += f"  {disk.used_gb:.0f}/{disk.total_gb:.0f} GB"
                if disk.read_mbps is not None:
                    line += f"  R {disk.read_mbps:.1f} W {disk.write_mbps:.1f} MB/s"
                bits.append(line)
            self._res_disk.set_text("  ·  ".join(bits))
        else:
            self._res_disk.set_text("No disks")
        bat = sensors.battery_status or "Battery"
        if sensors.battery_pct is not None:
            bat += f"  {sensors.battery_pct}%"
        if sensors.battery_power_w:
            bat += f"  {sensors.battery_power_w:.1f} W"
        if sensors.on_ac:
            bat += "  ·  AC"
        self._res_bat.set_text(bat)

    def _on_proc_filter(self, _entry: Gtk.SearchEntry) -> None:
        self._refresh_proc_list()

    def _refresh_proc_list(self) -> None:
        query = (self._proc_search.get_text() or "").strip().lower()
        while True:
            row = self._proc_list.get_row_at_index(0)
            if row is None:
                break
            self._proc_list.remove(row)
        shown = 0
        for proc in self._proc_rows:
            if query and query not in proc.name.lower() and query not in str(proc.pid):
                continue
            box = Gtk.Box(spacing=12)
            box.set_margin_start(8)
            box.set_margin_end(8)
            box.set_margin_top(4)
            box.set_margin_bottom(4)
            name = Gtk.Label(label=f"{proc.name}  ({proc.pid})", xalign=0, hexpand=True)
            cpu = Gtk.Label(label=f"{proc.cpu_pct:.0f}%")
            mem = Gtk.Label(label=f"{proc.mem_mb:.0f} MB")
            cpu.set_width_chars(5)
            mem.set_width_chars(8)
            end = Gtk.Button(label="End")
            end.connect("clicked", self._on_end_process, proc.pid)
            box.append(name)
            box.append(cpu)
            box.append(mem)
            box.append(end)
            self._proc_list.append(box)
            shown += 1
            if shown >= 25:
                break

    def _on_end_process(self, _btn, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGTERM)
            self._toast(f"Sent SIGTERM to PID {pid}")
        except PermissionError:
            self._toast(f"Permission denied for PID {pid}")
        except ProcessLookupError:
            self._toast(f"PID {pid} is gone")
        except OSError as exc:
            self._toast(str(exc))


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
