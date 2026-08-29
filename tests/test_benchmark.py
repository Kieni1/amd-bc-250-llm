from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "cmd/benchmark"
sys.path.insert(0, str(BENCH))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = load_module("benchmark_common_test", BENCH / "benchmark_common.py")
generation = load_module("generation_benchmark_test", BENCH / "generation-benchmark.py")
category = load_module("category_benchmark_test", BENCH / "category-benchmark.py")


class GenerationPolicyTests(unittest.TestCase):
    def test_neutral_generate_overrides_system_without_raw_mode(self) -> None:
        payload = generation.generate_payload(
            "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl",
            "test",
            128,
            "neutral",
            "omit",
            "30m",
        )
        self.assertEqual(payload["system"], generation.NEUTRAL_SYSTEM)
        self.assertEqual(payload["options"], {"temperature": 0, "num_predict": 128})
        self.assertNotIn("raw", payload)
        self.assertNotIn("think", payload)

    def test_production_generate_preserves_modelfile_sampling_and_system(self) -> None:
        payload = generation.generate_payload(
            "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl",
            "test",
            128,
            "production",
            "omit",
            "30m",
        )
        self.assertNotIn("system", payload)
        self.assertEqual(payload["options"], {"num_predict": 128})
        self.assertNotIn("temperature", payload["options"])

    def test_ollama_03215_think_policy_is_model_specific(self) -> None:
        self.assertEqual(generation.resolve_think_policy("prod-gpt-oss20b-x", "auto"), "medium")
        self.assertEqual(generation.resolve_think_policy("prod-qwen35-9b-unsloth-q6-k", "auto"), "false")
        self.assertEqual(generation.resolve_think_policy("prod-gemma4-e4b", "auto"), "omit")
        self.assertEqual(generation.resolve_think_policy("agentic-ornith15-9b", "auto"), "omit")
        self.assertEqual(generation.resolve_think_policy("exp-qwen35-9b-davidau-defiant-fable", "auto"), "omit")

    def test_early_stop_only_flags_short_done_reason_stop(self) -> None:
        self.assertIsNone(generation.early_stop_warning({"eval_count": 28, "done_reason": "length"}, 384, 0.9))
        self.assertIsNotNone(generation.early_stop_warning({"eval_count": 28, "done_reason": "stop"}, 384, 0.9))
        self.assertIsNone(generation.early_stop_warning({"eval_count": 380, "done_reason": "stop"}, 384, 0.9))


class CategoryPolicyTests(unittest.TestCase):
    def test_embedding_prefixes_match_packaged_rag_policy(self) -> None:
        q, d, scheme = category.embedding_scheme("embed-jina-v5-small-retrieval-q4-k-m")
        self.assertEqual((q, d, scheme), ("Query: ", "Document: ", "jina-v5"))
        q, d, scheme = category.embedding_scheme("embed-qwen3-0.6b-q8-0")
        self.assertIn("German, French, and English office documents", q)
        self.assertEqual(d, "")
        self.assertEqual(scheme, "qwen3-embedding")

    def test_ocr_prompts_preserve_source_language_and_structure(self) -> None:
        self.assertEqual(category.OCR_PROMPTS["glm"], "Text Recognition:")
        for kind in ("dots", "ovis", "chandra"):
            prompt = category.OCR_PROMPTS[kind].lower()
            self.assertIn("preserve", prompt)
            self.assertIn("translat", prompt)
        self.assertIn("tables as html", category.OCR_PROMPTS["ovis"].lower())

    def test_fixtures_cover_multilingual_office_categories(self) -> None:
        embed = json.loads((ROOT / "examples/benchmark/embedding-office.json").read_text(encoding="utf-8"))
        task = json.loads((ROOT / "examples/benchmark/task-cases.json").read_text(encoding="utf-8"))
        ocr = json.loads((ROOT / "examples/benchmark/ocr/manifest.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(embed["documents"]), 6)
        self.assertTrue(any(query.get("kind") == "cross" for query in embed["queries"]))
        self.assertEqual({case["language"] for case in task}, {"de", "fr", "en"})
        self.assertTrue({"de", "fr"} <= {case["language"] for case in ocr})
        for case in ocr:
            self.assertTrue((ROOT / "examples/benchmark/ocr" / case["file"]).is_file())


class TelemetryTests(unittest.TestCase):
    def test_percentile_interpolates_and_empty_summary_is_safe(self) -> None:
        self.assertEqual(common.percentile([1.0], 95), 1.0)
        self.assertAlmostEqual(common.percentile([1.0, 2.0, 3.0, 4.0], 50), 2.5)
        empty = common.empty_telemetry()
        self.assertEqual(empty["seconds_ge_85c"], 0.0)
        self.assertIsNone(empty["temp_max_c"])


if __name__ == "__main__":
    unittest.main()
