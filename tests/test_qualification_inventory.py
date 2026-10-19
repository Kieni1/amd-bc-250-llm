from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUAL_DIR = ROOT / "cmd/qualification"
sys.path.insert(0, str(QUAL_DIR))
SPEC = importlib.util.spec_from_file_location("qualification_inventory", QUAL_DIR / "qualification_inventory.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class QualificationInventoryTests(unittest.TestCase):
    def test_cleanup_policy_keeps_recent_latest_and_nonterminal_evidence(self) -> None:
        now = datetime.now(UTC)
        rows = []
        for index in range(5):
            rows.append(
                {
                    "kind": "package-gate",
                    "path": f"/tmp/gate-{index}",
                    "created_at": (now - timedelta(days=60 + index)).isoformat(),
                    "terminal": True,
                    "size_bytes": 1,
                }
            )
        rows.append(
            {
                "kind": "resilience",
                "path": "/tmp/incomplete",
                "created_at": (now - timedelta(days=100)).isoformat(),
                "terminal": False,
                "size_bytes": 1,
            }
        )
        chosen = MODULE.clean_candidates(rows, older_than_days=30, keep_latest=2)
        self.assertEqual([row["path"] for row in chosen], ["/tmp/gate-2", "/tmp/gate-3", "/tmp/gate-4"])
        self.assertNotIn("/tmp/incomplete", [row["path"] for row in chosen])

    def test_inventory_scans_package_gate_and_resilience_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            gate_root = base / "gates"
            res_root = base / "resilience"
            for path in (gate_root, res_root):
                path.mkdir()
            gate = gate_root / "gate-a"
            gate.mkdir()
            identity = {"example": "identity"}
            (gate / "gate.json").write_text(
                json.dumps({"created_at": "2026-10-01T00:00:00Z", "result": "PASS", "qualification_identity": identity}),
                encoding="utf-8",
            )
            res = res_root / "campaign-a"
            res.mkdir()
            (res / "state.json").write_text(
                json.dumps({"created_at": "2026-10-02T00:00:00Z", "result": "PASS", "phase": "complete", "qualification_identity": identity}),
                encoding="utf-8",
            )
            old = (MODULE.PACKAGE_GATE_ROOT, MODULE.RESILIENCE_ROOT, MODULE.KNOWN_ROOTS, MODULE.current_context)
            try:
                MODULE.PACKAGE_GATE_ROOT = gate_root
                MODULE.RESILIENCE_ROOT = res_root
                MODULE.KNOWN_ROOTS = {"package-gate": gate_root, "resilience": res_root}
                MODULE.current_context = lambda: identity
                rows = MODULE.inventory()
            finally:
                (MODULE.PACKAGE_GATE_ROOT, MODULE.RESILIENCE_ROOT, MODULE.KNOWN_ROOTS, MODULE.current_context) = old
            self.assertEqual({row["kind"] for row in rows}, {"package-gate", "resilience"})
            self.assertTrue(all(row["applicability"] == "CURRENT" for row in rows))

    def test_cleanup_path_must_be_direct_child_of_owned_root_and_not_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "gates"
            root.mkdir()
            child = root / "gate-a"
            child.mkdir()
            outside = Path(temporary) / "outside"
            outside.mkdir()
            link = root / "gate-link"
            link.symlink_to(outside, target_is_directory=True)
            old_roots = MODULE.KNOWN_ROOTS
            try:
                MODULE.KNOWN_ROOTS = {"package-gate": root}
                self.assertTrue(MODULE.safe_candidate(child, "package-gate"))
                self.assertFalse(MODULE.safe_candidate(link, "package-gate"))
                self.assertFalse(MODULE.safe_candidate(outside, "package-gate"))
            finally:
                MODULE.KNOWN_ROOTS = old_roots


if __name__ == "__main__":
    unittest.main()
