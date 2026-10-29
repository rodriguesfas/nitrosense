"""Named performance profiles with apply + verify (requested vs effective)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nitrosense.audit import record
from nitrosense.cpu import read_cpu_power, set_pl1
from nitrosense.gpu import powerd_active, set_tgp
from nitrosense.hardware import NITRO_MODES, Hardware
from nitrosense.history import capture as capture_snapshot, push as push_undo
from nitrosense.tuning import read_tuning, set_epp, set_governor, set_ppd

STATE_PATH = Path.home() / ".config" / "nitrosense" / "profile_state.json"
SAFE_ID = "safe"


@dataclass(frozen=True)
class Profile:
    id: str
    label_key: str
    mode: str  # quiet | balanced | performance
    fans: str  # auto | max
    pl1_w: int
    gpu_boost: bool
    governor: str
    epp: str
    ppd: str  # performance | balanced | power-saver
    notes_key: str


PROFILES: tuple[Profile, ...] = (
    Profile(
        id="eco",
        label_key="prof.eco",
        mode="quiet",
        fans="auto",
        pl1_w=45,
        gpu_boost=False,
        governor="schedutil",
        epp="balance_power",
        ppd="power-saver",
        notes_key="prof.eco_hint",
    ),
    Profile(
        id="daily",
        label_key="prof.daily",
        mode="balanced",
        fans="auto",
        pl1_w=55,
        gpu_boost=False,
        governor="schedutil",
        epp="balance_performance",
        ppd="balanced",
        notes_key="prof.daily_hint",
    ),
    Profile(
        id="compile",
        label_key="prof.compile",
        mode="performance",
        fans="auto",
        pl1_w=115,
        gpu_boost=False,
        governor="performance",
        epp="performance",
        ppd="performance",
        notes_key="prof.compile_hint",
    ),
    Profile(
        id="ai",
        label_key="prof.ai",
        mode="performance",
        fans="auto",
        pl1_w=95,
        gpu_boost=True,
        governor="schedutil",
        epp="balance_performance",
        ppd="performance",
        notes_key="prof.ai_hint",
    ),
    Profile(
        id="sustained",
        label_key="prof.sustained",
        mode="performance",
        fans="max",
        pl1_w=95,
        gpu_boost=True,
        governor="performance",
        epp="performance",
        ppd="performance",
        notes_key="prof.sustained_hint",
    ),
    Profile(
        id=SAFE_ID,
        label_key="prof.safe",
        mode="balanced",
        fans="auto",
        pl1_w=55,
        gpu_boost=False,
        governor="schedutil",
        epp="balance_performance",
        ppd="balanced",
        notes_key="prof.safe_hint",
    ),
)


@dataclass
class CheckItem:
    name: str
    requested: Any
    effective: Any
    ok: bool


@dataclass
class ApplyResult:
    profile_id: str
    checks: list[CheckItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and all(c.ok for c in self.checks)


def get_profile(profile_id: str) -> Profile:
    for p in PROFILES:
        if p.id == profile_id:
            return p
    raise KeyError(profile_id)


def saved_profile_id() -> str | None:
    if not STATE_PATH.is_file():
        return None
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    pid = raw.get("profile_id")
    return str(pid) if pid else None


def _save_state(profile_id: str, result: ApplyResult) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile_id": profile_id,
        "ok": result.ok,
        "checks": [asdict(c) for c in result.checks],
        "errors": result.errors,
    }
    STATE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def apply_profile(
    profile_id: str,
    hw: Hardware | None = None,
    *,
    record_undo: bool = True,
) -> ApplyResult:
    profile = get_profile(profile_id)
    hw = hw or Hardware()
    hw.refresh_paths()
    if record_undo:
        try:
            push_undo(capture_snapshot(hw, profile_id=saved_profile_id()))
        except Exception:  # noqa: BLE001
            pass
    result = ApplyResult(profile_id=profile_id)
    fw = next(item[2] for item in NITRO_MODES if item[0] == profile.mode)

    try:
        hw.set_profile(fw)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"mode: {exc}")

    try:
        if profile.fans == "max":
            hw.set_fans(100, 100, False)
        else:
            hw.set_fans(0, 0, True)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"fans: {exc}")

    try:
        set_pl1(profile.pl1_w, persist=True)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"pl1: {exc}")

    try:
        # 75 unlocks Dynamic Boost; 60 is the SKU default ceiling path
        set_tgp(75 if profile.gpu_boost else 60, persist=True)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"gpu: {exc}")

    try:
        set_governor(profile.governor)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"governor: {exc}")

    try:
        set_epp(profile.epp)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"epp: {exc}")

    try:
        set_ppd(profile.ppd)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"ppd: {exc}")

    result.checks = verify(profile, hw)
    _save_state(profile_id, result)
    record(
        "profile_apply",
        profile=profile_id,
        ok=result.ok,
        errors=result.errors or None,
    )
    return result


def verify(profile: Profile, hw: Hardware | None = None) -> list[CheckItem]:
    hw = hw or Hardware()
    hw.refresh_paths()
    snap = hw.snapshot()
    fw = next(item[2] for item in NITRO_MODES if item[0] == profile.mode)
    cpu = read_cpu_power()
    tuning = read_tuning()
    fans_auto = bool(snap.fan_auto)
    want_auto = profile.fans == "auto"
    pl1 = cpu.pl1_w if cpu else None
    checks = [
        CheckItem("mode", fw, snap.profile, snap.profile == fw),
        CheckItem(
            "fans",
            "auto" if want_auto else "max",
            "auto" if fans_auto else "manual",
            fans_auto == want_auto
            or (
                not want_auto
                and (snap.fan_cpu_pct or 0) >= 99
                and (snap.fan_gpu_pct or 0) >= 99
            ),
        ),
        CheckItem(
            "pl1_w",
            profile.pl1_w,
            pl1,
            pl1 is not None and abs(pl1 - profile.pl1_w) <= 5,
        ),
        CheckItem(
            "gpu_boost",
            profile.gpu_boost,
            powerd_active(),
            powerd_active() is profile.gpu_boost,
        ),
        CheckItem(
            "governor",
            profile.governor,
            tuning.governor,
            tuning.governor == profile.governor,
        ),
        CheckItem(
            "epp",
            profile.epp,
            tuning.epp,
            tuning.epp == profile.epp,
        ),
        CheckItem(
            "ppd",
            profile.ppd,
            tuning.ppd,
            tuning.ppd == profile.ppd,
        ),
    ]
    return checks


def restore_safe(hw: Hardware | None = None) -> ApplyResult:
    return apply_profile(SAFE_ID, hw)
