from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_generation():
    path = ROOT / "cmd/benchmark/generation-benchmark.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("bc250_generation_tests", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GenerationSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.generation = load_generation()

    def test_visible_answer_has_identity(self) -> None:
        identity = self.generation.visible_response_identity("hello", "hidden")
        self.assertEqual(identity["state"], "present")
        self.assertTrue(identity["determinism_eligible"])
        self.assertEqual(identity["sha256"], hashlib.sha256(b"hello").hexdigest())

    def test_thinking_only_never_hashes_empty_visible_answer(self) -> None:
        identity = self.generation.visible_response_identity("", "reasoning")
        self.assertEqual(identity["state"], "thinking-only")
        self.assertFalse(identity["determinism_eligible"])
        self.assertIsNone(identity["sha256"])

    def test_empty_generation_is_incomplete(self) -> None:
        result = self.generation.generation_measurement_semantics(
            {"done_reason": "length", "eval_count": 128},
            requested=128, response="", thinking="reasoning",
        )
        self.assertEqual(result["outcome"], "incomplete")
        self.assertIn("visible-answer-empty", result["diagnostics"])
        self.assertIn("output-budget", result["diagnostics"])

    def test_visible_generation_is_complete(self) -> None:
        result = self.generation.generation_measurement_semantics(
            {"done_reason": "stop", "eval_count": 16},
            requested=128, response="answer", thinking="",
        )
        self.assertEqual(result["outcome"], "pass")
        self.assertEqual(result["diagnostics"], [])

    def test_generation_help_is_available(self) -> None:
        result = subprocess.run(
            ["python3", "cmd/benchmark/generation-benchmark.py", "--help"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("bc250 benchmark generation", result.stdout)


if __name__ == "__main__":
    unittest.main()
