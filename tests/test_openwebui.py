from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import sys
import unittest
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


class OpenWebUIStatusTests(unittest.TestCase):

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
