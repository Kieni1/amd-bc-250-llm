from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/check-upstream-patches.py"
SPEC = importlib.util.spec_from_file_location("bc250_check_upstream_patches", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)


class UpstreamPatchContractTests(unittest.TestCase):
    def test_live_manager_pin_matches_notice(self):
        pin = checks.load_live_manager_pin(ROOT)
        self.assertEqual(
            pin["commit"], "a929085d791f126ce76a60eb609610820fb08066"
        )
        checks.validate_notice_revision(ROOT, str(pin["commit"]))

    def test_stale_notice_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "licenses").mkdir()
            stale = (ROOT / "licenses/THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
            stale = stale.replace(
                "a929085d791f126ce76a60eb609610820fb08066",
                "8eb45f07810af738f3e4945ea0cc29d399e378a6",
            )
            (root / "licenses/THIRD_PARTY_NOTICES.md").write_text(stale, encoding="utf-8")
            with self.assertRaises(checks.ValidationError):
                checks.validate_notice_revision(
                    root, "a929085d791f126ce76a60eb609610820fb08066"
                )

    def test_patched_semantics_reject_old_reboot_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bc250-cu-live-manager.sh"
            path.write_text(
                'SERVICE_BIN="/usr/bin/bc250-cu-live-manager"\n'
                'systemctl reboot\n'
                '[ -x "$SERVICE_BIN" ] || die '
                '"packaged service executable is missing: $SERVICE_BIN"',
                encoding="utf-8",
            )
            with self.assertRaises(checks.ValidationError):
                checks.validate_patched_semantics(path)

    def test_make_sources_runs_patch_validation_after_source_preparation(self):
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn(
            "sources:\n\t./scripts/prepare-sources.py\n\t./scripts/check-upstream-patches.py",
            makefile,
        )
        self.assertIn(
            "sources-check:\n\t./scripts/prepare-sources.py --check\n\t./scripts/check-upstream-patches.py",
            makefile,
        )


if __name__ == "__main__":
    unittest.main()
