#!/usr/bin/env python3
"""Manage BC-250 model catalog, verified local sources and runtime registrations."""

from __future__ import annotations

import argparse
import errno
import getpass
import grp
import hashlib
import importlib.util
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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import tomllib


def _load_shared_model_contract_module():
    """Load the shared package contract validator in source and installed layouts."""
    candidates = (
        Path(__file__).resolve().with_name("model_contract.py"),
        Path(__file__).resolve().parents[1] / "cmd" / "model_contract.py",
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        spec = importlib.util.spec_from_file_location("bc250_model_contract_shared", candidate)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    raise RuntimeError("shared model_contract.py is missing")


_SHARED_MODEL_CONTRACT = _load_shared_model_contract_module()

PROJECT = "bc250-llm-server"
INSTALLED_SHARE = Path(f"/usr/share/{PROJECT}/model-management")
INSTALLED_CONFIG = Path(f"/etc/{PROJECT}")
PACKAGED_MODEL_DIR = INSTALLED_SHARE / "modelfiles"
OPERATOR_MODEL_DIR = INSTALLED_CONFIG / "models.d"
RETIRED_CATALOG = INSTALLED_SHARE / "retired-models.json"
MODEL_CATALOG = INSTALLED_SHARE / "model-catalog.json"
MODEL_PROFILES = INSTALLED_SHARE / "model-profiles.json"

OLLAMA_CATEGORIES = ("production", "experiments", "task", "agentic", "embedding")
NORMAL_CATEGORIES = ("production", "experiments", "task", "embedding")
OPTIONAL_CATEGORIES = frozenset({"experiments", "agentic"})
OPTIONAL_MODEL_NAMES = frozenset({
    "embed-qwen3-0.6b-q8-0",
})
CATEGORIES = (*OLLAMA_CATEGORIES, "mtp", "all")
MTP_RECOMMENDATIONS = {"primary", "alternative"}
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
    command = os.environ.get("BC250_DISPATCHER") or shutil.which("bc250")
    if not command:
        raise ModelError("bc250 dispatcher is required for package-managed model registration")
    action = "leave" if mode == "normal" else "enter"
    result = subprocess.run(
        [command, "advanced", "agent", action],
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


def modelfile_category(value: str, *, allow_persistent_legacy: bool = False) -> str:
    if allow_persistent_legacy and value == "experimental":
        return "experiments"
    if value not in OLLAMA_CATEGORIES:
        raise ModelError(f"unsupported Modelfile category: {value}")
    return value


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



def model_catalog_path() -> Path:
    source_root = local_source_root()
    local = source_root / "model-catalog.json" if source_root else None
    return local if local and local.is_file() else MODEL_CATALOG


def model_profiles_path() -> Path:
    source_root = local_source_root()
    local = source_root / "model-profiles.json" if source_root else None
    return local if local and local.is_file() else MODEL_PROFILES


def _load_json_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelError(f"could not read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise ModelError(f"invalid {label}: {path}")
    return value


def load_model_profiles(path: Path | None = None) -> dict[str, dict]:
    source = path or model_profiles_path()
    document = _load_json_object(source, "model profiles")
    try:
        catalog = load_model_catalog()
        return _SHARED_MODEL_CONTRACT.validate_model_profiles_document(
            document, source=source, catalog=catalog
        )
    except _SHARED_MODEL_CONTRACT.ModelContractError as error:
        raise ModelError(str(error)) from error


def recommended_model_ids() -> frozenset[str]:
    return frozenset(
        model_id
        for model_id, profile in load_model_profiles().items()
        if profile.get("recommended") is True
    )


def _validate_string_list(value, *, path: Path, model_id: str, field: str) -> list[str]:
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ModelError(f"{path}: {model_id}: {field} must be a non-empty string list")
    return list(value)


def load_model_catalog(path: Path | None = None) -> dict[str, dict]:
    source = path or model_catalog_path()
    document = _load_json_object(source, "model catalog")
    try:
        return _SHARED_MODEL_CONTRACT.validate_model_catalog_document(
            document, source=source
        )
    except _SHARED_MODEL_CONTRACT.ModelContractError as error:
        raise ModelError(str(error)) from error


def _catalog_for_model_directory(directory: Path) -> Path | None:
    local = directory.parent / "model-catalog.json"
    if local.is_file():
        return local
    if directory == PACKAGED_MODEL_DIR and MODEL_CATALOG.is_file():
        return MODEL_CATALOG
    return None


def _runtime_template_metadata(path: Path) -> tuple[str, str]:
    category = ""
    name = ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ModelError(f"cannot read Modelfile {path}: {error}") from error
    for line in lines:
        if line.startswith("# BC250 category: "):
            category = line.removeprefix("# BC250 category: ").strip()
        elif line.startswith("# Ollama model: "):
            name = line.removeprefix("# Ollama model: ").strip()
    return category, name


def load_packaged_model(path: Path, model_id: str, entry: dict) -> dict:
    if path.name != f"{model_id}.Modelfile" or not path.is_file():
        raise ModelError(f"missing runtime Modelfile template for {model_id}: {path}")
    text = path.read_text(encoding="utf-8")
    category_marker, name_marker = _runtime_template_metadata(path)
    category = entry["category"]
    if modelfile_category(category_marker) != category or name_marker != model_id:
        raise ModelError(f"{path}: runtime template identity does not match model catalog")
    if any(line.startswith(("# Source: ", "# GGUF: ", "# SHA256: ")) for line in text.splitlines()):
        raise ModelError(f"{path}: acquisition metadata belongs in model-catalog.json")
    if text.splitlines().count("FROM __BC250_SOURCE__") != 1:
        raise ModelError(f"{path}: expected exactly one 'FROM __BC250_SOURCE__' line")
    required_parameters = ["PARAMETER num_gpu 99"]
    if category != "embedding":
        required_parameters.append("PARAMETER num_keep 256")
    for parameter in required_parameters:
        if len(re.findall(rf"^{re.escape(parameter)}$", text, re.MULTILINE)) != 1:
            raise ModelError(f"{path}: expected exactly one {parameter!r}")

    source = entry["source"]
    provider = entry["provider"]
    runtime_from = source.get("local_path") if provider == "ollama" else source.get("provider_ref")
    return {
        "enabled": entry["enabled"],
        "provider": provider,
        "category": category,
        "id": model_id,
        "name": model_id,
        "repository": source["repository"],
        "revision": source["revision"],
        "gguf": source["filename"],
        "sha256": source.get("expected_sha256", ""),
        "from": runtime_from,
        "modelfile": entry["runtime"]["modelfile"],
        "template": path,
        "origin": "packaged",
        "catalog": entry,
        "ownership": entry["ownership"],
        "capabilities": entry["capabilities"],
        "runtime_metadata": entry["runtime"],
        "native_context_max": entry.get("native_context_max"),
        "source_metadata": source,
    }


def load_packaged_models(directory: Path, catalog_path: Path) -> list[dict]:
    catalog = load_model_catalog(catalog_path)
    models = []
    for model_id, entry in catalog.items():
        models.append(
            load_packaged_model(directory / entry["runtime"]["modelfile"], model_id, entry)
        )
    templates = {
        path.stem
        for path in directory.glob("*.Modelfile")
        if path.name != "MODEL-TEMPLATE.Modelfile.example"
    }
    missing_catalog = templates - set(catalog)
    if missing_catalog:
        raise ModelError(
            f"{catalog_path}: runtime template(s) missing catalog entries: {', '.join(sorted(missing_catalog))}"
        )
    return models


def _operator_metadata_defaults(model: dict, previous: dict | None) -> dict:
    if previous:
        for field in ("capabilities", "native_context_max"):
            if field in previous:
                model[field] = previous[field]
    if "capabilities" not in model:
        model["capabilities"] = {
            "modalities": ["text"],
            "features": ["text-generation"],
            "reasoning": "candidate",
            "ocr": False,
            "tools": model["category"] == "agentic",
            "benchmark_kinds": ["generation"] + (["agent"] if model["category"] == "agentic" else []),
        }
    model["ownership"] = {
        "source": "bc250" if model["provider"] == "ollama" else "ollama",
        "registration": "bc250",
        "state": "bc250" if model["provider"] == "ollama" else "provider",
    }
    model["runtime_metadata"] = {
        "lane": {"production": "main", "experiments": "main", "task": "task", "agentic": "agent", "embedding": "embedding"}[model["category"]],
        "modelfile": model["modelfile"],
        "agent_prepare_required": model["category"] == "agentic",
    }
    model["source_metadata"] = {
        "repository": model["repository"],
        "revision": model["revision"],
        "filename": model["gguf"],
        "expected_sha256": model.get("sha256", ""),
        "policy": "pinned" if re.fullmatch(r"[0-9a-f]{40}", model["revision"]) else "tracking",
        "reproducibility": "operator-defined",
    }
    return model


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
    category = modelfile_category(
        metadata["category"],
        allow_persistent_legacy=OPERATOR_MODEL_DIR in path.parents,
    )
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


def validate_operator_model_directory(directory: Path) -> None:
    """Reject visible regular files that the operator overlay would ignore."""
    if directory != OPERATOR_MODEL_DIR or not directory.is_dir():
        return
    invalid = [
        path.name
        for path in sorted(directory.iterdir())
        if path.is_file() and not path.name.startswith(".") and path.suffix != ".Modelfile"
    ]
    if invalid:
        names = ", ".join(invalid)
        raise ModelError(
            f"invalid operator model definition(s) in {directory}: {names}\n"
            "Files in models.d must end in .Modelfile.\n"
            "Operator-owned files are not modified automatically. Move, rename, or "
            "remove the listed file(s), then rerun: sudo bc250 install"
        )


def load_operator_model(path: Path, previous: dict | None) -> dict:
    text = path.read_text(encoding="utf-8")
    if previous is not None and "FROM __BC250_SOURCE__" in text and "# Source: " not in text:
        category_marker, name_marker = _runtime_template_metadata(path)
        if modelfile_category(category_marker) != previous["category"] or name_marker != previous["id"]:
            raise ModelError(f"{path}: runtime override identity does not match packaged model")
        required_parameters = ["PARAMETER num_gpu 99"]
        if previous["category"] != "embedding":
            required_parameters.append("PARAMETER num_keep 256")
        for parameter in required_parameters:
            if len(re.findall(rf"^{re.escape(parameter)}$", text, re.MULTILINE)) != 1:
                raise ModelError(f"{path}: expected exactly one {parameter!r}")
        model = dict(previous)
        model["template"] = path
        model["origin"] = "operator"
        model["runtime_metadata"] = dict(previous.get("runtime_metadata") or {})
        model["runtime_metadata"]["modelfile"] = path.name
        return model
    return _operator_metadata_defaults(load_modelfile(path), previous)


def discover_models(directories: list[Path]) -> list[dict]:
    # Package models are defined by model-catalog.json plus runtime-only
    # Modelfile templates. Later operator directories retain the historical
    # self-contained Modelfile format and override a same-named package entry.
    discovered: dict[str, dict] = {}
    found_directory = False
    for directory in directories:
        if not directory.is_dir():
            continue
        found_directory = True
        validate_operator_model_directory(directory)
        catalog_path = _catalog_for_model_directory(directory)
        if catalog_path is not None:
            incoming = load_packaged_models(directory, catalog_path)
        else:
            incoming = [(path, discovered.get(path.stem)) for path in sorted(directory.glob("*.Modelfile"))]
        if catalog_path is None:
            incoming = [load_operator_model(path, previous) for path, previous in incoming]
        for model in incoming:
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
        role = require_string(model, "role", context)
        if re.fullmatch(r"[a-z0-9][a-z0-9-]*", role) is None:
            raise ModelError(f"{context}: role must be a lowercase token")
        recommendation = require_string(model, "recommendation", context)
        if recommendation not in MTP_RECOMMENDATIONS:
            allowed = ", ".join(sorted(MTP_RECOMMENDATIONS))
            raise ModelError(f"{context}: recommendation must be one of: {allowed}")
        if model.get("source_policy") not in {"tracking", "pinned"}:
            raise ModelError(f"{context}: source_policy must be tracking or pinned")
        require_string(model, "reproducibility", context)
        for field, allowed_values in {
            "source_owner": {"bc250"},
            "registration_owner": {"none"},
            "state_owner": {"bc250"},
            "runtime_lane": {"llamacpp-mtp"},
            "reasoning_capability": {"verified", "candidate", "unsupported"},
        }.items():
            if model.get(field) not in allowed_values:
                raise ModelError(f"{context}: invalid {field}")
        _validate_string_list(model.get("modalities"), path=path, model_id=model_id, field="modalities")
        _validate_string_list(model.get("features"), path=path, model_id=model_id, field="features")
        _validate_string_list(model.get("benchmark_kinds"), path=path, model_id=model_id, field="benchmark_kinds")
        for field in ("ocr", "tools"):
            if not isinstance(model.get(field), bool):
                raise ModelError(f"{context}: {field} must be boolean")
        checksum = model.get("sha256", "")
        if not isinstance(checksum, str) or (
            checksum and re.fullmatch(r"[0-9a-f]{64}", checksum) is None
        ):
            raise ModelError(f"{context}: invalid SHA256")
        model["source_metadata"] = {
            "repository": model["repository"],
            "revision": model["revision"],
            "filename": model["gguf"],
            "expected_sha256": checksum,
            "policy": model["source_policy"],
            "reproducibility": model["reproducibility"],
        }
        model["ownership"] = {
            "source": model["source_owner"],
            "registration": model["registration_owner"],
            "state": model["state_owner"],
        }
        model["runtime_metadata"] = {
            "lane": model["runtime_lane"],
            "modelfile": None,
            "agent_prepare_required": False,
        }
        model["capabilities"] = {
            "modalities": list(model["modalities"]),
            "features": list(model["features"]),
            "reasoning": model["reasoning_capability"],
            "ocr": model["ocr"],
            "tools": model["tools"],
            "benchmark_kinds": list(model["benchmark_kinds"]),
        }
        model["native_context_max"] = None
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
        # every bc250 model view. Keep the same MTP index whether the operator
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


def select_models(
    models: list[dict],
    selection: str,
    *,
    group_excluded_categories: frozenset[str] = frozenset(),
) -> list[dict]:
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
            choices = [
                model["id"]
                for model in models
                if model.get("category") not in group_excluded_categories
            ]
        elif special == "production":
            choices = [
                model["id"]
                for model in models
                if model.get("category") == "production"
                and model.get("category") not in group_excluded_categories
            ]
        elif special == "recommended":
            choices = [
                model["id"]
                for model in models
                if model["id"] in recommended_model_ids()
                and model.get("category") not in group_excluded_categories
            ]
        else:
            # Exact IDs, indexes and numeric ranges are explicit selections. In
            # the interactive installer they may therefore include standalone
            # MTP entries even though broad groups intentionally cannot.
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


def registered_models_by_host(hosts: list[str] | set[str] | tuple[str, ...]) -> dict[str, set[str] | None]:
    """Probe distinct Ollama hosts concurrently; probes are read-only and independently bounded."""
    ordered = list(dict.fromkeys(hosts))
    if not ordered:
        return {}
    with ThreadPoolExecutor(max_workers=min(4, len(ordered))) as pool:
        values = list(pool.map(registered_models, ordered))
    return dict(zip(ordered, values, strict=True))


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
        source = Path(item["source"])
        runtime = Path(item["runtime_modelfile"])
        source_root = Path(CATEGORY_DEFAULTS[category]["destination"])
        runtime_root = Path(CATEGORY_DEFAULTS[category]["modelfile_destination"])
        if not source.is_absolute() or not source.is_relative_to(source_root):
            raise ModelError(f"retired model source is outside manager-owned storage: {source}")
        if not runtime.is_absolute() or not runtime.is_relative_to(runtime_root):
            raise ModelError(f"retired runtime Modelfile is outside manager-owned storage: {runtime}")
        if item["ollama_host"] != CATEGORY_DEFAULTS[category]["ollama_host"]:
            raise ModelError(f"retired model host/category mismatch: {item['name']}")
        normalized = dict(item)
        normalized["category"] = category
        result.append(normalized)
    return result


def retired_present(item: dict, registrations: dict[str, set[str] | None]) -> bool:
    source = Path(item["source"])
    runtime = Path(item["runtime_modelfile"])
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
    registrations = registered_models_by_host(hosts)
    present = [item for item in retired if retired_present(item, registrations)]
    if not present:
        print("No retired package-managed models are present.")
        return 0
    print("Retired package-managed models:")
    total = 0
    for index, item in enumerate(present, 1):
        source = Path(item["source"])
        size = source.stat().st_size if source.is_file() else 0
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
        name = item["name"]
        host = item["ollama_host"]
        source = Path(item["source"])
        runtime = Path(item["runtime_modelfile"])
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
            failures.append(name)
            continue
        if names is None:
            print("    ERROR: expected Ollama registration state unavailable; local data retained", file=sys.stderr)
            failures.append(name)
            continue
        if name in names:
            if not ollama_bin:
                print("    ERROR: ollama executable unavailable; local data retained", file=sys.stderr)
                failures.append(name)
                continue
            result = run_as_ollama(
                [ollama_bin, "rm", name],
                {"HOME": "/var/lib/ollama", "OLLAMA_HOST": host},
            )
            if result.returncode != 0:
                print("    ERROR: registration removal failed; local data retained", file=sys.stderr)
                failures.append(name)
                continue
            print(f"    removed Ollama registration from {host}")
        for path in (runtime, source, state_path(source)):
            if path.exists():
                path.unlink()
                print(f"    removed {path}")
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
    registrations = registered_models_by_host(hosts)
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
            print(f"    - {name:<56} [{host}, set up, retired purge eligible]")
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
    registrations = registered_models_by_host(
        [
            defaults["ollama_host"]
            for defaults, _models in catalogs
            if defaults.get("ollama_host")
        ]
    )
    for defaults, models in catalogs:
        category = defaults["category"]
        available = (
            models
            if category != "mtp" or include_disabled_mtp
            else [model for model in models if model["enabled"]]
        )
        label = (
            "Testing"
            if category == "experiments"
            else ("MTP" if category == "mtp" else category.title())
        )
        print(f"{label} models:")
        host = defaults.get("ollama_host")
        print_models(defaults, available, registrations.get(host) if host else None)


def state_path(output: Path) -> Path:
    return output.with_name(f"{output.name}.bc250.json")


def load_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict) or value.get("schema") not in {1, 2, 3, 4}:
        return {}
    return value


def state_matches(state: dict, model: dict, output: Path) -> bool:
    """Compatibility helper backed by the canonical source-state inspector."""
    return inspect_local_source(state, model, output)[0] == "current"


def source_policy(model: dict) -> str:
    """Return the catalog/operator source policy for one model."""
    configured = (model.get("source_metadata") or {}).get("policy")
    if configured in {"tracking", "pinned"}:
        return str(configured)
    if model.get("sha256"):
        return "pinned"
    return "pinned" if re.fullmatch(r"[0-9a-f]{40}", str(model.get("revision", ""))) else "tracking"


def inspect_local_source(state: dict, model: dict, output: Path) -> tuple[str, str, str]:
    """Return (status, detail, checksum) for one manager-owned GGUF.

    Tracking sources deliberately treat an existing validated artifact as current
    until explicit refresh. A catalog ref change such as commit -> latest/main is
    therefore metadata migration, not source drift. Pinned sources still require
    exact catalog provenance and digest agreement.
    """
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

    recorded = str(state.get("acquired_sha256") or state.get("sha256", ""))
    expected = str(model.get("sha256", ""))
    policy = source_policy(model)

    changed = [
        key
        for key in ("repository", "gguf")
        if state.get(key) != model.get(key)
    ]
    if policy == "pinned":
        state_ref = state.get("configured_ref", state.get("revision"))
        if state_ref != model.get("revision"):
            changed.append("revision")
    if changed:
        return "drift", f"state provenance differs: {', '.join(changed)}", recorded
    if re.fullmatch(r"[0-9a-f]{64}", recorded) is None:
        return "drift", "state sidecar has no valid SHA-256", ""
    if policy == "pinned" and expected and recorded != expected:
        return "drift", "recorded SHA-256 differs from current catalog pin", recorded

    configured_ref = str(model.get("revision", ""))
    acquired_ref = str(
        state.get("resolved_revision")
        or state.get("revision")
        or state.get("configured_ref")
        or ""
    )
    tracking_migration = (
        policy == "tracking"
        and acquired_ref
        and acquired_ref != configured_ref
    )
    detail = "verified by recorded file identity"
    if tracking_migration:
        detail = (
            f"verified tracking artifact acquired from {acquired_ref}; "
            f"configured ref is {configured_ref}; refresh required to advance"
        )

    if (
        state.get("schema") in {2, 3, 4}
        and state.get("size") == stat_result.st_size
        and state.get("mtime_ns") == stat_result.st_mtime_ns
        and state.get("ctime_ns") == stat_result.st_ctime_ns
    ):
        return "current", detail, recorded

    try:
        actual = sha256(output)
    except OSError as error:
        return "unavailable", f"cannot hash GGUF: {error}", recorded
    if actual != recorded:
        return "drift", "GGUF content differs from recorded SHA-256", recorded
    if tracking_migration:
        return "current", detail, recorded
    return "current", "verified by SHA-256", recorded


def rendered_modelfile_content(source: Path, model: dict, output: Path | None) -> str:
    """Render the runtime Modelfile without mutating the filesystem."""
    rendered: list[str] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith("# Source: "):
            line = f"# Source: {model['repository']} @ {model['revision']}"
        elif line.startswith("# GGUF: "):
            line = f"# GGUF: {model['gguf']}"
        elif line.startswith("FROM "):
            if output is not None:
                line = f"FROM {output}"
            elif line == "FROM __BC250_SOURCE__":
                line = f"FROM {model['from']}"
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


def read_protected_token_file(token_file: Path) -> str:
    """Read an explicitly supplied Hugging Face token only from a private file."""
    if token_file.is_symlink():
        raise ModelError(f"token file must not be a symlink: {token_file}")
    try:
        info = token_file.stat()
    except OSError as error:
        raise ModelError(f"cannot stat token file {token_file}: {error}") from error
    if not stat.S_ISREG(info.st_mode):
        raise ModelError(f"token file must be a regular file: {token_file}")
    if info.st_mode & 0o077:
        raise ModelError(
            f"token file must not be group/world accessible: {token_file} "
            f"(mode {stat.S_IMODE(info.st_mode):04o})"
        )
    try:
        token = token_file.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ModelError(f"cannot read token file {token_file}: {error}") from error
    if not token:
        raise ModelError(f"token file is empty: {token_file}")
    return token


def status_token(token_file: Path | None) -> str:
    if token_file:
        return read_protected_token_file(token_file)
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
    optional_unselected = (
        (
            model.get("category") in OPTIONAL_CATEGORIES
            or model.get("name") in OPTIONAL_MODEL_NAMES
        )
        and modelfile_status == "missing"
        and registration_status in {"missing", "unavailable"}
    )
    if optional_unselected:
        # A cached optional source is not desired active state by itself.  Only a
        # runtime Modelfile/registration makes an optional model selected.
        overall = "OPTIONAL"
    elif source_status == "missing":
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
        current_source_policy = source_policy(model)
        if current_source_policy == "pinned":
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


def write_state(
    path: Path,
    model: dict,
    checksum: str,
    gid: int,
    *,
    preserve_acquisition: bool = False,
) -> None:
    """Write verified local-source state without advancing tracking refs implicitly."""
    stat_result = path.with_name(path.name.removesuffix(".bc250.json")).stat()
    existing = load_state(path)
    policy = source_policy(model)
    configured_ref = str(model.get("revision", ""))

    resolved_revision = None
    legacy_revision = str(existing.get("resolved_revision") or existing.get("revision") or "")
    if preserve_acquisition and policy == "tracking" and legacy_revision:
        if existing.get("repository") == model.get("repository") and existing.get("gguf") == model.get("gguf"):
            resolved_revision = legacy_revision
    elif policy == "pinned" and re.fullmatch(r"[0-9a-f]{40}", configured_ref):
        resolved_revision = configured_ref

    # Keep the legacy revision field meaningful for older tooling while schema 4
    # separates the configured moving ref from the exact acquired byte identity.
    legacy_state_revision = resolved_revision or configured_ref
    value = {
        "schema": 4,
        "model_name": model.get("name", model["id"]),
        "model_id": model["id"],
        "category": model.get("category", ""),
        "repository": model["repository"],
        "revision": legacy_state_revision,
        "configured_ref": configured_ref,
        "resolved_revision": resolved_revision,
        "source_policy": policy,
        "gguf": model["gguf"],
        "sha256": checksum,
        "acquired_sha256": checksum,
        "size": stat_result.st_size,
        "mtime_ns": stat_result.st_mtime_ns,
        "ctime_ns": stat_result.st_ctime_ns,
    }
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
            "ollama user or group is missing; run sudo bc250 install"
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
    if (
        os.environ.get("BC250_INSTALL_TRANSCRIPT") == "1"
        and len(command) > 1
        and Path(command[0]).name == "ollama"
        and command[1] == "create"
    ):
        # The installer itself owns a PTY for interactive prompts and transcript
        # capture. Pipe `ollama create` through Python so Ollama emits plain
        # non-interactive progress instead of terminal spinner escape sequences.
        child_environment.setdefault("NO_COLOR", "1")
        process = subprocess.Popen(
            argv,
            env=child_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
        return subprocess.CompletedProcess(argv, process.wait())
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
        token = read_protected_token_file(token_file)
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
                    state.get("schema") != 4
                    or state.get("configured_ref") != model.get("revision")
                    or state.get("source_policy") != source_policy(model)
                    or state.get("acquired_sha256") != checksum
                    or state.get("size") != current.st_size
                    or state.get("mtime_ns") != current.st_mtime_ns
                    or state.get("ctime_ns") != current.st_ctime_ns
                    or permissions_changed
                )
                if source_metadata_changed:
                    write_state(
                        metadata, model, checksum, gid, preserve_acquisition=True
                    )
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

    all_current = (
        summarize_current
        and current_skipped == len(models)
        and not failures
    )
    if summarize_current and current_skipped:
        category = str(defaults.get("category", "models"))
        title = "MTP" if category == "mtp" else category.title()
        if all_current:
            print(f"{title}: {current_skipped}/{len(models)} current")
        else:
            print(f"{title}: {current_skipped}/{len(models)} already current.")

    if failures:
        print(f"\nFailed: {' '.join(failures)}", file=sys.stderr)
        return 2
    if all_current:
        return 0
    print(f"\nDone: {len(models)} model(s) processed.")
    return 0


def effective_ownership(model: dict) -> dict[str, str]:
    """Return explicit ownership metadata with safe provider-compatible fallbacks."""
    provider = str(model.get("provider") or "")
    if provider == "download-only":
        fallback = {"source": "bc250", "registration": "none", "state": "bc250"}
    elif provider == "ollama-hf":
        fallback = {"source": "ollama", "registration": "bc250", "state": "provider"}
    else:
        fallback = {"source": "bc250", "registration": "bc250", "state": "bc250"}
    ownership = model.get("ownership")
    if not isinstance(ownership, dict):
        return fallback
    return {
        key: str(ownership.get(key) or value)
        for key, value in fallback.items()
    }


def show_removal_plan(
    groups: list[tuple[dict, list[dict]]], args: argparse.Namespace
) -> None:
    """Explain provider/ownership-aware cleanup without relying on filesystem guesses."""
    keep_source = args.command == "unregister"
    title = "Unregister plan:" if keep_source else "Removal plan:"
    print(title)
    for defaults, models in groups:
        host = ollama_host(defaults, getattr(args, "host", None))
        for model in models:
            label = model.get("name", model["id"])
            ownership = effective_ownership(model)
            source_owner = ownership["source"]
            registration_owner = ownership["registration"]
            state_owner = ownership["state"]
            print(f"\n{label}")
            print(
                "  Ownership: "
                f"source={source_owner}, registration={registration_owner}, state={state_owner}"
            )
            if registration_owner == "none" or model["provider"] == "download-only":
                print("  Registration: none")
            else:
                print(f"  Registration: remove through Ollama at {host}")

            output = None
            if source_owner == "bc250":
                output = model_path(defaults, model, getattr(args, "destination", None))
            runtime = runtime_modelfile_path(defaults, model, output)
            if runtime and model["provider"] != "download-only":
                print(f"  Runtime Modelfile: remove {runtime}")

            if source_owner == "bc250":
                try:
                    size = (
                        f" ({output.stat().st_size / 1024**3:.1f} GiB)"
                        if output is not None and output.is_file()
                        else ""
                    )
                except OSError:
                    size = ""
                action = "retain" if keep_source else "remove"
                print(f"  Manager-owned source: {action} {output}{size}")
                print(f"  State sidecar: {action} {state_path(output)}")
            elif source_owner in {"ollama", "provider"}:
                print(
                    "  Provider assets: released via Ollama registration semantics; "
                    "BC-250 never deletes shared blob files directly"
                )
                if keep_source:
                    print("  Source retention: provider-owned; no BC-250 GGUF/state to retain")
            else:
                print("  Source ownership: no package-managed source action")
            print("  Catalog definition: retain")


def _existing_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def remove_models(defaults: dict, models: list[dict], args: argparse.Namespace) -> int:
    """Unregister or fully remove selected state while respecting provider ownership."""
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
    reclaimed_manager_bytes = 0

    for model in models:
        label = model.get("name", model["id"])
        verb = "unregistering" if keep_source else "removing"
        print(f"\n>>> {verb} {label}")
        ownership = effective_ownership(model)
        source_owner = ownership["source"]
        registration_owner = ownership["registration"]

        if registration_owner != "none" and model["provider"].startswith("ollama"):
            if not ollama_bin:
                print(
                    "    ERROR: ollama executable is unavailable; source/state retained",
                    file=sys.stderr,
                )
                failures.append(label)
                continue
            result = run_as_ollama(
                [ollama_bin, "rm", model["name"]],
                {"HOME": "/var/lib/ollama", "OLLAMA_HOST": host},
            )
            registrations = registered_models(host)
            if registrations is not None and model["name"] in registrations:
                print(
                    "    ERROR: Ollama registration remains after removal; source/state retained",
                    file=sys.stderr,
                )
                failures.append(label)
                continue
            if result.returncode != 0 and registrations is None:
                print(
                    "    ERROR: Ollama removal failed and post-state could not be verified; "
                    "source/state retained",
                    file=sys.stderr,
                )
                failures.append(label)
                continue
            if result.returncode != 0:
                print("    registration was already absent; continuing with owned state cleanup")
            else:
                print("    removed Ollama registration")

            # Older/provider-managed installs could leave the temporary hf.co source
            # manifest behind. Remove that registration too, but never manipulate the
            # shared blob graph directly.
            if model["provider"] == "ollama-hf":
                source_registration = str(model.get("from") or "")
                remaining = registered_models(host)
                if source_registration and remaining is not None and source_registration in remaining:
                    source_result = run_as_ollama(
                        [ollama_bin, "rm", source_registration],
                        {"HOME": "/var/lib/ollama", "OLLAMA_HOST": host},
                    )
                    after_source = registered_models(host)
                    if after_source is not None and source_registration in after_source:
                        print(
                            f"    ERROR: temporary provider registration remains: {source_registration}",
                            file=sys.stderr,
                        )
                        failures.append(label)
                        continue
                    if source_result.returncode != 0 and after_source is None:
                        print(
                            f"    ERROR: could not verify removal of provider registration: {source_registration}",
                            file=sys.stderr,
                        )
                        failures.append(label)
                        continue
                    if source_result.returncode != 0:
                        print(f"    provider registration was already absent: {source_registration}")
                    else:
                        print(f"    removed stale provider registration {source_registration}")
                print(
                    "    provider-owned shared blobs remain under Ollama ownership; "
                    "no direct blob deletion attempted"
                )
                if keep_source:
                    print(
                        "    no manager-owned GGUF/state to retain; "
                        "multimodal source/projector blobs are Ollama-managed"
                    )

        output = None
        if source_owner == "bc250":
            output = model_path(defaults, model, getattr(args, "destination", None))
        runtime = runtime_modelfile_path(defaults, model, output)
        paths: list[Path] = []
        if runtime and model["provider"] != "download-only":
            paths.append(runtime)
        if output is not None and not keep_source:
            paths.extend((output, state_path(output)))

        failed_local = False
        for path in paths:
            if not path.exists():
                continue
            size = _existing_size(path)
            try:
                path.unlink()
            except OSError as exc:
                print(f"    ERROR: cannot remove {path}: {exc}", file=sys.stderr)
                failed_local = True
                continue
            if path.exists():
                print(f"    ERROR: path remains after removal: {path}", file=sys.stderr)
                failed_local = True
                continue
            reclaimed_manager_bytes += size
            print(f"    removed {path}")

        if failed_local:
            failures.append(label)
            continue
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
            f"\nUnregistered {removed} model(s). Verified manager-owned GGUF/state "
            "retained where present."
        )
    else:
        print(
            f"\nRemoved {removed} model(s). Catalog definitions were retained; "
            "manager-owned GGUF/state removed where present."
        )
        if reclaimed_manager_bytes:
            print(
                "Manager-owned files removed: "
                f"{reclaimed_manager_bytes / 1024**3:.2f} GiB logical bytes."
            )
    if failures:
        print(f"Failed: {' '.join(failures)}", file=sys.stderr)
        return 2
    return 0


class UsageModelError(ModelError):
    """Command-line usage error; callers should return rc=2."""


class FriendlyArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UsageModelError(message)


CLI_EPILOG = """Common workflows:
  bc250 model list
  sudo bc250 model install
  sudo bc250 model status all --compact
  sudo bc250 model apply all all
  bc250 advanced agent list
  sudo bc250 advanced agent status MODEL
  sudo bc250 advanced agent prepare MODEL
  bc250 advanced mtp list
  sudo bc250 advanced mtp prepare MODEL
  sudo bc250 model purge-retired

Use 'bc250 model COMMAND --help' for command-specific options.
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


def selection_arguments(parser: argparse.ArgumentParser, command: str) -> None:
    if command == "install":
        selection_help = (
            "model id/index/range or comma-separated selection; also recommended, "
            "production or all. Broad groups cover eligible Ollama models only; "
            "standalone MTP requires an explicit id/index/range selection"
        )
    else:
        selection_help = (
            "model id/index/range or comma-separated selection; also recommended, "
            f"production or all. Category 'all' plus selection 'all' selects every "
            f"eligible model for this command: 'bc250 model {command} all all'"
        )
    parser.add_argument("selection", nargs="?", help=selection_help)


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


def apply_arguments(parser: argparse.ArgumentParser, command: str) -> None:
    catalog_arguments(parser, category_optional=True)
    selection_arguments(parser, command)
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


def removal_arguments(parser: argparse.ArgumentParser, command: str) -> None:
    catalog_arguments(parser, category_optional=True)
    selection_arguments(parser, command)
    mutation_common_arguments(parser)
    parser.add_argument(
        "--explain",
        action="store_true",
        help="show provider-aware removal effects without changing model state",
    )
    parser.add_argument("--yes", action="store_true", help="skip confirmation")



def effective_runtime_view(defaults: dict, model: dict) -> dict:
    """Return runtime parameters from the actual package template/rendering path."""
    if model["provider"] == "download-only":
        return {
            "engine": "llama.cpp",
            "context": model.get("context"),
            "draft": model.get("draft"),
        }
    output = None if model["provider"] == "ollama-hf" else model_path(defaults, model)
    content = rendered_modelfile_content(model["template"], model, output)
    parameters: dict[str, str] = {}
    capabilities: list[str] = []
    renderer = None
    parser = None
    runtime_from = None
    for line in content.splitlines():
        if line.startswith("FROM "):
            runtime_from = line.split(maxsplit=1)[1]
        elif line.startswith("PARAMETER "):
            parts = line.split(maxsplit=2)
            if len(parts) == 3:
                parameters[parts[1]] = parts[2]
        elif line.startswith("RENDERER "):
            renderer = line.split(maxsplit=1)[1]
        elif line.startswith("PARSER "):
            parser = line.split(maxsplit=1)[1]
        elif line.startswith("CAPABILITY "):
            capabilities.append(line.split(maxsplit=1)[1])
    return {
        "engine": "ollama",
        "from": runtime_from,
        "parameters": parameters,
        "renderer": renderer,
        "parser": parser,
        "declared_runtime_capabilities": capabilities,
    }


def model_inspect_payload(
    defaults: dict, model: dict, *, effective: bool
) -> dict:
    profiles = load_model_profiles()
    payload = {
        "schema": 1,
        "id": model["id"],
        "category": model["category"],
        "provider": model["provider"],
        "enabled": bool(model.get("enabled", True)),
        "source": dict(model.get("source_metadata") or {}),
        "ownership": dict(model.get("ownership") or {}),
        "runtime": dict(model.get("runtime_metadata") or {}),
        "capabilities": dict(model.get("capabilities") or {}),
        "native_context_max": model.get("native_context_max"),
        "qualification": profiles.get(model["id"]),
        "definition_origin": definition_origin(model),
    }
    if model["provider"] in {"download-only", "ollama"}:
        payload["source"]["resolved_path"] = str(model_path(defaults, model))
    else:
        payload["source"]["resolved_path"] = None

    if effective:
        host = defaults.get("ollama_host")
        registrations = registered_models(host) if host else None
        inspection = inspect_model_state(
            defaults,
            model,
            registrations=registrations,
        )
        payload["runtime"]["effective"] = effective_runtime_view(defaults, model)
        source_record = (
            load_state(inspection.state_path)
            if inspection.state_path and inspection.state_path.is_file()
            else {}
        )
        effective_source_policy = source_record.get("source_policy", source_policy(model))
        effective_configured_ref = source_record.get("configured_ref", model.get("revision"))
        effective_resolved_revision = source_record.get("resolved_revision")
        legacy_revision = source_record.get("revision")
        if (
            effective_resolved_revision is None
            and effective_source_policy == "tracking"
            and isinstance(legacy_revision, str)
            and legacy_revision != effective_configured_ref
        ):
            effective_resolved_revision = legacy_revision
        payload["state"] = {
            "source": inspection.source_status,
            "source_detail": inspection.source_detail,
            "source_sha256": inspection.source_checksum or None,
            "source_policy": effective_source_policy,
            "configured_ref": effective_configured_ref,
            "resolved_revision": effective_resolved_revision,
            "acquired_sha256": source_record.get("acquired_sha256") or inspection.source_checksum or None,
            "runtime_modelfile": inspection.modelfile_status,
            "registration": inspection.registration_status,
            "overall": inspection.overall_status,
            "source_path": str(inspection.source_path) if inspection.source_path else None,
            "state_path": str(inspection.state_path) if inspection.state_path else None,
            "runtime_modelfile_path": (
                str(inspection.runtime_modelfile) if inspection.runtime_modelfile else None
            ),
        }
    return payload


def print_model_inspect_payload(payload: dict) -> None:
    print(f"Model:              {payload['id']}")
    print(f"Category/provider:  {payload['category']} / {payload['provider']}")
    runtime = payload.get("runtime") or {}
    print(f"Runtime lane:       {runtime.get('lane', 'unknown')}")
    capabilities = payload.get("capabilities") or {}
    print(f"Modalities:         {', '.join(capabilities.get('modalities', [])) or 'unknown'}")
    print(f"Reasoning:          {capabilities.get('reasoning', 'unknown')}")
    print(f"Benchmark kinds:    {', '.join(capabilities.get('benchmark_kinds', [])) or 'unknown'}")
    source = payload.get("source") or {}
    print(f"Source:             {source.get('repository', 'unknown')} @ {source.get('revision', 'unknown')}")
    print(f"Source policy:      {source.get('policy', 'unknown')} / {source.get('reproducibility', 'unknown')}")
    ownership = payload.get("ownership") or {}
    print(
        "Ownership:          "
        f"source={ownership.get('source', 'unknown')} "
        f"registration={ownership.get('registration', 'unknown')} "
        f"state={ownership.get('state', 'unknown')}"
    )
    profile = payload.get("qualification") or {}
    if profile:
        print(f"Intended role:      {profile.get('intended_role', 'unknown')}")
        print(f"Comparison role:    {profile.get('comparison_role', 'unknown')}")
        print(f"Qualified context:  {profile.get('qualified_context_target', 'unknown')}")
        print(f"Recommended:        {'yes' if profile.get('recommended') else 'no'}")
    if state := payload.get("state"):
        print(f"Source state:       {state['source']}")
        print(f"Registration:       {state['registration']}")
        print(f"Overall state:      {state['overall']}")


def build_parser() -> argparse.ArgumentParser:
    parser = FriendlyArgumentParser(
        prog="bc250 model",
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
        "--include-disabled", action="store_true", help="include disabled MTP entries"
    )

    status = commands.add_parser(
        "status",
        help="inspect source, provenance, Modelfile and registration state",
    )
    catalog_arguments(status, category_optional=True)
    selection_arguments(status, "status")
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

    inspecting = commands.add_parser(
        "inspect",
        help="show consolidated package metadata for one model",
    )
    inspecting.add_argument("id", help="exact catalog model id")
    inspecting.add_argument(
        "--category",
        choices=CATEGORIES,
        default="all",
        help="optional category constraint; defaults to the combined catalog",
    )
    inspecting.add_argument(
        "--effective",
        action="store_true",
        help="also inspect protected source/registration state and rendered runtime parameters",
    )
    inspecting.add_argument(
        "--json",
        action="store_true",
        help="emit the machine-readable inspect contract",
    )
    inspecting.add_argument("--source", type=Path, help="alternate MTP TOML catalog")
    inspecting.add_argument(
        "--modelfile-dir",
        type=Path,
        action="append",
        help="alternate Modelfile directory; may be repeated",
    )

    path = commands.add_parser(
        "path",
        help="print the resolved source path and MTP context metadata for one model",
    )
    catalog_arguments(path, category_optional=True)
    path.add_argument("id", nargs="?", help="exact catalog model id")

    installing = commands.add_parser(
        "install",
        help="interactively install/manage models from the combined catalog",
    )
    selection_arguments(installing, "install")
    mutation_common_arguments(installing)
    installing.add_argument("--source", type=Path, help="alternate MTP TOML catalog")
    installing.add_argument(
        "--modelfile-dir",
        type=Path,
        action="append",
        help="alternate Modelfile directory; may be repeated",
    )
    installing.add_argument(
        "--token-file",
        type=Path,
        help="Hugging Face token file for downloads",
    )

    applying = commands.add_parser(
        "apply",
        help="make selected models match the current catalog; reuse verified GGUFs",
    )
    apply_arguments(applying, "apply")

    refreshing = commands.add_parser(
        "refresh",
        help="re-fetch selected model sources and then apply the current catalog",
    )
    apply_arguments(refreshing, "refresh")

    unregistering = commands.add_parser(
        "unregister",
        help="remove Ollama registration/runtime Modelfile but retain GGUF and state",
    )
    removal_arguments(unregistering, "unregister")

    removing = commands.add_parser(
        "remove",
        help="remove registration plus manager-owned GGUF/state; retain catalog definition",
    )
    removal_arguments(removing, "remove")

    retired = commands.add_parser(
        "purge-retired",
        help="purge models explicitly retired by the package",
    )
    retired.add_argument("--yes", action="store_true", help="skip confirmation")
    return parser



def category_required(command: str) -> ModelError:
    categories = ", ".join(CATEGORIES)
    example = {
        "apply": "sudo bc250 model apply agentic",
        "refresh": "sudo bc250 model refresh agentic MODEL",
        "unregister": "sudo bc250 model unregister agentic MODEL",
        "remove": "sudo bc250 model remove agentic MODEL",
        "path": "bc250 model path agentic MODEL",
    }.get(command, f"bc250 model {command} agentic")
    return UsageModelError(
        f"{command}: model category is required; choose one of: {categories}. Example: {example}"
    )


def require_privilege(command: str, values: list[str]) -> None:
    if command == "inspect" and "--effective" in values and os.geteuid() != 0:
        rerun = shlex.join(["sudo", "bc250", "model", *values])
        raise ModelError(
            f"inspect --effective reads protected model state; run: {rerun}"
        )
    if command == "status" and os.geteuid() != 0:
        rerun = shlex.join(["sudo", "bc250", "model", *values])
        raise ModelError(
            f"status inspects protected GGUF/state directories; run: {rerun}"
        )
    if command in {"unregister", "remove"} and "--explain" in values:
        return
    if command in {"install", "apply", "refresh", "unregister", "remove", "purge-retired"} and os.geteuid() != 0:
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
        if model.get("category") == "mtp":
            details.append(f"{model['recommendation']} / {model['role']}")
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
        label = (
            "Testing"
            if category == "experiments"
            else ("MTP" if category == "mtp" else category.title())
        )
        print(f"{label} models:")
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


def displayed_status_text(inspection: ModelInspection) -> str:
    if inspection.overall_status != "OPTIONAL":
        return inspection.overall_status
    if inspection.registration_status == "unavailable":
        if inspection.source_status == "current":
            return "OPTIONAL — source cached, registration unavailable"
        if inspection.source_status == "drift":
            return (
                "OPTIONAL — source cached, registration unavailable "
                "(source needs refresh before use)"
            )
        if inspection.source_status == "unavailable":
            return "OPTIONAL — source and registration state unavailable"
        return "OPTIONAL — registration unavailable"
    if inspection.source_status == "current":
        return "OPTIONAL — source cached, not registered"
    if inspection.source_status == "drift":
        return "OPTIONAL — source cached, not registered (source needs refresh before use)"
    if inspection.source_status == "unavailable":
        return "OPTIONAL — not selected (source state unavailable)"
    return "OPTIONAL — not installed"


def recommended_status_action(inspection: ModelInspection) -> str | None:
    if inspection.overall_status == "OPTIONAL":
        return None
    model = inspection.model
    category = model["category"]
    name = model.get("name", model["id"])
    if inspection.remote_status == "update available":
        if category == "mtp" and not model.get("enabled", False):
            return f"sudo bc250 model refresh mtp {name} --include-disabled"
        return f"sudo bc250 model refresh {category} {name}"
    if inspection.overall_status in {"MISSING", "DRIFT"}:
        if category == "mtp" and not model.get("enabled", False):
            return f"sudo bc250 advanced mtp prepare {name}"
        return f"sudo bc250 model apply {category} {name}"
    return None


def compact_inspection_details(inspection: ModelInspection) -> list[str]:
    """Return concise state labels suitable for interactive model selection."""
    model = inspection.model
    if model.get("category") == "mtp":
        if inspection.source_status == "current":
            return ["FETCHED", "VERIFIED"]
        if inspection.source_status == "missing":
            return ["NOT FETCHED"]
        if inspection.source_status == "drift":
            return ["SOURCE DRIFT"]
        return ["SOURCE UNAVAILABLE"]
    if (
        model.get("category") == "agentic"
        and inspection.registration_status == "unavailable"
        and inspection.source_status in {"current", "ollama-managed"}
        and inspection.modelfile_status == "current"
    ):
        return ["agent lane inactive", "deferred"]
    if inspection.overall_status == "CURRENT":
        return ["CURRENT"]
    if inspection.overall_status == "OPTIONAL":
        if inspection.registration_status == "unavailable":
            if inspection.source_status in {"current", "drift"}:
                return ["OPTIONAL", "source cached, registration unavailable"]
            return ["OPTIONAL", "registration unavailable"]
        if inspection.source_status in {"current", "drift"}:
            return ["OPTIONAL", "source cached, not registered"]
        return ["OPTIONAL", "not installed"]

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
        if model.get("category") == "agentic" and inspection.registration_status == "unavailable":
            registration = "not inspected (agent lane inactive in normal mode)"
        else:
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
    if (
        model.get("category") == "agentic"
        and inspection.registration_status == "unavailable"
        and inspection.source_status in {"current", "ollama-managed"}
        and inspection.modelfile_status == "current"
    ):
        print("  Status:         SOURCE CURRENT — runtime registration not inspected")
    else:
        print(f"  Status:         {displayed_status_text(inspection)}")
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
        if getattr(args, "explain", False):
            show_removal_plan(list(groups.values()), args)
            return 0
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
        if getattr(args, "explain", False):
            show_removal_plan([(defaults, selected)], args)
            return 0
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
    models: list[dict],
    selection: str | None,
    *,
    interactive: bool,
    group_excluded_categories: frozenset[str] = frozenset(),
    prompt: str | None = None,
) -> list[dict]:
    if not models:
        return []
    if selection is None and not interactive:
        return models
    if selection is None:
        selection = prompt_line(
            prompt
            or "Select models by number, range, or group (recommended/production/all); press Enter to cancel: "
        )
    if not selection:
        return []
    return select_models(
        models,
        selection,
        group_excluded_categories=group_excluded_categories,
    )


def install_available_models(catalogs: list[tuple[dict, list[dict]]]) -> list[dict]:
    """Return the interactive installer catalog, including standalone MTP entries."""
    return [model for _defaults, models in catalogs for model in models]


def print_install_catalog_state(catalogs: list[tuple[dict, list[dict]]]) -> list[dict]:
    """Show the combined installer catalog with current local state."""
    available = install_available_models(catalogs)
    registrations = registered_models_by_host(
        [defaults["ollama_host"] for defaults, _models in catalogs if defaults.get("ollama_host")]
    )
    available_ids = {(model["category"], model["id"]) for model in available}
    print("Available models:")
    for defaults, models in catalogs:
        chosen = [model for model in models if (model["category"], model["id"]) in available_ids]
        if not chosen:
            continue
        category = defaults["category"]
        label = (
            "Testing"
            if category == "experiments"
            else ("MTP" if category == "mtp" else category.title())
        )
        print(f"{label} models:")
        host = defaults.get("ollama_host")
        for model in chosen:
            inspection = inspect_model_state(
                defaults,
                model,
                registrations=registrations.get(host) if host else None,
            )
            print_model_inspection_compact(inspection)
    return available


def run_install_workflow(
    args: argparse.Namespace, *, directories: list[Path] | None, source: Path | None
) -> int:
    catalogs = load_all_catalogs(directories=directories, source=source)
    suppress_catalog = (
        getattr(args, "quiet", False)
        or os.environ.get("BC250_MODELCTL_SUPPRESS_CATALOG") == "1"
    )
    available = (
        install_available_models(catalogs)
        if suppress_catalog
        else print_install_catalog_state(catalogs)
    )
    if not suppress_catalog:
        print("\nSelect models to install/reconcile.")
        print(
            "Standalone MTP selections download and verify GGUF artifacts only; "
            "they do not register with Ollama or start llama.cpp."
        )
    selected = selected_models_for_catalog(
        available,
        args.selection,
        interactive=True,
        group_excluded_categories=frozenset({"mtp"}),
        prompt=(
            "Select models by number, range, or group (recommended/production/all); "
            "MTP requires an explicit ID/index/range; press Enter to cancel: "
        ),
    )
    if not selected:
        print("Cancelled — no changes made.")
        return 0
    operation = argparse.Namespace(**vars(args))
    operation.command = "apply"
    operation.category = "all"
    operation.revision = None
    operation.sha256 = None
    operation.min_free_bytes = None
    operation.include_disabled = False
    return run_all_catalog_operation(catalogs, selected, operation)


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
    args = parser.parse_args(values)
    if args.command is None:
        parser.print_help()
        return 0
    require_privilege(args.command, values)
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

    if args.command == "install":
        return run_install_workflow(args, directories=directories, source=source)

    if args.command == "list":
        category = args.category or "all"
        if category == "all":
            catalogs = load_all_catalogs(directories=directories, source=source)
            print_catalogs_basic(catalogs, include_disabled_mtp=args.include_disabled)
            return 0
        defaults, models = load_models(category, directories=directories, source=source)
        available = (
            models
            if category != "mtp" or args.include_disabled
            else [model for model in models if model["enabled"]]
        )
        if category == "mtp" and not available:
            print("MTP models: no enabled models; use --include-disabled to include disabled opt-in models.")
            return 0
        label = (
            "Testing"
            if category == "experiments"
            else ("MTP" if category == "mtp" else category.title())
        )
        print(f"{label} models:")
        print_catalog_models(available)
        return 0

    if args.command == "inspect":
        defaults, model = resolve_one_model(
            canonical_category(args.category),
            args.id,
            directories=directories,
            source=source,
        )
        payload = model_inspect_payload(defaults, model, effective=args.effective)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print_model_inspect_payload(payload)
        return 0

    if args.command == "path":
        if args.category is None:
            raise category_required("path")
        if not args.id:
            raise ModelError(
                "path: model id is required. Example: bc250 model path agentic MODEL"
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
            registrations = registered_models_by_host(
                [defaults["ollama_host"] for defaults, _models in catalogs if defaults.get("ollama_host")]
            )
            for defaults, models in catalogs:
                host = defaults.get("ollama_host")
                category_models = [
                    model
                    for model in models
                    if (model["category"], model["id"]) in selected_ids
                ]
                if args.compact and category_models:
                    category = defaults["category"]
                    label = (
                        "Testing"
                        if category == "experiments"
                        else ("MTP" if category == "mtp" else category.title())
                    )
                    print(f"{label} models:")
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
            label = (
                "Testing"
                if category == "experiments"
                else ("MTP" if category == "mtp" else category.title())
            )
            print(f"{label} models:")
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
            if args.selection is None:
                print(
                    "\nCategory 'all' means the combined catalog; it does not select "
                    "every model by itself."
                )
                if args.command in {"remove", "unregister"}:
                    print(
                        "For destructive actions, enter an explicit model/range or type "
                        "'all' at the prompt; confirmation still applies."
                    )
                else:
                    print(
                        "To select every eligible model explicitly: "
                        f"sudo bc250 model {args.command} all all"
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
    except UsageModelError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
    except ModelError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
