#!/usr/bin/env python3
"""Semantic repository checks used locally, in CI, and by the RPM build."""

from __future__ import annotations

import ast
import glob
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging/bc250-llm-server.spec"
FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)
    print(f"ERROR: {message}", file=sys.stderr)


def require(relative: str, executable: bool = False) -> Path:
    path = ROOT / relative
    if not path.is_file():
        fail(f"missing {relative}")
    elif executable and not (path.stat().st_mode & 0o111):
        fail(f"not executable: {relative}")
    return path


def parse_spec_macro(spec_text: str, name: str) -> str:
    match = re.search(rf"^%global\s+{re.escape(name)}\s+(\S+)$", spec_text, re.MULTILINE)
    return match.group(1) if match else ""


def load_modelctl():
    module_path = ROOT / "models/modelctl.py"
    spec = importlib.util.spec_from_file_location("bc250_modelctl", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load models/modelctl.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_source_preparer():
    module_path = ROOT / "scripts/prepare-sources.py"
    spec = importlib.util.spec_from_file_location("bc250_prepare_sources", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load scripts/prepare-sources.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_required_files() -> None:
    required = [
        "README.md",
        "TLDR.md",
        "docs/COMMANDS.md",
        "VERSION",
        "Makefile",
        ".github/workflows/build-rpm.yml",
        "packaging/bc250-llm-server.spec",
        "packaging/bc250-llm-server.tmpfiles",
        "packaging/bc250",
        "packaging/install-manifest.tsv",
        "packaging/upstreams.toml",
        "scripts/install-manifest.py",
        "scripts/prepare-sources.py",
        "scripts/make-source-tarball.sh",
        "models/modelctl.py",
        "models/sources/production.toml",
        "models/sources/experiments.toml",
        "models/mtp/models.toml",
        "models/sources/task.toml",
        "models/sources/coding.toml",
        "models/embedding/README.md",
        "models/embedding/pull-embedding-model.sh",
        "models/experiments/README.md",
        "models/experiments/compare-experiments.sh",
        "models/mtp/README.md",
        "models/mtp/run-mtp-llamacpp.sh",
        "models/setup-ollama-instance.sh",
        "models/task-model/setup-ollama.sh",
        "models/coding-agent/setup-ollama.sh",
        "maintenance/owui-maintenance@.service",
        "licenses/LICENSE",
        "licenses/THIRD_PARTY_NOTICES.md",
        "licenses/40CU-LICENSE-NOTICE",
    ]
    executables = {
        "packaging/bc250",
        "scripts/install-manifest.py",
        "scripts/prepare-sources.py",
        "models/modelctl.py",
        "models/embedding/pull-embedding-model.sh",
        "models/experiments/compare-experiments.sh",
        "models/mtp/run-mtp-llamacpp.sh",
        "models/setup-ollama-instance.sh",
        "models/task-model/setup-ollama.sh",
        "models/coding-agent/setup-ollama.sh",
    }
    for relative in required:
        require(relative, relative in executables)


def check_python() -> None:
    files = [
        file
        for directory in ("models", "scripts", "tests")
        for file in (ROOT / directory).rglob("*.py")
    ]
    for file in sorted(files):
        try:
            ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except (OSError, SyntaxError) as error:
            fail(f"Python syntax error in {file.relative_to(ROOT)}: {error}")


def check_catalogs() -> None:
    modelctl = load_modelctl()
    expected_enabled = {
        "production": 0,
        "experiments": 0,
        "mtp": 0,
        "task": 1,
        "coding": 2,
    }
    for category in modelctl.CATEGORIES:
        source = (
            ROOT / "models/mtp/models.toml"
            if category == "mtp"
            else ROOT / "models/sources" / f"{category}.toml"
        )
        modelfiles = ROOT / "models/modelfiles" / category
        try:
            _defaults, models = modelctl.load_catalog(
                source, category, modelfiles, strict_metadata=True
            )
        except modelctl.ModelError as error:
            fail(str(error))
            continue
        enabled = [model for model in models if model["enabled"]]
        if len(enabled) != expected_enabled[category]:
            fail(f"{category} catalog must have {expected_enabled[category]} enabled model(s)")
        referenced = {
            model["modelfile"] for model in models if model["provider"] == "ollama"
        }
        packaged = {path.name for path in modelfiles.glob("*.Modelfile")}
        if referenced != packaged:
            missing = sorted(referenced - packaged)
            obsolete = sorted(packaged - referenced)
            if missing:
                fail(f"{category} catalog references missing Modelfiles: {', '.join(missing)}")
            if obsolete:
                fail(f"{category} has unreferenced Modelfiles: {', '.join(obsolete)}")

    for modelfile in sorted((ROOT / "models/modelfiles").rglob("*.Modelfile")):
        text = modelfile.read_text(encoding="utf-8")
        if text.count("PARAMETER num_gpu 99") != 1:
            fail(f"{modelfile.relative_to(ROOT)} must set num_gpu 99 exactly once")
        if text.count("PARAMETER num_keep 256") != 1:
            fail(f"{modelfile.relative_to(ROOT)} must set num_keep 256 exactly once")


def check_upstreams(spec_text: str) -> None:
    try:
        with (ROOT / "packaging/upstreams.toml").open("rb") as stream:
            lock = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        fail(f"cannot parse packaging/upstreams.toml: {error}")
        return
    sources = lock.get("sources", [])
    if lock.get("schema") != 1 or len(sources) != 3:
        fail("upstream lock must use schema 1 and contain three sources")
        return
    expected_macros = {"governor": "governor_commit", "unlock": "unlock_commit", "live_manager": "live_manager_commit"}
    source_preparer = load_source_preparer()
    for source in sources:
        source_id = source.get("id", "")
        commit = source.get("commit", "")
        checksum = source.get("sha256", "")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            fail(f"upstream {source_id}: invalid commit")
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            fail(f"upstream {source_id}: invalid sha256")
        macro = expected_macros.get(source_id)
        if macro and parse_spec_macro(spec_text, macro) != commit:
            fail(f"spec macro {macro} differs from upstream lock")
        if source_id == "governor" and parse_spec_macro(spec_text, "governor_version") != source.get("version"):
            fail("spec governor_version differs from upstream lock")
        if source_id == "unlock":
            required = {item.format(commit=commit) for item in source.get("required", [])}
            prefix = f"bc250-40cu-unlock-{commit}"
            for member in (
                f"{prefix}/README.md",
                f"{prefix}/scripts/bc250-enable-40cu-fedora.sh",
                f"{prefix}/patch/bc250-40cu-amdgpu.patch",
            ):
                if member not in required:
                    fail(f"unlock source lock does not require {member}")
        archive = ROOT / "sources" / source["archive"].format(commit=commit)
        if archive.is_file():
            try:
                source_preparer.verify_archive(source, archive)
            except (OSError, source_preparer.SourceError, source_preparer.tarfile.TarError) as error:
                fail(str(error))
    result = subprocess.run(
        [str(ROOT / "scripts/prepare-sources.py"), "--print-files"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode or len(result.stdout.split()) != 4:
        fail("prepare-sources.py --print-files did not resolve four RPM archives")


def check_spec(spec_text: str) -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    match = re.search(r"^Version:\s+(\S+)$", spec_text, re.MULTILINE)
    if not match or match.group(1) != version:
        fail("VERSION and spec Version differ")
    release = re.search(r"^Release:\s+(\S+)$", spec_text, re.MULTILINE)
    changelog = re.search(r"^\* .+ - (\S+)$", spec_text.split("%changelog", 1)[-1], re.MULTILINE)
    if release and changelog:
        release_base = release.group(1).removesuffix("%{?dist}")
        if changelog.group(1) != f"{version}-{release_base}":
            fail("top changelog entry does not match Version-Release")
    else:
        fail("spec Release or changelog entry missing")

    required_fragments = [
        "License:        GPL-2.0-only AND MIT",
        "Requires:       umr",
        "python3 scripts/install-manifest.py",
        "%files -f %{payload_filelist}",
        "%license licenses/LICENSE governor-src/LICENSE licenses/40CU-LICENSE-NOTICE",
        "patch -d unlock-src -p1 < patches/40cu-fedora-helper.patch",
        "systemctl try-restart tika.service open-webui.service",
    ]
    for fragment in required_fragments:
        if fragment not in spec_text:
            fail(f"spec is missing: {fragment}")
    if "packaging/wrappers" in spec_text or "rm -rf %{buildroot}" in spec_text:
        fail("spec retains obsolete wrapper or buildroot handling")
    if "migrate-legacy" in spec_text:
        fail("spec retains obsolete pre-production catalog migration")
    post = spec_text.split("%post\n", 1)[-1].split("%preun", 1)[0]
    if re.search(r"bc250-40cu|amdgpu\.ko|depmod|dracut|reboot|grubby", post):
        fail("RPM post-install scriptlet manipulates kernel/CU state")


def check_install_manifest() -> None:
    manifest = ROOT / "packaging/install-manifest.tsv"
    definitions = {
        "bindir": "/usr/bin",
        "libexec": "/usr/libexec/bc250-llm-server",
        "share": "/usr/share/bc250-llm-server",
        "config": "/etc/bc250-llm-server",
        "sysconfdir": "/etc",
        "datadir": "/usr/share",
        "docdir": "/usr/share/doc/bc250-llm-server",
        "unitdir": "/usr/lib/systemd/system",
        "tmpfilesdir": "/usr/lib/tmpfiles.d",
        "presetdir": "/usr/lib/systemd/system-preset",
        "modulesloaddir": "/usr/lib/modules-load.d",
        "modprobedir": "/usr/lib/modprobe.d",
        "dbusdir": "/usr/share/dbus-1/system.d",
        "unlock_commit": "0" * 40,
        "live_manager_commit": "1" * 40,
    }
    destinations: set[str] = set()
    external_prefixes = ("governor-src/", "unlock-src/", "live-manager-src/")
    for line_number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        fields = raw.split("\t")
        if len(fields) != 4:
            fail(f"install manifest line {line_number} does not have four fields")
            continue
        kind, mode, source, destination = fields
        try:
            int(mode, 8)
            destination = destination.format_map(definitions)
            source = source.format_map(definitions)
        except (ValueError, KeyError) as error:
            fail(f"install manifest line {line_number}: {error}")
            continue
        if not destination.startswith("/"):
            fail(f"install manifest line {line_number}: destination is not absolute")
        if kind in {"dir", "ghost", "text", "aliases"}:
            continue
        if source.startswith(external_prefixes):
            continue
        matches = glob.glob(str(ROOT / source))
        if not matches:
            fail(f"install manifest line {line_number}: no source matches {source}")
        if not destination.endswith("/") and destination in destinations:
            fail(f"duplicate install destination: {destination}")
        destinations.add(destination)


def check_configs() -> None:
    try:
        with (ROOT / "governor/config.toml").open("rb") as stream:
            governor = tomllib.load(stream)
        ET.parse(ROOT / "governor/com.cyanskillfish.Governor.conf")
    except (OSError, ValueError, tomllib.TOMLDecodeError, ET.ParseError) as error:
        fail(f"governor configuration parse failed: {error}")
        return
    frequency = governor.get("frequency-range", {})
    if frequency.get("min") != 350:
        fail("governor minimum must remain 350 MHz")
    safe_points = governor.get("safe-points", [])
    for expected in ({"frequency": 350, "voltage": 700}, {"frequency": 2000, "voltage": 960}):
        if not any(all(point.get(key) == value for key, value in expected.items()) for point in safe_points):
            fail(f"governor safe point missing: {expected}")

    timers = {
        "maintenance/owui-backup-config.timer": "Unit=owui-maintenance@backup-config.service",
        "maintenance/owui-backup-users.timer": "Unit=owui-maintenance@backup-users.service",
        "maintenance/owui-prune.timer": "Unit=owui-maintenance@prune-uploads.service",
    }
    for relative, line in timers.items():
        if line not in (ROOT / relative).read_text(encoding="utf-8"):
            fail(f"{relative} does not target the maintenance template")


def check_security_and_stale_paths() -> None:
    excluded = {".git", "build", "dist", "rpmbuild", "sources", "__pycache__"}
    secret_pattern = re.compile(r"hf_[A-Za-z0-9]{20,}|WEBUI_ADMIN_PASSWORD=|WEBUI_SECRET_KEY=")
    site_pattern = re.compile(r"llm_admin|llm\.office\.local")
    home_pattern = re.compile(r"/home/[^/\s]+")
    stale = (
        "model-sources.sh",
        "experiment-sources.sh",
        "setup-gemma-1b-task.sh",
        "setup-coding-agent.sh",
        "packaging/wrappers",
    )
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in excluded for part in path.relative_to(ROOT).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = str(path.relative_to(ROOT))
        if relative not in {"scripts/validate.py", "verify.sh"} and secret_pattern.search(text):
            fail(f"secret-like value found in {relative}")
        if relative != "scripts/validate.py" and site_pattern.search(text):
            fail(f"site-specific account or hostname found in {relative}")
        if path.suffix not in {".md", ".example"} and relative != "scripts/validate.py" and home_pattern.search(text):
            fail(f"hard-coded operator home found in {relative}")
        if path.suffix == ".md" and any(value in text for value in stale):
            fail(f"stale model-management path in {relative}")


def check_runtime_contracts() -> None:
    dispatcher = ROOT / "packaging/bc250"
    result = subprocess.run(
        [str(dispatcher), "--list-aliases"],
        check=False,
        stdout=subprocess.PIPE,
        text=True,
    )
    aliases = result.stdout.splitlines()
    if result.returncode or len(aliases) != len(set(aliases)) or len(aliases) < 20:
        fail("dispatcher aliases are missing, duplicated, or unreadable")
    for required_alias in (
        "model",
        "fetch-models",
        "fetch-experiments",
        "fetch-mtp",
        "verify",
        "verify-lan",
    ):
        if required_alias not in aliases:
            fail(f"dispatcher is missing compatibility alias {required_alias}")

    instance_setup = (ROOT / "models/setup-ollama-instance.sh").read_text(encoding="utf-8")
    for fragment in (
        'port="${TASK_PORT:-11435}"',
        'service="ollama-task.service"',
        'port="${CODING_AGENT_PORT:-11436}"',
        'service="ollama-agent.service"',
    ):
        if fragment not in instance_setup:
            fail(f"isolated Ollama setup is missing: {fragment}")
    for obsolete in (ROOT / "task-model", ROOT / "coding-agent", ROOT / "experiments"):
        if obsolete.exists():
            fail(f"obsolete top-level model helper remains: {obsolete.name}")

    workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(encoding="utf-8")
    if (
        "continue-on-error: true" in workflow
        or "set -o pipefail" not in workflow
        or "dist/RPM-CONTENTS.txt" not in workflow
    ):
        fail("CI rpmlint must remain gating and pipefail-safe")
    for relative, pattern in (
        ("containers/open-webui.container", r"^Image=ghcr\.io/open-webui/open-webui@sha256:[0-9a-f]{64}$"),
        ("containers/tika.container", r"^Image=docker\.io/apache/tika@sha256:[0-9a-f]{64}$"),
    ):
        if not re.search(pattern, (ROOT / relative).read_text(encoding="utf-8"), re.MULTILINE):
            fail(f"container image is not digest-pinned: {relative}")

    openwebui = (ROOT / "containers/open-webui.container").read_text(encoding="utf-8")
    if "Memory=2g" not in openwebui:
        fail("Open WebUI container memory limit must remain 2 GiB")
    nginx_map = (ROOT / "nginx/websocket-map.conf").read_text(encoding="utf-8")
    nginx_proxy = (ROOT / "nginx/bc250-llm-server.conf").read_text(encoding="utf-8")
    if "map $http_upgrade $connection_upgrade" not in nginx_map:
        fail("nginx WebSocket map is missing")
    if "proxy_set_header Connection $connection_upgrade;" not in nginx_proxy:
        fail("nginx proxy does not use the WebSocket map")

    memory = (ROOT / "system/memory-profile.sh").read_text(encoding="utf-8")
    if 'FULL_TTM_ARGS="ttm.pages_limit=4194304"' not in memory:
        fail("reviewed 16 GiB TTM profile is missing")
    if 'PARAM_NAMES="amdgpu.gttsize ttm.pages_limit ttm.page_pool_size amdgpu.ppfeaturemask"' not in memory:
        fail("memory profile does not remove current and legacy arguments")
    active_memory_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "system").glob("*")
        if path.is_file()
    ) + (ROOT / "docs/MEMORY.md").read_text(encoding="utf-8")
    if re.search(r"ttm\.pages_limit=3959290|amdgpu\.gttsize=(14750|15258)", active_memory_text):
        fail("obsolete memory profile remains in active content")

    diagnose = (ROOT / "monitoring/llm-run-diagnose.sh").read_text(encoding="utf-8")
    if "ttm.pages_limit = 4194304" not in diagnose or re.search(r"3959290|amdgpu\.gttsize=15258", diagnose):
        fail("model-run diagnostic does not use the reviewed TTM profile")

    installer = (ROOT / "system/install-ollama.sh").read_text(encoding="utf-8")
    if 'VERSION="${OLLAMA_VERSION:-0.32.1}"' not in installer or "Installer SHA-256:" not in installer:
        fail("Ollama installer version/audit contract changed")
    mtp_runner = (ROOT / "models/mtp/run-mtp-llamacpp.sh").read_text(encoding="utf-8")
    if 'resolved="$("$MANAGER" resolve mtp "$choice"' not in mtp_runner:
        fail("MTP runner does not safely quote the model manager path")
    if "--provider download-only" not in mtp_runner:
        fail("MTP runner does not restrict catalog resolution to download-only entries")
    modelctl_source = (ROOT / "models/modelctl.py").read_text(encoding="utf-8")
    if "error.errno != errno.EXDEV" not in modelctl_source or "shutil.copyfileobj" not in modelctl_source:
        fail("model manager lacks the cross-filesystem download fallback")
    cu_wrapper = (ROOT / "system/40cu.sh").read_text(encoding="utf-8")
    if "check_governor_limit" in cu_wrapper or "Clock and voltage policy belongs entirely to the operator" not in cu_wrapper:
        fail("40-CU command must leave governor policy to the operator")


def main() -> int:
    check_required_files()
    check_python()
    spec_text = SPEC.read_text(encoding="utf-8")
    check_catalogs()
    check_upstreams(spec_text)
    check_spec(spec_text)
    check_install_manifest()
    check_configs()
    check_security_and_stale_paths()
    check_runtime_contracts()
    if FAILURES:
        print(f"Validation failed with {len(FAILURES)} error(s).", file=sys.stderr)
        return 1
    print("Semantic repository checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
