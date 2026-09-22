#!/usr/bin/env bash
# Install linuwu_sense (root). Called via pkexec.
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo "needs root (pkexec)" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/vendor/Div-Linuwu-Sense"
KO="$VENDOR/src/linuwu_sense.ko"
KVER="$(uname -r)"
MDIR="/lib/modules/${KVER}/kernel/drivers/platform/x86"
MODNAME=linuwu_sense
USER_NAME="$(getent passwd "${PKEXEC_UID:-${SUDO_UID:-}}" | cut -d: -f1)"
USER_NAME="${USER_NAME:-${SUDO_USER:-}}"
if [[ -z "$USER_NAME" || "$USER_NAME" == "root" ]]; then
  USER_NAME="$(logname 2>/dev/null || true)"
fi
USER_NAME="${USER_NAME:-root}"

if [[ ! -f "$KO" ]]; then
  echo "module not built: $KO" >&2
  exit 1
fi

rmmod acer_wmi 2>/dev/null || true
echo "blacklist acer_wmi" > /etc/modprobe.d/blacklist-acer_wmi.conf
install -d "$MDIR"
install -m 644 "$KO" "$MDIR/${MODNAME}.ko"
depmod -a
echo "$MODNAME" > /etc/modules-load.d/${MODNAME}.conf
modprobe "$MODNAME"

if [[ -f "$VENDOR/linuwu_sense.service" ]]; then
  cp "$VENDOR/linuwu_sense.service" /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now linuwu_sense.service || true
fi

if ! getent group linuwu_sense >/dev/null; then
  groupadd linuwu_sense
fi
usermod -aG linuwu_sense "$USER_NAME"

SYSFS="/sys/module/${MODNAME}/drivers/platform:acer-wmi/acer-wmi"
CONF=/etc/tmpfiles.d/${MODNAME}.conf
: > "$CONF"
if [[ -d "$SYSFS/nitro_sense" ]]; then
  for f in fan_speed battery_limiter battery_calibration usb_charging backlight_timeout lcd_override boot_animation_sound; do
    [[ -e "$SYSFS/nitro_sense/$f" ]] || continue
    echo "f $SYSFS/nitro_sense/$f 0660 root linuwu_sense" >> "$CONF"
  done
fi
if [[ -d "$SYSFS/predator_sense" ]]; then
  for f in fan_speed battery_limiter battery_calibration usb_charging backlight_timeout lcd_override boot_animation_sound; do
    [[ -e "$SYSFS/predator_sense/$f" ]] || continue
    echo "f $SYSFS/predator_sense/$f 0660 root linuwu_sense" >> "$CONF"
  done
fi
if [[ -f /sys/firmware/acpi/platform_profile ]]; then
  echo "f /sys/firmware/acpi/platform_profile 0660 root linuwu_sense" >> "$CONF"
fi
if [[ -d "$SYSFS/four_zoned_kb" ]]; then
  for z in four_zone_mode per_zone_mode; do
    echo "f $SYSFS/four_zoned_kb/$z 0660 root linuwu_sense" >> "$CONF"
  done
fi
systemd-tmpfiles --create "$CONF" || true
"$ROOT/bin/nitrosense-fixperms" || true

echo "linuwu_sense installed for $USER_NAME"
ls "$SYSFS" 2>/dev/null || true
cat /sys/firmware/acpi/platform_profile_choices 2>/dev/null || echo "no platform_profile yet"
