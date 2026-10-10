#!/usr/bin/env python3
"""Concise package/runtime version report for operators and support evidence."""

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


def command(argv: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def rpm_identity() -> dict[str, str | None]:
    result = command(
        [
            "rpm",
            "-q",
            "--qf",
            "%{NAME}|%{VERSION}|%{RELEASE}|%{ARCH}\\n",
            PACKAGE,
        ]
    )
    if result is None or result.returncode != 0:
        return {"name": PACKAGE, "version": None, "release": None, "arch": None, "nevra": None}
    fields = result.stdout.strip().split("|")
    if len(fields) != 4:
        return {"name": PACKAGE, "version": None, "release": None, "arch": None, "nevra": None}
    name, version, release, arch = fields
    return {
        "name": name,
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


def gfx_status(libexec: Path) -> dict[str, Any] | None:
    helper = libexec / "gfx1013.sh"
    if not helper.is_file():
        return None
    result = command([str(helper), "status", "--json"])
    if result is None or result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bc250 version", description="Show package and pinned runtime identities.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--short", action="store_true", help="print only installed package NVR/NEVRA")
    args = parser.parse_args(argv)
    if args.json and args.short:
        parser.error("--json and --short are mutually exclusive")

    share = Path(os.environ.get("BC250_SHARE", DEFAULT_SHARE))
    libexec = Path(os.environ.get("BC250_LIBEXEC", DEFAULT_LIBEXEC))
    package = rpm_identity()
    runtime = key_values(share / "runtime.env")
    source_version = one_line(share / "VERSION")
    gfx = gfx_status(libexec)
    gfx_upstream = gfx.get("upstream") if isinstance(gfx, dict) else None
    if not isinstance(gfx_upstream, dict):
        gfx_upstream = {}
    gfx_kernel = gfx.get("kernel") if isinstance(gfx, dict) else None
    if not isinstance(gfx_kernel, dict):
        gfx_kernel = {}
    payload: dict[str, Any] = {
        "schema": "bc250.version.v1",
        "package": package,
        "source_version": source_version,
        "kernel": os.uname().release,
        "runtime": {
            "ollama": runtime.get("BC250_OLLAMA_VERSION"),
            "open_webui": runtime.get("BC250_OPEN_WEBUI_VERSION"),
            "tika": runtime.get("BC250_TIKA_VERSION"),
            "tika_digest": runtime.get("BC250_TIKA_IMAGE_DIGEST"),
            "governor": runtime.get("BC250_GOVERNOR_VERSION"),
        },
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
    print(f"Ollama:       {payload['runtime']['ollama'] or 'unknown'}")
    print(f"Open WebUI:   {payload['runtime']['open_webui'] or 'unknown'}")
    print(f"Tika:         {payload['runtime']['tika'] or 'unknown'} @ {payload['runtime']['tika_digest'] or 'unknown'}")
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
