#!/usr/bin/env python3
"""Download GGUF files and register the repository's Ollama model profiles."""

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
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.request


PROJECT = "bc250-llm-server"
CATEGORIES = ("production", "experiments", "mtp", "task", "coding")
INSTALLED_SHARE = Path(f"/usr/share/{PROJECT}/model-management")
INSTALLED_CONFIG = Path(f"/etc/{PROJECT}")


class ModelError(RuntimeError):
    """A user-facing model-management error."""


def default_paths(category: str) -> tuple[Path, Path]:
    script_dir = Path(__file__).resolve().parent
    source_tree_catalog = (
        script_dir / "mtp/models.toml"
        if category == "mtp"
        else script_dir / "sources" / f"{category}.toml"
    )
    source_tree_modelfiles = script_dir / "modelfiles" / category
    if source_tree_catalog.is_file():
        return source_tree_catalog, source_tree_modelfiles
    if category in {"production", "experiments", "mtp"}:
        catalog = Path(f"/etc/{PROJECT}/{category}-models.toml")
    else:
        catalog = INSTALLED_SHARE / "sources" / f"{category}.toml"
    return catalog, INSTALLED_SHARE / "modelfiles" / category


def _require_string(mapping: dict, key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ModelError(f"{context}: {key} must be a non-empty string")
    return value


def model_output_path(defaults: dict, model: dict, destination: str | None = None) -> Path:
    root = Path(destination or _require_string(defaults, "destination", "defaults"))
    if defaults.get("layout", "flat") == "by-id":
        root /= _require_string(model, "id", "model")
    return root / _require_string(model, "gguf", f"model {model.get('id', '?')}")


def read_modelfile_metadata(path: Path) -> dict[str, str]:
    """Read catalog-derived fields from a packaged or rendered Modelfile."""
    metadata = {"name": "", "repository": "", "revision": "", "gguf": "", "from": ""}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ModelError(f"cannot read Modelfile {path}: {error}") from error
    for line in lines:
        if line.startswith("# Ollama model: "):
            metadata["name"] = line.removeprefix("# Ollama model: ").strip()
        elif line.startswith("# Source: "):
            source = line.removeprefix("# Source: ").strip()
            if " @ " in source:
                metadata["repository"], metadata["revision"] = source.rsplit(" @ ", 1)
        elif line.startswith("# GGUF: "):
            metadata["gguf"] = line.removeprefix("# GGUF: ").strip()
        elif line.startswith("FROM ") and not metadata["from"]:
            metadata["from"] = line.split(maxsplit=1)[1].strip()
    return metadata


def render_modelfile(source: Path, destination: Path, model: dict, output: Path) -> None:
    """Render an immutable packaged template for the selected runtime values."""
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ModelError(f"cannot read Modelfile {source}: {error}") from error

    replacements = {
        "# Ollama model: ": model["name"],
        "# Source: ": f"{model['repository']} @ {model['revision']}",
        "# GGUF: ": model["gguf"],
    }
    replaced = {key: False for key in replacements}
    from_replaced = False
    rendered: list[str] = []
    for line in lines:
        for prefix, value in replacements.items():
            if line.startswith(prefix):
                line = f"{prefix}{value}"
                replaced[prefix] = True
                break
        if line.startswith("FROM ") and not from_replaced:
            line = f"FROM {output}"
            from_replaced = True
        rendered.append(line)
    missing = [prefix.strip() for prefix, present in replaced.items() if not present]
    if not from_replaced:
        missing.append("FROM")
    if missing:
        raise ModelError(f"{source}: missing required template fields: {', '.join(missing)}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        temporary.write_text("\n".join(rendered) + "\n", encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def load_catalog(
    path: Path,
    category: str,
    modelfile_dir: Path,
    *,
    strict_metadata: bool = False,
) -> tuple[dict, list[dict]]:
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ModelError(f"cannot load catalog {path}: {error}") from error

    if document.get("schema") != 1:
        raise ModelError(f"{path}: unsupported or missing schema")
    defaults = document.get("defaults")
    models = document.get("models")
    if not isinstance(defaults, dict) or not isinstance(models, list):
        raise ModelError(f"{path}: defaults and models are required")
    if defaults.get("category") != category:
        raise ModelError(f"{path}: category must be {category!r}")
    if defaults.get("layout", "flat") not in {"flat", "by-id"}:
        raise ModelError(f"{path}: layout must be 'flat' or 'by-id'")
    _require_string(defaults, "destination", f"{path}: defaults")
    _require_string(defaults, "download_namespace", f"{path}: defaults")

    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    seen_modelfiles: set[str] = set()
    for index, model in enumerate(models):
        context = f"{path}: models[{index}]"
        if not isinstance(model, dict):
            raise ModelError(f"{context} must be a table")
        model_id = _require_string(model, "id", context)
        provider = _require_string(model, "provider", context)
        _require_string(model, "repository", context)
        _require_string(model, "revision", context)
        gguf = _require_string(model, "gguf", context)
        if Path(gguf).name != gguf:
            raise ModelError(f"{context}: gguf must be a filename, not a path")
        if provider not in {"ollama", "download-only"}:
            raise ModelError(f"{context}: unsupported provider {provider!r}")
        if not isinstance(model.get("enabled"), bool):
            raise ModelError(f"{context}: enabled must be true or false")
        if model_id in seen_ids:
            raise ModelError(f"{path}: duplicate model id {model_id!r}")
        seen_ids.add(model_id)

        checksum = model.get("sha256", "")
        if checksum and not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ModelError(f"{context}: sha256 must be 64 lowercase hexadecimal characters")

        if provider == "download-only":
            for key in ("context", "draft"):
                value = model.get(key)
                if not isinstance(value, int) or value <= 0:
                    raise ModelError(f"{context}: {key} must be a positive integer")
            continue

        name = _require_string(model, "name", context)
        modelfile_name = _require_string(model, "modelfile", context)
        if Path(modelfile_name).name != modelfile_name:
            raise ModelError(f"{context}: modelfile must be a filename")
        if modelfile_name != f"{name}.Modelfile":
            raise ModelError(f"{context}: Modelfile name must match the Ollama model name")
        if name in seen_names:
            raise ModelError(f"{path}: duplicate Ollama model name {name!r}")
        if modelfile_name in seen_modelfiles:
            raise ModelError(f"{path}: duplicate Modelfile {modelfile_name!r}")
        seen_names.add(name)
        seen_modelfiles.add(modelfile_name)
        if category == "experiments" and not name.startswith("exp-"):
            raise ModelError(f"{context}: experiment Ollama names must start with 'exp-'")

        modelfile = modelfile_dir / modelfile_name
        metadata = read_modelfile_metadata(modelfile)
        expected = {
            "name": name,
            "gguf": gguf,
            "from": str(model_output_path(defaults, model)),
        }
        if strict_metadata:
            expected.update(
                repository=model["repository"],
                revision=model["revision"],
            )
        for key, value in expected.items():
            if metadata[key] != value:
                raise ModelError(
                    f"{modelfile}: {key} metadata is {metadata[key]!r}, expected {value!r}"
                )
    return defaults, models


def parse_selection(selection: str, count: int) -> list[int]:
    if count <= 0:
        return []
    if not selection.strip() or selection.strip().lower() == "all":
        return list(range(count))
    selected: list[int] = []
    for raw_part in selection.split(","):
        part = raw_part.strip().replace(" ", "")
        if not part:
            continue
        match = re.fullmatch(r"([0-9]+)-([0-9]+)", part)
        if match:
            start, end = map(int, match.groups())
            if start > end:
                start, end = end, start
            if start >= count:
                print(f"WARNING: selection {part!r} is outside 0-{count - 1}; ignoring it.", file=sys.stderr)
                continue
            if end >= count:
                print(f"WARNING: selection {part!r} extends beyond {count - 1}; truncating it.", file=sys.stderr)
                end = count - 1
            selected.extend(range(start, end + 1))
            continue
        if part.isdigit():
            index = int(part)
            if index < count:
                selected.append(index)
            else:
                print(f"WARNING: selection {part!r} is outside 0-{count - 1}; ignoring it.", file=sys.stderr)
            continue
        print(f"WARNING: invalid selection {part!r}; ignoring it.", file=sys.stderr)
    return list(dict.fromkeys(selected))


def list_models(models: list[dict], include_disabled: bool = False) -> list[dict]:
    visible = [model for model in models if include_disabled or model["enabled"]]
    for index, model in enumerate(visible):
        state = "enabled" if model["enabled"] else "disabled"
        name = model.get("name", model["id"])
        print(f"  {index:2d}) {name:<52} [{model['provider']}, {state}]")
    return visible


def _command_path(command: str) -> str:
    path = shutil.which(command)
    if path is None:
        raise ModelError(f"missing command: {command}")
    return path


def _ollama_identity() -> tuple[int, int]:
    try:
        account = pwd.getpwnam("ollama")
        group = grp.getgrnam("ollama")
    except KeyError as error:
        raise ModelError("ollama user or group is missing; run bc250-install-ollama first") from error
    return account.pw_uid, group.gr_gid


def _ensure_directory(path: Path, uid: int, gid: int, mode: int = 0o750) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chown(path, uid, gid)
    os.chmod(path, mode)


def _run_as_ollama(command: list[str], environment: dict[str, str]) -> subprocess.CompletedProcess:
    runuser = _command_path("runuser")
    env_args = [f"{key}={value}" for key, value in environment.items()]
    return subprocess.run([runuser, "-u", "ollama", "--", "env", *env_args, *command], check=False)


def _api_base(host: str) -> str:
    host = host.rstrip("/")
    return host if "://" in host else f"http://{host}"


def _api_request(host: str, endpoint: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{_api_base(host)}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise ModelError(f"Ollama request failed at {_api_base(host)}{endpoint}: {error}") from error


def _prompt_hf_token() -> str:
    token = os.environ.get("HF_TOKEN", "")
    if token:
        return token
    try:
        with open("/dev/tty", "r+", encoding="utf-8") as tty:
            return getpass.getpass("Hugging Face token (Enter for none): ", stream=tty)
    except OSError:
        return ""


def _verify_checksum(path: Path, expected: str) -> None:
    if not expected:
        return
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != expected:
        raise ModelError(f"checksum mismatch for {path}: got {actual}, expected {expected}")


def move_download(staged: Path, output: Path) -> None:
    """Place a staged download atomically, including across filesystems."""
    try:
        os.replace(staged, output)
        return
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output.name}.",
            suffix=".partial",
            dir=output.parent,
            delete=False,
        ) as target:
            temporary = Path(target.name)
            with staged.open("rb") as source:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, output)
        staged.unlink()
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def resolve_model(models: list[dict], model_id: str, provider: str | None = None) -> dict:
    for model in models:
        if model["enabled"] and model["id"] == model_id:
            if provider is None or model["provider"] == provider:
                return model
    qualifier = f" {provider}" if provider else ""
    raise ModelError(f"enabled{qualifier} model id not found: {model_id}")


def _runtime_model(model: dict, args: argparse.Namespace) -> dict:
    runtime = dict(model)
    for argument, key in (("revision", "revision"), ("sha256", "sha256")):
        value = getattr(args, argument, None)
        if value is not None:
            runtime[key] = value
    if not runtime.get("revision"):
        raise ModelError("--revision must not be empty")
    checksum = runtime.get("sha256", "")
    if checksum and not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ModelError("--sha256 must be 64 lowercase hexadecimal characters")
    return runtime


def install_models(
    defaults: dict,
    models: list[dict],
    modelfile_dir: Path,
    args: argparse.Namespace,
) -> int:
    if os.geteuid() != 0:
        raise ModelError("run with sudo")
    uid, gid = _ollama_identity()
    _command_path("hf")
    _command_path("runuser")

    if len(models) != 1 and any(getattr(args, key) is not None for key in ("revision", "sha256")):
        raise ModelError("--revision and --sha256 require exactly one selected model")
    runtime_models = [_runtime_model(model, args) for model in models]
    needs_ollama = any(model["provider"] == "ollama" for model in runtime_models)
    host = (
        args.host
        or os.environ.get("OLLAMA_HOST")
        or os.environ.get("OLLAMA_URL")
        or defaults.get("ollama_host", "127.0.0.1:11434")
    )
    ollama_bin = ""
    if needs_ollama:
        ollama_bin = _command_path("ollama")
        _api_request(host, "/api/tags")

    hf_home = Path(os.environ.get("HF_HOME", "/var/llm/hf-cache"))
    download_root = Path(
        os.environ.get(
            "DOWNLOAD_DIR",
            str(hf_home / "downloads" / defaults["download_namespace"]),
        )
    )
    destination_override = args.destination or os.environ.get("DEST")
    modelfile_destination = os.environ.get("MODELFILE_DIR", defaults.get("modelfile_destination", ""))

    for path in (hf_home, hf_home / "hub", hf_home / "downloads", download_root):
        _ensure_directory(path, uid, gid)
    if modelfile_destination:
        _ensure_directory(Path(modelfile_destination), 0, gid)

    token = _prompt_hf_token()
    hf_environment = {
        "HOME": "/var/lib/ollama",
        "HF_TOKEN": token,
        "HF_HOME": str(hf_home),
        "HF_HUB_CACHE": str(hf_home / "hub"),
        "HF_HUB_DISABLE_XET": "1",
    }
    if token:
        result = _run_as_ollama([_command_path("hf"), "auth", "whoami"], hf_environment)
        if result.returncode != 0:
            print("WARNING: Hugging Face token was not accepted; continuing without it.", file=sys.stderr)
            token = ""
            hf_environment["HF_TOKEN"] = ""

    failures: list[str] = []
    for model in runtime_models:
        label = model.get("name", model["id"])
        print(f"\n>>> {label} [{model['provider']}]")
        try:
            output = model_output_path(defaults, model, destination_override)
            _ensure_directory(output.parent, uid, gid)
            download_dir = download_root / model["id"] if defaults.get("layout", "flat") == "by-id" else download_root
            _ensure_directory(download_dir, uid, gid)
            staged = download_dir / model["gguf"]

            minimum = args.min_free_bytes
            if minimum is None:
                minimum = int(defaults.get("min_free_bytes", 0))
            if not output.exists() and minimum and shutil.disk_usage(output.parent).free < minimum:
                raise ModelError(f"at least {minimum // (1024**3)} GiB free is required in {output.parent}")

            if output.is_file() and output.stat().st_size > 0:
                print("    GGUF exists, skipping download")
            else:
                command = [_command_path("hf"), "download", model["repository"], model["gguf"]]
                if model["revision"] != "latest":
                    command.extend(("--revision", model["revision"]))
                command.extend(("--local-dir", str(download_dir)))
                if _run_as_ollama(command, hf_environment).returncode != 0:
                    raise ModelError("download failed")
                if not staged.is_file() or staged.stat().st_size == 0:
                    raise ModelError(f"download completed without {staged}")
                move_download(staged, output)

            _verify_checksum(output, model.get("sha256", ""))
            if not model.get("sha256"):
                print(f"    no checksum configured; using revision {model['revision']!r}")
            os.chown(output, 0, gid)
            os.chmod(output, 0o640)

            if model["provider"] == "download-only":
                print("    downloaded for llama.cpp")
                continue

            source_modelfile = modelfile_dir / model["modelfile"]
            temporary_modelfile = False
            if modelfile_destination:
                create_modelfile = Path(modelfile_destination) / model["modelfile"]
            else:
                with tempfile.NamedTemporaryFile(
                    prefix=".bc250-model-",
                    suffix=".Modelfile",
                    dir=output.parent,
                    delete=False,
                ) as stream:
                    create_modelfile = Path(stream.name)
                temporary_modelfile = True
            try:
                render_modelfile(source_modelfile, create_modelfile, model, output)
                os.chown(create_modelfile, 0, gid)
                os.chmod(create_modelfile, 0o640)
                result = _run_as_ollama(
                    [ollama_bin, "create", model["name"], "-f", str(create_modelfile)],
                    {"HOME": "/var/lib/ollama", "OLLAMA_HOST": host},
                )
                if result.returncode != 0:
                    raise ModelError("ollama create failed")
                _api_request(host, "/api/show", {"model": model["name"]})
                print("    installed")
            finally:
                if temporary_modelfile:
                    create_modelfile.unlink(missing_ok=True)
        except (ModelError, OSError) as error:
            print(f"    ERROR: {error}", file=sys.stderr)
            failures.append(label)

    if needs_ollama:
        subprocess.run([ollama_bin, "list"], env={**os.environ, "OLLAMA_HOST": host}, check=False)
    if failures:
        print(f"\nFailed: {' '.join(failures)}", file=sys.stderr)
        return 2
    print(f"\nDone: {len(runtime_models)} model(s) processed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bc250-model", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list catalog entries")
    list_parser.add_argument("category", choices=CATEGORIES)
    list_parser.add_argument("--all", action="store_true", help="include disabled entries")
    list_parser.add_argument("--source", type=Path)
    list_parser.add_argument("--modelfile-dir", type=Path)

    resolve_parser = subparsers.add_parser("resolve", help="resolve one enabled catalog entry")
    resolve_parser.add_argument("category", choices=CATEGORIES)
    resolve_parser.add_argument("id")
    resolve_parser.add_argument("--provider", choices=("ollama", "download-only"))
    resolve_parser.add_argument("--source", type=Path)
    resolve_parser.add_argument("--modelfile-dir", type=Path)

    install_parser = subparsers.add_parser("install", help="download and register selected entries")
    install_parser.add_argument("category", choices=CATEGORIES)
    install_parser.add_argument("selection", nargs="?")
    install_parser.add_argument("--list", action="store_true", help="list enabled entries without installing")
    install_parser.add_argument("--source", type=Path)
    install_parser.add_argument("--modelfile-dir", type=Path)
    install_parser.add_argument("--host")
    install_parser.add_argument("--revision")
    install_parser.add_argument("--sha256")
    install_parser.add_argument("--destination")
    install_parser.add_argument("--min-free-bytes", type=int)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    default_source, default_modelfile_dir = default_paths(args.category)
    source = args.source or (Path(os.environ["SOURCE_FILE"]) if "SOURCE_FILE" in os.environ else default_source)
    modelfile_dir = args.modelfile_dir or (
        Path(os.environ["MODELFILE_SOURCE_DIR"])
        if "MODELFILE_SOURCE_DIR" in os.environ
        else default_modelfile_dir
    )
    defaults, models = load_catalog(source, args.category, modelfile_dir)

    if args.command == "list":
        print(f"{args.category.title()} models:")
        list_models(models, args.all)
        return 0
    if args.command == "resolve":
        model = resolve_model(models, args.id, args.provider)
        print(
            "\t".join(
                (
                    str(model_output_path(defaults, model)),
                    str(model.get("context", "")),
                    str(model.get("draft", "")),
                )
            )
        )
        return 0

    enabled = [model for model in models if model["enabled"]]
    print(f"Available {args.category} models:")
    list_models(enabled)
    if args.list:
        return 0
    if not enabled:
        print(f"No {args.category} models are enabled in {source}.")
        return 0
    selection = args.selection
    if selection is None:
        try:
            with open("/dev/tty", "r+", encoding="utf-8") as tty:
                tty.write("Indices (for example 0,2-4) or Enter for all: ")
                tty.flush()
                selection = tty.readline().strip()
        except OSError:
            selection = "all"
    indices = parse_selection(selection, len(enabled))
    if not indices:
        raise ModelError("no valid models selected")
    return install_models(defaults, [enabled[index] for index in indices], modelfile_dir, args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ModelError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
