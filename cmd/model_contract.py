"""Read and validate package-owned BC-250 model catalog/profile metadata."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any

PROJECT = "bc250-llm-server"
DEFAULT_MODEL_ROOT = Path(f"/usr/share/{PROJECT}/model-management")
DEFAULT_OPENWEBUI_ROOT = Path(f"/usr/share/{PROJECT}/openwebui")
_SOURCE_ROOT = Path(__file__).resolve().parents[1]

OLLAMA_CATEGORIES = ("production", "experiments", "task", "agentic", "embedding")
CATEGORY_PREFIXES = {
    "production": "prod-",
    "experiments": "exp-",
    "task": "task-",
    "agentic": "agentic-",
    "embedding": "embed-",
}
EXPECTED_LANES = {
    "production": "main",
    "experiments": "main",
    "task": "task",
    "agentic": "agent",
    "embedding": "embedding",
}
ALLOWED_PROVIDERS = {"ollama", "ollama-hf"}
ALLOWED_REASONING = {"verified", "candidate", "unsupported"}
ALLOWED_SOURCE_POLICY = {"tracking", "pinned"}
ALLOWED_OWNERSHIP = {"bc250", "ollama", "provider", "none"}
ALLOWED_OWUI_EXPOSURE = {"curated", "testing", "forbidden"}
ALLOWED_AGENT_VALIDATION = {"not-applicable", "static-output-contract"}


class ModelContractError(RuntimeError):
    """Package model metadata is unavailable or semantically malformed."""


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


def _require_string(table: dict[str, Any], key: str, context: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise ModelContractError(f"{context}: {key} must be a non-empty string")
    return value


def _require_string_list(value: Any, context: str) -> list[str]:
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ModelContractError(f"{context} must be a non-empty string list")
    return list(value)


def normalize_model_id(model_id: str) -> str:
    return str(model_id).strip().removesuffix(":latest")


def validate_model_catalog_document(
    document: dict[str, Any], *, source: Path | str = "model-catalog.json"
) -> dict[str, dict[str, Any]]:
    """Validate the shared intrinsic/acquisition model contract."""
    context_source = str(source)
    models = document.get("models")
    if document.get("schema") != 1 or not isinstance(models, dict):
        raise ModelContractError(f"{context_source}: unsupported model-catalog schema")

    result: dict[str, dict[str, Any]] = {}
    for model_id, entry in models.items():
        context = f"{context_source}: {model_id}"
        if not isinstance(model_id, str) or re.fullmatch(r"[a-z0-9][a-z0-9._-]*", model_id) is None:
            raise ModelContractError(f"{context}: invalid model id")
        if not isinstance(entry, dict):
            raise ModelContractError(f"{context}: entry must be an object")

        category = entry.get("category")
        if category not in OLLAMA_CATEGORIES:
            raise ModelContractError(f"{context}: invalid category")
        if not model_id.startswith(CATEGORY_PREFIXES[category]):
            raise ModelContractError(f"{context}: id does not match category prefix")
        provider = entry.get("provider")
        if provider not in ALLOWED_PROVIDERS:
            raise ModelContractError(f"{context}: invalid provider")
        if not isinstance(entry.get("enabled"), bool):
            raise ModelContractError(f"{context}: enabled must be boolean")

        source_info = entry.get("source")
        if not isinstance(source_info, dict):
            raise ModelContractError(f"{context}: source must be an object")
        repository = _require_string(source_info, "repository", f"{context}: source")
        if re.fullmatch(r"[^/\s]+/[^/\s]+", repository) is None:
            raise ModelContractError(f"{context}: source repository must be owner/repository")
        _require_string(source_info, "revision", f"{context}: source")
        filename = _require_string(source_info, "filename", f"{context}: source")
        if Path(filename).name != filename or filename in {".", ".."}:
            raise ModelContractError(f"{context}: source filename must be a filename")
        remote_path_value = source_info.get("remote_path", filename)
        if not isinstance(remote_path_value, str) or not remote_path_value:
            raise ModelContractError(f"{context}: source remote_path must be a non-empty string")
        remote_path = PurePosixPath(remote_path_value)
        if (
            remote_path.is_absolute()
            or "\\" in remote_path_value
            or any(part in {"", ".", ".."} for part in remote_path.parts)
            or remote_path.name != filename
        ):
            raise ModelContractError(
                f"{context}: source remote_path must be a safe relative repository path "
                "ending in filename"
            )
        digest = source_info.get("expected_sha256", "")
        if not isinstance(digest, str) or (digest and re.fullmatch(r"[0-9a-f]{64}", digest) is None):
            raise ModelContractError(f"{context}: invalid expected_sha256")
        source_policy = source_info.get("policy")
        if source_policy not in ALLOWED_SOURCE_POLICY:
            raise ModelContractError(f"{context}: source policy must be tracking or pinned")
        reproducibility = _require_string(source_info, "reproducibility", f"{context}: source")
        if source_policy == "tracking" and digest:
            raise ModelContractError(
                f"{context}: tracking sources record acquired digests in state, not expected_sha256"
            )
        if source_policy == "pinned" and provider == "ollama" and not digest:
            raise ModelContractError(
                f"{context}: pinned manager-owned sources require expected_sha256"
            )
        if source_policy == "tracking" and provider == "ollama" and reproducibility != "tracking-ref":
            raise ModelContractError(
                f"{context}: tracking manager-owned source must use reproducibility=tracking-ref"
            )
        if source_policy == "pinned" and provider == "ollama" and reproducibility != "pinned+digest":
            raise ModelContractError(
                f"{context}: pinned manager-owned source must use reproducibility=pinned+digest"
            )
        if provider == "ollama":
            local_path = Path(_require_string(source_info, "local_path", f"{context}: source"))
            if not local_path.is_absolute() or local_path.name != filename:
                raise ModelContractError(
                    f"{context}: local_path must be absolute and end in filename"
                )
        else:
            if "remote_path" in source_info:
                raise ModelContractError(
                    f"{context}: ollama-hf sources use provider_ref, not remote_path"
                )
            provider_ref = _require_string(source_info, "provider_ref", f"{context}: source")
            remote = re.fullmatch(
                r"hf\.co/(?P<repository>[^/\s]+/[^/:\s]+):[^\s]+", provider_ref
            )
            if remote is None:
                raise ModelContractError(
                    f"{context}: ollama-hf provider_ref must be an hf.co owner/repository reference"
                )
            if remote.group("repository") != repository:
                raise ModelContractError(
                    f"{context}: provider_ref repository must match source repository"
                )

        ownership = entry.get("ownership")
        if not isinstance(ownership, dict):
            raise ModelContractError(f"{context}: ownership must be an object")
        for field in ("source", "registration", "state"):
            if ownership.get(field) not in ALLOWED_OWNERSHIP:
                raise ModelContractError(f"{context}: invalid ownership.{field}")
        expected_ownership = (
            {"source": "bc250", "registration": "bc250", "state": "bc250"}
            if provider == "ollama"
            else {"source": "ollama", "registration": "bc250", "state": "provider"}
        )
        if any(ownership.get(field) != value for field, value in expected_ownership.items()):
            raise ModelContractError(
                f"{context}: ownership does not match {provider} provider contract"
            )

        runtime = entry.get("runtime")
        if not isinstance(runtime, dict):
            raise ModelContractError(f"{context}: runtime must be an object")
        if runtime.get("lane") != EXPECTED_LANES[category]:
            raise ModelContractError(f"{context}: runtime lane does not match category")
        if runtime.get("modelfile") != f"{model_id}.Modelfile":
            raise ModelContractError(f"{context}: runtime Modelfile must match model id")
        if not isinstance(runtime.get("agent_prepare_required"), bool):
            raise ModelContractError(f"{context}: agent_prepare_required must be boolean")
        if runtime["agent_prepare_required"] != (category == "agentic"):
            raise ModelContractError(
                f"{context}: agent_prepare_required must be true only for agentic models"
            )

        capabilities = entry.get("capabilities")
        if not isinstance(capabilities, dict):
            raise ModelContractError(f"{context}: capabilities must be an object")
        _require_string_list(capabilities.get("modalities"), f"{context}: capabilities.modalities")
        _require_string_list(capabilities.get("features"), f"{context}: capabilities.features")
        benchmark_values = _require_string_list(
            capabilities.get("benchmark_kinds"), f"{context}: capabilities.benchmark_kinds"
        )
        if capabilities.get("reasoning") not in ALLOWED_REASONING:
            raise ModelContractError(f"{context}: invalid reasoning capability")
        for field in ("ocr", "tools"):
            if not isinstance(capabilities.get(field), bool):
                raise ModelContractError(f"{context}: capabilities.{field} must be boolean")
        for optional_profile in ("ocr_profile", "embedding_profile", "translation_profile"):
            value = capabilities.get(optional_profile)
            if value is not None and (
                not isinstance(value, str) or re.fullmatch(r"[a-z0-9][a-z0-9-]*", value) is None
            ):
                raise ModelContractError(f"{context}: invalid capabilities.{optional_profile}")
        if capabilities["ocr"]:
            if not capabilities.get("ocr_profile"):
                raise ModelContractError(f"{context}: OCR models require capabilities.ocr_profile")
            if "ocr" not in benchmark_values:
                raise ModelContractError(f"{context}: OCR models must declare the ocr benchmark kind")
        elif capabilities.get("ocr_profile") is not None:
            raise ModelContractError(f"{context}: non-OCR models cannot define capabilities.ocr_profile")
        if "embedding" in benchmark_values and not capabilities.get("embedding_profile"):
            raise ModelContractError(
                f"{context}: embedding benchmark models require capabilities.embedding_profile"
            )
        if capabilities.get("embedding_profile") and category != "embedding":
            raise ModelContractError(f"{context}: embedding_profile is only valid for embedding models")
        if capabilities.get("translation_profile") and "generation" not in benchmark_values:
            raise ModelContractError(
                f"{context}: translation_profile requires generation benchmark support"
            )

        # Optional upstream rights metadata: recording it is not permission to deploy.
        license_info = entry.get("license")
        if license_info is not None:
            if not isinstance(license_info, dict):
                raise ModelContractError(f"{context}: license must be an object")
            _require_string(license_info, "id", f"{context}: license")
            _require_string(license_info, "use_note", f"{context}: license")

        native = entry.get("native_context_max")
        if native is not None and (type(native) is not int or native <= 0):
            raise ModelContractError(
                f"{context}: native_context_max must be null or a positive integer"
            )
        result[model_id] = entry
    return result


def validate_model_profiles_document(
    document: dict[str, Any],
    *,
    source: Path | str = "model-profiles.json",
    catalog: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Validate BC-250 qualification/role policy and its catalog relationship."""
    context_source = str(source)
    profiles = document.get("profiles")
    if document.get("schema") != 2 or not isinstance(profiles, dict):
        raise ModelContractError(f"{context_source}: unsupported model-profile schema")

    result: dict[str, dict[str, Any]] = {}
    for model_id, profile in profiles.items():
        context = f"{context_source}: {model_id}"
        if not isinstance(model_id, str) or not model_id or not isinstance(profile, dict):
            raise ModelContractError(f"{context}: invalid model profile entry")
        for field in (
            "profile_class",
            "intended_role",
            "comparison_role",
            "residency_policy",
            "reasoning_request_policy",
            "agent_validation",
        ):
            _require_string(profile, field, context)
        if profile.get("owui_testing_exposure") not in ALLOWED_OWUI_EXPOSURE:
            raise ModelContractError(
                f"{context}: owui_testing_exposure must be curated, testing, or forbidden"
            )
        if profile["agent_validation"] not in ALLOWED_AGENT_VALIDATION:
            raise ModelContractError(
                f"{context}: agent_validation must be not-applicable or static-output-contract"
            )
        for field in ("recommended", "specialized"):
            if not isinstance(profile.get(field), bool):
                raise ModelContractError(f"{context}: {field} must be boolean")
        output_expectation = profile.get("output_token_expectation")
        if output_expectation is not None and (
            type(output_expectation) is not int or output_expectation <= 0
        ):
            raise ModelContractError(
                f"{context}: output_token_expectation must be null or a positive integer"
            )
        qualified = profile.get("qualified_context_target")
        product_default = profile.get("product_context_default")
        if type(qualified) is not int or qualified <= 0:
            raise ModelContractError(
                f"{context}: qualified_context_target must be a positive integer"
            )
        if product_default is not None and (
            type(product_default) is not int or product_default <= 0
        ):
            raise ModelContractError(
                f"{context}: product_context_default must be null or a positive integer"
            )
        if product_default is not None and product_default > qualified:
            raise ModelContractError(
                f"{context}: product_context_default cannot exceed qualified_context_target"
            )
        result[model_id] = profile

    if catalog is not None:
        missing = sorted(set(catalog) - set(result))
        if missing:
            raise ModelContractError(
                f"{context_source}: catalog model(s) missing qualification profiles: {', '.join(missing)}"
            )
        for model_id, entry in catalog.items():
            profile = result[model_id]
            category = entry["category"]
            expected_agent_validation = (
                "static-output-contract" if category == "agentic" else "not-applicable"
            )
            if profile["agent_validation"] != expected_agent_validation:
                raise ModelContractError(
                    f"{context_source}: {model_id}: agent_validation does not match runtime category"
                )
            if category == "agentic" and profile["owui_testing_exposure"] != "forbidden":
                raise ModelContractError(
                    f"{context_source}: {model_id}: agentic models must forbid normal OWUI testing exposure"
                )
            native = entry.get("native_context_max")
            if native is not None and profile["qualified_context_target"] > native:
                raise ModelContractError(
                    f"{context_source}: {model_id}: qualified context exceeds native_context_max"
                )
    return result


def load_model_catalog() -> dict[str, dict[str, Any]]:
    path = model_catalog_path()
    return validate_model_catalog_document(_load_json(path), source=path)


def load_model_profiles(
    catalog: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    path = model_profiles_path()
    validated_catalog = load_model_catalog() if catalog is None else catalog
    return validate_model_profiles_document(
        _load_json(path), source=path, catalog=validated_catalog
    )



def required_baseline_model_ids(
    *, roles_path: Path | None = None, desired_path: Path | None = None
) -> frozenset[str]:
    """Derive the required baseline from active roles and task/embedding policy.

    Experiment, Agent and alternate task/embedding models remain optional until
    a role or desired-state setting explicitly selects them. This is the same
    baseline selection policy used by the installer's required-model step.
    """
    def source_or_installed(filename: str) -> Path:
        local = _SOURCE_ROOT / "config/openwebui" / filename
        return local if local.is_file() else DEFAULT_OPENWEBUI_ROOT / filename

    roles = roles_path or Path(os.environ.get("BC250_OWUI_MODELS_FILE") or source_or_installed("models.json"))
    desired_override = os.environ.get("BC250_OWUI_DESIRED_STATE")
    desired = desired_path or Path(desired_override or source_or_installed("desired-state.json"))
    if desired_path is None and desired_override:
        # Same override contract as openwebui-setup, install and verify.
        if desired.is_symlink() or not desired.is_file():
            raise ModelContractError(f"desired-state override must be a regular non-symlink file: {desired}")
        info = desired.stat()
        if info.st_mode & 0o022 or (os.geteuid() == 0 and info.st_uid != 0):
            raise ModelContractError(f"desired-state override ownership/permissions are unsafe: {desired}")
    role_document = _load_json(roles)
    desired_document = _load_json(desired)
    role_models = role_document.get("models")
    if not isinstance(role_models, list):
        raise ModelContractError(f"{roles}: models must be a list")
    result: set[str] = set()
    for role in role_models:
        if not isinstance(role, dict):
            raise ModelContractError(f"{roles}: model role must be an object")
        if role.get("is_active") is True:
            identity = role.get("base_model_id")
            if identity:
                if not isinstance(identity, str):
                    raise ModelContractError(f"{roles}: invalid base_model_id")
                result.add(normalize_model_id(identity))
    for section, setting in (("task", "TASK_MODEL"), ("embedding", "RAG_EMBEDDING_MODEL")):
        entry = desired_document.get(section)
        if not isinstance(entry, dict) or not isinstance(entry.get(setting), str):
            raise ModelContractError(f"{desired}: {section}.{setting} must be a model id")
        result.add(normalize_model_id(entry[setting]))
    if not result:
        raise ModelContractError("required baseline model IDs cannot be empty")
    return frozenset(result)


def validate_testing_visibility_policies(
    policies: dict[str, Any], profiles: dict[str, dict[str, Any]] | None = None
) -> None:
    """Explicit testing visibility must not override forbidden profile safety.

    A hidden testing profile needs an explanatory admin-only description;
    neither a retired model nor an operator-only entry gains permission here.
    """
    if not isinstance(policies, dict):
        raise ModelContractError("testing_model_policies must be an object")
    definitions = profiles if profiles is not None else load_model_profiles()
    for raw_id, policy in policies.items():
        if not isinstance(policy, dict):
            raise ModelContractError(f"testing visibility policy {raw_id} must be an object")
        profile = definitions.get(normalize_model_id(raw_id))
        if profile is None or "ordinary_user_visible" not in policy:
            continue
        visible = policy["ordinary_user_visible"]
        if not isinstance(visible, bool):
            raise ModelContractError(f"testing visibility policy {raw_id} must be boolean")
        exposure = profile.get("owui_testing_exposure")
        if exposure == "forbidden" and visible:
            raise ModelContractError(f"{raw_id}: forbidden profile cannot be ordinary-user-visible")
        if exposure == "testing" and not visible:
            description = str(policy.get("description", "")).lower()
            if "admin-only" not in description and "hidden" not in description:
                raise ModelContractError(
                    f"{raw_id}: hiding a testing profile requires an explicit admin-only/hidden description"
                )


def model_contract(model_id: str) -> dict[str, Any] | None:
    """Return validated intrinsic + BC-250 qualification metadata for one packaged model."""
    canonical = normalize_model_id(model_id)
    catalog = load_model_catalog()
    entry = catalog.get(canonical)
    if entry is None:
        return None
    profiles = load_model_profiles(catalog)
    return {"id": canonical, "catalog": entry, "profile": profiles[canonical]}


def model_capabilities(model_id: str) -> dict[str, Any]:
    contract = model_contract(model_id)
    if contract is None:
        return {}
    return dict(contract["catalog"]["capabilities"])


def benchmark_kinds(model_id: str) -> tuple[str, ...]:
    values = model_capabilities(model_id).get("benchmark_kinds", [])
    return tuple(str(value) for value in values)
