"""Read package-owned BC-250 model catalog/profile metadata for runtime consumers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROJECT = "bc250-llm-server"
DEFAULT_MODEL_ROOT = Path(f"/usr/share/{PROJECT}/model-management")
_SOURCE_ROOT = Path(__file__).resolve().parents[1]


class ModelContractError(RuntimeError):
    """Package model metadata is unavailable or malformed."""


def _resource_path(env_name: str, source_name: str, installed_name: str) -> Path:
    override = os.environ.get(env_name)
    if override:
        return Path(override)
    source = _SOURCE_ROOT / "models" / source_name
    if source.is_file():
        return source
    return DEFAULT_MODEL_ROOT / installed_name


def model_catalog_path() -> Path:
    return _resource_path("BC250_MODEL_CATALOG", "model-catalog.json", "model-catalog.json")


def model_profiles_path() -> Path:
    return _resource_path("BC250_MODEL_PROFILES", "model-profiles.json", "model-profiles.json")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelContractError(f"cannot read model contract {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ModelContractError(f"model contract {path} is not an object")
    return value


def normalize_model_id(model_id: str) -> str:
    return str(model_id).strip().removesuffix(":latest")


def load_model_catalog() -> dict[str, dict[str, Any]]:
    path = model_catalog_path()
    document = _load_json(path)
    models = document.get("models")
    if document.get("schema") != 1 or not isinstance(models, dict):
        raise ModelContractError(f"invalid model catalog: {path}")
    if not all(isinstance(key, str) and isinstance(value, dict) for key, value in models.items()):
        raise ModelContractError(f"invalid model catalog entries: {path}")
    return models


def load_model_profiles() -> dict[str, dict[str, Any]]:
    path = model_profiles_path()
    document = _load_json(path)
    profiles = document.get("profiles")
    if document.get("schema") != 2 or not isinstance(profiles, dict):
        raise ModelContractError(f"invalid model profiles: {path}")
    if not all(isinstance(key, str) and isinstance(value, dict) for key, value in profiles.items()):
        raise ModelContractError(f"invalid model profile entries: {path}")
    return profiles


def model_contract(model_id: str) -> dict[str, Any] | None:
    """Return intrinsic + BC-250 qualification metadata for one packaged Ollama model."""
    canonical = normalize_model_id(model_id)
    catalog = load_model_catalog()
    entry = catalog.get(canonical)
    if entry is None:
        return None
    return {
        "id": canonical,
        "catalog": entry,
        "profile": load_model_profiles().get(canonical),
    }


def model_capabilities(model_id: str) -> dict[str, Any]:
    contract = model_contract(model_id)
    if contract is None:
        return {}
    capabilities = contract["catalog"].get("capabilities")
    return dict(capabilities) if isinstance(capabilities, dict) else {}


def benchmark_kinds(model_id: str) -> tuple[str, ...]:
    values = model_capabilities(model_id).get("benchmark_kinds")
    if not isinstance(values, list):
        return ()
    return tuple(str(value) for value in values if isinstance(value, str) and value)
