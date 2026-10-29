"""Opt-in stability / throughput harness with abort + restore."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from nitrosense.audit import record
from nitrosense.profiles import restore_safe
from nitrosense.throttle import ThrottleSnapshot, probe as probe_throttle

RESULTS = Path.home() / ".config" / "nitrosense" / "bench_results.jsonl"
ProgressCb = Callable[[str], None]


@dataclass
class BenchLimits:
    max_temp_c: int = 95
    max_duration_s: int = 3600


@dataclass
class BenchResult:
    kind: str
    duration_s: float
    ok: bool
    aborted: bool = False
    reason: str = ""
    samples: int = 0
    max_temp_c: int | None = None
    throttle_hits: int = 0
    notes: list[str] = field(default_factory=list)


class BenchRunner:
    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def abort(self, *, restore: bool = True) -> None:
        self._stop.set()
        with self._lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    proc.terminate()
                except OSError:
                    pass
        if restore:
            try:
                restore_safe()
            except Exception:  # noqa: BLE001
                pass
        record("bench_abort", restore=restore)

    def run(
        self,
        kind: str,
        duration_s: int,
        *,
        limits: BenchLimits | None = None,
        on_progress: ProgressCb | None = None,
    ) -> BenchResult:
        limits = limits or BenchLimits()
        duration_s = max(15, min(int(duration_s), limits.max_duration_s))
        if kind not in {"cpu", "gpu", "combined", "memory"}:
            raise ValueError(f"unknown bench kind: {kind}")
        self._stop.clear()
        cmd = self._command(kind, duration_s)
        if on_progress:
            on_progress(f"start {kind} {duration_s}s")
        started = time.monotonic()
        max_temp: int | None = None
        throttle_hits = 0
        samples = 0
        notes: list[str] = []
        aborted = False
        fail_reason = ""

        with self._lock:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
            )
            proc = self._proc

        try:
            while True:
                if self._stop.is_set():
                    aborted = True
                    fail_reason = "aborted"
                    break
                rc = proc.poll()
                elapsed = time.monotonic() - started
                snap = probe_throttle(hot_c=limits.max_temp_c)
                samples += 1
                temps = list(snap.acer_temp_c)
                if snap.gpu_temp_c is not None:
                    temps.append(snap.gpu_temp_c)
                if temps:
                    cur = max(temps)
                    max_temp = cur if max_temp is None else max(max_temp, cur)
                    if cur >= limits.max_temp_c:
                        fail_reason = f"temp>={limits.max_temp_c}"
                        aborted = True
                        self._stop.set()
                        break
                if snap.throttling:
                    throttle_hits += 1
                    notes.extend(snap.reasons)
                if on_progress and samples % 5 == 0:
                    on_progress(
                        f"{kind} {int(elapsed)}s temp={max_temp} throttle={throttle_hits}"
                    )
                if rc is not None:
                    if rc != 0 and not aborted:
                        fail_reason = f"worker_exit_{rc}"
                    break
                if elapsed >= duration_s + 5:
                    # worker should have exited; force stop
                    break
                time.sleep(1.0)
        finally:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        proc.kill()
            with self._lock:
                self._proc = None

        ok = (not aborted) and fail_reason == "" and throttle_hits < max(3, duration_s // 10)
        if throttle_hits and ok:
            notes.append(f"soft_throttle_hits={throttle_hits}")
        result = BenchResult(
            kind=kind,
            duration_s=round(time.monotonic() - started, 1),
            ok=ok,
            aborted=aborted,
            reason=fail_reason,
            samples=samples,
            max_temp_c=max_temp,
            throttle_hits=throttle_hits,
            notes=sorted(set(notes)),
        )
        _append_result(result)
        record(
            "bench_result",
            kind=result.kind,
            ok=result.ok,
            duration_s=result.duration_s,
            reason=result.reason or None,
            max_temp_c=result.max_temp_c,
        )
        if aborted and fail_reason.startswith("temp"):
            try:
                restore_safe()
            except Exception:  # noqa: BLE001
                pass
        return result

    def _command(self, kind: str, duration_s: int) -> list[str]:
        stress = shutil.which("stress-ng")
        if stress is None:
            raise RuntimeError("stress-ng not installed")
        if kind == "cpu":
            return [
                stress,
                "--cpu",
                str(max(1, os.cpu_count() or 4)),
                "--timeout",
                f"{duration_s}s",
                "--metrics-brief",
            ]
        if kind == "memory":
            return [
                stress,
                "--vm",
                "2",
                "--vm-bytes",
                "2G",
                "--timeout",
                f"{duration_s}s",
            ]
        if kind == "gpu":
            # Lightweight GPU occupancy via nvidia-smi persistence + compute burn if available
            # Fall back to CPU+short CUDA-less load: keep GPU awake with periodic queries.
            script = (
                "import subprocess,time,sys\n"
                f"end=time.time()+{duration_s}\n"
                "while time.time()<end:\n"
                "  subprocess.run(['nvidia-smi','dmon','-s','pucvmet','-c','1'],"
                "check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
                "  time.sleep(0.2)\n"
            )
            return ["python3", "-c", script]
        # combined: CPU stress + GPU keep-alive
        script = (
            "import os,subprocess,time\n"
            f"dur={duration_s}\n"
            "stress=subprocess.Popen(['stress-ng','--cpu',str(os.cpu_count() or 4),"
            "'--timeout',f'{dur}s'], start_new_session=True)\n"
            "end=time.time()+dur\n"
            "try:\n"
            "  while time.time()<end and stress.poll() is None:\n"
            "    subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,temperature.gpu',"
            "'--format=csv,noheader'],check=False,stdout=subprocess.DEVNULL,"
            "stderr=subprocess.DEVNULL)\n"
            "    time.sleep(0.5)\n"
            "finally:\n"
            "  if stress.poll() is None:\n"
            "    stress.terminate()\n"
        )
        return ["python3", "-c", script]


def _append_result(result: BenchResult) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def recent_results(limit: int = 20) -> list[dict]:
    if not RESULTS.is_file():
        return []
    try:
        lines = RESULTS.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
