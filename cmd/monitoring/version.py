#!/usr/bin/env python3
"""Concise package, configured-runtime and observed-runtime identity report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PACKAGE = "bc250-llm-server"
DEFAULT_SHARE = Path("/usr/share/bc250-llm-server")
DEFAULT_LIBEXEC = Path("/usr/libexec/bc250-llm-server")


def command(argv: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def rpm_identity() -> dict[str, str | None]:
    result = command(
        ["rpm", "-q", "--qf", "%{NAME}|%{EPOCHNUM}|%{VERSION}|%{RELEASE}|%{ARCH}\n", PACKAGE]
    )
    empty = {
        "name": PACKAGE,
        "epoch": None,
        "version": None,
        "release": None,
        "arch": None,
        "nevra": None,
    }
    if result is None or result.returncode != 0:
        return empty
    fields = result.stdout.strip().split("|")
    if len(fields) != 5:
        return empty
    name, epoch, version, release, arch = fields
    return {
        "name": name,
        "epoch": epoch,
        "version": version,
        "release": release,
        "arch": arch,
        "nevra": f"{name}-{version}-{release}.{arch}",
    }


def key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def one_line(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip().splitlines()[0]
    except (OSError, IndexError):
        return None


def json_helper(path: Path, *args: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    result = command([str(path), *args], timeout=30)
    if result is None or result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def match_label(value: object) -> str:
    if value is True:
        return "MATCH"
    if value is False:
        return "MISMATCH"
    return "UNKNOWN"


def runtime_line(label: str, row: dict[str, Any] | None) -> str:
    row = row if isinstance(row, dict) else {}
    expected = row.get("expected") if isinstance(row.get("expected"), dict) else {}
    observed = row.get("observed") if isinstance(row.get("observed"), dict) else {}
    return (
        f"{label:<13} expected {expected.get('version') or 'unknown'} @ {expected.get('digest') or 'unknown'}; "
        f"observed {observed.get('version') or 'unavailable'} @ {observed.get('digest') or 'unavailable'}; "
        f"{match_label(row.get('match'))}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bc250 version",
        description="Show package pins separately from observed runtime identities.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--short", action="store_true", help="print only installed package NVR/NEVRA")
    args = parser.parse_args(argv)
    if args.json and args.short:
        parser.error("--json and --short are mutually exclusive")

    share = Path(os.environ.get("BC250_SHARE", DEFAULT_SHARE))
    libexec = Path(os.environ.get("BC250_LIBEXEC", DEFAULT_LIBEXEC))
    package = rpm_identity()
    configured = key_values(share / "runtime.env")
    source_version = one_line(share / "VERSION")
    status = json_helper(libexec / "status-json.py")
    gfx = status.get("gfx1013") if isinstance(status, dict) else None
    if not isinstance(gfx, dict):
        gfx = json_helper(libexec / "gfx1013.sh", "status", "--json")
    runtime_identity = status.get("runtime_identity") if isinstance(status, dict) else None
    if not isinstance(runtime_identity, dict):
        runtime_identity = {}
    gfx_upstream = gfx.get("upstream") if isinstance(gfx, dict) else None
    if not isinstance(gfx_upstream, dict):
        gfx_upstream = {}
    gfx_kernel = gfx.get("kernel") if isinstance(gfx, dict) else None
    if not isinstance(gfx_kernel, dict):
        gfx_kernel = {}
    payload: dict[str, Any] = {
        "schema": "bc250.version.v2",
        "package": package,
        "source_version": source_version,
        "kernel": os.uname().release,
        "configured_runtime": {
            "ollama": configured.get("BC250_OLLAMA_VERSION"),
            "open_webui": configured.get("BC250_OPEN_WEBUI_VERSION"),
            "open_webui_digest": configured.get("BC250_OPEN_WEBUI_IMAGE_DIGEST"),
            "tika": configured.get("BC250_TIKA_VERSION"),
            "tika_digest": configured.get("BC250_TIKA_IMAGE_DIGEST"),
            "governor": configured.get("BC250_GOVERNOR_VERSION"),
        },
        "runtime_identity": runtime_identity,
        "gfx1013": {
            "state": gfx.get("state") if gfx else None,
            "package_profile": gfx.get("profile") if gfx else None,
            "upstream_version": gfx_upstream.get("version"),
            "pinned_commit": gfx_upstream.get("commit"),
            "prepared_kernel": gfx_kernel.get("prepared"),
        },
    }
    if args.short:
        print(package.get("nevra") or source_version or "unknown")
        return 0 if package.get("nevra") else 2
    if args.json:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    print(f"Package:      {package.get('nevra') or 'unavailable'}")
    print(f"Kernel:       {payload['kernel']}")
    print(f"Ollama pin:   {payload['configured_runtime']['ollama'] or 'unknown'}")
    print(runtime_line("Open WebUI:", runtime_identity.get("open_webui")))
    print(runtime_line("Tika:", runtime_identity.get("tika")))
    print(f"Governor pin: {payload['configured_runtime']['governor'] or 'unknown'}")
    if gfx:
        print(
            "GFX1013:      "
            f"{gfx.get('state', 'unknown')} / {gfx.get('profile', 'unknown')} / "
            f"{gfx_upstream.get('commit', 'unknown')}"
        )
    else:
        print("GFX1013:      unavailable")
    return 0 if package.get("nevra") else 2


if __name__ == "__main__":
    raise SystemExit(main())
