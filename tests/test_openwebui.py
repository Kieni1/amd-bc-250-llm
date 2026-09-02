from __future__ import annotations

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
            "/api/v1/tasks/config": {
                "TASK_MODEL": OPENWEBUI.TASK_MODEL,
                "TASK_MODEL_EXTERNAL": None,
                "TASK_MODEL_PARAMS": {},
                "ENABLE_TITLE_GENERATION": True,
                "ENABLE_TAGS_GENERATION": True,
                "ENABLE_FOLLOW_UP_GENERATION": False,
                "ENABLE_AUTOCOMPLETE_GENERATION": False,
                "ENABLE_SEARCH_QUERY_GENERATION": False,
                "ENABLE_RETRIEVAL_QUERY_GENERATION": False,
            },
            "/api/v1/retrieval/embedding": OPENWEBUI.desired_embedding(),
            "/api/v1/retrieval/config": OPENWEBUI.desired_rag(),
            "/api/v1/models/export": OPENWEBUI.load_models()["models"],
        }
        self.responses.update(overrides or {})

    def probe(self, path: str) -> None:
        del path

    def get(self, path: str) -> Any:
        return self.responses[path]


class OpenWebUIStatusTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
