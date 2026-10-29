"""Unit tests for performance profiles (no privileged writes)."""

from __future__ import annotations

import unittest

from nitrosense.profiles import PROFILES, SAFE_ID, get_profile


class ProfilesTest(unittest.TestCase):
    def test_ids_unique(self) -> None:
        ids = [p.id for p in PROFILES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(SAFE_ID, ids)

    def test_safe_is_conservative(self) -> None:
        safe = get_profile(SAFE_ID)
        self.assertEqual(safe.mode, "balanced")
        self.assertEqual(safe.fans, "auto")
        self.assertFalse(safe.gpu_boost)
        self.assertLessEqual(safe.pl1_w, 65)

    def test_compile_is_cpu_heavy(self) -> None:
        compile_p = get_profile("compile")
        self.assertEqual(compile_p.pl1_w, 115)
        self.assertFalse(compile_p.gpu_boost)
        self.assertEqual(compile_p.governor, "performance")

    def test_ai_enables_boost(self) -> None:
        ai = get_profile("ai")
        self.assertTrue(ai.gpu_boost)
        self.assertGreaterEqual(ai.pl1_w, 55)


if __name__ == "__main__":
    unittest.main()
