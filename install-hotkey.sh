#!/usr/bin/env bash
# Bind the dedicated N key (NitroSense) and a menu entry — no sudo.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
APP_DESKTOP="$HOME/.local/share/applications/nitrosense-linux.desktop"
APP_ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
KB="org.gnome.settings-daemon.plugins.media-keys"
KB_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/nitrosense/"

chmod +x "$ROOT/bin/nitrosense" "$ROOT/bin/nitrosense-hotkey"

mkdir -p "$(dirname "$APP_DESKTOP")" "$APP_ICON_DIR" "$UNIT_DIR"
cp "$ROOT/data/icon.svg" "$APP_ICON_DIR/nitrosense-linux.svg"
sed -e "s|@EXEC@|$ROOT/bin/nitrosense|g" -e "s|@ICON@|nitrosense-linux|g" \
  "$ROOT/data/nitrosense.desktop.in" > "$APP_DESKTOP"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

sed "s|@HOTKEY@|$ROOT/bin/nitrosense-hotkey|g" \
  "$ROOT/data/nitrosense-hotkey.service.in" > "$UNIT_DIR/nitrosense-hotkey.service"
systemctl --user daemon-reload
systemctl --user enable --now nitrosense-hotkey.service

# XF86Launch1 = KEY_PROG1 (148) no Acer WMI deste ANV15-51.
gsettings set "$KB" custom-keybindings "['$KB_PATH']"
gsettings set "${KB}.custom-keybinding:${KB_PATH}" name "NitroSense"
gsettings set "${KB}.custom-keybinding:${KB_PATH}" command "$ROOT/bin/nitrosense"
gsettings set "${KB}.custom-keybinding:${KB_PATH}" binding "XF86Launch1"

echo "NitroSense key (PROG1 / XF86Launch1) → $ROOT/bin/nitrosense"
echo "Service: systemctl --user status nitrosense-hotkey.service"
