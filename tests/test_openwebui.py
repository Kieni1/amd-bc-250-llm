from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "cmd/openwebui/openwebui-setup.py"
SPEC = importlib.util.spec_from_file_location("openwebui_setup", HELPER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"could not load {HELPER}")
OPENWEBUI = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = OPENWEBUI
SPEC.loader.exec_module(OPENWEBUI)


REQUIRED_READ = {"principal_type": "user", "principal_id": "*", "permission": "read"}

PRODUCTION_MODEL_IDS = {
    "bc250-office-standard",
    "bc250-office-documents",
    "bc250-office-translation-de-fr",
    "bc250-office-translation-fr-de",
    "bc250-office-advanced",
    "bc250-office-deep-reasoning",
    "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl:latest",
    "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl:latest",
    "prod-translate-gemma4-sub-e4b-17s-q4-k-xl:latest",
    "prod-qwen35-9b-unsloth-q6-k:latest",
    "prod-gpt-oss20b-ggml-org-mxfp4:latest",
    "task-lfm25-1.2b-instruct-liquidai-q6-k:latest",
}

HIDDEN_MODEL_IDS: set[str] = set()


def desired_models() -> list[dict[str, Any]]:
    return copy.deepcopy(OPENWEBUI.load_models()["models"])


def live_model_views(*, include_required_grants: bool = True) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    presets: list[dict[str, Any]] = []
    bases: list[dict[str, Any]] = []
    for desired in desired_models():
        live = copy.deepcopy(desired)
        required = live.pop("access_grants", [])
        live["access_grants"] = copy.deepcopy(required if include_required_grants else [])
        if live["base_model_id"] is None:
            bases.append(live)
        else:
            presets.append(live)
    return presets, bases


def status_responses(*, include_required_grants: bool = True) -> dict[str, Any]:
    presets, bases = live_model_views(include_required_grants=include_required_grants)
    return {
        "/api/v1/configs/export": OPENWEBUI.desired_application(),
        "/ollama/config": OPENWEBUI.desired_ollama(),
        "/api/v1/tasks/config": OPENWEBUI.desired_task(),
        "/api/v1/retrieval/embedding": OPENWEBUI.desired_embedding(),
        "/api/v1/retrieval/config": OPENWEBUI.desired_rag(),
        "/api/v1/functions/export": OPENWEBUI.load_functions(),
        "/api/v1/models/export": presets,
        "/api/v1/models/base": bases,
    }


class FakeClient:
    def __init__(self, overrides: dict[str, Any] | None = None):
        self.responses = status_responses()
        self.responses.update(copy.deepcopy(overrides or {}))
        self.posts: list[tuple[str, Any]] = []

    def probe(self, path: str = "/") -> None:
        del path

    def get(self, path: str) -> Any:
        if path not in self.responses:
            raise AssertionError(f"unexpected GET {path}")
        return copy.deepcopy(self.responses[path])

    def post(self, path: str, payload: Any) -> Any:
        self.posts.append((path, copy.deepcopy(payload)))
        if path == "/api/v1/models/model/access/update":
            model_id = payload["id"]
            for view_path in ("/api/v1/models/export", "/api/v1/models/base"):
                for model in self.responses.get(view_path, []):
                    if model.get("id") == model_id:
                        model["access_grants"] = copy.deepcopy(payload["access_grants"])
                        return copy.deepcopy(model)
            raise AssertionError(f"access update target not found: {model_id}")
        return {}


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
    def __init__(self, *, include_required_grants: bool = False) -> None:
        self.calls: list[tuple[str, str, Any | None]] = []
        presets, bases = live_model_views(include_required_grants=include_required_grants)
        self.responses = {
            "/api/v1/tasks/config": {"unrelated": "preserved"},
            "/api/v1/functions/list": OPENWEBUI.load_functions(),
            "/api/v1/models/export": presets,
            "/api/v1/models/base": bases,
        }

    def get(self, path: str) -> Any:
        self.calls.append(("GET", path, None))
        if path not in self.responses:
            raise AssertionError(f"unexpected GET {path}")
        return copy.deepcopy(self.responses[path])

    def post(self, path: str, payload: Any) -> Any:
        self.calls.append(("POST", path, copy.deepcopy(payload)))
        if path.startswith("/api/v1/functions/id/") and path.endswith("/update"):
            desired = OPENWEBUI.load_functions()[0]
            return {
                "id": desired["id"],
                "name": desired["name"],
                "is_active": desired["is_active"],
                "is_global": desired["is_global"],
            }
        if path == "/api/v1/models/model/access/update":
            model_id = payload["id"]
            for view_path in ("/api/v1/models/export", "/api/v1/models/base"):
                for model in self.responses[view_path]:
                    if model["id"] == model_id:
                        model["access_grants"] = copy.deepcopy(payload["access_grants"])
                        return copy.deepcopy(model)
            raise AssertionError(f"access update target not found: {model_id}")
        return {}


class OpenWebUIStatusTests(unittest.TestCase):

    def test_apply_owns_persisted_application_policy_and_testing_visibility(self) -> None:
        client = FakeApplyClient()
        OPENWEBUI.apply(client)
        posts = [(path, payload) for method, path, payload in client.calls if method == "POST"]
        app_payload = next(payload for path, payload in posts if path == "/api/v1/configs/import")
        self.assertEqual(app_payload, {"config": OPENWEBUI.desired_application()})
        self.assertFalse(app_payload["config"]["evaluation.arena.enable"])

        model_payload = next(payload for path, payload in posts if path == "/api/v1/models/import")
        base_overrides = {
            model["id"]: model
            for model in model_payload["models"]
            if model.get("base_model_id") is None
        }
        self.assertEqual(
            set(base_overrides),
            {
                "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl:latest",
                "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl:latest",
                "prod-translate-gemma4-sub-e4b-17s-q4-k-xl:latest",
                "prod-qwen35-9b-unsloth-q6-k:latest",
                "prod-gpt-oss20b-ggml-org-mxfp4:latest",
                "task-lfm25-1.2b-instruct-liquidai-q6-k:latest",
            },
        )
        self.assertTrue(all(model["is_active"] for model in base_overrides.values()))
        self.assertTrue(all((model.get("meta") or {}).get("hidden") is False for model in base_overrides.values()))

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

    def test_status_detects_testing_visibility_drift(self) -> None:
        bases = status_responses()["/api/v1/models/base"]
        target = next(
            model
            for model in bases
            if model["id"] == "task-lfm25-1.2b-instruct-liquidai-q6-k:latest"
        )
        target["meta"]["hidden"] = True
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                OPENWEBUI.status(FakeClient({"/api/v1/models/base": bases}), True),
                2,
            )
        self.assertIn("Package base-model override differs", output.getvalue())
        self.assertIn(".meta.hidden", output.getvalue())

        presets = status_responses()["/api/v1/models/export"]
        standard = next(model for model in presets if model["id"] == "bc250-office-standard")
        standard["meta"]["capabilities"]["builtin_tools"] = True
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                OPENWEBUI.status(FakeClient({"/api/v1/models/export": presets}), True),
                2,
            )
        self.assertIn(".meta.capabilities", output.getvalue())

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
        self.assertIn("Implementation/task models", text)
        self.assertIn("visible for testing", text)
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
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                OPENWEBUI.status(FakeClient({"/api/v1/models/export": {}}), True),
                1,
            )
        self.assertIn("Open WebUI model inspection unavailable for this API shape", output.getvalue())

    def test_status_rejects_non_list_base_model_view(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                OPENWEBUI.status(FakeClient({"/api/v1/models/base": {}}), True),
                1,
            )
        self.assertIn("Open WebUI model inspection unavailable for this API shape", output.getvalue())

    def test_status_rejects_non_list_function_export(self) -> None:
        with self.assertRaisesRegex(OPENWEBUI.ApiError, "function export response"):
            OPENWEBUI.status(FakeClient({"/api/v1/functions/export": {}}), True)

    def test_production_model_ids_and_minimum_acl_contract_are_exact(self) -> None:
        models = {model["id"]: model for model in desired_models()}
        active = {model_id for model_id, model in models.items() if model.get("is_active")}
        self.assertEqual(active, PRODUCTION_MODEL_IDS)
        for model_id in PRODUCTION_MODEL_IDS:
            self.assertEqual(OPENWEBUI.desired_access_grants(models[model_id]), [REQUIRED_READ])

        legacy = models["bc250-office-translation"]
        self.assertFalse(legacy["is_active"])
        self.assertEqual(OPENWEBUI.desired_access_grants(legacy), [])

    def test_testing_visibility_tool_policy_and_deep_reasoning_keep_alive(self) -> None:
        models = {model["id"]: model for model in desired_models()}
        hidden = {
            model_id
            for model_id, model in models.items()
            if (model.get("meta") or {}).get("hidden") is True
        }
        self.assertEqual(hidden, HIDDEN_MODEL_IDS)
        base_overrides = {
            model_id
            for model_id, model in models.items()
            if model.get("base_model_id") is None and model.get("is_active")
        }
        self.assertEqual(
            base_overrides,
            {
                "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl:latest",
                "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl:latest",
                "prod-translate-gemma4-sub-e4b-17s-q4-k-xl:latest",
                "prod-qwen35-9b-unsloth-q6-k:latest",
                "prod-gpt-oss20b-ggml-org-mxfp4:latest",
                "task-lfm25-1.2b-instruct-liquidai-q6-k:latest",
            },
        )
        for model_id in (
            "bc250-office-standard",
            "bc250-office-translation-de-fr",
            "bc250-office-translation-fr-de",
            "bc250-office-advanced",
            "bc250-office-deep-reasoning",
        ):
            self.assertFalse(models[model_id]["meta"]["capabilities"]["builtin_tools"])
        documents = models["bc250-office-documents"]
        self.assertTrue(documents["meta"]["capabilities"]["builtin_tools"])
        self.assertTrue(documents["meta"]["builtinTools"]["knowledge"])
        self.assertFalse(documents["meta"]["builtinTools"]["chats"])
        self.assertEqual(models["bc250-office-deep-reasoning"]["params"].get("keep_alive"), 0)
        self.assertEqual(models["prod-gpt-oss20b-ggml-org-mxfp4:latest"]["params"].get("keep_alive"), 0)
        self.assertNotIn("keep_alive", models["bc250-office-standard"]["params"])
        self.assertNotIn("keep_alive", models["bc250-office-advanced"]["params"])
        for model_id in (
            "bc250-office-standard",
            "bc250-office-documents",
            "bc250-office-advanced",
            "bc250-office-deep-reasoning",
        ):
            self.assertNotIn("system", models[model_id]["params"])

    def test_model_import_payload_does_not_replace_acl_state(self) -> None:
        payload = OPENWEBUI.model_import_payload(OPENWEBUI.load_models())
        self.assertTrue(all("access_grants" not in model for model in payload["models"]))
        deep = next(
            model for model in payload["models"] if model["id"] == "bc250-office-deep-reasoning"
        )
        self.assertEqual(deep["params"].get("keep_alive"), 0)

    def test_compatibility_assumption_matches_packaged_openwebui_pin(self) -> None:
        values: dict[str, str] = {}
        for line in (ROOT / "config/runtime.env").read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        self.assertEqual(values["BC250_OPEN_WEBUI_VERSION"], OPENWEBUI.OPENWEBUI_MODEL_API_VERSION)

    def test_status_reports_two_view_model_summary(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(OPENWEBUI.status(FakeClient(), True), 0)
        self.assertIn("Open WebUI models: 6 presets current, 6 base overrides current", output.getvalue())

    def test_status_detects_missing_base_override_with_correct_terminology(self) -> None:
        responses = status_responses()
        missing = "prod-gpt-oss20b-ggml-org-mxfp4:latest"
        responses["/api/v1/models/base"] = [
            model for model in responses["/api/v1/models/base"] if model["id"] != missing
        ]
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(OPENWEBUI.status(FakeClient(responses), True), 2)
        self.assertIn(f"Package base-model override missing: {missing}", output.getvalue())
        self.assertNotIn(f"Package model preset missing: {missing}", output.getvalue())

    def test_status_detects_missing_required_acl_but_allows_extra_grants(self) -> None:
        responses = status_responses()
        target = next(model for model in responses["/api/v1/models/export"] if model["id"] == "bc250-office-standard")
        target["access_grants"] = [
            {"principal_type": "group", "principal_id": "operators", "permission": "write"}
        ]
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(OPENWEBUI.status(FakeClient(responses), True), 2)
        self.assertIn("missing user:*:read", output.getvalue())

        target["access_grants"].append(copy.deepcopy(REQUIRED_READ))
        self.assertEqual(OPENWEBUI.status(FakeClient(responses), True), 0)

    def test_status_allows_historical_grant_on_inactive_legacy_record(self) -> None:
        responses = status_responses()
        legacy = next(
            model for model in responses["/api/v1/models/export"] if model["id"] == "bc250-office-translation"
        )
        legacy["access_grants"] = [copy.deepcopy(REQUIRED_READ)]
        self.assertEqual(OPENWEBUI.status(FakeClient(responses), True), 0)

    def test_status_detects_inactive_required_model(self) -> None:
        responses = status_responses()
        target = next(
            model for model in responses["/api/v1/models/base"]
            if model["id"] == "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl:latest"
        )
        target["is_active"] = False
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(OPENWEBUI.status(FakeClient(responses), True), 2)
        self.assertIn(
            "Package base-model override differs: prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl:latest.is_active",
            output.getvalue(),
        )

    def test_status_detects_deep_keep_alive_drift(self) -> None:
        responses = status_responses()
        deep = next(
            model for model in responses["/api/v1/models/export"]
            if model["id"] == "bc250-office-deep-reasoning"
        )
        deep["params"].pop("keep_alive", None)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(OPENWEBUI.status(FakeClient(responses), True), 2)
        self.assertIn("Package model preset differs: bc250-office-deep-reasoning.params", output.getvalue())

    def test_status_bad_model_api_shape_is_inspection_error_not_mass_drift(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                OPENWEBUI.status(FakeClient({"/api/v1/models/base": {"items": []}}), True),
                1,
            )
        text = output.getvalue()
        self.assertIn("Open WebUI model inspection unavailable for this API shape", text)
        self.assertNotIn("Package base-model override missing", text)

    def test_status_ignores_unrelated_operator_model(self) -> None:
        responses = status_responses()
        responses["/api/v1/models/export"].append(
            {
                "id": "operator-owned-preset",
                "base_model_id": "operator-base:latest",
                "name": "Operator model",
                "params": {},
                "meta": {},
                "is_active": True,
                "access_grants": [],
            }
        )
        self.assertEqual(OPENWEBUI.status(FakeClient(responses), True), 0)

    def test_apply_acl_convergence_is_additive_and_idempotent(self) -> None:
        client = FakeApplyClient(include_required_grants=False)
        standard = next(
            model for model in client.responses["/api/v1/models/export"]
            if model["id"] == "bc250-office-standard"
        )
        unrelated = {"principal_type": "group", "principal_id": "operators", "permission": "write"}
        standard["access_grants"] = [copy.deepcopy(unrelated)]
        legacy = next(
            model for model in client.responses["/api/v1/models/export"]
            if model["id"] == "bc250-office-translation"
        )
        legacy["access_grants"] = [copy.deepcopy(REQUIRED_READ)]

        desired = desired_models()
        presets = OPENWEBUI.model_view_map(
            client.get("/api/v1/models/export"), "model export", base_model_id_is_none=False
        )
        bases = OPENWEBUI.model_view_map(
            client.get("/api/v1/models/base"), "base-model view", base_model_id_is_none=True
        )
        OPENWEBUI.apply_model_access(client, desired, presets, bases)

        updates = [
            payload
            for method, path, payload in client.calls
            if method == "POST" and path == "/api/v1/models/model/access/update"
        ]
        self.assertEqual(len(updates), 12)
        standard_update = next(payload for payload in updates if payload["id"] == "bc250-office-standard")
        self.assertIn(unrelated, standard_update["access_grants"])
        self.assertIn(REQUIRED_READ, standard_update["access_grants"])
        self.assertNotIn("bc250-office-translation", {payload["id"] for payload in updates})
        self.assertEqual(legacy["access_grants"], [REQUIRED_READ])

        client.calls.clear()
        presets = OPENWEBUI.model_view_map(
            client.get("/api/v1/models/export"), "model export", base_model_id_is_none=False
        )
        bases = OPENWEBUI.model_view_map(
            client.get("/api/v1/models/base"), "base-model view", base_model_id_is_none=True
        )
        OPENWEBUI.apply_model_access(client, desired, presets, bases)
        self.assertFalse(
            any(
                method == "POST" and path == "/api/v1/models/model/access/update"
                for method, path, _payload in client.calls
            )
        )

    def test_status_does_not_expose_api_token(self) -> None:
        secret = "owui-secret-token-do-not-print-0121"
        with tempfile.TemporaryDirectory() as temporary:
            token_path = Path(temporary) / "owui.key"
            token_path.write_text(secret + "\n", encoding="utf-8")
            token_path.chmod(0o600)
            fake = FakeClient()
            stdout = io.StringIO()
            stderr = io.StringIO()
            argv = ["bc250-openwebui-setup", "status", "--token-file", str(token_path)]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(OPENWEBUI, "Client", return_value=fake),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                self.assertEqual(OPENWEBUI.main(), 0)
            self.assertNotIn(secret, stdout.getvalue())
            self.assertNotIn(secret, stderr.getvalue())

    def test_translation_roles_match_stage2e_contract_exactly(self) -> None:
        prompt_path = ROOT / "config/openwebui/prompts/translation-explicit-direction-v1.txt"
        prompt = prompt_path.read_text(encoding="utf-8")
        self.assertEqual(
            hashlib.sha256(prompt.encode()).hexdigest(),
            "93daa33b148423cfc7f909c2c4b1f1ba7567c9cfe21ffa599c79b0b6b1175a52",
        )
        models = {item["id"]: item for item in OPENWEBUI.load_models()["models"]}
        for model_id in (
            "bc250-office-translation-de-fr",
            "bc250-office-translation-fr-de",
        ):
            model = models[model_id]
            self.assertEqual(model["params"]["system"], prompt)
            self.assertIn("Preserve legal and contractual modality exactly", model["params"]["system"])
            self.assertEqual(model["params"]["max_tokens"], 2048)
            self.assertNotIn("think", model["params"])
            self.assertEqual(
                model["meta"]["filterIds"], ["bc250_translation_direction"]
            )
            self.assertEqual(
                model["base_model_id"],
                "prod-translate-gemma4-sub-e4b-17s-q4-k-xl:latest",
            )

        main_models = OPENWEBUI.desired_ollama()["OLLAMA_API_CONFIGS"]["0"]["model_ids"]
        task_models = OPENWEBUI.desired_ollama()["OLLAMA_API_CONFIGS"]["1"]["model_ids"]
        self.assertEqual(main_models, [])
        self.assertEqual(task_models, [])
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
                + "and preserve the document structure. Preserve legal/contractual modality without "
                + "strengthening or weakening obligations, permissions, recommendations or prohibitions. "
                + "Return only the translation.\n\n"
                + "[CURRENT_SOURCE]\n",
                "Guten Tag.\nZweite Zeile.",
            ),
            "bc250-office-translation-fr-de": (
                "Translate from French to German. Translate every ordinary-language source word "
                + "and preserve the document structure. Preserve legal/contractual modality without "
                + "strengthening or weakening obligations, permissions, recommendations or prohibitions. "
                + "Return only the translation.\n\n"
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
