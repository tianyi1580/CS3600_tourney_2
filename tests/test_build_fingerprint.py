from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from Yolanda.infra.build_fingerprint import compute_build_fingerprint


class BuildFingerprintTests(unittest.TestCase):
    def test_fingerprint_is_deterministic_for_same_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fp_same_") as tmp:
            root = Path(tmp)
            (root / "agent.py").write_text("print('a')\n", encoding="utf-8")
            (root / "policy.py").write_text("x = 1\n", encoding="utf-8")
            a = compute_build_fingerprint(bot_dir=root)
            b = compute_build_fingerprint(bot_dir=root)
            self.assertEqual(a, b)

    def test_fingerprint_changes_when_source_changes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fp_change_") as tmp:
            root = Path(tmp)
            src = root / "agent.py"
            src.write_text("x = 1\n", encoding="utf-8")
            before = compute_build_fingerprint(bot_dir=root)
            src.write_text("x = 2\n", encoding="utf-8")
            after = compute_build_fingerprint(bot_dir=root)
            self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
