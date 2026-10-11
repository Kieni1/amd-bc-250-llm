#!/usr/bin/env python3
"""Machine-readable BC-250 appliance status."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PACKAGE = "bc250-llm-server"
DEFAULT_LIBEXEC = Path("/usr/libexec/bc250-llm-server")
DEFAULT_SHARE = Path("/usr/share/bc250-llm-server")


def run(argv: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired):
        return None


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


def rpm_identity() -> dict[str, str | None]:
    result = run(
        ["rpm", "-q", "--qf", "%{NAME}|%{EPOCHNUM}|%{VERSION}|%{RELEASE}|%{ARCH}\n", PACKAGE]
    )
    empty = {
        "name": PACKAGE,
        "epoch": None,
        "nevra": None,
        "version": None,
        "release": None,
        "arch": None,
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
        "nevra": f"{name}-{version}-{release}.{arch}",
        "version": version,
        "release": release,
        "arch": arch,
    }


def unit_state(unit: str) -> dict[str, str]:
    active = run(["systemctl", "is-active", unit])
    enabled = run(["systemctl", "is-enabled", unit])
    return {
        "active": active.stdout.strip() if active and active.stdout.strip() else "unknown",
        "enabled": enabled.stdout.strip() if enabled and enabled.stdout.strip() else "unknown",
    }


def runtime_mode(libexec: Path) -> str:
    helper = libexec / "agent-mode.sh"
    if not helper.is_file():
        return "unknown"
    result = run([str(helper), "status"])
    if result is None:
        return "unknown"
    for line in result.stdout.splitlines():
        if line.startswith("mode="):
            value = line.partition("=")[2].strip()
            if value in {"normal", "degraded", "stopped", "agent"}:
                return value
    return "unknown"


def memory_status() -> dict[str, int | None]:
    values: dict[str, int | None] = {
        "mem_available_kib": None,
        "swap_total_kib": None,
        "swap_free_kib": None,
        "swap_used_kib": None,
    }
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    parsed: dict[str, int] = {}
    for line in lines:
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        first = rest.strip().split()[0] if rest.strip() else ""
        if first.isdigit():
            parsed[key] = int(first)
    values["mem_available_kib"] = parsed.get("MemAvailable")
    values["swap_total_kib"] = parsed.get("SwapTotal")
    values["swap_free_kib"] = parsed.get("SwapFree")
    if parsed.get("SwapTotal") is not None and parsed.get("SwapFree") is not None:
        values["swap_used_kib"] = parsed["SwapTotal"] - parsed["SwapFree"]
    return values


def memory_psi() -> dict[str, float | None]:
    result: dict[str, float | None] = {"some_avg10": None, "full_avg10": None}
    try:
        lines = Path("/proc/pressure/memory").read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    for line in lines:
        fields = line.split()
        if not fields:
            continue
        kind = fields[0]
        pairs = dict(field.split("=", 1) for field in fields[1:] if "=" in field)
        try:
            avg10 = float(pairs.get("avg10", ""))
        except ValueError:
            continue
        if kind == "some":
            result["some_avg10"] = avg10
        elif kind == "full":
            result["full_avg10"] = avg10
    return result


def gfx_status(libexec: Path) -> dict[str, Any]:
    helper = libexec / "gfx1013.sh"
    if not helper.is_file():
        return {"state": "UNAVAILABLE", "reason": f"missing {helper}"}
    result = run([str(helper), "status", "--json"], timeout=30)
    if result is None:
        return {"state": "UNAVAILABLE", "reason": "gfx1013 status invocation failed"}
    if result.returncode != 0:
        return {"state": "BROKEN", "reason": result.stderr.strip() or f"status rc={result.returncode}"}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"state": "BROKEN", "reason": "gfx1013 status returned invalid JSON"}
    return payload if isinstance(payload, dict) else {"state": "BROKEN", "reason": "gfx1013 JSON is not an object"}


def failed_units() -> list[str] | None:
    result = run(["systemctl", "--failed", "--no-legend", "--plain"])
    if result is None or result.returncode not in (0, 1):
        return None
    units: list[str] = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields:
            units.append(fields[0])
    return units


def restart_status() -> dict[str, str | None]:
    available = run(["bash", "-lc", "command -v needs-restarting >/dev/null 2>&1"])
    if available is None or available.returncode != 0:
        return {"status": "not_evaluated", "reason": "optional needs-restarting helper unavailable"}
    probe = run(["needs-restarting", "-r"])
    if probe is None:
        return {"status": "not_evaluated", "reason": "needs-restarting could not be executed"}
    if probe.returncode == 0:
        return {"status": "pass", "reason": None}
    return {"status": "recommended", "reason": "package/kernel restart recommended"}


def container_image_identity(name: str) -> dict[str, str | None]:
    result = run(["podman", "inspect", "--format", "{{.ImageName}}", name])
    image = result.stdout.strip() if result and result.returncode == 0 else ""
    digest_match = re.search(r"sha256:[0-9a-f]{64}", image)
    digest = digest_match.group(0) if digest_match else None
    if image and digest is None:
        inspected = run(["podman", "image", "inspect", "--format", "{{.Digest}}", image])
        candidate = inspected.stdout.strip() if inspected and inspected.returncode == 0 else ""
        if re.fullmatch(r"sha256:[0-9a-f]{64}", candidate):
            digest = candidate
    return {"image": image or None, "digest": digest}


def tika_live_version() -> str | None:
    script = (
        "import urllib.request; "
        "print(urllib.request.urlopen('http://tika:9998/version', timeout=5)"
        ".read().decode('utf-8','replace').strip())"
    )
    result = run(["podman", "exec", "open-webui", "python", "-c", script])
    if result is None or result.returncode != 0:
        return None
    value = result.stdout.strip()
    if value.startswith("Apache Tika "):
        value = value.removeprefix("Apache Tika ").strip()
    return value or None


def open_webui_live_version() -> str | None:
    result = run(
        [
            "curl",
            "-fsS",
            "--connect-timeout",
            "1",
            "--max-time",
            "3",
            "http://127.0.0.1:3000/api/version",
        ]
    )
    if result is None or result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    version = payload.get("version")
    return version if isinstance(version, str) and version else None


def identity_match(
    expected_version: str | None,
    expected_digest: str | None,
    observed_version: str | None,
    observed_digest: str | None,
) -> bool | None:
    if not expected_version or not expected_digest or not observed_version or not observed_digest:
        return None
    return observed_version == expected_version and observed_digest == expected_digest


def runtime_identity(share: Path) -> dict[str, object]:
    runtime = key_values(share / "runtime.env")
    tika_expected_version = (runtime.get("BC250_TIKA_VERSION") or "").removesuffix("-full") or None
    owui_expected_version = runtime.get("BC250_OPEN_WEBUI_VERSION")
    tika_expected_digest = runtime.get("BC250_TIKA_IMAGE_DIGEST")
    owui_expected_digest = runtime.get("BC250_OPEN_WEBUI_IMAGE_DIGEST")
    tika_image = container_image_identity("tika")
    owui_image = container_image_identity("open-webui")
    tika_observed_version = tika_live_version()
    owui_observed_version = open_webui_live_version()
    tika_match = identity_match(
        tika_expected_version,
        tika_expected_digest,
        tika_observed_version,
        tika_image["digest"],
    )
    owui_match = identity_match(
        owui_expected_version,
        owui_expected_digest,
        owui_observed_version,
        owui_image["digest"],
    )
    overall_match = None
    if tika_match is not None and owui_match is not None:
        overall_match = tika_match and owui_match
    return {
        "match": overall_match,
        "tika": {
            "expected": {"version": tika_expected_version, "digest": tika_expected_digest},
            "observed": {
                "version": tika_observed_version,
                "digest": tika_image["digest"],
                "image": tika_image["image"],
            },
            "match": tika_match,
        },
        "open_webui": {
            "expected": {"version": owui_expected_version, "digest": owui_expected_digest},
            "observed": {
                "version": owui_observed_version,
                "digest": owui_image["digest"],
                "image": owui_image["image"],
            },
            "match": owui_match,
        },
    }


def main() -> int:
    libexec = Path(os.environ.get("BC250_LIBEXEC", DEFAULT_LIBEXEC))
    share = Path(os.environ.get("BC250_SHARE", DEFAULT_SHARE))
    services = {
        unit: unit_state(unit)
        for unit in (
            "ollama.service",
            "ollama-task.service",
            "ollama-embedding.service",
            "ollama-agent.service",
            "open-webui.service",
            "tika.service",
            "cyan-skillfish-governor-smu.service",
        )
    }
    payload = {
        "schema": "bc250.status.v2",
        "package": rpm_identity(),
        "kernel": os.uname().release,
        "command_line": (
            Path("/proc/cmdline").read_text(encoding="utf-8", errors="replace").strip()
            if Path("/proc/cmdline").is_file()
            else None
        ),
        "runtime_mode": runtime_mode(libexec),
        "services": services,
        "runtime_identity": runtime_identity(share),
        "memory": memory_status(),
        "memory_psi": memory_psi(),
        "failed_units": failed_units(),
        "os_package_restart_check": restart_status(),
        "gfx1013": gfx_status(libexec),
    }
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
