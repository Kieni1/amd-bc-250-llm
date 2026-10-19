from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WorkflowSmokeTests(unittest.TestCase):
    def test_optional_and_operator_workflows_expose_help(self) -> None:
        commands = [
            ["bash", "cmd/maintenance/maintenance.sh", "--help"],
            ["python3", "cmd/openwebui/openwebui-setup.py", "--help"],
            ["bash", "cmd/benchmark/benchmark.sh", "--help"],
            ["python3", "cmd/benchmark/generation-benchmark.py", "--help"],
            ["python3", "cmd/qualification/qualification_inventory.py", "--help"],
            ["python3", "cmd/qualification/resilience_manager.py", "--help"],
            ["python3", "models/rag/rag.py", "--help"],
            ["bash", "models/ocr/bc250-ocr.sh", "--help"],
            ["bash", "cmd/system/ollama-profile.sh", "--help"],
            ["bash", "cmd/system/agent-mode.sh", "--help"],
            ["bash", "uninstall.sh", "--help"],
        ]
        for argv in commands:
            with self.subTest(argv=argv):
                result = subprocess.run(
                    argv, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertTrue(result.stdout.strip())

    def test_public_dispatcher_targets_exist_in_source_tree(self) -> None:
        dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
        for expected in (
            "install", "status", "health", "verify", "version", "model", "rag",
            "ocr", "maintenance", "benchmark", "qualification", "resilience", "reset",
        ):
            self.assertIn(f'"{expected}|', dispatcher)


if __name__ == "__main__":
    unittest.main()
