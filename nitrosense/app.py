"""GTK4 GUI — NitroSense Windows look for Acer Nitro V."""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from nitrosense import __version__

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk, Pango

from nitrosense.gpu import restore_saved_tgp, set_tgp
from nitrosense.hardware import NITRO_MODES, Hardware
from nitrosense.i18n import LANG_LABELS, LANGS, lang as ui_lang, save_lang, set_lang, t
from nitrosense.lighting import (
    NIGHT_TEMP_MAX,
    NIGHT_TEMP_MIN,
    lock_leds,
    night_light,
    screen_brightness,
    set_night_light,
    set_night_temp,
    set_screen_brightness,
    toggle_lock_led,
)
from nitrosense.scenarios import Rule, ScenarioConfig, load as load_scenarios, save as save_scenarios
from nitrosense.sensors import GpuInfo, ProcInfo, Sensors, read_sensors
from nitrosense.widgets import (
    DISK,
    CoreTile,
    KeyboardDeck,
    LaptopHero,
    MetricTile,
    ModeIcon,
    NET,
    RingGauge,
    Sparkline,
    SWAP,
)

ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = Path(__file__).with_name("style.css")
SETUP = ROOT / "setup.sh"
AUTOSTART_PATH = Path.home() / ".config/autostart/nitrosense.desktop"
DESKTOP_SRC = Path.home() / ".local/share/applications/nitrosense-linux.desktop"
HOTKEY_UNIT = "nitrosense-hotkey.service"
GITHUB_URL = "https://github.com/rodriguesfas/nitrosense"
_SKIP_SCENARIO_APPS = {
    "bash",
    "sh",
    "zsh",
    "systemd",
    "dbus-daemon",
    "dbus-broker",
    "pipewire",
    "pipewire-pulse",
    "wireplumber",
    "pulseaudio",
    "Xorg",
    "Xwayland",
    "gnome-shell",
    "gjs",
    "python3",
    "python",
    "nitrosense",
}


def _tile(kind: str, title_key: str, css: str, callback, *cb_args) -> Gtk.Button:
    btn = Gtk.Button()
    btn.add_css_class(css)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, halign=Gtk.Align.CENTER)
    size = 46 if css == "mode-tile" else 36
    box.append(ModeIcon(kind, size=size))
    lab = Gtk.Label(label=t(title_key))
    lab.add_css_class("ns-tile-label")
    box.append(lab)
    btn.set_child(box)
    btn.connect("clicked", callback, *cb_args)
    btn._ns_i18n = title_key  # type: ignore[attr-defined]
    return btn


def _dmi(key: str) -> str:
    try:
        text = Path(f"/sys/class/dmi/id/{key}").read_text(encoding="utf-8").strip()
    except OSError:
        return "—"
    return text or "—"


def _autostart_on() -> bool:
    return AUTOSTART_PATH.is_file()


def _set_autostart(on: bool) -> None:
    AUTOSTART_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not on:
        AUTOSTART_PATH.unlink(missing_ok=True)
        return
    if DESKTOP_SRC.is_file():
        text = DESKTOP_SRC.read_text(encoding="utf-8")
    else:
        exe = ROOT / "bin" / "nitrosense"
        text = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=NitroSense\n"
            f"Exec={exe}\n"
            "Icon=nitrosense-linux\n"
            "Terminal=false\n"
            "Categories=System;Settings;HardwareSettings;\n"
        )
    if "X-GNOME-Autostart-enabled" not in text:
        text = text.rstrip() + "\nX-GNOME-Autostart-enabled=true\n"
    AUTOSTART_PATH.write_text(text, encoding="utf-8")


def _systemctl_user(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _hotkey_on() -> bool:
    return _systemctl_user("is-active", "--quiet", HOTKEY_UNIT).returncode == 0


def _set_hotkey(on: bool) -> None:
    if on:
        _systemctl_user("enable", "--now", HOTKEY_UNIT)
    else:
        _systemctl_user("disable", "--now", HOTKEY_UNIT)


class NitroWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app, title="NitroSense")
        self.set_default_size(1280, 920)
        self.add_css_class("nitrosense")
        self.hw = Hardware()
        self._busy = False
        self._fan_mode = "auto"
        self.cpu_gauge = RingGauge("CPU")
        self.gpu_gauge = RingGauge("GPU")
        self.hero = LaptopHero()
        self.mode_buttons: dict[str, Gtk.Button] = {}
        self.fan_buttons: dict[str, Gtk.Button] = {}
        self.scen_mode_buttons: dict[str, Gtk.Button] = {}
        self.scen_fan_buttons: dict[str, Gtk.Button] = {}
        self.cpu_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.gpu_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.scen_cpu_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.scen_gpu_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self._i18n_items: list[tuple[Gtk.Widget, str, str]] = []
        self._light_hold = 0.0
        self.limit_switch = Gtk.Switch()
        self.timeout_switch = Gtk.Switch()
        self.lcd_switch = Gtk.Switch()
        self.boot_switch = Gtk.Switch()
        self.autostart_switch = Gtk.Switch()
        self.hotkey_switch = Gtk.Switch()
        self.night_switch = Gtk.Switch()
        self.brightness_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.night_temp_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, NIGHT_TEMP_MIN, NIGHT_TEMP_MAX, 50
        )
        self._brightness_to = None
        self._night_temp_to = None
        self.kb_deck = KeyboardDeck()
        self.usb_values = (0, 10, 20, 30)
        self.usb_drop = Gtk.DropDown.new_from_strings(
            [t("usb.off"), t("usb.until", pct=10), t("usb.until", pct=20), t("usb.until", pct=30)]
        )
        self.calibrate_btn = Gtk.Button(label=t("set.calibrate_btn"))
        self.lang_drop = Gtk.DropDown.new_from_strings(list(LANG_LABELS))
        self._banner = Gtk.Label(wrap=True, xalign=0)
        self._banner.add_css_class("warn-banner")
        self._banner.set_visible(False)
        self._status = Gtk.Label(xalign=0)
        self._status.add_css_class("ns-status")
        self._status.set_visible(False)
        self._chip = Gtk.Label(label="AC")
        self._chip.add_css_class("ns-chip")
        self.chart_cpu_t = Sparkline(t("chart.cpu_temp"), "°C")
        self.chart_gpu_t = Sparkline(t("chart.gpu_temp"), "°C", color=(0.3, 0.7, 1.0))
        self.chart_cpu_l = Sparkline(t("chart.cpu_load"), "%")
        self.chart_gpu_l = Sparkline(t("chart.gpu_load"), "%", color=(0.3, 0.7, 1.0))
        self.chart_ram_p = Sparkline(t("chart.ram_load"), "%", color=(0.2, 0.85, 0.55))
        self.chart_ram_g = Sparkline(t("chart.ram_used"), "GB", color=(0.2, 0.85, 0.55))
        self.chart_swap_p = Sparkline(t("chart.swap_load"), "%", color=SWAP)
        self.chart_swap_g = Sparkline(t("chart.swap_used"), "GB", color=SWAP)
        self.chart_net_rx = Sparkline(t("chart.net_down"), "Mbps", color=NET)
        self.chart_net_tx = Sparkline(t("chart.net_up"), "Mbps", color=NET)
        self.chart_disk_r = Sparkline(t("chart.disk_read"), "MB/s", color=DISK)
        self.chart_disk_w = Sparkline(t("chart.disk_write"), "MB/s", color=DISK)
        self.home_ram = MetricTile(t("tile.ram"), "%", height=56)
        self.home_swap = MetricTile(t("tile.swap"), "%", color=SWAP, height=56)
        self.home_net = MetricTile(t("tile.net"), "Mb/s", color=NET, ceiling=None, height=56)
        self.home_disk = MetricTile(t("tile.disk"), "%", color=DISK, height=56)
        self.res_cpu_spark = Sparkline(t("tile.total"), "%")
        self.res_cpu_spark.set_content_height(88)
        self.mem_used_tile = MetricTile(t("tile.memory"), "%")
        self.mem_swap_tile = MetricTile(t("tile.swap"), "%", color=SWAP)
        self.net_rx_tile = MetricTile(t("tile.download"), "Mb/s", color=NET, ceiling=None)
        self.net_tx_tile = MetricTile(t("tile.upload"), "Mb/s", color=NET, ceiling=None)
        self.bat_charge_tile = MetricTile(t("tile.charge"), "%")
        self.bat_power_tile = MetricTile(t("tile.power"), "W", ceiling=None)
        self._disk_host = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self._disk_widgets: dict[str, dict] = {}
        self._gpu_host = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self._gpu_widgets: dict[str, dict] = {}
        self._core_tiles: list[CoreTile] = []
        self._core_host = Gtk.FlowBox()
        self._core_host.set_selection_mode(Gtk.SelectionMode.NONE)
        self._core_host.set_homogeneous(True)
        self._core_host.set_min_children_per_line(2)
        self._core_host.set_max_children_per_line(4)
        self._core_host.set_row_spacing(10)
        self._core_host.set_column_spacing(10)
        self._core_host.set_hexpand(True)
        self._core_host.set_valign(Gtk.Align.START)
        self._core_host.add_css_class("ns-core-grid")
        self._cpu_logical = Gtk.Switch()
        self._cpu_logical.set_active(True)
        self._cpu_logical.set_valign(Gtk.Align.CENTER)
        self._cpu_logical.connect("notify::active", self._on_cpu_logical)
        self._proc_widgets: dict[int, dict] = {}
        self._proc_search = Gtk.SearchEntry()
        self._proc_search.set_placeholder_text(t("proc.filter"))
        self._proc_search.connect("search-changed", self._on_proc_filter)
        self._proc_list = Gtk.ListBox()
        self._proc_list.add_css_class("boxed-list")
        self._proc_rows: list[ProcInfo] = []
        self._rpm_visual = 1800.0
        self._rpm_cpu = 1800.0
        self._rpm_gpu = 1800.0
        self._fan_scale_to = None
        self._fan_user = False
        self._custom_cpu = 50
        self._custom_gpu = 50
        self._mode_manual_until = 0.0
        self._scen_cfg: ScenarioConfig = load_scenarios()
        self._scen_active_match: str | None = None
        self._scen_app_names: list[str] = []
        self.tgp_buttons: dict[str, Gtk.Button] = {}
        self._tgp_default_w: int | None = None
        self._tgp_max_w: int | None = None
        self._tgp_restore_tried = False
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

        tabs = Gtk.Stack()
        tabs.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        tabs.set_vexpand(True)
        tabs.add_titled(self._page_home(), "home", t("tab.home"))
        tabs.add_titled(self._page_scenario(), "scenario", t("tab.scenario"))
        tabs.add_titled(self._page_monitoring(), "monitoring", t("tab.monitoring"))
        tabs.add_titled(self._page_resources(), "resources", t("tab.resources"))
        tabs.add_titled(self._page_lighting(), "lighting", t("tab.lighting"))
        tabs.add_titled(self._page_settings(), "settings", t("tab.settings"))
        self._tabs = tabs
        for name, key in (
            ("home", "tab.home"),
            ("scenario", "tab.scenario"),
            ("monitoring", "tab.monitoring"),
            ("resources", "tab.resources"),
            ("lighting", "tab.lighting"),
            ("settings", "tab.settings"),
        ):
            child = tabs.get_child_by_name(name)
            if child is not None:
                self._i18n_bind(child, key, "stack")

        switcher = Gtk.StackSwitcher(stack=tabs, hexpand=True)
        switcher.add_css_class("ns-nav")
        switcher.set_halign(Gtk.Align.CENTER)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.append(switcher)
        outer.append(self._banner)
        outer.append(tabs)
        start = os.environ.get("NITROSENSE_TAB")
        if start and tabs.get_child_by_name(start):
            tabs.set_visible_child_name(start)
        outer.append(self._status)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(outer)
        self.set_content(toolbar)
        self._i18n_bind(self.chart_cpu_t, "chart.cpu_temp", "spark")
        self._i18n_bind(self.chart_gpu_t, "chart.gpu_temp", "spark")
        self._i18n_bind(self.chart_cpu_l, "chart.cpu_load", "spark")
        self._i18n_bind(self.chart_gpu_l, "chart.gpu_load", "spark")
        self._i18n_bind(self.chart_ram_p, "chart.ram_load", "spark")
        self._i18n_bind(self.chart_ram_g, "chart.ram_used", "spark")
        self._i18n_bind(self.chart_swap_p, "chart.swap_load", "spark")
        self._i18n_bind(self.chart_swap_g, "chart.swap_used", "spark")
        self._i18n_bind(self.chart_net_rx, "chart.net_down", "spark")
        self._i18n_bind(self.chart_net_tx, "chart.net_up", "spark")
        self._i18n_bind(self.chart_disk_r, "chart.disk_read", "spark")
        self._i18n_bind(self.chart_disk_w, "chart.disk_write", "spark")
        self._i18n_bind(self.home_ram, "tile.ram", "metric")
        self._i18n_bind(self.home_swap, "tile.swap", "metric")
        self._i18n_bind(self.home_net, "tile.net", "metric")
        self._i18n_bind(self.home_disk, "tile.disk", "metric")
        self._i18n_bind(self.mem_used_tile, "tile.memory", "metric")
        self._i18n_bind(self.mem_swap_tile, "tile.swap", "metric")
        self._i18n_bind(self.net_rx_tile, "tile.download", "metric")
        self._i18n_bind(self.net_tx_tile, "tile.upload", "metric")
        self._i18n_bind(self.bat_charge_tile, "tile.charge", "metric")
        self._i18n_bind(self.bat_power_tile, "tile.power", "metric")
        self._i18n_bind(self.res_cpu_spark, "tile.total", "spark")
        self._i18n_bind(self._proc_search, "proc.filter", "placeholder")
        self._i18n_bind(self.calibrate_btn, "set.calibrate_btn")
        self._bind_mode_tiles()

    def _page_home(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        overlay = Gtk.Overlay()
        overlay.set_child(self.hero)
        overlay.set_vexpand(True)
        overlay.set_size_request(-1, 360)

        left = Gtk.Box(halign=Gtk.Align.START, valign=Gtk.Align.CENTER)
        left.set_margin_start(28)
        left.append(self.cpu_gauge)
        overlay.add_overlay(left)

        right = Gtk.Box(halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
        right.set_margin_end(28)
        right.append(self.gpu_gauge)
        overlay.add_overlay(right)

        modes = Gtk.Box(spacing=12, homogeneous=True, halign=Gtk.Align.CENTER)
        mapping = (
            ("quiet", "quiet", "mode.quiet"),
            ("balanced", "balanced", "mode.default"),
            ("performance", "performance", "mode.performance"),
        )
        for key, icon, title in mapping:
            btn = _tile(icon, title, "mode-tile", self._on_mode, key)
            self.mode_buttons[key] = btn
            modes.append(btn)

        fans = Gtk.Box(spacing=12, homogeneous=True, halign=Gtk.Align.CENTER)
        for key, icon, title in (
            ("auto", "auto", "fan.auto"),
            ("max", "max", "fan.max"),
            ("custom", "custom", "fan.custom"),
        ):
            btn = _tile(icon, title, "fan-pill", self._on_fan_mode, key)
            self.fan_buttons[key] = btn
            fans.append(btn)

        self.custom_reveal = self._fan_custom_reveal(
            self.cpu_scale, self.gpu_scale, Gtk.Align.CENTER
        )

        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        controls.set_margin_bottom(4)
        controls.append(modes)
        controls.append(fans)
        controls.append(self.custom_reveal)

        page.append(overlay)
        page.append(controls)
        grid = self._flow_grid(
            self.home_ram, self.home_swap, self.home_net, self.home_disk, cols=4
        )
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_margin_bottom(10)
        page.append(grid)
        return page

    def _card(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.add_css_class("panel")
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(24)
        box.set_margin_end(24)
        return box

    def _fan_custom_reveal(
        self, cpu_scale: Gtk.Scale, gpu_scale: Gtk.Scale, halign: Gtk.Align
    ) -> Gtk.Revealer:
        box = Gtk.Box(spacing=16)
        box.set_halign(halign)
        for scale, key in ((cpu_scale, "fan.cpu"), (gpu_scale, "fan.gpu")):
            scale.set_hexpand(True)
            scale.set_size_request(220, -1)
            scale.set_draw_value(True)
            scale.set_value(50)
            scale.connect("value-changed", self._on_fan_scale)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            lab = Gtk.Label(xalign=0)
            lab.add_css_class("muted")
            self._i18n_bind(lab, key)
            col.append(lab)
            col.append(scale)
            box.append(col)
        reveal = Gtk.Revealer(child=box)
        reveal.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        return reveal

    def _page_scenario(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.set_margin_top(16)
        page.set_margin_bottom(16)
        page.set_margin_start(24)
        page.set_margin_end(24)

        page.append(self._res_title("tab.scenario"))
        intro = Gtk.Label(wrap=True, xalign=0)
        intro.add_css_class("muted")
        self._i18n_bind(intro, "scen.intro")
        page.append(intro)

        self._scen_now = Gtk.Label(label=t("scen.now", mode="—", fan="—", extra=""), xalign=0)
        self._scen_now.add_css_class("muted")
        page.append(self._scen_now)

        modes = Gtk.Box(spacing=12, homogeneous=True)
        for key, icon, title in (
            ("quiet", "quiet", "mode.quiet"),
            ("balanced", "balanced", "mode.default"),
            ("performance", "performance", "mode.performance"),
        ):
            btn = _tile(icon, title, "mode-tile", self._on_mode, key)
            self.scen_mode_buttons[key] = btn
            modes.append(btn)
        page.append(modes)

        fans = Gtk.Box(spacing=12, homogeneous=True)
        for key, icon, title in (
            ("auto", "auto", "fan.auto"),
            ("max", "max", "fan.max"),
            ("custom", "custom", "fan.custom"),
        ):
            btn = _tile(icon, title, "fan-pill", self._on_fan_mode, key)
            self.scen_fan_buttons[key] = btn
            fans.append(btn)
        page.append(fans)
        self.scen_custom_reveal = self._fan_custom_reveal(
            self.scen_cpu_scale, self.scen_gpu_scale, Gtk.Align.START
        )
        page.append(self.scen_custom_reveal)

        rules = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        rules.add_css_class("panel")
        head = Gtk.Box(spacing=10)
        head_lab = Gtk.Label(xalign=0)
        head_lab.add_css_class("ns-page-title")
        self._i18n_bind(head_lab, "scen.rules")
        head_lab.set_hexpand(True)
        en_lab = Gtk.Label()
        en_lab.add_css_class("muted")
        self._i18n_bind(en_lab, "scen.apply")
        self._scen_enable = Gtk.Switch()
        self._scen_enable.set_valign(Gtk.Align.CENTER)
        self._scen_enable.set_active(self._scen_cfg.enabled)
        self._scen_enable.connect("notify::active", self._on_scen_enable)
        head.append(head_lab)
        head.append(en_lab)
        head.append(self._scen_enable)
        rules.append(head)

        add_row = Gtk.Box(spacing=8)
        self._scen_app_model = Gtk.StringList.new(["—"])
        self._scen_app_drop = Gtk.DropDown(model=self._scen_app_model)
        self._scen_app_drop.set_hexpand(True)
        self._scen_mode_model = Gtk.StringList.new(
            [t("mode.quiet"), t("mode.default"), t("mode.performance")]
        )
        self._scen_mode_drop = Gtk.DropDown(model=self._scen_mode_model)
        self._scen_mode_drop.set_selected(1)
        self._scen_fan_model = Gtk.StringList.new(
            [t("fan.auto"), t("fan.max"), t("fan.custom")]
        )
        self._scen_fan_drop = Gtk.DropDown(model=self._scen_fan_model)
        fan_idx = {"auto": 0, "max": 1, "custom": 2}.get(self._fan_mode, 0)
        self._scen_fan_drop.set_selected(fan_idx)
        add_btn = Gtk.Button()
        self._i18n_bind(add_btn, "scen.add")
        add_btn.add_css_class("suggested-action")
        add_btn.connect("clicked", self._on_scen_add)
        add_row.append(self._scen_app_drop)
        add_row.append(self._scen_mode_drop)
        add_row.append(self._scen_fan_drop)
        add_row.append(add_btn)
        rules.append(add_row)

        hint = Gtk.Label(wrap=True, xalign=0)
        hint.add_css_class("muted")
        self._i18n_bind(hint, "scen.hint")
        rules.append(hint)

        self._scen_empty = Gtk.Label(wrap=True, xalign=0)
        self._scen_empty.add_css_class("muted")
        self._i18n_bind(self._scen_empty, "scen.empty")
        rules.append(self._scen_empty)
        self._scen_list = Gtk.ListBox()
        self._scen_list.add_css_class("boxed-list")
        rules.append(self._scen_list)
        page.append(rules)
        self._refresh_scen_list()

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_child(page)
        return scrolled

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
        hint = Gtk.Label(wrap=True, xalign=0)
        hint.add_css_class("muted")
        self._i18n_bind(hint, "mon.hint")
        hint.add_css_class("muted")
        card = self._card()
        card.append(grid)
        card.append(hint)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_child(card)
        return scrolled

    def _flow_grid(self, *tiles: Gtk.Widget, cols: int = 2) -> Gtk.FlowBox:
        box = Gtk.FlowBox()
        box.set_selection_mode(Gtk.SelectionMode.NONE)
        box.set_homogeneous(True)
        box.set_min_children_per_line(min(cols, 4))
        box.set_max_children_per_line(cols)
        box.set_row_spacing(10)
        box.set_column_spacing(10)
        box.set_hexpand(True)
        box.set_valign(Gtk.Align.START)
        box.add_css_class("ns-core-grid")
        for tile in tiles:
            box.append(tile)
        return box

    def _res_title(self, key: str) -> Gtk.Label:
        lab = Gtk.Label(xalign=0)
        lab.add_css_class("ns-page-title")
        self._i18n_bind(lab, key)
        return lab

    def _i18n_bind(self, widget: Gtk.Widget, key: str, kind: str = "label") -> None:
        self._i18n_items.append((widget, key, kind))
        self._i18n_put(widget, key, kind)

    def _i18n_put(self, widget: Gtk.Widget, key: str, kind: str) -> None:
        text = t(key)
        if kind == "stack":
            page = self._tabs.get_page(widget)
            if page is not None:
                page.set_title(text)
            return
        if kind == "spark":
            widget.title = text  # type: ignore[attr-defined]
            widget.queue_draw()
            return
        if kind == "metric":
            widget.title = text  # type: ignore[attr-defined]
            widget.caption.set_text(text)  # type: ignore[attr-defined]
            return
        if kind == "placeholder":
            widget.set_placeholder_text(text)
            return
        widget.set_label(text)

    def _bind_mode_tiles(self) -> None:
        for group in (
            self.mode_buttons,
            self.fan_buttons,
            self.scen_mode_buttons,
            self.scen_fan_buttons,
        ):
            for btn in group.values():
                key = getattr(btn, "_ns_i18n", None)
                if not key:
                    continue
                child = btn.get_child()
                lab = child.get_last_child() if child is not None else None
                if lab is not None:
                    self._i18n_bind(lab, key)

    def _apply_i18n(self) -> None:
        for widget, key, kind in self._i18n_items:
            self._i18n_put(widget, key, kind)
        self._refresh_usb_labels()
        if hasattr(self, "_scen_mode_model"):
            self._busy = True
            mode_sel = int(self._scen_mode_drop.get_selected())
            self._scen_mode_model.splice(
                0,
                self._scen_mode_model.get_n_items(),
                [t("mode.quiet"), t("mode.default"), t("mode.performance")],
            )
            if 0 <= mode_sel < 3:
                self._scen_mode_drop.set_selected(mode_sel)
            if hasattr(self, "_scen_fan_model"):
                fan_sel = int(self._scen_fan_drop.get_selected())
                self._scen_fan_model.splice(
                    0,
                    self._scen_fan_model.get_n_items(),
                    [t("fan.auto"), t("fan.max"), t("fan.custom")],
                )
                if 0 <= fan_sel < 3:
                    self._scen_fan_drop.set_selected(fan_sel)
            self._busy = False
        self._update_scen_now(None)
        self._refresh_tgp_labels()

    def _refresh_usb_labels(self) -> None:
        model = self.usb_drop.get_model()
        if not isinstance(model, Gtk.StringList):
            return
        labels = [
            t("usb.off"),
            t("usb.until", pct=10),
            t("usb.until", pct=20),
            t("usb.until", pct=30),
        ]
        selected = int(self.usb_drop.get_selected())
        self._busy = True
        model.splice(0, model.get_n_items(), labels)
        if 0 <= selected < 4:
            self.usb_drop.set_selected(selected)
        self._busy = False

    def _on_language(self, drop: Gtk.DropDown, _pspec) -> None:
        if self._busy:
            return
        idx = int(drop.get_selected())
        if 0 <= idx < len(LANGS):
            set_lang(LANGS[idx])
            save_lang(LANGS[idx])
            self._apply_i18n()

    def _hero(self) -> tuple[Gtk.Box, Gtk.Label, Gtk.Label]:
        big = Gtk.Label(xalign=0)
        big.add_css_class("ns-hero")
        sub = Gtk.Label(xalign=0, wrap=True)
        sub.add_css_class("muted")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.append(big)
        box.append(sub)
        return box, big, sub

    def _facts(self, keys: tuple[str, ...]) -> tuple[Gtk.Grid, dict[str, Gtk.Label]]:
        grid = Gtk.Grid(column_spacing=28, row_spacing=8)
        values: dict[str, Gtk.Label] = {}
        for i, key in enumerate(keys):
            col, row = i % 2, i // 2
            cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            k = Gtk.Label(xalign=0)
            k.add_css_class("ns-fact-k")
            fact_key = {
                "Driver": "fact.driver",
                "Firmware": "fact.firmware",
                "Profile": "fact.profile",
                "Choices": "fact.choices",
                "Model": "fact.model",
                "Threads": "fact.threads",
                "Frequency": "fact.frequency",
                "Temperature": "fact.temperature",
                "Used": "fact.used",
                "Available": "fact.available",
                "Cached": "fact.cached",
                "Swap": "fact.swap",
                "Interface": "fact.interface",
                "Type": "fact.type",
                "IPv4": "fact.ipv4",
                "Link": "fact.link",
                "Status": "fact.status",
                "Power": "fact.power",
                "Energy": "fact.energy",
                "Cycles": "fact.cycles",
            }.get(key)
            if fact_key:
                self._i18n_bind(k, fact_key)
            else:
                k.set_text(key)
            v = Gtk.Label(label="—", xalign=0)
            v.add_css_class("ns-fact-v")
            cell.append(k)
            cell.append(v)
            grid.attach(cell, col, row, 1, 1)
            values[key] = v
        return grid, values

    def _res_sheet(self, *children: Gtk.Widget) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(22)
        box.set_margin_end(22)
        for child in children:
            box.append(child)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_child(box)
        return scrolled

    def _page_resources(self) -> Gtk.Widget:
        self._cpu_hero_box, self._cpu_hero, self._cpu_sub = self._hero()
        self._cpu_facts_grid, self._cpu_facts = self._facts(
            ("Model", "Threads", "Frequency", "Temperature")
        )
        opt = Gtk.Box(spacing=12)
        opt.add_css_class("ns-option-row")
        opt_lab = Gtk.Label(xalign=0)
        self._i18n_bind(opt_lab, "res.logical")
        opt_lab.set_hexpand(True)
        opt.append(opt_lab)
        opt.append(self._cpu_logical)
        cpu_page = self._res_sheet(
            self._res_title("res.processor"),
            self._cpu_hero_box,
            self._cpu_facts_grid,
            self._res_title("res.options"),
            opt,
            self._res_title("res.usage"),
            self._core_host,
            self.res_cpu_spark,
        )

        self._ram_hero_box, self._ram_hero, self._ram_sub = self._hero()
        self._ram_facts_grid, self._ram_facts = self._facts(
            ("Used", "Available", "Cached", "Swap")
        )
        ram_page = self._res_sheet(
            self._res_title("res.memory"),
            self._ram_hero_box,
            self._ram_facts_grid,
            self._res_title("res.usage"),
            self._flow_grid(self.mem_used_tile, self.mem_swap_tile, cols=2),
        )

        gpu_page = self._res_sheet(
            self._res_title("res.graphics"),
            self._gpu_host,
        )

        self._net_hero_box, self._net_hero, self._net_sub = self._hero()
        self._net_facts_grid, self._net_facts = self._facts(
            ("Interface", "Type", "IPv4", "Link")
        )
        net_page = self._res_sheet(
            self._res_title("res.network"),
            self._net_hero_box,
            self._net_facts_grid,
            self._res_title("res.usage"),
            self._flow_grid(self.net_rx_tile, self.net_tx_tile, cols=2),
        )

        storage_page = self._res_sheet(
            self._res_title("res.storage"),
            self._disk_host,
        )

        self._bat_hero_box, self._bat_hero, self._bat_sub = self._hero()
        self._bat_facts_grid, self._bat_facts = self._facts(
            ("Status", "Power", "Energy", "Cycles")
        )
        bat_page = self._res_sheet(
            self._res_title("res.battery"),
            self._bat_hero_box,
            self._bat_facts_grid,
            self._res_title("res.usage"),
            self._flow_grid(self.bat_charge_tile, self.bat_power_tile, cols=2),
        )

        proc_head = Gtk.Box(spacing=12)
        proc_head.add_css_class("ns-proc-head")
        proc_head.set_margin_start(8)
        proc_head.set_margin_end(8)
        name_h = Gtk.Label(xalign=0, hexpand=True)
        pid_h = Gtk.Label()
        cpu_h = Gtk.Label()
        mem_h = Gtk.Label()
        act_h = Gtk.Label(label="")
        self._i18n_bind(name_h, "proc.name")
        self._i18n_bind(pid_h, "proc.pid")
        self._i18n_bind(cpu_h, "proc.cpu")
        self._i18n_bind(mem_h, "proc.memory")
        pid_h.set_width_chars(7)
        cpu_h.set_width_chars(6)
        mem_h.set_width_chars(9)
        act_h.set_width_chars(5)
        for lab in (name_h, pid_h, cpu_h, mem_h, act_h):
            lab.add_css_class("ns-proc-head")
        proc_head.append(name_h)
        proc_head.append(pid_h)
        proc_head.append(cpu_h)
        proc_head.append(mem_h)
        proc_head.append(act_h)
        proc_scroll = Gtk.ScrolledWindow()
        proc_scroll.set_vexpand(True)
        proc_scroll.set_min_content_height(360)
        proc_scroll.set_child(self._proc_list)
        proc_page = self._res_sheet(
            self._res_title("res.processes"),
            self._proc_search,
            proc_head,
            proc_scroll,
        )

        self._res_stack = Gtk.Stack()
        self._res_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._res_stack.add_named(cpu_page, "cpu")
        self._res_stack.add_named(ram_page, "memory")
        self._res_stack.add_named(gpu_page, "gpu")
        self._res_stack.add_named(net_page, "network")
        self._res_stack.add_named(storage_page, "storage")
        self._res_stack.add_named(bat_page, "battery")
        self._res_stack.add_named(proc_page, "processes")

        nav = Gtk.ListBox()
        nav.add_css_class("ns-side")
        nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
        nav.set_vexpand(True)
        nav.set_size_request(176, -1)
        self._res_nav_ids = (
            "cpu",
            "memory",
            "gpu",
            "network",
            "storage",
            "battery",
            "processes",
        )
        for title_key in (
            "res.processor",
            "res.memory",
            "res.graphics",
            "res.network",
            "res.storage",
            "res.battery",
            "res.processes",
        ):
            lab = Gtk.Label(xalign=0)
            self._i18n_bind(lab, title_key)
            nav.append(lab)
        nav.connect("row-selected", self._on_res_nav)
        start_res = os.environ.get("NITROSENSE_RES", "cpu")
        idx = self._res_nav_ids.index(start_res) if start_res in self._res_nav_ids else 0
        nav.select_row(nav.get_row_at_index(idx))

        split = Gtk.Box(spacing=0)
        split.add_css_class("ns-res-split")
        split.set_vexpand(True)
        split.append(nav)
        split.append(self._res_stack)
        self._res_stack.set_hexpand(True)
        return split

    def _on_res_nav(self, _list: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            return
        idx = row.get_index()
        if 0 <= idx < len(self._res_nav_ids):
            self._res_stack.set_visible_child_name(self._res_nav_ids[idx])

    def _page_lighting(self) -> Gtk.Widget:
        self.timeout_switch.connect("state-set", self._on_flag, "backlight_timeout")
        self.lcd_switch.connect("state-set", self._on_flag, "lcd_override")
        self.night_switch.connect("state-set", self._on_night_light)
        self.brightness_scale.set_draw_value(True)
        self.brightness_scale.set_hexpand(True)
        self.brightness_scale.set_value(screen_brightness() or 100)
        self.brightness_scale.connect("value-changed", self._on_brightness)
        self.night_temp_scale.set_draw_value(True)
        self.night_temp_scale.set_hexpand(True)
        enabled, temp = night_light()
        self.night_temp_scale.set_value(temp or 2700)
        self.night_temp_scale.connect("value-changed", self._on_night_temp)
        if enabled is not None:
            self.night_switch.set_active(enabled)

        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("released", self._on_kb_deck_click)
        self.kb_deck.add_controller(click)
        self.kb_deck.set_cursor_from_name("pointer")

        kb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        kb.add_css_class("panel")
        leds = Gtk.Box(spacing=8)
        self._led_chips = {}
        for key, i18n_key in (("caps", "light.caps"), ("num", "light.num"), ("scroll", "light.scroll")):
            chip = Gtk.Button()
            chip.add_css_class("ns-led")
            chip.set_cursor_from_name("pointer")
            chip.connect("clicked", self._on_lock_led, key)
            self._i18n_bind(chip, i18n_key)
            self._led_chips[key] = chip
            leds.append(chip)
        kb.append(
            self._option_row("light.timeout", self.timeout_switch, "light.timeout_hint")
        )
        kb.append(leds)

        display = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        display.add_css_class("panel")
        self._brightness_lab = Gtk.Label(xalign=0)
        self._i18n_bind(self._brightness_lab, "light.brightness")
        display.append(self._brightness_lab)
        display.append(self.brightness_scale)
        self._lcd_row = self._option_row("light.lcd", self.lcd_switch)
        display.append(self._lcd_row)

        night = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        night.add_css_class("panel")
        night.append(self._option_row("light.night", self.night_switch, "light.night_hint"))
        night.append(self.night_temp_scale)

        self._kb_rgb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._kb_rgb_box.add_css_class("panel")
        modes = Gtk.Box(spacing=8)
        for idx, name in enumerate(
            ("Static", "Breathing", "Neon", "Wave", "Shifting", "Zoom", "Meteor", "Twinkling")
        ):
            btn = Gtk.Button(label=name)
            btn.connect("clicked", self._on_rgb_mode, idx)
            modes.append(btn)
        rgb_title = Gtk.Label(xalign=0)
        rgb_title.add_css_class("ns-page-title")
        self._i18n_bind(rgb_title, "light.rgb")
        self._kb_rgb_box.append(rgb_title)
        self._kb_rgb_box.append(modes)

        return self._res_sheet(
            self._res_title("light.page"),
            self.kb_deck,
            self._res_title("light.keyboard"),
            kb,
            self._res_title("light.display"),
            display,
            self._res_title("light.night_section"),
            night,
            self._kb_rgb_box,
        )

    def _option_row(self, label_key: str, widget: Gtk.Widget, hint_key: str | None = None) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.add_css_class("ns-option-row")
        line = Gtk.Box(spacing=12)
        lab = Gtk.Label(xalign=0, hexpand=True)
        self._i18n_bind(lab, label_key)
        line.append(lab)
        line.append(widget)
        box.append(line)
        if hint_key:
            note = Gtk.Label(wrap=True, xalign=0)
            note.add_css_class("muted")
            self._i18n_bind(note, hint_key)
            box.append(note)
        return box

    def _page_settings(self) -> Gtk.Widget:
        self.limit_switch.connect("state-set", self._on_flag, "battery_limiter")
        self.boot_switch.connect("state-set", self._on_flag, "boot_animation_sound")
        self.usb_drop.connect("notify::selected", self._on_usb)
        self.calibrate_btn.connect("clicked", self._on_calibrate)
        self.autostart_switch.set_active(_autostart_on())
        self.autostart_switch.connect("state-set", self._on_autostart)
        hotkey_unit = Path.home() / ".config/systemd/user" / HOTKEY_UNIT
        self.hotkey_switch.set_sensitive(hotkey_unit.is_file())
        self.hotkey_switch.set_active(_hotkey_on())
        self.hotkey_switch.connect("state-set", self._on_hotkey)

        self._drv_facts_grid, self._drv_facts = self._facts(
            ("Driver", "Firmware", "Profile", "Choices")
        )
        setup_btn = Gtk.Button()
        self._i18n_bind(setup_btn, "set.install")
        setup_btn.connect("clicked", self._on_setup_help)
        setup_btn.set_halign(Gtk.Align.START)
        driver = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        driver.add_css_class("panel")
        driver.append(self._drv_facts_grid)
        driver.append(setup_btn)

        battery = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        battery.append(self._option_row("set.limit", self.limit_switch, "set.limit_hint"))
        battery.append(self._option_row("set.usb", self.usb_drop, "set.usb_hint"))
        battery.append(
            self._option_row("set.calibrate", self.calibrate_btn, "set.calibrate_hint")
        )

        self._boot_row = self._option_row("set.boot", self.boot_switch, "set.boot_hint")
        self._boot_row.set_visible(False)

        startup = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        startup.append(
            self._option_row("set.autostart", self.autostart_switch, "set.autostart_hint")
        )
        startup.append(self._option_row("set.hotkey", self.hotkey_switch, "set.hotkey_hint"))
        self.lang_drop.set_selected(LANGS.index(ui_lang()) if ui_lang() in LANGS else 0)
        self.lang_drop.connect("notify::selected", self._on_language)
        startup.append(self._option_row("set.language", self.lang_drop, "set.language_hint"))

        tgp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        tgp.add_css_class("panel")
        self._tgp_now = Gtk.Label(xalign=0)
        self._tgp_now.add_css_class("muted")
        tgp.append(self._tgp_now)
        tgp_hint = Gtk.Label(wrap=True, xalign=0)
        tgp_hint.add_css_class("muted")
        self._i18n_bind(tgp_hint, "set.tgp_hint")
        tgp.append(tgp_hint)
        tgp_row = Gtk.Box(spacing=12, homogeneous=True)
        for key, icon in (("default", "balanced"), ("boost", "performance")):
            btn = Gtk.Button()
            btn.add_css_class("mode-tile")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, halign=Gtk.Align.CENTER)
            box.append(ModeIcon(icon, size=46))
            lab = Gtk.Label()
            lab.add_css_class("ns-tile-label")
            box.append(lab)
            btn.set_child(box)
            btn.connect("clicked", self._on_tgp, key)
            btn._ns_lab = lab  # type: ignore[attr-defined]
            self.tgp_buttons[key] = btn
            tgp_row.append(btn)
        tgp.append(tgp_row)
        self._tgp_missing = Gtk.Label(wrap=True, xalign=0)
        self._tgp_missing.add_css_class("muted")
        self._i18n_bind(self._tgp_missing, "set.tgp_missing")
        tgp.append(self._tgp_missing)
        self._tgp_panel = tgp
        self._refresh_tgp_labels()

        about_lab = Gtk.Label(
            label=(
                f"NitroSense {__version__}  ·  {_dmi('product_name')}  ·  "
                f"{_dmi('board_name')}  ·  BIOS {_dmi('product_version')}"
            ),
            wrap=True,
            xalign=0,
        )
        about_lab.add_css_class("muted")
        github = Gtk.LinkButton(uri=GITHUB_URL, label="github.com/rodriguesfas/nitrosense")
        github.set_halign(Gtk.Align.START)
        driver.append(about_lab)
        driver.append(github)

        return self._res_sheet(
            self._res_title("set.driver"),
            driver,
            self._res_title("set.tgp"),
            tgp,
            self._res_title("set.battery"),
            battery,
            self._res_title("set.startup"),
            startup,
            self._boot_row,
        )

    def _spin(self) -> bool:
        self.hero.tick(self._rpm_cpu, self._rpm_gpu)
        self.kb_deck.tick()
        return True

    def _tick(self) -> bool:
        self.hw.refresh_paths()
        snap = self.hw.snapshot()
        sensors = read_sensors()
        if snap.fan_cpu_rpm is not None:
            self._rpm_cpu = float(snap.fan_cpu_rpm)
        if snap.fan_gpu_rpm is not None:
            self._rpm_gpu = float(snap.fan_gpu_rpm)
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
        self._sync_home_tiles(sensors)
        self._sync_core_grid(sensors)
        self.res_cpu_spark.push(sensors.cpu_load)
        self._sync_gpus(sensors.gpus, snap)
        rx = sensors.net_rx_mbps
        tx = sensors.net_tx_mbps
        self._proc_rows = sensors.processes
        self._proc_tick = getattr(self, "_proc_tick", 0) + 1
        if self._proc_tick % 2 == 0:
            self._refresh_proc_list()
            if hasattr(self, "_scen_list"):
                self._refresh_scen_list()
        self._refresh_scen_apps(sensors)
        if self._apply_scenario(sensors, snap):
            snap = self.hw.snapshot()
        self._apply_hw(snap, sensors)
        return True

    def _apply_hw(self, snap, sensors: Sensors) -> None:
        caps = snap.caps
        # Driver warning stays in the status bar — Windows NitroSense has no orange banner.

        current_mode = None
        for key, _label, fw in NITRO_MODES:
            if snap.profile == fw:
                current_mode = key
                break
        self._set_active_map(self.mode_buttons, current_mode)
        self._set_active_map(self.scen_mode_buttons, current_mode)
        if current_mode:
            self.hero.set_mode(current_mode)

        if not self._fan_user:
            if snap.fan_auto:
                self._fan_mode = "auto"
            elif (snap.fan_cpu_pct or 0) >= 99 and (snap.fan_gpu_pct or 0) >= 99:
                self._fan_mode = "max"
            elif not snap.fan_auto and (snap.fan_cpu_pct or snap.fan_gpu_pct):
                self._fan_mode = "custom"
        self._set_active_map(self.fan_buttons, self._fan_mode)
        self._set_active_map(self.scen_fan_buttons, self._fan_mode)
        custom = self._fan_mode == "custom"
        self.custom_reveal.set_reveal_child(custom)
        if hasattr(self, "scen_custom_reveal"):
            self.scen_custom_reveal.set_reveal_child(custom)
        self._update_scen_now(current_mode)

        self._busy = True
        # Custom sliders are the setpoint. Do not copy firmware/PWM back
        # onto them — that snaps the thumb to 100 while the user is dragging.
        self._set_switch(self.limit_switch, caps.battery_limiter, snap.battery_limiter)
        self._set_switch(self.timeout_switch, caps.backlight_timeout, snap.backlight_timeout)
        self._set_switch(self.lcd_switch, caps.lcd_override, snap.lcd_override)
        self._set_switch(self.boot_switch, caps.boot_animation, snap.boot_animation)
        self.usb_drop.set_sensitive(caps.usb_charging)
        if snap.usb_charging in self.usb_values:
            self.usb_drop.set_selected(self.usb_values.index(snap.usb_charging))
        self.calibrate_btn.set_sensitive(caps.battery_calibration)
        self._kb_rgb_box.set_visible(caps.rgb_keyboard)
        if hasattr(self, "_lcd_row"):
            self._lcd_row.set_visible(caps.lcd_override)
        if hasattr(self, "_boot_row"):
            self._boot_row.set_visible(caps.boot_animation)
        self.kb_deck.set_timeout(bool(snap.backlight_timeout))
        self._busy = False
        self._sync_session_lighting()

        self._fill_resource_labels(sensors, snap)
        if sensors.on_ac:
            self._chip.set_text("AC  ·  " + (f"{sensors.battery_pct}%" if sensors.battery_pct is not None else "—"))
        else:
            self._chip.set_text(
                "BATTERY  ·  " + (f"{sensors.battery_pct}%" if sensors.battery_pct is not None else "—")
            )
        drv = {"linuwu": "Linuwu Sense", "acer_wmi": "acer_wmi", "none": "no fan driver"}[caps.driver]
        fw = "—"
        if self.hw.sense is not None:
            try:
                fw = (self.hw.sense / "version").read_text(encoding="utf-8").strip() or "—"
            except OSError:
                fw = "—"
        if hasattr(self, "_drv_facts"):
            self._drv_facts["Driver"].set_text(drv)
            self._drv_facts["Firmware"].set_text(fw)
            self._drv_facts["Profile"].set_text(snap.profile or "—")
            self._drv_facts["Choices"].set_text(" ".join(snap.profile_choices) or "—")
        self._sync_tgp(sensors)
        if not self._tgp_restore_tried:
            self._tgp_restore_tried = True
            GLib.idle_add(self._restore_saved_tgp)

    def _set_switch(self, widget: Gtk.Switch, enabled: bool, value: bool | None) -> None:
        widget.set_sensitive(enabled)
        if value is not None:
            widget.set_active(value)

    def _toast(self, message: str) -> None:
        self._status.set_text(message)
        self._status.set_visible(True)

    def _nvidia_gpu(self, sensors: Sensors | None) -> GpuInfo | None:
        if sensors is None:
            return None
        return next((g for g in sensors.gpus if g.vendor == "NVIDIA"), None)

    def _refresh_tgp_labels(self) -> None:
        default = self._tgp_default_w or 60
        boost = self._tgp_max_w or 75
        mapping = (("default", "set.tgp_default", default), ("boost", "set.tgp_boost", boost))
        for key, i18n, watts in mapping:
            btn = self.tgp_buttons.get(key)
            if btn is None:
                continue
            lab = getattr(btn, "_ns_lab", None)
            if lab is not None:
                lab.set_text(t(i18n, watts=watts))

    def _sync_tgp(self, sensors: Sensors) -> None:
        if not self.tgp_buttons:
            return
        gpu = self._nvidia_gpu(sensors)
        has = gpu is not None and (
            gpu.power_default_w is not None or gpu.power_max_w is not None
        )
        if hasattr(self, "_tgp_missing"):
            self._tgp_missing.set_visible(not has)
        for btn in self.tgp_buttons.values():
            btn.set_sensitive(has)
            btn.set_visible(has)
        if not has:
            if hasattr(self, "_tgp_now"):
                self._tgp_now.set_text(t("set.tgp_now", watts="—"))
            self._set_active_map(self.tgp_buttons, None)
            return
        default = int(round(gpu.power_default_w or 60))
        boost = int(round(gpu.power_max_w or 75))
        current = (
            int(round(gpu.power_limit_w)) if gpu.power_limit_w is not None else default
        )
        self._tgp_default_w = default
        self._tgp_max_w = boost
        self._refresh_tgp_labels()
        self._tgp_now.set_text(t("set.tgp_now", watts=current))
        active = "boost" if current >= boost - 1 else "default"
        self._set_active_map(self.tgp_buttons, active)

    def _on_tgp(self, _btn, key: str) -> None:
        watts = self._tgp_max_w if key == "boost" else self._tgp_default_w
        if watts is None:
            return
        self._run(set_tgp, int(watts))

    def _restore_saved_tgp(self) -> bool:
        try:
            restore_saved_tgp()
        except Exception:  # noqa: BLE001
            pass
        return False

    def _run(self, fn, *args) -> None:
        try:
            fn(*args)
        except Exception as exc:  # noqa: BLE001
            self._toast(str(exc))

    def _set_active_map(self, buttons: dict[str, Gtk.Button], key: str | None) -> None:
        for name, btn in buttons.items():
            on = name == key
            if on:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")
            child = btn.get_child()
            icon = child.get_first_child() if child is not None else None
            if isinstance(icon, ModeIcon):
                icon.set_active(on)
            lab = icon.get_next_sibling() if icon is not None else None
            if isinstance(lab, Gtk.Label):
                if on:
                    lab.add_css_class("ns-tile-label-on")
                else:
                    lab.remove_css_class("ns-tile-label-on")

    def _update_scen_now(self, current_mode: str | None) -> None:
        if not hasattr(self, "_scen_now"):
            return
        labels = {
            "quiet": t("mode.quiet"),
            "balanced": t("mode.default"),
            "performance": t("mode.performance"),
        }
        mode_txt = labels.get(current_mode or "", current_mode or "—")
        fan_key = {"auto": "fan.auto", "max": "fan.max", "custom": "fan.custom"}.get(
            self._fan_mode or ""
        )
        fan_txt = t(fan_key) if fan_key else (self._fan_mode or "—")
        extra = t("scen.rule_extra", name=self._scen_active_match) if self._scen_active_match else ""
        self._scen_now.set_text(t("scen.now", mode=mode_txt, fan=fan_txt, extra=extra))

    def _refresh_scen_apps(self, sensors: Sensors) -> None:
        if not hasattr(self, "_scen_app_model"):
            return
        names = sorted(
            {
                p.name
                for p in sensors.processes
                if p.name
                and p.name not in _SKIP_SCENARIO_APPS
                and not p.name.startswith("[")
            },
            key=str.lower,
        )
        if names == self._scen_app_names:
            return
        prev = None
        sel = self._scen_app_drop.get_selected()
        if 0 <= sel < self._scen_app_model.get_n_items():
            prev = self._scen_app_model.get_string(sel)
        additions = names or ["—"]
        self._scen_app_model.splice(0, self._scen_app_model.get_n_items(), additions)
        self._scen_app_names = names
        if prev in additions:
            self._scen_app_drop.set_selected(additions.index(prev))

    def _refresh_scen_list(self) -> None:
        if not hasattr(self, "_scen_list"):
            return
        labels = {
            "quiet": t("mode.quiet"),
            "balanced": t("mode.default"),
            "performance": t("mode.performance"),
        }
        fans = {
            "auto": t("fan.auto"),
            "max": t("fan.max"),
            "custom": t("fan.custom"),
        }
        running = {p.name.lower() for p in getattr(self, "_proc_rows", [])}
        sig = (
            tuple((r.match, r.mode, r.fans, r.cpu, r.gpu) for r in self._scen_cfg.rules),
            frozenset(r.match.lower() for r in self._scen_cfg.rules if r.match.lower() in running),
        )
        if sig == getattr(self, "_scen_list_sig", None):
            return
        self._scen_list_sig = sig
        while True:
            row = self._scen_list.get_row_at_index(0)
            if row is None:
                break
            self._scen_list.remove(row)
        self._scen_empty.set_visible(not self._scen_cfg.rules)
        for rule in self._scen_cfg.rules:
            box = Gtk.Box(spacing=12)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(12)
            box.set_margin_end(12)
            name = Gtk.Label(label=rule.match, xalign=0)
            name.set_hexpand(True)
            name.add_css_class("ns-rule-app")
            mode_txt = labels.get(rule.mode, rule.mode)
            fan_txt = fans.get(rule.fans, rule.fans)
            if rule.fans == "custom":
                detail = t(
                    "scen.rule_custom",
                    mode=mode_txt,
                    fans=fan_txt,
                    cpu=rule.cpu,
                    gpu=rule.gpu,
                )
            elif rule.fans in fans:
                detail = t("scen.rule", mode=mode_txt, fans=fan_txt)
            else:
                detail = mode_txt
            mode = Gtk.Label(label=detail)
            mode.add_css_class("muted")
            live = rule.match.lower() in running
            status = Gtk.Label(label=t("scen.running") if live else "")
            if live:
                status.add_css_class("ns-live")
            rm = Gtk.Button(label=t("scen.remove"))
            rm.connect("clicked", self._on_scen_remove, rule.match)
            box.append(name)
            box.append(mode)
            box.append(status)
            box.append(rm)
            row = Gtk.ListBoxRow()
            row.set_child(box)
            self._scen_list.append(row)

    def _fans_match_rule(self, rule: Rule, snap) -> bool:
        fans = rule.fans if rule.fans in ("auto", "max", "custom") else ""
        if not fans:
            return True
        if fans == "auto":
            return bool(snap.fan_auto)
        if fans == "max":
            return (
                not snap.fan_auto
                and (snap.fan_cpu_pct or 0) >= 99
                and (snap.fan_gpu_pct or 0) >= 99
            )
        cpu = max(1, min(100, int(rule.cpu)))
        gpu = max(1, min(100, int(rule.gpu)))
        return (
            not snap.fan_auto
            and snap.fan_cpu_pct == cpu
            and snap.fan_gpu_pct == gpu
        )

    def _apply_fan_rule(self, rule: Rule) -> None:
        fans = rule.fans if rule.fans in ("auto", "max", "custom") else "auto"
        self._fan_mode = fans
        if fans == "auto":
            self._run(self.hw.set_fans, 0, 0, True)
        elif fans == "max":
            self._run(self.hw.set_fans, 100, 100, False)
        else:
            cpu = max(1, min(100, int(rule.cpu)))
            gpu = max(1, min(100, int(rule.gpu)))
            self._custom_cpu = cpu
            self._custom_gpu = gpu
            self._set_fan_scales(cpu, gpu)
            self._run(self.hw.set_fans, cpu, gpu, False)
        self._set_active_map(self.fan_buttons, fans)
        self._set_active_map(self.scen_fan_buttons, fans)
        custom = fans == "custom"
        self.custom_reveal.set_reveal_child(custom)
        if hasattr(self, "scen_custom_reveal"):
            self.scen_custom_reveal.set_reveal_child(custom)

    def _apply_scenario(self, sensors: Sensors, snap) -> bool:
        if not self._scen_cfg.enabled or not self._scen_cfg.rules:
            self._scen_active_match = None
            return False
        if time.monotonic() < self._mode_manual_until:
            return False
        names = {p.name.lower() for p in sensors.processes}
        for rule in self._scen_cfg.rules:
            needle = rule.match.lower()
            if needle not in names:
                continue
            self._scen_active_match = rule.match
            fw = next(item[2] for item in NITRO_MODES if item[0] == rule.mode)
            changed = False
            if snap.profile != fw:
                self._run(self.hw.set_profile, fw)
                self.hero.set_mode(rule.mode)
                changed = True
            if not self._fans_match_rule(rule, snap):
                self._apply_fan_rule(rule)
                changed = True
            return changed
        self._scen_active_match = None
        return False

    def _on_scen_enable(self, switch: Gtk.Switch, _pspec) -> None:
        if self._busy:
            return
        self._scen_cfg.enabled = switch.get_active()
        if not self._scen_cfg.enabled:
            self._scen_active_match = None
        save_scenarios(self._scen_cfg)

    def _on_scen_add(self, _btn) -> None:
        idx = self._scen_app_drop.get_selected()
        if idx < 0 or idx >= self._scen_app_model.get_n_items():
            return
        name = self._scen_app_model.get_string(idx)
        if not name or name == "—":
            return
        modes = ("quiet", "balanced", "performance")
        fans = ("auto", "max", "custom")
        sel = self._scen_mode_drop.get_selected()
        mode = modes[sel] if 0 <= sel < len(modes) else "balanced"
        fan_sel = self._scen_fan_drop.get_selected() if hasattr(self, "_scen_fan_drop") else 0
        fan = fans[fan_sel] if 0 <= fan_sel < len(fans) else "auto"
        cpu = max(1, min(100, int(self._custom_cpu)))
        gpu = max(1, min(100, int(self._custom_gpu)))
        self._scen_cfg.rules = [r for r in self._scen_cfg.rules if r.match.lower() != name.lower()]
        self._scen_cfg.rules.append(Rule(match=name, mode=mode, fans=fan, cpu=cpu, gpu=gpu))
        save_scenarios(self._scen_cfg)
        self._refresh_scen_list()

    def _on_scen_remove(self, _btn, match: str) -> None:
        self._scen_cfg.rules = [r for r in self._scen_cfg.rules if r.match != match]
        if self._scen_active_match == match:
            self._scen_active_match = None
        save_scenarios(self._scen_cfg)
        self._refresh_scen_list()

    def _on_mode(self, _btn, key: str) -> None:
        self._mode_manual_until = time.monotonic() + 45
        fw = next(item[2] for item in NITRO_MODES if item[0] == key)
        self.hero.set_mode(key)
        self._set_active_map(self.mode_buttons, key)
        self._set_active_map(self.scen_mode_buttons, key)
        self._run(self.hw.set_profile, fw)

    def _set_fan_scales(self, cpu: int, gpu: int) -> None:
        self._busy = True
        self.cpu_scale.set_value(cpu)
        self.scen_cpu_scale.set_value(cpu)
        self.gpu_scale.set_value(gpu)
        self.scen_gpu_scale.set_value(gpu)
        self._busy = False

    def _on_fan_mode(self, _btn, key: str) -> None:
        self._mode_manual_until = time.monotonic() + 45
        self._fan_user = True
        self._fan_mode = key
        self._set_active_map(self.fan_buttons, key)
        self._set_active_map(self.scen_fan_buttons, key)
        custom = key == "custom"
        self.custom_reveal.set_reveal_child(custom)
        if hasattr(self, "scen_custom_reveal"):
            self.scen_custom_reveal.set_reveal_child(custom)
        if key == "auto":
            self._run(self.hw.set_fans, 0, 0, True)
        elif key == "max":
            self._run(self.hw.set_fans, 100, 100, False)
        else:
            cpu = max(1, min(100, int(self._custom_cpu)))
            gpu = max(1, min(100, int(self._custom_gpu)))
            self._set_fan_scales(cpu, gpu)
            self._run(self.hw.set_fans, cpu, gpu, False)

    def _on_fan_scale(self, scale: Gtk.Scale) -> None:
        if self._busy or self._fan_mode != "custom":
            return
        self._mode_manual_until = time.monotonic() + 45
        peer = None
        if scale in (self.cpu_scale, self.scen_cpu_scale):
            peer = self.scen_cpu_scale if scale is self.cpu_scale else self.cpu_scale
        elif scale in (self.gpu_scale, self.scen_gpu_scale):
            peer = self.scen_gpu_scale if scale is self.gpu_scale else self.gpu_scale
        if peer is not None and abs(peer.get_value() - scale.get_value()) >= 0.5:
            self._busy = True
            peer.set_value(scale.get_value())
            self._busy = False
        cpu = max(1, int(self.cpu_scale.get_value()))
        gpu = max(1, int(self.gpu_scale.get_value()))
        self._custom_cpu = cpu
        self._custom_gpu = gpu
        if self._fan_scale_to is not None:
            GLib.source_remove(self._fan_scale_to)
        self._fan_scale_to = GLib.timeout_add(180, self._flush_fan_scale)

    def _flush_fan_scale(self) -> bool:
        self._fan_scale_to = None
        if self._fan_mode != "custom" or self._busy:
            return False
        self._run(
            self.hw.set_fans,
            max(1, min(100, int(self._custom_cpu))),
            max(1, min(100, int(self._custom_gpu))),
            False,
        )
        return False

    def _sync_session_lighting(self) -> None:
        hold = time.monotonic() < getattr(self, "_light_hold", 0)
        if not hold and getattr(self, "_brightness_to", None) is None:
            pct = screen_brightness()
            if pct is not None:
                if abs(self.brightness_scale.get_value() - pct) >= 2:
                    self._busy = True
                    self.brightness_scale.set_value(pct)
                    self._busy = False
                self._brightness_lab.set_text(t("light.brightness_pct", pct=pct))
        if not hold:
            enabled, temp = night_light()
            if enabled is not None:
                self._busy = True
                self.night_switch.set_active(enabled)
                self._busy = False
                self.night_temp_scale.set_sensitive(enabled)
            if (
                temp is not None
                and getattr(self, "_night_temp_to", None) is None
                and abs(self.night_temp_scale.get_value() - temp) >= 40
            ):
                self._busy = True
                self.night_temp_scale.set_value(temp)
                self._busy = False
        leds = lock_leds()
        for key, chip in getattr(self, "_led_chips", {}).items():
            if leds.get(key):
                chip.add_css_class("on")
            else:
                chip.remove_css_class("on")

    def _on_brightness(self, scale: Gtk.Scale) -> None:
        if self._busy:
            return
        self._light_hold = time.monotonic() + 2.5
        self._brightness_lab.set_text(t("light.brightness_pct", pct=int(scale.get_value())))
        if self._brightness_to is not None:
            GLib.source_remove(self._brightness_to)
        self._brightness_to = GLib.timeout_add(80, self._flush_brightness)

    def _flush_brightness(self) -> bool:
        self._brightness_to = None
        self._run(set_screen_brightness, int(self.brightness_scale.get_value()))
        return False

    def _on_night_light(self, _switch: Gtk.Switch, state: bool) -> bool:
        if self._busy:
            return False
        self._light_hold = time.monotonic() + 2.5
        self._run(set_night_light, state)
        self.night_temp_scale.set_sensitive(state)
        return False

    def _on_night_temp(self, _scale: Gtk.Scale) -> None:
        if self._busy:
            return
        self._light_hold = time.monotonic() + 2.5
        if self._night_temp_to is not None:
            GLib.source_remove(self._night_temp_to)
        self._night_temp_to = GLib.timeout_add(180, self._flush_night_temp)

    def _on_kb_deck_click(self, *_args) -> None:
        if not self.timeout_switch.get_sensitive():
            return
        self.timeout_switch.set_active(not self.timeout_switch.get_active())

    def _on_lock_led(self, _btn, key: str) -> None:
        self._run(toggle_lock_led, key)
        GLib.timeout_add(150, self._sync_leds_soon)

    def _sync_leds_soon(self) -> bool:
        leds = lock_leds()
        for name, chip in getattr(self, "_led_chips", {}).items():
            if leds.get(name):
                chip.add_css_class("on")
            else:
                chip.remove_css_class("on")
        return False

    def _flush_night_temp(self) -> bool:
        self._night_temp_to = None
        self._run(set_night_temp, int(self.night_temp_scale.get_value()))
        return False

    def _on_flag(self, switch: Gtk.Switch, state: bool, name: str) -> bool:
        if self._busy:
            return False
        self._run(self.hw.set_flag, name, state)
        if name == "backlight_timeout":
            self.kb_deck.set_timeout(state)
            self._light_hold = time.monotonic() + 2.5
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
            heading=t("set.calibrate_title"),
            body=t("set.calibrate_body"),
        )
        dialog.add_response("cancel", t("cancel"))
        dialog.add_response("ok", t("start"))
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_calibrate_resp)
        dialog.present()

    def _on_calibrate_resp(self, _dialog, response: str) -> None:
        if response == "ok":
            self._run(self.hw.set_flag, "battery_calibration", True)

    def _on_rgb_mode(self, _btn, mode: int) -> None:
        self._run(self.hw.set_rgb_mode, mode, 5, 100, 1, 255, 106, 0)

    def _on_setup_help(self, _btn) -> None:
        snap = self.hw.snapshot()
        if snap.caps.driver == "linuwu":
            fw = "—"
            if self.hw.sense is not None:
                try:
                    fw = (self.hw.sense / "version").read_text(encoding="utf-8").strip() or "—"
                except OSError:
                    fw = "—"
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading=t("set.install_done_title"),
                body=t("set.install_done_body", fw=fw),
            )
            dialog.add_response("ok", t("ok"))
            dialog.add_response("reinstall", t("set.install_reinstall"))
            dialog.set_default_response("ok")
            dialog.connect("response", self._on_setup_resp)
            dialog.present()
            return
        self._begin_driver_setup()

    def _on_setup_resp(self, _dialog, response: str) -> None:
        if response == "reinstall":
            self._begin_driver_setup()

    def _setup_script(self) -> Path:
        for path in (
            SETUP,
            Path("/usr/share/nitrosense/setup.sh"),
            Path("/usr/bin/nitrosense-setup"),
        ):
            if path.is_file() and os.access(path, os.X_OK):
                return path
        raise FileNotFoundError(t("set.install_missing"))

    def _begin_driver_setup(self) -> None:
        try:
            script = self._setup_script()
        except FileNotFoundError as exc:
            self._toast(str(exc))
            return
        kver = os.uname().release
        if not Path(f"/lib/modules/{kver}/build").is_dir():
            self._toast(t("set.install_no_headers", kver=kver))
            return
        close = t("set.install_close")
        inner = (
            f"export NITROSENSE_ASSUME_YES=1; "
            f"{shlex.quote(str(script))}; "
            f"ec=$?; echo; "
            f"if [ \"$ec\" -eq 0 ]; then echo OK; else echo FAILED $ec; fi; "
            f"read -r -p {shlex.quote(close + ' ')} _"
        )
        launches: list[list[str]] = []
        if shutil.which("gnome-terminal"):
            launches.append(["gnome-terminal", "--", "bash", "-lc", inner])
        if shutil.which("kgx"):
            launches.append(["kgx", "-e", "bash", "-lc", inner])
        if shutil.which("konsole"):
            launches.append(["konsole", "-e", "bash", "-lc", inner])
        if shutil.which("x-terminal-emulator"):
            launches.append(["x-terminal-emulator", "-e", "bash", "-lc", inner])
        for cmd in launches:
            try:
                subprocess.Popen(cmd, start_new_session=True)
                self._toast(t("set.install_body"))
                return
            except OSError:
                continue
        self._toast(t("set.install_no_term", setup=script))

    def _on_autostart(self, _switch: Gtk.Switch, state: bool) -> bool:
        if self._busy:
            return False
        try:
            _set_autostart(state)
        except OSError as exc:
            self._toast(str(exc))
        return False

    def _on_hotkey(self, _switch: Gtk.Switch, state: bool) -> bool:
        if self._busy:
            return False
        _set_hotkey(state)
        if state and not _hotkey_on():
            self._toast("Could not start nitrosense-hotkey.service")
        return False

    def _on_cpu_logical(self, *_args) -> None:
        for tile in self._core_tiles:
            tile.clear()
        child = self._core_host.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._core_host.remove(child)
            child = nxt
        self._core_tiles.clear()

    def _core_view(self, sensors: Sensors) -> list[tuple[float, float | None]]:
        loads = sensors.cpu_cores
        freqs = sensors.cpu_core_freq or [None] * len(loads)
        ids = sensors.cpu_core_ids
        if len(freqs) < len(loads):
            freqs = list(freqs) + [None] * (len(loads) - len(freqs))
        logical = True
        if hasattr(self, "_cpu_logical"):
            logical = self._cpu_logical.get_active()
        if logical or not ids or len(ids) != len(loads):
            return [(loads[i], freqs[i]) for i in range(len(loads))]
        groups: dict[int, list[int]] = {}
        for i, cid in enumerate(ids):
            groups.setdefault(cid, []).append(i)
        rows: list[tuple[float, float | None]] = []
        for cid in sorted(groups):
            idxs = groups[cid]
            avg = sum(loads[i] for i in idxs) / len(idxs)
            present = [freqs[i] for i in idxs if freqs[i] is not None]
            rows.append((avg, max(present) if present else None))
        return rows

    def _sync_home_tiles(self, sensors: Sensors) -> None:
        if sensors.ram_used_gb is not None and sensors.ram_total_gb:
            self.home_ram.update(
                sensors.ram_pct,
                caption=f"{t('tile.ram')}  ·  {sensors.ram_used_gb:.1f}/{sensors.ram_total_gb:.0f} GB",
            )
        else:
            self.home_ram.update(None)
        if sensors.swap_total_gb:
            self.home_swap.update(
                sensors.swap_pct,
                caption=f"{t('tile.swap')}  ·  {sensors.swap_used_gb:.1f}/{sensors.swap_total_gb:.0f} GB",
            )
        else:
            self.home_swap.update(0.0, caption=t("swap.off"), text=t("off"))
        rx, tx = sensors.net_rx_mbps, sensors.net_tx_mbps
        if rx is None or tx is None:
            self.home_net.update(None, caption=sensors.net_iface or t("tile.net"))
        else:
            hint = sensors.net_ipv4 or sensors.net_iface or "NET"
            self.home_net.update(
                rx + tx,
                caption=f"NET  ·  {hint}",
                text=f"↓{rx:.1f}  ↑{tx:.1f}",
            )
        disk = sensors.disks[0] if sensors.disks else None
        if disk is not None and disk.used_gb is not None and disk.total_gb is not None:
            name = disk.name.upper() if disk.name else "DISK"
            self.home_disk.update(
                disk.pct,
                caption=f"{name}  ·  {disk.used_gb:.0f}/{disk.total_gb:.0f} GB",
            )
        else:
            self.home_disk.update(None)

    def _sync_core_grid(self, sensors: Sensors) -> None:
        rows = self._core_view(sensors)
        n = len(rows)
        while len(self._core_tiles) > n:
            tile = self._core_tiles.pop()
            parent = tile.get_parent()
            if parent is not None:
                self._core_host.remove(parent)
        while len(self._core_tiles) < n:
            tile = CoreTile(len(self._core_tiles))
            self._core_tiles.append(tile)
            self._core_host.append(tile)
        for i, (load, freq) in enumerate(rows):
            tile = self._core_tiles[i]
            tile.index = i
            tile.update(load, freq)

    def _fill_resource_labels(self, sensors: Sensors, snap=None) -> None:
        load = sensors.cpu_load
        self._cpu_hero.set_text("—" if load is None else f"{load:.0f}%")
        self._cpu_sub.set_text(sensors.cpu_name or "CPU")
        self._cpu_facts["Model"].set_text(sensors.cpu_name or "—")
        self._cpu_facts["Threads"].set_text(str(len(sensors.cpu_cores) or "—"))
        self._cpu_facts["Frequency"].set_text(
            f"{sensors.cpu_freq_ghz:.2f} GHz" if sensors.cpu_freq_ghz else "—"
        )
        self._cpu_facts["Temperature"].set_text(
            f"{sensors.cpu_temp:.0f} °C" if sensors.cpu_temp is not None else "—"
        )

        if sensors.ram_used_gb is not None and sensors.ram_total_gb:
            self._ram_hero.set_text(f"{sensors.ram_pct:.0f}%")
            self._ram_sub.set_text(
                f"{sensors.ram_used_gb:.1f} / {sensors.ram_total_gb:.1f} GB in use"
            )
            self._ram_facts["Used"].set_text(f"{sensors.ram_used_gb:.1f} GB")
            self.mem_used_tile.update(
                sensors.ram_pct,
                caption=f"Memory  ·  {sensors.ram_used_gb:.1f}/{sensors.ram_total_gb:.0f} GB",
            )
        else:
            self._ram_hero.set_text("—")
            self._ram_sub.set_text("Memory")
            self.mem_used_tile.update(None)
        if sensors.ram_available_gb is not None:
            self._ram_facts["Available"].set_text(f"{sensors.ram_available_gb:.1f} GB")
        if sensors.ram_cached_gb is not None:
            self._ram_facts["Cached"].set_text(f"{sensors.ram_cached_gb:.1f} GB")
        if sensors.swap_total_gb:
            self._ram_facts["Swap"].set_text(
                f"{sensors.swap_used_gb:.1f} / {sensors.swap_total_gb:.0f} GB"
            )
            self.mem_swap_tile.update(
                sensors.swap_pct,
                caption=f"Swap  ·  {sensors.swap_used_gb:.1f}/{sensors.swap_total_gb:.0f} GB",
            )
        else:
            self._ram_facts["Swap"].set_text("off")
            self.mem_swap_tile.update(0.0, caption="Swap  ·  off", text="off")

        rx = sensors.net_rx_mbps
        tx = sensors.net_tx_mbps
        if rx is None or tx is None:
            self._net_hero.set_text("—")
            self._net_sub.set_text(sensors.net_iface or "No default-route interface")
            self.net_rx_tile.update(None)
            self.net_tx_tile.update(None)
        else:
            self._net_hero.set_text(f"{rx + tx:.1f}")
            self._net_sub.set_text("Mb/s  down + up")
            self.net_rx_tile.update(rx, caption="Download")
            self.net_tx_tile.update(tx, caption="Upload")
        self._net_facts["Interface"].set_text(sensors.net_iface or "—")
        self._net_facts["Type"].set_text((sensors.net_kind or "—").upper())
        self._net_facts["IPv4"].set_text(sensors.net_ipv4 or "—")
        self._net_facts["Link"].set_text(
            f"{sensors.net_link_mbps:.0f} Mb/s" if sensors.net_link_mbps else "—"
        )

        self._sync_disks(sensors.disks)

        pct = sensors.battery_pct
        self._bat_hero.set_text("—" if pct is None else f"{pct}%")
        plug = "AC adapter" if sensors.on_ac else "On battery"
        self._bat_sub.set_text(f"{sensors.battery_status or 'Battery'}  ·  {plug}")
        self.bat_charge_tile.update(None if pct is None else float(pct), caption="Charge")
        self.bat_power_tile.update(
            sensors.battery_power_w,
            caption="Power draw" if not sensors.on_ac else "Power  ·  AC",
        )
        self._bat_facts["Status"].set_text(sensors.battery_status or "—")
        self._bat_facts["Power"].set_text(
            f"{sensors.battery_power_w:.1f} W" if sensors.battery_power_w else "—"
        )
        if sensors.battery_energy_wh is not None and sensors.battery_full_wh:
            self._bat_facts["Energy"].set_text(
                f"{sensors.battery_energy_wh:.1f} / {sensors.battery_full_wh:.1f} Wh"
            )
        elif sensors.battery_energy_wh is not None:
            self._bat_facts["Energy"].set_text(f"{sensors.battery_energy_wh:.1f} Wh")
        self._bat_facts["Cycles"].set_text(
            "—" if sensors.battery_cycles is None else str(sensors.battery_cycles)
        )

    def _sync_disks(self, disks) -> None:
        names = [d.name for d in disks]
        if names != list(self._disk_widgets):
            while True:
                child = self._disk_host.get_first_child()
                if child is None:
                    break
                self._disk_host.remove(child)
            self._disk_widgets.clear()
            for disk in disks:
                title = Gtk.Label(label=disk.name.upper(), xalign=0)
                title.add_css_class("ns-page-title")
                sub = Gtk.Label(xalign=0, wrap=True)
                sub.add_css_class("muted")
                used = MetricTile("Used", "%", color=DISK)
                read = MetricTile("Read", "MB/s", color=DISK, ceiling=None)
                write = MetricTile("Write", "MB/s", color=DISK, ceiling=None)
                wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                wrap.append(title)
                wrap.append(sub)
                wrap.append(self._flow_grid(used, read, write, cols=3))
                self._disk_host.append(wrap)
                self._disk_widgets[disk.name] = {
                    "sub": sub,
                    "used": used,
                    "read": read,
                    "write": write,
                }
        for disk in disks:
            slot = self._disk_widgets.get(disk.name)
            if slot is None:
                continue
            slot["sub"].set_text(disk.mount or "unmounted")
            if disk.used_gb is not None and disk.total_gb is not None:
                slot["used"].update(
                    disk.pct,
                    caption=f"Used  ·  {disk.used_gb:.0f}/{disk.total_gb:.0f} GB",
                )
            else:
                slot["used"].update(None, caption="Used")
            slot["read"].update(disk.read_mbps)
            slot["write"].update(disk.write_mbps)

    def _sync_gpus(self, gpus: list[GpuInfo], snap) -> None:
        keys = [g.key for g in gpus]
        if keys != list(self._gpu_widgets):
            while True:
                child = self._gpu_host.get_first_child()
                if child is None:
                    break
                self._gpu_host.remove(child)
            self._gpu_widgets.clear()
            for gpu in gpus:
                vendor = Gtk.Label(label=gpu.vendor.upper(), xalign=0)
                vendor.add_css_class("ns-page-title")
                sub = Gtk.Label(label=gpu.name, xalign=0, wrap=True)
                sub.add_css_class("muted")
                load = MetricTile("Usage", "%")
                temp = MetricTile("Temperature", "°C", ceiling=110)
                freq = MetricTile("Frequency", "MHz", ceiling=None, color=NET)
                tiles: list[MetricTile] = [load, temp, freq]
                power = None
                if gpu.vendor == "NVIDIA" or gpu.power_w is not None:
                    power = MetricTile("Power", "W", ceiling=None)
                    tiles.append(power)
                wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                wrap.append(vendor)
                wrap.append(sub)
                wrap.append(self._flow_grid(*tiles, cols=2))
                self._gpu_host.append(wrap)
                self._gpu_widgets[gpu.key] = {
                    "sub": sub,
                    "load": load,
                    "temp": temp,
                    "freq": freq,
                    "power": power,
                }
        for gpu in gpus:
            slot = self._gpu_widgets.get(gpu.key)
            if slot is None:
                continue
            slot["sub"].set_text(gpu.name)
            rpm = snap.fan_gpu_rpm if snap is not None and gpu.vendor == "NVIDIA" else None
            cap = "Usage"
            if rpm is not None:
                cap = f"Usage  ·  {rpm} RPM"
            slot["load"].update(gpu.load, caption=cap)
            slot["temp"].update(gpu.temp)
            slot["freq"].update(gpu.freq_mhz)
            if slot["power"] is not None:
                if gpu.power_w is not None and gpu.power_limit_w is not None:
                    slot["power"].update(
                        gpu.power_w,
                        caption=f"Power  ·  limit {gpu.power_limit_w:.0f} W",
                    )
                else:
                    slot["power"].update(gpu.power_w)

    def _on_proc_filter(self, _entry: Gtk.SearchEntry) -> None:
        self._refresh_proc_list()

    def _refresh_proc_list(self) -> None:
        query = (self._proc_search.get_text() or "").strip().lower()
        wanted: list[ProcInfo] = []
        for proc in self._proc_rows:
            if query and query not in proc.name.lower() and query not in str(proc.pid):
                continue
            wanted.append(proc)
            if len(wanted) >= 28:
                break
        wanted_ids = {p.pid for p in wanted}
        for pid in list(self._proc_widgets):
            if pid not in wanted_ids:
                row = self._proc_widgets.pop(pid)["row"]
                self._proc_list.remove(row)
        for proc in wanted:
            slot = self._proc_widgets.get(proc.pid)
            if slot is None:
                box = Gtk.Box(spacing=12)
                box.set_margin_start(8)
                box.set_margin_end(8)
                box.set_margin_top(5)
                box.set_margin_bottom(5)
                name = Gtk.Label(xalign=0, hexpand=True)
                name.set_ellipsize(Pango.EllipsizeMode.END)
                pid_l = Gtk.Label()
                cpu = Gtk.Label()
                mem = Gtk.Label()
                pid_l.set_width_chars(7)
                cpu.set_width_chars(6)
                mem.set_width_chars(9)
                end = Gtk.Button(label=t("proc.end"))
                end.connect("clicked", self._on_end_process, proc.pid)
                box.append(name)
                box.append(pid_l)
                box.append(cpu)
                box.append(mem)
                box.append(end)
                self._proc_list.append(box)
                slot = {
                    "row": box.get_parent(),
                    "name": name,
                    "pid": pid_l,
                    "cpu": cpu,
                    "mem": mem,
                }
                self._proc_widgets[proc.pid] = slot
            slot["name"].set_text(proc.name)
            slot["pid"].set_text(str(proc.pid))
            slot["cpu"].set_text(f"{proc.cpu_pct:.0f}%")
            slot["mem"].set_text(f"{proc.mem_mb:.0f} MB")

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
