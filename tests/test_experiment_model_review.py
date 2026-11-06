"""OPEN WIP 2026-11-05 experiment pruning and role-challenger safety regressions."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "models"))
import modelctl

OPENWEBUI_MODULE = ROOT / "cmd/openwebui/openwebui-setup.py"
SPEC = importlib.util.spec_from_file_location("experiment_review_openwebui", OPENWEBUI_MODULE)
assert SPEC and SPEC.loader
openwebui = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = openwebui
SPEC.loader.exec_module(openwebui)

CATALOG = json.loads((ROOT / "models/model-catalog.json").read_text())["models"]
PROFILES = json.loads((ROOT / "models/model-profiles.json").read_text())["profiles"]
RETIRED = {
    entry["name"]
    for entry in json.loads((ROOT / "models/retired-models.json").read_text())["models"]
}
REMOVED = {
    "exp-nemotron35-bolt-e4b-nvidia-q4-k-m",
    "exp-lfm3-1.7b-atomicchat-uncensored-q6-k",
    "exp-lfm3-vl-2b-liquidai-q6-k",
    "exp-minicpm-v47-1b-openbmb-q4-k-m",
    "exp-granite42-3b-ibm-q6-k",
    "exp-qwen35-4b-unsloth-q6-k",
    "exp-qwen35-9b-hauhaucs-uncensored-q6-k",
    "exp-qwen35-9b-davidau-defiant-fable-q6-k",
    "exp-qwen38-27b-ista-gsq-rco-iq3-s",
    "exp-spark-x26-4b-abenzerps-uncensored-iq3-m",
    "agentic-qwen25-coder7b-unsloth-q5-k-m",
    "exp-gemma4-12b-google-qat-q4-0",
    "exp-lfm3-1.7b-liquidai-q6-k",
}


class ExperimentModelReviewTests(unittest.TestCase):
    def test_catalog_profiles_and_modelfiles_match(self) -> None:
        self.assertTrue(set(CATALOG) <= set(PROFILES))
        self.assertEqual(
            set(CATALOG),
            {p.stem for p in (ROOT / "models/modelfiles").glob("*.Modelfile")},
        )
        self.assertEqual(27, len(CATALOG))
        self.assertEqual(10, sum(m["category"] == "experiments" for m in CATALOG.values()))

    def test_retired_ids_not_active_and_do_not_reappear_in_modelfiles(self) -> None:
        self.assertTrue(REMOVED <= RETIRED)
        self.assertTrue(set(CATALOG).isdisjoint(RETIRED))
        for model_id in REMOVED:
            self.assertFalse((ROOT / "models/modelfiles" / f"{model_id}.Modelfile").exists())

    def test_production_roles_and_task_embedding_defaults_not_switched(self) -> None:
        roles = json.loads((ROOT / "config/openwebui/models.json").read_text())["models"]
        self.assertTrue(all(r["base_model_id"].startswith("prod-") for r in roles if r["is_active"] and r["base_model_id"] is not None))
        state = json.loads((ROOT / "config/openwebui/desired-state.json").read_text())
        self.assertEqual(state["task"]["TASK_MODEL"], "task-lfm25-1.2b-instruct-liquidai-q6-k:latest")
        self.assertEqual(state["embedding"]["RAG_EMBEDDING_MODEL"], "embed-jina-v5-small-retrieval-q4-k-m")

    def test_lfm3_is_an_optional_task_lane_challenger(self) -> None:
        candidate = CATALOG["task-lfm3-1.7b-liquidai-q6-k"]
        profile = PROFILES["task-lfm3-1.7b-liquidai-q6-k"]
        self.assertEqual(candidate["category"], "task")
        self.assertEqual(candidate["runtime"]["lane"], "task")
        self.assertEqual(candidate["source"]["repository"], "LiquidAI/LFM3-1.7B-GGUF")
        self.assertFalse(profile["recommended"])
        self.assertEqual(profile["owui_testing_exposure"], "forbidden")
        modelfile = (ROOT / "models/modelfiles/task-lfm3-1.7b-liquidai-q6-k.Modelfile").read_text()
        self.assertIn("PARAMETER num_ctx 4096", modelfile)
        self.assertNotIn("\nSYSTEM ", modelfile)
        self.assertNotIn(candidate_id := "task-lfm3-1.7b-liquidai-q6-k", modelctl._SHARED_MODEL_CONTRACT.required_baseline_model_ids())
        defaults = {"destination": "/unused", "modelfile_destination": "/unused"}
        model = {"id": candidate_id, "name": candidate_id, "category": "task", "provider": "ollama", "origin": "packaged", "gguf": candidate["source"]["filename"]}
        with (
            patch.object(modelctl, "inspect_local_source", return_value=("missing", "absent", "")),
            patch.object(modelctl, "runtime_modelfile_path", return_value=Path("/tmp/optional-lfm3.Modelfile")),
            patch.object(modelctl, "inspect_runtime_modelfile", return_value=("missing", "absent")),
        ):
            result = modelctl.inspect_model_state(defaults, model, registrations=set(), destination="/tmp")
        self.assertEqual(result.overall_status, "OPTIONAL")

    def test_role_driven_required_set_updates_on_selected_task(self) -> None:
        contract = modelctl._SHARED_MODEL_CONTRACT
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roles = root / "roles.json"
            desired = root / "desired.json"
            roles.write_text(json.dumps({"models": [{"is_active": True, "base_model_id": "prod-demo:latest"}]}))
            desired.write_text(json.dumps({"task": {"TASK_MODEL": "task-lfm3-1.7b-liquidai-q6-k:latest"}, "embedding": {"RAG_EMBEDDING_MODEL": "embed-demo:latest"}}))
            self.assertEqual(contract.required_baseline_model_ids(roles_path=roles, desired_path=desired), frozenset({"prod-demo", "task-lfm3-1.7b-liquidai-q6-k", "embed-demo"}))

    def test_new_heretic_controls_are_admin_only(self) -> None:
        for model_id in ("exp-qwen35-9b-llmfan46-heretic-q6-k", "exp-gemma4-e4b-sc117-heretic-qat-q4-k-xl"):
            self.assertEqual(PROFILES[model_id]["owui_testing_exposure"], "forbidden")
            self.assertFalse(PROFILES[model_id]["recommended"])
        self.assertEqual(CATALOG["exp-qwen35-9b-llmfan46-heretic-q6-k"]["source"]["repository"], "llmfan46/Qwen3.5-9B-ultra-uncensored-heretic-v2-GGUF")
        self.assertEqual(CATALOG["exp-gemma4-e4b-sc117-heretic-qat-q4-k-xl"]["source"]["repository"], "SC117/gemma-4-E4B-it-heretic-QAT-GGUF")

    def test_gemma12_has_verified_quant_and_unchanged_context_limit(self) -> None:
        model_id = "exp-gemma4-12b-unsloth-qat-ud-q4-k-xl"
        source = CATALOG[model_id]["source"]
        self.assertEqual(source["repository"], "unsloth/gemma-4-12B-it-qat-GGUF")
        self.assertEqual(source["filename"], "gemma-4-12B-it-qat-UD-Q4_K_XL.gguf")
        self.assertIn("PARAMETER num_ctx 16384", (ROOT / "models/modelfiles" / f"{model_id}.Modelfile").read_text())

    def test_retired_registered_models_not_auto_published(self) -> None:
        inventories = {"main": ["exp-qwen35-9b-hauhaucs-uncensored-q6-k:latest", "exp-qwen35-9b-llmfan46-heretic-q6-k:latest", "exp-index-translate-9b-indexteam-q4-k-m:latest"], "task": ["exp-lfm3-1.7b-liquidai-q6-k:latest", "task-lfm3-1.7b-liquidai-q6-k:latest"]}
        effective = openwebui.effective_model_document(openwebui.load_models(), inventories)
        raw_ids = {r["id"] for r in effective["models"]}
        self.assertNotIn("exp-qwen35-9b-hauhaucs-uncensored-q6-k:latest", raw_ids)
        self.assertNotIn("exp-lfm3-1.7b-liquidai-q6-k:latest", raw_ids)
        self.assertNotIn("exp-qwen35-9b-llmfan46-heretic-q6-k:latest", raw_ids)
        self.assertNotIn("task-lfm3-1.7b-liquidai-q6-k:latest", raw_ids)
        self.assertIn("exp-index-translate-9b-indexteam-q4-k-m:latest", raw_ids)

    def test_license_cautions_exposed_in_model_inspection(self) -> None:
        self.assertEqual(CATALOG["embed-jina-v5-small-retrieval-q4-k-m"]["license"]["id"], "CC-BY-NC-4.0")
        self.assertEqual(CATALOG["embed-qwen3-0.6b-q8-0"]["license"]["id"], "Apache-2.0")
        self.assertIn("commercial", CATALOG["embed-jina-v5-small-retrieval-q4-k-m"]["license"]["use_note"].lower())
        for model_id in ("task-lfm25-1.2b-instruct-liquidai-q6-k", "task-lfm3-1.7b-liquidai-q6-k"):
            self.assertIn("LFM Open License", CATALOG[model_id]["license"]["id"])
        # Package-model inspector returns this catalog metadata, without claiming approval.
        self.assertIn('"license": model.get("catalog", {}).get("license")', (ROOT / "models/modelctl.py").read_text())


class ExperimentModelReviewFollowUpTests(unittest.TestCase):
    """Follow-up fixes from the 2026-11-06 review of the cumulative model WIP."""

    def test_heretic_qwen_source_is_the_published_v2_repository(self) -> None:
        source = CATALOG["exp-qwen35-9b-llmfan46-heretic-q6-k"]["source"]
        self.assertEqual(source["repository"], "llmfan46/Qwen3.5-9B-ultra-uncensored-heretic-v2-GGUF")
        self.assertEqual(source["provider_ref"], f"hf.co/{source['repository']}:Q6_K")
        self.assertIn("-v2-", source["filename"])

    def test_task_benchmark_sends_think_false_only_when_profile_requests_it(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "experiment_review_category", ROOT / "cmd/benchmark/category-benchmark.py"
        )
        assert spec and spec.loader
        sys.path.insert(0, str(ROOT / "cmd/benchmark"))
        category = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = category
        spec.loader.exec_module(category)
        self.assertIs(category.task_think_request("task-lfm3-1.7b-liquidai-q6-k:latest"), False)
        self.assertIsNone(category.task_think_request("task-lfm25-1.2b-instruct-liquidai-q6-k"))
        self.assertIsNone(category.task_think_request("unknown-external-model"))

    def test_task_screen_accepts_packaged_task_challenger(self) -> None:
        screen = (ROOT / "quality-checks/task/10-candidate-screen.sh").read_text(encoding="utf-8")
        self.assertIn("task-*) CANDIDATE_KIND=task", screen)
        self.assertIn('sudo bc250 model apply task "$CANDIDATE"', screen)
        self.assertIn('[[ "$CANDIDATE_KIND" == task ]] || register_candidate_on_task', screen)

    def test_active_quality_check_scripts_reference_only_catalog_models(self) -> None:
        import re

        pattern = re.compile(r"'((?:exp|prod|task|agentic|embed)-[a-z0-9.\-]+[a-z0-9])'")
        for script in sorted((ROOT / "quality-checks").rglob("*.sh")):
            if "history" in script.parts:
                continue
            for model_id in pattern.findall(script.read_text(encoding="utf-8")):
                with self.subTest(script=script.name, model=model_id):
                    self.assertIn(model_id, CATALOG)

    def test_unreadable_role_document_is_a_model_error_not_a_traceback(self) -> None:
        modelctl._REQUIRED_BASELINE_CACHE.clear()
        try:
            with (
                patch.dict("os.environ", {"BC250_OWUI_MODELS_FILE": "/nonexistent/models.json"}),
                self.assertRaisesRegex(modelctl.ModelError, "required baseline models"),
            ):
                modelctl.required_baseline_model_ids()
        finally:
            modelctl._REQUIRED_BASELINE_CACHE.clear()

    def test_baseline_desired_state_override_is_validated(self) -> None:
        contract = modelctl._SHARED_MODEL_CONTRACT
        with tempfile.TemporaryDirectory() as directory:
            desired = Path(directory) / "desired.json"
            desired.write_text((ROOT / "config/openwebui/desired-state.json").read_text(encoding="utf-8"))
            desired.chmod(0o666)
            with (
                patch.dict("os.environ", {"BC250_OWUI_DESIRED_STATE": str(desired)}),
                self.assertRaises(contract.ModelContractError),
            ):
                contract.required_baseline_model_ids()


if __name__ == "__main__":
    unittest.main()
