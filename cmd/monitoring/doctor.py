#!/usr/bin/env python3
"""Read-only BC-250 appliance diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_LIBEXEC = Path("/usr/libexec/bc250-llm-server")
PACKAGE = "bc250-llm-server"


def color_enabled() -> bool:
    return (
        sys.stdout.isatty()
        and os.environ.get("TERM", "dumb") != "dumb"
        and "NO_COLOR" not in os.environ
    )


def color_verdict(text: str) -> str:
    if not color_enabled():
        return text
    if text in {"PASS", "OK"}:
        code = "\033[1;32m"
    elif text in {"FAIL", "FAILED", "ERROR"}:
        code = "\033[1;31m"
    elif text in {"WARN", "WARNING", "DEGRADED", "ATTENTION"}:
        code = "\033[1;33m"
    else:
        return text
    return f"{code}{text}\033[0m"


def run(argv: list[str], timeout: int = 300) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired):
        return None


def add(
    checks: list[dict[str, Any]],
    name: str,
    status: str,
    detail: str,
    *,
    category: str = "appliance",
) -> None:
    checks.append({"name": name, "status": status, "detail": detail, "category": category})


def load_status(libexec: Path) -> dict[str, Any]:
    helper = libexec / "status-json.py"
    result = run([str(helper)]) if helper.is_file() else None
    if result is None or result.returncode != 0:
        raise RuntimeError("bc250 status --json helper is unavailable")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise TypeError("status JSON is not an object")
    return payload


def rpm_verify(checks: list[dict[str, Any]]) -> None:
    result = run(["rpm", "-V", PACKAGE], timeout=120)
    if result is None:
        add(checks, "rpm-integrity", "FAIL", "rpm -V could not be executed")
    elif result.returncode == 0 and not result.stdout.strip() and not result.stderr.strip():
        add(checks, "rpm-integrity", "PASS", "rpm -V is clean")
    else:
        detail = (result.stdout.strip() or result.stderr.strip() or f"rc={result.returncode}").splitlines()[0]
        add(checks, "rpm-integrity", "FAIL", f"rpm -V reported package drift: {detail}")


def verify_product(checks: list[dict[str, Any]], libexec: Path) -> None:
    helper = libexec / "verify.sh"
    if os.geteuid() != 0:
        add(checks, "package-verifier", "INFO", "not run without root; rerun health with sudo for full verification")
        return
    if not helper.is_file():
        add(checks, "package-verifier", "FAIL", f"missing verifier: {helper}")
        return
    result = run([str(helper)], timeout=600)
    if result is None:
        add(checks, "package-verifier", "FAIL", "verifier could not be executed")
    elif result.returncode == 0:
        add(checks, "package-verifier", "PASS", "package verifier passed")
    else:
        add(checks, "package-verifier", "FAIL", f"package verifier returned rc={result.returncode}")



def topology(checks: list[dict[str, Any]], status: dict[str, Any]) -> None:
    mode = status.get("runtime_mode")
    services = status.get("services") if isinstance(status.get("services"), dict) else {}
    if mode == "normal":
        expected = {
            "ollama.service": "active",
            "ollama-task.service": "active",
            "ollama-embedding.service": "active",
            "ollama-agent.service": "inactive",
        }
        bad = [
            f"{unit}={services.get(unit, {}).get('active', 'unknown')}"
            for unit, want in expected.items()
            if services.get(unit, {}).get("active") != want
        ]
        if bad:
            add(checks, "runtime-topology", "FAIL", "normal topology mismatch: " + ", ".join(bad))
        else:
            add(checks, "runtime-topology", "PASS", "normal Ollama topology is healthy")
    elif mode == "agent":
        add(checks, "runtime-topology", "PASS", "exclusive Agent topology is active")
    elif mode in {"degraded", "stopped"}:
        add(checks, "runtime-topology", "FAIL", f"runtime mode is {mode}")
    else:
        add(checks, "runtime-topology", "WARN", "runtime topology could not be classified")



def runtime_identities(checks: list[dict[str, Any]], status: dict[str, Any]) -> None:
    identities = status.get("runtime_identity")
    if not isinstance(identities, dict):
        add(checks, "runtime-identity", "WARN", "package runtime identity is unavailable")
        return
    if identities.get("inspection") == "not_inspected":
        add(
            checks,
            "runtime-identity",
            "INFO",
            "not inspected without root; run with sudo for package-owned container identity",
        )
        return
    for key, label in (("open_webui", "Open WebUI"), ("tika", "Tika")):
        row = identities.get(key)
        if not isinstance(row, dict):
            add(checks, f"runtime-{key}", "WARN", f"{label} runtime identity is unavailable")
            continue
        expected = row.get("expected") if isinstance(row.get("expected"), dict) else {}
        observed = row.get("observed") if isinstance(row.get("observed"), dict) else {}
        match = row.get("match")
        detail = (
            f"expected {expected.get('version') or 'unknown'} @ {expected.get('digest') or 'unknown'}; "
            f"observed {observed.get('version') or 'unavailable'} @ {observed.get('digest') or 'unavailable'}"
        )
        if match is True:
            add(checks, f"runtime-{key}", "PASS", detail)
        elif match is False:
            add(checks, f"runtime-{key}", "FAIL", detail)
        else:
            add(checks, f"runtime-{key}", "WARN", detail)


def resources(checks: list[dict[str, Any]], status: dict[str, Any]) -> None:
    memory = status.get("memory") if isinstance(status.get("memory"), dict) else {}
    available = memory.get("mem_available_kib")
    if isinstance(available, int):
        mib = available / 1024
        if mib < 128:
            add(checks, "memory-headroom", "FAIL", f"MemAvailable={mib:.0f} MiB below 128 MiB hard floor")
        elif mib < 512:
            add(checks, "memory-headroom", "WARN", f"MemAvailable={mib:.0f} MiB; diagnostic headroom TIGHT")
        else:
            add(checks, "memory-headroom", "PASS", f"MemAvailable={mib:.0f} MiB")
    else:
        add(checks, "memory-headroom", "WARN", "MemAvailable unavailable")
    used = memory.get("swap_used_kib")
    if isinstance(used, int):
        add(checks, "swap", "PASS", f"SwapUsed={used / 1024:.0f} MiB")
    else:
        add(checks, "swap", "WARN", "swap usage unavailable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bc250 health", description="Run read-only appliance health diagnostics.")
    parser.add_argument("--json", action="store_true", help="emit machine-readable diagnostics")
    args = parser.parse_args(argv)
    libexec = Path(os.environ.get("BC250_LIBEXEC", DEFAULT_LIBEXEC))
    checks: list[dict[str, Any]] = []
    try:
        status = load_status(libexec)
    except (RuntimeError, TypeError, json.JSONDecodeError) as exc:
        add(checks, "status", "FAIL", str(exc))
        status = {}
    package = status.get("package") if isinstance(status.get("package"), dict) else {}
    nevra = package.get("nevra")
    add(
        checks,
        "package-identity",
        "PASS" if nevra else "FAIL",
        str(nevra or "installed package identity unavailable"),
    )
    rpm_verify(checks)
    failed = status.get("failed_units")
    if failed == []:
        add(checks, "failed-units", "PASS", "no failed systemd units")
    elif isinstance(failed, list):
        add(checks, "failed-units", "FAIL", "failed units: " + ", ".join(map(str, failed)))
    else:
        add(checks, "failed-units", "WARN", "failed-unit query unavailable")
    topology(checks, status)
    runtime_identities(checks, status)
    resources(checks, status)
    verify_product(checks, libexec)

    failures = sum(item["status"] == "FAIL" for item in checks)
    warnings = sum(item["status"] == "WARN" for item in checks)
    overall = "FAIL" if failures else ("WARN" if warnings else "PASS")
    payload = {
        "schema": "bc250.doctor.v3",
        "overall": overall,
        "failures": failures,
        "warnings": warnings,
        "checks": checks,
    }
    if args.json:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(f"Overall appliance health: {color_verdict(overall)}")
        for item in checks:
            prefix = "APP"
            print(f"[{color_verdict(item['status']):<4}] {prefix} {item['name']}: {item['detail']}")
        if os.geteuid() != 0:
            print("Run with sudo for the full bc250 verify portion.")
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
