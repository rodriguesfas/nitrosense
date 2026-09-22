"""Leituras que não dependem do Linuwu (coretemp, NVIDIA, bateria, load)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

_cpu_prev: tuple[int, int] | None = None


@dataclass
class Sensors:
    cpu_temp: float | None = None
    cpu_load: float | None = None
    cpu_name: str | None = None
    gpu_temp: float | None = None
    gpu_load: float | None = None
    gpu_power_w: float | None = None
    gpu_power_limit_w: float | None = None
    gpu_name: str | None = None
    battery_pct: int | None = None
    battery_status: str | None = None
    on_ac: bool | None = None
    ram_total_gb: float | None = None
    ram_used_gb: float | None = None
    ram_pct: float | None = None


def read_sensors() -> Sensors:
    out = Sensors()
    out.cpu_temp = _cpu_package_temp()
    out.cpu_load = _cpu_load()
    out.cpu_name = _cpu_name()
    _nvidia(out)
    _battery(out)
    _ram(out)
    return out


def _cpu_package_temp() -> float | None:
    base = Path("/sys/class/hwmon")
    if not base.is_dir():
        return None
    for hwmon in base.glob("hwmon*"):
        if _read(hwmon / "name") != "coretemp":
            continue
        package = None
        hottest = None
        for label in hwmon.glob("temp*_label"):
            name = _read(label) or ""
            raw = _read(label.with_name(label.name.replace("_label", "_input")))
            if raw is None:
                continue
            try:
                celsius = int(raw) / 1000.0
            except ValueError:
                continue
            if "Package" in name:
                package = celsius
            hottest = celsius if hottest is None else max(hottest, celsius)
        return package if package is not None else hottest
    return None


def _cpu_name() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def _cpu_load() -> float | None:
    global _cpu_prev
    try:
        line = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
    except OSError:
        return None
    parts = line.split()
    if len(parts) < 5 or parts[0] != "cpu":
        return None
    nums = [int(x) for x in parts[1:]]
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    total = sum(nums)
    prev = _cpu_prev
    _cpu_prev = (idle, total)
    if prev is None:
        return None
    didle = idle - prev[0]
    dtotal = total - prev[1]
    if dtotal <= 0:
        return None
    return max(0.0, min(100.0, (1.0 - didle / dtotal) * 100.0))


def _nvidia(out: Sensors) -> None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu,utilization.gpu,power.draw,power.limit",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return
    if result.returncode != 0 or not result.stdout.strip():
        return
    line = result.stdout.strip().splitlines()[0]
    parts = [p.strip() for p in line.split(",")]
    if not parts:
        return
    out.gpu_name = parts[0] or None
    if len(parts) > 1:
        out.gpu_temp = _f(parts[1])
    if len(parts) > 2:
        out.gpu_load = _f(parts[2])
    if len(parts) > 3:
        out.gpu_power_w = _f(parts[3])
    if len(parts) > 4:
        out.gpu_power_limit_w = _f(parts[4])


def _battery(out: Sensors) -> None:
    bat = Path("/sys/class/power_supply/BAT1")
    if not bat.is_dir():
        bats = list(Path("/sys/class/power_supply").glob("BAT*"))
        bat = bats[0] if bats else None
    if bat is not None:
        cap = _read(bat / "capacity")
        out.battery_pct = int(cap) if cap and cap.isdigit() else None
        out.battery_status = _read(bat / "status")
    ac = Path("/sys/class/power_supply/ACAD")
    if not ac.is_dir():
        acs = [
            p
            for p in Path("/sys/class/power_supply").iterdir()
            if p.name.startswith(("AC", "ADP"))
        ]
        ac = acs[0] if acs else None
    if ac is not None:
        online = _read(ac / "online")
        out.on_ac = online == "1"


def _ram(out: Sensors) -> None:
    info: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            key, raw = line.split(":", 1)
            num = raw.strip().split()[0]
            if num.isdigit():
                info[key] = int(num)
    except OSError:
        return
    total = info.get("MemTotal")
    available = info.get("MemAvailable")
    if not total:
        return
    out.ram_total_gb = total / (1024 * 1024)
    if available is not None:
        used = max(0, total - available)
        out.ram_used_gb = used / (1024 * 1024)
        out.ram_pct = max(0.0, min(100.0, used * 100.0 / total))


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _f(raw: str) -> float | None:
    try:
        return float(raw)
    except ValueError:
        return None
