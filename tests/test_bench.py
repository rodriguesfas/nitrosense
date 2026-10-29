"""Bench helpers (no long workloads)."""

from __future__ import annotations

import unittest

from nitrosense.bench import (
    DURATION_PRESETS,
    KINDS,
    compare_results,
    best_for_kind,
)


class BenchMetaTest(unittest.TestCase):
    def test_kinds_include_ai_compile_vram(self) -> None:
        for kind in ("ai", "compile", "vram", "sustained"):
            self.assertIn(kind, KINDS)

    def test_duration_presets(self) -> None:
        seconds = [s for _, s in DURATION_PRESETS]
        self.assertIn(60, seconds)
        self.assertIn(1800, seconds)
        self.assertIn(14400, seconds)

    def test_compare_results(self) -> None:
        a = {"kind": "cpu", "ok": True, "max_temp_c": 80, "metric_value": 10, "throttle_hits": 1}
        b = {"kind": "cpu", "ok": True, "max_temp_c": 70, "metric_value": 8, "throttle_hits": 0}
        cmp_ = compare_results(a, b)
        self.assertTrue(cmp_["kind_match"])
        self.assertEqual(cmp_["max_temp_delta"], 10)
        self.assertEqual(cmp_["metric_delta"], 2)

    def test_best_for_kind_empty(self) -> None:
        self.assertIsNone(best_for_kind("no_such_kind_zzz"))


if __name__ == "__main__":
    unittest.main()
