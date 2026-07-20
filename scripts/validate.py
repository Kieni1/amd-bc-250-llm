#!/usr/bin/env python3
"""Run the small, deterministic preflight required to build the RPM."""

from __future__ import annotations

import glob
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging/bc250-llm-server.spec"
MANIFEST = ROOT / "packaging/install-manifest.tsv"
EXTERNAL_BUILD_TREES = ("governor-src/", "unlock-src/", "live-manager-src/")
FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)
    print(f"ERROR: {message}", file=sys.stderr)


def check_required_inputs() -> None:
    required = (
        "VERSION",
        "Makefile",
        "packaging/bc250-llm-server.spec",
        "packaging/install-manifest.tsv",
        "packaging/upstreams.toml",
        "licenses/LICENSE",
        "licenses/40CU-LICENSE-NOTICE",
        "models/modelctl.py",
        "models/sources/production.toml",
        "models/sources/experiments.toml",
        "models/sources/task.toml",
        "models/sources/coding.toml",
        "models/mtp/models.toml",
        "scripts/install-manifest.py",
        "scripts/make-source-tarball.sh",
        "scripts/prepare-sources.py",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"required build input is missing: {relative}")

    for relative in (
        "scripts/install-manifest.py",
        "scripts/make-source-tarball.sh",
        "scripts/prepare-sources.py",
        "models/modelctl.py",
        "packaging/bc250",
    ):
        path = ROOT / relative
        if path.is_file() and not os.access(path, os.X_OK):
            fail(f"required helper is not executable: {relative}")


def check_python_syntax() -> None:
    for directory in (ROOT / "scripts", ROOT / "models"):
        for path in directory.rglob("*.py"):
            try:
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
            except (OSError, SyntaxError) as error:
                fail(f"Python syntax check failed for {path.relative_to(ROOT)}: {error}")


def check_version() -> None:
    try:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        spec = SPEC.read_text(encoding="utf-8")
    except OSError as error:
        fail(f"cannot read version metadata: {error}")
        return

    match = re.search(r"^Version:\s*(\S+)\s*$", spec, re.MULTILINE)
    if not version:
        fail("VERSION is empty")
    elif match is None:
        fail("spec Version is missing")
    elif match.group(1) != version:
        fail("VERSION and spec Version differ")


def load_modelctl():
    path = ROOT / "models/modelctl.py"
    spec = importlib.util.spec_from_file_location("bc250_modelctl_validate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_model_catalogs() -> None:
    try:
        modelctl = load_modelctl()
    except Exception as error:  # The detailed import error is the useful result.
        fail(f"cannot load model catalog validator: {error}")
        return

    for category in modelctl.CATEGORIES:
        catalog = (
            ROOT / "models/mtp/models.toml"
            if category == "mtp"
            else ROOT / f"models/sources/{category}.toml"
        )
        modelfile_dir = ROOT / f"models/modelfiles/{category}"
        try:
            _, models = modelctl.load_catalog(
                catalog,
                category,
                modelfile_dir,
                strict_metadata=True,
            )
        except Exception as error:
            fail(str(error))
            continue

        referenced = {
            model["modelfile"]
            for model in models
            if model.get("provider") == "ollama"
        }
        packaged = (
            {path.name for path in modelfile_dir.glob("*.Modelfile")}
            if modelfile_dir.is_dir()
            else set()
        )
        if referenced != packaged:
            missing = sorted(referenced - packaged)
            obsolete = sorted(packaged - referenced)
            if missing:
                fail(f"{category}: referenced Modelfiles are missing: {', '.join(missing)}")
            if obsolete:
                fail(f"{category}: unreferenced Modelfiles are packaged: {', '.join(obsolete)}")

    for path in (ROOT / "models/modelfiles").rglob("*.Modelfile"):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        if len(re.findall(r"^PARAMETER\s+num_gpu\s+99\s*$", text, re.MULTILINE)) != 1:
            fail(f"{relative}: expected exactly one 'PARAMETER num_gpu 99'")
        if len(re.findall(r"^PARAMETER\s+num_keep\s+256\s*$", text, re.MULTILINE)) != 1:
            fail(f"{relative}: expected exactly one 'PARAMETER num_keep 256'")


def check_manifest_sources() -> None:
    try:
        lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        fail(f"cannot read install manifest: {error}")
        return

    for line_number, line in enumerate(lines, 1):
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 4:
            fail(f"install manifest line {line_number}: expected four tab-separated fields")
            continue
        entry_type, mode, source, _destination = fields
        if entry_type not in {"dir", "file", "config", "ghost", "text", "aliases"}:
            fail(f"install manifest line {line_number}: unsupported type {entry_type!r}")
        if re.fullmatch(r"0[0-7]{3}", mode) is None:
            fail(f"install manifest line {line_number}: invalid mode {mode!r}")
        if entry_type in {"dir", "ghost", "text"} or source == "-":
            continue
        if source.startswith(EXTERNAL_BUILD_TREES):
            continue
        if not glob.glob(str(ROOT / source)):
            fail(f"install manifest line {line_number}: source does not exist: {source}")


def check_upstream_lock() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/prepare-sources.py"), "--print-files"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "unknown error"
        fail(f"cannot read pinned source lock: {detail}")
    elif len(result.stdout.split()) != 4:
        fail("pinned source lock must describe the four RPM source archives")


def main() -> int:
    check_required_inputs()
    check_python_syntax()
    check_version()
    check_model_catalogs()
    check_manifest_sources()
    check_upstream_lock()
    if FAILURES:
        print(f"Basic RPM preflight failed with {len(FAILURES)} error(s).", file=sys.stderr)
        return 1
    print("Basic RPM preflight checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
