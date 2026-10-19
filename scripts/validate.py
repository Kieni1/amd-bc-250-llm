#!/usr/bin/env python3
"""Run fast, deterministic repository checks needed before an RPM build."""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging/bc250-llm-server.spec"
MANIFEST = ROOT / "packaging/install-manifest.tsv"
UPSTREAMS = ROOT / "packaging/upstreams.toml"
RELEASE_CONTRACT = ROOT / "release-contract.json"
EXCLUDED_TREES = {
    ".git",
    ".build",
    "build",
    "dist",
    "rpmbuild",
    "sources",
    "governor-src",
    "live-manager-src",
    "__pycache__",
    "development",
}
EXTERNAL_BUILD_TREES = ("governor-src/", "live-manager-src/")
FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)
    print(f"ERROR: {message}", file=sys.stderr)


def dynamic_excluded_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for name in (
        "BC250_LOCAL_BUILD_ROOT",
        "BC250_BUILD_DIR",
        "BC250_SOURCE_DIR",
        "BC250_GFX1013_CACHE_ROOT",
    ):
        value = os.environ.get(name)
        if not value:
            continue
        try:
            path = Path(value).expanduser().resolve()
            relative = path.relative_to(ROOT)
        except (OSError, ValueError):
            continue
        if relative.parts and relative not in roots:
            roots.append(relative)
    return tuple(roots)


def included_files():
    dynamic = dynamic_excluded_roots()
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if not path.is_file():
            continue
        if any(part in EXCLUDED_TREES for part in relative.parts):
            continue
        if any(relative == excluded or excluded in relative.parents for excluded in dynamic):
            continue
        yield relative, path


def check_required_inputs() -> None:
    required = (
        "VERSION",
        "release-contract.json",
        "MODELS.md",
        "Makefile",
        "build-local.sh",
        "install",
        "uninstall.sh",
        ".github/workflows/build-rpm.yml",
        "packaging/bc250-llm-server.spec",
        "packaging/install-manifest.tsv",
        "packaging/bc250-llm-server.sysusers",
        "packaging/upstreams.toml",
        "models/modelctl.py",
        "models/model-profiles.json",
        "cmd/monitoring/status.sh",
        "cmd/monitoring/support-bundle.sh",
        "cmd/maintenance/maintenance.sh",
        "models/modelfiles/MODEL-TEMPLATE.Modelfile.example",
        "models/mtp/models.toml",
        "examples/benchmark/agent-cases.json",
        "examples/benchmark/translation-office.json",
        "examples/benchmark/rag-quality-office.json",
        "examples/benchmark/ocr/manifest.json",
        "docs/FILESTRUCTURE.md",
        "docs/INSTALLATION.md",
        "docs/HARDWARE.md",
        "docs/OPERATIONS.md",
        "docs/OPENWEBUI.md",
        "docs/BENCHMARKING.md",
        "docs/SECURITY.md",
        "docs/RAG.md",
        "scripts/check-gfx1013-mesa.py",
        "scripts/check-upstream-patches.py",
        "scripts/install-manifest.py",
        "scripts/make-source-tarball.sh",
        "scripts/prepare-sources.py",
        "scripts/release-contract.py",
        "tests/test_release_pipeline.py",
        "licenses/LICENSE",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"required build input is missing: {relative}")
    executables = (
        "install",
        "uninstall.sh",
        "packaging/bc250",
        "models/modelctl.py",
        "cmd/monitoring/status.sh",
        "cmd/monitoring/support-bundle.sh",
        "cmd/maintenance/maintenance.sh",
        "scripts/check-gfx1013-mesa.py",
        "scripts/check-upstream-patches.py",
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
    changelog_match = re.search(
        r"^%changelog\s*$\n\*[^\n]* - (\S+)\s*$", spec, re.MULTILINE
    )
    if not version:
        fail("VERSION is empty")
    elif version_match is None or version_match.group(1) != version:
        fail("VERSION and spec Version differ")
    if release_match is None or changelog_match is None:
        fail("spec Release or top changelog entry is malformed")
    elif changelog_match.group(1) != f"{version}-{release_match.group(1)}":
        fail("top changelog entry does not match Version-Release")
    description_match = re.search(
        r"(?ms)^%description\s*$\n(.*?)(?=^%[A-Za-z])", spec
    )
    if description_match is None:
        fail("RPM spec is missing the main %description")
    elif any(len(line) > 79 for line in description_match.group(1).splitlines()):
        fail("RPM %description contains a line longer than 79 characters")
    if re.search(r"(?m)^Requires:\s+git\s*$", spec):
        fail("runtime dependency must use git-core instead of the larger git meta-package")


def check_release_contract() -> None:
    try:
        contract = json.loads(RELEASE_CONTRACT.read_text(encoding="utf-8"))
        spec = SPEC.read_text(encoding="utf-8")
        scope = json.loads((ROOT / "development/DEVELOPMENT-SCOPE.json").read_text(encoding="utf-8"))
        runtime_lines = (ROOT / "config/runtime.env").read_text(encoding="utf-8").splitlines()
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read release contract metadata: {error}")
        return

    if contract.get("schema") != "bc250.release-contract.v1":
        fail("release-contract.json has an unsupported schema")
        return
    package = contract.get("package", {})
    runtime = contract.get("runtime", {})
    gfx = contract.get("gfx1013", {})
    validation = contract.get("validation", {})

    def spec_value(field: str) -> str:
        match = re.search(rf"^{re.escape(field)}:\s*([^%\s]+)", spec, re.MULTILINE)
        return match.group(1) if match else ""

    expected_name = package.get("name", "")
    expected_version = package.get("version", "")
    expected_release = package.get("rpm_release", "")
    expected_fedora = str(package.get("fedora", ""))
    if expected_name != spec_value("Name"):
        fail("release contract package.name differs from RPM spec Name")
    if expected_version != (ROOT / "VERSION").read_text(encoding="utf-8").strip():
        fail("release contract package.version differs from VERSION")
    if expected_version != spec_value("Version"):
        fail("release contract package.version differs from RPM spec Version")
    if expected_release != spec_value("Release"):
        fail("release contract package.rpm_release differs from RPM spec Release")
    if expected_fedora != "44":
        fail("release contract Fedora target must remain 44 for this package line")

    release = scope.get("release", {}) if isinstance(scope, dict) else {}
    if release.get("version") != expected_version or release.get("rpm_release") != expected_release:
        fail("development scope release identity differs from release contract")
    if release.get("nvr") != f"{expected_name}-{expected_version}-{expected_release}":
        fail("development scope NVR differs from release contract")

    runtime_values: dict[str, str] = {}
    for raw in runtime_lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        runtime_values[key] = value
    if runtime_values.get("BC250_OLLAMA_VERSION") != runtime.get("ollama"):
        fail("runtime Ollama pin differs from release contract")

    try:
        gfx_cli = (ROOT / "cmd/system/gfx1013.sh").read_text(encoding="utf-8")
    except OSError as error:
        fail(f"cannot read GFX1013 CLI metadata: {error}")
        gfx_cli = ""
    for field, shell_name in (
        ("patch_reference_kernel", "PATCH_REFERENCE_KERNEL"),
        ("qualification_kernel", "PACKAGE_QUALIFICATION_KERNEL"),
    ):
        expected = gfx.get(field, "")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9][0-9A-Za-z._+-]*\.x86_64", expected):
            fail(f"GFX {field} is missing or malformed in release contract")
            continue
        match = re.search(rf"(?m)^{shell_name}=([^\s]+)$", gfx_cli)
        actual = match.group(1).strip('\"\'') if match else ""
        if actual != expected:
            fail(f"GFX {field} differs from {shell_name} in cmd/system/gfx1013.sh")

    checks = (
        ("package_profile", ROOT / "gfx1013/upstream/PACKAGE-PROFILE-VERSION"),
        ("upstream_version", ROOT / "gfx1013/upstream/VERSION"),
        ("upstream_commit", ROOT / "gfx1013/upstream/SOURCE-REVISION"),
    )
    for field, path in checks:
        try:
            actual = path.read_text(encoding="utf-8").strip()
        except OSError as error:
            fail(f"cannot read GFX release metadata {path.relative_to(ROOT)}: {error}")
            continue
        if actual != gfx.get(field):
            fail(f"GFX {field} differs from release contract")
    try:
        mesa_fields = {}
        for raw in (ROOT / "gfx1013/upstream/MESA-SOURCE").read_text(encoding="utf-8").splitlines():
            if "=" in raw:
                key, value = raw.split("=", 1)
                mesa_fields[key.strip()] = value.strip()
        if mesa_fields.get("srpm_nevra") != gfx.get("mesa_srpm_nevra"):
            fail("GFX Mesa SRPM identity differs from release contract")
    except OSError as error:
        fail(f"cannot read GFX Mesa source metadata: {error}")

    release_test = validation.get("release_pipeline_test")
    excludes = validation.get("package_excludes")
    if release_test != "tests/test_release_pipeline.py":
        fail("release contract must identify tests/test_release_pipeline.py as the host release test")
    if excludes != [release_test]:
        fail("release contract package exclusions must contain only the host release-pipeline test")
    for plan_name in ("full_plan", "fast_plan"):
        stages = validation.get(plan_name)
        if not isinstance(stages, list) or not stages:
            fail(f"release contract {plan_name} must be a non-empty stage list")
            continue
        ids = [stage.get("id") for stage in stages if isinstance(stage, dict)]
        if len(ids) != len(stages) or any(not value for value in ids) or len(set(ids)) != len(ids):
            fail(f"release contract {plan_name} has missing or duplicate stage ids")


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
    if governor.get("frequency-range", {}).get("max") != 1850:
        fail("packaged governor maximum must be 1850 MHz")
    gpu_usage = governor.get("gpu-usage", {})
    if gpu_usage.get("fix-freq") is not False:
        fail("packaged governor fix-freq must be explicitly false")
    if gpu_usage.get("method") != "busy-flag":
        fail("packaged governor usage method must remain busy-flag")
    if gpu_usage.get("temp-read") != "sysfs":
        fail("packaged governor v0.4.13 temperature source must be sysfs")
    points = governor.get("safe-points", [])
    if not any(
        isinstance(point, dict)
        and point.get("frequency") == 2000
        and point.get("voltage") == 960
        for point in points
    ):
        fail("packaged governor must retain the 2000 MHz / 960 mV point")


def check_layout_and_docs() -> None:
    for relative in (
        "cmd",
        "config",
        "docs",
        "examples",
        "models",
        "packaging",
        "scripts",
        "tests",
    ):
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
    dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
    routes = set(re.findall(r'^  "([a-z0-9-]+)\|', dispatcher, flags=re.MULTILINE))
    required = {
        "agent-mode", "benchmark", "code", "code-commit", "compare-mtp", "doctor", "health",
        "fetch-mtp", "gfx1013", "gitea-review", "install", "maintenance", "model", "ocr",
        "package-gate", "rag", "reset", "resilience", "revalidate", "ollama-profile",
        "openwebui-setup", "qualification", "run-mtp", "status", "support-bundle", "storage", "verify", "version",
    }
    if routes != required:
        fail(f"dispatcher command set differs from the supported interface: {sorted(routes)}")

    checks = {
        "install": (
            "dnf install -y",
            "--exclude=ollama",
            "exec bc250 install",
        ),
        "cmd/system/install.sh": (
            'source "$runtime_env"',
            'requested="$BC250_OLLAMA_VERSION"',
            "rpm -e --test ollama",
            '"$MEMORY_PROFILE" ensure',
            '"$SWAP_PROFILE" ensure',
            "BC250_MODEL_SELECTION",
            "BC250_MODELCTL_CURRENT_SUMMARY=1",
            "bc250 model status all --compact",
            "MTP remains a separate opt-in workflow",
            "bc250 model apply all",
            "request_primary_reboot_if_needed",
        ),
        "cmd/system/gfx1013.sh": (
            "PACKAGE_PROFILE=v0.2.5-alpha",
            "PINNED_COMMIT=d3e6dc062c34d2523db0abe5741d1f5b0dea00d9",
            "SOURCE-SHA256SUMS",
            "PATCH-SHA256SUMS",
            "grub2-set-default",
            "VK_DRIVER_FILES",
            "prepare_cleanup_on_exit",
            "Secure Boot",
            "ROLLBACK_REQUIRED",
            "acquire_lifecycle_lock",
            "enable requires PATCHED_BOOT_UNVERIFIED",
            "restore_prepared_state_after_enable_failure",
            "status_json",
            "reset()",
            "verify_private_radv_device",
            "BC250_GFX1013_PACKAGE_NEVRA",
            "ConditionKernelCommandLine=$PATCH_MARKER",
            "ExecCondition=+$INSTALLED_SELF ollama-guard",
            "ollama_guard()",
            "benchmark {stock|gfx|restored|status|report}",
        ),
        "cmd/system/storage.py": (
            "reflink=1",
            "dedupe -q",
            "PRUNE-SOURCES",
        ),
        "uninstall.sh": (
            "PURGE-BC250-LLM",
            '"$MEMORY_PROFILE" remove',
            '"$SWAP_PROFILE" remove',
            "dnf remove -y bc250-llm-server.x86_64",
            "/var/lib/bc250-llm-server",
            "/var/lib/open-webui",
        ),
        "cmd/system/install-ollama.sh": (
            'source "$runtime_env"',
            'VERSION="${OLLAMA_VERSION:-$BC250_OLLAMA_VERSION}"',
            'PAYLOAD_URL="${OLLAMA_PAYLOAD_URL:-${BC250_OLLAMA_PAYLOAD_URL:-}}"',
            'PAYLOAD_SHA256="${OLLAMA_PAYLOAD_SHA256:-${BC250_OLLAMA_PAYLOAD_SHA256:-}}"',
            'actual_sha256="$(sha256sum "$tmp"',
            'if [[ "$actual_sha256" != "$PAYLOAD_SHA256" ]]',
            'tar --zstd -xf "$tmp" -C "$install_root"',
            'package_unit=/usr/lib/systemd/system/ollama.service',
            'ERROR: refusing to overwrite a custom Ollama service override',
            '[[ "$fragment" == "$package_unit" ]]',
            'for port in 11434 11435 11437',
            'http://127.0.0.1:${port}/api/version',
        ),
        "config/systemd/ollama-task.service": (
            "OLLAMA_HOST=0.0.0.0:11435",
            "Conflicts=ollama-agent.service",
        ),
        "config/systemd/ollama-embedding.service": (
            "OLLAMA_HOST=0.0.0.0:11437",
            "OLLAMA_CONTEXT_LENGTH=4096",
        ),
        "config/systemd/ollama-agent.service": (
            "OLLAMA_HOST=0.0.0.0:11436",
            "Conflicts=ollama.service ollama-task.service ollama-embedding.service",
        ),
        "models/modelctl.py": (
            "OLLAMA_HOST",
            "OLLAMA_URL",
            "HF_TOKEN",
            "terminal=True",
            'command_path("script")',
            "OPERATOR_MODEL_DIR",
            "RECOMMENDED_MODELS",
            "already current; skipping",
        ),
        "packaging/bc250-llm-server.spec": (
            "Requires:       zram-generator",
            "Requires:       util-linux-script",
            "Requires:       xfsprogs",
            "Requires:       git-core",
            "%posttrans",
            "BC-250 LLM appliance package installed.",
            "BC-250 LLM appliance package upgraded.",
            "sudo bc250 install",
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

    runtime_path = ROOT / "config/runtime.env"
    try:
        runtime_lines = runtime_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        fail(f"cannot read runtime metadata: {error}")
    else:
        runtime: dict[str, str] = {}
        for raw in runtime_lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            runtime[key] = value
        ollama_version = runtime.get("BC250_OLLAMA_VERSION", "")
        ollama_url = runtime.get("BC250_OLLAMA_PAYLOAD_URL", "")
        ollama_sha = runtime.get("BC250_OLLAMA_PAYLOAD_SHA256", "")
        owui_version = runtime.get("BC250_OPEN_WEBUI_VERSION", "")
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", ollama_version):
            fail("runtime metadata has invalid BC250_OLLAMA_VERSION")
        if f"/v{ollama_version}/ollama-linux-amd64.tar.zst" not in ollama_url:
            fail("runtime Ollama payload URL does not match BC250_OLLAMA_VERSION")
        if re.fullmatch(r"[0-9a-f]{64}", ollama_sha) is None:
            fail("runtime Ollama payload SHA-256 is malformed")
        if not owui_version or runtime.get("BC250_OPEN_WEBUI_TASK_CONTRACT") != owui_version:
            fail("Open WebUI task contract must match the pinned Open WebUI version")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", runtime.get("BC250_OPEN_WEBUI_IMAGE_DIGEST", "")) is None:
            fail("runtime Open WebUI image digest is malformed")
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", runtime.get("BC250_GOVERNOR_VERSION", "")):
            fail("runtime governor version metadata is malformed")
        if re.fullmatch(r"[0-9a-f]{40}", runtime.get("BC250_GOVERNOR_COMMIT", "")) is None:
            fail("runtime governor commit metadata is malformed")

    workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(encoding="utf-8")
    if not re.search(r"(?m)^  LANG: C$", workflow):
        fail("GitHub Actions must force portable LANG=C")
    if not re.search(r"(?m)^  LC_ALL: C$", workflow):
        fail("GitHub Actions must force portable LC_ALL=C")
    refs = re.findall(r"uses:\s+actions/[^@\s]+@([^\s#]+)", workflow)
    if not refs or any(re.fullmatch(r"[0-9a-f]{40}", ref) is None for ref in refs):
        fail("GitHub Actions must use full reviewed commit IDs")



def check_greenfield_command_surface() -> None:
    """Reject pre-greenfield public command spellings in active source and package docs."""
    dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
    routes = sorted(set(re.findall(r'^  "([a-z0-9-]+)\|', dispatcher, flags=re.MULTILINE)))
    removed = (
        "rag" + "-import",
        "un" + "install",
        "check" + "-temp",
        "verify" + "-lan",
        "memory" + "-profile",
        "swap" + "-profile",
        "cu" + "-status",
        "install" + "-ollama",
        "reset" + "-info",
        "uninstall" + "-info",
    )
    # gfx1013 is also the deliberate package artifact namespace
    # (/opt/bc250-gfx1013, BLS variant, state paths), so a blind prefixed-token
    # ban would reject valid internal paths. The public dispatcher still owns
    # the command spelling `bc250 gfx1013`.
    names = [name for name in routes if name != "gfx1013"] + list(removed)
    prefixed_pattern = re.compile(
        r"\bbc250-(?:" + "|".join(re.escape(name) for name in names) + r")\b(?=[\s`'\"),;:]|$)"
    )
    removed_model_verbs = ("cleanup", "cleanup" + "-retired", "resolve")
    model_pattern = re.compile(
        r"\bbc250\s+model\s+(?:"
        + "|".join(re.escape(name) for name in removed_model_verbs)
        + r")\b"
    )
    removed_rag_compat = "rag" + "-import"
    rag_import_pattern = re.compile(r"\bbc250\s+" + re.escape(removed_rag_compat) + r"\b")
    rag_verb_pattern = re.compile(r"\bbc250\s+rag\s+(?:plan|sync)\b")
    archive_prefixes = (
        Path("quality-checks/history"),
    )

    scope = json.loads((ROOT / "development/DEVELOPMENT-SCOPE.json").read_text(encoding="utf-8"))
    current_development_files: set[Path] = {
        ROOT / "development/DEVELOPMENT-SCOPE.json",
        ROOT / "development/README.md",
    }
    for component in scope.get("components", {}).values():
        if component.get("status") not in {"active", "boundary_active"}:
            continue
        for item in component.get("paths", []):
            if not item.startswith("development/") or any(char in item for char in "*?["):
                continue
            current_development_files.add(ROOT / item)
    candidates = list(included_files()) + [
        (path.relative_to(ROOT), path)
        for path in sorted(current_development_files)
        if path.is_file()
    ]
    for relative, path in candidates:
        if relative == Path("scripts/validate.py"):
            continue
        if any(relative.is_relative_to(prefix) for prefix in archive_prefixes):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern, description in (
            (prefixed_pattern, "pre-greenfield public command spelling"),
            (model_pattern, "removed model-manager command grammar"),
            (rag_import_pattern, "removed RAG importer command grammar"),
            (rag_verb_pattern, "removed RAG compatibility subcommand"),
        ):
            match = pattern.search(text)
            if match:
                fail(f"{relative}: {description} remains: {match.group(0)}")


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
        if kind not in {"dir", "file", "config", "ghost", "text"}:
            fail(f"install manifest line {number}: unsupported type {kind!r}")
        if re.fullmatch(r"0[0-7]{3}", mode) is None:
            fail(f"install manifest line {number}: invalid mode {mode!r}")
        if kind in {"dir", "ghost", "text"} or source == "-":
            continue
        if source.startswith(EXTERNAL_BUILD_TREES):
            continue
        if not glob.glob(str(ROOT / source)):
            fail(f"install manifest line {number}: source does not exist: {source}")


def check_development_scope() -> None:
    """Verify frozen/archive development domains without loading their internals."""
    scope = ROOT / "development/scope.py"
    manifest = ROOT / "development/DEVELOPMENT-SCOPE.json"
    if not scope.is_file() or not manifest.is_file():
        fail("development scope manifest/helper is missing")
        return
    try:
        compile(scope.read_text(encoding="utf-8"), str(scope.relative_to(ROOT)), "exec")
    except (OSError, SyntaxError) as error:
        fail(f"development scope helper syntax check failed: {error}")
        return
    result = subprocess.run(
        [sys.executable, str(scope), "check", "--quiet"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        fail(f"development scope check failed: {detail}")


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
    spec = SPEC.read_text(encoding="utf-8")
    for source in sources:
        if isinstance(source, dict) and source.get("commit") not in spec:
            fail(
                f"upstream pin is not referenced by the RPM spec: {source.get('id', 'unknown')}"
            )
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/prepare-sources.py"), "--print-files"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"cannot read upstream source manifest: {result.stderr.strip()}")
    elif len(result.stdout.split()) != 3:
        fail("upstream manifest must produce the three RPM source inputs")


def main() -> int:
    check_required_inputs()
    check_syntax()
    check_version()
    check_release_contract()
    check_configuration()
    check_layout_and_docs()
    check_repository_safety()
    check_dispatcher_and_runtime_contracts()
    check_greenfield_command_surface()
    check_manifest_sources()
    check_development_scope()
    check_upstream_manifest()
    if FAILURES:
        print(f"RPM preflight failed with {len(FAILURES)} error(s).", file=sys.stderr)
        return 1
    print("RPM preflight checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
