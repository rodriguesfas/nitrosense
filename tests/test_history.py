"""Undo stack persistence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nitrosense import history
from nitrosense.history import Snapshot, depth, push


class HistoryTest(unittest.TestCase):
    def test_push_depth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "undo.json"
            with mock.patch.object(history, "STACK_PATH", path):
                self.assertEqual(depth(), 0)
                push(
                    Snapshot(
                        profile_id="daily",
                        mode_fw="balanced",
                        fans="auto",
                        fan_cpu=None,
                        fan_gpu=None,
                        pl1_w=55,
                        gpu_boost=False,
                        governor="schedutil",
                        epp="balance_performance",
                        ppd="balanced",
                    )
                )
                self.assertEqual(depth(), 1)


if __name__ == "__main__":
    unittest.main()
