from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts/validate.py"
SPEC = importlib.util.spec_from_file_location("bc250_validate_tests", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate)


class ValidationScopeTests(unittest.TestCase):
    def test_rpm_prep_sources_are_outside_the_repository_security_scan(self) -> None:
        for relative in (
            "governor-src/vendor/crate/example.rs",
            "unlock-src/README.md",
            "live-manager-src/tool.sh",
        ):
            with self.subTest(relative=relative):
                self.assertTrue(validate.security_scan_excludes(Path(relative)))

        self.assertFalse(
            validate.security_scan_excludes(Path("models/coding-agent/coding-agent.sh"))
        )


if __name__ == "__main__":
    unittest.main()
