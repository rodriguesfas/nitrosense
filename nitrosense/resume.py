"""Listen for system sleep/hibernate and restore a safe or saved profile."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

PrepareCb = Callable[[bool], None]


def watch_prepare_for_sleep(callback: PrepareCb) -> Gio.DBusConnection | None:
    """callback(sleeping=True) before sleep; callback(False) after resume."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    except Exception:  # noqa: BLE001
        return None

    def _on_signal(
        _conn, _sender, _path, _iface, signal_name, params
    ) -> None:
        if signal_name != "PrepareForSleep":
            return
        try:
            sleeping = bool(params.unpack()[0])
        except Exception:  # noqa: BLE001
            return
        callback(sleeping)

    try:
        bus.signal_subscribe(
            "org.freedesktop.login1",
            "org.freedesktop.login1.Manager",
            "PrepareForSleep",
            "/org/freedesktop/login1",
            None,
            Gio.DBusSignalFlags.NONE,
            _on_signal,
        )
    except Exception:  # noqa: BLE001
        return None
    return bus
