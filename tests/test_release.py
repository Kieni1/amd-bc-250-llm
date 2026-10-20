from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def make_recipe(target: str) -> str:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(rf"(?ms)^{re.escape(target)}:(.*?)(?=^\S[^\n]*:|\Z)", text)
    if not match:
        raise AssertionError(f"missing Make target: {target}")
    return match.group(0)


class ReleaseContractTests(unittest.TestCase):
    def test_github_is_primary_and_selection_is_explicit(self) -> None:
        contract = json.loads((ROOT / "release-contract.json").read_text(encoding="utf-8"))
        primary = contract["authority"]["primary"]
        self.assertEqual(primary["kind"], "github-actions")
        self.assertEqual(primary["selection_event"], "workflow_dispatch")
        self.assertEqual(primary["selection_record"], "release-selection.json")
        self.assertEqual(contract["authority"]["secondary"]["kind"], "local-reproduction")

    def test_release_gate_keeps_quality_advisory(self) -> None:
        contract = json.loads((ROOT / "release-contract.json").read_text(encoding="utf-8"))
        self.assertFalse(contract["validation"]["advisory_quality"]["blocking"])
        self.assertEqual(
            contract["validation"]["package_critical_tests"],
            [
                "tests/test_core.py",
                "tests/test_packaging.py",
                "tests/test_sources.py",
                "tests/test_upstream_patch_validation.py",
                "tests/test_runtime.py",
                "tests/test_rag.py",
                "tests/test_rag_import.py",
                "tests/test_qualification.py",
            ],
        )
        workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(encoding="utf-8")
        self.assertIn("make release-gate", workflow)
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn("quality-report", workflow)

    def test_release_gate_builds_from_frozen_inputs(self) -> None:
        preflight = make_recipe("release-gate-preflight")
        package = make_recipe("release-gate-package")
        self.assertLess(preflight.index("freeze-rpm-inputs"), preflight.index("check-frozen-source"))
        self.assertIn("RPM_TREE_TARGET=rpm-tree-frozen srpm", package)
        self.assertIn("rebuild-srpm", package)
        self.assertIn("check-rpm-payload", package)
        self.assertNotIn("RPM_TREE_TARGET=rpm-tree-frozen rpm", package)
        self.assertLess(package.index("rebuild-srpm"), package.index("check-rpm-payload"))
        self.assertLess(package.index("check-rpm-payload"), package.index("release-evidence"))

    def test_lint_ignores_generated_and_vendored_trees(self) -> None:
        lint = make_recipe("lint")
        for ignored in ("./sources/*", "./build/*", "./.build/*", "./dist/*", "./rpmbuild/*", "./vendor/*", "./governor-src/*", "./live-manager-src/*"):
            self.assertIn(ignored, lint)

    def test_source_tar_uses_tracked_git_files(self) -> None:
        source = (ROOT / "scripts/make-source-tarball.sh").read_text(encoding="utf-8")
        self.assertIn("git ls-files", source)
        self.assertIn("BC250_BUILD_DIR", source)
        self.assertIn("SOURCE_DATE_EPOCH", source)

    def test_github_source_identity_checks_head(self) -> None:
        source = (ROOT / "scripts/check-release-source.sh").read_text(encoding="utf-8")
        self.assertIn("GITHUB_SHA", source)
        self.assertIn("rev-parse HEAD", source)
        self.assertIn("BC250_REQUIRE_GIT_SOURCE", source)

    def test_release_evidence_schemas_are_current(self) -> None:
        contract = json.loads((ROOT / "release-contract.json").read_text(encoding="utf-8"))
        evidence = contract["evidence"]
        self.assertEqual(evidence["release_evidence_schema"], "bc250.release-evidence.v2")
        self.assertEqual(evidence["release_selection_schema"], "bc250.release-selection.v1")


if __name__ == "__main__":
    unittest.main()
