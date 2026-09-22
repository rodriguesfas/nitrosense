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


def _f(raw: str) -> float | None:
    raw = raw.strip().replace("[N/A]", "").replace("W", "")
    if not raw or "deprecated" in raw.lower():
        return None
    try:
        return float(raw)
    except ValueError:
        return None


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
    if default is None and maximum is None:
        return None
    return TgpInfo(
        name=parts[0] or None,
        current_w=int(round(cur)) if cur is not None else None,
        default_w=int(round(default)) if default is not None else None,
        min_w=int(round(minimum)) if minimum is not None else None,
        max_w=int(round(maximum)) if maximum is not None else None,
    )


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
