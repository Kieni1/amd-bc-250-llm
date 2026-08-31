from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_ollama_0332_think_policy_is_model_specific(self) -> None:
        self.assertEqual(
            generation.resolve_think_policy("prod-gpt-oss20b-x", "auto"), "medium"
        )
        self.assertEqual(
            generation.resolve_think_policy("prod-qwen35-9b-unsloth-q6-k", "auto"),
            "false",
        )
        self.assertEqual(
            generation.resolve_think_policy("prod-gemma4-e4b", "auto"), "omit"
        )
        self.assertEqual(
            generation.resolve_think_policy("agentic-ornith15-9b", "auto"), "omit"
        )
        self.assertEqual(
            generation.resolve_think_policy(
                "exp-qwen38-4b-distill-empero-q6-k", "auto"
            ),
            "omit",
        )

    def test_early_stop_only_flags_short_done_reason_stop(self) -> None:
        self.assertIsNone(
            generation.early_stop_warning(
                {"eval_count": 28, "done_reason": "length"}, 384, 0.10
            )
        )
        self.assertIsNotNone(
            generation.early_stop_warning(
                {"eval_count": 28, "done_reason": "stop"}, 384, 0.10
            )
        )
        self.assertIsNone(
            generation.early_stop_warning(
                {"eval_count": 204, "done_reason": "stop"}, 512, 0.10
            )
        )

    def test_reasoning_latency_budget_and_prompt_variants_are_explicit(self) -> None:
        self.assertEqual(generation.latency_budget(96, 512, "false", "prod-qwen35-9b"), 96)
        self.assertEqual(generation.latency_budget(96, 512, "false", "prod-lfm25-8b"), 512)
        self.assertEqual(generation.latency_budget(96, 512, "medium", "prod-gpt-oss20b"), 512)
        self.assertEqual(generation.latency_budget(96, 512, "omit", "prod-gemma4-e2b"), 512)
        first = generation.prompt_variant("Prompt", 0)
        second = generation.prompt_variant("Prompt", 1)
        self.assertNotEqual(first, second)
        self.assertTrue(first.lstrip("\n").startswith("Prompt"))
        self.assertNotIn("reqid", first.casefold())

    def test_chat_budget_and_context_warnings_are_persistable(self) -> None:
        self.assertIsNotNone(
            generation.answer_budget_warning(
                {"answer_started": False, "done_reason": "length"}, 512
            )
        )
        self.assertIsNone(
            generation.answer_budget_warning(
                {"answer_started": True, "done_reason": "length"}, 512
            )
        )
        self.assertIsNone(generation.context_truncation_warning(100, 200))
        self.assertIn(
            "possible context truncation",
            generation.context_truncation_warning(200, 180),
        )
        for field in ("answer_started", "answer_chars", "thinking_chars"):
            self.assertIn(field, generation.CSV_FIELDS)

    def test_ollama_0330_prompt_cache_fix_does_not_warm_context_curve(self) -> None:
        source = (BENCH / "generation-benchmark.py").read_text(encoding="utf-8")
        self.assertIn('"prefill_cache_mode": "cold-runner"', source)
        self.assertGreaterEqual(source.count("client.ensure_unloaded(model)"), 4)


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
        prompt = category.OCR_PROMPTS["ovis"].lower()
        self.assertIn("preserve", prompt)
        self.assertIn("translat", prompt)
        self.assertIn("tables as html", prompt)
        self.assertEqual(set(category.OCR_PROMPTS), {"glm", "ovis"})

    def test_fixtures_cover_multilingual_office_categories(self) -> None:
        embed = json.loads(
            (ROOT / "examples/benchmark/embedding-office.json").read_text(
                encoding="utf-8"
            )
        )
        task = json.loads(
            (ROOT / "examples/benchmark/task-cases.json").read_text(encoding="utf-8")
        )
        ocr = json.loads(
            (ROOT / "examples/benchmark/ocr/manifest.json").read_text(encoding="utf-8")
        )
        agent = json.loads(
            (ROOT / "examples/benchmark/agent-cases.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(embed["documents"]), 9)
        self.assertTrue(any(query.get("kind") == "cross" for query in embed["queries"]))
        self.assertIn("de-kuendigung-alt", {doc["id"] for doc in embed["documents"]})
        self.assertIn("q-current-lease", {query["id"] for query in embed["queries"]})
        self.assertEqual({case["language"] for case in task}, {"de", "fr", "en"})
        self.assertTrue({"de", "fr"} <= {case["language"] for case in ocr})
        for case in ocr:
            self.assertTrue((ROOT / "examples/benchmark/ocr" / case["file"]).is_file())
        self.assertEqual(
            {case["validator"] for case in agent}, {"bash", "python", "json"}
        )
        usecase = json.loads(
            (ROOT / "examples/benchmark/usecase-office.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(usecase), 5)
        self.assertEqual(
            {case["model"] for case in usecase},
            {
                "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl",
                "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl",
                "prod-lfm25-8b-a1b-liquidai-q6-k",
                "prod-qwen35-9b-unsloth-q6-k",
                "prod-gpt-oss20b-ggml-org-mxfp4",
            },
        )
        qwen = next(case for case in usecase if "qwen35" in case["model"])
        self.assertIs(qwen["think"], False)
        lfm = next(case for case in usecase if "lfm25" in case["model"])
        self.assertNotIn("translate", lfm["prompt"].casefold())

    def test_agent_validators_check_syntax_and_requirements_without_execution(
        self,
    ) -> None:
        bash_case = {"id": "b", "validator": "bash", "required": ["echo"]}
        self.assertEqual(
            category.validate_agent_output("echo ok", bash_case)[:2], (True, True)
        )
        self.assertEqual(category.validate_agent_output("if then", bash_case)[0], False)
        py_case = {"id": "p", "validator": "python", "required": ["def run"]}
        self.assertEqual(
            category.validate_agent_output("def run():\n    return 1", py_case)[:2],
            (True, True),
        )
        json_case = {"id": "j", "validator": "json", "required": ["summary"]}
        self.assertEqual(
            category.validate_agent_output('{"summary":"ok"}', json_case)[:2],
            (True, True),
        )

    def test_usecase_acceptance_checks_required_any_and_forbidden(self) -> None:
        case = {
            "required": ["AB-42"],
            "required_any": ["vendredi", "documents"],
            "forbidden": ["Unterlagen bis Freitag"],
        }
        self.assertTrue(category._acceptance_ok("Documents vendredi AB-42", case)[0])
        self.assertFalse(category._acceptance_ok("AB-42 Unterlagen bis Freitag", case)[0])

    def test_ocr_score_tracks_required_field_order(self) -> None:
        case = {"expected_text": "A B C", "required_fields": ["A", "B", "C"]}
        self.assertEqual(category.ocr_scores("A B C", case)[5], 1.0)
        self.assertLess(category.ocr_scores("C B A", case)[5], 1.0)

    def test_ocr_score_penalizes_hallucinated_extra_text(self) -> None:
        case = {
            "expected_text": "Invoice 4821 Total CHF 319.50",
            "required_fields": ["4821", "319.50"],
        }
        exact = category.ocr_scores(case["expected_text"], case)
        noisy = category.ocr_scores(
            case["expected_text"] + " invented unrelated paragraph with extra values",
            case,
        )
        self.assertEqual(exact[0], 1.0)
        self.assertLess(noisy[0], exact[0])  # precision
        self.assertLess(noisy[2], exact[2])  # F1
        self.assertLess(noisy[3], exact[3])  # normalized character similarity
        self.assertEqual(noisy[4], 1.0)  # exact required fields still present

    def test_task_prompts_follow_open_webui_0112_windows_and_shapes(self) -> None:
        messages = [{"role": "user", "content": f"m{i}"} for i in range(7)]
        title = category.task_prompt({"type": "title", "messages": messages})
        tags = category.task_prompt({"type": "tags", "messages": messages})
        query = category.task_prompt({"type": "query", "messages": messages})
        self.assertNotIn("m4", title)
        self.assertIn("m5", title)
        self.assertNotIn("m0", tags)
        self.assertIn("m1", tags)
        self.assertIn("1-3 broad theme tags plus 1-3 specific", tags)
        self.assertIn('["General"]', tags)
        self.assertIn("Today's date is", query)
        self.assertIn("err on the side", query)

    def test_task_json_parser_matches_open_webui_fenced_json_tolerance(self) -> None:
        fenced = '```json\n{"title":"Open WebUI PDF extraction"}\n```'
        self.assertEqual(category.parse_json_object(fenced), {"title": "Open WebUI PDF extraction"})
        self.assertFalse(category.strict_json_object(fenced))
        self.assertTrue(category.strict_json_object('{"title":"ok"}'))

    def test_task_language_hint_is_informational(self) -> None:
        self.assertEqual(category.task_language_hint("Datenschutz und Dokument Analyse", "de"), "match")
        self.assertEqual(category.task_language_hint("privacy and document analysis", "de"), "other")

    def test_agent_empty_final_is_not_syntax_success_and_budgets_allow_reasoning(self) -> None:
        case = {"id": "b", "validator": "bash", "required": ["echo"]}
        self.assertEqual(category.validate_agent_output("", case)[:2], (False, False))
        cases = json.loads((ROOT / "examples/benchmark/agent-cases.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(min(item["num_predict"] for item in cases), 768)
        source = (BENCH / "category-benchmark.py").read_text(encoding="utf-8")
        agent = source.split("def benchmark_agent", 1)[1].split("OCR_PROMPTS", 1)[0]
        for field in ("thinking_chars", "answer_started", 'response.get("eval_count"', 'response.get("done_reason"'):
            self.assertIn(field, agent)

    def test_agent_lane_inherits_service_sampling_and_keepalive(self) -> None:
        case = {"num_predict": 256}
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENT_TEMPERATURE", None)
            self.assertEqual(category.agent_options(case), {"num_predict": 256})
        with patch.dict(os.environ, {"AGENT_TEMPERATURE": "0"}, clear=False):
            self.assertEqual(
                category.agent_options(case), {"num_predict": 256, "temperature": 0.0}
            )
        source = (BENCH / "category-benchmark.py").read_text(encoding="utf-8")
        agent = source.split("def benchmark_agent", 1)[1].split("OCR_PROMPTS", 1)[0]
        self.assertNotIn('"keep_alive": KEEP_ALIVE', agent)
        self.assertIn("client.ensure_unloaded(model)", agent)

    def test_client_normalizes_ollama_host_and_falls_back_when_cli_stop_fails(
        self,
    ) -> None:
        client = common.OllamaClient("127.0.0.1:11434")
        self.assertEqual(client.base_url, "http://127.0.0.1:11434")
        with (
            patch.object(
                common.subprocess, "run", return_value=SimpleNamespace(returncode=1)
            ),
            patch.object(client, "json_request", return_value={}) as http_stop,
        ):
            self.assertTrue(client.stop("model"))
            http_stop.assert_called_once()

    def test_confirmed_unload_is_required_for_cold_measurements(self) -> None:
        client = common.OllamaClient("http://127.0.0.1:11434")
        with (
            patch.object(client, "model_loaded", return_value=True),
            patch.object(client, "stop", return_value=True),
            patch.object(client, "wait_unloaded", return_value=False),
            self.assertRaises(common.BenchmarkError),
        ):
            client.ensure_unloaded("model", timeout=0.01)
        with (
            patch.object(client, "model_loaded", return_value=False),
            patch.object(client, "stop") as stop,
        ):
            client.ensure_unloaded("model", timeout=0.01)
            stop.assert_not_called()


class TelemetryTests(unittest.TestCase):
    def test_percentile_interpolates_and_empty_summary_is_safe(self) -> None:
        self.assertEqual(common.percentile([1.0], 95), 1.0)
        self.assertAlmostEqual(common.percentile([1.0, 2.0, 3.0, 4.0], 50), 2.5)
        empty = common.empty_telemetry()
        self.assertEqual(empty["seconds_ge_85c"], 0.0)
        self.assertIsNone(empty["temp_max_c"])

    def test_telemetry_selects_one_amd_drm_device_and_edge_sensor(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.dict(os.environ, {}, clear=False),
        ):
            os.environ.pop("BC250_DRM_CARD", None)
            drm = Path(temporary)
            intel = drm / "card0/device"
            intel.mkdir(parents=True)
            (intel / "vendor").write_text("0x8086\n")

            amd = drm / "card1/device"
            (amd / "hwmon/hwmon0").mkdir(parents=True)
            (amd / "vendor").write_text("0x1002\n")
            (amd / "boot_vga").write_text("1\n")
            (amd / "pp_dpm_sclk").write_text("0: 500Mhz\n1: 1200Mhz *\n")
            (amd / "hwmon/hwmon0/name").write_text("amdgpu\n")
            (amd / "hwmon/hwmon0/temp1_input").write_text("72000\n")
            (amd / "hwmon/hwmon0/temp1_label").write_text("edge\n")
            (amd / "hwmon/hwmon0/temp2_input").write_text("95000\n")
            (amd / "hwmon/hwmon0/temp2_label").write_text("junction\n")

            other = drm / "card2/device"
            other.mkdir(parents=True)
            (other / "vendor").write_text("0x1002\n")
            (other / "boot_vga").write_text("0\n")

            selected = common.discover_amdgpu_device(drm)
            self.assertEqual(selected, amd)
            label, temp = common.amdgpu_edge_temperature(selected)
            self.assertIn("card1/amdgpu/edge", label)
            self.assertEqual(temp, 72.0)
            self.assertEqual(common.current_gpu_clock_mhz(selected), 1200.0)

    def test_cosine_rejects_mismatched_embedding_dimensions(self) -> None:
        with self.assertRaisesRegex(common.BenchmarkError, "dimension mismatch"):
            common.cosine([1.0, 2.0], [1.0])


if __name__ == "__main__":
    unittest.main()
