"""GNOME top-bar icon via StatusNotifierItem (Ubuntu AppIndicators). GTK4-safe."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import cairo
from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parents[1]
_BUS_NAME = "org.alfred.nitrosense.status"
_ITEM_PATH = "/StatusNotifierItem"
_MENU_PATH = "/MenuBar"

_SNI_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="ContextMenu">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="Activate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="Scroll">
      <arg type="i" name="delta" direction="in"/>
      <arg type="s" name="orientation" direction="in"/>
    </method>
  </interface>
</node>
"""

_MENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="Status" type="s" access="read"/>
    <method name="GetLayout">
      <arg type="i" name="parentId" direction="in"/>
      <arg type="i" name="recursionDepth" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="u" name="revision" direction="out"/>
      <arg type="(ia{sv}av)" name="layout" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="a(ia{sv})" name="properties" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="name" direction="in"/>
      <arg type="v" name="value" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="eventId" direction="in"/>
      <arg type="v" name="data" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" name="id" direction="in"/>
      <arg type="b" name="needUpdate" direction="out"/>
    </method>
    <signal name="LayoutUpdated">
      <arg type="u" name="revision"/>
      <arg type="i" name="parent"/>
    </signal>
    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{sv})" name="updatedProps"/>
      <arg type="a(ias)" name="removedProps"/>
    </signal>
  </interface>
</node>
"""


def _icon_pixmap(size: int = 32) -> tuple[int, int, bytes]:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)
    cr.set_source_rgba(0.09, 0.09, 0.11, 1.0)
    _round_rect(cr, 1, 1, size - 2, size - 2, max(4, size * 0.18))
    cr.fill()
    cr.set_source_rgb(1.0, 0.48, 0.0)
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(size * 0.62)
    text = "N"
    ext = cr.text_extents(text)
    cr.move_to((size - ext.width) / 2 - ext.x_bearing, (size - ext.height) / 2 - ext.y_bearing)
    cr.show_text(text)
    src = bytes(surface.get_data())
    stride = surface.get_stride()
    out = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            i = y * stride + x * 4
            blue, green, red, alpha = src[i], src[i + 1], src[i + 2], src[i + 3]
            j = (y * size + x) * 4
            out[j : j + 4] = bytes((alpha, red, green, blue))
    return size, size, bytes(out)


def _round_rect(cr, x, y, w, h, r) -> None:
    cr.new_path()
    cr.arc(x + w - r, y + r, r, -3.14159 / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, 3.14159 / 2)
    cr.arc(x + r, y + h - r, r, 3.14159 / 2, 3.14159)
    cr.arc(x + r, y + r, r, 3.14159, 3 * 3.14159 / 2)
    cr.close_path()


def _icon_theme_path() -> str:
    packaged = Path("/usr/share/icons/hicolor/scalable/apps/nitrosense.svg")
    if packaged.is_file():
        return str(packaged.parent)
    src = ROOT / "data" / "icon.svg"
    cache = Path.home() / ".cache" / "nitrosense"
    if src.is_file():
        cache.mkdir(parents=True, exist_ok=True)
        dest = cache / "nitrosense.svg"
        text = src.read_text(encoding="utf-8")
        if not dest.is_file() or dest.read_text(encoding="utf-8") != text:
            dest.write_text(text, encoding="utf-8")
        return str(cache)
    return str(cache)


class TrayIcon:
    def __init__(
        self,
        *,
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
        on_mode: Callable[[str], None] | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        self._on_show = on_show
        self._on_quit = on_quit
        self._on_mode = on_mode
        self._labels = labels or {}
        self._revision = 1
        self._pixmap = _icon_pixmap(32)
        self._sni_id = 0
        self._menu_id = 0
        self._conn: Gio.DBusConnection | None = None
        self._own = Gio.bus_own_name(
            Gio.BusType.SESSION,
            _BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus,
            None,
            None,
        )

    def _L(self, key: str, fallback: str) -> str:
        return self._labels.get(key) or fallback

    def _on_bus(self, conn: Gio.DBusConnection, _name: str) -> None:
        self._conn = conn
        sni_info = Gio.DBusNodeInfo.new_for_xml(_SNI_XML)
        menu_info = Gio.DBusNodeInfo.new_for_xml(_MENU_XML)
        self._sni_id = conn.register_object(
            _ITEM_PATH,
            sni_info.interfaces[0],
            self._sni_method,
            self._sni_get,
            None,
        )
        self._menu_id = conn.register_object(
            _MENU_PATH,
            menu_info.interfaces[0],
            self._menu_method,
            self._menu_get,
            None,
        )
        self._register_watcher()

    def _register_watcher(self) -> None:
        if self._conn is None:
            return
        for name in ("org.kde.StatusNotifierWatcher", "org.freedesktop.StatusNotifierWatcher"):
            try:
                proxy = Gio.DBusProxy.new_sync(
                    self._conn,
                    Gio.DBusProxyFlags.NONE,
                    None,
                    name,
                    "/StatusNotifierWatcher",
                    "org.kde.StatusNotifierWatcher",
                    None,
                )
                proxy.call_sync(
                    "RegisterStatusNotifierItem",
                    GLib.Variant("(s)", (_ITEM_PATH,)),
                    Gio.DBusCallFlags.NONE,
                    2000,
                    None,
                )
                return
            except GLib.Error:
                continue

    def _sni_get(self, _conn, _sender, _path, _iface, name):
        pix = self._pixmap
        tooltip = (
            "",
            [],
            "NitroSense",
            self._L("tray.tooltip", "NitroSense"),
        )
        values = {
            "Category": GLib.Variant("s", "Hardware"),
            "Id": GLib.Variant("s", "nitrosense"),
            "Title": GLib.Variant("s", "NitroSense"),
            "Status": GLib.Variant("s", "Active"),
            "WindowId": GLib.Variant("i", 0),
            "IconName": GLib.Variant("s", "nitrosense"),
            "IconThemePath": GLib.Variant("s", _icon_theme_path()),
            "IconPixmap": GLib.Variant("a(iiay)", [(pix[0], pix[1], pix[2])]),
            "ToolTip": GLib.Variant("(sa(iiay)ss)", tooltip),
            "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", _MENU_PATH),
        }
        return values.get(name)

    def _sni_method(self, _conn, _sender, _path, _iface, method, params, invocation):
        if method in {"Activate", "SecondaryActivate", "ContextMenu"}:
            GLib.idle_add(self._on_show)
        invocation.return_value(None)

    def _menu_get(self, _conn, _sender, _path, _iface, name):
        if name == "Version":
            return GLib.Variant("u", 3)
        if name == "Status":
            return GLib.Variant("s", "normal")
        return None

    def _menu_tree(self):
        def node(ident: int, props: dict, children: list | None = None):
            packed = {}
            for key, val in props.items():
                packed[key] = val if isinstance(val, GLib.Variant) else GLib.Variant("s", str(val))
            return (ident, packed, children or [])

        kids = [
            node(1, {"label": self._L("tray.show", "Show window")}),
            node(2, {"type": GLib.Variant("s", "separator")}),
            node(10, {"label": self._L("mode.quiet", "Quiet")}),
            node(11, {"label": self._L("mode.default", "Default")}),
            node(12, {"label": self._L("mode.performance", "Performance")}),
            node(13, {"type": GLib.Variant("s", "separator")}),
            node(30, {"label": self._L("tray.quit", "Quit")}),
        ]
        return (0, {"children-display": GLib.Variant("s", "submenu")}, kids)

    def _to_variant_layout(self, node) -> GLib.Variant:
        ident, props, children = node
        child_vars = [self._to_variant_layout(ch) for ch in children]
        return GLib.Variant("(ia{sv}av)", (ident, props, child_vars))

    def _menu_method(self, _conn, _sender, _path, _iface, method, params, invocation):
        if method == "GetLayout":
            layout = self._to_variant_layout(self._menu_tree())
            invocation.return_value(GLib.Variant.new_tuple(GLib.Variant("u", self._revision), layout))
            return
        if method == "GetGroupProperties":
            invocation.return_value(GLib.Variant("(a(ia{sv}))", ([],)))
            return
        if method == "GetProperty":
            invocation.return_value(GLib.Variant("(v)", (GLib.Variant("s", ""),)))
            return
        if method == "Event":
            ident = int(params[0])
            event = str(params[1])
            if event == "clicked":
                GLib.idle_add(self._menu_click, ident)
            invocation.return_value(None)
            return
        if method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
            return
        invocation.return_error_literal(
            Gio.dbus_error_quark(),
            Gio.DBusError.UNKNOWN_METHOD,
            method,
        )

    def _menu_click(self, ident: int) -> bool:
        if ident == 1:
            self._on_show()
        elif ident == 10 and self._on_mode:
            self._on_mode("quiet")
        elif ident == 11 and self._on_mode:
            self._on_mode("balanced")
        elif ident == 12 and self._on_mode:
            self._on_mode("performance")
        elif ident == 30:
            self._on_quit()
        return False

    def close(self) -> None:
        if self._conn is not None:
            if self._sni_id:
                self._conn.unregister_object(self._sni_id)
            if self._menu_id:
                self._conn.unregister_object(self._menu_id)
        if self._own:
            Gio.bus_unown_name(self._own)
            self._own = 0
