#!/usr/bin/env bash
# Instala driver Linuwu + atalho da GUI NitroSense Linux.
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
    echo "falta $1" >&2
    exit 1
  }
}

need_cmd git
need_cmd make
need_cmd python3

if [[ ! -d /lib/modules/$(uname -r)/build ]]; then
  echo "Instala linux-headers-$(uname -r) antes." >&2
  exit 1
fi

echo "==> GUI (atalho do utilizador)"
mkdir -p "$(dirname "$APP_DESKTOP")" "$APP_ICON_DIR"
install -m 0755 "$ROOT/bin/nitrosense" "$ROOT/bin/nitrosense"
install -m 0755 "$ROOT/bin/nitrosense-helper" "$ROOT/bin/nitrosense-helper"
install -m 0755 "$ROOT/bin/nitrosense-fixperms" "$ROOT/bin/nitrosense-fixperms"
cp "$ROOT/data/icon.svg" "$APP_ICON_DIR/nitrosense-linux.svg"
sed -e "s|@EXEC@|$ROOT/bin/nitrosense|g" -e "s|@ICON@|nitrosense-linux|g" \
  "$ROOT/data/nitrosense.desktop.in" > "$APP_DESKTOP"
chmod 0644 "$APP_DESKTOP"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "A GUI já abre sem driver (CPU/GPU). Para fans, modos e bateria precisa do Linuwu."
echo "Isto substitui acer_wmi, pede sudo, e no 1º login depois tens de sair da sessão"
echo "para o grupo linuwu_sense aplicar."
echo
read -r -p "Instalar driver Linuwu Sense agora? [s/N] " ans
ans="${ans:-N}"
if [[ "$ans" != [sS] ]]; then
  echo "Ok. Corre de novo e aceita quando quiseres o driver."
  echo "Abrir GUI: $ROOT/bin/nitrosense"
  exit 0
fi

echo "==> Driver Div-Linuwu-Sense (ANV15-51 testado no DAMX)"
mkdir -p "$ROOT/vendor"
if [[ ! -d "$VENDOR/.git" ]]; then
  git clone --depth 1 "$REPO" "$VENDOR"
else
  git -C "$VENDOR" pull --ff-only || true
fi

if ! make -C "$VENDOR" install; then
  echo
  echo "Compilação Linuwu falhou neste kernel $(uname -r)."
  echo "Fallback: acer_wmi.predator_v4=1 (modos + fans PWM, sem limite de bateria)."
  read -r -p "Aplicar fallback in-tree? [s/N] " fb
  if [[ "$fb" == [sS] ]]; then
    echo "options acer_wmi predator_v4=1" | sudo tee /etc/modprobe.d/nitrosense-acer-wmi.conf
    sudo update-initramfs -u
    echo "Reinicia para o parâmetro entrar."
  fi
  exit 1
fi

# ANV15-51: tmpfiles do Linuwu omitem backlight_timeout e platform_profile.
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
echo "Driver instalado. Se os writes falharem, faz logout/login (grupo linuwu_sense)."
echo "Abrir: $ROOT/bin/nitrosense"
echo "Ou procura NitroSense Linux no menu."
