"""Driver health probe tests."""

from __future__ import annotations

import unittest

from nitrosense.drivers import DriverHealth, summary_line


class DriversTest(unittest.TestCase):
    def test_summary_line(self) -> None:
        h = DriverHealth(
            kernel="7.0.0-42-generic",
            linuwu_ko=True,
            linuwu_loaded=True,
            platform_profile=True,
            nvidia_ko=True,
            nvidia_loaded=True,
            nvidia_smi_ok=True,
            notes=[],
        )
        text = summary_line(h)
        self.assertIn("Linuwu OK", text)
        self.assertIn("NVIDIA OK", text)

    def test_probe_runs(self) -> None:
        from nitrosense.drivers import probe

        h = probe()
        self.assertTrue(h.kernel)
        self.assertIsInstance(h.notes, list)


if __name__ == "__main__":
    unittest.main()
