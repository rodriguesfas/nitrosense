#!/usr/bin/env bash
# Install the Linuwu driver and a desktop entry for NitroSense Linux.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ -w "$ROOT" ]]; then
  VENDOR="$ROOT/vendor/Div-Linuwu-Sense"
else
  VENDOR="${XDG_CACHE_HOME:-$HOME/.cache}/nitrosense/Div-Linuwu-Sense"
fi
REPO="https://github.com/PXDiv/Div-Linuwu-Sense.git"
APP_DESKTOP="$HOME/.local/share/applications/nitrosense-linux.desktop"
APP_ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing $1" >&2
    exit 1
  }
}

need_cmd git
need_cmd make
need_cmd python3

if [[ ! -d /lib/modules/$(uname -r)/build ]]; then
  echo "Install linux-headers-$(uname -r) first." >&2
  exit 1
fi

echo "==> GUI (user desktop entry)"
mkdir -p "$(dirname "$APP_DESKTOP")" "$APP_ICON_DIR" "$HOME/.config/autostart"
install -m 0755 "$ROOT/bin/nitrosense" "$ROOT/bin/nitrosense"
install -m 0755 "$ROOT/bin/nitrosense-helper" "$ROOT/bin/nitrosense-helper"
install -m 0755 "$ROOT/bin/nitrosense-fixperms" "$ROOT/bin/nitrosense-fixperms"
install -m 0755 "$ROOT/bin/nitrosense-tgp-restore" "$ROOT/bin/nitrosense-tgp-restore"
cp "$ROOT/data/icon.svg" "$APP_ICON_DIR/nitrosense-linux.svg"
sed -e "s|@EXEC@|$ROOT/bin/nitrosense|g" -e "s|@ICON@|nitrosense-linux|g" \
  "$ROOT/data/nitrosense.desktop.in" > "$APP_DESKTOP"
chmod 0644 "$APP_DESKTOP"
sed -e "s|@EXEC@|$ROOT/bin/nitrosense-tgp-restore|g" \
  "$ROOT/data/nitrosense-tgp.desktop.in" > "$HOME/.config/autostart/nitrosense-tgp.desktop"
chmod 0644 "$HOME/.config/autostart/nitrosense-tgp.desktop"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "The GUI already opens without a driver (CPU/GPU). Fans, modes and battery need Linuwu."
echo "This replaces acer_wmi, asks for sudo, and you must log out once afterwards"
echo "so the linuwu_sense group applies."
echo
read -r -p "Install the Linuwu Sense driver now? [y/N] " ans
ans="${ans:-N}"
if [[ "$ans" != [yY] ]]; then
  echo "OK. Run this again and accept when you want the driver."
  echo "Launch GUI: $ROOT/bin/nitrosense"
  exit 0
fi

echo "==> Div-Linuwu-Sense driver (ANV15-51 covered by DAMX)"
mkdir -p "$ROOT/vendor"
if [[ ! -d "$VENDOR/.git" ]]; then
  git clone --depth 1 "$REPO" "$VENDOR"
else
  git -C "$VENDOR" pull --ff-only || true
fi

if ! make -C "$VENDOR" install; then
  echo
  echo "Linuwu build failed on kernel $(uname -r)."
  echo "Fallback: acer_wmi.predator_v4=1 (modes + PWM fans, no battery limiter)."
  read -r -p "Apply in-tree fallback? [y/N] " fb
  if [[ "$fb" == [yY] ]]; then
    echo "options acer_wmi predator_v4=1" | sudo tee /etc/modprobe.d/nitrosense-acer-wmi.conf
    sudo update-initramfs -u
    echo "Reboot for the parameter to take effect."
  fi
  exit 1
fi

# ANV15-51: Linuwu tmpfiles omit backlight_timeout and platform_profile.
TMPCONF=/etc/tmpfiles.d/linuwu_sense.conf
SYSFS_BASE=/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi
{
  echo "f /sys/firmware/acpi/platform_profile 0660 root linuwu_sense"
  if [[ -f $SYSFS_BASE/nitro_sense/backlight_timeout ]]; then
    echo "f $SYSFS_BASE/nitro_sense/backlight_timeout 0660 root linuwu_sense"
  fi
} | sudo tee -a "$TMPCONF" >/dev/null
sudo systemd-tmpfiles --create "$TMPCONF" || true
sudo "$ROOT/bin/nitrosense-fixperms" || true

POLICY_DST=/usr/share/polkit-1/actions/org.alfred.nitrosense.policy
sed "s|@HELPER@|$ROOT/bin/nitrosense-helper|g" \
  "$ROOT/data/org.alfred.nitrosense.policy.in" | sudo tee "$POLICY_DST" >/dev/null

echo
echo "Driver installed. If writes fail, log out/in (linuwu_sense group)."
echo "Launch: $ROOT/bin/nitrosense"
echo "Or search NitroSense in the app menu."
