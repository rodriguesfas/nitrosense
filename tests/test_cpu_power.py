"""CPU unlock is RAPL PL1 → PL2, not a fake turbo flag."""

from __future__ import annotations

import unittest

from nitrosense.cpu import CpuPower, _uw_to_w, boost_pl1, cpu_unlocked
from nitrosense.i18n import set_lang, t


class CpuPowerTest(unittest.TestCase):
    def test_uw_to_w(self) -> None:
        self.assertEqual(_uw_to_w("55000000"), 55)
        self.assertEqual(_uw_to_w("115000000"), 115)
        self.assertIsNone(_uw_to_w("0"))
        self.assertIsNone(_uw_to_w("N/A"))

    def test_unlock_threshold(self) -> None:
        capped = CpuPower(pl1_w=55, pl2_w=115, tdp_w=45)
        self.assertFalse(cpu_unlocked(capped))
        self.assertEqual(boost_pl1(capped), 115)
        self.assertTrue(cpu_unlocked(CpuPower(pl1_w=115, pl2_w=115, tdp_w=45)))
        self.assertTrue(cpu_unlocked(CpuPower(pl1_w=112, pl2_w=115, tdp_w=45)))

    def test_status_copy_names_live_pl1(self) -> None:
        set_lang("en")
        text = t("cpu.cap_on", live="55", boost="115")
        self.assertIn("live 55 W", text)
        self.assertIn("ceiling 115 W", text)
        set_lang("pt_BR")
        text = t("cpu.cap_on", live="115", boost="115")
        self.assertIn("agora 115 W", text)
        self.assertIn("teto 115 W", text)


if __name__ == "__main__":
    unittest.main()
