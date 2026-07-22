#!/usr/bin/env python3
"""Run fast, deterministic repository checks needed before an RPM build."""

from __future__ import annotations

import glob
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging/bc250-llm-server.spec"
MANIFEST = ROOT / "packaging/install-manifest.tsv"
UPSTREAMS = ROOT / "packaging/upstreams.toml"
EXCLUDED_TREES = {
    ".git",
    "build",
    "dist",
    "rpmbuild",
    "sources",
    "governor-src",
    "unlock-src",
    "live-manager-src",
    "__pycache__",
}
EXTERNAL_BUILD_TREES = ("governor-src/", "unlock-src/", "live-manager-src/")
FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)
    print(f"ERROR: {message}", file=sys.stderr)


def included_files():
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if path.is_file() and not any(part in EXCLUDED_TREES for part in relative.parts):
            yield relative, path


def check_required_inputs() -> None:
    required = (
        "VERSION",
        "Makefile",
        "install",
        "uninstall.sh",
        ".github/workflows/build-rpm.yml",
        "packaging/bc250-llm-server.spec",
        "packaging/install-manifest.tsv",
        "packaging/bc250-llm-server.sysusers",
        "packaging/upstreams.toml",
        "models/modelctl.py",
        "cmd/system/40cu-module.sh",
        "models/sources/production.toml",
        "models/sources/experiments.toml",
        "models/sources/task.toml",
        "models/sources/coding.toml",
        "models/mtp/models.toml",
        "scripts/install-manifest.py",
        "scripts/make-source-tarball.sh",
        "scripts/prepare-sources.py",
        "licenses/LICENSE",
        "licenses/40CU-LICENSE-NOTICE",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"required build input is missing: {relative}")
    executables = (
        "install",
        "uninstall.sh",
        "packaging/bc250",
        "models/modelctl.py",
        "cmd/system/40cu-module.sh",
        "scripts/install-manifest.py",
        "scripts/make-source-tarball.sh",
        "scripts/prepare-sources.py",
        "scripts/validate.sh",
    )
    for relative in executables:
        path = ROOT / relative
        if path.is_file() and not os.access(path, os.X_OK):
            fail(f"required helper is not executable: {relative}")


def check_syntax() -> None:
    for relative, path in included_files():
        if path.suffix != ".py":
            continue
        try:
            compile(path.read_text(encoding="utf-8"), str(relative), "exec")
        except (OSError, SyntaxError) as error:
            fail(f"Python syntax check failed for {relative}: {error}")


def check_version() -> None:
    try:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        spec = SPEC.read_text(encoding="utf-8")
    except OSError as error:
        fail(f"cannot read version metadata: {error}")
        return
    version_match = re.search(r"^Version:\s*(\S+)\s*$", spec, re.MULTILINE)
    release_match = re.search(r"^Release:\s*([^%\s]+)", spec, re.MULTILINE)
    changelog_match = re.search(r"^%changelog\s*$\n\*[^\n]* - (\S+)\s*$", spec, re.MULTILINE)
    if not version:
        fail("VERSION is empty")
    elif version_match is None or version_match.group(1) != version:
        fail("VERSION and spec Version differ")
    if release_match is None or changelog_match is None:
        fail("spec Release or top changelog entry is malformed")
    elif changelog_match.group(1) != f"{version}-{release_match.group(1)}":
        fail("top changelog entry does not match Version-Release")


def check_configuration() -> None:
    try:
        with (ROOT / "config/governor/config.toml").open("rb") as stream:
            governor = tomllib.load(stream)
        ET.parse(ROOT / "config/governor/com.cyanskillfish.Governor.conf")
    except (OSError, tomllib.TOMLDecodeError, ET.ParseError) as error:
        fail(f"cannot parse governor configuration: {error}")
        return
    if governor.get("frequency-range", {}).get("min") != 350:
        fail("packaged governor minimum must be 350 MHz")
    points = governor.get("safe-points", [])
    if not any(
        isinstance(point, dict)
        and point.get("frequency") == 2000
        and point.get("voltage") == 960
        for point in points
    ):
        fail("packaged governor must retain the 2000 MHz / 960 mV point")


def check_layout_and_docs() -> None:
    for relative in ("cmd", "config", "docs", "examples", "models", "packaging", "scripts", "tests"):
        if not (ROOT / relative).is_dir():
            fail(f"required source group is missing: {relative}/")
    for relative, path in included_files():
        if path.suffix != ".md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            fail(f"cannot read documentation file {relative}: {error}")
            continue
        for target in re.findall(r"\[[^]]*\]\(([^)]+)\)", text):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            local = target.split("#", 1)[0]
            if local and not (path.parent / local).exists():
                fail(f"{relative}: broken relative link: {target}")


def check_repository_safety() -> None:
    legacy_root = "/var" + "/llm"
    for relative, path in included_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if legacy_root in text:
            fail(f"legacy appliance state path remains in {relative}")
        if re.search(r"hf_[A-Za-z0-9]{20,}", text):
            fail(f"Hugging Face token-shaped string found in {relative}")
        if re.search("/" + r"home/[^/\s]+", text):
            fail(f"hard-coded operator home path found in {relative}")
        if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", text):
            fail(f"private-key material found in {relative}")


def check_dispatcher_and_runtime_contracts() -> None:
    result = subprocess.run(
        [str(ROOT / "packaging/bc250"), "--list-aliases"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    aliases = result.stdout.splitlines()
    required = {
        "40cu", "benchmark", "check-temp", "code", "code-commit",
        "compare-experiments", "cu-status", "fetch-experiments", "fetch-models",
        "fetch-mtp", "gitea-review", "install-cu-manager", "install-ollama",
        "memory-profile", "model", "ollama-profile", "pull-embedding-model",
        "run-mtp", "setup-coding-agent", "setup-task-model", "swap-profile",
        "uninstall", "uninstall-info", "verify", "verify-lan",
    }
    if result.returncode != 0:
        fail(f"dispatcher alias listing failed: {result.stderr.strip()}")
    elif len(aliases) != len(set(aliases)) or set(aliases) != required:
        fail("dispatcher command set differs from the supported interface")

    checks = {
        "install": (
            "--exclude=ollama",
            "dnf_action=reinstall",
            "rpm -e --test ollama",
            "packages-added.txt",
            "firewall-http-before",
            'bc250-model install production "$production_selection" --include-disabled',
            "bc250-setup-task-model",
            "bc250-setup-coding-agent",
        ),
        "uninstall.sh": (
            "PURGE-BC250-LLM",
            "packages-added.txt",
            "bc250_cc_write_mode",
            "dracut --force --kver",
            "dnf remove -y bc250-llm-server.x86_64",
            "/var/lib/bc250-llm-server",
            "/var/lib/open-webui",
        ),
        "cmd/system/install-ollama.sh": (
            "env -u OLLAMA_VERSION sh",
            'OLLAMA_VERSION="$VERSION" sh',
        ),
        "models/setup-ollama-instance.sh": (
            "TASK_PORT:-11435",
            "CODING_AGENT_PORT:-11436",
            "/var/lib/bc250-llm-server/ollama/task",
            "/var/lib/bc250-llm-server/ollama/agent",
        ),
        "models/modelctl.py": (
            "OLLAMA_HOST",
            "OLLAMA_URL",
            "HF_TOKEN",
            "terminal=True",
            'command_path("script")',
        ),
        "packaging/bc250-llm-server.spec": (
            "Requires:       zram-generator",
            "systemctl try-restart tika.service open-webui.service",
        ),
    }
    for relative, snippets in checks.items():
        try:
            text = (ROOT / relative).read_text(encoding="utf-8")
        except OSError as error:
            fail(f"cannot read runtime contract {relative}: {error}")
            continue
        for snippet in snippets:
            if snippet not in text:
                fail(f"{relative}: required behavior is missing: {snippet}")

    workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(encoding="utf-8")
    refs = re.findall(r"uses:\s+actions/[^@\s]+@([^\s#]+)", workflow)
    if not refs or any(re.fullmatch(r"[0-9a-f]{40}", ref) is None for ref in refs):
        fail("GitHub Actions must use full reviewed commit IDs")


def check_manifest_sources() -> None:
    try:
        lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        fail(f"cannot read install manifest: {error}")
        return
    for number, line in enumerate(lines, 1):
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 4:
            fail(f"install manifest line {number}: expected four tab-separated fields")
            continue
        kind, mode, source, _destination = fields
        if kind not in {"dir", "file", "config", "ghost", "text", "aliases"}:
            fail(f"install manifest line {number}: unsupported type {kind!r}")
        if re.fullmatch(r"0[0-7]{3}", mode) is None:
            fail(f"install manifest line {number}: invalid mode {mode!r}")
        if kind in {"dir", "ghost", "text"} or source == "-":
            continue
        if source.startswith(EXTERNAL_BUILD_TREES):
            continue
        if not glob.glob(str(ROOT / source)):
            fail(f"install manifest line {number}: source does not exist: {source}")


def check_upstream_manifest() -> None:
    try:
        with UPSTREAMS.open("rb") as stream:
            document = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        fail(f"cannot parse upstream manifest: {error}")
        return
    sources = document.get("sources")
    if document.get("schema") != 1 or not isinstance(sources, list):
        fail("upstream source manifest has an unsupported schema")
        return
    forbidden = {"sha256", "vendor_sha256", "required"}
    if any(forbidden & source.keys() for source in sources if isinstance(source, dict)):
        fail("upstream source manifest restored obsolete digest/member bookkeeping")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/prepare-sources.py"), "--print-files"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        fail(f"cannot read upstream source manifest: {result.stderr.strip()}")
    elif len(result.stdout.split()) != 4:
        fail("upstream manifest must produce the four RPM source inputs")


def main() -> int:
    check_required_inputs()
    check_syntax()
    check_version()
    check_configuration()
    check_layout_and_docs()
    check_repository_safety()
    check_dispatcher_and_runtime_contracts()
    check_manifest_sources()
    check_upstream_manifest()
    if FAILURES:
        print(f"RPM preflight failed with {len(FAILURES)} error(s).", file=sys.stderr)
        return 1
    print("RPM preflight checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
