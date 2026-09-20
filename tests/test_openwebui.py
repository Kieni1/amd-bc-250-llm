from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "cmd/openwebui/openwebui-setup.py"
SPEC = importlib.util.spec_from_file_location("openwebui_setup", HELPER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"could not load {HELPER}")
OPENWEBUI = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = OPENWEBUI
SPEC.loader.exec_module(OPENWEBUI)


class FakeClient:
    def __init__(self, overrides: dict[str, Any] | None = None):
        self.responses = {
            "/api/v1/configs/export": OPENWEBUI.desired_application(),
            "/ollama/config": OPENWEBUI.desired_ollama(),
            "/api/v1/tasks/config": OPENWEBUI.desired_task(),
            "/api/v1/retrieval/embedding": OPENWEBUI.desired_embedding(),
            "/api/v1/retrieval/config": OPENWEBUI.desired_rag(),
            "/api/v1/functions/export": OPENWEBUI.load_functions(),
            "/api/v1/models/export": OPENWEBUI.load_models()["models"],
        }
        self.responses.update(overrides or {})

    def probe(self, path: str) -> None:
        del path

    def get(self, path: str) -> Any:
        return self.responses[path]




class FakeFunctionApplyClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, path: str) -> Any:
        if path == "/api/v1/functions/list":
            return []
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        self.calls.append((path, payload))
        if path == "/api/v1/functions/create":
            return {
                "id": payload["id"],
                "name": payload["name"],
                "is_active": False,
                "is_global": False,
            }
        if path.endswith("/toggle"):
            return {
                "id": "bc250_translation_direction",
                "name": "BC-250 Translation Direction Wrapper",
                "is_active": True,
                "is_global": False,
            }
        raise AssertionError(f"unexpected POST {path}")


class FakeApplyClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any | None]] = []

    def get(self, path: str) -> Any:
        self.calls.append(("GET", path, None))
        if path == "/api/v1/tasks/config":
            return {"unrelated": "preserved"}
        if path == "/api/v1/functions/list":
            return OPENWEBUI.load_functions()
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path: str, payload: Any) -> Any:
        self.calls.append(("POST", path, payload))
        if path.startswith("/api/v1/functions/id/") and path.endswith("/update"):
            desired = OPENWEBUI.load_functions()[0]
            return {
                "id": desired["id"],
                "name": desired["name"],
                "is_active": desired["is_active"],
                "is_global": desired["is_global"],
            }
        return {}


class OpenWebUIStatusTests(unittest.TestCase):

    def test_apply_owns_persisted_application_policy_and_hidden_models(self) -> None:
        client = FakeApplyClient()
        OPENWEBUI.apply(client)
        posts = [(path, payload) for method, path, payload in client.calls if method == "POST"]
        app_payload = next(payload for path, payload in posts if path == "/api/v1/configs/import")
        self.assertEqual(app_payload, {"config": OPENWEBUI.desired_application()})
        self.assertFalse(app_payload["config"]["evaluation.arena.enable"])

        model_payload = next(payload for path, payload in posts if path == "/api/v1/models/import")
        hidden = {
            model["id"]: model
            for model in model_payload["models"]
            if (model.get("meta") or {}).get("hidden") is True
        }
        self.assertEqual(
            set(hidden),
            {
                "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl:latest",
                "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl:latest",
                "prod-translate-gemma4-sub-e4b-17s-q4-k-xl:latest",
                "prod-qwen35-9b-unsloth-q6-k:latest",
                "prod-gpt-oss20b-ggml-org-mxfp4:latest",
                "task-lfm25-1.2b-instruct-liquidai-q6-k:latest",
            },
        )
        self.assertTrue(all(model["is_active"] for model in hidden.values()))
        self.assertTrue(all(model["base_model_id"] is None for model in hidden.values()))

    def test_persisted_application_policy_matches_local_offline_contract(self) -> None:
        self.assertEqual(
            OPENWEBUI.desired_application(),
            {
                "evaluation.arena.enable": False,
                "openai.enable": False,
                "direct.enable": False,
                "code_execution.enable": False,
                "code_interpreter.enable": False,
                "memories.enable": False,
                "ui.enable_community_sharing": False,
            },
        )

    def test_rag_owns_persisted_upload_policy(self) -> None:
        rag = OPENWEBUI.desired_rag()
        self.assertEqual(rag["FILE_MAX_SIZE"], 128)
        self.assertEqual(rag["FILE_MAX_COUNT"], 20)
        self.assertIn("pdf", rag["ALLOWED_FILE_EXTENSIONS"])
        self.assertIn("docx", rag["ALLOWED_FILE_EXTENSIONS"])

    def test_status_detects_arena_drift(self) -> None:
        current = OPENWEBUI.desired_application()
        current["evaluation.arena.enable"] = True
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                OPENWEBUI.status(FakeClient({"/api/v1/configs/export": current}), True),
                2,
            )
        self.assertIn(
            "Application config differs: evaluation.arena.enable", output.getvalue()
        )

    def test_status_detects_hidden_model_drift(self) -> None:
        models = copy.deepcopy(OPENWEBUI.load_models()["models"])
        target = next(
            model
            for model in models
            if model["id"] == "task-lfm25-1.2b-instruct-liquidai-q6-k:latest"
        )
        target["meta"]["hidden"] = False
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                OPENWEBUI.status(FakeClient({"/api/v1/models/export": models}), True),
                2,
            )
        self.assertIn(".meta.hidden", output.getvalue())

    def test_allowed_extension_order_does_not_create_false_drift(self) -> None:
        rag = OPENWEBUI.desired_rag()
        rag["ALLOWED_FILE_EXTENSIONS"] = list(reversed(rag["ALLOWED_FILE_EXTENSIONS"]))
        self.assertEqual(
            OPENWEBUI.status(FakeClient({"/api/v1/retrieval/config": rag}), True),
            0,
        )

    def test_apply_functions_creates_and_activates_package_filter(self) -> None:
        client = FakeFunctionApplyClient()
        OPENWEBUI.apply_functions(client)
        paths = [path for path, _payload in client.calls]
        self.assertEqual(
            paths,
            [
                "/api/v1/functions/create",
                "/api/v1/functions/id/bc250_translation_direction/toggle",
            ],
        )
        create_payload = client.calls[0][1]
        self.assertEqual(create_payload["id"], "bc250_translation_direction")
        self.assertIn("class Filter", create_payload["content"])

    def test_status_accepts_well_formed_api_responses(self) -> None:
        self.assertEqual(OPENWEBUI.status(FakeClient(), True), 0)

    def test_verbose_status_surfaces_verified_role_contracts(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(OPENWEBUI.status(FakeClient(), True, verbose=True), 0)
        text = output.getvalue()
        self.assertIn("Package-owned Open WebUI roles", text)
        self.assertIn("bc250-office-translation-de-fr", text)
        self.assertIn("max_tokens=2048", text)
        self.assertIn("think=omitted", text)
        self.assertIn("filters=bc250_translation_direction", text)
        self.assertIn("Task and RAG", text)
        self.assertIn("Package-owned functions", text)
        self.assertIn("Hidden implementation models", text)
        self.assertIn("task-lfm25-1.2b-instruct-liquidai-q6-k:latest", text)

    def test_status_rejects_non_object_config_responses(self) -> None:
        endpoints = (
            "/ollama/config",
            "/api/v1/tasks/config",
            "/api/v1/retrieval/embedding",
            "/api/v1/retrieval/config",
        )
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint), self.assertRaises(OPENWEBUI.ApiError):
                OPENWEBUI.status(FakeClient({endpoint: []}), True)

    def test_status_rejects_non_list_model_export(self) -> None:
        with self.assertRaisesRegex(OPENWEBUI.ApiError, "model export response"):
            OPENWEBUI.status(FakeClient({"/api/v1/models/export": {}}), True)

    def test_status_rejects_non_list_function_export(self) -> None:
        with self.assertRaisesRegex(OPENWEBUI.ApiError, "function export response"):
            OPENWEBUI.status(FakeClient({"/api/v1/functions/export": {}}), True)

    def test_translation_roles_match_stage2e_contract_exactly(self) -> None:
        prompt_path = ROOT / "config/openwebui/prompts/translation-explicit-direction-v1.txt"
        prompt = prompt_path.read_text(encoding="utf-8")
        self.assertEqual(
            hashlib.sha256(prompt.encode()).hexdigest(),
            "c12ccfb4694a444dff66400141c6ae8eaebb66195e98851ddc5b562cbbdb57db",
        )
        models = {item["id"]: item for item in OPENWEBUI.load_models()["models"]}
        for model_id in (
            "bc250-office-translation-de-fr",
            "bc250-office-translation-fr-de",
        ):
            model = models[model_id]
            self.assertEqual(model["params"]["system"], prompt)
            self.assertEqual(model["params"]["max_tokens"], 2048)
            self.assertNotIn("think", model["params"])
            self.assertEqual(
                model["meta"]["filterIds"], ["bc250_translation_direction"]
            )
            self.assertEqual(
                model["base_model_id"],
                "prod-translate-gemma4-sub-e4b-17s-q4-k-xl:latest",
            )

        allowed = OPENWEBUI.desired_ollama()["OLLAMA_API_CONFIGS"]["0"]["model_ids"]
        self.assertIn("prod-translate-gemma4-sub-e4b-17s-q4-k-xl:latest", allowed)
        legacy = models["bc250-office-translation"]
        self.assertEqual(legacy["base_model_id"], "exp-lfm25-8b-a1b-liquidai-q6-k:latest")
        self.assertFalse(legacy["is_active"])

    def test_translation_direction_filter_wraps_source_exactly(self) -> None:
        path = ROOT / "config/openwebui/functions/bc250_translation_direction.py"
        spec = importlib.util.spec_from_file_location("bc250_translation_direction", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec else None)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        cases = {
            "bc250-office-translation-de-fr": (
                "Translate from German to French. Translate every ordinary-language source word "
                + "and preserve the document structure. Return only the translation.\n\n"
                + "[CURRENT_SOURCE]\n",
                "Guten Tag.\nZweite Zeile.",
            ),
            "bc250-office-translation-fr-de": (
                "Translate from French to German. Translate every ordinary-language source word "
                + "and preserve the document structure. Return only the translation.\n\n"
                + "[CURRENT_SOURCE]\n",
                "Bonjour.\nDeuxième ligne.",
            ),
        }
        for model_id, (wrapper, source) in cases.items():
            with self.subTest(model_id=model_id):
                body = {"model": model_id, "messages": [{"role": "user", "content": source}]}
                result = asyncio.run(module.Filter().inlet(body))
                self.assertEqual(result["messages"][-1]["content"], wrapper + source)

    def test_package_function_manifest_loads_non_global_active_filter(self) -> None:
        functions = OPENWEBUI.load_functions()
        self.assertEqual(len(functions), 1)
        function = functions[0]
        self.assertEqual(function["id"], "bc250_translation_direction")
        self.assertTrue(function["is_active"])
        self.assertFalse(function["is_global"])
        self.assertIn("class Filter", function["content"])


if __name__ == "__main__":
    unittest.main()
