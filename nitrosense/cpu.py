"""Intel RAPL package PL1 (sustained CPU watts). Needs pkexec to change."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from nitrosense.hardware import pkexec_helper
from nitrosense.i18n import load_ui, save_ui

POWERCAP = Path("/sys/class/powercap")
CPUFREQ = Path("/sys/devices/system/cpu")


@dataclass
class CpuPower:
    pl1_w: int | None = None
    pl2_w: int | None = None
    tdp_w: int | None = None
    epp: str | None = None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _uw_to_w(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        uw = int(raw.split()[0])
    except ValueError:
        return None
    if uw <= 0:
        return None
    return int(round(uw / 1_000_000))


def package_rapl() -> Path | None:
    if not POWERCAP.is_dir():
        return None
    for path in sorted(POWERCAP.glob("intel-rapl:*")):
        if path.name.count(":") != 1:
            continue
        if _read(path / "name") == "package-0":
            return path
    return None


def read_cpu_power() -> CpuPower | None:
    pkg = package_rapl()
    if pkg is None:
        return None
    pl1 = _uw_to_w(_read(pkg / "constraint_0_power_limit_uw"))
    pl2 = _uw_to_w(_read(pkg / "constraint_1_power_limit_uw"))
    tdp = _uw_to_w(_read(pkg / "constraint_0_max_power_uw"))
    if pl1 is None and pl2 is None:
        return None
    epp = _read(CPUFREQ / "cpu0" / "cpufreq" / "energy_performance_preference")
    return CpuPower(pl1_w=pl1, pl2_w=pl2, tdp_w=tdp, epp=epp)


def saved_cpu_pl1() -> int | None:
    raw = load_ui().get("cpu_pl1_watts")
    try:
        watts = int(raw)
    except (TypeError, ValueError):
        return None
    return watts if watts > 0 else None


def saved_cpu_default() -> int | None:
    raw = load_ui().get("cpu_default_w")
    try:
        watts = int(raw)
    except (TypeError, ValueError):
        return None
    return watts if watts > 0 else None


def cpu_unlocked(info: CpuPower | None) -> bool:
    if info is None or info.pl1_w is None or info.pl2_w is None:
        return False
    return info.pl1_w >= info.pl2_w - 5


def default_pl1(info: CpuPower) -> int:
    saved = saved_cpu_default()
    if saved is not None:
        return saved
    if info.tdp_w is not None and info.tdp_w > 0:
        if info.pl1_w is not None and not cpu_unlocked(info):
            return max(info.tdp_w, info.pl1_w)
        return info.tdp_w
    if info.pl1_w is not None:
        return info.pl1_w
    return 45


def boost_pl1(info: CpuPower) -> int:
    if info.pl2_w is not None and info.pl2_w > 0:
        return info.pl2_w
    return 115


def set_pl1(watts: int, *, persist: bool = True) -> None:
    info = read_cpu_power()
    lo = 15
    hi = boost_pl1(info) if info is not None else 115
    if info is not None and info.pl2_w is not None:
        hi = max(hi, info.pl2_w)
    watts = max(lo, min(hi, int(watts)))
    pkg = package_rapl()
    wrote = False
    if pkg is not None:
        path = pkg / "constraint_0_power_limit_uw"
        try:
            path.write_text(str(watts * 1_000_000) + "\n", encoding="utf-8")
            wrote = True
        except PermissionError:
            wrote = False
        except OSError as exc:
            if getattr(exc, "errno", None) != 13:
                raise
    if not wrote:
        helper = pkexec_helper()
        pkexec = shutil.which("pkexec")
        if helper is None or pkexec is None:
            raise PermissionError("CPU PL1 needs pkexec / nitrosense-helper")
        privileged = subprocess.run(
            [pkexec, str(helper), "cpu", str(watts)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if privileged.returncode != 0:
            err = (privileged.stderr or privileged.stdout or "").strip()
            raise RuntimeError(err or "could not set CPU power limit")
    if persist:
        save_ui(cpu_pl1_watts=int(watts))


def set_cpu_unlock(unlock: bool, *, persist: bool = True) -> None:
    info = read_cpu_power()
    if info is None:
        raise RuntimeError("intel RAPL package-0 not found")
    if unlock:
        if saved_cpu_default() is None and info.pl1_w is not None and not cpu_unlocked(info):
            save_ui(cpu_default_w=int(info.pl1_w))
        watts = boost_pl1(info)
    else:
        watts = default_pl1(info)
    set_pl1(watts, persist=persist)


def restore_saved_cpu() -> bool:
    want = saved_cpu_pl1()
    if want is None:
        return False
    info = read_cpu_power()
    if info is None:
        return False
    if info.pl1_w is not None and int(info.pl1_w) == int(want):
        return False
    set_pl1(want, persist=False)
    return True


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        restore_saved_cpu()
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
