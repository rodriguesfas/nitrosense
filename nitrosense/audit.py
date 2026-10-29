"""Append-only audit log for privileged NitroSense changes."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

LOG_DIR = Path.home() / ".config" / "nitrosense"
LOG_PATH = LOG_DIR / "audit.jsonl"
MAX_LINES = 2000


def record(action: str, **fields: Any) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "action": action,
        **{k: v for k, v in fields.items() if v is not None},
    }
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _trim()


def recent(limit: int = 40) -> list[dict[str, Any]]:
    if not LOG_PATH.is_file():
        return []
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-max(1, limit) :]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _trim() -> None:
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= MAX_LINES:
        return
    LOG_PATH.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
