"""NVIDIA TGP (Total Graphics Power) via nvidia-smi. Needs pkexec to change."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

from nitrosense.hardware import pkexec_helper
from nitrosense.i18n import load_ui, save_ui


@dataclass
class TgpInfo:
    name: str | None = None
    current_w: int | None = None
    default_w: int | None = None
    min_w: int | None = None
    max_w: int | None = None


@dataclass
class PowerReadings:
    """Live watts from `nvidia-smi -q -d POWER` (GPU Power Readings)."""

    draw_w: float | None = None
    current_w: float | None = None
    default_w: float | None = None
    min_w: float | None = None
    max_w: float | None = None


_POWER_FIELDS = (
    ("Instantaneous Power Draw", "draw_w"),
    ("Current Power Limit", "current_w"),
    ("Default Power Limit", "default_w"),
    ("Min Power Limit", "min_w"),
    ("Max Power Limit", "max_w"),
)
_POWER_END = ("GPU Memory Power Readings", "Module Power Readings", "Power Smoothing")


def _f(raw: str) -> float | None:
    raw = raw.strip().replace("[N/A]", "").replace("W", "")
    if not raw or "deprecated" in raw.lower() or raw.upper() == "N/A":
        return None
    if raw.lower() == "not found":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _round_w(value: float | None) -> int | None:
    return int(round(value)) if value is not None else None


def parse_smi_power_readings(text: str) -> PowerReadings | None:
    """First GPU Power Readings block. CSV power.limit is [N/A] on 595-open."""
    start = text.find("GPU Power Readings")
    if start < 0:
        return None
    rest = text[start:]
    end = len(rest)
    for marker in _POWER_END:
        at = rest.find(marker, 20)
        if at > 0:
            end = min(end, at)
    block = rest[:end]
    found = False
    readings = PowerReadings()
    for line in block.splitlines():
        if ":" not in line:
            continue
        label, raw = line.split(":", 1)
        label = " ".join(label.split())
        for prefix, field in _POWER_FIELDS:
            if label == prefix:
                setattr(readings, field, _f(raw))
                found = True
                break
    if not found:
        return None
    if (
        readings.current_w is None
        and readings.default_w is None
        and readings.max_w is None
    ):
        return None
    return readings


def smi_power_readings() -> PowerReadings | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "-q", "-d", "POWER"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return parse_smi_power_readings(result.stdout)


def _overlay_power(info: TgpInfo, readings: PowerReadings | None) -> TgpInfo:
    if readings is None:
        return info
    if readings.current_w is not None:
        info.current_w = _round_w(readings.current_w)
    if info.default_w is None:
        info.default_w = _round_w(readings.default_w)
    if info.min_w is None:
        info.min_w = _round_w(readings.min_w)
    if info.max_w is None:
        info.max_w = _round_w(readings.max_w)
    return info


def saved_tgp() -> int | None:
    raw = load_ui().get("tgp_watts")
    try:
        watts = int(raw)
    except (TypeError, ValueError):
        return None
    return watts if watts > 0 else None


def save_tgp_choice(watts: int) -> None:
    save_ui(tgp_watts=int(watts))


def powerd_active() -> bool:
    try:
        return (
            subprocess.run(
                ["systemctl", "is-active", "--quiet", "nvidia-powerd"],
                check=False,
                timeout=1,
            ).returncode
            == 0
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def read_tgp() -> TgpInfo | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,enforced.power.limit,power.default_limit,"
                "power.min_limit,power.max_limit",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    line = result.stdout.strip().splitlines()[0]
    parts = [p.strip() for p in line.split(",")]
    if not parts:
        return None
    cur = _f(parts[1]) if len(parts) > 1 else None
    default = _f(parts[2]) if len(parts) > 2 else None
    minimum = _f(parts[3]) if len(parts) > 3 else None
    maximum = _f(parts[4]) if len(parts) > 4 else None
    readings = smi_power_readings()
    if default is None and maximum is None:
        if readings is None or (readings.default_w is None and readings.max_w is None):
            return None
    info = TgpInfo(
        name=parts[0] or None,
        current_w=_round_w(cur),
        default_w=_round_w(default),
        min_w=_round_w(minimum),
        max_w=_round_w(maximum),
    )
    return _overlay_power(info, readings)


def set_tgp(watts: int, *, persist: bool = True) -> None:
    info = read_tgp()
    lo = info.min_w if info and info.min_w is not None else 5
    hi = info.max_w if info and info.max_w is not None else 75
    watts = max(lo, min(hi, int(watts)))
    try:
        result = subprocess.run(
            ["nvidia-smi", "-pl", str(watts)],
            check=False,
            capture_output=True,
            text=True,
            timeout=4,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("nvidia-smi is not available") from exc
    smi_out = ((result.stdout or "") + (result.stderr or "")).lower()
    pl_ok = result.returncode == 0 and "not supported" not in smi_out
    if not pl_ok:
        helper = pkexec_helper()
        pkexec = shutil.which("pkexec")
        if helper is None or pkexec is None:
            raise PermissionError("TGP needs pkexec / nitrosense-helper")
        # pkexec 124 has no --action-id; polkit picks org.alfred.nitrosense.tgp
        # via exec.path + argv1=tgp (allow_active=yes, no password).
        privileged = subprocess.run(
            [pkexec, str(helper), "tgp", str(watts)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if privileged.returncode != 0:
            err = (privileged.stderr or privileged.stdout or result.stderr or "").strip()
            raise RuntimeError(err or "could not set GPU power limit")
    if persist:
        save_tgp_choice(watts)


def restore_saved_tgp() -> bool:
    want = saved_tgp()
    if want is None:
        return False
    info = read_tgp()
    if info is None:
        return False
    if info.current_w is not None and int(info.current_w) == int(want):
        return False
    hi = info.max_w if info.max_w is not None else 75
    if want >= hi - 1 and powerd_active():
        return False
    set_tgp(want, persist=False)
    return True


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        restore_saved_tgp()
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
