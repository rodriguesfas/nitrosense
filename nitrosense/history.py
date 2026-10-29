"""Undo stack for performance profile applications."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from nitrosense.audit import record
from nitrosense.cpu import read_cpu_power
from nitrosense.gpu import powerd_active
from nitrosense.hardware import Hardware
from nitrosense.tuning import read_tuning

STACK_PATH = Path.home() / ".config" / "nitrosense" / "undo_stack.json"
MAX_DEPTH = 20


@dataclass
class Snapshot:
    profile_id: str | None
    mode_fw: str | None
    fans: str
    fan_cpu: int | None
    fan_gpu: int | None
    pl1_w: int | None
    gpu_boost: bool
    governor: str | None
    epp: str | None
    ppd: str | None


def capture(hw: Hardware | None = None, *, profile_id: str | None = None) -> Snapshot:
    hw = hw or Hardware()
    hw.refresh_paths()
    snap = hw.snapshot()
    cpu = read_cpu_power()
    tuning = read_tuning()
    fans = "auto" if snap.fan_auto else "custom"
    if (
        not snap.fan_auto
        and (snap.fan_cpu_pct or 0) >= 99
        and (snap.fan_gpu_pct or 0) >= 99
    ):
        fans = "max"
    return Snapshot(
        profile_id=profile_id,
        mode_fw=snap.profile,
        fans=fans,
        fan_cpu=snap.fan_cpu_pct,
        fan_gpu=snap.fan_gpu_pct,
        pl1_w=cpu.pl1_w if cpu else None,
        gpu_boost=powerd_active(),
        governor=tuning.governor,
        epp=tuning.epp,
        ppd=tuning.ppd,
    )


def push(snapshot: Snapshot) -> None:
    stack = _load()
    stack.append(asdict(snapshot))
    _save(stack[-MAX_DEPTH:])
    record("undo_push", profile_id=snapshot.profile_id, depth=len(stack))


def depth() -> int:
    return len(_load())


def undo(hw: Hardware | None = None) -> Snapshot | None:
    """Pop and re-apply the previous snapshot. Returns the restored snapshot."""
    from nitrosense.cpu import set_pl1
    from nitrosense.gpu import set_tgp
    from nitrosense.tuning import set_epp, set_governor, set_ppd

    stack = _load()
    if not stack:
        return None
    raw = stack.pop()
    _save(stack)
    snap = Snapshot(**raw)
    hw = hw or Hardware()
    hw.refresh_paths()
    if snap.mode_fw:
        try:
            hw.set_profile(snap.mode_fw)
        except Exception:  # noqa: BLE001
            pass
    try:
        if snap.fans == "auto":
            hw.set_fans(0, 0, True)
        elif snap.fans == "max":
            hw.set_fans(100, 100, False)
        else:
            hw.set_fans(snap.fan_cpu or 50, snap.fan_gpu or 50, False)
    except Exception:  # noqa: BLE001
        pass
    if snap.pl1_w is not None:
        try:
            set_pl1(int(snap.pl1_w), persist=True)
        except Exception:  # noqa: BLE001
            pass
    try:
        set_tgp(75 if snap.gpu_boost else 60, persist=True)
    except Exception:  # noqa: BLE001
        pass
    if snap.governor:
        try:
            set_governor(snap.governor)
        except Exception:  # noqa: BLE001
            pass
    if snap.epp:
        try:
            set_epp(snap.epp)
        except Exception:  # noqa: BLE001
            pass
    if snap.ppd:
        try:
            set_ppd(snap.ppd)
        except Exception:  # noqa: BLE001
            pass
    record("undo_apply", profile_id=snap.profile_id, remaining=len(stack))
    return snap


def _load() -> list[dict[str, Any]]:
    if not STACK_PATH.is_file():
        return []
    try:
        raw = json.loads(STACK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list(raw) if isinstance(raw, list) else []


def _save(stack: list[dict[str, Any]]) -> None:
    STACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    STACK_PATH.write_text(json.dumps(stack, indent=2) + "\n", encoding="utf-8")
