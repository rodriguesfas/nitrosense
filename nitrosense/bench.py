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
from nitrosense.profiles import restore_safe, saved_profile_id
from nitrosense.throttle import probe as probe_throttle

RESULTS = Path.home() / ".config" / "nitrosense" / "bench_results.jsonl"
ProgressCb = Callable[[str], None]

KIND_CPU = "cpu"
KIND_GPU = "gpu"
KIND_MEMORY = "memory"
KIND_COMBINED = "combined"
KIND_COMPILE = "compile"
KIND_AI = "ai"
KIND_VRAM = "vram"
KIND_SUSTAINED = "sustained"

KINDS = (
    KIND_CPU,
    KIND_GPU,
    KIND_MEMORY,
    KIND_COMBINED,
    KIND_COMPILE,
    KIND_AI,
    KIND_VRAM,
    KIND_SUSTAINED,
)

DURATION_PRESETS = (
    ("1m", 60),
    ("5m", 300),
    ("30m", 1800),
    ("1h", 3600),
    ("4h", 14400),
)

@dataclass
class BenchLimits:
    max_temp_c: int = 95
    max_duration_s: int = 14400
    # Soft throttle hits allowed before FAIL (scales with duration).
    throttle_budget_factor: float = 0.15


@dataclass
class BenchResult:
    kind: str
    duration_s: float
    ok: bool
    aborted: bool = False
    reason: str = ""
    samples: int = 0
    max_temp_c: int | None = None
    avg_temp_c: float | None = None
    throttle_hits: int = 0
    profile_id: str | None = None
    metric: str | None = None  # e.g. tokens/s, compile loops
    metric_value: float | None = None
    notes: list[str] = field(default_factory=list)
    ts: str = ""


class BenchRunner:
    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._children: list[subprocess.Popen[str]] = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._metric: tuple[str, float] | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def abort(self, *, restore: bool = True) -> None:
        self._stop.set()
        with self._lock:
            procs = list(self._children)
            if self._proc is not None:
                procs.append(self._proc)
        for proc in procs:
            if proc.poll() is not None:
                continue
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
        profile_id: str | None = None,
    ) -> BenchResult:
        limits = limits or BenchLimits()
        duration_s = max(15, min(int(duration_s), limits.max_duration_s))
        if kind not in KINDS:
            raise ValueError(f"unknown bench kind: {kind}")
        self._stop.clear()
        self._metric = None
        self._children = []
        cmd = self._command(kind, duration_s)
        if on_progress:
            on_progress(f"start {kind} {duration_s}s")
        started = time.monotonic()
        max_temp: int | None = None
        temp_sum = 0
        temp_n = 0
        throttle_hits = 0
        samples = 0
        notes: list[str] = []
        aborted = False
        fail_reason = ""
        budget = max(3, int(duration_s * limits.throttle_budget_factor))

        with self._lock:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            proc = self._proc

        output_chunks: list[str] = []
        try:
            while True:
                if self._stop.is_set():
                    aborted = True
                    fail_reason = "aborted"
                    break
                rc = proc.poll()
                if proc.stdout is not None:
                    line = proc.stdout.readline() if rc is None else proc.stdout.read()
                    if line:
                        output_chunks.append(line)
                        self._ingest_metric(kind, line)
                elapsed = time.monotonic() - started
                snap = probe_throttle(hot_c=limits.max_temp_c)
                samples += 1
                temps = list(snap.acer_temp_c)
                if snap.gpu_temp_c is not None:
                    temps.append(snap.gpu_temp_c)
                if temps:
                    cur = max(temps)
                    temp_sum += cur
                    temp_n += 1
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
                        f"{kind} {int(elapsed)}s/{duration_s}s "
                        f"temp={max_temp} throttle={throttle_hits}"
                    )
                if rc is not None:
                    if rc != 0 and not aborted:
                        # AI/compile may print metrics then exit 0; non-zero is fail
                        # unless we got a usable metric for AI timed runs.
                        if kind == KIND_AI and self._metric is not None:
                            notes.append(f"worker_exit_{rc}_with_metric")
                        else:
                            fail_reason = f"worker_exit_{rc}"
                    break
                if elapsed >= duration_s + 15:
                    break
                time.sleep(0.5 if rc is None else 0)
        finally:
            self._kill_proc(proc)
            with self._lock:
                self._proc = None
                for child in self._children:
                    self._kill_proc(child)
                self._children = []

        if throttle_hits > budget and not fail_reason:
            fail_reason = f"throttle_hits>{budget}"
            aborted = True
        ok = (not aborted) and fail_reason == ""
        if throttle_hits and ok:
            notes.append(f"soft_throttle_hits={throttle_hits}")
        metric_name, metric_value = (None, None)
        if self._metric is not None:
            metric_name, metric_value = self._metric
        result = BenchResult(
            kind=kind,
            duration_s=round(time.monotonic() - started, 1),
            ok=ok,
            aborted=aborted,
            reason=fail_reason,
            samples=samples,
            max_temp_c=max_temp,
            avg_temp_c=round(temp_sum / temp_n, 1) if temp_n else None,
            throttle_hits=throttle_hits,
            profile_id=profile_id or saved_profile_id(),
            metric=metric_name,
            metric_value=metric_value,
            notes=sorted(set(notes)),
            ts=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        _append_result(result)
        record(
            "bench_result",
            kind=result.kind,
            ok=result.ok,
            duration_s=result.duration_s,
            reason=result.reason or None,
            max_temp_c=result.max_temp_c,
            metric=result.metric,
            metric_value=result.metric_value,
            profile_id=result.profile_id,
        )
        if aborted and (
            fail_reason.startswith("temp") or fail_reason.startswith("throttle")
        ):
            try:
                restore_safe()
            except Exception:  # noqa: BLE001
                pass
        return result

    def _ingest_metric(self, kind: str, line: str) -> None:
        line = line.strip()
        if kind == KIND_AI and "tok/s" in line:
            # e.g. prompt eval or generation lines from llama
            for part in line.replace(",", " ").split():
                if part.endswith("tok/s") or part.endswith("t/s"):
                    try:
                        self._metric = ("tok_s", float(part.split("tok")[0].split("t")[0]))
                    except ValueError:
                        pass
        if kind == KIND_COMPILE and line.startswith("compile_loops="):
            try:
                self._metric = ("compile_loops", float(line.split("=", 1)[1]))
            except ValueError:
                pass
        if kind == KIND_VRAM and line.startswith("allocated_mib="):
            try:
                self._metric = ("vram_mib", float(line.split("=", 1)[1].split()[0]))
            except ValueError:
                pass

    def _kill_proc(self, proc: subprocess.Popen[str] | None) -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.terminate()
            except OSError:
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    proc.kill()
                except OSError:
                    pass

    def _command(self, kind: str, duration_s: int) -> list[str]:
        stress = shutil.which("stress-ng")
        if kind == KIND_CPU:
            if stress is None:
                raise RuntimeError("stress-ng not installed")
            return [
                stress,
                "--cpu",
                str(max(1, os.cpu_count() or 4)),
                "--timeout",
                f"{duration_s}s",
                "--metrics-brief",
            ]
        if kind == KIND_MEMORY:
            if stress is None:
                raise RuntimeError("stress-ng not installed")
            return [
                stress,
                "--vm",
                "2",
                "--vm-bytes",
                "2G",
                "--timeout",
                f"{duration_s}s",
            ]
        if kind == KIND_GPU:
            # Keep GPU busy via repeated CUDA context + light alloc churn.
            return [
                "python3",
                "-m",
                "nitrosense.cuda_burn",
                "--duration",
                str(duration_s),
                "--fraction",
                "0.35",
            ]
        if kind == KIND_VRAM:
            return [
                "python3",
                "-m",
                "nitrosense.cuda_burn",
                "--duration",
                str(duration_s),
                "--fraction",
                "0.70",
            ]
        if kind == KIND_COMBINED:
            script = f"""
import os, subprocess, time, sys
dur={duration_s}
stress=subprocess.Popen(
    ['stress-ng','--cpu',str(os.cpu_count() or 4),'--timeout',f'{{dur}}s'],
    start_new_session=True,
)
gpu=subprocess.Popen(
    [sys.executable,'-m','nitrosense.cuda_burn','--duration',str(dur),'--fraction','0.4'],
    start_new_session=True,
)
end=time.time()+dur
try:
    while time.time()<end:
        if stress.poll() is not None and gpu.poll() is not None:
            break
        time.sleep(1)
finally:
    for p in (stress, gpu):
        if p.poll() is None:
            p.terminate()
"""
            return ["python3", "-c", script]
        if kind == KIND_SUSTAINED:
            # Long dual load: CPU matrix + moderate VRAM hold.
            script = f"""
import os, subprocess, time, sys
dur={duration_s}
stress=subprocess.Popen(
    ['stress-ng','--cpu',str(max(2,(os.cpu_count() or 4)//2)),
     '--matrix',str(max(1,(os.cpu_count() or 4)//2)),
     '--timeout',f'{{dur}}s'],
    start_new_session=True,
)
gpu=subprocess.Popen(
    [sys.executable,'-m','nitrosense.cuda_burn','--duration',str(dur),'--fraction','0.5'],
    start_new_session=True,
)
end=time.time()+dur
try:
    while time.time()<end:
        if stress.poll() is not None and gpu.poll() is not None:
            break
        time.sleep(1)
finally:
    for p in (stress, gpu):
        if p.poll() is None:
            p.terminate()
"""
            return ["python3", "-c", script]
        if kind == KIND_COMPILE:
            return [
                "python3",
                "-m",
                "nitrosense.bench_compile",
                "--duration",
                str(duration_s),
            ]
        if kind == KIND_AI:
            return [
                "python3",
                "-m",
                "nitrosense.bench_ai",
                "--duration",
                str(duration_s),
            ]
        raise ValueError(kind)


def _append_result(result: BenchResult) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def recent_results(limit: int = 40) -> list[dict]:
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


def compare_results(a: dict, b: dict) -> dict:
    """Compare two bench result dicts (newer vs older baseline)."""

    def _num(key: str):
        va, vb = a.get(key), b.get(key)
        if va is None or vb is None:
            return None
        try:
            return float(va) - float(vb)
        except (TypeError, ValueError):
            return None

    return {
        "kind_match": a.get("kind") == b.get("kind"),
        "ok_a": a.get("ok"),
        "ok_b": b.get("ok"),
        "max_temp_delta": _num("max_temp_c"),
        "duration_delta": _num("duration_s"),
        "metric_delta": _num("metric_value"),
        "throttle_delta": _num("throttle_hits"),
        "profile_a": a.get("profile_id"),
        "profile_b": b.get("profile_id"),
    }


def best_for_kind(kind: str) -> dict | None:
    rows = [r for r in recent_results(200) if r.get("kind") == kind and r.get("ok")]
    if not rows:
        return None

    def score(r: dict) -> tuple:
        metric = r.get("metric_value") or 0.0
        temp = r.get("max_temp_c") or 999
        thr = r.get("throttle_hits") or 0
        return (float(metric), -float(thr), -float(temp))

    return max(rows, key=score)
