#!/usr/bin/env python3
"""Fetch and register BC-250 model catalog entries."""

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
CATEGORIES = ("production", "experiments", "mtp", "task", "coding")
INSTALLED_SHARE = Path(f"/usr/share/{PROJECT}/model-management")
INSTALLED_CONFIG = Path(f"/etc/{PROJECT}")


class ModelError(RuntimeError):
    """A concise error suitable for command-line output."""


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


def default_paths(category: str) -> tuple[Path, Path]:
    script_dir = Path(__file__).resolve().parent
    source_catalog = (
        script_dir / "mtp/models.toml"
        if category == "mtp"
        else script_dir / "sources" / f"{category}.toml"
    )
    if source_catalog.is_file():
        return source_catalog, script_dir / "modelfiles"
    if category in {"production", "experiments", "mtp"}:
        catalog = INSTALLED_CONFIG / f"{category}-models.toml"
    else:
        catalog = INSTALLED_SHARE / "sources" / f"{category}.toml"
    return catalog, INSTALLED_SHARE / "modelfiles"


def model_path(defaults: dict, model: dict, destination: str | None = None) -> Path:
    root = Path(destination or defaults["destination"])
    if defaults.get("layout", "flat") == "by-id":
        root /= model["id"]
    return root / model["gguf"]


def modelfile_metadata(path: Path) -> dict[str, str]:
    values = {"name": "", "repository": "", "revision": "", "gguf": "", "from": ""}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ModelError(f"cannot read Modelfile {path}: {error}") from error
    for line in lines:
        if line.startswith("# Ollama model: "):
            values["name"] = line.removeprefix("# Ollama model: ").strip()
        elif line.startswith("# Source: ") and " @ " in line:
            source = line.removeprefix("# Source: ").strip()
            values["repository"], values["revision"] = source.rsplit(" @ ", 1)
        elif line.startswith("# GGUF: "):
            values["gguf"] = line.removeprefix("# GGUF: ").strip()
        elif line.startswith("FROM ") and not values["from"]:
            values["from"] = line.split(maxsplit=1)[1].strip()
    return values


def load_catalog(path: Path, category: str, modelfile_dir: Path) -> tuple[dict, list[dict]]:
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
    require_string(defaults, "destination", f"{path}: defaults")
    require_string(defaults, "download_namespace", f"{path}: defaults")
    if defaults.get("layout", "flat") not in {"flat", "by-id"}:
        raise ModelError(f"{path}: layout must be flat or by-id")
    minimum = defaults.get("min_free_bytes", 0)
    if type(minimum) is not int or minimum < 0:
        raise ModelError(f"{path}: min_free_bytes must be a non-negative integer")

    prefixes = {
        "production": "prod-",
        "experiments": "exp-",
        "task": "task-",
        "coding": "agentic-",
    }
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    seen_modelfiles: set[str] = set()
    for index, model in enumerate(models):
        context = f"{path}: models[{index}]"
        if not isinstance(model, dict):
            raise ModelError(f"{context} must be a table")
        if not isinstance(model.get("enabled"), bool):
            raise ModelError(f"{context}: enabled must be true or false")
        provider = require_string(model, "provider", context)
        if provider not in {"ollama", "download-only"}:
            raise ModelError(f"{context}: unsupported provider {provider!r}")
        model_id = require_string(model, "id", context)
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", model_id) is None:
            raise ModelError(f"{context}: id must be a path-safe identifier")
        if model_id in seen_ids:
            raise ModelError(f"{path}: duplicate model id {model_id!r}")
        seen_ids.add(model_id)
        require_string(model, "repository", context)
        require_string(model, "revision", context)
        require_filename(model, "gguf", context)
        checksum = model.get("sha256", "")
        if not isinstance(checksum, str) or (
            checksum and re.fullmatch(r"[0-9a-f]{64}", checksum) is None
        ):
            raise ModelError(f"{context}: sha256 must be 64 lowercase hexadecimal characters")

        if provider == "download-only":
            for key in ("context", "draft"):
                if type(model.get(key)) is not int or model[key] <= 0:
                    raise ModelError(f"{context}: {key} must be a positive integer")
            if "name" in model or "modelfile" in model:
                raise ModelError(f"{context}: download-only entries cannot define Ollama fields")
            continue

        name = require_string(model, "name", context)
        modelfile_name = require_filename(model, "modelfile", context)
        if name in seen_names or modelfile_name in seen_modelfiles:
            raise ModelError(f"{context}: duplicate Ollama name or Modelfile")
        seen_names.add(name)
        seen_modelfiles.add(modelfile_name)
        if modelfile_name != f"{name}.Modelfile":
            raise ModelError(f"{context}: Modelfile filename must match the Ollama name")
        prefix = prefixes.get(category)
        if prefix and not name.startswith(prefix):
            raise ModelError(f"{context}: Ollama name must start with {prefix!r}")

        template = modelfile_dir / modelfile_name
        expected = {
            "name": name,
            "repository": model["repository"],
            "revision": model["revision"],
            "gguf": model["gguf"],
            "from": str(model_path(defaults, model)),
        }
        actual = modelfile_metadata(template)
        for key, value in expected.items():
            if actual[key] != value:
                raise ModelError(f"{template}: {key} is {actual[key]!r}, expected {value!r}")
        text = template.read_text(encoding="utf-8")
        for parameter in ("PARAMETER num_gpu 99", "PARAMETER num_keep 256"):
            if len(re.findall(rf"^{re.escape(parameter)}$", text, re.MULTILINE)) != 1:
                raise ModelError(f"{template}: expected exactly one {parameter!r}")
    return defaults, models


def select_models(models: list[dict], selection: str) -> list[dict]:
    if not models:
        return []
    value = selection.strip()
    if not value or value.lower() == "all":
        return list(models)
    lookup: dict[str, int] = {}
    for index, model in enumerate(models):
        lookup[model["id"]] = index
        if model.get("name"):
            lookup[model["name"]] = index
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
        state = "enabled" if model["enabled"] else "disabled"
        print(f"  {index:2d}) {model.get('name', model['id']):<56} [{model['provider']}, {state}]")


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
        # Hugging Face suppresses its progress renderer when output is captured.
        # A small PTY keeps live byte progress visible in installer transcripts.
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
    if token and run_as_ollama([hf_bin, "auth", "whoami"], hf_environment(token, hf_home)).returncode == 0:
        print("Using the validated Hugging Face token.")
        return token
    if token:
        print("WARNING: Hugging Face rejected the token; downloading anonymously.", file=sys.stderr)
    else:
        print("Using anonymous Hugging Face downloads.")
    return ""


def render_modelfile(source: Path, destination: Path, model: dict, output: Path) -> None:
    lines = source.read_text(encoding="utf-8").splitlines()
    rendered: list[str] = []
    for line in lines:
        if line.startswith("# Ollama model: "):
            line = f"# Ollama model: {model['name']}"
        elif line.startswith("# Source: "):
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


def install_models(defaults: dict, models: list[dict], modelfiles: Path, args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        raise ModelError("run with sudo")
    if len(models) != 1 and (args.revision is not None or args.sha256 is not None):
        raise ModelError("--revision and --sha256 require one selected model")
    uid, gid = ollama_identity()
    hf_bin = command_path("hf")
    ollama_bin = command_path("ollama") if any(m["provider"] == "ollama" for m in models) else ""
    host = args.host or os.environ.get("OLLAMA_HOST") or os.environ.get("OLLAMA_URL") \
        or defaults.get("ollama_host", "127.0.0.1:11434")
    hf_home = Path(os.environ.get("HF_HOME", f"/var/cache/{PROJECT}/huggingface"))
    download_root = Path(os.environ.get("DOWNLOAD_DIR", str(hf_home / "downloads" / defaults["download_namespace"])))
    modelfile_root = Path(os.environ.get("MODELFILE_DIR", defaults.get("modelfile_destination", ""))) \
        if os.environ.get("MODELFILE_DIR") or defaults.get("modelfile_destination") else None
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
                    raise ModelError(f"{free / 1024**3:.1f} GiB free; {minimum / 1024**3:.1f} GiB required")
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
            runtime_template = modelfile_root / model["modelfile"] if modelfile_root else output.parent / model["modelfile"]
            render_modelfile(modelfiles / model["modelfile"], runtime_template, model, output)
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
        subprocess.run([ollama_bin, "list"], env={**os.environ, "OLLAMA_HOST": host}, check=False)
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
        if defaults.get("layout") == "by-id":
            try:
                output.parent.rmdir()
            except OSError:
                pass
    print(f"\nRemoved {len(models)} model(s). Catalog was not changed.")
    return 0


def catalog_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("category", choices=CATEGORIES)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--modelfile-dir", type=Path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bc250-model", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="list catalog entries")
    catalog_arguments(listing)
    listing.add_argument("--all", action="store_true", help="include disabled entries")
    resolving = commands.add_parser("resolve", help="resolve one enabled entry")
    catalog_arguments(resolving)
    resolving.add_argument("id")
    resolving.add_argument("--provider", choices=("ollama", "download-only"))
    installing = commands.add_parser("install", help="download and register selected entries")
    catalog_arguments(installing)
    installing.add_argument("selection", nargs="?")
    installing.add_argument("--list", action="store_true")
    installing.add_argument("--host")
    installing.add_argument("--revision")
    installing.add_argument("--sha256")
    installing.add_argument("--destination")
    installing.add_argument("--min-free-bytes", type=int)
    installing.add_argument("--token-file", type=Path)
    installing.add_argument("--include-disabled", action="store_true")
    installing.add_argument("--refresh", action="store_true")
    cleaning = commands.add_parser("cleanup", help="remove selected local model artifacts")
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
    default_source, default_modelfiles = default_paths(args.category)
    source = args.source or Path(os.environ.get("SOURCE_FILE", default_source))
    modelfiles = args.modelfile_dir or Path(os.environ.get("MODELFILE_SOURCE_DIR", default_modelfiles))
    defaults, catalog_models = load_catalog(source, args.category, modelfiles)

    if args.command == "list":
        print(f"{args.category.title()} models:")
        print_models([model for model in catalog_models if args.all or model["enabled"]])
        return 0
    if args.command == "resolve":
        for model in catalog_models:
            if model["enabled"] and model["id"] == args.id and (
                args.provider is None or model["provider"] == args.provider
            ):
                print(f"{model_path(defaults, model)}\t{model.get('context', '')}\t{model.get('draft', '')}")
                return 0
        raise ModelError(f"enabled model id not found: {args.id}")

    available = catalog_models if args.command == "cleanup" or args.include_disabled \
        else [model for model in catalog_models if model["enabled"]]
    print(f"Available {args.category} models:")
    print_models(available)
    if args.list:
        return 0
    if not available:
        print(f"No selectable {args.category} models in {source}.")
        return 0
    selection = args.selection
    if selection is None:
        default = "" if args.command == "cleanup" else "all"
        selection = prompt_line("Models (id/name/index/range): ", default)
    if not selection:
        print("Cleanup cancelled.")
        return 0
    selected = select_models(available, selection)
    if args.command == "cleanup":
        return cleanup_models(defaults, selected, args)
    return install_models(defaults, selected, modelfiles, args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ModelError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
