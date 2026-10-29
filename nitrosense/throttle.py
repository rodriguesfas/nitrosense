"""Detect thermal / power clipping from sysfs and nvidia-smi."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from nitrosense.cpu import read_cpu_power
from nitrosense.gpu import smi_power_readings


@dataclass
class ThrottleSnapshot:
    cpu_pl1_w: int | None = None
    cpu_pl2_w: int | None = None
    cpu_tdp_w: int | None = None
    cpu_freq_mhz: float | None = None
    cpu_freq_max_mhz: float | None = None
    gpu_live_w: float | None = None
    gpu_default_w: float | None = None
    gpu_temp_c: int | None = None
    acer_temp_c: list[int] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def throttling(self) -> bool:
        return bool(self.reasons)


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def _cpu_freq() -> tuple[float | None, float | None]:
    cur = _read_int(Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"))
    mx = _read_int(Path("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq"))
    return (
        None if cur is None else cur / 1000.0,
        None if mx is None else mx / 1000.0,
    )


def _acer_temps() -> list[int]:
    out: list[int] = []
    base = Path("/sys/class/hwmon")
    if not base.is_dir():
        return out
    for hwmon in base.glob("hwmon*"):
        try:
            name = (hwmon / "name").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if name != "acer":
            continue
        for temp in sorted(hwmon.glob("temp*_input")):
            raw = _read_int(temp)
            if raw is not None:
                out.append(raw // 1000)
    return out


def _gpu_temp() -> int | None:
    smi = shutil.which("nvidia-smi")
    if smi is None:
        return None
    result = subprocess.run(
        [smi, "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        return None
    try:
        return int((result.stdout or "").strip().splitlines()[0])
    except (ValueError, IndexError):
        return None


def probe(*, hot_c: int = 90) -> ThrottleSnapshot:
    snap = ThrottleSnapshot()
    cpu = read_cpu_power()
    if cpu is not None:
        snap.cpu_pl1_w = cpu.pl1_w
        snap.cpu_pl2_w = cpu.pl2_w
        snap.cpu_tdp_w = cpu.tdp_w
    snap.cpu_freq_mhz, snap.cpu_freq_max_mhz = _cpu_freq()
    readings = smi_power_readings()
    if readings is not None and readings.current_limit_w is not None:
        snap.gpu_live_w = readings.current_limit_w
        snap.gpu_default_w = readings.default_limit_w
    snap.gpu_temp_c = _gpu_temp()
    snap.acer_temp_c = _acer_temps()

    if (
        snap.cpu_pl1_w is not None
        and snap.cpu_pl2_w is not None
        and snap.cpu_pl1_w + 5 < snap.cpu_pl2_w
        and snap.cpu_tdp_w is not None
        and snap.cpu_pl1_w <= snap.cpu_tdp_w + 5
    ):
        # Cap near TDP while PL2 is much higher → sustained power limit active
        pass
    if (
        snap.cpu_freq_mhz is not None
        and snap.cpu_freq_max_mhz is not None
        and snap.cpu_freq_max_mhz > 0
        and snap.cpu_freq_mhz < snap.cpu_freq_max_mhz * 0.55
    ):
        # Only flag when also hot — idle clocks are normally low
        hottest = max(snap.acer_temp_c) if snap.acer_temp_c else snap.gpu_temp_c
        if hottest is not None and hottest >= hot_c - 5:
            snap.reasons.append("cpu_freq_thermal")

    hottest = max(snap.acer_temp_c) if snap.acer_temp_c else None
    if hottest is not None and hottest >= hot_c:
        snap.reasons.append(f"acer_hot_{hottest}c")
    if snap.gpu_temp_c is not None and snap.gpu_temp_c >= hot_c:
        snap.reasons.append(f"gpu_hot_{snap.gpu_temp_c}c")

    if (
        snap.gpu_live_w is not None
        and snap.gpu_default_w is not None
        and snap.gpu_live_w + 0.5 < snap.gpu_default_w
    ):
        snap.reasons.append("gpu_power_limit_below_default")

    return snap
