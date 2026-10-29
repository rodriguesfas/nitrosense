"""Repeated GCC -O3 compile loop as a sustained CPU compile workload."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import time
from pathlib import Path

SRC = """
#include <math.h>
double work(double x) {
  double s = 0.0;
  for (int i = 0; i < 250000; ++i) {
    s += sin(x + i) * cos(x - i);
  }
  return s;
}
int main(void) { return work(0.1) > 0.0; }
"""


def run(duration_s: int) -> int:
    duration_s = max(15, int(duration_s))
    end = time.time() + duration_s
    loops = 0
    with tempfile.TemporaryDirectory(prefix="ns-compile-") as td:
        c_path = Path(td) / "burn.c"
        out = Path(td) / "burn"
        c_path.write_text(SRC, encoding="utf-8")
        while time.time() < end:
            result = subprocess.run(
                ["gcc", "-O3", "-ffast-math", str(c_path), "-lm", "-o", str(out)],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(result.stderr or result.stdout or "gcc failed", flush=True)
                return result.returncode or 1
            loops += 1
    print(f"compile_loops={loops}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=60)
    args = parser.parse_args()
    return run(args.duration)


if __name__ == "__main__":
    raise SystemExit(main())
