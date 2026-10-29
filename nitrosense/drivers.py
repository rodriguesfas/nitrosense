"""Kernel-module health for Linuwu Sense and NVIDIA (post-upgrade checks)."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DriverHealth:
    kernel: str
    linuwu_ko: bool
    linuwu_loaded: bool
    platform_profile: bool
    nvidia_ko: bool
    nvidia_loaded: bool
    nvidia_smi_ok: bool
    notes: list[str]


def _ko_exists(name: str) -> bool:
    kver = os.uname().release
    roots = [
        Path(f"/lib/modules/{kver}/kernel/drivers/platform/x86/{name}.ko"),
        Path(f"/lib/modules/{kver}/kernel/nvidia-595-open/{name}.ko"),
        Path(f"/lib/modules/{kver}/updates/dkms/{name}.ko"),
    ]
    # Compressed variants
    for root in list(roots):
        roots.extend(
            [
                Path(str(root) + ".zst"),
                Path(str(root) + ".xz"),
            ]
        )
    if name == "nvidia":
        roots.extend(
            Path(f"/lib/modules/{kver}").glob(f"**/nvidia.ko*")
        )
    return any(p.is_file() for p in roots)


def _module_loaded(name: str) -> bool:
    try:
        text = Path("/proc/modules").read_text(encoding="utf-8")
    except OSError:
        return False
    return any(line.split()[0] == name for line in text.splitlines() if line)


def _smi_ok() -> bool:
    smi = shutil.which("nvidia-smi")
    if smi is None:
        return False
    result = subprocess.run(
        [smi, "-L"],
        check=False,
        capture_output=True,
        text=True,
        timeout=8,
    )
    return result.returncode == 0 and "GPU" in (result.stdout or "")


def probe() -> DriverHealth:
    kver = os.uname().release
    notes: list[str] = []
    linuwu_ko = _ko_exists("linuwu_sense")
    linuwu_loaded = Path("/sys/module/linuwu_sense").exists() or _module_loaded(
        "linuwu_sense"
    )
    profile = Path("/sys/firmware/acpi/platform_profile").is_file()
    nvidia_ko = _ko_exists("nvidia")
    nvidia_loaded = _module_loaded("nvidia")
    smi = _smi_ok()

    if not linuwu_ko:
        notes.append(
            f"Linuwu Sense .ko missing for {kver} — SETTINGS → Install Linuwu driver"
        )
    elif not linuwu_loaded:
        notes.append("Linuwu Sense built but not loaded — reboot not required; modprobe or reinstall")
    if not profile and linuwu_loaded:
        notes.append("platform_profile missing despite Linuwu — check Acer WMI")
    if not nvidia_ko:
        notes.append(
            f"NVIDIA modules missing for {kver} — install linux-modules-nvidia-*-{kver}"
        )
    elif not nvidia_loaded:
        notes.append("NVIDIA .ko present but not loaded — modprobe nvidia (no reboot needed)")
    elif not smi:
        notes.append("nvidia module loaded but nvidia-smi failed")

    return DriverHealth(
        kernel=kver,
        linuwu_ko=linuwu_ko,
        linuwu_loaded=linuwu_loaded,
        platform_profile=profile,
        nvidia_ko=nvidia_ko,
        nvidia_loaded=nvidia_loaded,
        nvidia_smi_ok=smi,
        notes=notes,
    )


def summary_line(health: DriverHealth | None = None) -> str:
    h = health or probe()
    parts = [
        f"kernel {h.kernel}",
        "Linuwu OK" if h.linuwu_loaded and h.platform_profile else "Linuwu FAIL",
        "NVIDIA OK" if h.nvidia_smi_ok else "NVIDIA FAIL",
    ]
    return " · ".join(parts)
