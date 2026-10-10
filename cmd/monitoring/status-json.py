#!/usr/bin/env python3
"""Machine-readable BC-250 appliance status."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PACKAGE = "bc250-llm-server"
DEFAULT_LIBEXEC = Path("/usr/libexec/bc250-llm-server")


def run(argv: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired):
        return None


def rpm_identity() -> dict[str, str | None]:
    result = run(["rpm", "-q", "--qf", "%{NAME}|%{EPOCHNUM}|%{VERSION}|%{RELEASE}|%{ARCH}\\n", PACKAGE])
    if result is None or result.returncode != 0:
        return {"name": PACKAGE, "nevra": None, "version": None, "release": None, "arch": None}
    fields = result.stdout.strip().split("|")
    if len(fields) != 5:
        return {"name": PACKAGE, "nevra": None, "version": None, "release": None, "arch": None}
    name, epoch, version, release, arch = fields
    return {
        "name": name,
        "nevra": f"{name}-{epoch}:{version}-{release}.{arch}",
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


def restart_status() -> str:
    available = run(["bash", "-lc", "command -v needs-restarting >/dev/null 2>&1"])
    if available is None or available.returncode != 0:
        return "unknown"
    probe = run(["needs-restarting", "-r"])
    if probe is None:
        return "unknown"
    return "pass" if probe.returncode == 0 else "recommended"


def main() -> int:
    libexec = Path(os.environ.get("BC250_LIBEXEC", DEFAULT_LIBEXEC))
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
        "schema": "bc250.status.v1",
        "package": rpm_identity(),
        "kernel": os.uname().release,
        "command_line": (
            Path("/proc/cmdline").read_text(encoding="utf-8", errors="replace").strip()
            if Path("/proc/cmdline").is_file()
            else None
        ),
        "runtime_mode": runtime_mode(libexec),
        "services": services,
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
