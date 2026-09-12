#!/usr/bin/env python3
"""Safe Open WebUI Ollama-provider transaction helpers for translation screens."""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

RELEVANT_KEYS = ("ENABLE_OLLAMA_API", "OLLAMA_BASE_URLS", "OLLAMA_API_CONFIGS")
SENSITIVE_KEY_RE = re.compile(
    r"(^key$|authorization|headers?|cookie|token|secret|password|api[_-]?key|credential)",
    re.IGNORECASE,
)


def load_json(path: Path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def dump_json(value, path: Path) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def relevant_config(value: dict) -> dict:
    return {key: value.get(key) for key in RELEVANT_KEYS}


def main_provider_index(config: dict, port: int = 11434) -> int:
    missing = [key for key in RELEVANT_KEYS if key not in config]
    if missing:
        raise ValueError(f"Open WebUI Ollama config missing keys: {missing}")
    urls = config["OLLAMA_BASE_URLS"]
    configs = config["OLLAMA_API_CONFIGS"]
    if config["ENABLE_OLLAMA_API"] is not True:
        raise ValueError("Open WebUI Ollama API is disabled")
    if not isinstance(urls, list) or not isinstance(configs, dict):
        raise TypeError("unexpected Open WebUI Ollama config shape")
    matches: list[int] = []
    for idx, url in enumerate(urls):
        if not isinstance(url, str):
            continue
        try:
            if urlsplit(url).port == port:
                matches.append(idx)
        except ValueError:
            continue
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one main Ollama provider on port {port}, found {matches}"
        )
    idx = matches[0]
    provider = configs.get(str(idx))
    if not isinstance(provider, dict):
        raise TypeError(f"missing Ollama API config for main provider index {idx}")
    if provider.get("enable", True) is not True:
        raise ValueError("main Ollama provider is disabled")
    return idx


def prepare_candidate(config: dict, raw_candidate: str) -> tuple[dict, dict]:
    idx = main_provider_index(config)
    result = copy.deepcopy(config)
    provider = result["OLLAMA_API_CONFIGS"][str(idx)]
    model_ids = provider.get("model_ids")
    changed = False
    if model_ids:
        if not isinstance(model_ids, list) or not all(isinstance(item, str) for item in model_ids):
            raise ValueError("main provider model_ids is not a list of strings")
        if raw_candidate not in model_ids:
            model_ids.append(raw_candidate)
            changed = True
    elif model_ids not in (None, []):
        raise ValueError("main provider model_ids must be missing, empty, or a list")

    prefix_id = provider.get("prefix_id")
    if prefix_id is not None and not isinstance(prefix_id, str):
        raise ValueError("main provider prefix_id must be a string when set")
    effective = f"{prefix_id}.{raw_candidate}" if prefix_id else raw_candidate
    meta = {
        "provider_index": idx,
        "provider_url": _redact_url(result["OLLAMA_BASE_URLS"][idx]),
        "prefix_id": prefix_id,
        "raw_candidate_id": raw_candidate,
        "effective_candidate_id": effective,
        "allowlist_changed": changed,
    }
    return result, meta


def configs_match(expected: dict, actual: dict) -> bool:
    return relevant_config(expected) == relevant_config(actual)


def _redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if not parts.scheme or "@" not in parts.netloc:
        return value
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, f"<redacted>@{host}", parts.path, parts.query, parts.fragment))


def redact(value, key: str | None = None):
    if key is not None and SENSITIVE_KEY_RE.search(key):
        if value in (None, "", [], {}):
            return value
        return "<redacted>"
    if isinstance(value, dict):
        return {k: redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _redact_url(value)
    return value


def _scalar_secrets(value) -> set[str]:
    secrets: set[str] = set()
    if isinstance(value, str) and value:
        secrets.add(value)
    elif isinstance(value, (int, float)):
        secrets.add(str(value))
    elif isinstance(value, dict):
        for child in value.values():
            secrets.update(_scalar_secrets(child))
    elif isinstance(value, list):
        for child in value:
            secrets.update(_scalar_secrets(child))
    return secrets


def collect_secrets(value, key: str | None = None) -> set[str]:
    secrets: set[str] = set()
    if key is not None and SENSITIVE_KEY_RE.search(key):
        return _scalar_secrets(value)
    if isinstance(value, dict):
        for child_key, child in value.items():
            secrets.update(collect_secrets(child, str(child_key)))
    elif isinstance(value, list):
        for child in value:
            secrets.update(collect_secrets(child))
    elif isinstance(value, str):
        try:
            parts = urlsplit(value)
        except ValueError:
            parts = None
        if parts and parts.scheme and parts.username:
            secrets.add(parts.username)
            if parts.password:
                secrets.add(parts.password)
    return secrets



def sanitize_response(path: Path, secrets_config: dict | None = None):
    data = path.read_bytes()
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        text = data.decode("utf-8", errors="replace")
        for secret in sorted(collect_secrets(secrets_config or {}), key=len, reverse=True):
            if secret:
                text = text.replace(secret, "<redacted>")
        return text
    return redact(value)


def scan_tree_for_secrets(root: Path, secrets: set[str]) -> list[str]:
    needles = [secret.encode() for secret in secrets if secret]
    if not needles:
        return []
    hits: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if any(needle in data for needle in needles):
            hits.append(str(path))
    return hits


def command_prepare(args: argparse.Namespace) -> int:
    original = load_json(args.input)
    candidate, meta = prepare_candidate(original, args.candidate)
    dump_json(candidate, args.output)
    json.dump(meta, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def command_compare(args: argparse.Namespace) -> int:
    expected = load_json(args.expected)
    actual = load_json(args.actual)
    if not configs_match(expected, actual):
        print("relevant Open WebUI Ollama config differs", file=sys.stderr)
        return 1
    return 0


def command_redact(args: argparse.Namespace) -> int:
    json.dump(redact(load_json(args.input)), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0



def command_sanitize(args: argparse.Namespace) -> int:
    config = load_json(args.secrets_from) if args.secrets_from else None
    value = sanitize_response(args.input, config)
    if isinstance(value, str):
        sys.stdout.write(value)
        if value and not value.endswith("\n"):
            sys.stdout.write("\n")
    else:
        json.dump(value, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


def command_scan(args: argparse.Namespace) -> int:
    config = load_json(args.config)
    secrets = collect_secrets(config)
    if args.token_file and args.token_file.is_file():
        token = args.token_file.read_text(encoding="utf-8").strip()
        if token:
            secrets.add(token)
    hits = scan_tree_for_secrets(args.root, secrets)
    if hits:
        print("credential material found in evidence:", file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--input", type=Path, required=True)
    prepare.add_argument("--candidate", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.set_defaults(func=command_prepare)

    compare = commands.add_parser("compare")
    compare.add_argument("--expected", type=Path, required=True)
    compare.add_argument("--actual", type=Path, required=True)
    compare.set_defaults(func=command_compare)

    redact_cmd = commands.add_parser("redact")
    redact_cmd.add_argument("--input", type=Path, required=True)
    redact_cmd.set_defaults(func=command_redact)


    sanitize = commands.add_parser("sanitize")
    sanitize.add_argument("--input", type=Path, required=True)
    sanitize.add_argument("--secrets-from", type=Path)
    sanitize.set_defaults(func=command_sanitize)

    scan = commands.add_parser("scan")
    scan.add_argument("--config", type=Path, required=True)
    scan.add_argument("--root", type=Path, required=True)
    scan.add_argument("--token-file", type=Path)
    scan.set_defaults(func=command_scan)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
