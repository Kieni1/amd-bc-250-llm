#!/usr/bin/env python3
"""Discover BC-250 Modelfiles, download their GGUFs and register them."""

from __future__ import annotations

import argparse
import errno
import getpass
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib


PROJECT = "bc250-llm-server"
INSTALLED_SHARE = Path(f"/usr/share/{PROJECT}/model-management")
INSTALLED_CONFIG = Path(f"/etc/{PROJECT}")
PACKAGED_MODEL_DIR = INSTALLED_SHARE / "modelfiles"
OPERATOR_MODEL_DIR = INSTALLED_CONFIG / "models.d"

CATEGORY_ALIASES = {
    "production": "production",
    "experimental": "experiments",
    "experiments": "experiments",
    "task": "task",
    "tasker": "task",
    "agentic": "agentic",
    "coding": "agentic",
    "embedding": "embedding",
    "embedded": "embedding",
    "embed": "embedding",
    "mtp": "mtp",
}
CATEGORIES = tuple(CATEGORY_ALIASES)
OLLAMA_CATEGORIES = ("production", "experiments", "task", "agentic", "embedding")
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
        "ollama_host": "127.0.0.1:11434",
        "min_free_bytes": 0,
    },
}


class ModelError(RuntimeError):
    """A concise error suitable for command-line output."""


def canonical_category(value: str) -> str:
    try:
        return CATEGORY_ALIASES[value]
    except KeyError as error:
        raise ModelError(f"unsupported model category: {value}") from error


def require_string(table: dict, key: str, context: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise ModelError(f"{context}: {key} must be a non-empty string")
    return value


def require_filename(table: dict, key: str, context: str) -> str:
    value = require_string(table, key, context)
    if Path(value).name != value or value in {".", ".."}:
        raise ModelError(f"{context}: {key} must be a filename")
    return value


def local_source_root() -> Path | None:
    script_dir = Path(__file__).resolve().parent
    if (script_dir / "modelfiles").is_dir() and (script_dir / "mtp/models.toml").is_file():
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
    context = str(path)
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
    category = canonical_category(metadata["category"])
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
    if not output.is_absolute() or output.name != metadata["gguf"]:
        raise ModelError(f"{path}: FROM must be an absolute path ending in the GGUF filename")
    expected_root = Path(CATEGORY_DEFAULTS[category]["destination"])
    if not output.is_relative_to(expected_root):
        raise ModelError(f"{path}: FROM must be below {expected_root}")

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
        "provider": "ollama",
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
            discovered[model["name"]] = model
    if not found_directory:
        joined = ", ".join(str(path) for path in directories)
        raise ModelError(f"no Modelfile directory found: {joined}")
    return sorted(discovered.values(), key=lambda model: model["name"])


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
        if model_id in seen or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", model_id) is None:
            raise ModelError(f"{context}: duplicate or invalid id")
        seen.add(model_id)
        require_string(model, "repository", context)
        require_string(model, "revision", context)
        require_filename(model, "gguf", context)
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
        return load_mtp_catalog(source or default_mtp_catalog())
    if source is not None:
        raise ModelError("--source is only supported for the MTP catalog")
    defaults = dict(CATEGORY_DEFAULTS[canonical])
    defaults["category"] = canonical
    models = [
        model
        for model in discover_models(model_directories(directories))
        if model["category"] == canonical
    ]
    return defaults, models


def select_models(models: list[dict], selection: str) -> list[dict]:
    if not models:
        return []
    value = selection.strip()
    if value.lower() == "all":
        return list(models)
    lookup = {model["id"]: index for index, model in enumerate(models)}
    selected: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if item in lookup:
            selected.append(lookup[item])
        elif re.fullmatch(r"[0-9]+", item):
            selected.append(int(item))
        elif match := re.fullmatch(r"([0-9]+)-([0-9]+)", item):
            first, last = map(int, match.groups())
            if first > last:
                first, last = last, first
            selected.extend(range(first, last + 1))
        else:
            raise ModelError(f"unknown model selection {item!r}")
    if not selected or any(index >= len(models) for index in selected):
        raise ModelError(f"selection is outside 0-{len(models) - 1}")
    return [models[index] for index in dict.fromkeys(selected)]


def print_models(models: list[dict]) -> None:
    for index, model in enumerate(models):
        detail = model.get("origin", "enabled" if model["enabled"] else "disabled")
        print(f"  {index:2d}) {model.get('name', model['id']):<56} [{model['provider']}, {detail}]")


def state_path(output: Path) -> Path:
    return output.with_name(f"{output.name}.bc250.json")


def load_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) and value.get("schema") == 1 else {}


def state_matches(state: dict, model: dict, output: Path) -> bool:
    recorded = str(state.get("sha256", ""))
    expected = model.get("sha256", "")
    return (
        output.is_file()
        and output.stat().st_size > 0
        and all(state.get(key) == model[key] for key in ("repository", "revision", "gguf"))
        and re.fullmatch(r"[0-9a-f]{64}", recorded) is not None
        and (not expected or recorded == expected)
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_state(path: Path, model: dict, checksum: str, gid: int) -> None:
    value = {
        "schema": 1,
        "repository": model["repository"],
        "revision": model["revision"],
        "gguf": model["gguf"],
        "sha256": checksum,
    }
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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


def ollama_identity() -> tuple[int, int]:
    try:
        return pwd.getpwnam("ollama").pw_uid, grp.getgrnam("ollama").gr_gid
    except KeyError as error:
        raise ModelError("ollama user or group is missing; run bc250-install-ollama") from error


def ensure_directory(path: Path, uid: int, gid: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chown(path, uid, gid)
    os.chmod(path, 0o750)


def run_as_ollama(
    command: list[str], environment: dict[str, str], *, terminal: bool = False
) -> subprocess.CompletedProcess:
    child_environment = dict(os.environ)
    child_environment.update(environment)
    argv = [command_path("runuser"), "--preserve-environment", "-u", "ollama", "--", *command]
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


def hf_token(hf_bin: str, hf_home: Path, token_file: Path | None) -> str:
    if token_file:
        try:
            token = token_file.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise ModelError(f"cannot read token file {token_file}: {error}") from error
    else:
        token = os.environ.get("HF_TOKEN", "").strip()
    if not token and os.environ.get("BC250_HF_ANONYMOUS") != "1" and can_prompt():
        token = prompt_secret("HF_TOKEN (optional; Enter for anonymous downloads): ")
    if token and run_as_ollama(
        [hf_bin, "auth", "whoami"], hf_environment(token, hf_home)
    ).returncode == 0:
        print("Using the validated Hugging Face token.")
        return token
    if token:
        print("WARNING: Hugging Face rejected the token; downloading anonymously.", file=sys.stderr)
    else:
        print("Using anonymous Hugging Face downloads.")
    return ""


def render_modelfile(source: Path, model: dict, output: Path, destination: Path) -> None:
    rendered: list[str] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith("# Source: "):
            line = f"# Source: {model['repository']} @ {model['revision']}"
        elif line.startswith("# GGUF: "):
            line = f"# GGUF: {model['gguf']}"
        elif line.startswith("FROM "):
            line = f"FROM {output}"
        rendered.append(line)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        temporary.write_text("\n".join(rendered) + "\n", encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def install_models(defaults: dict, models: list[dict], args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        raise ModelError("run with sudo")
    if len(models) != 1 and (args.revision is not None or args.sha256 is not None):
        raise ModelError("--revision and --sha256 require one selected model")
    uid, gid = ollama_identity()
    hf_bin = command_path("hf")
    command_path("runuser")
    command_path("script")
    ollama_bin = command_path("ollama") if any(m["provider"] == "ollama" for m in models) else ""
    host = args.host or os.environ.get("OLLAMA_HOST") or os.environ.get("OLLAMA_URL") \
        or defaults.get("ollama_host", "127.0.0.1:11434")
    hf_home = Path(os.environ.get("HF_HOME", f"/var/cache/{PROJECT}/huggingface"))
    download_root = Path(
        os.environ.get("DOWNLOAD_DIR", str(hf_home / "downloads" / defaults["download_namespace"]))
    )
    modelfile_root = Path(
        os.environ.get("MODELFILE_DIR", defaults.get("modelfile_destination", ""))
    ) if os.environ.get("MODELFILE_DIR") or defaults.get("modelfile_destination") else None
    for path in (hf_home, hf_home / "hub", download_root):
        ensure_directory(path, uid, gid)
    if modelfile_root:
        ensure_directory(modelfile_root, 0, gid)

    token: str | None = None
    failures: list[str] = []
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
        print(f"\n>>> {label} [{model['provider']}]")
        try:
            output = model_path(defaults, model, args.destination or os.environ.get("DEST"))
            ensure_directory(output.parent, uid, gid)
            metadata = state_path(output)
            state = load_state(metadata)
            if state_matches(state, model, output) and not args.refresh:
                checksum = state["sha256"]
                print(f"    reusing GGUF; recorded SHA-256 {checksum}")
            else:
                minimum = args.min_free_bytes if args.min_free_bytes is not None \
                    else int(defaults.get("min_free_bytes", 0))
                free = shutil.disk_usage(output.parent).free
                if minimum and free < minimum:
                    raise ModelError(
                        f"{free / 1024**3:.1f} GiB free; {minimum / 1024**3:.1f} GiB required"
                    )
                staging = download_root / model["id"]
                ensure_directory(staging, uid, gid)
                staged = staging / model["gguf"]
                staged.unlink(missing_ok=True)
                if token is None:
                    token = hf_token(hf_bin, hf_home, args.token_file)
                command = [hf_bin, "download", model["repository"], model["gguf"]]
                if model["revision"] != "latest":
                    command.extend(("--revision", model["revision"]))
                command.extend(("--local-dir", str(staging)))
                print(
                    f"    downloading {model['repository']} @ {model['revision']}: "
                    f"{model['gguf']}"
                )
                if run_as_ollama(
                    command, hf_environment(token, hf_home), terminal=True
                ).returncode != 0:
                    raise ModelError("Hugging Face download failed")
                if not staged.is_file() or staged.stat().st_size == 0:
                    raise ModelError(f"download completed without {staged}")
                print("    calculating SHA-256")
                checksum = sha256(staged)
                if expected and checksum != expected:
                    raise ModelError(f"checksum mismatch: got {checksum}, expected {expected}")
                atomic_replace(staged, output)
                os.chown(output, 0, gid)
                os.chmod(output, 0o640)
                write_state(metadata, model, checksum, gid)
                print(f"    recorded SHA-256 {checksum}")

            os.chown(output, 0, gid)
            os.chmod(output, 0o640)
            if model["provider"] == "download-only":
                print("    ready for llama.cpp")
                continue

            runtime_template = (
                modelfile_root / model["modelfile"]
                if modelfile_root
                else output.parent / model["modelfile"]
            )
            render_modelfile(model["template"], model, output, runtime_template)
            os.chown(runtime_template, 0, gid)
            os.chmod(runtime_template, 0o640)
            result = run_as_ollama(
                [ollama_bin, "create", model["name"], "-f", str(runtime_template)],
                {"HOME": "/var/lib/ollama", "OLLAMA_HOST": host},
            )
            if result.returncode != 0:
                raise ModelError("ollama create failed")
            print("    registered with Ollama")
        except (ModelError, OSError) as error:
            print(f"    ERROR: {error}", file=sys.stderr)
            failures.append(label)
    if ollama_bin:
        subprocess.run(
            [ollama_bin, "list"],
            env={**os.environ, "OLLAMA_HOST": host},
            check=False,
        )
    if failures:
        print(f"\nFailed: {' '.join(failures)}", file=sys.stderr)
        return 2
    print(f"\nDone: {len(models)} model(s) processed.")
    return 0


def cleanup_models(defaults: dict, models: list[dict], args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        raise ModelError("run with sudo")
    if not args.yes:
        names = ", ".join(model.get("name", model["id"]) for model in models)
        if prompt_line(f"Remove {names}? [y/N] ").lower() not in {"y", "yes"}:
            print("Cleanup cancelled.")
            return 0
    _uid, gid = ollama_identity()
    host = defaults.get("ollama_host", "127.0.0.1:11434")
    ollama_bin = shutil.which("ollama")
    for model in models:
        label = model.get("name", model["id"])
        print(f"\n>>> removing {label}")
        if model["provider"] == "ollama" and ollama_bin:
            run_as_ollama(
                [ollama_bin, "rm", model["name"]],
                {"HOME": "/var/lib/ollama", "OLLAMA_HOST": host},
            )
        output = model_path(defaults, model)
        paths = [output, state_path(output)]
        destination = defaults.get("modelfile_destination")
        if destination and model.get("modelfile"):
            paths.append(Path(destination) / model["modelfile"])
        for path in paths:
            if path.exists():
                path.unlink()
                print(f"    removed {path}")
        try:
            output.parent.rmdir()
        except OSError:
            pass
    print(f"\nRemoved {len(models)} model(s). Source Modelfiles were retained.")
    return 0


def catalog_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("category", choices=CATEGORIES)
    parser.add_argument("--source", type=Path, help="alternate MTP TOML catalog")
    parser.add_argument(
        "--modelfile-dir",
        type=Path,
        action="append",
        help="alternate Modelfile directory; may be repeated",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bc250-model", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="list discovered templates")
    catalog_arguments(listing)
    listing.add_argument("--all", action="store_true", help="include disabled MTP entries")
    resolving = commands.add_parser("resolve", help="resolve one model id")
    catalog_arguments(resolving)
    resolving.add_argument("id")
    resolving.add_argument("--provider", choices=("ollama", "download-only"))
    installing = commands.add_parser("install", help="download and register selected models")
    catalog_arguments(installing)
    installing.add_argument("selection", nargs="?")
    installing.add_argument("--list", action="store_true")
    installing.add_argument("--host")
    installing.add_argument("--revision")
    installing.add_argument("--sha256")
    installing.add_argument("--destination")
    installing.add_argument("--min-free-bytes", type=int)
    installing.add_argument("--token-file", type=Path)
    installing.add_argument(
        "--include-disabled",
        action="store_true",
        help="include disabled MTP entries for this invocation",
    )
    installing.add_argument("--refresh", action="store_true")
    cleaning = commands.add_parser("cleanup", help="remove selected deployed models")
    catalog_arguments(cleaning)
    cleaning.add_argument("selection", nargs="?")
    cleaning.add_argument("--list", action="store_true")
    cleaning.add_argument("--yes", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(line_buffering=True)
    args = build_parser().parse_args(argv)
    category = canonical_category(args.category)
    defaults, models = load_models(
        category,
        directories=args.modelfile_dir,
        source=args.source or (Path(os.environ["SOURCE_FILE"]) if os.environ.get("SOURCE_FILE") else None),
    )

    if args.command == "list":
        available = models if category != "mtp" or args.all else [m for m in models if m["enabled"]]
        print(f"{category.title()} models:")
        print_models(available)
        return 0
    if args.command == "resolve":
        for model in models:
            if model["id"] == args.id and (
                args.provider is None or model["provider"] == args.provider
            ) and (category != "mtp" or model["enabled"]):
                print(
                    f"{model_path(defaults, model)}\t"
                    f"{model.get('context', '')}\t{model.get('draft', '')}"
                )
                return 0
        raise ModelError(f"model id not found: {args.id}")

    available = models
    if category == "mtp" and args.command != "cleanup" and not args.include_disabled:
        available = [model for model in models if model["enabled"]]
    print(f"Available {category} models:")
    print_models(available)
    if args.list:
        return 0
    if not available:
        print(f"No selectable {category} models were found.")
        return 0
    selection = args.selection
    if selection is None:
        selection = prompt_line("Models (id/index/range; Enter to cancel): ")
    if not selection:
        print("No models selected.")
        return 0
    selected = select_models(available, selection)
    if args.command == "cleanup":
        return cleanup_models(defaults, selected, args)
    return install_models(defaults, selected, args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ModelError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
