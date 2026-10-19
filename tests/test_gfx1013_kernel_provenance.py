from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "gfx1013/upstream/check-kernel-provenance.py"
TARGET = "drivers/gpu/drm/amd/amdgpu/example.c"


class Gfx1013KernelProvenanceTests(unittest.TestCase):
    def make_patch_dir(self, root: Path) -> Path:
        patches = root / "patches"
        patches.mkdir()
        (patches / "0001.patch").write_text(
            f"--- a/{TARGET}\n+++ b/{TARGET}\n@@ -1 +1 @@\n-int bc250_example;\n+int bc250_example = 1;\n",
            encoding="utf-8",
        )
        return patches

    def run_check(self, roots: dict[str, str]) -> subprocess.CompletedProcess[str]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        build = root / "BUILD"
        build.mkdir()
        patches = self.make_patch_dir(root)
        for name, content in roots.items():
            target = build / name / TARGET
            target.parent.mkdir(parents=True)
            target.write_text(content, encoding="utf-8")
        output = root / "evidence.txt"
        root_output = root / "prepared-root.txt"
        result = subprocess.run(
            [
                sys.executable,
                str(CHECK),
                "--prepared-build-root",
                str(build),
                "--patch-dir",
                str(patches),
                "--root-output",
                str(root_output),
                "--output",
                str(output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        result.evidence = output.read_text(encoding="utf-8") if output.exists() else ""  # type: ignore[attr-defined]
        result.prepared_root = root_output.read_text(encoding="utf-8").strip() if root_output.exists() else ""  # type: ignore[attr-defined]
        return result

    def test_accepts_one_fedora_prepared_tree_and_hashes_its_targets(self) -> None:
        content = "int bc250_example = 42; /* Fedora %prep result */\n"
        result = self.run_check({"kernel-prepared": content})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mode=fedora-prepared-source", result.evidence)  # type: ignore[attr-defined]
        self.assertIn("prepared_root=kernel-prepared", result.evidence)  # type: ignore[attr-defined]
        self.assertIn(hashlib.sha256(content.encode()).hexdigest(), result.evidence)  # type: ignore[attr-defined]
        self.assertTrue(result.prepared_root.endswith("/BUILD/kernel-prepared"))  # type: ignore[attr-defined]

    def test_rejects_missing_prepared_target_tree(self) -> None:
        result = self.run_check({})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one source tree", result.stderr)

    def test_rejects_ambiguous_fedora_prepared_trees(self) -> None:
        result = self.run_check({"tree-a": "int bc250_example;\n", "tree-b": "int bc250_example;\n"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("found 2", result.stderr)


if __name__ == "__main__":
    unittest.main()
