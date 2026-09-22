"""Hardware layer: Linuwu Sense sysfs with acer_wmi / PWM fallback."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PROFILE_FILE = Path("/sys/firmware/acpi/platform_profile")
PROFILE_CHOICES = Path("/sys/firmware/acpi/platform_profile_choices")

SENSE_NAMES = ("nitro_sense", "predator_sense")
KB_DIR_NAME = "four_zoned_kb"

# NitroSense names → firmware values on this ANV15-51.
# Firmware rejects "performance" (turbo); Windows Performance maps to
# balanced-performance.
NITRO_MODES = (
    ("quiet", "Quiet", "quiet"),
    ("balanced", "Default", "balanced"),
    ("performance", "Performance", "balanced-performance"),
)

HELPER_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "bin" / "nitrosense-helper",
    Path("/usr/libexec/nitrosense-helper"),
    Path("/usr/local/libexec/nitrosense-helper"),
)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _find_sense_dir() -> Path | None:
    roots = [
        Path("/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi"),
        Path("/sys/devices/platform/acer-wmi"),
    ]
    for root in roots:
        if not root.exists():
            continue
        for name in SENSE_NAMES:
            candidate = root / name
            if candidate.is_dir():
                return candidate
    for name in SENSE_NAMES:
        matches = list(Path("/sys/devices").glob(f"**/acer-wmi/{name}"))
        if matches:
            return matches[0]
    return None


def _find_kb_dir(sense: Path | None) -> Path | None:
    if sense is None:
        return None
    parent = sense.parent
    kb = parent / KB_DIR_NAME
    return kb if kb.is_dir() else None


def _find_acer_hwmon() -> Path | None:
    base = Path("/sys/class/hwmon")
    if not base.is_dir():
        return None
    for hwmon in base.glob("hwmon*"):
        name = _read(hwmon / "name")
        if name in {"acer", "acer_wmi"}:
            return hwmon
    return None


def helper_path() -> Path | None:
    for path in HELPER_CANDIDATES:
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def pkexec_helper() -> Path | None:
    """Helper path that matches the installed polkit exec.path annotation."""
    for path in (
        Path("/usr/libexec/nitrosense-helper"),
        Path("/usr/local/libexec/nitrosense-helper"),
    ):
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return helper_path()


@dataclass
class Capabilities:
    driver: str = "none"
    profiles: bool = False
    fan_speed: bool = False
    pwm: bool = False
    battery_limiter: bool = False
    battery_calibration: bool = False
    usb_charging: bool = False
    backlight_timeout: bool = False
    lcd_override: bool = False
    boot_animation: bool = False
    rgb_keyboard: bool = False


@dataclass
class Snapshot:
    caps: Capabilities = field(default_factory=Capabilities)
    profile: str | None = None
    profile_choices: list[str] = field(default_factory=list)
    fan_cpu_pct: int | None = None
    fan_gpu_pct: int | None = None
    fan_auto: bool = True
    fan_cpu_rpm: int | None = None
    fan_gpu_rpm: int | None = None
    battery_limiter: bool | None = None
    battery_calibration: bool | None = None
    usb_charging: int | None = None
    backlight_timeout: bool | None = None
    lcd_override: bool | None = None
    boot_animation: bool | None = None
    rgb_per_zone: str | None = None
    rgb_mode: str | None = None


class Hardware:
    def __init__(self) -> None:
        self.sense = _find_sense_dir()
        self.kb = _find_kb_dir(self.sense)
        self.hwmon = _find_acer_hwmon()
        self.caps = self._detect_caps()

    def refresh_paths(self) -> None:
        self.sense = _find_sense_dir()
        self.kb = _find_kb_dir(self.sense)
        self.hwmon = _find_acer_hwmon()
        self.caps = self._detect_caps()

    def _detect_caps(self) -> Capabilities:
        caps = Capabilities()
        if Path("/sys/module/linuwu_sense").exists() or (
            self.sense is not None and "linuwu" in str(self.sense)
        ):
            caps.driver = "linuwu"
        elif self.sense is not None or self.hwmon is not None:
            caps.driver = "acer_wmi"
        elif PROFILE_FILE.exists():
            caps.driver = "acer_wmi"
        else:
            caps.driver = "none"

        caps.profiles = PROFILE_FILE.exists()
        if self.sense is not None:
            caps.fan_speed = (self.sense / "fan_speed").is_file()
            caps.battery_limiter = (self.sense / "battery_limiter").is_file()
            caps.battery_calibration = (self.sense / "battery_calibration").is_file()
            caps.usb_charging = (self.sense / "usb_charging").is_file()
            caps.backlight_timeout = (self.sense / "backlight_timeout").is_file()
            caps.lcd_override = (self.sense / "lcd_override").is_file()
            caps.boot_animation = (self.sense / "boot_animation_sound").is_file()
        if self.hwmon is not None:
            caps.pwm = (self.hwmon / "pwm1").is_file()
        caps.rgb_keyboard = bool(
            self.kb and (self.kb / "four_zone_mode").is_file()
        )
        return caps

    def snapshot(self) -> Snapshot:
        snap = Snapshot(caps=self.caps)
        if PROFILE_FILE.exists():
            snap.profile = _read(PROFILE_FILE)
        choices = _read(PROFILE_CHOICES)
        if choices:
            snap.profile_choices = choices.split()

        if self.sense is not None:
            raw = _read(self.sense / "fan_speed")
            if raw is not None:
                snap.fan_auto, snap.fan_cpu_pct, snap.fan_gpu_pct = _parse_fan_speed(raw)
            snap.battery_limiter = _as_bool(_read(self.sense / "battery_limiter"))
            snap.battery_calibration = _as_bool(
                _read(self.sense / "battery_calibration")
            )
            usb = _read(self.sense / "usb_charging")
            snap.usb_charging = int(usb) if usb and usb.isdigit() else None
            snap.backlight_timeout = _as_bool(_read(self.sense / "backlight_timeout"))
            snap.lcd_override = _as_bool(_read(self.sense / "lcd_override"))
            snap.boot_animation = _as_bool(_read(self.sense / "boot_animation_sound"))

        if self.hwmon is not None:
            snap.fan_cpu_rpm = _as_int(_read(self.hwmon / "fan1_input"))
            snap.fan_gpu_rpm = _as_int(_read(self.hwmon / "fan2_input"))
            if snap.fan_cpu_pct is None and (self.hwmon / "pwm1").is_file():
                pwm1 = _as_int(_read(self.hwmon / "pwm1"))
                pwm2 = _as_int(_read(self.hwmon / "pwm2"))
                enable = _read(self.hwmon / "pwm1_enable")
                snap.fan_auto = enable in {None, "2"}
                if pwm1 is not None:
                    snap.fan_cpu_pct = round(pwm1 * 100 / 255)
                if pwm2 is not None:
                    snap.fan_gpu_pct = round(pwm2 * 100 / 255)

        if self.kb is not None:
            snap.rgb_per_zone = _read(self.kb / "per_zone_mode")
            snap.rgb_mode = _read(self.kb / "four_zone_mode")
        return snap

    def set_profile(self, firmware_value: str) -> None:
        self.write(PROFILE_FILE, firmware_value)

    def set_fans(self, cpu_pct: int, gpu_pct: int, auto: bool) -> None:
        if auto:
            if self.caps.fan_speed and self.sense is not None:
                # Linuwu requires the CPU,GPU pair. A lone "0" returns EINVAL.
                self.write(self.sense / "fan_speed", "0,0")
            elif self.hwmon is not None:
                self.write(self.hwmon / "pwm1_enable", "2")
                if (self.hwmon / "pwm2_enable").is_file():
                    self.write(self.hwmon / "pwm2_enable", "2")
            return

        cpu_pct = max(1, min(100, int(cpu_pct)))
        gpu_pct = max(1, min(100, int(gpu_pct)))
        if self.caps.fan_speed and self.sense is not None:
            self.write(self.sense / "fan_speed", f"{cpu_pct},{gpu_pct}")
        elif self.hwmon is not None:
            self.write(self.hwmon / "pwm1_enable", "1")
            self.write(self.hwmon / "pwm1", str(round(cpu_pct * 255 / 100)))
            if (self.hwmon / "pwm2").is_file():
                self.write(self.hwmon / "pwm2_enable", "1")
                self.write(self.hwmon / "pwm2", str(round(gpu_pct * 255 / 100)))

    def set_flag(self, name: str, enabled: bool) -> None:
        if self.sense is None:
            raise RuntimeError("nitro_sense sysfs missing — install the driver")
        path = self.sense / name
        if not path.is_file():
            raise RuntimeError(f"this chassis does not expose {name}")
        self.write(path, "1" if enabled else "0")

    def set_usb_charging(self, value: int) -> None:
        if self.sense is None:
            raise RuntimeError("nitro_sense sysfs missing — install the driver")
        if value not in {0, 10, 20, 30}:
            raise ValueError("USB charging: 0, 10, 20 or 30")
        self.write(self.sense / "usb_charging", str(value))

    def set_rgb_mode(
        self,
        mode: int,
        speed: int,
        brightness: int,
        direction: int,
        red: int,
        green: int,
        blue: int,
    ) -> None:
        if self.kb is None:
            raise RuntimeError("4-zone RGB keyboard is not available on this chassis")
        payload = f"{mode},{speed},{brightness},{direction},{red},{green},{blue}"
        self.write(self.kb / "four_zone_mode", payload)

    def write(self, path: Path, value: str) -> None:
        path = path.resolve()
        try:
            path.write_text(value + "\n", encoding="utf-8")
            return
        except PermissionError:
            pass
        except OSError as exc:
            if getattr(exc, "errno", None) != 13:
                raise
        helper = pkexec_helper()
        pkexec = shutil.which("pkexec")
        if helper is None or pkexec is None:
            raise PermissionError(
                f"no permission to write {path} — run setup.sh"
            )
        result = subprocess.run(
            [pkexec, str(helper), "write", str(path), value],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(err or f"helper failed ({result.returncode})")


def _parse_fan_speed(raw: str) -> tuple[bool, int | None, int | None]:
    raw = raw.replace(" ", "")
    if raw in {"0", "0,0"}:
        return True, None, None
    if "," in raw:
        left, right = raw.split(",", 1)
        try:
            return False, int(left), int(right)
        except ValueError:
            return True, None, None
    try:
        value = int(raw)
    except ValueError:
        return True, None, None
    return (value == 0), (None if value == 0 else value), (
        None if value == 0 else value
    )


def _as_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    raw = raw.strip()
    if raw in {"0", "1"}:
        return raw == "1"
    return None


def _as_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw.split()[0])
    except (ValueError, IndexError):
        return None
