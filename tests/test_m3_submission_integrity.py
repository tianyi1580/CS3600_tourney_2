from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "workflows" / "m3_submission_integrity.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("m3_submission_integrity", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load workflows/m3_submission_integrity.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class M3SubmissionIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_module()

    def test_extract_build_tag(self) -> None:
        msg = "status ok | build=fp1:abc123def456 | model=1"
        self.assertEqual(self.module._extract_build_tag(msg), "fp1:abc123def456")

    def test_validate_zip_contract_fails_on_wrong_top_level(self) -> None:
        with tempfile.TemporaryDirectory(prefix="zip_contract_") as tmp:
            root = Path(tmp)
            zip_path = root / "bad.zip"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("WrongBot/agent.py", "print('x')\n")
            result = self.module.IntegrityResult()
            self.module._validate_zip_contract(zip_path, "Yolanda", result)
            self.assertTrue(any("zip_top_level_mismatch" in item for item in result.failures))


if __name__ == "__main__":
    unittest.main()
