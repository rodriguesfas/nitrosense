"""Session lighting: display brightness, Night Light, lock-key LEDs."""

from __future__ import annotations

import subprocess
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

_GSD = "org.gnome.SettingsDaemon.Power"
_GSD_PATH = "/org/gnome/SettingsDaemon/Power"
_SCREEN = "org.gnome.SettingsDaemon.Power.Screen"
_COLOR = "org.gnome.settings-daemon.plugins.color"
_LOGIN1 = "org.freedesktop.login1"
_LOGIN1_PATH = "/org/freedesktop/login1/session/auto"
_LOGIN1_IFACE = "org.freedesktop.login1.Session"

NIGHT_TEMP_MIN = 1700
NIGHT_TEMP_MAX = 4700
LOCK_KEYS = {
    "caps": "Caps_Lock",
    "num": "Num_Lock",
    "scroll": "Scroll_Lock",
}


def _backlight_dir() -> Path | None:
    root = Path("/sys/class/backlight")
    if not root.is_dir():
        return None
    dirs = [p for p in sorted(root.iterdir()) if (p / "max_brightness").is_file()]
    return dirs[0] if dirs else None


def _props() -> Gio.DBusProxy | None:
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        return Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            _GSD,
            _GSD_PATH,
            "org.freedesktop.DBus.Properties",
            None,
        )
    except GLib.Error:
        return None


def screen_brightness() -> int | None:
    path = _backlight_dir()
    if path is not None:
        try:
            actual = int((path / "actual_brightness").read_text(encoding="utf-8").strip())
            maximum = int((path / "max_brightness").read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            actual, maximum = -1, 0
        if maximum > 0:
            return max(0, min(100, round(actual * 100 / maximum)))
    proxy = _props()
    if proxy is None:
        return None
    try:
        result = proxy.call_sync(
            "Get",
            GLib.Variant("(ss)", (_SCREEN, "Brightness")),
            Gio.DBusCallFlags.NONE,
            1500,
            None,
        )
    except GLib.Error:
        return None
    value = result.unpack()[0]
    return int(value) if value is not None else None


def set_screen_brightness(pct: int) -> None:
    pct = max(0, min(100, int(pct)))
    path = _backlight_dir()
    if path is not None:
        try:
            maximum = int((path / "max_brightness").read_text(encoding="utf-8").strip())
        except (OSError, ValueError) as exc:
            raise RuntimeError("display brightness is not available") from exc
        value = max(0, min(maximum, round(pct * maximum / 100)))
        if _logind_set(path.name, value):
            return
        try:
            (path / "brightness").write_text(f"{value}\n", encoding="utf-8")
            return
        except OSError:
            pass
    _gsd_set(pct)


def _logind_set(device: str, value: int) -> bool:
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        proxy = Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            _LOGIN1,
            _LOGIN1_PATH,
            _LOGIN1_IFACE,
            None,
        )
        proxy.call_sync(
            "SetBrightness",
            GLib.Variant("(ssu)", ("backlight", device, value)),
            Gio.DBusCallFlags.NONE,
            1500,
            None,
        )
        return True
    except GLib.Error:
        return False


def _gsd_set(pct: int) -> None:
    proxy = _props()
    if proxy is None:
        raise RuntimeError("display brightness is not available")
    proxy.call_sync(
        "Set",
        GLib.Variant("(ssv)", (_SCREEN, "Brightness", GLib.Variant("i", pct))),
        Gio.DBusCallFlags.NONE,
        1500,
        None,
    )


def _color_settings() -> Gio.Settings | None:
    try:
        return Gio.Settings.new(_COLOR)
    except GLib.Error:
        return None


def night_light() -> tuple[bool | None, int | None]:
    settings = _color_settings()
    if settings is None:
        return None, None
    return settings.get_boolean("night-light-enabled"), int(
        settings.get_uint("night-light-temperature")
    )


def set_night_light(enabled: bool) -> None:
    settings = _color_settings()
    if settings is None:
        raise RuntimeError("Night Light is not available")
    if not settings.set_boolean("night-light-enabled", enabled):
        raise RuntimeError("could not change Night Light")


def set_night_temp(kelvin: int) -> None:
    settings = _color_settings()
    if settings is None:
        raise RuntimeError("Night Light is not available")
    kelvin = max(NIGHT_TEMP_MIN, min(NIGHT_TEMP_MAX, int(kelvin)))
    if not settings.set_uint("night-light-temperature", kelvin):
        raise RuntimeError("could not change colour temperature")


def lock_leds() -> dict[str, bool]:
    out = {"caps": False, "num": False, "scroll": False}
    base = Path("/sys/class/leds")
    if not base.is_dir():
        return out
    mapping = (("caps", "capslock"), ("num", "numlock"), ("scroll", "scrolllock"))
    for key, suffix in mapping:
        matches = sorted(base.glob(f"*::{suffix}"))
        if not matches:
            continue
        try:
            raw = (matches[0] / "brightness").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        out[key] = raw not in {"", "0"}
    return out


def toggle_lock_led(key: str) -> None:
    name = LOCK_KEYS.get(key)
    if not name:
        raise RuntimeError(f"unknown lock LED {key}")
    try:
        result = subprocess.run(
            ["xdotool", "key", name],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("could not toggle lock key") from exc
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(err or "could not toggle lock key")
