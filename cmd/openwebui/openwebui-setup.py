#!/usr/bin/env python3
"""Configure the package-owned Open WebUI 0.11.3 baseline through supported APIs."""

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
    if not isinstance(data, dict) or any(not isinstance(data.get(k), dict) for k in ("ollama", "task", "embedding", "rag")):
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
    return data


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

    task = client.get("/api/v1/tasks/config")
    if not isinstance(task, dict):
        raise ApiError("task config response was not an object")
    task.update(desired_task())
    client.post("/api/v1/tasks/config/update", task)
    client.post("/api/v1/retrieval/embedding/update", desired_embedding())
    client.post("/api/v1/retrieval/config/update", desired_rag())
    apply_functions(client)
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


def print_verbose_summary(models: list[dict[str, Any]], functions: list[dict[str, Any]]) -> None:
    print()
    print("Package-owned Open WebUI roles")
    for model in models:
        if not bool(model.get("is_active")):
            continue
        model_id = str(model.get("id") or "unknown")
        base = str(model.get("base_model_id") or "unknown")
        params = model.get("params") if isinstance(model.get("params"), dict) else {}
        meta = model.get("meta") if isinstance(model.get("meta"), dict) else {}
        filters = meta.get("filterIds") if isinstance(meta.get("filterIds"), list) else []
        extras: list[str] = []
        if "max_tokens" in params:
            extras.append(f"max_tokens={params['max_tokens']}")
        if "think" in params:
            extras.append(f"think={params['think']}")
        elif "translation" in model_id:
            extras.append("think=omitted")
        if filters:
            extras.append("filters=" + ",".join(str(value) for value in filters))
        suffix = f"  ({'; '.join(extras)})" if extras else ""
        print(f"  {model_id:<36} -> {base}{suffix}")

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
        if canonical(rag.get(key)) != canonical(value):
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

    exported = require_list(client.get("/api/v1/models/export"), "model export")
    live_models = {item.get("id"): item for item in exported if isinstance(item, dict)}
    for model in load_models()["models"]:
        model_id = model["id"]
        live = live_models.get(model_id)
        if not isinstance(live, dict):
            problems.append(f"Package model preset missing: {model_id}")
            continue
        for key in ("base_model_id", "name", "params", "is_active"):
            if canonical(live.get(key)) != canonical(model.get(key)):
                problems.append(f"Package model preset differs: {model_id}.{key}")
        desired_meta = model.get("meta") if isinstance(model.get("meta"), dict) else {}
        live_meta = live.get("meta") if isinstance(live.get("meta"), dict) else {}
        for key in ("description", "tags", "filterIds", "defaultFilterIds"):
            if key in desired_meta and canonical(live_meta.get(key)) != canonical(desired_meta[key]):
                problems.append(f"Package model preset differs: {model_id}.meta.{key}")

    if problems:
        print("Desired-state drift: detected")
        for problem in problems:
            print(f"  - {problem}")
        return 2
    print("Desired-state drift: none in package-owned settings")
    if verbose:
        print_verbose_summary(load_models()["models"], load_functions())
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
