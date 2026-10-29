"""CPU governor / EPP and power-profiles-daemon coordination."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from nitrosense.audit import record
from nitrosense.hardware import pkexec_helper

CPU_ROOT = Path("/sys/devices/system/cpu")
EPP_SAFE = ("default", "performance", "balance_performance", "balance_power", "power")
GOV_SAFE = (
    "conservative",
    "ondemand",
    "userspace",
    "powersave",
    "performance",
    "schedutil",
)


@dataclass
class TuningState:
    governor: str | None
    epp: str | None
    ppd: str | None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def read_tuning() -> TuningState:
    cpu0 = CPU_ROOT / "cpu0" / "cpufreq"
    return TuningState(
        governor=_read(cpu0 / "scaling_governor"),
        epp=_read(cpu0 / "energy_performance_preference"),
        ppd=_ppd_get(),
    )


def _ppd_get() -> str | None:
    exe = shutil.which("powerprofilesctl")
    if exe is None:
        return None
    result = subprocess.run(
        [exe, "get"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip() or None


def set_ppd(profile: str) -> None:
    """performance | balanced | power-saver — user-level, no pkexec."""
    if profile not in {"performance", "balanced", "power-saver"}:
        raise ValueError(f"unsupported power profile: {profile}")
    exe = shutil.which("powerprofilesctl")
    if exe is None:
        return
    result = subprocess.run(
        [exe, "set", profile],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(err or "powerprofilesctl failed")
    record("ppd", profile=profile, effective=_ppd_get())


def set_governor(name: str) -> None:
    if name not in GOV_SAFE:
        raise ValueError(f"governor not allowed: {name}")
    _helper("governor", name)
    record("governor", requested=name, effective=read_tuning().governor)


def set_epp(name: str) -> None:
    if name not in EPP_SAFE:
        raise ValueError(f"EPP not allowed: {name}")
    _helper("epp", name)
    record("epp", requested=name, effective=read_tuning().epp)


def _helper(cmd: str, value: str) -> None:
    helper = pkexec_helper()
    pkexec = shutil.which("pkexec")
    if helper is None or pkexec is None:
        raise PermissionError(f"{cmd} needs pkexec / nitrosense-helper")
    result = subprocess.run(
        [pkexec, str(helper), cmd, value],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(err or f"helper {cmd} failed ({result.returncode})")
