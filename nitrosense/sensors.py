"""Sensor reads that do not depend on Linuwu (coretemp, NVIDIA, RAM, swap, net, disks, processes)."""

from __future__ import annotations

import fcntl
import os
import socket
import struct
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

_cpu_prev: tuple[int, int] | None = None
_core_prev: dict[int, tuple[int, int]] = {}
_net_prev: tuple[str, int, int, float] | None = None
_disk_prev: dict[str, tuple[int, int, float]] = {}
_proc_prev: dict[int, int] = {}
_proc_total_prev: int | None = None

_SKIP_IFACE = {"lo", "docker0", "tailscale0"}
_SKIP_PREFIX = ("br-", "veth", "virbr", "docker", "tun", "tap", "wg", "vnet")
_SKIP_DISK = ("loop", "ram", "sr", "zram", "dm-", "md")


_intel_rc6: tuple[int, float] | None = None
_pci_pretty_cache: dict[str, str] = {}


@dataclass
class ProcInfo:
    pid: int
    name: str
    cpu_pct: float
    mem_mb: float


@dataclass
class GpuInfo:
    key: str
    vendor: str
    name: str
    temp: float | None = None
    load: float | None = None
    power_w: float | None = None
    power_limit_w: float | None = None
    power_default_w: float | None = None
    power_min_w: float | None = None
    power_max_w: float | None = None
    freq_mhz: float | None = None


@dataclass
class DiskInfo:
    name: str
    mount: str | None = None
    used_gb: float | None = None
    total_gb: float | None = None
    pct: float | None = None
    read_mbps: float | None = None
    write_mbps: float | None = None


@dataclass
class Sensors:
    cpu_temp: float | None = None
    cpu_load: float | None = None
    cpu_name: str | None = None
    cpu_freq_ghz: float | None = None
    cpu_cores: list[float] = field(default_factory=list)
    cpu_core_freq: list[float | None] = field(default_factory=list)
    cpu_core_ids: list[int] = field(default_factory=list)
    gpu_temp: float | None = None
    gpu_load: float | None = None
    gpu_power_w: float | None = None
    gpu_power_limit_w: float | None = None
    gpu_power_default_w: float | None = None
    gpu_power_max_w: float | None = None
    gpu_name: str | None = None
    gpus: list[GpuInfo] = field(default_factory=list)
    battery_pct: int | None = None
    battery_status: str | None = None
    battery_power_w: float | None = None
    battery_cycles: int | None = None
    battery_energy_wh: float | None = None
    battery_full_wh: float | None = None
    on_ac: bool | None = None
    ram_total_gb: float | None = None
    ram_used_gb: float | None = None
    ram_pct: float | None = None
    ram_available_gb: float | None = None
    ram_cached_gb: float | None = None
    swap_total_gb: float | None = None
    swap_used_gb: float | None = None
    swap_pct: float | None = None
    net_iface: str | None = None
    net_kind: str | None = None
    net_ipv4: str | None = None
    net_rx_mbps: float | None = None
    net_tx_mbps: float | None = None
    net_link_mbps: float | None = None
    net_pct: float | None = None
    disks: list[DiskInfo] = field(default_factory=list)
    processes: list[ProcInfo] = field(default_factory=list)


def read_sensors() -> Sensors:
    out = Sensors()
    out.cpu_temp = _cpu_package_temp()
    out.cpu_name = _cpu_name()
    _cpu(out)
    _gpus(out)
    _battery(out)
    _ram(out)
    _swap(out)
    _net(out)
    _disks(out)
    _processes(out)
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


def _cpu(out: Sensors) -> None:
    global _cpu_prev, _core_prev
    try:
        lines = Path("/proc/stat").read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    loads: dict[int, float] = {}
    next_cores: dict[int, tuple[int, int]] = {}
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        key = parts[0]
        if key != "cpu" and not key.startswith("cpu"):
            continue
        try:
            nums = [int(x) for x in parts[1:]]
        except ValueError:
            continue
        if len(nums) < 4:
            continue
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
        total = sum(nums)
        if key == "cpu":
            prev = _cpu_prev
            _cpu_prev = (idle, total)
            if prev is not None:
                dtotal = total - prev[1]
                if dtotal > 0:
                    out.cpu_load = max(
                        0.0, min(100.0, (1.0 - (idle - prev[0]) / dtotal) * 100.0)
                    )
            continue
        try:
            idx = int(key[3:])
        except ValueError:
            continue
        next_cores[idx] = (idle, total)
        prev = _core_prev.get(idx)
        if prev is not None:
            dtotal = total - prev[1]
            if dtotal > 0:
                loads[idx] = max(0.0, min(100.0, (1.0 - (idle - prev[0]) / dtotal) * 100.0))
            else:
                loads[idx] = 0.0
        else:
            loads[idx] = 0.0
    _core_prev = next_cores
    n = (max(next_cores) + 1) if next_cores else 0
    out.cpu_cores = [loads.get(i, 0.0) for i in range(n)]
    freqs: list[float | None] = []
    ids: list[int] = []
    live: list[float] = []
    base = Path("/sys/devices/system/cpu")
    for i in range(n):
        raw = _read(base / f"cpu{i}" / "cpufreq" / "scaling_cur_freq")
        if raw and raw.isdigit():
            ghz = int(raw) / 1_000_000.0
            freqs.append(ghz)
            live.append(ghz)
        else:
            freqs.append(None)
        cid = _read(base / f"cpu{i}" / "topology" / "core_id")
        ids.append(int(cid) if cid and cid.lstrip("-").isdigit() else i)
    out.cpu_core_freq = freqs
    out.cpu_core_ids = ids
    if live:
        out.cpu_freq_ghz = sum(live) / len(live)


def _gpus(out: Sensors) -> None:
    found: list[GpuInfo] = []
    found.extend(_nvidia_gpus())
    intel = _intel_gpu()
    if intel is not None:
        found.append(intel)
    found.sort(key=lambda g: (0 if g.vendor == "Intel" else 1, g.key))
    out.gpus = found
    primary = next((g for g in found if g.vendor == "NVIDIA"), None)
    if primary is None and found:
        primary = found[0]
    if primary is None:
        return
    out.gpu_name = primary.name
    out.gpu_temp = primary.temp
    out.gpu_load = primary.load
    out.gpu_power_w = primary.power_w
    out.gpu_power_limit_w = primary.power_limit_w
    out.gpu_power_default_w = primary.power_default_w
    out.gpu_power_max_w = primary.power_max_w


def _nvidia_gpus() -> list[GpuInfo]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,temperature.gpu,utilization.gpu,power.draw,"
                "enforced.power.limit,power.default_limit,power.min_limit,"
                "power.max_limit,clocks.gr",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    gpus: list[GpuInfo] = []
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if not parts:
            continue
        idx = parts[0] if parts[0].isdigit() else str(len(gpus))
        name = parts[1] if len(parts) > 1 else "NVIDIA GPU"
        gpus.append(
            GpuInfo(
                key=f"nvidia-{idx}",
                vendor="NVIDIA",
                name=name,
                temp=_f(parts[2]) if len(parts) > 2 else None,
                load=_f(parts[3]) if len(parts) > 3 else None,
                power_w=_f(parts[4]) if len(parts) > 4 else None,
                power_limit_w=_f(parts[5]) if len(parts) > 5 else None,
                power_default_w=_f(parts[6]) if len(parts) > 6 else None,
                power_min_w=_f(parts[7]) if len(parts) > 7 else None,
                power_max_w=_f(parts[8]) if len(parts) > 8 else None,
                freq_mhz=_f(parts[9]) if len(parts) > 9 else None,
            )
        )
    return gpus


def _intel_gpu() -> GpuInfo | None:
    global _intel_rc6
    card = _drm_card("0x8086")
    if card is None:
        return None
    gt = card / "gt" / "gt0"
    freq = _f(_read(gt / "rps_act_freq_mhz") or "") or _f(_read(gt / "rps_cur_freq_mhz") or "")
    rc6_raw = _read(gt / "rc6_residency_ms")
    load = None
    now = time.monotonic()
    if rc6_raw and rc6_raw.isdigit():
        rc6 = int(rc6_raw)
        prev = _intel_rc6
        _intel_rc6 = (rc6, now)
        if prev is not None:
            dt_ms = (now - prev[1]) * 1000.0
            if dt_ms > 0:
                idle = max(0.0, min(1.0, (rc6 - prev[0]) / dt_ms))
                load = max(0.0, min(100.0, (1.0 - idle) * 100.0))
    return GpuInfo(
        key="intel",
        vendor="Intel",
        name=_pci_pretty(card, "Intel UHD Graphics"),
        load=load,
        freq_mhz=freq,
        temp=_cpu_package_temp(),
    )


def _drm_card(vendor: str) -> Path | None:
    base = Path("/sys/class/drm")
    if not base.is_dir():
        return None
    for card in sorted(base.glob("card[0-9]")):
        if _read(card / "device" / "vendor") == vendor:
            return card
    return None


def _pci_pretty(card: Path, fallback: str) -> str:
    slot = None
    try:
        for line in (card / "device" / "uevent").read_text(encoding="utf-8").splitlines():
            if line.startswith("PCI_SLOT_NAME="):
                slot = line.split("=", 1)[1]
                break
    except OSError:
        slot = None
    if not slot:
        return fallback
    cached = _pci_pretty_cache.get(slot)
    if cached:
        return cached
    try:
        result = subprocess.run(
            ["lspci", "-s", slot],
            check=False,
            capture_output=True,
            text=True,
            timeout=0.4,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return fallback
    text = (result.stdout or "").strip()
    name = fallback
    if "[" in text and "]" in text:
        inside = text[text.rfind("[") + 1 : text.rfind("]")]
        if inside and not inside.startswith("8086"):
            name = inside if "Intel" in inside else f"Intel {inside}"
    elif ":" in text:
        name = text.split(":", 1)[1].strip()
    _pci_pretty_cache[slot] = name
    return name


def _battery(out: Sensors) -> None:
    bat = Path("/sys/class/power_supply/BAT1")
    if not bat.is_dir():
        bats = list(Path("/sys/class/power_supply").glob("BAT*"))
        bat = bats[0] if bats else None
    if bat is not None:
        cap = _read(bat / "capacity")
        out.battery_pct = int(cap) if cap and cap.isdigit() else None
        out.battery_status = _read(bat / "status")
        power = _read(bat / "power_now") or _read(bat / "current_now")
        voltage = _read(bat / "voltage_now")
        if power and power.lstrip("-").isdigit():
            # power_now is µW; current_now is µA
            val = int(power)
            if (bat / "power_now").is_file():
                out.battery_power_w = abs(val) / 1_000_000.0
            elif voltage and voltage.lstrip("-").isdigit():
                out.battery_power_w = abs(val) * int(voltage) / 1_000_000.0 / 1_000_000.0
        cycles = _read(bat / "cycle_count")
        if cycles and cycles.isdigit():
            out.battery_cycles = int(cycles)
        energy_now = _read(bat / "energy_now")
        energy_full = _read(bat / "energy_full")
        if energy_now and energy_now.lstrip("-").isdigit():
            out.battery_energy_wh = abs(int(energy_now)) / 1_000_000.0
        if energy_full and energy_full.lstrip("-").isdigit():
            out.battery_full_wh = abs(int(energy_full)) / 1_000_000.0
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
        out.ram_available_gb = available / (1024 * 1024)
    cached = (info.get("Cached") or 0) + (info.get("Buffers") or 0)
    out.ram_cached_gb = cached / (1024 * 1024)


def _swap(out: Sensors) -> None:
    info: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            key, raw = line.split(":", 1)
            num = raw.strip().split()[0]
            if num.isdigit() and key in {"SwapTotal", "SwapFree"}:
                info[key] = int(num)
    except OSError:
        return
    total = info.get("SwapTotal")
    free = info.get("SwapFree")
    if not total:
        out.swap_total_gb = 0.0
        out.swap_used_gb = 0.0
        out.swap_pct = 0.0
        return
    used = max(0, total - (free or 0))
    out.swap_total_gb = total / (1024 * 1024)
    out.swap_used_gb = used / (1024 * 1024)
    out.swap_pct = max(0.0, min(100.0, used * 100.0 / total))


def _skip_iface(name: str) -> bool:
    if name in _SKIP_IFACE:
        return True
    return name.startswith(_SKIP_PREFIX)


def _default_iface() -> str | None:
    try:
        lines = Path("/proc/net/route").read_text(encoding="utf-8").splitlines()[1:]
    except OSError:
        return None
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "00000000":
            name = parts[0]
            if not _skip_iface(name):
                return name
    return None


def _parse_netdev() -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    try:
        lines = Path("/proc/net/dev").read_text(encoding="utf-8").splitlines()[2:]
    except OSError:
        return out
    for line in lines:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        cols = rest.split()
        if len(cols) < 9:
            continue
        try:
            out[name] = (int(cols[0]), int(cols[8]))
        except ValueError:
            continue
    return out


def _link_mbps(name: str) -> float | None:
    raw = _read(Path(f"/sys/class/net/{name}/speed"))
    if raw is None:
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    if val <= 0 or val > 1_000_000:
        return None
    return val


def _pick_iface(stats: dict[str, tuple[int, int]]) -> str | None:
    preferred = _default_iface()
    if preferred and preferred in stats:
        return preferred
    base = Path("/sys/class/net")
    if base.is_dir():
        for path in sorted(base.iterdir()):
            name = path.name
            if _skip_iface(name) or name not in stats:
                continue
            if _read(path / "operstate") == "up":
                return name
    for name in stats:
        if not _skip_iface(name):
            return name
    return None


def _net(out: Sensors) -> None:
    global _net_prev
    stats = _parse_netdev()
    iface = _pick_iface(stats)
    if iface is None:
        return
    rx, tx = stats[iface]
    now = time.monotonic()
    out.net_iface = iface
    out.net_link_mbps = _link_mbps(iface)
    out.net_kind = (
        "wifi" if Path(f"/sys/class/net/{iface}/wireless").is_dir() else "eth"
    )
    out.net_ipv4 = _iface_ipv4(iface)
    prev = _net_prev
    _net_prev = (iface, rx, tx, now)
    if prev is None or prev[0] != iface:
        return
    dt = now - prev[3]
    if dt <= 0:
        return
    out.net_rx_mbps = max(0.0, (rx - prev[1]) * 8.0 / dt / 1_000_000.0)
    out.net_tx_mbps = max(0.0, (tx - prev[2]) * 8.0 / dt / 1_000_000.0)
    total = out.net_rx_mbps + out.net_tx_mbps
    scale = out.net_link_mbps or 100.0
    out.net_pct = max(0.0, min(100.0, total * 100.0 / scale))


def _iface_ipv4(name: str) -> str | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        packed = struct.pack("256s", name.encode("utf-8")[:15])
        raw = fcntl.ioctl(sock.fileno(), 0x8915, packed)  # SIOCGIFADDR
        sock.close()
        return socket.inet_ntoa(raw[20:24])
    except OSError:
        return None


def _physical_disks() -> list[str]:
    base = Path("/sys/block")
    if not base.is_dir():
        return []
    names: list[str] = []
    for path in sorted(base.iterdir()):
        name = path.name
        if name.startswith(_SKIP_DISK):
            continue
        names.append(name)
    return names


def _diskstats() -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    try:
        lines = Path("/proc/diskstats").read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        parts = line.split()
        if len(parts) < 10:
            continue
        name = parts[2]
        try:
            out[name] = (int(parts[5]), int(parts[9]))  # sectors read / written
        except ValueError:
            continue
    return out


def _root_disk() -> tuple[str | None, str]:
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, "/"
    for line in lines:
        if " / " not in f" {line} ":
            continue
        parts = line.split()
        if len(parts) < 5 or parts[4] != "/":
            continue
        src = parts[-2] if len(parts) >= 2 else ""
        if src.startswith("/dev/"):
            node = src.rsplit("/", 1)[-1]
            for disk in _physical_disks():
                if node == disk or node.startswith(disk):
                    return disk, "/"
        break
    disks = _physical_disks()
    return (disks[0] if disks else None), "/"


def _mount_for_disk(name: str) -> str | None:
    try:
        lines = Path("/proc/mounts").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    best = None
    for line in lines:
        parts = line.split()
        if len(parts) < 2 or not parts[0].startswith("/dev/"):
            continue
        node = parts[0].rsplit("/", 1)[-1]
        if node == name or node.startswith(name):
            mount = parts[1]
            if mount == "/":
                return "/"
            if best is None:
                best = mount
    return best


def _disks(out: Sensors) -> None:
    global _disk_prev
    stats = _diskstats()
    now = time.monotonic()
    root_disk, _root = _root_disk()
    infos: list[DiskInfo] = []
    next_prev: dict[str, tuple[int, int, float]] = {}
    for name in _physical_disks():
        info = DiskInfo(name=name, mount=_mount_for_disk(name))
        if info.mount:
            try:
                usage = os.statvfs(info.mount)
            except OSError:
                usage = None
            if usage is not None:
                total = usage.f_frsize * usage.f_blocks
                free = usage.f_frsize * usage.f_bavail
                used = max(0, total - free)
                info.total_gb = total / (1024**3)
                info.used_gb = used / (1024**3)
                if total:
                    info.pct = used * 100.0 / total
        rw = stats.get(name)
        if rw is not None:
            rsect, wsect = rw
            prev = _disk_prev.get(name)
            next_prev[name] = (rsect, wsect, now)
            if prev is not None:
                dt = now - prev[2]
                if dt > 0:
                    info.read_mbps = max(0.0, (rsect - prev[0]) * 512.0 / dt / 1_000_000.0)
                    info.write_mbps = max(0.0, (wsect - prev[1]) * 512.0 / dt / 1_000_000.0)
        infos.append(info)
    _disk_prev = next_prev
    if root_disk:
        infos.sort(key=lambda d: 0 if d.name == root_disk else 1)
    out.disks = infos


def _processes(out: Sensors) -> None:
    global _proc_prev, _proc_total_prev
    try:
        stat_lines = Path("/proc/stat").read_text(encoding="utf-8").splitlines()
        total_parts = stat_lines[0].split()[1:]
        total_jiffies = sum(int(x) for x in total_parts)
    except (OSError, ValueError, IndexError):
        return
    prev_total = _proc_total_prev
    _proc_total_prev = total_jiffies
    rows: list[ProcInfo] = []
    next_prev: dict[int, int] = {}
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            raw = (entry / "stat").read_text(encoding="utf-8", errors="replace")
            comm_end = raw.rfind(")")
            comm_start = raw.find("(")
            name = raw[comm_start + 1 : comm_end] if comm_start >= 0 and comm_end > comm_start else entry.name
            fields = raw[comm_end + 2 :].split()
            jiffies = int(fields[11]) + int(fields[12])
            rss_pages = int(fields[21])
        except (OSError, ValueError, IndexError):
            continue
        next_prev[pid] = jiffies
        cpu = 0.0
        if prev_total is not None and pid in _proc_prev:
            dt = total_jiffies - prev_total
            if dt > 0:
                cpu = max(0.0, (jiffies - _proc_prev[pid]) * 100.0 / dt)
        rows.append(
            ProcInfo(
                pid=pid,
                name=name,
                cpu_pct=cpu,
                mem_mb=rss_pages * (os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)),
            )
        )
    _proc_prev = next_prev
    rows.sort(key=lambda r: r.cpu_pct, reverse=True)
    out.processes = rows[:40]


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _f(raw: str) -> float | None:
    raw = (raw or "").strip().replace("[N/A]", "").replace("W", "").replace("%", "")
    if not raw or "deprecated" in raw.lower():
        return None
    try:
        return float(raw)
    except ValueError:
        return None
