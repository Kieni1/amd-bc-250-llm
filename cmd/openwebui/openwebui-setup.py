#!/usr/bin/env python3
"""Configure the package-owned Open WebUI 0.11.4 baseline through supported APIs."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_URL = "http://127.0.0.1:3000"
DEFAULT_MODELS = Path("/usr/share/bc250-llm-server/openwebui/models.json")
SOURCE_MODELS = Path(__file__).resolve().parents[2] / "config/openwebui/models.json"
DEFAULT_DESIRED = Path("/usr/share/bc250-llm-server/openwebui/desired-state.json")
SOURCE_DESIRED = Path(__file__).resolve().parents[2] / "config/openwebui/desired-state.json"
DEFAULT_FUNCTIONS = Path("/usr/share/bc250-llm-server/openwebui/functions.json")
SOURCE_FUNCTIONS = Path(__file__).resolve().parents[2] / "config/openwebui/functions.json"

# The model-view/access contract below is qualified against the packaged Open WebUI pin.
OPENWEBUI_MODEL_API_VERSION = "0.11.4"
AUTO_VISIBLE_TAG = "bc250-auto-visible"
NORMAL_PROVIDER_LANES = {
    "main": "http://127.0.0.1:11434",
    "task": "http://127.0.0.1:11435",
}
REQUEST_CUSTOM_PARAM_KEYS = frozenset(
    {
        "think",
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "presence_penalty",
        "repeat_penalty",
    }
)
NATIVE_MODEL_PARAM_KEYS = frozenset({"system", "max_tokens", "keep_alive", "custom_params"})
TESTING_MODEL_POLICY_KEYS = frozenset({"description", "tags", "custom_params", "qualification", "ordinary_user_visible"})
_DISCOVERED_MODEL_CACHE: dict[str, list[str]] | None = None


def desired_file() -> Path:
    override = os.environ.get("BC250_OWUI_DESIRED_STATE")
    if override:
        return Path(override)
    if DEFAULT_DESIRED.is_file():
        return DEFAULT_DESIRED
    return SOURCE_DESIRED


def load_desired_state() -> dict[str, Any]:
    path = desired_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read Open WebUI desired state {path}: {exc}") from exc
    if not isinstance(data, dict) or any(
        not isinstance(data.get(k), dict)
        for k in ("ollama", "task", "embedding", "rag", "application")
    ):
        raise RuntimeError(f"invalid Open WebUI desired state: {path}")
    return data


DESIRED = load_desired_state()
TASK_MODEL = str(DESIRED["task"]["TASK_MODEL"])
EMBED_MODEL = str(DESIRED["embedding"]["RAG_EMBEDDING_MODEL"])


class ApiError(RuntimeError):
    """HTTP/API failure with a concise CLI message."""


class Client:
    def __init__(self, base_url: str, token: str | None = None, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, payload: Any | None = None) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise ApiError(f"{method} {path}: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"{method} {path}: {exc.reason}") from exc
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ApiError(f"{method} {path}: response was not JSON") from exc

    def probe(self, path: str = "/") -> None:
        headers = {"Accept": "*/*"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            f"{self.base_url}{path}", headers=headers, method="GET"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response.read(1)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise ApiError(f"GET {path}: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"GET {path}: {exc.reason}") from exc

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: Any) -> Any:
        return self.request("POST", path, payload)


def models_file() -> Path:
    override = os.environ.get("BC250_OWUI_MODELS_FILE")
    if override:
        return Path(override)
    if DEFAULT_MODELS.is_file():
        return DEFAULT_MODELS
    return SOURCE_MODELS


def load_models() -> dict[str, Any]:
    path = models_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiError(f"cannot read model preset file {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise ApiError(f"invalid model preset file: {path}")
    policies = data.get("testing_model_policies", {})
    if not isinstance(policies, dict):
        raise ApiError(f"invalid testing_model_policies in {path}")
    validate_model_request_policy_shape(data)
    return data


def validate_model_request_policy_shape(document: dict[str, Any]) -> None:
    """Fail closed when request-only sampler policy is stored outside custom_params."""
    models = document.get("models", [])
    if not isinstance(models, list):
        raise ApiError("model preset file models is not a list")
    for index, raw in enumerate(models):
        if not isinstance(raw, dict):
            raise ApiError(f"model record {index} is not an object")
        model_id = str(raw.get("id") or f"index-{index}")
        root_misplaced = sorted(REQUEST_CUSTOM_PARAM_KEYS.intersection(raw))
        if root_misplaced:
            raise ApiError(
                f"model {model_id} request params must be under params.custom_params: "
                + ", ".join(root_misplaced)
            )
        params = raw.get("params", {})
        if not isinstance(params, dict):
            raise ApiError(f"model {model_id} params is not an object")
        params_misplaced = sorted(REQUEST_CUSTOM_PARAM_KEYS.intersection(params))
        if params_misplaced:
            raise ApiError(
                f"model {model_id} request params must be under params.custom_params: "
                + ", ".join(params_misplaced)
            )
        unexpected_params = sorted(set(params) - NATIVE_MODEL_PARAM_KEYS)
        if unexpected_params:
            raise ApiError(
                f"model {model_id} has unsupported direct params; request-specific values "
                "belong under params.custom_params: " + ", ".join(unexpected_params)
            )
        custom_params = params.get("custom_params")
        if custom_params is not None and not isinstance(custom_params, dict):
            raise ApiError(f"model {model_id} params.custom_params is not an object")

    policies = document.get("testing_model_policies", {})
    if not isinstance(policies, dict):
        raise ApiError("testing_model_policies is not an object")
    for model_id, raw in policies.items():
        if not isinstance(raw, dict):
            raise ApiError(f"testing model policy {model_id} is not an object")
        unexpected_policy_keys = sorted(set(raw) - TESTING_MODEL_POLICY_KEYS)
        if unexpected_policy_keys:
            raise ApiError(
                f"testing model policy {model_id} has unsupported keys; request-specific "
                "values belong under custom_params: " + ", ".join(unexpected_policy_keys)
            )
        misplaced = sorted(REQUEST_CUSTOM_PARAM_KEYS.intersection(raw))
        if misplaced:
            raise ApiError(
                f"testing model policy {model_id} request params must be under custom_params: "
                + ", ".join(misplaced)
            )
        custom_params = raw.get("custom_params")
        if custom_params is not None and not isinstance(custom_params, dict):
            raise ApiError(
                f"testing model policy {model_id} custom_params is not an object"
            )


def testing_model_policies(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = document.get("testing_model_policies", {})
    if not isinstance(raw, dict):
        raise ApiError("testing_model_policies is not an object")
    policies: dict[str, dict[str, Any]] = {}
    for model_id, value in raw.items():
        if not isinstance(model_id, str) or not model_id or not isinstance(value, dict):
            raise ApiError("invalid testing model policy entry")
        policies[model_id] = value
    return policies


def discover_normal_provider_models() -> dict[str, list[str]]:
    global _DISCOVERED_MODEL_CACHE
    if _DISCOVERED_MODEL_CACHE is not None:
        return {lane: list(models) for lane, models in _DISCOVERED_MODEL_CACHE.items()}
    if os.environ.get("BC250_OWUI_MODEL_DISCOVERY", "1").strip().lower() in {"0", "false", "no"}:
        _DISCOVERED_MODEL_CACHE = {}
        return {}
    discovered: dict[str, list[str]] = {}
    for lane, default_url in NORMAL_PROVIDER_LANES.items():
        env_name = f"BC250_OLLAMA_{lane.upper()}_URL"
        base_url = os.environ.get(env_name, default_url).rstrip("/")
        request = urllib.request.Request(f"{base_url}/api/tags", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=1.0) as response:
                payload = json.loads(response.read())
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            continue
        rows = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            continue
        names = sorted({
            str(row.get("name") or row.get("model") or "").strip()
            for row in rows if isinstance(row, dict)
        } - {""})
        discovered[lane] = names
    _DISCOVERED_MODEL_CACHE = discovered
    return {lane: list(models) for lane, models in discovered.items()}


def auto_visible_model_record(
    model_id: str, lane: str, policy: dict[str, Any] | None = None
) -> dict[str, Any]:
    policy = policy or {}
    tags = [
        {"name": "BC250"},
        {"name": "testing"},
        {"name": lane},
        {"name": AUTO_VISIBLE_TAG},
    ]
    for tag in policy.get("tags", []):
        if isinstance(tag, str) and tag and all(item["name"] != tag for item in tags):
            tags.append({"name": tag})
    custom_params = policy.get("custom_params", {})
    params = {"custom_params": custom_params} if isinstance(custom_params, dict) and custom_params else {}
    ordinary_user_visible = policy.get("ordinary_user_visible", True) is not False
    description = str(policy.get("description") or (
        f"Installed {lane}-lane model exposed for pre-v1 comparison testing. "
        "Use a curated Office role for normal product use."
    ))
    qualification = policy.get("qualification")
    meta: dict[str, Any] = {
        "hidden": not ordinary_user_visible,
        "description": description,
        "tags": tags,
        "capabilities": {"builtin_tools": False, "file_context": True},
        "bc250_managed": "testing-discovery",
        "bc250_lane": lane,
        "bc250_ordinary_user_visible": ordinary_user_visible,
    }
    if isinstance(qualification, dict) and qualification:
        meta["bc250_qualification"] = qualification
    record: dict[str, Any] = {
        "id": model_id,
        "base_model_id": None,
        "name": model_id,
        "meta": meta,
        "params": params,
        "is_active": True,
    }
    if ordinary_user_visible:
        record["access_grants"] = [
            {"principal_type": "user", "principal_id": "*", "permission": "read"}
        ]
    return record


def effective_model_document(
    document: dict[str, Any], inventory: dict[str, list[str]] | None = None
) -> dict[str, Any]:
    models = [dict(model) for model in require_list(document.get("models"), "model records")]
    known = {str(model.get("id")) for model in models}
    policies = testing_model_policies(document)
    lanes = discover_normal_provider_models() if inventory is None else inventory
    for lane in ("main", "task"):
        for model_id in lanes.get(lane, []):
            if model_id in known:
                continue
            models.append(auto_visible_model_record(model_id, lane, policies.get(model_id)))
            known.add(model_id)
    return {"models": models}


def is_auto_visible_model(model: dict[str, Any]) -> bool:
    meta = model.get("meta") if isinstance(model.get("meta"), dict) else {}
    return meta.get("bc250_managed") == "testing-discovery"


def remove_stale_auto_visible_models(
    client: Client,
    desired_ids: set[str],
    base_overrides: dict[str, dict[str, Any]],
    discovered_lanes: set[str],
) -> None:
    """Remove stale auto-managed records only for provider lanes we actually inspected.

    A transient /api/tags failure must never make an entire lane look empty and trigger
    destructive cleanup. Static package-owned model records are never handled here.
    """
    for model_id, live in sorted(base_overrides.items()):
        if model_id in desired_ids or not is_auto_visible_model(live):
            continue
        meta = live.get("meta") if isinstance(live.get("meta"), dict) else {}
        lane = str(meta.get("bc250_lane") or "")
        if lane not in discovered_lanes:
            continue
        result = client.post("/api/v1/models/model/delete", {"id": model_id})
        if result is not True and not (isinstance(result, dict) and result.get("success") is True):
            raise ApiError(f"Open WebUI did not delete stale package-managed testing model {model_id}")


def functions_file() -> Path:
    override = os.environ.get("BC250_OWUI_FUNCTIONS_FILE")
    if override:
        return Path(override)
    if DEFAULT_FUNCTIONS.is_file():
        return DEFAULT_FUNCTIONS
    return SOURCE_FUNCTIONS


def load_functions() -> list[dict[str, Any]]:
    path = functions_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiError(f"cannot read Open WebUI function manifest {path}: {exc}") from exc
    entries = data.get("functions") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ApiError(f"invalid Open WebUI function manifest: {path}")

    functions: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ApiError(f"invalid Open WebUI function entry in {path}")
        function_id = entry.get("id")
        name = entry.get("name")
        content_file = entry.get("content_file")
        meta = entry.get("meta", {})
        if not all(isinstance(value, str) and value for value in (function_id, name, content_file)):
            raise ApiError(f"invalid Open WebUI function identity in {path}")
        if not isinstance(meta, dict):
            raise ApiError(f"invalid Open WebUI function metadata for {function_id}")
        source = path.parent / content_file
        try:
            content = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise ApiError(f"cannot read Open WebUI function source {source}: {exc}") from exc
        functions.append(
            {
                "id": function_id,
                "name": name,
                "content": content,
                "meta": meta,
                "is_active": bool(entry.get("is_active", True)),
                "is_global": bool(entry.get("is_global", False)),
            }
        )
    return functions


def desired_ollama() -> dict[str, Any]:
    return dict(DESIRED["ollama"])


def desired_task() -> dict[str, Any]:
    return dict(DESIRED["task"])


def desired_embedding() -> dict[str, Any]:
    return dict(DESIRED["embedding"])


def desired_rag() -> dict[str, Any]:
    return dict(DESIRED["rag"])


def desired_application() -> dict[str, Any]:
    return dict(DESIRED["application"])


def authenticate(client: Client, action: str) -> str:
    if action == "create":
        print("Create the first Open WebUI administrator. Credentials are sent only to local Open WebUI and are not stored by this package.")
        name = input("Admin name: ").strip()
        email = input("Admin email: ").strip()
        password = getpass.getpass("Admin password: ")
        confirm = getpass.getpass("Confirm password: ")
        if not name or not email or not password:
            raise ApiError("name, email and password are required")
        if password != confirm:
            raise ApiError("passwords do not match")
        result = client.post(
            "/api/v1/auths/signup", {"name": name, "email": email, "password": password}
        )
    else:
        print("Sign in to the existing Open WebUI administrator. Credentials are not stored by this package.")
        email = input("Admin email: ").strip()
        password = getpass.getpass("Admin password: ")
        result = client.post("/api/v1/auths/signin", {"email": email, "password": password})
    token = result.get("token") if isinstance(result, dict) else None
    role = result.get("role") if isinstance(result, dict) else None
    if not token:
        raise ApiError("Open WebUI did not return an authentication token")
    if role != "admin":
        raise ApiError(f"authenticated user role is {role!r}, not 'admin'")
    return token


def apply_functions(client: Client) -> None:
    listed = require_list(client.get("/api/v1/functions/list"), "function list")
    existing_ids = {
        item.get("id") for item in listed if isinstance(item, dict) and item.get("id")
    }
    for desired in load_functions():
        payload = {
            "id": desired["id"],
            "name": desired["name"],
            "content": desired["content"],
            "meta": desired["meta"],
        }
        if desired["id"] in existing_ids:
            result = client.post(f"/api/v1/functions/id/{desired['id']}/update", payload)
        else:
            result = client.post("/api/v1/functions/create", payload)
        current = require_object(result, f"function {desired['id']}")
        if bool(current.get("is_active")) != desired["is_active"]:
            current = require_object(
                client.post(f"/api/v1/functions/id/{desired['id']}/toggle", {}),
                f"function {desired['id']} active toggle",
            )
        if bool(current.get("is_global")) != desired["is_global"]:
            require_object(
                client.post(f"/api/v1/functions/id/{desired['id']}/toggle/global", {}),
                f"function {desired['id']} global toggle",
            )


def apply(client: Client) -> None:
    client.post("/ollama/config/update", desired_ollama())

    client.post("/api/v1/configs/import", {"config": desired_application()})

    task = client.get("/api/v1/tasks/config")
    if not isinstance(task, dict):
        raise ApiError("task config response was not an object")
    task.update(desired_task())
    client.post("/api/v1/tasks/config/update", task)
    client.post("/api/v1/retrieval/embedding/update", desired_embedding())
    client.post("/api/v1/retrieval/config/update", desired_rag())
    apply_functions(client)
    source_models = load_models()
    discovered_inventory = discover_normal_provider_models()
    desired_models = effective_model_document(source_models, discovered_inventory)
    client.post("/api/v1/models/import", model_import_payload(desired_models))
    try:
        preset_models, base_models = load_live_model_views(client)
    except ApiError as exc:
        raise ApiError(
            f"Open WebUI model inspection unavailable for this API shape: {exc}"
        ) from exc
    desired_ids = {str(model.get("id")) for model in desired_models["models"]}
    remove_stale_auto_visible_models(
        client, desired_ids, base_models, set(discovered_inventory)
    )
    if any(model_id not in desired_ids and is_auto_visible_model(model) for model_id, model in base_models.items()):
        preset_models, base_models = load_live_model_views(client)
    apply_model_access(client, desired_models["models"], preset_models, base_models)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)



def multiple_models_state(application: dict[str, Any]) -> bool | None:
    """Return effective admin-owned multi-model-chat permission when exposed by config export."""
    direct = application.get("user.permissions.chat.multiple_models")
    if isinstance(direct, bool):
        return direct
    permissions = application.get("user.permissions")
    if isinstance(permissions, dict):
        chat = permissions.get("chat")
        if isinstance(chat, dict) and isinstance(chat.get("multiple_models"), bool):
            return chat["multiple_models"]
    return None

def values_match(key: str, current: Any, expected: Any) -> bool:
    if key == "ALLOWED_FILE_EXTENSIONS" and isinstance(current, list) and isinstance(expected, list):
        return sorted(str(value) for value in current) == sorted(str(value) for value in expected)
    return canonical(current) == canonical(expected)


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApiError(f"{label} response was not an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ApiError(f"{label} response was not a list")
    return value


def model_record_kind(model: dict[str, Any]) -> str:
    if "base_model_id" not in model:
        raise ApiError(f"model record lacks base_model_id: {model.get('id', 'unknown')}")
    return "base_override" if model["base_model_id"] is None else "preset"


def model_record_label(model: dict[str, Any]) -> str:
    return "direct/base-model override" if model_record_kind(model) == "base_override" else "workspace/derived model"


def model_import_payload(document: dict[str, Any]) -> dict[str, Any]:
    models = document.get("models")
    if not isinstance(models, list):
        raise ApiError("invalid model preset file: models is not a list")
    payload = {"models": [
        {
            key: value
            for key, value in require_object(model, "model record").items()
            if key != "access_grants"
        }
        for model in models
    ]}
    return payload


def access_grant_key(grant: Any, label: str) -> tuple[str, str, str]:
    item = require_object(grant, label)
    principal_type = item.get("principal_type")
    principal_id = item.get("principal_id")
    permission = item.get("permission")
    if principal_type not in {"user", "group", "anyone"}:
        raise ApiError(f"{label} has unsupported principal_type")
    if not isinstance(principal_id, str) or not principal_id:
        raise ApiError(f"{label} has invalid principal_id")
    if permission not in {"read", "write"}:
        raise ApiError(f"{label} has unsupported permission")
    if principal_type == "anyone" and (principal_id != "*" or permission != "read"):
        raise ApiError(f"{label} has unsupported anyone grant")
    return principal_type, principal_id, permission


def desired_access_grants(model: dict[str, Any]) -> list[dict[str, str]]:
    raw = model.get("access_grants", [])
    grants = require_list(raw, f"desired access grants for {model.get('id', 'unknown')}")
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, grant in enumerate(grants):
        key = access_grant_key(grant, f"desired access grant {index}")
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {"principal_type": key[0], "principal_id": key[1], "permission": key[2]}
        )
    return result


def access_grant_keys(value: Any, label: str) -> set[tuple[str, str, str]]:
    grants = require_list(value, label)
    return {
        access_grant_key(grant, f"{label} item {index}")
        for index, grant in enumerate(grants)
    }


def merge_access_grants(
    live: Any, required: list[dict[str, str]], label: str
) -> list[dict[str, str]]:
    live_grants = require_list(live, label)
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, grant in enumerate([*live_grants, *required]):
        key = access_grant_key(grant, f"{label} item {index}")
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            {"principal_type": key[0], "principal_id": key[1], "permission": key[2]}
        )
    return merged


def model_view_map(
    value: Any, label: str, *, base_model_id_is_none: bool
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(require_list(value, label)):
        item = require_object(raw, f"{label} item {index}")
        model_id = item.get("id")
        if not isinstance(model_id, str) or not model_id:
            raise ApiError(f"{label} item {index} has invalid id")
        if "base_model_id" not in item:
            raise ApiError(f"{label} item {model_id} lacks base_model_id")
        if (item.get("base_model_id") is None) != base_model_id_is_none:
            raise ApiError(f"{label} item {model_id} has unexpected base_model_id shape")
        if model_id in records:
            raise ApiError(f"{label} contains duplicate model id: {model_id}")
        if not isinstance(item.get("access_grants", []), list):
            raise ApiError(f"{label} item {model_id} access_grants was not a list")
        records[model_id] = item
    return records


def load_live_model_views(
    client: Client,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    # Open WebUI v0.11.4 represents curated presets and raw-model overrides in
    # separate API views. Keep this explicit so a future pin change fails as an
    # inspection-compatibility issue instead of looking like mass desired-state drift.
    presets = model_view_map(
        client.get("/api/v1/models/export"),
        "model export",
        base_model_id_is_none=False,
    )
    base_overrides = model_view_map(
        client.get("/api/v1/models/base"),
        "base-model view",
        base_model_id_is_none=True,
    )
    return presets, base_overrides


def live_model_record(
    desired: dict[str, Any],
    presets: dict[str, dict[str, Any]],
    base_overrides: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    source = base_overrides if model_record_kind(desired) == "base_override" else presets
    return source.get(str(desired.get("id", "")))


def apply_model_access(
    client: Client,
    models: list[dict[str, Any]],
    presets: dict[str, dict[str, Any]],
    base_overrides: dict[str, dict[str, Any]],
) -> None:
    package_public_read = ("user", "*", "read")
    for desired in models:
        required = desired_access_grants(desired)
        model_id = desired.get("id")
        if not isinstance(model_id, str) or not model_id:
            raise ApiError("package model record has invalid id")
        live = live_model_record(desired, presets, base_overrides)
        if not isinstance(live, dict):
            raise ApiError(
                f"package {model_record_label(desired)} missing after import: {model_id}"
            )
        live_grants = require_list(
            live.get("access_grants", []), f"access grants for {model_id}"
        )
        live_keys = access_grant_keys(live_grants, f"access grants for {model_id}")
        required_keys = {
            access_grant_key(grant, f"required grant for {model_id}")
            for grant in required
        }
        meta = desired.get("meta") if isinstance(desired.get("meta"), dict) else {}
        package_managed_private = (
            is_auto_visible_model(desired)
            and meta.get("bc250_ordinary_user_visible") is False
        )
        needs_remove_public = package_managed_private and package_public_read in live_keys
        if required_keys <= live_keys and not needs_remove_public:
            continue
        merged = merge_access_grants(live_grants, required, f"access grants for {model_id}")
        if needs_remove_public:
            merged = [
                grant
                for grant in merged
                if access_grant_key(grant, f"access grants for {model_id}") != package_public_read
            ]
        updated = require_object(
            client.post(
                "/api/v1/models/model/access/update",
                {"id": model_id, "name": desired.get("name") or model_id, "access_grants": merged},
            ),
            f"model access update {model_id}",
        )
        updated_keys = access_grant_keys(
            updated.get("access_grants", []), f"updated access grants for {model_id}"
        )
        if not required_keys <= updated_keys:
            raise ApiError(f"Open WebUI did not retain required access grants for {model_id}")
        if package_managed_private and package_public_read in updated_keys:
            raise ApiError(f"Open WebUI retained package public read access for {model_id}")


def print_verbose_summary(models: list[dict[str, Any]], functions: list[dict[str, Any]]) -> None:
    print()
    print("Package-owned Open WebUI roles")
    implementation_models: list[tuple[str, bool, dict[str, Any], str]] = []
    for model in models:
        if not bool(model.get("is_active")):
            continue
        model_id = str(model.get("id") or "unknown")
        base_value = model.get("base_model_id")
        params = model.get("params") if isinstance(model.get("params"), dict) else {}
        meta = model.get("meta") if isinstance(model.get("meta"), dict) else {}
        if base_value is None:
            lane = str(meta.get("bc250_lane") or "package")
            implementation_models.append((model_id, bool(meta.get("hidden")), params, lane))
            continue
        base = str(base_value)
        filters = meta.get("filterIds") if isinstance(meta.get("filterIds"), list) else []
        extras: list[str] = []
        if "max_tokens" in params:
            extras.append(f"max_tokens={params['max_tokens']}")
        if "keep_alive" in params:
            extras.append(f"keep_alive={params['keep_alive']}")
        custom_params = params.get("custom_params") if isinstance(params.get("custom_params"), dict) else {}
        if custom_params:
            effective = ",".join(f"{key}={custom_params[key]}" for key in sorted(custom_params))
            extras.append(f"effective={effective}")
        elif "think" in params:
            extras.append(f"think={params['think']}")
        elif "translation" in model_id:
            extras.append("think=omitted")
        if filters:
            extras.append("filters=" + ",".join(str(value) for value in filters))
        suffix = f"  ({'; '.join(extras)})" if extras else ""
        print(f"  {model_id:<36} -> {base}{suffix}")

    if implementation_models:
        print()
        print("Implementation/task models")
        for model_id, hidden, params, lane in implementation_models:
            visibility = "admin/testing only" if hidden else "ordinary-user testing"
            custom_params = params.get("custom_params") if isinstance(params.get("custom_params"), dict) else {}
            effective = ""
            if custom_params:
                values = ",".join(f"{key}={custom_params[key]}" for key in sorted(custom_params))
                effective = f"; effective={values}"
            print(f"  {model_id:<52} {visibility}; lane={lane}{effective}")

    print()
    print("Task and RAG")
    print(f"  task model:       {TASK_MODEL}")
    print(f"  embedding model:  {EMBED_MODEL}")
    print(f"  extraction:       {DESIRED['rag'].get('CONTENT_EXTRACTION_ENGINE', 'unknown')}")
    print(
        "  chunks:           "
        f"{DESIRED['rag'].get('CHUNK_SIZE', 'unknown')} / "
        f"overlap {DESIRED['rag'].get('CHUNK_OVERLAP', 'unknown')}"
    )

    if functions:
        print()
        print("Package-owned functions")
        for function in functions:
            state = "active" if bool(function.get("is_active")) else "inactive"
            scope = "global" if bool(function.get("is_global")) else "model-specific"
            print(f"  {function.get('id', 'unknown')}: {state}, {scope}")


def status(client: Client, authenticated: bool, *, verbose: bool = False) -> int:
    try:
        client.probe("/")
    except ApiError as exc:
        print(f"Open WebUI: unavailable ({exc})")
        return 1
    print("Open WebUI: reachable")
    if not authenticated:
        print("Desired-state drift: skipped (set OWUI_API_KEY or --token-file for authenticated comparison)")
        if verbose:
            print("Verbose verified summary: skipped (administrator API key required)")
        return 0

    problems: list[str] = []
    application = require_object(
        client.get("/api/v1/configs/export"), "application config"
    )
    for key, value in desired_application().items():
        if not values_match(key, application.get(key), value):
            problems.append(f"Application config differs: {key}")

    ollama = require_object(client.get("/ollama/config"), "Ollama config")
    desired = desired_ollama()
    for key in ("ENABLE_OLLAMA_API", "OLLAMA_BASE_URLS", "OLLAMA_API_CONFIGS"):
        if canonical(ollama.get(key)) != canonical(desired[key]):
            problems.append(f"Ollama config differs: {key}")

    task = require_object(client.get("/api/v1/tasks/config"), "task config")
    expected_task = desired_task()
    for key, value in expected_task.items():
        if canonical(task.get(key)) != canonical(value):
            problems.append(f"Task config differs: {key}")

    embedding = require_object(
        client.get("/api/v1/retrieval/embedding"), "embedding config"
    )
    expected_embedding = desired_embedding()
    for key in (
        "RAG_EMBEDDING_ENGINE",
        "RAG_EMBEDDING_MODEL",
        "RAG_EMBEDDING_BATCH_SIZE",
        "ENABLE_ASYNC_EMBEDDING",
        "RAG_EMBEDDING_CONCURRENT_REQUESTS",
        "ollama_config",
    ):
        if canonical(embedding.get(key)) != canonical(expected_embedding[key]):
            problems.append(f"Embedding config differs: {key}")

    rag = require_object(client.get("/api/v1/retrieval/config"), "RAG config")
    for key, value in desired_rag().items():
        if not values_match(key, rag.get(key), value):
            problems.append(f"RAG config differs: {key}")

    exported_functions = require_list(
        client.get("/api/v1/functions/export"), "function export"
    )
    live_functions = {
        item.get("id"): item for item in exported_functions if isinstance(item, dict)
    }
    for desired_function in load_functions():
        function_id = desired_function["id"]
        live = live_functions.get(function_id)
        if not isinstance(live, dict):
            problems.append(f"Package function missing: {function_id}")
            continue
        if live.get("name") != desired_function["name"]:
            problems.append(f"Package function name differs: {function_id}")
        if live.get("content") != desired_function["content"]:
            problems.append(f"Package function content differs: {function_id}")
        live_meta = live.get("meta") if isinstance(live.get("meta"), dict) else {}
        if live_meta.get("description") != desired_function["meta"].get("description"):
            problems.append(f"Package function description differs: {function_id}")
        if bool(live.get("is_active")) != desired_function["is_active"]:
            problems.append(f"Package function active state differs: {function_id}")
        if bool(live.get("is_global")) != desired_function["is_global"]:
            problems.append(f"Package function global state differs: {function_id}")

    discovered_inventory = discover_normal_provider_models()
    desired_document = effective_model_document(load_models(), discovered_inventory)
    desired_models = desired_document["models"]
    try:
        preset_models, base_models = load_live_model_views(client)
    except ApiError as exc:
        print(f"Open WebUI model inspection unavailable for this API shape: {exc}")
        return 1

    active_presets = 0
    active_base_overrides = 0
    for model in desired_models:
        model_id = model["id"]
        kind = model_record_kind(model)
        label = model_record_label(model)
        if bool(model.get("is_active")):
            if kind == "preset":
                active_presets += 1
            else:
                active_base_overrides += 1
        live = live_model_record(model, preset_models, base_models)
        if not isinstance(live, dict):
            problems.append(f"Package {label} missing: {model_id}")
            continue
        for key in ("base_model_id", "name", "params", "is_active"):
            if canonical(live.get(key)) != canonical(model.get(key)):
                problems.append(f"Package {label} differs: {model_id}.{key}")
        desired_meta = model.get("meta") if isinstance(model.get("meta"), dict) else {}
        live_meta = live.get("meta") if isinstance(live.get("meta"), dict) else {}
        for key in (
            "description", "tags", "filterIds", "defaultFilterIds", "hidden",
            "capabilities", "builtinTools", "bc250_managed", "bc250_lane",
            "bc250_qualification", "bc250_ordinary_user_visible",
        ):
            if key in desired_meta and canonical(live_meta.get(key)) != canonical(
                desired_meta[key]
            ):
                problems.append(f"Package {label} differs: {model_id}.meta.{key}")
        required_grants = desired_access_grants(model)
        desired_meta = model.get("meta") if isinstance(model.get("meta"), dict) else {}
        access_policy_relevant = bool(required_grants) or (
            is_auto_visible_model(model)
            and desired_meta.get("bc250_ordinary_user_visible") is False
        )
        if access_policy_relevant:
            try:
                live_grants = access_grant_keys(
                    live.get("access_grants", []), f"access grants for {model_id}"
                )
            except ApiError as exc:
                print(f"Open WebUI model inspection unavailable for this API shape: {exc}")
                return 1
            missing_grants = [
                grant
                for grant in required_grants
                if access_grant_key(grant, f"required grant for {model_id}") not in live_grants
            ]
            for grant in missing_grants:
                problems.append(
                    f"Package {label} access differs: {model_id} "
                    "(missing "
                    f"{grant['principal_type']}:{grant['principal_id']}:{grant['permission']})"
                )
            if (
                is_auto_visible_model(model)
                and desired_meta.get("bc250_ordinary_user_visible") is False
                and ("user", "*", "read") in live_grants
            ):
                problems.append(
                    f"Package {label} access differs: {model_id} "
                    "(package public read grant must be absent)"
                )

    desired_ids = {str(model.get("id")) for model in desired_models}
    for model_id, live in base_models.items():
        if model_id in desired_ids or not is_auto_visible_model(live):
            continue
        live_meta = live.get("meta") if isinstance(live.get("meta"), dict) else {}
        if str(live_meta.get("bc250_lane") or "") in discovered_inventory:
            problems.append(f"Stale package-managed testing model: {model_id}")

    if problems:
        print("Desired-state drift: detected")
        for problem in problems:
            print(f"  - {problem}")
        return 2
    print("Desired-state drift: none in package-owned settings")
    print(
        f"Open WebUI models: {active_presets} presets current, "
        f"{active_base_overrides} base overrides current"
    )
    if verbose:
        print_verbose_summary(desired_models, load_functions())
        compare_state = multiple_models_state(application)
        rendered_compare = (
            "enabled" if compare_state is True else "disabled" if compare_state is False else "not reported"
        )
        print()
        print("Administrator-owned feature state")
        print(f"  multi-model chat: {rendered_compare} (reported only; not package-converged)")
    return 0



def read_token_file(path: str) -> str:
    token_path = Path(path).expanduser()
    try:
        st = token_path.stat()
    except OSError as exc:
        raise ApiError(f"cannot read API key file {token_path}: {exc}") from exc
    if not stat.S_ISREG(st.st_mode):
        raise ApiError(f"API key file is not a regular file: {token_path}")
    if st.st_mode & 0o077:
        raise ApiError(f"API key file must not be group/world accessible: {token_path}")
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ApiError(f"cannot read API key file {token_path}: {exc}") from exc
    if not token:
        raise ApiError(f"API key file is empty: {token_path}")
    return token


def write_token_file(path: str, token: str) -> None:
    token_path = Path(path)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(token_path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as handle:
            handle.write(token + "\n")
            handle.flush()
    finally:
        os.close(fd)


def suggested_token_file() -> str:
    configured = os.environ.get("BC250_OWUI_TOKEN_FILE", "").strip()
    if configured:
        return configured
    default = Path("/root/owui-test.key")
    return str(default) if default.is_file() else ""

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("init", "apply", "status"))
    p.add_argument("--url", default=os.environ.get("OWUI_URL", DEFAULT_URL))
    p.add_argument(
        "--token-file", "--owui-token-file", dest="token_file",
        help="read an administrator API key from a protected file",
    )
    p.add_argument(
        "--token-output",
        help="write the authenticated token to a protected temporary file for the caller",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="show the verified active role, task, RAG and package-function summary",
    )
    return p


def main() -> int:
    args = parser().parse_args()
    env_token = os.environ.get("OWUI_API_KEY", "").strip() or None
    token = read_token_file(args.token_file) if args.token_file else env_token
    client = Client(args.url, token)
    if args.command == "status":
        return status(client, bool(token), verbose=args.verbose)
    if args.command == "init":
        if args.token_file:
            print(f"Using Open WebUI administrator API key file: {args.token_file}")
        elif token:
            print("Using OWUI_API_KEY from the environment; interactive sign-in is not required.")
        else:
            if not sys.stdin.isatty():
                raise ApiError("init requires a TTY, --token-file, or OWUI_API_KEY")
            candidate = suggested_token_file()
            print("Open WebUI administrator access")
            if candidate:
                print()
                print("A protected administrator API key file was found:")
                print(f"  {candidate}")
                print()
                print("  1) Use this API key file")
                print("  2) Sign in with an existing administrator")
                print("  3) Create the first administrator")
                print("  4) Use a different API key file")
                choice = input("Choose [1/2/3/4] [1]: ").strip() or "1"
                if choice not in {"1", "2", "3", "4"}:
                    raise ApiError("choose 1, 2, 3 or 4")
                if choice == "1":
                    selected = candidate
                    token = read_token_file(selected)
                    print(f"Using Open WebUI administrator API key file: {selected}")
                elif choice == "4":
                    selected = input("API key file: ").strip()
                    if not selected:
                        raise ApiError("an API key file path is required")
                    token = read_token_file(selected)
                    print(f"Using Open WebUI administrator API key file: {selected}")
                else:
                    token = authenticate(Client(args.url), "signin" if choice == "2" else "create")
            else:
                print("  1) Sign in with an existing administrator")
                print("  2) Create the first administrator")
                print("  3) Use an administrator API key file")
                choice = input("Choose [1/2/3]: ").strip()
                if choice not in {"1", "2", "3"}:
                    raise ApiError("choose 1, 2 or 3")
                if choice == "3":
                    selected = input("API key file: ").strip()
                    if not selected:
                        raise ApiError("an API key file path is required")
                    token = read_token_file(selected)
                    print(f"Using Open WebUI administrator API key file: {selected}")
                else:
                    token = authenticate(Client(args.url), "signin" if choice == "1" else "create")
            client = Client(args.url, token)
    elif not token:
        raise ApiError(
            f"{args.command} requires --token-file or OWUI_API_KEY; the key is never stored by default"
        )

    if args.token_output and token:
        write_token_file(args.token_output, token)

    apply(client)
    print("Open WebUI package-owned baseline applied through supported APIs.")
    return status(client, True, verbose=args.verbose)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ApiError, KeyboardInterrupt) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
