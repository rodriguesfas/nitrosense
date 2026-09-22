#!/usr/bin/env bash
# Package the GUI + helper (Python). The Linuwu module is not in the .deb.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "invalid VERSION: $VERSION" >&2
  exit 1
fi

PKG=nitrosense
ARCH=all
DEB_NAME="${PKG}_${VERSION}_${ARCH}.deb"
STAGE="$ROOT/dist/${PKG}_${VERSION}_${ARCH}"

rm -rf "$STAGE"
mkdir -p \
  "$STAGE/DEBIAN" \
  "$STAGE/usr/bin" \
  "$STAGE/usr/libexec" \
  "$STAGE/usr/share/nitrosense" \
  "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/icons/hicolor/scalable/apps" \
  "$STAGE/usr/share/polkit-1/actions" \
  "$STAGE/usr/lib/systemd/user" \
  "$STAGE/etc/xdg/autostart" \
  "$STAGE/usr/share/doc/nitrosense"

cp -a "$ROOT/nitrosense" "$STAGE/usr/share/nitrosense/nitrosense"
cp -a "$ROOT/bin" "$STAGE/usr/share/nitrosense/bin"
install -m 0755 "$ROOT/setup.sh" "$STAGE/usr/share/nitrosense/setup.sh"
install -m 0755 "$ROOT/install-hotkey.sh" "$STAGE/usr/share/nitrosense/install-hotkey.sh"
install -m 0755 "$ROOT/bin/install-driver-root.sh" "$STAGE/usr/share/nitrosense/bin/install-driver-root.sh"
cp -a "$ROOT/data" "$STAGE/usr/share/nitrosense/data"
install -m 0644 "$ROOT/README.md" "$STAGE/usr/share/doc/nitrosense/README.md"
install -m 0644 "$ROOT/LICENSE" "$STAGE/usr/share/doc/nitrosense/copyright"
printf '%s\n' "$VERSION" > "$STAGE/usr/share/nitrosense/VERSION"

find "$STAGE" -type d -name '__pycache__' -exec rm -rf {} +
find "$STAGE" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

install -m 0755 "$ROOT/bin/nitrosense" "$STAGE/usr/bin/nitrosense"
install -m 0755 "$ROOT/bin/nitrosense-tgp-restore" "$STAGE/usr/bin/nitrosense-tgp-restore"
install -m 0755 "$ROOT/bin/nitrosense-helper" "$STAGE/usr/libexec/nitrosense-helper"
install -m 0755 "$ROOT/bin/nitrosense-hotkey" "$STAGE/usr/libexec/nitrosense-hotkey"
install -m 0755 "$ROOT/bin/nitrosense-fixperms" "$STAGE/usr/libexec/nitrosense-fixperms"

cat > "$STAGE/usr/bin/nitrosense-setup" <<'EOF'
#!/usr/bin/env bash
exec /usr/share/nitrosense/setup.sh "$@"
EOF
chmod 0755 "$STAGE/usr/bin/nitrosense-setup"

sed -e 's|@EXEC@|nitrosense|g' -e 's|@ICON@|nitrosense|g' \
  "$ROOT/data/nitrosense.desktop.in" > "$STAGE/usr/share/applications/nitrosense.desktop"
install -m 0644 "$ROOT/data/icon.svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/nitrosense.svg"
sed 's|@HELPER@|/usr/libexec/nitrosense-helper|g' \
  "$ROOT/data/org.alfred.nitrosense.policy.in" \
  > "$STAGE/usr/share/polkit-1/actions/org.alfred.nitrosense.policy"
sed 's|@HOTKEY@|/usr/libexec/nitrosense-hotkey|g' \
  "$ROOT/data/nitrosense-hotkey.service.in" \
  > "$STAGE/usr/lib/systemd/user/nitrosense-hotkey.service"
sed 's|@EXEC@|nitrosense-tgp-restore|g' \
  "$ROOT/data/nitrosense-tgp.desktop.in" \
  > "$STAGE/etc/xdg/autostart/nitrosense-tgp.desktop"
install -d "$STAGE/usr/lib/systemd/system" "$STAGE/etc/dbus-1/system.d"
install -m 0644 "$ROOT/data/nvidia-powerd.service" "$STAGE/usr/lib/systemd/system/nvidia-powerd.service"
install -m 0644 "$ROOT/data/nvidia-powerd-dbus.conf" "$STAGE/etc/dbus-1/system.d/nvidia-powerd.conf"

SIZE="$(du -sk "$STAGE" | awk '{print $1}')"

cat > "$STAGE/DEBIAN/control" <<EOF
Package: ${PKG}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, python3-gi-cairo, pkexec
Maintainer: Francisco Rodrigues <franciscosouzaacer@gmail.com>
Installed-Size: ${SIZE}
Homepage: https://github.com/rodriguesfas/nitrosense
Description: Unofficial NitroSense clone for Acer Nitro on Linux
 GTK4 HUD for Acer Nitro (ANV15-51 tested): CPU/GPU/RAM, Quiet/Default/
 Performance, Auto/Max/Custom fans, per-app scenario rules, NVIDIA TGP,
 battery limiter, USB charging. Fan and profile writes need the Linuwu
 Sense kernel module (not in this package). After install, run
 nitrosense-setup or follow the README.
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi
if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload || true
fi
exit 0
EOF
chmod 0755 "$STAGE/DEBIAN/postinst"

mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$STAGE" "$ROOT/dist/$DEB_NAME"
echo "$ROOT/dist/$DEB_NAME"
