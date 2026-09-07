from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
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
runtime_workflow = load_module("runtime_benchmark_test", BENCH / "runtime-benchmark.py")
openwebui_workflow = load_module("openwebui_benchmark_test", BENCH / "openwebui-benchmark.py")


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
        self.assertIn('bool_setting("RUN_WARM_PREFIX", False)', source)
        self.assertIn('"prefix_warm"', source)


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
        self.assertIn("table row", prompt)
        self.assertNotIn("tables as html", prompt)
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
        translation = json.loads(
            (ROOT / "examples/benchmark/translation-office.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(translation), 8)
        self.assertEqual(
            {(case["source_language"], case["target_language"]) for case in translation},
            {("de", "fr"), ("fr", "de")},
        )
        rag_quality = json.loads(
            (ROOT / "examples/benchmark/rag-quality-office.json").read_text(encoding="utf-8")
        )
        self.assertEqual(rag_quality["corpus_file"], "embedding-office.json")
        self.assertGreaterEqual(len(rag_quality["cases"]), 4)

    def test_agent_validators_check_syntax_and_requirements_without_execution(
        self,
    ) -> None:
        bash_case = {"id": "b", "validator": "bash", "required": ["echo"]}
        result = category.evaluate_agent_output("echo ok", bash_case)
        self.assertTrue(result["syntax_ok"])
        self.assertTrue(result["requirements_ok"])
        result = category.evaluate_agent_output("if then", bash_case)
        self.assertFalse(result["syntax_ok"])

        py_case = {"id": "p", "validator": "python", "required": ["def run"]}
        result = category.evaluate_agent_output("def run():\n    return 1", py_case)
        self.assertTrue(result["syntax_ok"])
        self.assertTrue(result["requirements_ok"])

        json_case = {"id": "j", "validator": "json", "required": ["summary"]}
        result = category.evaluate_agent_output('{"summary":"ok"}', json_case)
        self.assertTrue(result["syntax_ok"])
        self.assertTrue(result["requirements_ok"])

        strict_case = {
            "id": "strict",
            "validator": "python",
            "required": ["raise ValueError"],
            "raw_only": True,
        }
        strict = category.evaluate_agent_output("```python\nraise ValueError\n```", strict_case)
        self.assertTrue(strict["syntax_ok"])
        self.assertTrue(strict["requirements_ok"])
        self.assertFalse(strict["format_ok"])
        self.assertFalse(strict["accepted"])

        safe_bash = {
            "id": "safe",
            "validator": "bash",
            "required": ["find"],
            "required_any": [["-printf", "-print0"]],
        }
        result = category.evaluate_agent_output("find . -maxdepth 1 -print", safe_bash)
        self.assertTrue(result["syntax_ok"])
        self.assertFalse(result["requirements_ok"])

        typed_json = {
            "id": "typed",
            "validator": "json",
            "json_keys": ["files", "commands"],
            "json_array_keys": ["files", "commands"],
        }
        result = category.evaluate_agent_output('{"files":[],"commands":[]}', typed_json)
        self.assertTrue(result["syntax_ok"])
        self.assertTrue(result["requirements_ok"])
        result = category.evaluate_agent_output(
            '{"files":"bad","commands":[]}', typed_json
        )
        self.assertTrue(result["syntax_ok"])
        self.assertFalse(result["requirements_ok"])

    def test_agent_python_contract_is_scoped_to_requested_function(self) -> None:
        case = next(
            item
            for item in json.loads(
                (ROOT / "examples/benchmark/agent-cases.json").read_text(encoding="utf-8")
            )
            if item["id"] == "python-port-parser"
        )
        adversarial = """\
def parse_ports(value: str) -> list[int]:
    return [80]

def split():
    pass

split()
sorted([])
raise ValueError
"""
        result = category.evaluate_agent_output(adversarial, case)
        self.assertTrue(result["syntax_ok"])
        self.assertFalse(result["requirements_ok"])
        self.assertIn("missing call: split", result["problems"])
        self.assertIn("missing comparison boundary: 65535", result["problems"])

        nested = """\
def parse_ports(value: str) -> list[int]:
    def dead():
        value.split(",")
        sorted([])
        if not 1 <= 2 <= 65535:
            raise ValueError
        return set()
    return [80]
"""
        nested_result = category.evaluate_agent_output(nested, case)
        self.assertFalse(nested_result["requirements_ok"])
        self.assertIn("missing duplicate removal", nested_result["problems"])

    def test_agent_python_contract_requires_dedup_and_associated_range_raise(self) -> None:
        case = next(
            item
            for item in json.loads(
                (ROOT / "examples/benchmark/agent-cases.json").read_text(encoding="utf-8")
            )
            if item["id"] == "python-port-parser"
        )
        duplicate_preserving = """\
def parse_ports(value: str) -> list[int]:
    out = []
    for item in value.split(","):
        if not item:
            continue
        port = int(item)
        if not 1 <= port <= 65535:
            raise ValueError
        out.append(port)
    return sorted(out)
"""
        result = category.evaluate_agent_output(duplicate_preserving, case)
        self.assertFalse(result["requirements_ok"])
        self.assertIn("missing duplicate removal", result["problems"])

        unrelated_raise = """\
def parse_ports(value: str) -> list[int]:
    ports = set()
    for item in value.split(","):
        port = int(item)
        if 1 <= port <= 65535:
            ports.add(port)
    if value == "never":
        raise ValueError
    return sorted(ports)
"""
        result = category.evaluate_agent_output(unrelated_raise, case)
        self.assertFalse(result["requirements_ok"])
        self.assertIn("missing associated range guard", " ".join(result["problems"]))

        inverted_range = """\
def parse_ports(value: str) -> list[int]:
    ports = set()
    for item in value.split(","):
        port = int(item)
        if 1 <= port <= 65535:
            raise ValueError
        ports.add(port)
    return sorted(ports)
"""
        result = category.evaluate_agent_output(inverted_range, case)
        self.assertFalse(result["requirements_ok"])
        self.assertIn("missing associated range guard", " ".join(result["problems"]))

        good = """\
def parse_ports(value: str) -> list[int]:
    ports = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        port = int(item)
        if not 1 <= port <= 65535:
            raise ValueError
        ports.add(port)
    return sorted(ports)
"""
        self.assertTrue(category.evaluate_agent_output(good, case)["accepted"])

    def test_agent_bash_contract_rejects_token_only_false_positive(self) -> None:
        case = next(
            item
            for item in json.loads(
                (ROOT / "examples/benchmark/agent-cases.json").read_text(encoding="utf-8")
            )
            if item["id"] == "bash-model-list"
        )
        bad = '#!/usr/bin/env bash\necho "$1/*.Modelfile" | sort\nexit 2\n'
        result = category.evaluate_agent_output(bad, case)
        self.assertTrue(result["syntax_ok"])
        self.assertFalse(result["requirements_ok"])
        self.assertIn("missing guarded argument check with exit 2", result["problems"])
        self.assertIn("missing basename extraction", result["problems"])

        detached_exit = """\
#!/usr/bin/env bash
if [ -n "$1" ]; then
    echo ok >/dev/null
fi
dir="$1"
shopt -s nullglob
for path in "$dir"/*.Modelfile; do
    basename "$path"
done | sort
exit 2
"""
        result = category.evaluate_agent_output(detached_exit, case)
        self.assertFalse(result["requirements_ok"])
        self.assertIn("missing guarded argument check with exit 2", result["problems"])

        unsafe_empty_glob = """\
#!/usr/bin/env bash
if [ "$#" -ne 1 ]; then
    exit 2
fi
dir="$1"
for path in "$dir"/*.Modelfile; do
    basename "$path"
done | sort
"""
        result = category.evaluate_agent_output(unsafe_empty_glob, case)
        self.assertFalse(result["requirements_ok"])
        self.assertIn("glob is not safe when no Modelfile matches", result["problems"])

        good = """\
#!/usr/bin/env bash
if [ "$#" -ne 1 ]; then
    exit 2
fi
dir="$1"
shopt -s nullglob
for path in "$dir"/*.Modelfile; do
    basename "$path"
done | sort
"""
        self.assertTrue(category.evaluate_agent_output(good, case)["accepted"])

        find_good = """\
#!/usr/bin/env bash
if [ "$#" -ne 1 ]; then
    exit 2
fi
find "$1" -maxdepth 1 -type f -name '*.Modelfile' -printf '%f\n' | sort
"""
        self.assertTrue(category.evaluate_agent_output(find_good, case)["accepted"])

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

    def test_ocr_structure_score_tracks_local_row_association(self) -> None:
        case = {
            "expected_text": "Item A 1 September IT Item B 2 September HR",
            "required_fields": ["Item A", "Item B"],
            "structure_groups": [["Item A", "1 September", "IT"]],
            "structure_window": 80,
        }
        self.assertEqual(category.ocr_scores("Item A 1 September IT", case)[6], 1.0)
        self.assertEqual(category.ocr_scores("Item A " + "x " * 100 + "1 September IT", case)[6], 0.0)
        self.assertEqual(category.ocr_table_signal("<table><tr><td>A</td></tr></table>"), 1.0)

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


    def test_task_semantic_groups_gate_relevance_without_wrapper_text(self) -> None:
        parsed = {"queries": ["privacy policy", "cloud storage confidentiality"]}
        value = category.task_value_text(parsed, "query")
        matched, total = category.semantic_groups_score(
            value, [["personaldaten", "personenbezogen"], ["cloud"], ["datenschutz"]]
        )
        self.assertEqual((matched, total), (1, 3))
        self.assertEqual(category.task_language_hint(value, "de"), "other")

    def test_translation_identifier_fragment_is_not_meaningful_translation(self) -> None:
        fragment = "AB-42 4 septembre 2026"
        self.assertLess(len(common.normalize_words(fragment)), 6)
        self.assertEqual(category.task_language_hint(fragment, "fr"), "unknown")

    def test_usecase_weekday_reasoning_allows_valid_intermediate_tuesday(self) -> None:
        cases = json.loads((ROOT / "examples/benchmark/usecase-office.json").read_text(encoding="utf-8"))
        case = next(item for item in cases if item["id"] == "reasoning-gpt-oss")
        self.assertTrue(
            category._acceptance_ok(
                "Wednesday. Tuesday is the first working day; Wednesday is the second.",
                case,
            )[0]
        )

    def test_usecase_common_record_construction_has_no_duplicate_keys(self) -> None:
        case = {"id": "office", "prompt": "Prompt"}
        row = {
            "timestamp": "2026-09-06T12:00:00+02:00",
            "case_id": "office",
            "model": "prod-test",
        }
        record = category._usecase_result_record(
            case=case,
            model="prod-test",
            row=row,
            ok=True,
            problems=[],
            content="answer",
            thinking="",
            telemetry={},
            wall=1.25,
            done_reason="stop",
        )
        self.assertEqual(record["case_id"], "office")
        self.assertEqual(record["model"], "prod-test")
        self.assertEqual(record["outcome"], "pass")

    def test_embedding_qualification_uses_fixture_aggregate_policy(self) -> None:
        fixture = json.loads(
            (ROOT / "examples/benchmark/embedding-office.json").read_text(encoding="utf-8")
        )
        policy = fixture["qualification"]
        measured = {"recall_at_3": 1.0, "mrr": 0.9231, "hard_recall_at_1": 0.5}
        self.assertTrue(all(category.embedding_qualification_checks(measured, policy).values()))
        degraded = dict(measured, mrr=0.70)
        self.assertFalse(category.embedding_qualification_checks(degraded, policy)["mrr"])
        source = (BENCH / "category-benchmark.py").read_text(encoding="utf-8")
        self.assertNotIn("query_ok = rank <= 3", source)
        self.assertNotIn('checks={"target_in_top3": rank <= 3}', source)
        self.assertIn('"target_in_top3": rank <= 3', source)

    def test_ocr_markup_is_canonicalized_for_text_fidelity_only(self) -> None:
        plain = "Invoice 4821 Total CHF 319.50"
        marked = "## Invoice 4821\n<table><tr><td>Total</td><td>CHF 319.50</td></tr></table>"
        case = {"expected_text": plain, "required_fields": ["4821", "319.50"]}
        plain_score = category.ocr_scores(plain, case)
        marked_score = category.ocr_scores(marked, case)
        self.assertAlmostEqual(plain_score[2], marked_score[2])
        self.assertAlmostEqual(plain_score[3], marked_score[3])
        self.assertEqual(category.ocr_table_signal(marked), 1.0)

    def test_task_prompts_follow_open_webui_0113_windows_and_shapes(self) -> None:
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

    def test_task_language_hint_supports_required_language_reporting(self) -> None:
        self.assertEqual(category.task_language_hint("Datenschutz und Dokument Analyse", "de"), "match")
        self.assertEqual(category.task_language_hint("privacy and document analysis", "de"), "other")

    def test_agent_empty_final_is_not_syntax_success_and_budgets_allow_reasoning(self) -> None:
        case = {"id": "b", "validator": "bash", "required": ["echo"]}
        result = category.evaluate_agent_output("", case)
        self.assertFalse(result["syntax_ok"])
        self.assertFalse(result["requirements_ok"])
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

    def test_translation_acceptance_normalizes_hyphens_and_locale_numbers(self) -> None:
        actual = "Facture INV‑4821 : CHF 319,50; référence ZH‑204."
        self.assertIn(category.acceptance_text("INV-4821"), category.acceptance_text(actual))
        self.assertIn(category.acceptance_text("CHF 319.50"), category.acceptance_text(actual))
        self.assertIn(category.acceptance_text("ZH-204"), category.acceptance_text(actual))

    def test_translation_source_leakage_is_not_mislabeled_as_language(self) -> None:
        failures = category.translation_failure_kinds(
            "Texte français avec une phrase source.",
            language_ok=True,
            source_leakage_ok=False,
            semantic_ok=True,
            preserved_ok=True,
        )
        self.assertEqual(failures, ["source-leakage"])

    def test_translation_direction_can_be_made_explicit_for_ab_comparison(self) -> None:
        case = {"source_language": "fr", "target_language": "de", "input": "Bonjour."}
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRANSLATION_EXPLICIT_DIRECTION", None)
            self.assertEqual(category.translation_prompt(case), "Bonjour.")
        with patch.dict(os.environ, {"TRANSLATION_EXPLICIT_DIRECTION": "1"}, clear=False):
            prompt = category.translation_prompt(case)
            self.assertIn("French to German", prompt)
            self.assertTrue(prompt.endswith("Bonjour."))

    def test_task_and_agent_benchmarks_return_quality_status(self) -> None:
        source = (BENCH / "category-benchmark.py").read_text(encoding="utf-8")
        task = source.split("def benchmark_task", 1)[1].split("def clean_code_output", 1)[0]
        agent = source.split("def benchmark_agent", 1)[1].split("OCR_PROMPTS", 1)[0]
        self.assertIn("return 0 if passed == total else 3", task)
        self.assertIn("return 0 if passed == total else 3", agent)

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


    def test_common_result_summary_separates_failures_from_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "results.jsonl"
            rows = [
                common.result_record(category="task", model="m", case_id="a", result_type="qualification", outcome="pass"),
                common.result_record(
                    category="task", model="m", case_id="b", result_type="qualification", outcome="quality-fail",
                    failure_kinds=["language"], diagnostics=["output-budget"],
                ),
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            summary_json, summary_txt = common.write_result_summary(path, category="task")
            summary = json.loads(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(summary["infrastructure"], "pass")
            self.assertEqual(summary["quality"], "mixed")
            self.assertEqual(summary["failure_kinds"], {"language": 1})
            self.assertEqual(summary["diagnostics"], {"output-budget": 1})
            self.assertIn("Quality        MIXED", summary_txt.read_text(encoding="utf-8"))

    def test_result_directory_is_canonical_and_refuses_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "task-run"
            paths = common.prepare_result_dir("task", root)
            self.assertEqual(paths.root, root)
            self.assertEqual(paths.results_jsonl, root / "results.jsonl")
            self.assertEqual(paths.summary_json, root / "summary.json")
            self.assertEqual(paths.summary_txt, root / "summary.txt")
            self.assertEqual(paths.meta_json, root / "meta.json")
            self.assertEqual(paths.csv_export, root / "results.csv")
            self.assertTrue(paths.fixtures_dir.is_dir())
            paths.results_jsonl.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(common.BenchmarkError):
                common.prepare_result_dir("task", root)

    def test_common_result_summary_rejects_corrupt_canonical_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "results.jsonl"
            path.write_text('{"schema_version":1,"outcome":"pass"}\nnot-json\n', encoding="utf-8")
            with self.assertRaises(common.BenchmarkError):
                common.write_result_summary(path, category="task")

    def test_telemetry_records_swap_start_peak_end_and_delta(self) -> None:
        fields = common.empty_telemetry()
        for name in ("swap_used_start_mib", "swap_used_max_mib", "swap_used_end_mib", "swap_peak_delta_mib"):
            self.assertIn(name, fields)

    def test_cosine_rejects_mismatched_embedding_dimensions(self) -> None:
        with self.assertRaisesRegex(common.BenchmarkError, "dimension mismatch"):
            common.cosine([1.0, 2.0], [1.0])

    def test_revalidation_v4_is_six_phase_packaged_qualification(self) -> None:
        source = (ROOT / "cmd/benchmark/revalidate.sh").read_text(encoding="utf-8")
        self.assertIn("HARNESS_VERSION=4.0", source)
        start = source.index("run_qualification_sequence() {")
        sequence = source[start:source.index("\nworker() {", start)]
        for phase in ("phase_preflight", "phase_roles", "phase_edge", "phase_agent", "phase_owui", "phase_restore_report"):
            self.assertIn(phase, sequence)
        for obsolete in ("phase_num_batch", "phase_kernel", "phase_governor", "translation-implicit", "translation-explicit", "rag-quality-nonthinking"):
            self.assertNotIn(obsolete, sequence)

    def test_revalidation_run_step_separates_quality_from_infrastructure(self) -> None:
        source = (ROOT / "cmd/benchmark/revalidate.sh").read_text(encoding="utf-8")
        block = source[source.index("run_step() {"):source.index("warm_embedding() {")]
        self.assertIn('[[ "$kind" == quality && $rc -eq 3 ]]', block)
        self.assertIn('record_event "$label" quality quality-fail', block)
        self.assertIn('record_event "$label" infra infra-fail', block)
        self.assertIn('return "$rc"', block)
        self.assertNotIn("restore_all", block)
        self.assertIn("trap - ERR TERM INT", block)

    def test_revalidation_run_step_runtime_rc_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            source = ROOT / "cmd/benchmark/revalidate.sh"
            script = f"""
source \"{source}\" help >/dev/null
RAW=\"{t / 'results'}\"
EVENTS=\"{t / 'events.tsv'}\"
PHASE_FILE=\"{t / 'phase'}\"
STAGE_FILE=\"{t / 'stage'}\"
STAGE_STARTED_FILE=\"{t / 'stage-started'}\"
LAST_EVENT_FILE=\"{t / 'last-event'}\"
mkdir -p \"$RAW\"
printf 'roles\\n' > \"$PHASE_FILE\"
: > \"$EVENTS\"
if run_step test quality-case quality bash -c 'exit 3'; then qrc=0; else qrc=$?; fi
if run_step test infra-case infra bash -c 'exit 7'; then irc=0; else irc=$?; fi
printf 'qrc=%s irc=%s\\n' \"$qrc\" \"$irc\"
"""
            completed = subprocess.run(
                ["bash", "-c", script],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("qrc=0 irc=7", completed.stdout)
            events = (t / "events.tsv").read_text(encoding="utf-8")
            self.assertIn("quality-case\tquality\tquality-fail", events)
            self.assertIn("infra-case\tinfra\tinfra-fail", events)

    def test_revalidation_explicit_partial_coverage_does_not_mean_mixed_quality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            source = ROOT / "cmd/benchmark/revalidate.sh"
            script = f"""
source "{source}" help >/dev/null
EVENTS="{t / 'events.tsv'}"
printf '2026-09-06T12:00:00+02:00\troles\ttask\tquality\tpass\tok\n' > "$EVENTS"
printf '2026-09-06T12:00:01+02:00\towui\topenwebui-rag\tcoverage\tskipped\texplicit skip\n' >> "$EVENTS"
quality_state
"""
            completed = subprocess.run(
                ["bash", "-c", script], text=True, capture_output=True, check=True
            )
            self.assertEqual(completed.stdout.strip(), "pass")

    def test_common_result_quality_uses_qualification_records_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "results.jsonl"
            rows = [
                common.result_record(
                    category="embeddings", model="m", case_id="q1",
                    result_type="measurement", outcome="pass",
                ),
                common.result_record(
                    category="embeddings", model="m", case_id="qualification",
                    result_type="qualification", outcome="quality-fail",
                    failure_kinds=["retrieval"],
                ),
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            summary_json, _ = common.write_result_summary(path, category="embeddings")
            summary = json.loads(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(summary["quality"], "fail")
            self.assertEqual(summary["result_types"], {"measurement": 1, "qualification": 1})
            self.assertEqual(summary["qualification_counts"]["quality-fail"], 1)
            self.assertEqual(summary["failure_kinds"], {"retrieval": 1})

    def test_all_common_result_calls_declare_measurement_or_qualification(self) -> None:
        for path in BENCH.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                    continue
                if node.func.id != "result_record":
                    continue
                keywords = {kw.arg for kw in node.keywords if kw.arg}
                self.assertIn("result_type", keywords, f"{path.name}:{node.lineno}")

    def test_revalidation_package_roles_are_immutable_and_exact(self) -> None:
        source = (ROOT / "cmd/benchmark/revalidate.sh").read_text(encoding="utf-8")
        for model in (
            "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl",
            "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl",
            "prod-lfm25-8b-a1b-liquidai-q6-k",
            "prod-qwen35-9b-unsloth-q6-k",
            "prod-gpt-oss20b-ggml-org-mxfp4",
        ):
            self.assertIn(model, source)
        self.assertIn("readonly -a PACKAGE_PROD_MODELS", source)
        self.assertNotIn("installed_prod_models()", source)
        self.assertNotIn("${GPT_OSS_MODEL:-", source)
        edge = source[source.index("phase_edge() {"):source.index("phase_agent() {")]
        self.assertIn('"${PACKAGE_PROD_MODELS[@]}"', edge)

    def test_revalidation_token_is_validated_before_run_state_without_curl_bearer_argv(self) -> None:
        source = (ROOT / "cmd/benchmark/revalidate.sh").read_text(encoding="utf-8")
        validate = source[source.index("validate_owui_token_file() {"):source.index("api_ready() {")]
        self.assertIn('python3 - "$path"', validate)
        self.assertNotIn("curl", validate)
        start = source[source.index("start_run() {"):source.index("capture_cmd() {")]
        self.assertLess(start.index('validate_owui_token_file "$token_file"'), start.index('rm -rf "$WORK"'))
        self.assertIn("--skip-owui", start)
        self.assertNotIn("OWUI_API_KEY", start)

    def test_edge_sanity_policy_rejects_gross_decode_regression(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            source = ROOT / "cmd/benchmark/revalidate.sh"
            rows = []
            specs = {
                "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl": (100.0, 32768),
                "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl": (60.0, 32768),
                "prod-lfm25-8b-a1b-liquidai-q6-k": (120.0, 32768),
                "prod-qwen35-9b-unsloth-q6-k": (40.0, 32768),
                "prod-gpt-oss20b-ggml-org-mxfp4": (70.0, 16384),
            }
            for model, (tps, context) in specs.items():
                rows.append({
                    "category": "generation", "model": model, "case_id": "short-1",
                    "result_type": "measurement", "outcome": "pass", "diagnostics": [],
                    "metrics": {
                        "tokens_per_second": tps, "allocated_context": context,
                        "resident_size_bytes": 1000, "resident_vram_bytes": 1000,
                        "mem_available_min_mib": 1024, "temp_max_c": 70,
                        "prompt_eval_count": 5000,
                    },
                })
            good = t / "good.jsonl"
            bad = t / "bad.jsonl"
            good.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            rows[0]["metrics"]["tokens_per_second"] = 1.0
            bad.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            script = (
                f'source "{source}" help >/dev/null\n'
                f'write_edge_policy "{t / "policy.json"}"\n'
                f'check_edge_generation_sanity "{good}" "{t / "policy.json"}" "{t / "good-out.json"}"\n'
                f'if check_edge_generation_sanity "{bad}" "{t / "policy.json"}" "{t / "bad-out.json"}" 2>/dev/null; then exit 9; fi\n'
            )
            subprocess.run(["bash", "-c", script], check=True)
            self.assertTrue(json.loads((t / "good-out.json").read_text())["passed"])
            self.assertFalse(json.loads((t / "bad-out.json").read_text())["passed"])

    def test_revalidation_quality_cause_report_reads_canonical_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            result_dir = t / "task" / "results"
            result_dir.mkdir(parents=True)
            (result_dir / "summary.json").write_text(json.dumps({
                "category": "task",
                "qualification_counts": {"pass": 3, "quality-fail": 3, "skipped": 0},
                "failure_kinds": {"language": 2, "relevance": 1},
            }), encoding="utf-8")
            source = ROOT / "cmd/benchmark/revalidate.sh"
            script = f'source "{source}" help >/dev/null\nRAW="{t}"\nquality_cause_report\n'
            completed = subprocess.run(
                ["bash", "-c", script], text=True, capture_output=True, check=True
            )
            self.assertIn("task", completed.stdout)
            self.assertIn("3/6", completed.stdout)
            self.assertIn("language=2", completed.stdout)
            self.assertIn("relevance=1", completed.stdout)

    def test_rag_cycle_residency_loss_is_infrastructure_failure(self) -> None:
        self.assertEqual(category.rag_cycle_outcome(True, False), ("infra-fail", ["coexistence"], 1))
        self.assertEqual(category.rag_cycle_outcome(False, True), ("quality-fail", ["answer"], 3))
        self.assertEqual(category.rag_cycle_outcome(True, True), ("pass", [], 0))

    def test_openwebui_restore_requires_readback_and_cleanup_failures_propagate(self) -> None:
        class FakeClient:
            def __init__(self, restored: dict[str, object]):
                self.restored = restored
            def post(self, _path: str, _payload: object) -> dict[str, object]:
                return {}
            def get(self, _path: str) -> dict[str, object]:
                return self.restored
            def delete(self, _path: str) -> dict[str, object]:
                raise openwebui_workflow.Failure("delete failed")

        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            paths = SimpleNamespace(results_jsonl=t / "results.jsonl")
            expected = {"CHUNK_MIN_SIZE_TARGET": 0}
            good = FakeClient({"CHUNK_MIN_SIZE_TARGET": 0})
            bad = FakeClient({"CHUNK_MIN_SIZE_TARGET": 99})
            self.assertTrue(openwebui_workflow.restore_config(
                good, paths, "owui-chunk-min", "m", "/update", expected,
                "/read", openwebui_workflow.rag_config,
            ))
            self.assertFalse(openwebui_workflow.restore_config(
                bad, paths, "owui-chunk-min", "m", "/update", expected,
                "/read", openwebui_workflow.rag_config,
            ))
            with self.assertRaisesRegex(openwebui_workflow.Failure, "cleanup failed"):
                openwebui_workflow.cleanup_kb(good, "kb", None, "name")


    def test_revalidation_token_survives_restore_through_finalization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            source = ROOT / "cmd/benchmark/revalidate.sh"
            token = t / "owui-token"
            script = f"""
source "{source}" help >/dev/null
OWUI_TOKEN="{token}"
printf secret > "$OWUI_TOKEN"
command_exists() {{ return 1; }}
disable_worker_for_future_boots() {{ :; }}
restore_all
[[ -f "$OWUI_TOKEN" ]] || exit 20
finish_worker_session
[[ ! -e "$OWUI_TOKEN" ]] || exit 21
printf 'ok\n'
"""
            completed = subprocess.run(
                ["bash", "-c", script], text=True, capture_output=True, check=True
            )
            self.assertEqual(completed.stdout.strip(), "ok")

    def test_revalidation_failed_launch_removes_transient_token(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            source = ROOT / "cmd/benchmark/revalidate.sh"
            token = t / "owui-token"
            script = f"""
source "{source}" help >/dev/null
OWUI_TOKEN="{token}"
printf secret > "$OWUI_TOKEN"
install_unit() {{ return 0; }}
systemctl() {{ [[ "$1" != start ]]; }}
if launch_worker; then exit 30; fi
[[ ! -e "$OWUI_TOKEN" ]] || exit 31
printf 'ok\n'
"""
            completed = subprocess.run(
                ["bash", "-c", script], text=True, capture_output=True, check=True
            )
            self.assertEqual(completed.stdout.strip(), "ok")

    def test_revalidation_sanitizes_hostile_benchmark_environment_and_pins_role_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            source = ROOT / "cmd/benchmark/revalidate.sh"
            probe = t / "probe"
            probe.write_text(
                "#!/bin/bash\nprintf '%s|%s|%s|%s\n' \"${TRANSLATION_MODEL-unset}\" \"${TRANSLATION_EXPLICIT_DIRECTION-unset}\" \"${BC250_BENCH_FIXTURES-unset}\" \"${AGENT_TEMPERATURE-unset}\"\n",
                encoding="utf-8",
            )
            probe.chmod(0o755)
            script = f"""
source "{source}" help >/dev/null
export TRANSLATION_MODEL=evil TRANSLATION_EXPLICIT_DIRECTION=1 BC250_BENCH_FIXTURES=/evil AGENT_TEMPERATURE=9
qualification_benchmark "{probe}"
RAW="{t / 'raw'}"
mkdir -p "$RAW/roles"
set_phase() {{ :; }}
warm_embedding() {{ :; }}
snapshot() {{ :; }}
write_phase_report() {{ :; }}
run_step() {{ printf '%s\n' "$*"; }}
phase_roles
"""
            completed = subprocess.run(
                ["bash", "-c", script], text=True, capture_output=True, check=True
            )
            lines = completed.stdout.splitlines()
            self.assertEqual(lines[0], "unset|unset|unset|unset")
            output = "\n".join(lines[1:])
            self.assertIn("translation quality qualification_benchmark bc250-benchmark translation prod-lfm25-8b-a1b-liquidai-q6-k --ollama-url http://127.0.0.1:11434", output)
            self.assertIn("--ollama-url http://127.0.0.1:11437", output)
            self.assertIn("--embedding-ollama-url http://127.0.0.1:11437", output)
            self.assertIn("--ollama-url http://127.0.0.1:11435", output)

    def test_edge_sanity_gates_fail_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            source = ROOT / "cmd/benchmark/revalidate.sh"
            specs = {
                "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl": 32768,
                "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl": 32768,
                "prod-lfm25-8b-a1b-liquidai-q6-k": 32768,
                "prod-qwen35-9b-unsloth-q6-k": 32768,
                "prod-gpt-oss20b-ggml-org-mxfp4": 16384,
            }
            base = []
            for model, context in specs.items():
                base.append({
                    "category": "generation", "model": model, "case_id": "short-1",
                    "result_type": "measurement", "outcome": "pass", "diagnostics": [],
                    "metrics": {
                        "tokens_per_second": 100.0, "allocated_context": context,
                        "resident_size_bytes": 1000, "resident_vram_bytes": 1000,
                        "mem_available_min_mib": 1024, "temp_max_c": 70,
                        "prompt_eval_count": 5000,
                    },
                })
            cases = {
                "residency": lambda row: row["metrics"].update(resident_vram_bytes=100),
                "memory": lambda row: row["metrics"].update(mem_available_min_mib=1),
                "context": lambda row: row["metrics"].update(allocated_context=1024),
                "truncation": lambda row: (row["diagnostics"].append("context-truncation"), row["metrics"].update(prompt_eval_count=1000)),
            }
            for name, mutate in cases.items():
                rows = json.loads(json.dumps(base))
                mutate(rows[0])
                path = t / f"{name}.jsonl"
                path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            script_lines = [
                f'source "{source}" help >/dev/null',
                f'write_edge_policy "{t / "policy.json"}"',
            ]
            for name in cases:
                script_lines.append(
                    f'if check_edge_generation_sanity "{t / (name + ".jsonl")}" "{t / "policy.json"}" "{t / (name + ".out.json")}" 2>/dev/null; then exit 40; fi'
                )
            subprocess.run(["bash", "-c", "\n".join(script_lines)], check=True)
            for name in cases:
                result = json.loads((t / f"{name}.out.json").read_text(encoding="utf-8"))
                self.assertFalse(result["passed"], name)

    def test_initialized_benchmark_failures_finalize_canonical_evidence(self) -> None:
        def assert_failed_run(root: Path, category_name: str) -> None:
            self.assertTrue((root / "results.jsonl").is_file())
            self.assertTrue((root / "summary.json").is_file())
            self.assertTrue((root / "summary.txt").is_file())
            meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
            self.assertIsNotNone(meta["finished_at"])
            rows = [
                json.loads(line)
                for line in (root / "results.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(rows[-1]["category"], category_name)
            self.assertEqual(rows[-1]["outcome"], "infra-fail")
            self.assertEqual(rows[-1]["case_id"], "benchmark-infrastructure-failure")
            summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["infrastructure"], "fail")

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)

            task_dir = base / "task"
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "bc250-benchmark",
                        "task",
                        "test-model",
                        "--output-dir",
                        str(task_dir),
                    ],
                ),
                patch.object(
                    category.OllamaClient,
                    "version",
                    side_effect=category.BenchmarkError("forced task metadata failure"),
                ),
            ):
                self.assertEqual(category.entrypoint(), 1)
            assert_failed_run(task_dir, "task")

            generation_dir = base / "generation"
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "bc250-benchmark generation",
                        "test-model",
                        "--profile",
                        "edge",
                        "--output-dir",
                        str(generation_dir),
                    ],
                ),
                patch.object(generation.OllamaClient, "version", return_value="0.33.3"),
                patch.object(generation.OllamaClient, "show", return_value={}),
                patch.object(
                    generation.OllamaClient,
                    "digest",
                    side_effect=generation.BenchmarkError(
                        "forced generation metadata failure"
                    ),
                ),
            ):
                self.assertEqual(generation.entrypoint(), 1)
            assert_failed_run(generation_dir, "generation")

            runtime_dir = base / "runtime"
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "bc250-benchmark",
                        "num-batch",
                        "test-model",
                        "--output-dir",
                        str(runtime_dir),
                    ],
                ),
                patch.object(
                    runtime_workflow.OllamaClient,
                    "digest",
                    side_effect=runtime_workflow.BenchmarkError(
                        "forced runtime metadata failure"
                    ),
                ),
            ):
                self.assertEqual(runtime_workflow.entrypoint(), 1)
            assert_failed_run(runtime_dir, "num-batch")

            owui_dir = base / "owui"
            token = base / "token"
            token.write_text("secret\n", encoding="utf-8")
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "bc250-benchmark",
                        "owui-embedding-batch",
                        "--token-file",
                        str(token),
                        "--output-dir",
                        str(owui_dir),
                    ],
                ),
                patch.object(
                    openwebui_workflow.JsonClient,
                    "get",
                    side_effect=openwebui_workflow.Failure("forced OWUI failure"),
                ),
            ):
                self.assertEqual(openwebui_workflow.entrypoint(), 1)
            assert_failed_run(owui_dir, "owui-embedding-batch")

    def test_edge_context_floor_rejects_low_context_reload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            source = ROOT / "cmd/benchmark/revalidate.sh"
            specs = {
                "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl": 32768,
                "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl": 32768,
                "prod-lfm25-8b-a1b-liquidai-q6-k": 32768,
                "prod-qwen35-9b-unsloth-q6-k": 32768,
                "prod-gpt-oss20b-ggml-org-mxfp4": 16384,
            }
            rows = []
            for model, context in specs.items():
                rows.append(
                    {
                        "category": "generation",
                        "model": model,
                        "case_id": "short-1",
                        "result_type": "measurement",
                        "outcome": "pass",
                        "diagnostics": [],
                        "metrics": {
                            "tokens_per_second": 100.0,
                            "allocated_context": context,
                            "resident_size_bytes": 1000,
                            "resident_vram_bytes": 1000,
                            "mem_available_min_mib": 1024,
                            "temp_max_c": 70,
                            "prompt_eval_count": 5000,
                        },
                    }
                )
            rows.append(json.loads(json.dumps(rows[0])))
            rows[-1]["case_id"] = "ctx_220"
            rows[-1]["metrics"]["allocated_context"] = 1024
            path = t / "context-reload.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            script = (
                f'source "{source}" help >/dev/null\n'
                f'write_edge_policy "{t / "policy.json"}"\n'
                f'if check_edge_generation_sanity "{path}" '
                f'"{t / "policy.json"}" "{t / "out.json"}" 2>/dev/null; '
                "then exit 41; fi\n"
            )
            subprocess.run(["bash", "-c", script], check=True)
            result = json.loads((t / "out.json").read_text(encoding="utf-8"))
            self.assertFalse(result["passed"])
            check = result["checks"]["prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl"]
            self.assertEqual(check["min_allocated_context"], 1024)

    def test_edge_missing_temperature_telemetry_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            source = ROOT / "cmd/benchmark/revalidate.sh"
            specs = {
                "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl": 32768,
                "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl": 32768,
                "prod-lfm25-8b-a1b-liquidai-q6-k": 32768,
                "prod-qwen35-9b-unsloth-q6-k": 32768,
                "prod-gpt-oss20b-ggml-org-mxfp4": 16384,
            }
            rows = []
            for model, context in specs.items():
                rows.append(
                    {
                        "category": "generation",
                        "model": model,
                        "case_id": "short-1",
                        "result_type": "measurement",
                        "outcome": "pass",
                        "diagnostics": [],
                        "metrics": {
                            "tokens_per_second": 100.0,
                            "allocated_context": context,
                            "resident_size_bytes": 1000,
                            "resident_vram_bytes": 1000,
                            "mem_available_min_mib": 1024,
                            "prompt_eval_count": 5000,
                        },
                    }
                )
            path = t / "missing-temperature.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            script = (
                f'source "{source}" help >/dev/null\n'
                f'write_edge_policy "{t / "policy.json"}"\n'
                f'if check_edge_generation_sanity "{path}" '
                f'"{t / "policy.json"}" "{t / "out.json"}" 2>/dev/null; '
                "then exit 42; fi\n"
            )
            subprocess.run(["bash", "-c", script], check=True)
            result = json.loads((t / "out.json").read_text(encoding="utf-8"))
            self.assertFalse(result["passed"])
            for check in result["checks"].values():
                self.assertFalse(check["temperature_telemetry_present"])
                self.assertIsNone(check["temp_max_c"])

    def test_partial_revalidation_completion_and_status_surface_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            source = ROOT / "cmd/benchmark/revalidate.sh"
            work = t / "work"
            reports = t / "results"
            phases = work / "phase-reports"
            work.mkdir()
            reports.mkdir()
            phases.mkdir()
            bundle = reports / "run-1-bc250-revalidation-results.tar.gz"
            bundle.write_text("bundle\n", encoding="utf-8")
            script = f'''\
source "{source}" help >/dev/null
WORK="{work}"
REPORT_DIR="{reports}"
PHASE_REPORT_DIR="{phases}"
PHASE_FILE="$WORK/phase"
STAGE_FILE="$WORK/stage"
LAST_EVENT_FILE="$WORK/last-event"
STAGE_STARTED_FILE="$WORK/stage-started"
RUN_STATE_FILE="$WORK/run-state"
INFRA_STATE_FILE="$WORK/infrastructure-state"
QUALITY_STATE_FILE="$WORK/quality-state"
RESTORATION_STATE_FILE="$WORK/restoration-state"
RUN_ID_FILE="$WORK/run-id"
RUN_HARNESS_VERSION_FILE="$WORK/harness-version"
COVERAGE_STATE_FILE="$WORK/coverage-state"
ERROR_CONTEXT="$WORK/error-context.txt"
FAILURE_RC_FILE="$WORK/failure-rc"
EVENTS="$WORK/events.tsv"
printf 'done\n' > "$PHASE_FILE"
printf 'complete\n' > "$STAGE_FILE"
printf '2026-09-07T00:00:00+02:00\n' > "$LAST_EVENT_FILE"
printf '2026-09-07T00:00:00+02:00\n' > "$STAGE_STARTED_FILE"
printf 'incomplete\n' > "$RUN_STATE_FILE"
printf 'pass\n' > "$INFRA_STATE_FILE"
printf 'pass\n' > "$QUALITY_STATE_FILE"
printf 'pass\n' > "$RESTORATION_STATE_FILE"
printf 'partial\n' > "$COVERAGE_STATE_FILE"
printf 'run-1\n' > "$RUN_ID_FILE"
printf '4.0\n' > "$RUN_HARNESS_VERSION_FILE"
: > "$EVENTS"
systemctl() {{ echo inactive; }}
follow_run
printf '%s\n' '---STATUS---'
status_run status
printf '%s\n' '---RAW---'
status_raw
'''
            completed = subprocess.run(
                ["bash", "-c", script], text=True, capture_output=True, check=True
            )
            output = completed.stdout.lower()
            self.assertIn("run state:      incomplete", output)
            self.assertIn("coverage:       partial", output)
            self.assertIn("coverage       : partial", output)
            self.assertIn("coverage=partial", output)

    def test_installer_revalidation_guidance_matches_authenticated_harness(self) -> None:
        source = (ROOT / "cmd/system/install.sh").read_text(encoding="utf-8")
        self.assertNotIn(
            'echo "  Revalidation:           sudo bc250-revalidate start"', source
        )
        self.assertIn(
            "sudo bc250-revalidate start --owui-token-file $completion_owui_token",
            source,
        )
        self.assertIn("sudo bc250-revalidate start --owui-token-file FILE", source)
        self.assertIn("sudo bc250-revalidate start --skip-owui", source)

    def test_edge_policy_documents_conservative_threshold_rationale(self) -> None:
        source = (ROOT / "cmd/benchmark/revalidate.sh").read_text(encoding="utf-8")
        self.assertIn("Same-board decode", source)
        self.assertIn("MODELS.md map conservatively", source)
        self.assertIn("major CPU spill", source)
        self.assertIn("unsafe floor rather than desired headroom", source)
        self.assertIn("thermal warning/qualification ceiling", source)

    def test_system_context_restoration_includes_absent_state(self) -> None:
        self.assertTrue(openwebui_workflow.sysctx_restoration_matches("", ""))
        self.assertFalse(openwebui_workflow.sysctx_restoration_matches("", "false"))
        self.assertTrue(openwebui_workflow.sysctx_restoration_matches("false", "FALSE"))

    def test_owui_rag_cleanup_failure_is_classified_as_restoration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            paths = SimpleNamespace(results_jsonl=t / "results.jsonl")
            args = SimpleNamespace(output_dir=None, model="m", url="http://127.0.0.1:3000")
            with (
                patch.object(openwebui_workflow, "prepare_result_dir", return_value=paths),
                patch.object(openwebui_workflow, "owui_client", return_value=object()),
                patch.object(openwebui_workflow, "simple_meta"),
                patch.object(openwebui_workflow, "finish"),
                patch.object(openwebui_workflow, "run_owui_rag_case", side_effect=openwebui_workflow.RestorationFailure("cleanup failed")),
            ):
                self.assertEqual(openwebui_workflow.cmd_owui_rag(args), 1)
            row = json.loads(paths.results_jsonl.read_text(encoding="utf-8"))
            self.assertEqual(row["failure_kinds"], ["restoration"])

    def test_quality_cause_report_surfaces_corrupt_or_missing_canonical_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            result_dir = t / "task" / "results"
            result_dir.mkdir(parents=True)
            (result_dir / "summary.json").write_text("not-json\n", encoding="utf-8")
            events = t / "events.tsv"
            events.write_text(
                "2026-09-06T12:00:00+02:00\troles\ttask\tquality\tquality-fail\tscope=roles rc=3\n",
                encoding="utf-8",
            )
            source = ROOT / "cmd/benchmark/revalidate.sh"
            script = f'source "{source}" help >/dev/null\nRAW="{t}"\nEVENTS="{events}"\nquality_cause_report\n'
            completed = subprocess.run(
                ["bash", "-c", script], text=True, capture_output=True, check=True
            )
            self.assertIn("canonical summary unavailable", completed.stdout)
            self.assertIn("task", completed.stdout)

    def test_revalidation_tracks_liveness_and_progress_without_fake_heartbeat(self) -> None:
        source = (ROOT / "cmd/benchmark/revalidate.sh").read_text(encoding="utf-8")
        self.assertIn("events.tsv", source)
        self.assertIn("STAGE_STARTED_FILE", source)
        self.assertIn("LAST_EVENT_FILE", source)
        self.assertIn("Last event", source)
        self.assertNotIn("HEARTBEAT_FILE", source)
        self.assertNotIn("Heartbeat    ", source)

    def test_revalidation_final_state_separates_run_quality_and_restoration(self) -> None:
        source = (ROOT / "cmd/benchmark/revalidate.sh").read_text(encoding="utf-8")
        for name in ("RUN_STATE_FILE", "INFRA_STATE_FILE", "QUALITY_STATE_FILE", "RESTORATION_STATE_FILE"):
            self.assertIn(name, source)
        summary = source[source.index("create_summary() {"):source.index("create_final_bundle() {")]
        self.assertIn("Run state", summary)
        self.assertIn("Infrastructure", summary)
        self.assertIn("Quality", summary)
        self.assertIn("Restoration", summary)
        self.assertNotIn("PASSED", summary)

    def test_round2b_removes_private_revalidation_tuning_helper(self) -> None:
        source = (ROOT / "cmd/benchmark/revalidate.sh").read_text(encoding="utf-8")
        self.assertNotIn("owui-test-helper.py", source)
        self.assertNotIn("write_helper()", source)
        self.assertIn("bc250-benchmark concurrency", source)
        self.assertIn("bc250-benchmark owui-rag", source)

    def test_round2b_workflows_use_common_results_and_explicit_restoration(self) -> None:
        runtime_source = (ROOT / "cmd/benchmark/runtime-benchmark.py").read_text(encoding="utf-8")
        owui_source = (ROOT / "cmd/benchmark/openwebui-benchmark.py").read_text(encoding="utf-8")
        for command in ("num-batch", "concurrency"):
            self.assertIn(f'"{command}"', runtime_source)
        for command in ("owui-rag", "owui-embedding-batch", "owui-chunk-min", "owui-system-context"):
            self.assertIn(f'"{command}"', owui_source)
        for source in (runtime_source, owui_source):
            self.assertIn("prepare_result_dir", source)
            self.assertIn("result_record", source)
            self.assertIn("write_result_summary", source)
        self.assertIn("def restore_config(", owui_source)
        self.assertIn('category="owui-system-context"', owui_source)
        self.assertFalse((ROOT / "cmd/benchmark/workflow-benchmark.py").exists())


    def test_common_metadata_has_package_kernel_fixtures_and_finished_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            t = Path(temporary)
            fixture = t / "fixture.json"
            fixture.write_text("{}\n", encoding="utf-8")
            meta_path = t / "meta.json"
            meta = common.benchmark_metadata(
                "task",
                benchmark_version="8.0",
                models=[{"model": "task-test", "digest": "abc"}],
                fixtures=common.fixture_metadata(fixture),
                options={"lane": 11435},
                runtimes=[{"kind": "ollama", "url": "http://127.0.0.1:11435", "version": "0.33.3"}],
            )
            common.write_benchmark_metadata(meta_path, meta)
            common.finalize_benchmark_metadata(meta_path)
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(data["category"], "task")
            self.assertEqual(data["benchmark_version"], "8.0")
            self.assertTrue(data["package"]["version"])
            self.assertTrue(data["kernel"])
            self.assertEqual(data["fixtures"][0]["name"], "fixture.json")
            self.assertTrue(data["finished_at"])

    def test_category_metadata_records_effective_options_and_runtime(self) -> None:
        class FakeClient:
            base_url = "http://127.0.0.1:11437"
            timeout = 321.0
            def version(self) -> str:
                return "0.33.3"
            def show(self, _model: str) -> dict[str, object]:
                return {"details": {"family": "test"}}
            def digest(self, _model: str) -> str:
                return "abc"

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture.json"
            fixture.write_text("{}\n", encoding="utf-8")
            meta_path = root / "meta.json"
            category.write_meta(
                meta_path,
                FakeClient(),
                "embeddings",
                ["embed-test"],
                fixture,
                options={"repeats": 2, "query_prefix_override": "Q: "},
            )
            meta = json.loads(meta_path.read_text())
            self.assertEqual(meta["options"]["request_timeout_s"], 321.0)
            self.assertEqual(meta["options"]["repeats"], 2)
            self.assertEqual(meta["models"][0]["runtime_url"], "http://127.0.0.1:11437")

    def test_generation_metadata_lists_resolved_environment_controls(self) -> None:
        source = (BENCH / "generation-benchmark.py").read_text(encoding="utf-8")
        for option in (
            "num_predict_short", "num_predict_prefill", "num_predict_context",
            "num_predict_long", "repeats", "latency_repeats",
            "prefill_sentences", "ctx_points", "keep_alive",
            "early_eos_fraction", "request_timeout_s",
        ):
            self.assertIn(f'"{option}"', source)

    def test_generation_summary_contains_category_aggregates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "results.jsonl"
            for run, tps in enumerate((40.0, 42.0, 41.0), start=1):
                common.append_result(path, common.result_record(
                    category="generation", model="m", case_id=f"short-{run}",
                    result_type="measurement", outcome="pass",
                    diagnostics=["context-truncation"] if run == 3 else [],
                    metrics={
                        "tokens_per_second": tps, "resident_size_bytes": 1024,
                        "mem_available_min_mib": 2000, "swap_used_start_mib": 10,
                        "swap_used_max_mib": 20, "swap_used_end_mib": 15,
                        "swap_peak_delta_mib": 10, "temp_max_c": 70, "temp_p95_c": 68,
                    }, test="short", run=run,
                ))
            common.append_result(path, common.result_record(
                category="generation", model="m", case_id="prefill-1",
                result_type="measurement", outcome="pass",
                metrics={"prompt_tokens_per_second": 500.0}, test="prefill", run=1,
            ))
            summary_json, _summary_txt = common.write_result_summary(path, category="generation")
            summary = json.loads(summary_json.read_text(encoding="utf-8"))
            model = summary["aggregates"]["models"]["m"]
            self.assertAlmostEqual(model["decode_mean_tps"], 41.0)
            self.assertAlmostEqual(model["prefill_tps"], 500.0)
            self.assertEqual(model["diagnostics"], {"context-truncation": 1})

    def test_chronological_resource_aggregate_uses_run_boundaries(self) -> None:
        rows = [
            {
                "swap_used_start_mib": 100,
                "swap_used_max_mib": 150,
                "swap_used_end_mib": 140,
                "temp_p95_c": 68,
            },
            {
                "swap_used_start_mib": 140,
                "swap_used_max_mib": 180,
                "swap_used_end_mib": 120,
                "temp_p95_c": 70,
            },
        ]
        aggregate = common.chronological_resource_aggregate(rows)
        self.assertEqual(aggregate["swap_used_start_mib"], 100)
        self.assertEqual(aggregate["swap_used_max_mib"], 180)
        self.assertEqual(aggregate["swap_used_end_mib"], 120)
        self.assertEqual(aggregate["swap_peak_delta_mib"], 80)
        self.assertEqual(aggregate["temp_p95_max_case_c"], 70)

        nested = common.chronological_resource_aggregate(
            [{"metrics": row} for row in rows], nested_metrics=True
        )
        self.assertEqual(nested["swap_peak_delta_mib"], 80)

    def test_embedding_aggregate_record_drives_canonical_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "results.jsonl"
            metrics = {
                "recall_at_1": 0.8462,
                "recall_at_3": 1.0,
                "mrr": 0.9231,
                "cross_recall_at_1": 0.8889,
                "cross_mrr": 0.9444,
                "hard_recall_at_1": 0.5,
                "warm_input_tps": 321.0,
                "cold_load_s": 1.5,
            }
            common.append_result(
                path,
                common.result_record(
                    category="embeddings",
                    model="embed-jina",
                    case_id="aggregate",
                    result_type="measurement",
                    outcome="pass",
                    metrics=metrics,
                ),
            )
            summary_json, _ = common.write_result_summary(path, category="embeddings")
            model = json.loads(summary_json.read_text())["aggregates"]["models"]["embed-jina"]
            self.assertEqual(model["cross_recall_at_1"], 0.8889)
            self.assertEqual(model["cross_mrr"], 0.9444)
            self.assertEqual(model["warm_input_tps"], 321.0)

    def test_quality_summary_preserves_per_model_failure_causes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "results.jsonl"
            for model, cause in (("model-a", "language"), ("model-b", "relevance")):
                common.append_result(
                    path,
                    common.result_record(
                        category="task",
                        model=model,
                        case_id="case",
                        result_type="qualification",
                        outcome="quality-fail",
                        failure_kinds=[cause],
                    ),
                )
            summary_json, _ = common.write_result_summary(path, category="task")
            models = json.loads(summary_json.read_text())["aggregates"]["models"]
            self.assertEqual(models["model-a"]["failure_kinds"], {"language": 1})
            self.assertEqual(models["model-b"]["failure_kinds"], {"relevance": 1})

    def test_openwebui_metadata_resolves_model_on_supplied_runtime(self) -> None:
        seen: list[str] = []

        class FakeOllama:
            def __init__(self, url: str, _timeout: float = 900.0) -> None:
                self.base_url = url
                seen.append(url)
            def version(self) -> str:
                return "0.33.3"
            def digest(self, _model: str) -> str:
                return "digest"

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            openwebui_workflow, "OllamaClient", FakeOllama
        ):
            meta_path = Path(temporary) / "meta.json"
            paths = SimpleNamespace(meta_json=meta_path)
            openwebui_workflow.simple_meta(
                paths,
                "owui-embedding-batch",
                url="http://127.0.0.1:3000",
                model="embed-jina",
                model_runtime_url="http://127.0.0.1:11437",
            )
            meta = json.loads(meta_path.read_text())
            self.assertEqual(seen, ["http://127.0.0.1:11437"])
            self.assertEqual(meta["models"][0]["runtime_url"], "http://127.0.0.1:11437")

    def test_revalidation_quality_step_names_match_canonical_categories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = root / "events.tsv"
            for category_name in ("usecase", "agent", "owui-rag"):
                result_dir = root / category_name / "results"
                result_dir.mkdir(parents=True)
                (result_dir / "summary.json").write_text(
                    json.dumps({
                        "category": category_name,
                        "qualification_counts": {"pass": 0, "quality-fail": 1, "skipped": 0},
                        "failure_kinds": {"requirements": 1},
                    }),
                    encoding="utf-8",
                )
            events.write_text(
                "\n".join(
                    f"2026-09-07T00:00:00+00:00\troles\t{name}\tquality\tquality-fail\trc=3"
                    for name in ("usecase", "agent", "owui-rag")
                ) + "\n",
                encoding="utf-8",
            )
            source = ROOT / "cmd/benchmark/revalidate.sh"
            script = (
                f'source "{source}" help >/dev/null\n'
                f'RAW="{root}"\nEVENTS="{events}"\nquality_cause_report\n'
            )
            completed = subprocess.run(
                ["bash", "-c", script], text=True, capture_output=True, check=True
            )
            self.assertNotIn("canonical summary unavailable", completed.stdout)
            for name in ("usecase", "agent", "owui-rag"):
                self.assertIn(name, completed.stdout)

    def test_failed_launch_cleanup_removes_state_token_and_unit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "work"
            run_dir = root / "run"
            unit = root / "worker.service"
            token = root / "token"
            work.mkdir()
            run_dir.mkdir()
            unit.write_text("unit")
            token.write_text("secret")
            source = ROOT / "cmd/benchmark/revalidate.sh"
            script = f'''source "{source}" help >/dev/null
WORK="{work}"
RUN_DIR="{run_dir}"
UNIT_PATH="{unit}"
OWUI_TOKEN="{token}"
UNIT="test-worker.service"
systemctl() {{ return 0; }}
cleanup_failed_launch
[[ ! -e "$WORK" && ! -e "$RUN_DIR" && ! -e "$UNIT_PATH" && ! -e "$OWUI_TOKEN" ]]
'''
            subprocess.run(["bash", "-c", script], check=True)

    def test_agent_static_contract_has_no_legacy_correctness_alias(self) -> None:
        self.assertFalse(hasattr(category, "validate_agent_output"))
        source = (BENCH / "category-benchmark.py").read_text(encoding="utf-8")
        self.assertNotIn("correctness_ok", source)

    def test_generation_budget_diagnostics_distinguish_output_from_thinking(self) -> None:
        metrics = {"answer_started": False, "done_reason": "length"}
        self.assertEqual(generation.budget_diagnostics(metrics, 128, ""), ["output-budget"])
        self.assertEqual(
            generation.budget_diagnostics(metrics, 128, "reasoning"),
            ["output-budget", "thinking-budget"],
        )

    def test_round2c2_removes_stale_revalidation_and_splits_workflow_responsibility(self) -> None:
        revalidate = (ROOT / "cmd/benchmark/revalidate.sh").read_text(encoding="utf-8")
        for stale in ("PARAM_NAMES=", "run_bench()", "unload_model()", "disable_worker_for_future_boots", "Compatibility name"):
            self.assertNotIn(stale, revalidate)
        self.assertIn("Recent results", revalidate)
        self.assertIn("Revalidation run completed.", revalidate)
        self.assertTrue((BENCH / "runtime-benchmark.py").exists())
        self.assertTrue((BENCH / "openwebui-benchmark.py").exists())
        self.assertFalse((BENCH / "workflow-benchmark.py").exists())

    def test_revalidation_uses_complete_live_cu_routing_health(self) -> None:
        source = (ROOT / "cmd/benchmark/revalidate.sh").read_text(encoding="utf-8")
        block = source[source.index("check_live_cu_routing() {"):source.index("phase_preflight() {")]
        self.assertIn("bc250-cu-status --summary", block)
        self.assertIn("routed entries present; no off/problem cells", block)
        self.assertNotIn("40/40", block)


if __name__ == "__main__":
    unittest.main()
