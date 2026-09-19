#!/usr/bin/env python3
"""Manage BC-250 model catalog, verified local sources and runtime registrations."""

from __future__ import annotations

import argparse
import errno
import getpass
import grp
import hashlib
import json
import os
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import tomllib

PROJECT = "bc250-llm-server"
INSTALLED_SHARE = Path(f"/usr/share/{PROJECT}/model-management")
INSTALLED_CONFIG = Path(f"/etc/{PROJECT}")
PACKAGED_MODEL_DIR = INSTALLED_SHARE / "modelfiles"
OPERATOR_MODEL_DIR = INSTALLED_CONFIG / "models.d"
RETIRED_CATALOG = INSTALLED_SHARE / "retired-models.json"

OLLAMA_CATEGORIES = ("production", "experiments", "task", "agentic", "embedding")
NORMAL_CATEGORIES = ("production", "experiments", "task", "embedding")
CATEGORIES = (*OLLAMA_CATEGORIES, "mtp", "all")
RECOMMENDED_MODELS = {
    "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl",
    "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl",
    "prod-translate-gemma4-sub-e4b-17s-q4-k-xl",
    "prod-qwen35-9b-unsloth-q6-k",
    "prod-gpt-oss20b-ggml-org-mxfp4",
    "task-lfm25-1.2b-instruct-liquidai-q6-k",
    "agentic-ornith15-9b-ornith-q5-k-m",
    "embed-jina-v5-small-retrieval-q4-k-m",
}
LOW_FREE_BYTES = 20 * 1024**3
REGISTRATION_PROBE_TIMEOUT = 5
SYSTEMD_PROBE_TIMEOUT = 2
AGENT_OLLAMA_SERVICE = "ollama-agent.service"
CATEGORY_PREFIXES = {
    "production": "prod-",
    "experiments": "exp-",
    "task": "task-",
    "agentic": "agentic-",
    "embedding": "embed-",
}
CATEGORY_DEFAULTS = {
    "production": {
        "destination": "/var/lib/bc250-llm-server/gguf/production",
        "download_namespace": "production",
        "modelfile_destination": "/var/lib/bc250-llm-server/modelfiles/production",
        "ollama_host": "127.0.0.1:11434",
        "min_free_bytes": 0,
    },
    "experiments": {
        "destination": "/var/lib/bc250-llm-server/gguf/experiments",
        "download_namespace": "experiments",
        "modelfile_destination": "/var/lib/bc250-llm-server/modelfiles/experiments",
        "ollama_host": "127.0.0.1:11434",
        "min_free_bytes": 0,
    },
    "task": {
        "destination": "/var/lib/bc250-llm-server/gguf/task",
        "download_namespace": "task",
        "modelfile_destination": "/var/lib/bc250-llm-server/modelfiles/task",
        "ollama_host": "127.0.0.1:11435",
        "min_free_bytes": 0,
    },
    "agentic": {
        "destination": "/var/lib/bc250-llm-server/gguf/agent",
        "download_namespace": "agentic",
        "modelfile_destination": "/var/lib/bc250-llm-server/modelfiles/agent",
        "ollama_host": "127.0.0.1:11436",
        "min_free_bytes": 8589934592,
    },
    "embedding": {
        "destination": "/var/lib/bc250-llm-server/gguf/embedding",
        "download_namespace": "embedding",
        "modelfile_destination": "/var/lib/bc250-llm-server/modelfiles/embedding",
        "ollama_host": "127.0.0.1:11437",
        "min_free_bytes": 0,
    },
}


class ModelError(RuntimeError):
    """A concise error suitable for command-line output."""


@dataclass(frozen=True)
class ModelInspection:
    """Read-only view of one catalog entry across source and runtime state."""

    model: dict
    source_path: Path | None
    state_path: Path | None
    source_status: str
    source_detail: str
    source_checksum: str
    runtime_modelfile: Path | None
    modelfile_status: str
    registration_status: str
    overall_status: str
    remote_status: str = "not checked"
    remote_detail: str = ""


def set_appliance_mode(mode: str) -> None:
    """Switch the package-defined Ollama topology before registration work."""
    if mode not in {"normal", "agent"}:
        raise ModelError(f"unsupported appliance mode: {mode}")
    command = os.environ.get("BC250_AGENT_MODE") or shutil.which("bc250-agent-mode")
    if not command:
        raise ModelError("bc250-agent-mode is required for package-managed model registration")
    action = "leave" if mode == "normal" else "enter"
    result = subprocess.run(
        [command, action],
        check=False,
        stdout=(subprocess.DEVNULL if os.environ.get("BC250_MODELCTL_SUPPRESS_MODE_OUTPUT") == "1" else None),
    )
    if result.returncode:
        raise ModelError(f"could not enter {mode} appliance mode (rc={result.returncode})")


def operate_models(defaults: dict, models: list[dict], args: argparse.Namespace) -> int:
    if args.command in {"apply", "refresh"}:
        return apply_models(defaults, models, args)
    if args.command in {"unregister", "remove"}:
        return remove_models(defaults, models, args)
    raise ModelError(f"unsupported model operation: {args.command}")


def canonical_category(value: str) -> str:
    if value not in CATEGORIES:
        raise ModelError(f"unsupported model category: {value}")
    return value


def modelfile_category(value: str) -> str:
    # Keep reading existing operator/package metadata while exposing only the
    # canonical CLI vocabulary. Historical Modelfiles used singular experimental.
    normalized = "experiments" if value == "experimental" else value
    if normalized not in OLLAMA_CATEGORIES:
        raise ModelError(f"unsupported Modelfile category: {value}")
    return normalized


def require_string(
    table: dict, key: str, context: str, *, filename: bool = False
) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise ModelError(f"{context}: {key} must be a non-empty string")
    if filename and (Path(value).name != value or value in {".", ".."}):
        raise ModelError(f"{context}: {key} must be a filename")
    return value


def local_source_root() -> Path | None:
    script_dir = Path(__file__).resolve().parent
    if (script_dir / "modelfiles").is_dir() and (
        script_dir / "mtp/models.toml"
    ).is_file():
        return script_dir
    return None


def model_directories(explicit: list[Path] | None = None) -> list[Path]:
    if explicit:
        return explicit
    override = os.environ.get("MODELFILE_SOURCE_DIR", "")
    if override:
        return [Path(value) for value in override.split(os.pathsep) if value]
    source_root = local_source_root()
    if source_root:
        return [source_root / "modelfiles"]
    return [PACKAGED_MODEL_DIR, OPERATOR_MODEL_DIR]


def default_mtp_catalog() -> Path:
    source_root = local_source_root()
    if source_root:
        return source_root / "mtp/models.toml"
    configured = INSTALLED_CONFIG / "mtp-models.toml"
    return configured if configured.is_file() else INSTALLED_SHARE / "mtp-models.toml"


def model_path(defaults: dict, model: dict, destination: str | None = None) -> Path:
    if destination:
        return Path(destination) / model["gguf"]
    if model["provider"] == "ollama":
        return Path(model["from"])
    root = Path(defaults["destination"])
    if defaults.get("layout", "flat") == "by-id":
        root /= model["id"]
    return root / model["gguf"]


def modelfile_metadata(path: Path) -> dict[str, str]:
    values = {
        "category": "",
        "name": "",
        "repository": "",
        "revision": "",
        "gguf": "",
        "sha256": "",
        "from": "",
    }
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ModelError(f"cannot read Modelfile {path}: {error}") from error
    for line in lines:
        if line.startswith("# BC250 category: "):
            values["category"] = line.removeprefix("# BC250 category: ").strip()
        elif line.startswith("# Ollama model: "):
            values["name"] = line.removeprefix("# Ollama model: ").strip()
        elif line.startswith("# Source: ") and " @ " in line:
            source = line.removeprefix("# Source: ").strip()
            values["repository"], values["revision"] = source.rsplit(" @ ", 1)
        elif line.startswith("# GGUF: "):
            values["gguf"] = line.removeprefix("# GGUF: ").strip()
        elif line.startswith("# SHA256: "):
            values["sha256"] = line.removeprefix("# SHA256: ").strip()
        elif line.startswith("FROM ") and not values["from"]:
            values["from"] = line.split(maxsplit=1)[1].strip()
    return values


def load_modelfile(path: Path) -> dict:
    if path.suffix != ".Modelfile":
        raise ModelError(f"{path}: expected a .Modelfile template")
    name = path.name.removesuffix(".Modelfile")
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name) is None:
        raise ModelError(f"{path}: filename must be a lowercase Ollama model name")

    metadata = modelfile_metadata(path)
    for key in ("category", "name", "repository", "revision", "gguf", "from"):
        if not metadata[key]:
            raise ModelError(f"{path}: missing {key} metadata")
    text = path.read_text(encoding="utf-8")
    required_markers = (
        "# BC250 category: ",
        "# Ollama model: ",
        "# Source: ",
        "# GGUF: ",
        "FROM ",
    )
    for marker in required_markers:
        if sum(line.startswith(marker) for line in text.splitlines()) != 1:
            raise ModelError(f"{path}: expected exactly one {marker.strip()!r} line")
    if sum(line.startswith("# SHA256:") for line in text.splitlines()) > 1:
        raise ModelError(f"{path}: expected at most one '# SHA256:' line")
    category = modelfile_category(metadata["category"])
    if category not in OLLAMA_CATEGORIES:
        raise ModelError(f"{path}: MTP entries cannot use Modelfiles")
    if metadata["name"] != name:
        raise ModelError(f"{path}: Ollama name must match the filename")
    if not name.startswith(CATEGORY_PREFIXES[category]):
        raise ModelError(
            f"{path}: {category} model name must start with {CATEGORY_PREFIXES[category]!r}"
        )
    if re.fullmatch(r"[^/\s]+/[^/\s]+", metadata["repository"]) is None:
        raise ModelError(f"{path}: source must be a Hugging Face owner/repository")
    if re.fullmatch(r"\S+", metadata["revision"]) is None:
        raise ModelError(f"{path}: revision must be a commit, tag, branch or latest")
    if Path(metadata["gguf"]).name != metadata["gguf"]:
        raise ModelError(f"{path}: GGUF metadata must be a filename")

    output = Path(metadata["from"])
    remote_from = re.fullmatch(
        r"hf\.co/(?P<repository>[^/\s]+/[^/:\s]+):[^\s]+", metadata["from"]
    )
    if remote_from:
        if category != "experiments":
            raise ModelError(
                f"{path}: remote Hugging Face FROM is limited to experiments"
            )
        if remote_from.group("repository") != metadata["repository"]:
            raise ModelError(
                f"{path}: remote FROM repository must match Source metadata"
            )
        provider = "ollama-hf"
    else:
        if not output.is_absolute() or output.name != metadata["gguf"]:
            raise ModelError(
                f"{path}: FROM must be an absolute path ending in the GGUF filename"
            )
        expected_root = Path(CATEGORY_DEFAULTS[category]["destination"])
        if not output.is_relative_to(expected_root):
            raise ModelError(f"{path}: FROM must be below {expected_root}")
        provider = "ollama"

    checksum = metadata["sha256"]
    if checksum and re.fullmatch(r"[0-9a-f]{64}", checksum) is None:
        raise ModelError(f"{path}: SHA256 must be 64 lowercase hexadecimal characters")
    required_parameters = ["PARAMETER num_gpu 99"]
    if category != "embedding":
        required_parameters.append("PARAMETER num_keep 256")
    for parameter in required_parameters:
        if len(re.findall(rf"^{re.escape(parameter)}$", text, re.MULTILINE)) != 1:
            raise ModelError(f"{path}: expected exactly one {parameter!r}")

    return {
        "enabled": True,
        "provider": provider,
        "category": category,
        "id": name,
        "name": name,
        "repository": metadata["repository"],
        "revision": metadata["revision"],
        "gguf": metadata["gguf"],
        "sha256": checksum,
        "from": metadata["from"],
        "modelfile": path.name,
        "template": path,
        "origin": "operator" if OPERATOR_MODEL_DIR in path.parents else "packaged",
    }


def discover_models(directories: list[Path]) -> list[dict]:
    # Later directories override a same-named packaged template. This gives
    # /etc/bc250-llm-server/models.d the usual operator-over-package precedence.
    discovered: dict[str, dict] = {}
    found_directory = False
    for directory in directories:
        if not directory.is_dir():
            continue
        found_directory = True
        for path in sorted(directory.glob("*.Modelfile")):
            model = load_modelfile(path)
            previous = discovered.get(model["name"])
            if previous is not None:
                model["overrides_origin"] = previous.get("origin", "catalog")
            discovered[model["name"]] = model
    if not found_directory:
        joined = ", ".join(str(path) for path in directories)
        raise ModelError(f"no Modelfile directory found: {joined}")
    models = sorted(
        discovered.values(),
        key=lambda model: (OLLAMA_CATEGORIES.index(model["category"]), model["name"]),
    )
    for index, model in enumerate(models):
        model["index"] = index
    return models


def load_mtp_catalog(path: Path) -> tuple[dict, list[dict]]:
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ModelError(f"cannot load MTP catalog {path}: {error}") from error
    if document.get("schema") != 1:
        raise ModelError(f"{path}: unsupported or missing schema")
    defaults = document.get("defaults")
    models = document.get("models")
    if not isinstance(defaults, dict) or not isinstance(models, list):
        raise ModelError(f"{path}: defaults and models are required")
    if defaults.get("category") != "mtp":
        raise ModelError(f"{path}: category must be 'mtp'")
    require_string(defaults, "destination", f"{path}: defaults")
    require_string(defaults, "download_namespace", f"{path}: defaults")
    if defaults.get("layout", "flat") not in {"flat", "by-id"}:
        raise ModelError(f"{path}: layout must be flat or by-id")

    seen: set[str] = set()
    for index, model in enumerate(models):
        context = f"{path}: models[{index}]"
        if not isinstance(model, dict):
            raise ModelError(f"{context} must be a table")
        if not isinstance(model.get("enabled"), bool):
            raise ModelError(f"{context}: enabled must be true or false")
        if model.get("provider") != "download-only":
            raise ModelError(f"{context}: MTP provider must be download-only")
        model_id = require_string(model, "id", context)
        if (
            model_id in seen
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", model_id) is None
        ):
            raise ModelError(f"{context}: duplicate or invalid id")
        seen.add(model_id)
        require_string(model, "repository", context)
        require_string(model, "revision", context)
        require_string(model, "gguf", context, filename=True)
        for key in ("context", "draft"):
            if type(model.get(key)) is not int or model[key] <= 0:
                raise ModelError(f"{context}: {key} must be a positive integer")
        checksum = model.get("sha256", "")
        if not isinstance(checksum, str) or (
            checksum and re.fullmatch(r"[0-9a-f]{64}", checksum) is None
        ):
            raise ModelError(f"{context}: invalid SHA256")
    return defaults, models


def load_models(
    category: str,
    *,
    directories: list[Path] | None = None,
    source: Path | None = None,
) -> tuple[dict, list[dict]]:
    canonical = canonical_category(category)
    if canonical == "mtp":
        defaults, models = load_mtp_catalog(source or default_mtp_catalog())
        # MTP is a separate TOML catalog, but displayed indexes are global across
        # every bc250-model view. Keep the same MTP index whether the operator
        # lists only MTP entries or the combined catalog.
        next_index = len(discover_models(model_directories(directories)))
        normalized: list[dict] = []
        for model in models:
            value = dict(model)
            value["category"] = "mtp"
            value["index"] = next_index
            next_index += 1
            normalized.append(value)
        return defaults, normalized
    if source is not None:
        raise ModelError("--source is only supported for the MTP catalog")
    defaults = dict(CATEGORY_DEFAULTS[canonical])
    defaults["category"] = canonical
    discovered = discover_models(model_directories(directories))
    models = [model for model in discovered if model["category"] == canonical]
    return defaults, models


def load_all_catalogs(
    *,
    directories: list[Path] | None = None,
    source: Path | None = None,
) -> list[tuple[dict, list[dict]]]:
    """Return every catalog with globally unique display/selection indexes."""
    discovered = discover_models(model_directories(directories))
    catalogs: list[tuple[dict, list[dict]]] = []
    next_index = len(discovered)
    for category in OLLAMA_CATEGORIES:
        defaults = dict(CATEGORY_DEFAULTS[category])
        defaults["category"] = category
        models = [model for model in discovered if model["category"] == category]
        catalogs.append((defaults, models))
    mtp_defaults, mtp_models = load_mtp_catalog(source or default_mtp_catalog())
    normalized_mtp: list[dict] = []
    for model in mtp_models:
        value = dict(model)
        value["category"] = "mtp"
        value["index"] = next_index
        next_index += 1
        normalized_mtp.append(value)
    catalogs.append((mtp_defaults, normalized_mtp))
    return catalogs


def select_models(models: list[dict], selection: str) -> list[dict]:
    if not models:
        return []
    value = selection.strip()
    lookup = {
        key: index
        for index, model in enumerate(models)
        for key in (model["id"], str(model.get("index", index)))
    }
    selected: list[int] = []
    for item in value.split(","):
        item = item.strip()
        special = item.lower()
        if special == "all":
            choices = [model["id"] for model in models]
        elif special == "production":
            choices = [model["id"] for model in models if model.get("category") == "production"]
        elif special == "recommended":
            choices = [model["id"] for model in models if model["id"] in RECOMMENDED_MODELS]
        else:
            choices = [item]
            if match := re.fullmatch(r"([0-9]+)-([0-9]+)", item):
                first, last = map(int, match.groups())
                if first > last:
                    first, last = last, first
                choices = [str(number) for number in range(first, last + 1)]
        for choice in choices:
            if choice not in lookup:
                raise ModelError(f"unknown model selection {choice!r}")
            selected.append(lookup[choice])
    return [models[index] for index in dict.fromkeys(selected)]


def systemd_unit_active(unit: str) -> bool | None:
    """Return local systemd activity when cheaply knowable, otherwise None."""
    if not (systemctl := shutil.which("systemctl")):
        return None
    try:
        result = subprocess.run(
            [systemctl, "is-active", "--quiet", unit],
            capture_output=True,
            text=True,
            check=False,
            timeout=SYSTEMD_PROBE_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.returncode == 0


def registered_models(host: str) -> set[str] | None:
    if not (ollama := shutil.which("ollama")):
        return None
    if host == CATEGORY_DEFAULTS["agentic"]["ollama_host"]:
        active = systemd_unit_active(AGENT_OLLAMA_SERVICE)
        if active is False:
            return None
    try:
        result = subprocess.run(
            [ollama, "list"],
            env={**os.environ, "OLLAMA_HOST": host},
            capture_output=True,
            text=True,
            check=False,
            timeout=REGISTRATION_PROBE_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (
        None
        if result.returncode
        else {
            line.split()[0].removesuffix(":latest")
            for line in result.stdout.splitlines()[1:]
            if line.strip()
        }
    )


def print_models(
    defaults: dict, models: list[dict], registered=None, destination=None
) -> None:
    for offset, model in enumerate(models):
        provider = model["provider"]
        if provider == "ollama-hf":
            setup = None if registered is None else model["name"] in registered
            source = None
        else:
            try:
                source = model_path(defaults, model, destination).stat().st_size > 0
            except FileNotFoundError:
                source = False
            except OSError:
                source = None
            setup = None if registered is None else model.get("name") in registered
            if provider == "ollama":
                source = (
                    True
                    if setup is True
                    else None
                    if setup is None and source is False
                    else source
                )
        origin = model.get("origin", "enabled" if model["enabled"] else "disabled")
        download = {
            True: "downloaded",
            False: "not downloaded",
            None: "download unknown",
        }
        if provider == "ollama-hf":
            details = [provider, origin, "source Ollama-managed (main+projector)"]
        else:
            details = [provider, origin, download[source]]
        if provider.startswith("ollama"):
            if setup is None and defaults.get("category") == "agentic":
                details.append("registration deferred (agent lane inactive)")
            else:
                details.append(
                    {True: "set up", False: "not set up", None: "registration unavailable"}[setup]
                )
        index = model.get("index", offset)
        print(
            f"  {index:2d}) {model.get('name', model['id']):<56} [{', '.join(details)}]"
        )



def retired_catalog_path() -> Path:
    source_root = local_source_root()
    local = source_root / "retired-models.json" if source_root else None
    if local and local.is_file():
        return local
    return RETIRED_CATALOG


def load_retired_models() -> list[dict]:
    path = retired_catalog_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelError(f"could not read retired-model catalog {path}: {error}") from error
    models = value.get("models") if isinstance(value, dict) else None
    if not isinstance(models, list):
        raise ModelError(f"invalid retired-model catalog: {path}")
    result = []
    for item in models:
        if not isinstance(item, dict):
            raise ModelError(f"invalid retired-model entry in {path}")
        required = ("name", "category", "ollama_host", "source", "runtime_modelfile")
        if not all(isinstance(item.get(key), str) and item[key] for key in required):
            raise ModelError(f"incomplete retired-model entry in {path}")
        category = modelfile_category(item["category"])
        source = Path(item["source"]); runtime = Path(item["runtime_modelfile"])
        source_root = Path(CATEGORY_DEFAULTS[category]["destination"])
        runtime_root = Path(CATEGORY_DEFAULTS[category]["modelfile_destination"])
        if not source.is_absolute() or not source.is_relative_to(source_root):
            raise ModelError(f"retired model source is outside manager-owned storage: {source}")
        if not runtime.is_absolute() or not runtime.is_relative_to(runtime_root):
            raise ModelError(f"retired runtime Modelfile is outside manager-owned storage: {runtime}")
        if item["ollama_host"] != CATEGORY_DEFAULTS[category]["ollama_host"]:
            raise ModelError(f"retired model host/category mismatch: {item['name']}")
        normalized = dict(item); normalized["category"] = category
        result.append(normalized)
    return result


def retired_present(item: dict, registrations: dict[str, set[str] | None]) -> bool:
    source = Path(item["source"]); runtime = Path(item["runtime_modelfile"])
    registered = any(
        names is not None and item["name"] in names
        for names in registrations.values()
    )
    return source.exists() or state_path(source).exists() or runtime.exists() or registered


def purge_retired(*, yes: bool) -> int:
    if os.geteuid() != 0:
        raise ModelError("run with sudo")
    retired = load_retired_models()
    hosts = sorted({CATEGORY_DEFAULTS[category]["ollama_host"] for category in OLLAMA_CATEGORIES})
    registrations = {host: registered_models(host) for host in hosts}
    present = [item for item in retired if retired_present(item, registrations)]
    if not present:
        print("No retired package-managed models are present.")
        return 0
    print("Retired package-managed models:")
    total = 0
    for index, item in enumerate(present, 1):
        source = Path(item["source"]); size = source.stat().st_size if source.is_file() else 0
        total += size
        names = registrations.get(item["ollama_host"])
        other_hosts = [
            host for host, other_names in registrations.items()
            if host != item["ollama_host"] and other_names is not None and item["name"] in other_names
        ]
        if names is None:
            registration = "unknown (expected API unavailable)"
        elif item["name"] in names:
            registration = "present"
        elif other_hosts:
            registration = "misplaced on " + ",".join(other_hosts)
        else:
            registration = "absent"
        print(f"  {index:2d}) {item['name']} [{item['category']}, registration {registration}, source {size / 1024**3:.1f} GiB]")
    print(f"Manager-owned source data selected: {total / 1024**3:.1f} GiB")
    if not yes and prompt_line("Purge these retired package-managed models and local data? [y/N] ").lower() not in {"y", "yes"}:
        print("Cleanup cancelled.")
        return 0
    ollama_bin = shutil.which("ollama")
    failures: list[str] = []
    removed = 0
    for item in present:
        name = item["name"]; host = item["ollama_host"]
        source = Path(item["source"]); runtime = Path(item["runtime_modelfile"])
        print(f"\n>>> purging retired {name}")
        names = registrations.get(host)
        misplaced_hosts = [
            other_host
            for other_host, other_names in registrations.items()
            if other_host != host and other_names is not None and name in other_names
        ]
        if misplaced_hosts:
            print(
                "    ERROR: retired model is registered on unexpected Ollama host(s): "
                + ", ".join(misplaced_hosts)
                + "; local data retained",
                file=sys.stderr,
            )
            failures.append(name); continue
        if names is None:
            print("    ERROR: expected Ollama registration state unavailable; local data retained", file=sys.stderr)
            failures.append(name); continue
        if name in names:
            if not ollama_bin:
                print("    ERROR: ollama executable unavailable; local data retained", file=sys.stderr)
                failures.append(name); continue
            result = run_as_ollama([ollama_bin, "rm", name], {"HOME": "/var/lib/ollama", "OLLAMA_HOST": host})
            if result.returncode != 0:
                print("    ERROR: registration removal failed; local data retained", file=sys.stderr)
                failures.append(name); continue
            print(f"    removed Ollama registration from {host}")
        for path in (runtime, source, state_path(source)):
            if path.exists():
                path.unlink(); print(f"    removed {path}")
        try:
            source.parent.rmdir()
        except OSError:
            pass
        removed += 1
    print(f"\nPurged {removed} retired package-managed model(s).")
    if failures:
        print(f"Failed: {' '.join(failures)}", file=sys.stderr)
        return 2
    return 0

def print_all_models(directories: list[Path]) -> None:
    models = discover_models(directories)
    hosts = {
        CATEGORY_DEFAULTS[category]["ollama_host"] for category in OLLAMA_CATEGORIES
    }
    registrations = {host: registered_models(host) for host in hosts}
    for category in OLLAMA_CATEGORIES:
        defaults = CATEGORY_DEFAULTS[category]
        selected = [model for model in models if model["category"] == category]
        print(f"{category.title()} models:")
        print_models(defaults, selected, registrations[defaults["ollama_host"]])
    known = {model["name"] for model in models}
    hf_backings = {
        (CATEGORY_DEFAULTS[model["category"]]["ollama_host"], model["from"]): model[
            "name"
        ]
        for model in models
        if model["provider"] == "ollama-hf"
    }
    retired = {item["name"]: item for item in load_retired_models()}
    retired_registered = sorted(
        (host, name)
        for host, names in registrations.items()
        for name in names or ()
        if name in retired
    )
    if retired_registered:
        print("Retired package-managed Ollama models:")
        for host, name in retired_registered:
            print(f"    - {name:<56} [{host}, set up, cleanup-retired eligible]")
    unmanaged = sorted(
        (host, name)
        for host, names in registrations.items()
        for name in names or ()
        if name not in known and name not in retired and not (hf_backings.get((host, name)) in (names or set()))
    )
    if unmanaged:
        print("Unmanaged Ollama models (registered without a Modelfile):")
        for host, name in unmanaged:
            print(f"    - {name:<56} [{host}, set up, Modelfile missing]")
    expected = {
        model["name"]: CATEGORY_DEFAULTS[model["category"]]["ollama_host"]
        for model in models
    }
    misplaced = sorted(
        (host, name, expected[name])
        for host, names in registrations.items()
        for name in names or ()
        if name in expected and host != expected[name]
    )
    if misplaced:
        print("Misplaced Ollama models (registered on the wrong instance):")
        for host, name, wanted in misplaced:
            print(f"    - {name:<56} [{host}, expected {wanted}]")


def print_catalogs(catalogs: list[tuple[dict, list[dict]]], *, include_disabled_mtp: bool = False) -> None:
    """Print mixed catalogs while preserving each category's runtime/status rules."""
    registrations = {
        defaults["ollama_host"]: registered_models(defaults["ollama_host"])
        for defaults, _models in catalogs
        if defaults.get("ollama_host")
    }
    for defaults, models in catalogs:
        category = defaults["category"]
        available = (
            models
            if category != "mtp" or include_disabled_mtp
            else [model for model in models if model["enabled"]]
        )
        print(f"{'MTP' if category == 'mtp' else category.title()} models:")
        host = defaults.get("ollama_host")
        print_models(defaults, available, registrations.get(host) if host else None)


def state_path(output: Path) -> Path:
    return output.with_name(f"{output.name}.bc250.json")


def load_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict) or value.get("schema") not in {1, 2, 3}:
        return {}
    return value


def state_matches(state: dict, model: dict, output: Path) -> bool:
    """Compatibility helper backed by the canonical source-state inspector."""
    return inspect_local_source(state, model, output)[0] == "current"


def inspect_local_source(state: dict, model: dict, output: Path) -> tuple[str, str, str]:
    """Return (status, detail, checksum) for one manager-owned GGUF."""
    if not output.is_file():
        return "missing", "GGUF is not present", ""
    try:
        stat_result = output.stat()
    except OSError as error:
        return "unavailable", f"cannot stat GGUF: {error}", ""
    if stat_result.st_size <= 0:
        return "drift", "GGUF is empty", ""
    if not state:
        return "drift", "state sidecar is missing or invalid", ""

    recorded = str(state.get("sha256", ""))
    expected = str(model.get("sha256", ""))
    provenance = ("repository", "revision", "gguf")
    changed = [key for key in provenance if state.get(key) != model.get(key)]
    if changed:
        return "drift", f"state provenance differs: {', '.join(changed)}", recorded
    if re.fullmatch(r"[0-9a-f]{64}", recorded) is None:
        return "drift", "state sidecar has no valid SHA-256", ""
    if expected and recorded != expected:
        return "drift", "recorded SHA-256 differs from current catalog pin", recorded

    if (
        state.get("schema") in {2, 3}
        and state.get("size") == stat_result.st_size
        and state.get("mtime_ns") == stat_result.st_mtime_ns
        and state.get("ctime_ns") == stat_result.st_ctime_ns
    ):
        return "current", "verified by recorded file identity", recorded

    try:
        actual = sha256(output)
    except OSError as error:
        return "unavailable", f"cannot hash GGUF: {error}", recorded
    if actual != recorded:
        return "drift", "GGUF content differs from recorded SHA-256", recorded
    return "current", "verified by SHA-256", recorded


def rendered_modelfile_content(source: Path, model: dict, output: Path | None) -> str:
    """Render the runtime Modelfile without mutating the filesystem."""
    rendered: list[str] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith("# Source: "):
            line = f"# Source: {model['repository']} @ {model['revision']}"
        elif line.startswith("# GGUF: "):
            line = f"# GGUF: {model['gguf']}"
        elif line.startswith("FROM ") and output is not None:
            line = f"FROM {output}"
        rendered.append(line)
    return "\n".join(rendered) + "\n"


def runtime_modelfile_path(
    defaults: dict, model: dict, output: Path | None
) -> Path | None:
    if not model.get("modelfile"):
        return None
    configured = os.environ.get("MODELFILE_DIR") or defaults.get(
        "modelfile_destination", ""
    )
    if configured:
        return Path(configured) / model["modelfile"]
    if output is not None:
        return output.parent / model["modelfile"]
    return Path(model["template"])


def inspect_runtime_modelfile(
    model: dict, runtime: Path | None, output: Path | None
) -> tuple[str, str]:
    if model["provider"] == "download-only":
        return "not applicable", "download-only model"
    if runtime is None:
        return "unavailable", "runtime Modelfile path is unavailable"
    try:
        expected = rendered_modelfile_content(model["template"], model, output)
    except OSError as error:
        return "unavailable", f"cannot render catalog Modelfile: {error}"
    try:
        current = runtime.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "missing", "runtime Modelfile is missing"
    except OSError as error:
        return "unavailable", f"cannot read runtime Modelfile: {error}"
    if current == expected:
        return "current", "matches current catalog definition"
    return "drift", "runtime Modelfile differs from current catalog definition"


def _strip_etag(value: str) -> str:
    value = value.strip()
    value = value.removeprefix("W/")
    return value.strip('"')


def remote_file_sha256(model: dict, token: str = "") -> str:
    """Resolve a Hugging Face file SHA from response metadata without downloading it."""
    revision = "main" if model["revision"] == "latest" else model["revision"]
    repository = urllib.parse.quote(model["repository"], safe="/")
    revision_q = urllib.parse.quote(revision, safe="")
    filename = urllib.parse.quote(model["gguf"], safe="")
    url = f"https://huggingface.co/{repository}/resolve/{revision_q}/{filename}"
    headers = {"User-Agent": f"{PROJECT}/model-status"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            candidates = (
                response.headers.get("X-Linked-Etag", ""),
                response.headers.get("ETag", ""),
            )
    except (OSError, urllib.error.HTTPError, urllib.error.URLError) as error:
        raise ModelError(f"remote metadata lookup failed: {error}") from error
    for candidate in candidates:
        digest = _strip_etag(candidate)
        if digest.startswith("sha256:"):
            digest = digest.removeprefix("sha256:")
        if re.fullmatch(r"[0-9a-f]{64}", digest):
            return digest
    raise ModelError("remote metadata did not expose a comparable SHA-256")


def status_token(token_file: Path | None) -> str:
    if token_file:
        try:
            return token_file.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise ModelError(f"cannot read token file {token_file}: {error}") from error
    return os.environ.get("HF_TOKEN", "").strip()


def inspect_model_state(
    defaults: dict,
    model: dict,
    *,
    registrations: set[str] | None = None,
    destination: str | None = None,
    online: bool = False,
    token: str = "",
) -> ModelInspection:
    """Inspect catalog, local source, runtime Modelfile and registration as one contract."""
    output: Path | None = None
    metadata: Path | None = None
    source_checksum = ""
    if model["provider"] == "ollama-hf":
        source_status = "ollama-managed"
        source_detail = "source/model projector blobs are managed by Ollama"
    else:
        output = model_path(defaults, model, destination)
        metadata = state_path(output)
        state = load_state(metadata)
        source_status, source_detail, source_checksum = inspect_local_source(
            state, model, output
        )

    runtime = runtime_modelfile_path(defaults, model, output)
    modelfile_status, _modelfile_detail = inspect_runtime_modelfile(
        model, runtime, output
    )

    if model["provider"] == "download-only":
        registration_status = "not applicable"
    elif registrations is None:
        registration_status = "unavailable"
    elif model["name"] in registrations:
        registration_status = "current"
    else:
        registration_status = "missing"

    statuses = {source_status, modelfile_status, registration_status}
    if source_status == "missing":
        overall = "MISSING"
    elif "drift" in statuses or "missing" in statuses:
        overall = "DRIFT"
    elif "unavailable" in statuses:
        overall = "UNKNOWN"
    else:
        overall = "CURRENT"

    remote_status = "not checked"
    remote_detail = ""
    if online:
        if model["revision"] != "latest":
            remote_status = "pinned"
            remote_detail = f"catalog pins revision {model['revision']}"
        elif model["provider"] == "ollama-hf":
            remote_status = "unavailable"
            remote_detail = "Ollama-managed source cannot be compared to manager-owned GGUF state"
        elif source_status != "current" or not source_checksum:
            remote_status = "unavailable"
            remote_detail = "local source is not verified, so update comparison is unsafe"
        else:
            try:
                remote_checksum = remote_file_sha256(model, token)
            except ModelError as error:
                remote_status = "unavailable"
                remote_detail = str(error)
            else:
                if remote_checksum == source_checksum:
                    remote_status = "current"
                    remote_detail = "remote file SHA-256 matches local verified source"
                else:
                    remote_status = "update available"
                    remote_detail = f"remote SHA-256 {remote_checksum}"

    return ModelInspection(
        model=model,
        source_path=output,
        state_path=metadata,
        source_status=source_status,
        source_detail=source_detail,
        source_checksum=source_checksum,
        runtime_modelfile=runtime,
        modelfile_status=modelfile_status,
        registration_status=registration_status,
        overall_status=overall,
        remote_status=remote_status,
        remote_detail=remote_detail,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_file_permissions(path: Path, uid: int, gid: int, mode: int) -> bool:
    """Apply ownership/mode only when needed; return whether inode metadata changed."""
    current = path.stat()
    changed = False
    if current.st_uid != uid or current.st_gid != gid:
        os.chown(path, uid, gid)
        changed = True
        current = path.stat()
    if stat.S_IMODE(current.st_mode) != mode:
        os.chmod(path, mode)
        changed = True
    return changed


def write_state(path: Path, model: dict, checksum: str, gid: int) -> None:
    stat = path.with_name(path.name.removesuffix(".bc250.json")).stat()
    existing = load_state(path)
    value = {
        "schema": 3,
        "model_name": model.get("name", model["id"]),
        "model_id": model["id"],
        "category": model.get("category", ""),
        "repository": model["repository"],
        "revision": model["revision"],
        "gguf": model["gguf"],
        "sha256": checksum,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": stat.st_ctime_ns,
    }
    # Preserve dedupe bookkeeping across harmless state refreshes. The record
    # contains source/blob stat signatures, so storage.py will still reject it
    # automatically if a source inode/content transition made it stale.
    if isinstance(existing.get("dedupe"), dict):
        value["dedupe"] = existing["dedupe"]
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chown(temporary, 0, gid)
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_replace(staged: Path, output: Path) -> None:
    try:
        os.replace(staged, output)
        return
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent, prefix=f".{output.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            with staged.open("rb") as source:
                shutil.copyfileobj(source, stream, length=1024 * 1024)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
        staged.unlink()
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def command_path(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        if name == "script":
            raise ModelError(
                "missing command: script (install Fedora package util-linux-script)"
            )
        raise ModelError(f"missing command: {name}")
    return path


def ollama_host(defaults: dict, override: str | None = None) -> str:
    return (
        override
        or os.environ.get("OLLAMA_HOST")
        or os.environ.get("OLLAMA_URL")
        or defaults.get("ollama_host", "127.0.0.1:11434")
    )


def ollama_identity() -> tuple[int, int]:
    try:
        return pwd.getpwnam("ollama").pw_uid, grp.getgrnam("ollama").gr_gid
    except KeyError as error:
        raise ModelError(
            "ollama user or group is missing; run bc250-install-ollama"
        ) from error


def ensure_directory(path: Path, uid: int, gid: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chown(path, uid, gid)
    os.chmod(path, 0o750)


def run_as_ollama(
    command: list[str], environment: dict[str, str], *, terminal: bool = False
) -> subprocess.CompletedProcess:
    child_environment = dict(os.environ)
    child_environment.update(environment)
    argv = [
        command_path("runuser"),
        "--preserve-environment",
        "-u",
        "ollama",
        "--",
        *command,
    ]
    sys.stdout.flush()
    sys.stderr.flush()
    if terminal:
        # Hugging Face suppresses progress when output is captured. A PTY keeps
        # live byte progress visible in both direct use and installer logs.
        argv = [
            command_path("script"),
            "--quiet",
            "--return",
            "--flush",
            "--command",
            shlex.join(argv),
            "/dev/null",
        ]
    return subprocess.run(argv, env=child_environment, check=False)


def hf_environment(token: str, hf_home: Path) -> dict[str, str]:
    return {
        "HOME": "/var/lib/ollama",
        "HF_TOKEN": token,
        "HF_HOME": str(hf_home),
        "HF_HUB_CACHE": str(hf_home / "hub"),
        "HF_HUB_DISABLE_PROGRESS_BARS": "0",
        # Regular HTTPS is the supported appliance path.  Avoid hf_xet
        # advisories that suggest unmanaged pip changes on the host.
        "HF_HUB_DISABLE_XET": "1",
        "PYTHONUNBUFFERED": "1",
    }


def can_prompt() -> bool:
    try:
        with open("/dev/tty", "r", encoding="utf-8"):
            return True
    except OSError:
        return sys.stdin.isatty()


def prompt_line(message: str, default: str = "") -> str:
    try:
        with open("/dev/tty", "r+", encoding="utf-8") as tty:
            tty.write(message)
            tty.flush()
            return tty.readline().strip()
    except OSError:
        return input(message).strip() if sys.stdin.isatty() else default


def prompt_secret(message: str) -> str:
    try:
        with open("/dev/tty", "r+", encoding="utf-8") as tty:
            return getpass.getpass(message, stream=tty).strip()
    except OSError:
        return getpass.getpass(message).strip() if sys.stdin.isatty() else ""



def hf_session_value() -> str | None:
    path = os.environ.get("BC250_HF_SESSION_FILE", "").strip()
    if not path:
        return None
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if value == "anonymous":
        return ""
    if value.startswith("token:"):
        return value.removeprefix("token:")
    return None


def write_hf_session(token: str) -> None:
    path = os.environ.get("BC250_HF_SESSION_FILE", "").strip()
    if not path:
        return
    target = Path(path)
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"token:{token}" if token else "anonymous")
        os.chmod(target, 0o600)
    except OSError as error:
        raise ModelError(f"cannot update transient Hugging Face session file {target}: {error}") from error


def hf_token(hf_bin: str, hf_home: Path, token_file: Path | None) -> str:
    if token_file:
        try:
            token = token_file.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise ModelError(f"cannot read token file {token_file}: {error}") from error
    else:
        token = os.environ.get("HF_TOKEN", "").strip()
        if not token:
            session_token = hf_session_value()
            if session_token is not None:
                return session_token
    if not token and os.environ.get("BC250_HF_ANONYMOUS") != "1" and can_prompt():
        token = prompt_secret("HF_TOKEN (optional; Enter for anonymous downloads): ")
    if (
        token
        and run_as_ollama(
            [hf_bin, "auth", "whoami"], hf_environment(token, hf_home)
        ).returncode
        == 0
    ):
        print("Using the validated Hugging Face token for this installer/model session.")
        write_hf_session(token)
        return token
    if token:
        print(
            "WARNING: Hugging Face rejected the token; downloading anonymously.",
            file=sys.stderr,
        )
    else:
        print("Using anonymous Hugging Face downloads for this installer/model session.")
    write_hf_session("")
    return ""


def remove_hf_backing_registration(ollama_bin: str, host: str, model: dict) -> None:
    """Drop a redundant hf.co source manifest after the friendly alias exists."""
    registrations = registered_models(host)
    source = model["from"]
    if (
        registrations is None
        or source not in registrations
        or model["name"] not in registrations
    ):
        return
    result = run_as_ollama(
        [ollama_bin, "rm", source],
        {"HOME": "/var/lib/ollama", "OLLAMA_HOST": host},
    )
    if result.returncode != 0:
        print(
            f"    WARNING: could not remove temporary HF source registration {source}",
            file=sys.stderr,
        )
        return
    remaining = registered_models(host)
    if remaining is not None and model["name"] not in remaining:
        raise ModelError(
            f"friendly Ollama registration disappeared after removing {source}"
        )
    print(f"    removed temporary HF source registration {source}")



def write_runtime_modelfile(
    source: Path, model: dict, output: Path | None, destination: Path
) -> bool:
    content = rendered_modelfile_content(source, model, output)
    try:
        if destination.read_text(encoding="utf-8") == content:
            return False
    except FileNotFoundError:
        pass
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def reconciliation_reason(
    inspection: ModelInspection,
    *,
    force_download: bool,
    source_changed: bool,
    template_changed: bool,
) -> str:
    reasons: list[str] = []
    if force_download:
        reasons.append("refresh requested")
    if source_changed:
        reasons.append("GGUF/source changed")
    if template_changed:
        reasons.append("Modelfile changed")
    if inspection.registration_status == "unavailable":
        reasons.append("registration state unavailable")
    elif inspection.registration_status != "current":
        reasons.append("registration missing")
    return ", ".join(reasons) or "registration reconciliation required"


def apply_models(defaults: dict, models: list[dict], args: argparse.Namespace) -> int:
    """Converge selected models to the current catalog definition."""
    if os.geteuid() != 0:
        raise ModelError("run with sudo")
    if len(models) != 1 and (args.revision is not None or args.sha256 is not None):
        raise ModelError("--revision and --sha256 require one selected model")

    force_download = args.command == "refresh"
    uid, gid = ollama_identity()
    command_path("runuser")
    needs_download = any(m["provider"] != "ollama-hf" for m in models)
    hf_bin = command_path("hf") if needs_download else ""
    if needs_download:
        command_path("script")
    ollama_bin = (
        command_path("ollama")
        if any(m["provider"].startswith("ollama") for m in models)
        else ""
    )
    host = ollama_host(defaults, args.host)
    registrations = registered_models(host) if ollama_bin else None
    hf_home = Path(os.environ.get("HF_HOME", f"/var/cache/{PROJECT}/huggingface"))
    download_root = Path(
        os.environ.get(
            "DOWNLOAD_DIR", str(hf_home / "downloads" / defaults["download_namespace"])
        )
    )
    modelfile_root = (
        Path(os.environ.get("MODELFILE_DIR", defaults.get("modelfile_destination", "")))
        if os.environ.get("MODELFILE_DIR") or defaults.get("modelfile_destination")
        else None
    )
    if needs_download:
        for path in (hf_home, hf_home / "hub", download_root):
            ensure_directory(path, uid, gid)
    if modelfile_root:
        ensure_directory(modelfile_root, 0, gid)

    token: str | None = None
    failures: list[str] = []
    summarize_current = (
        os.environ.get("BC250_MODELCTL_CURRENT_SUMMARY") == "1"
        and not force_download
    )
    current_skipped = 0
    for configured in models:
        model = dict(configured)
        if args.revision is not None:
            model["revision"] = args.revision
        if args.sha256 is not None:
            model["sha256"] = args.sha256
        expected = model.get("sha256", "")
        if expected and re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise ModelError("--sha256 must be 64 lowercase hexadecimal characters")

        label = model.get("name", model["id"])
        header_printed = False

        def show_header(current_label: str, current_provider: str) -> None:
            nonlocal header_printed
            if not header_printed:
                print(f"\n>>> {current_label} [{current_provider}]")
                header_printed = True

        try:
            inspection = inspect_model_state(
                defaults,
                model,
                registrations=registrations,
                destination=args.destination or os.environ.get("DEST"),
            )
            if not summarize_current:
                show_header(label, model["provider"])
            if model["provider"] == "ollama-hf":
                if args.revision is not None or args.sha256 is not None or args.destination:
                    raise ModelError(
                        "remote Ollama-managed models do not accept source overrides"
                    )
                runtime_template = inspection.runtime_modelfile or model["template"]
                template_changed = write_runtime_modelfile(
                    model["template"], model, None, runtime_template
                )
                os.chown(runtime_template, 0, gid)
                os.chmod(runtime_template, 0o640)
                if (
                    not force_download
                    and not template_changed
                    and inspection.registration_status == "current"
                ):
                    if summarize_current:
                        current_skipped += 1
                    else:
                        print("    already current; skipping")
                    continue
                show_header(label, model["provider"])
                reason = reconciliation_reason(
                    inspection,
                    force_download=force_download,
                    source_changed=False,
                    template_changed=template_changed,
                )
                print(f"    registration drift: {reason}; reconciling")
                result = run_as_ollama(
                    [ollama_bin, "create", model["name"], "-f", str(runtime_template)],
                    {"HOME": "/var/lib/ollama", "OLLAMA_HOST": host},
                )
                if result.returncode != 0:
                    raise ModelError("ollama create failed")
                if registrations is not None:
                    registrations.add(model["name"])
                remove_hf_backing_registration(ollama_bin, host, model)
                print("    registered with Ollama; source blobs are Ollama-managed")
                continue

            output = inspection.source_path or model_path(
                defaults, model, args.destination or os.environ.get("DEST")
            )
            ensure_directory(output.parent, uid, gid)
            metadata = state_path(output)
            source_changed = True
            source_metadata_changed = False
            if inspection.source_status == "current" and not force_download:
                source_changed = False
                checksum = inspection.source_checksum
                permissions_changed = ensure_file_permissions(output, 0, gid, 0o640)
                current = output.stat()
                state = load_state(metadata)
                source_metadata_changed = (
                    state.get("schema") != 3
                    or state.get("size") != current.st_size
                    or state.get("mtime_ns") != current.st_mtime_ns
                    or state.get("ctime_ns") != current.st_ctime_ns
                    or permissions_changed
                )
                if source_metadata_changed:
                    write_state(metadata, model, checksum, gid)
                if not summarize_current:
                    print(f"    reusing validated GGUF; recorded SHA-256 {checksum}")
            else:
                show_header(label, model["provider"])
                minimum = (
                    args.min_free_bytes
                    if args.min_free_bytes is not None
                    else int(defaults.get("min_free_bytes", 0))
                )
                free = shutil.disk_usage(output.parent).free
                print(f"    filesystem free: {free / 1024**3:.1f} GiB")
                if free < LOW_FREE_BYTES:
                    print(
                        "    WARNING: low filesystem headroom before model download",
                        file=sys.stderr,
                    )
                if minimum and free < minimum:
                    raise ModelError(
                        f"{free / 1024**3:.1f} GiB free; {minimum / 1024**3:.1f} GiB required"
                    )
                staging = download_root / model["id"]
                ensure_directory(staging, uid, gid)
                staged = staging / model["gguf"]
                staged.unlink(missing_ok=True)
                if token is None:
                    session = getattr(args, "hf_session", None)
                    if isinstance(session, dict) and session.get("resolved"):
                        token = str(session.get("token", ""))
                    else:
                        token = hf_token(hf_bin, hf_home, args.token_file)
                        if isinstance(session, dict):
                            session["resolved"] = True
                            session["token"] = token
                command = [hf_bin, "download", model["repository"], model["gguf"]]
                if model["revision"] != "latest":
                    command.extend(("--revision", model["revision"]))
                command.extend(("--local-dir", str(staging)))
                print(
                    f"    downloading {model['repository']} @ {model['revision']}: "
                    f"{model['gguf']}"
                )
                if (
                    run_as_ollama(
                        command, hf_environment(token, hf_home), terminal=True
                    ).returncode
                    != 0
                ):
                    raise ModelError("Hugging Face download failed")
                if not staged.is_file() or staged.stat().st_size == 0:
                    raise ModelError(f"download completed without {staged}")
                print("    calculating SHA-256")
                checksum = sha256(staged)
                if expected and checksum != expected:
                    raise ModelError(
                        f"checksum mismatch: got {checksum}, expected {expected}"
                    )
                atomic_replace(staged, output)
                ensure_file_permissions(output, 0, gid, 0o640)
                write_state(metadata, model, checksum, gid)
                print(f"    recorded SHA-256 {checksum}")

            if model["provider"] == "download-only":
                show_header(label, model["provider"])
                print("    ready for llama.cpp")
                continue

            runtime_template = inspection.runtime_modelfile or (
                output.parent / model["modelfile"]
            )
            template_changed = write_runtime_modelfile(
                model["template"], model, output, runtime_template
            )
            os.chown(runtime_template, 0, gid)
            os.chmod(runtime_template, 0o640)
            if (
                not force_download
                and not source_changed
                and not template_changed
                and inspection.registration_status == "current"
            ):
                if summarize_current and not source_metadata_changed:
                    current_skipped += 1
                    continue
                show_header(label, model["provider"])
                if source_metadata_changed:
                    print("    refreshed source metadata/permissions")
                print("    already current; skipping")
                continue
            show_header(label, model["provider"])
            reason = reconciliation_reason(
                inspection,
                force_download=force_download,
                source_changed=source_changed,
                template_changed=template_changed,
            )
            print(f"    registration drift: {reason}; reconciling")
            result = run_as_ollama(
                [ollama_bin, "create", model["name"], "-f", str(runtime_template)],
                {"HOME": "/var/lib/ollama", "OLLAMA_HOST": host},
            )
            if result.returncode != 0:
                raise ModelError("ollama create failed")
            if registrations is not None:
                registrations.add(model["name"])
            print("    registered with Ollama")
        except (ModelError, OSError) as error:
            show_header(label, model["provider"])
            print(f"    ERROR: {error}", file=sys.stderr)
            failures.append(label)

    if summarize_current and current_skipped:
        category = str(defaults.get("category", "models"))
        title = "MTP" if category == "mtp" else category.title()
        if current_skipped == len(models) and not failures:
            print(f"{title}: {current_skipped}/{len(models)} already current; no changes needed.")
        else:
            print(f"{title}: {current_skipped}/{len(models)} already current.")

    if failures:
        print(f"\nFailed: {' '.join(failures)}", file=sys.stderr)
        return 2
    print(f"\nDone: {len(models)} model(s) processed.")
    return 0


def show_removal_plan(
    groups: list[tuple[dict, list[dict]]], args: argparse.Namespace
) -> None:
    keep_source = args.command == "unregister"
    title = "Unregister plan:" if keep_source else "Removal plan:"
    print(title)
    for defaults, models in groups:
        host = ollama_host(defaults, getattr(args, "host", None))
        for model in models:
            label = model.get("name", model["id"])
            print(f"\n{label}")
            if model["provider"].startswith("ollama"):
                print(f"  Registration: remove from {host}")
            else:
                print("  Registration: none (download-only)")
            runtime = runtime_modelfile_path(
                defaults,
                model,
                None if model["provider"] == "ollama-hf" else model_path(
                    defaults, model, getattr(args, "destination", None)
                ),
            )
            if runtime and model["provider"] != "download-only":
                print(f"  Runtime Modelfile: remove {runtime}")
            if model["provider"] == "ollama-hf":
                print("  Manager-owned source: none (Ollama-managed model/projector blobs)")
            else:
                output = model_path(defaults, model, getattr(args, "destination", None))
                try:
                    size = (
                        f" ({output.stat().st_size / 1024**3:.1f} GiB)"
                        if output.is_file()
                        else ""
                    )
                except OSError:
                    size = ""
                action = "retain" if keep_source else "remove"
                print(f"  Manager-owned source: {action} {output}{size}")
                print(f"  State sidecar: {action} {state_path(output)}")
            print("  Catalog definition: retain")


def remove_models(defaults: dict, models: list[dict], args: argparse.Namespace) -> int:
    """Unregister or fully remove selected manager-owned model state."""
    if os.geteuid() != 0:
        raise ModelError("run with sudo")
    keep_source = args.command == "unregister"
    if keep_source and any(model["provider"] == "download-only" for model in models):
        raise ModelError("download-only MTP models have no registration; use 'remove'")
    if not args.yes:
        show_removal_plan([(defaults, models)], args)
        names = ", ".join(model.get("name", model["id"]) for model in models)
        verb = "Unregister" if keep_source else "Remove"
        if prompt_line(f"{verb} {names}? [y/N] ").lower() not in {"y", "yes"}:
            print(f"{verb} cancelled.")
            return 0

    _uid, _gid = ollama_identity()
    host = ollama_host(defaults, getattr(args, "host", None))
    ollama_bin = shutil.which("ollama")
    failures: list[str] = []
    removed = 0
    for model in models:
        label = model.get("name", model["id"])
        verb = "unregistering" if keep_source else "removing"
        print(f"\n>>> {verb} {label}")
        if model["provider"].startswith("ollama"):
            if not ollama_bin:
                print(
                    "    ERROR: ollama executable is unavailable; local source retained",
                    file=sys.stderr,
                )
                failures.append(label)
                continue
            result = run_as_ollama(
                [ollama_bin, "rm", model["name"]],
                {"HOME": "/var/lib/ollama", "OLLAMA_HOST": host},
            )
            if result.returncode != 0:
                registrations = registered_models(host)
                if registrations is None or model["name"] in registrations:
                    print(
                        "    ERROR: Ollama registration could not be removed; local source retained",
                        file=sys.stderr,
                    )
                    failures.append(label)
                    continue

        output = None
        if model["provider"] != "ollama-hf":
            output = model_path(defaults, model, getattr(args, "destination", None))
        elif keep_source:
            print(
                "    no manager-owned GGUF/state to retain; "
                "multimodal source/projector blobs are Ollama-managed"
            )
        runtime = runtime_modelfile_path(defaults, model, output)
        paths: list[Path] = []
        if runtime and model["provider"] != "download-only":
            paths.append(runtime)
        if output is not None and not keep_source:
            paths.extend((output, state_path(output)))
        for path in paths:
            if path.exists():
                path.unlink()
                print(f"    removed {path}")
        if output is not None and keep_source:
            for path in (output, state_path(output)):
                if path.exists():
                    print(f"    retained local source {path}")
        if output is not None and not keep_source:
            try:
                output.parent.rmdir()
            except OSError:
                pass
        removed += 1

    if keep_source:
        print(
            f"\nUnregistered {removed} model(s). Verified GGUF/state retained where present."
        )
    else:
        print(
            f"\nRemoved {removed} model(s). Catalog definitions were retained; "
            "manager-owned GGUF/state removed where present."
        )
    if failures:
        print(f"Failed: {' '.join(failures)}", file=sys.stderr)
        return 2
    return 0



class FriendlyArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ModelError(message)


CLI_EPILOG = """Common workflows:
  bc250-model list
  sudo bc250-model status agentic
  sudo bc250-model apply agentic MODEL
  sudo bc250-model refresh agentic MODEL
  sudo bc250-model unregister agentic MODEL
  sudo bc250-model remove agentic MODEL
  sudo bc250-model purge-retired

Use 'bc250-model COMMAND --help' for command-specific options.
"""


def catalog_arguments(
    parser: argparse.ArgumentParser, *, category_optional: bool = False
) -> None:
    parser.add_argument(
        "category",
        choices=CATEGORIES,
        nargs="?" if category_optional else None,
        help="model category; use 'all' for the combined catalog",
    )
    parser.add_argument("--source", type=Path, help="alternate MTP TOML catalog")
    parser.add_argument(
        "--modelfile-dir",
        type=Path,
        action="append",
        help="alternate Modelfile directory; may be repeated",
    )


def selection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "selection",
        nargs="?",
        help="model id/index/range or comma-separated selection; also recommended, production or all",
    )


def mutation_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress catalog and topology-transition chatter",
    )
    parser.add_argument(
        "--host",
        help="override the target Ollama API for this invocation",
    )
    parser.add_argument(
        "--destination",
        help="override the manager-owned GGUF destination root",
    )


def apply_arguments(parser: argparse.ArgumentParser) -> None:
    catalog_arguments(parser, category_optional=True)
    selection_arguments(parser)
    mutation_common_arguments(parser)
    parser.add_argument(
        "--revision",
        help="one-model source revision override for this invocation",
    )
    parser.add_argument(
        "--sha256",
        help="one-model expected GGUF SHA-256 override for this invocation",
    )
    parser.add_argument(
        "--min-free-bytes",
        type=int,
        help="minimum free bytes required before a source download",
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        help="Hugging Face token file for downloads",
    )
    parser.add_argument(
        "--include-disabled",
        action="store_true",
        help="allow disabled MTP entries to be selected",
    )


def removal_arguments(parser: argparse.ArgumentParser) -> None:
    catalog_arguments(parser, category_optional=True)
    selection_arguments(parser)
    mutation_common_arguments(parser)
    parser.add_argument("--yes", action="store_true", help="skip confirmation")


def build_parser() -> argparse.ArgumentParser:
    parser = FriendlyArgumentParser(
        prog="bc250-model",
        description=(
            "Manage BC-250 model catalog definitions, verified local sources and "
            "Ollama registrations."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CLI_EPILOG,
    )
    commands = parser.add_subparsers(dest="command")

    listing = commands.add_parser(
        "list",
        help="list catalog definitions without inspecting protected runtime state",
    )
    catalog_arguments(listing, category_optional=True)
    listing.add_argument(
        "--all", action="store_true", help="include disabled MTP entries"
    )

    status = commands.add_parser(
        "status",
        help="inspect source, provenance, Modelfile and registration state",
    )
    catalog_arguments(status, category_optional=True)
    selection_arguments(status)
    status.add_argument(
        "--online",
        action="store_true",
        help="for moving revisions, compare the verified local GGUF with upstream metadata",
    )
    status.add_argument(
        "--token-file", type=Path, help="Hugging Face token file for --online"
    )
    display = status.add_mutually_exclusive_group()
    display.add_argument(
        "--verbose", action="store_true", help="show source identity and resolved paths"
    )
    display.add_argument(
        "--compact", action="store_true", help="show one state-rich catalog line per model"
    )
    status.add_argument(
        "--include-disabled",
        action="store_true",
        help="include disabled MTP entries",
    )

    path = commands.add_parser(
        "path",
        help="print the resolved source path and MTP context metadata for one model",
    )
    catalog_arguments(path, category_optional=True)
    path.add_argument("id", nargs="?", help="exact catalog model id")

    applying = commands.add_parser(
        "apply",
        help="make selected models match the current catalog; reuse verified GGUFs",
    )
    apply_arguments(applying)

    refreshing = commands.add_parser(
        "refresh",
        help="re-fetch selected model sources and then apply the current catalog",
    )
    apply_arguments(refreshing)

    unregistering = commands.add_parser(
        "unregister",
        help="remove Ollama registration/runtime Modelfile but retain GGUF and state",
    )
    removal_arguments(unregistering)

    removing = commands.add_parser(
        "remove",
        help="remove registration plus manager-owned GGUF/state; retain catalog definition",
    )
    removal_arguments(removing)

    retired = commands.add_parser(
        "purge-retired",
        help="purge models explicitly retired by the package",
    )
    retired.add_argument("--yes", action="store_true", help="skip confirmation")
    return parser


def legacy_cli_hint(argv: list[str]) -> str | None:
    if not argv:
        return None
    first = argv[0]
    if first in {"--install", "-install"}:
        return "'--install' is not a command; use: sudo bc250-model apply <category> [selection]"
    if first == "--refresh":
        return "'--refresh' is now an explicit operation; use: sudo bc250-model refresh <category> [selection]"
    if first == "install":
        if "--refresh" in argv[1:]:
            cleaned = " ".join(item for item in argv[1:] if item != "--refresh")
            return f"'install --refresh' was replaced by 'refresh'; use: sudo bc250-model refresh {cleaned}".rstrip()
        rest = " ".join(argv[1:])
        return f"'install' was replaced by 'apply'; use: sudo bc250-model apply {rest}".rstrip()
    if first == "cleanup":
        keep = "--keep-gguf" in argv[1:]
        rest = " ".join(item for item in argv[1:] if item != "--keep-gguf")
        replacement = "unregister" if keep else "remove"
        return f"'cleanup' was replaced by '{replacement}'; use: sudo bc250-model {replacement} {rest}".rstrip()
    if first == "cleanup-retired":
        return "'cleanup-retired' was replaced by 'purge-retired'; use: sudo bc250-model purge-retired"
    if first == "resolve":
        rest = " ".join(argv[1:])
        return f"'resolve' was replaced by 'path'; use: bc250-model path {rest}".rstrip()
    if first in CATEGORIES:
        if "--install" in argv[1:] or "-install" in argv[1:]:
            return f"command comes before category; use: sudo bc250-model apply {first} [selection]"
        if "--refresh" in argv[1:]:
            return f"command comes before category; use: sudo bc250-model refresh {first} [selection]"
    return None


def category_required(command: str) -> ModelError:
    categories = ", ".join(CATEGORIES)
    example = {
        "apply": "sudo bc250-model apply agentic",
        "refresh": "sudo bc250-model refresh agentic MODEL",
        "unregister": "sudo bc250-model unregister agentic MODEL",
        "remove": "sudo bc250-model remove agentic MODEL",
        "path": "bc250-model path agentic MODEL",
    }.get(command, f"bc250-model {command} agentic")
    return ModelError(
        f"{command}: model category is required; choose one of: {categories}. Example: {example}"
    )


def require_privilege(command: str) -> None:
    if command == "status" and os.geteuid() != 0:
        raise ModelError(
            "status inspects protected GGUF/state directories; run: sudo bc250-model status ..."
        )
    if command in {"apply", "refresh", "unregister", "remove", "purge-retired"} and os.geteuid() != 0:
        raise ModelError(f"{command} changes package-managed model state; run with sudo")


def definition_origin(model: dict) -> str:
    origin = str(model.get("origin", "catalog"))
    if model.get("overrides_origin"):
        return f"{origin} override"
    if model.get("category") == "mtp":
        return "enabled" if model.get("enabled") else "disabled"
    return origin


def print_catalog_models(models: list[dict]) -> None:
    for offset, model in enumerate(models):
        index = model.get("index", offset)
        label = model.get("name", model["id"])
        details = [model["provider"], definition_origin(model)]
        print(f"  {index:2d}) {label:<56} [{', '.join(details)}]")


def print_catalogs_basic(
    catalogs: list[tuple[dict, list[dict]]], *, include_disabled_mtp: bool
) -> None:
    for defaults, models in catalogs:
        category = defaults["category"]
        available = (
            models
            if category != "mtp" or include_disabled_mtp
            else [model for model in models if model["enabled"]]
        )
        if not available:
            continue
        print(f"{'MTP' if category == 'mtp' else category.title()} models:")
        print_catalog_models(available)


def status_source_text(inspection: ModelInspection) -> str:
    mapping = {
        "current": "present, verified",
        "missing": "missing",
        "drift": "present, not current",
        "unavailable": "unavailable",
        "ollama-managed": "Ollama-managed",
    }
    return mapping.get(inspection.source_status, inspection.source_status)


def recommended_status_action(inspection: ModelInspection) -> str | None:
    model = inspection.model
    category = model["category"]
    name = model.get("name", model["id"])
    if inspection.remote_status == "update available":
        if category == "mtp" and not model.get("enabled", False):
            return f"sudo bc250-model refresh mtp {name} --include-disabled"
        return f"sudo bc250-model refresh {category} {name}"
    if inspection.overall_status in {"MISSING", "DRIFT"}:
        if category == "mtp" and not model.get("enabled", False):
            return f"sudo bc250-fetch-mtp {name}"
        return f"sudo bc250-model apply {category} {name}"
    return None


def compact_inspection_details(inspection: ModelInspection) -> list[str]:
    """Return concise state labels suitable for interactive model selection."""
    model = inspection.model
    if (
        model.get("category") == "agentic"
        and inspection.registration_status == "unavailable"
        and inspection.source_status in {"current", "ollama-managed"}
        and inspection.modelfile_status == "current"
    ):
        return ["agent lane inactive", "deferred"]
    if inspection.overall_status == "CURRENT":
        return ["CURRENT"]

    details = [model["provider"], definition_origin(model)]
    source = {
        "current": "source verified",
        "missing": "source missing",
        "drift": "source drift",
        "unavailable": "source unavailable",
        "ollama-managed": "source Ollama-managed",
    }.get(inspection.source_status, f"source {inspection.source_status}")
    details.append(source)
    if model["provider"] != "download-only":
        modelfile = {
            "current": "Modelfile current",
            "missing": "Modelfile missing",
            "drift": "Modelfile drift",
            "unavailable": "Modelfile unavailable",
        }.get(inspection.modelfile_status, f"Modelfile {inspection.modelfile_status}")
        details.append(modelfile)
        registration = {
            "current": "registered",
            "missing": "not registered",
            "unavailable": "registration unavailable",
        }.get(
            inspection.registration_status,
            f"registration {inspection.registration_status}",
        )
        details.append(registration)
    details.append(inspection.overall_status)
    return details

def print_model_inspection_compact(inspection: ModelInspection) -> None:
    model = inspection.model
    index = int(model.get("index", 0))
    label = model.get("name", model["id"])
    details = compact_inspection_details(inspection)
    print(f"  {index:2d}) {label:<56} [{', '.join(details)}]")


def print_model_inspection(inspection: ModelInspection, *, verbose: bool) -> None:
    model = inspection.model
    label = model.get("name", model["id"])
    print(label)
    print(f"  Definition:     {definition_origin(model)}")
    print(f"  GGUF/source:    {status_source_text(inspection)}")
    if inspection.source_status not in {"current", "ollama-managed"}:
        print(f"    detail:       {inspection.source_detail}")
    if model["provider"] != "download-only":
        print(f"  Modelfile:      {inspection.modelfile_status}")
        registration = {
            "current": "present",
            "missing": "missing",
            "unavailable": "unavailable",
        }.get(inspection.registration_status, inspection.registration_status)
        print(f"  Registration:   {registration}")
    upstream = inspection.remote_status
    if upstream == "not checked":
        upstream += " (use --online)"
    print(f"  Upstream:       {upstream}")
    if inspection.remote_detail:
        print(f"    detail:       {inspection.remote_detail}")
    print(f"  Status:         {inspection.overall_status}")
    action = recommended_status_action(inspection)
    if action:
        print(f"  Recommended:    {action}")
    if verbose:
        repository = str(model.get("repository") or "")
        revision = str(model.get("revision") or "")
        if repository:
            print(f"  Source repo:    {repository}")
        if revision:
            print(f"  Source revision: {revision}")
        if inspection.source_checksum:
            print(f"  Source SHA-256: {inspection.source_checksum}")
        if inspection.source_path:
            print(f"  Source path:    {inspection.source_path}")
        if inspection.state_path:
            print(f"  State sidecar:  {inspection.state_path}")
        if inspection.runtime_modelfile:
            print(f"  Runtime file:   {inspection.runtime_modelfile}")
    print()


def all_available_models(
    catalogs: list[tuple[dict, list[dict]]], *, command: str, include_disabled: bool
) -> list[dict]:
    available: list[dict] = []
    for defaults, models in catalogs:
        category = defaults["category"]
        if category == "mtp" and command in {"apply", "refresh", "unregister"}:
            # MTP is never part of generic all-category convergence. Preparing an
            # MTP candidate must be an explicit mtp-category operation so normal
            # appliance setup cannot acquire experimental llama.cpp artifacts.
            continue
        if category == "mtp" and command == "status" and not include_disabled:
            available.extend(model for model in models if model["enabled"])
        else:
            available.extend(models)
    return available


def confirm_removal(
    groups: list[tuple[dict, list[dict]]], selected: list[dict], args: argparse.Namespace
) -> bool:
    if args.yes:
        return True
    show_removal_plan(groups, args)
    names = ", ".join(model.get("name", model["id"]) for model in selected)
    verb = "Unregister" if args.command == "unregister" else "Remove"
    if prompt_line(f"{verb} {names}? [y/N] ").lower() not in {"y", "yes"}:
        print(f"{verb} cancelled.")
        return False
    return True


def run_all_catalog_operation(
    catalogs: list[tuple[dict, list[dict]]],
    selected: list[dict],
    args: argparse.Namespace,
) -> int:
    # Source overrides are deliberately a one-model operation. Enforce that
    # invariant before the combined catalog is split into per-category groups.
    if (
        args.command in {"apply", "refresh"}
        and len(selected) != 1
        and (getattr(args, "revision", None) is not None or getattr(args, "sha256", None) is not None)
    ):
        raise ModelError("--revision and --sha256 require one selected model")

    selected_ids = {(model["category"], model["id"]) for model in selected}
    if (
        args.command in {"apply", "refresh"}
        and os.environ.get("BC250_MODELCTL_SELECTION_SUMMARY") == "1"
    ):
        print("Selected models:")
        for model in selected:
            print(f"  {model.get('name', model['id'])}")
        print(f"\nProcessing {len(selected)} selected model(s)...")

    groups: dict[str, tuple[dict, list[dict]]] = {}
    for defaults, models in catalogs:
        chosen = [
            model
            for model in models
            if (model["category"], model["id"]) in selected_ids
        ]
        if chosen:
            groups[defaults["category"]] = (defaults, chosen)

    if args.command in {"unregister", "remove"}:
        if not confirm_removal(list(groups.values()), selected, args):
            return 0
        args = argparse.Namespace(**vars(args))
        args.yes = True

    status = 0
    normal_selected = any(category in groups for category in NORMAL_CATEGORIES)
    agent_selected = "agentic" in groups

    if normal_selected:
        set_appliance_mode("normal")
        for category in NORMAL_CATEGORIES:
            group = groups.get(category)
            if group:
                status = max(status, operate_models(*group, args))

    if agent_selected:
        quiet_mode = (
            getattr(args, "quiet", False)
            or os.environ.get("BC250_MODELCTL_SUPPRESS_MODE_OUTPUT") == "1"
        )
        if quiet_mode:
            print("Switching temporarily to exclusive agent mode for agent model management.")
        set_appliance_mode("agent")
        try:
            status = max(status, operate_models(*groups["agentic"], args))
        finally:
            set_appliance_mode("normal")
            if quiet_mode:
                print("Normal mode restored after agent model management.")

    if "mtp" in groups:
        status = max(status, operate_models(*groups["mtp"], args))
    return status


def run_category_operation(
    defaults: dict, selected: list[dict], args: argparse.Namespace
) -> int:
    if args.command in {"unregister", "remove"}:
        if not confirm_removal([(defaults, selected)], selected, args):
            return 0
        args = argparse.Namespace(**vars(args))
        args.yes = True

    category = defaults["category"]
    if category == "mtp" and args.command == "unregister":
        raise ModelError("MTP models are download-only and cannot be unregistered; use 'remove'")
    if category == "mtp" or getattr(args, "host", None):
        return operate_models(defaults, selected, args)
    if category in NORMAL_CATEGORIES:
        set_appliance_mode("normal")
        return operate_models(defaults, selected, args)
    if category == "agentic":
        set_appliance_mode("agent")
        try:
            return operate_models(defaults, selected, args)
        finally:
            set_appliance_mode("normal")
    return operate_models(defaults, selected, args)


def resolve_one_model(
    category: str,
    model_id: str,
    *,
    directories: list[Path] | None,
    source: Path | None,
) -> tuple[dict, dict]:
    if category == "all":
        for defaults, models in load_all_catalogs(directories=directories, source=source):
            for model in models:
                if model["id"] == model_id:
                    return defaults, model
        raise ModelError(f"model id not found: {model_id}")
    defaults, models = load_models(category, directories=directories, source=source)
    for model in models:
        if model["id"] == model_id:
            return defaults, model
    raise ModelError(f"model id not found: {model_id}")


def selected_models_for_catalog(
    models: list[dict], selection: str | None, *, interactive: bool
) -> list[dict]:
    if not models:
        return []
    if selection is None and not interactive:
        return models
    if selection is None:
        selection = prompt_line(
            "Models (id/index/range/recommended/production/all; Enter to cancel): "
        )
    if not selection:
        return []
    return select_models(models, selection)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(line_buffering=True)

    values = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not values:
        parser.print_help()
        return 0
    if hint := legacy_cli_hint(values):
        raise ModelError(hint)

    args = parser.parse_args(values)
    if args.command is None:
        parser.print_help()
        return 0
    require_privilege(args.command)
    if getattr(args, "quiet", False):
        os.environ["BC250_MODELCTL_SUPPRESS_MODE_OUTPUT"] = "1"
        os.environ["BC250_MODELCTL_SUPPRESS_CATALOG"] = "1"
    args.hf_session = {"resolved": False, "token": ""}

    if args.command == "purge-retired":
        return purge_retired(yes=args.yes)

    source = args.source or (
        Path(os.environ["SOURCE_FILE"]) if os.environ.get("SOURCE_FILE") else None
    )
    directories = args.modelfile_dir

    if args.command == "list":
        category = args.category or "all"
        if category == "all":
            catalogs = load_all_catalogs(directories=directories, source=source)
            print_catalogs_basic(catalogs, include_disabled_mtp=args.all)
            return 0
        defaults, models = load_models(category, directories=directories, source=source)
        available = (
            models
            if category != "mtp" or args.all
            else [model for model in models if model["enabled"]]
        )
        if category == "mtp" and not available:
            print("MTP models: no enabled models; use --all to include disabled opt-in models.")
            return 0
        print(f"{'MTP' if category == 'mtp' else category.title()} models:")
        print_catalog_models(available)
        return 0

    if args.command == "path":
        if args.category is None:
            raise category_required("path")
        if not args.id:
            raise ModelError(
                "path: model id is required. Example: bc250-model path agentic MODEL"
            )
        defaults, model = resolve_one_model(
            canonical_category(args.category),
            args.id,
            directories=directories,
            source=source,
        )
        resolved = (
            model["from"]
            if model["provider"] == "ollama-hf"
            else model_path(defaults, model)
        )
        print(f"{resolved}\t{model.get('context', '')}\t{model.get('draft', '')}")
        return 0

    if args.command == "status":
        category = args.category or "all"
        token = status_token(args.token_file) if args.online else ""
        if category == "all":
            catalogs = load_all_catalogs(directories=directories, source=source)
            available = all_available_models(
                catalogs,
                command="status",
                include_disabled=args.include_disabled,
            )
            selected = selected_models_for_catalog(
                available, args.selection, interactive=False
            )
            selected_ids = {(model["category"], model["id"]) for model in selected}
            registrations: dict[str, set[str] | None] = {}
            for defaults, models in catalogs:
                host = defaults.get("ollama_host")
                if host and host not in registrations:
                    registrations[host] = registered_models(host)
                category_models = [
                    model
                    for model in models
                    if (model["category"], model["id"]) in selected_ids
                ]
                if args.compact and category_models:
                    category = defaults["category"]
                    print(f"{'MTP' if category == 'mtp' else category.title()} models:")
                for model in category_models:
                    inspection = inspect_model_state(
                        defaults,
                        model,
                        registrations=registrations.get(host) if host else None,
                        online=args.online,
                        token=token,
                    )
                    if args.compact:
                        print_model_inspection_compact(inspection)
                    else:
                        print_model_inspection(inspection, verbose=args.verbose)
            return 0

        defaults, models = load_models(category, directories=directories, source=source)
        available = (
            models
            if category != "mtp" or args.include_disabled
            else [model for model in models if model["enabled"]]
        )
        selected = selected_models_for_catalog(
            available, args.selection, interactive=False
        )
        host = defaults.get("ollama_host")
        registrations = registered_models(host) if host else None
        if args.compact and selected:
            print(f"{'MTP' if category == 'mtp' else category.title()} models:")
        for model in selected:
            inspection = inspect_model_state(
                defaults,
                model,
                registrations=registrations,
                online=args.online,
                token=token,
            )
            if args.compact:
                print_model_inspection_compact(inspection)
            else:
                print_model_inspection(inspection, verbose=args.verbose)
        return 0

    if args.category is None:
        raise category_required(args.command)
    category = canonical_category(args.category)
    if category == "all":
        catalogs = load_all_catalogs(directories=directories, source=source)
        available = all_available_models(
            catalogs,
            command=args.command,
            include_disabled=getattr(args, "include_disabled", False),
        )
        suppress_catalog = (
            getattr(args, "quiet", False)
            or os.environ.get("BC250_MODELCTL_SUPPRESS_CATALOG") == "1"
        )
        if not suppress_catalog:
            print("Available models:")
            print_catalogs_basic(
                catalogs,
                include_disabled_mtp=(args.command == "remove"),
            )
        selected = selected_models_for_catalog(
            available, args.selection, interactive=True
        )
        if not selected:
            print("No models selected.")
            return 0
        return run_all_catalog_operation(catalogs, selected, args)

    defaults, models = load_models(category, directories=directories, source=source)
    available = models
    if category == "mtp":
        if args.command == "unregister":
            raise ModelError(
                "MTP models are download-only and cannot be unregistered; use 'remove'"
            )
        if args.command in {"apply", "refresh"} and not args.include_disabled:
            available = [model for model in models if model["enabled"]]
    suppress_catalog = (
        getattr(args, "quiet", False)
        or os.environ.get("BC250_MODELCTL_SUPPRESS_CATALOG") == "1"
    )
    if not suppress_catalog:
        print(f"Available {category} models:")
        print_catalog_models(available)
    selected = selected_models_for_catalog(available, args.selection, interactive=True)
    if not selected:
        print("No models selected.")
        return 0
    return run_category_operation(defaults, selected, args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ModelError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
