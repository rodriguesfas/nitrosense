"""Local AI inference smoke/load via llama-server + OpenAI-compatible HTTP."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

LLAMA_SERVER = Path.home() / ".local/bin/llama-server"
MODELS = (
    Path("/home/fasr/SSD_BACKUP/local-ai/models/qwen2.5-coder-3b.gguf"),
    Path("/home/fasr/SSD_BACKUP/local-ai/models/qwen2.5-coder-7b.gguf"),
)


def _pick_model() -> Path:
    for path in MODELS:
        if path.is_file():
            return path
    raise FileNotFoundError("no GGUF model found under local-ai/models")


def run(duration_s: int, *, port: int = 8765) -> int:
    duration_s = max(30, int(duration_s))
    if not LLAMA_SERVER.is_file():
        print("llama-server not found", flush=True)
        return 1
    model = _pick_model()
    cmd = [
        str(LLAMA_SERVER),
        "-m",
        str(model),
        "-ngl",
        "99",
        "-c",
        "2048",
        "--port",
        str(port),
        "--host",
        "127.0.0.1",
        "-n",
        "128",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    rates: list[float] = []
    end = time.time() + duration_s
    try:
        ready = False
        for _ in range(90):
            if proc.poll() is not None:
                print("llama-server exited early", flush=True)
                return 1
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
                ready = True
                break
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(0.5)
        if not ready:
            print("llama-server not ready", flush=True)
            return 1
        while time.time() < end:
            payload = json.dumps(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": "Write a short Python fibonacci function.",
                        }
                    ],
                    "temperature": 0.2,
                    "max_tokens": 96,
                }
            ).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = json.loads(resp.read().decode())
            dt = max(0.001, time.time() - t0)
            usage = body.get("usage") or {}
            n = float(usage.get("completion_tokens") or 32)
            rate = n / dt
            rates.append(rate)
            print(f"{rate:.2f} tok/s", flush=True)
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
    if rates:
        avg = sum(rates) / len(rates)
        print(f"avg {avg:.2f} tok/s", flush=True)
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=120)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    return run(args.duration, port=args.port)


if __name__ == "__main__":
    raise SystemExit(main())
