"""Audit log append / read."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nitrosense import audit


class AuditTest(unittest.TestCase):
    def test_record_and_recent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.jsonl"
            with mock.patch.object(audit, "LOG_PATH", path), mock.patch.object(
                audit, "LOG_DIR", Path(tmp)
            ):
                audit.record("test_action", value=1)
                audit.record("test_action", value=2)
                rows = audit.recent(10)
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[-1]["value"], 2)


if __name__ == "__main__":
    unittest.main()
