"""Live TGP comes from nvidia-smi POWER block, not CSV power.limit ([N/A] on 595-open)."""

from __future__ import annotations

import unittest

from nitrosense.gpu import parse_smi_power_readings
from nitrosense.i18n import set_lang, t

IDLE = """
==============NVSMI LOG==============
GPU 00000000:01:00.0
    GPU Power Readings
        Average Power Draw                             : 3.70 W
        Instantaneous Power Draw                       : 3.73 W
        Current Power Limit                            : 60.00 W
        Requested Power Limit                          : N/A
        Default Power Limit                            : 60.00 W
        Min Power Limit                                : 5.00 W
        Max Power Limit                                : 75.00 W
    Power Samples
        Duration                                       : Not Found
        Max                                            : Not Found
        Min                                            : Not Found
        Avg                                            : Not Found
    GPU Memory Power Readings
        Average Power Draw                             : N/A
        Instantaneous Power Draw                       : N/A
    Module Power Readings
        Current Power Limit                            : N/A
        Default Power Limit                            : N/A
        Max Power Limit                                : N/A
"""

BOOST = IDLE.replace("Current Power Limit                            : 60.00 W",
                     "Current Power Limit                            : 66.21 W")


class PowerReadingsTest(unittest.TestCase):
    def test_idle_uses_gpu_block_not_module_na(self) -> None:
        readings = parse_smi_power_readings(IDLE)
        assert readings is not None
        self.assertEqual(readings.current_w, 60.0)
        self.assertEqual(readings.default_w, 60.0)
        self.assertEqual(readings.max_w, 75.0)
        self.assertAlmostEqual(readings.draw_w or 0, 3.73)

    def test_live_limit_tracks_dynamic_boost(self) -> None:
        readings = parse_smi_power_readings(BOOST)
        assert readings is not None
        self.assertEqual(round(readings.current_w or 0), 66)
        self.assertEqual(readings.max_w, 75.0)

    def test_status_copy_shows_live_not_fake_ceiling(self) -> None:
        set_lang("en")
        text = t("gpu.cap_on", live="60", boost="75")
        self.assertIn("live 60 W", text)
        self.assertIn("ceiling 75 W", text)
        self.assertNotIn("up to 75 W under load", text)
        set_lang("pt_BR")
        text = t("gpu.cap_on", live="66", boost="75")
        self.assertIn("agora 66 W", text)
        self.assertIn("teto 75 W", text)


if __name__ == "__main__":
    unittest.main()
