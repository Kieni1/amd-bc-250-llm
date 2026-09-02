#!/usr/bin/env python3
"""Configure the package-owned Open WebUI 0.11.3 baseline through supported APIs."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_URL = "http://127.0.0.1:3000"
DEFAULT_MODELS = Path("/usr/share/bc250-llm-server/openwebui/models.json")
SOURCE_MODELS = Path(__file__).resolve().parents[2] / "config/openwebui/models.json"
TASK_MODEL = "task-gemma3-1b-unsloth-ud-q4-k-xl:latest"
EMBED_MODEL = "embed-jina-v5-small-retrieval-q4-k-m"
MAIN_URL = "http://host.containers.internal:11434"
TASK_URL = "http://host.containers.internal:11435"
EMBED_URL = "http://host.containers.internal:11437"
RAG_TEMPLATE = (
    "Answer the user from the supplied context. If the requested fact is not supported by the context, "
    "state that the available documents do not provide sufficient evidence. Do not fill missing document facts "
    "from general knowledge unless the user explicitly asks for external or general knowledge. Respond in the "
    "user-requested language. Preserve names, numbers, dates, terminology, and important qualifications. Use "
    "inline [id] citations only for source tags that provide an id. <context>{{CONTEXT}}</context>"
)
PRODUCTION_MODELS = [
    "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl:latest",
    "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl:latest",
    "prod-gpt-oss20b-ggml-org-mxfp4:latest",
    "prod-lfm25-8b-a1b-liquidai-q6-k:latest",
    "prod-qwen35-9b-unsloth-q6-k:latest",
]
TASK_MODELS = [
    TASK_MODEL,
    "task-lfm25-2.6b-liquidai-q6-k:latest",
]


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
    return data


def desired_ollama() -> dict[str, Any]:
    return {
        "ENABLE_OLLAMA_API": True,
        "OLLAMA_BASE_URLS": [MAIN_URL, TASK_URL],
        "OLLAMA_API_CONFIGS": {
            "0": {
                "enable": True,
                "model_ids": PRODUCTION_MODELS,
                "tags": ["production"],
                "connection_type": "local",
            },
            "1": {
                "enable": True,
                "model_ids": TASK_MODELS,
                "tags": ["task"],
                "connection_type": "local",
            },
        },
    }


def desired_embedding() -> dict[str, Any]:
    return {
        "RAG_EMBEDDING_ENGINE": "ollama",
        "RAG_EMBEDDING_MODEL": EMBED_MODEL,
        "RAG_EMBEDDING_BATCH_SIZE": 1,
        "ENABLE_ASYNC_EMBEDDING": False,
        "RAG_EMBEDDING_CONCURRENT_REQUESTS": 1,
        "ollama_config": {"url": EMBED_URL, "key": ""},
    }


def desired_rag() -> dict[str, Any]:
    return {
        "RAG_TEMPLATE": RAG_TEMPLATE,
        "TOP_K": 8,
        "ENABLE_RAG_HYBRID_SEARCH": False,
        "RELEVANCE_THRESHOLD": 0,
        "CONTENT_EXTRACTION_ENGINE": "tika",
        "TIKA_SERVER_URL": "http://tika:9998",
        "TIKA_SERVER_VERSION": "3",
        "TEXT_SPLITTER": "token",
        "ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER": True,
        "CHUNK_SIZE": 1500,
        "CHUNK_MIN_SIZE_TARGET": 0,
        "CHUNK_OVERLAP": 200,
    }


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


def apply(client: Client) -> None:
    client.post("/ollama/config/update", desired_ollama())

    task = client.get("/api/v1/tasks/config")
    if not isinstance(task, dict):
        raise ApiError("task config response was not an object")
    task.update(
        {
            "TASK_MODEL": TASK_MODEL,
            "TASK_MODEL_EXTERNAL": None,
            "TASK_MODEL_PARAMS": {},
            "ENABLE_TITLE_GENERATION": True,
            "ENABLE_TAGS_GENERATION": True,
            "ENABLE_FOLLOW_UP_GENERATION": False,
            "ENABLE_AUTOCOMPLETE_GENERATION": False,
            "ENABLE_SEARCH_QUERY_GENERATION": False,
            "ENABLE_RETRIEVAL_QUERY_GENERATION": False,
        }
    )
    client.post("/api/v1/tasks/config/update", task)
    client.post("/api/v1/retrieval/embedding/update", desired_embedding())
    client.post("/api/v1/retrieval/config/update", desired_rag())
    client.post("/api/v1/models/import", load_models())


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApiError(f"{label} response was not an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ApiError(f"{label} response was not a list")
    return value


def status(client: Client, authenticated: bool) -> int:
    try:
        client.probe("/")
    except ApiError as exc:
        print(f"Open WebUI: unavailable ({exc})")
        return 1
    print("Open WebUI: reachable")
    if not authenticated:
        print("Desired-state drift: skipped (set OWUI_API_KEY for authenticated comparison)")
        return 0

    problems: list[str] = []
    ollama = require_object(client.get("/ollama/config"), "Ollama config")
    desired = desired_ollama()
    for key in ("ENABLE_OLLAMA_API", "OLLAMA_BASE_URLS", "OLLAMA_API_CONFIGS"):
        if canonical(ollama.get(key)) != canonical(desired[key]):
            problems.append(f"Ollama config differs: {key}")

    task = require_object(client.get("/api/v1/tasks/config"), "task config")
    expected_task = {
        "TASK_MODEL": TASK_MODEL,
        "TASK_MODEL_EXTERNAL": None,
        "TASK_MODEL_PARAMS": {},
        "ENABLE_TITLE_GENERATION": True,
        "ENABLE_TAGS_GENERATION": True,
        "ENABLE_FOLLOW_UP_GENERATION": False,
        "ENABLE_AUTOCOMPLETE_GENERATION": False,
        "ENABLE_SEARCH_QUERY_GENERATION": False,
        "ENABLE_RETRIEVAL_QUERY_GENERATION": False,
    }
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
        if canonical(rag.get(key)) != canonical(value):
            problems.append(f"RAG config differs: {key}")

    exported = require_list(client.get("/api/v1/models/export"), "model export")
    existing_ids = {item.get("id") for item in exported if isinstance(item, dict)}
    for model in load_models()["models"]:
        if model["id"] not in existing_ids:
            problems.append(f"Package model preset missing: {model['id']}")

    if problems:
        print("Desired-state drift: detected")
        for problem in problems:
            print(f"  - {problem}")
        return 2
    print("Desired-state drift: none in package-owned settings")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("init", "apply", "status"))
    p.add_argument("--url", default=os.environ.get("OWUI_URL", DEFAULT_URL))
    return p


def main() -> int:
    args = parser().parse_args()
    token = os.environ.get("OWUI_API_KEY", "").strip() or None
    client = Client(args.url, token)
    if args.command == "status":
        return status(client, bool(token))
    if args.command == "init":
        if token:
            print("Using OWUI_API_KEY from the environment; interactive sign-in is not required.")
        else:
            if not sys.stdin.isatty():
                raise ApiError("init requires a TTY or OWUI_API_KEY")
            print("Open WebUI initialization")
            print("  1) Create first administrator")
            print("  2) Sign in existing administrator")
            choice = input("Choose [1/2]: ").strip()
            if choice not in {"1", "2"}:
                raise ApiError("choose 1 or 2")
            token = authenticate(Client(args.url), "create" if choice == "1" else "signin")
            client = Client(args.url, token)
    elif not token:
        raise ApiError("apply requires OWUI_API_KEY in the environment; the key is never stored")

    apply(client)
    print("Open WebUI package-owned baseline applied through supported APIs.")
    return status(client, True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ApiError, KeyboardInterrupt) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
