"""Per-app Scenario rules (Windows NitroSense: bind profile + fans to a process)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CONFIG = Path.home() / ".config" / "nitrosense" / "scenarios.json"
MODES = ("quiet", "balanced", "performance")
FANS = ("auto", "max", "custom")


@dataclass
class Rule:
    match: str
    mode: str
    fans: str = "auto"
    cpu: int = 50
    gpu: int = 50


@dataclass
class ScenarioConfig:
    enabled: bool = True
    rules: list[Rule] = field(default_factory=list)


def load() -> ScenarioConfig:
    if not CONFIG.is_file():
        return ScenarioConfig()
    try:
        raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ScenarioConfig()
    rules: list[Rule] = []
    for item in raw.get("rules") or []:
        match = str(item.get("match") or "").strip()
        mode = str(item.get("mode") or "")
        fans_raw = item.get("fans")
        if fans_raw in FANS:
            fans = str(fans_raw)
        elif fans_raw is None:
            fans = ""
        else:
            fans = "auto"
        cpu = int(item.get("cpu") or 50)
        gpu = int(item.get("gpu") or 50)
        cpu = max(1, min(100, cpu))
        gpu = max(1, min(100, gpu))
        if match and mode in MODES:
            rules.append(Rule(match=match, mode=mode, fans=fans, cpu=cpu, gpu=gpu))
    return ScenarioConfig(enabled=bool(raw.get("enabled", True)), rules=rules)


def save(cfg: ScenarioConfig) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": cfg.enabled,
        "rules": [
            {
                "match": r.match,
                "mode": r.mode,
                "fans": r.fans,
                "cpu": r.cpu,
                "gpu": r.gpu,
            }
            for r in cfg.rules
        ],
    }
    CONFIG.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
