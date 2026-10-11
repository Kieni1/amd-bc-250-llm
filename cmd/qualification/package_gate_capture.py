#!/usr/bin/env python3
"""Capture an authoritative package-gate artifact for resilience qualification."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from resilience_common import (
        PACKAGE_GATE_SCHEMA,
        PACKAGE_NAME,
        RESULT_TO_RC,
        QualificationError,
        atomic_write_json,
        normal_topology_status,
        qualification_identity,
        query_candidate_rpm,
        query_installed_rpm,
        run_command,
        scan_secrets,
        sha256_path,
        utc_now,
        write_command_evidence,
    )
except ImportError as exc:  # pragma: no cover - exercised by packaged bootstrap smoke
    print(f"ERROR: package-gate common module unavailable: {exc}", file=sys.stderr)
    raise SystemExit(2) from None

DEFAULT_ROOT = Path("/var/lib/bc250-llm-server/package-gates")
DEFAULT_LIBEXEC = Path("/usr/libexec/bc250-llm-server")
DEFAULT_OWUI_TOKEN = Path("/var/lib/bc250-llm-server/secrets/openwebui-admin.key")
TIKA_EXPECTED = "4.1.0"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="bc250 package-gate",
        description=(
            "Create a closed, package-owned qualification gate. The result is derived "
            "from live checks; there is deliberately no --result override."
        ),
    )
    sub = result.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture", help="capture a new authoritative package gate")
    capture.add_argument("--candidate-rpm", type=Path, required=True)
    capture.add_argument("--output", type=Path)
    capture.add_argument("--source-artifact", type=Path)
    capture.add_argument(
        "--token-file",
        type=Path,
        help="Open WebUI administrator token file; defaults to the protected package token when present",
    )
    capture.add_argument("--libexec", type=Path, default=DEFAULT_LIBEXEC, help=argparse.SUPPRESS)
    return result


def _check_payload(status: str, detail: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"status": status, "detail": detail}
    payload.update(extra)
    return payload


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _tika_smoke(evidence: Path) -> tuple[str, dict[str, object]]:
    checks: dict[str, object] = {}
    active = run_command(["systemctl", "is-active", "tika.service"], timeout=30)
    write_command_evidence(evidence / "tika-service.txt", active)
    if active.returncode != 0 or active.stdout.strip() != "active":
        checks["service"] = _check_payload("DEFECT", "tika.service is not active")
        return "DEFECT", checks
    checks["service"] = _check_payload("PASS", "tika.service active")

    dns = run_command(["podman", "exec", "open-webui", "getent", "hosts", "tika"], timeout=30)
    write_command_evidence(evidence / "tika-dns.txt", dns)
    if dns.returncode != 0:
        checks["owui_dns"] = _check_payload("DEFECT", "Open WebUI cannot resolve private Tika alias")
        return "DEFECT", checks
    checks["owui_dns"] = _check_payload("PASS", "Open WebUI resolves private Tika alias")

    version_script = (
        "import urllib.request; "
        "print(urllib.request.urlopen('http://tika:9998/version', timeout=10).read().decode('utf-8','replace'))"
    )
    version = run_command(["podman", "exec", "open-webui", "python", "-c", version_script], timeout=30)
    write_command_evidence(evidence / "tika-version.txt", version)
    if version.returncode != 0:
        checks["version"] = _check_payload("DEFECT", "Open WebUI cannot reach Tika /version")
        return "DEFECT", checks
    if TIKA_EXPECTED not in version.stdout:
        checks["version"] = _check_payload(
            "DEFECT",
            f"Tika version endpoint did not report {TIKA_EXPECTED}",
            observed=version.stdout.strip(),
        )
        return "DEFECT", checks
    checks["version"] = _check_payload("PASS", f"Tika {TIKA_EXPECTED} reachable from Open WebUI")

    marker = "BC250TIKA410PACKAGEGATE7D6D6F"
    extraction_script = f"""
import urllib.request
marker = {marker!r}
request = urllib.request.Request(
    'http://tika:9998/tika',
    data=(marker + '\\n').encode('utf-8'),
    headers={{'Content-Type': 'text/plain', 'Accept': 'text/plain'}},
    method='PUT',
)
text = urllib.request.urlopen(request, timeout=20).read().decode('utf-8', 'replace')
print(text)
raise SystemExit(0 if marker in text else 7)
""".strip()
    extraction = run_command(
        ["podman", "exec", "open-webui", "python", "-c", extraction_script],
        timeout=45,
    )
    write_command_evidence(evidence / "tika-extraction.txt", extraction)
    if extraction.returncode != 0 or marker not in extraction.stdout:
        checks["deterministic_extraction"] = _check_payload(
            "DEFECT",
            "small deterministic Tika extraction failed",
            expected=marker,
            observed=extraction.stdout.strip(),
            returncode=extraction.returncode,
        )
        return "DEFECT", checks
    checks["deterministic_extraction"] = _check_payload(
        "PASS", "small deterministic text extraction preserved the marker"
    )
    return "PASS", checks


def _closed_manifest(directory: Path) -> None:
    files = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [f"{sha256_path(path)}  {path.relative_to(directory).as_posix()}" for path in files]
    _write_text(directory / "SHA256SUMS", "\n".join(lines))


def _result_priority(statuses: list[str]) -> str:
    if "SAFETY" in statuses:
        return "SAFETY"
    if "HARNESS" in statuses:
        return "HARNESS"
    if "INCOMPLETE" in statuses:
        return "INCOMPLETE"
    if "DEFECT" in statuses:
        return "DEFECT"
    return "PASS"


def capture(args: argparse.Namespace) -> int:
    candidate_path = args.candidate_rpm.resolve()
    if not candidate_path.is_file():
        raise QualificationError(f"candidate RPM does not exist: {candidate_path}", "INCOMPLETE")
    if args.source_artifact is not None and not args.source_artifact.resolve().is_file():
        raise QualificationError(f"source artifact does not exist: {args.source_artifact}", "INCOMPLETE")

    stamp = utc_now().replace(":", "").replace("-", "")
    output = (args.output or (DEFAULT_ROOT / f"gate-{stamp}")).resolve()
    if output.exists() and any(output.iterdir()):
        raise QualificationError(f"output directory is not empty: {output}", "INCOMPLETE")
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    evidence = output / "evidence"
    evidence.mkdir(mode=0o700, exist_ok=True)

    statuses: list[str] = []
    checks: dict[str, object] = {}

    candidate = query_candidate_rpm(candidate_path)
    installed = query_installed_rpm()
    candidate_sha = sha256_path(candidate_path)
    identity_status = "PASS" if candidate == installed else "DEFECT"
    checks["candidate_installed_identity"] = _check_payload(
        identity_status,
        "candidate and installed RPM identities match"
        if identity_status == "PASS"
        else "installed RPM does not match the exact candidate",
        candidate=candidate["nevra"],
        installed=installed["nevra"],
    )
    statuses.append(identity_status)
    _write_text(
        evidence / "rpm-identity.txt",
        f"candidate={candidate['nevra']}\ninstalled={installed['nevra']}\ncandidate_sha256={candidate_sha}",
    )

    qualification = qualification_identity(args.libexec)
    gfx = qualification.get("gfx1013") if isinstance(qualification.get("gfx1013"), dict) else {}
    gfx_state = str(gfx.get("state", "BROKEN"))
    if gfx_state in {"DISABLED", "ENABLED"}:
        gfx_status = "PASS"
        gfx_detail = f"stable GFX1013 lifecycle state: {gfx_state}"
    elif gfx_state in {"PREPARED", "PATCHED_BOOT_UNVERIFIED", "STALE_KERNEL"}:
        gfx_status = "INCOMPLETE"
        gfx_detail = f"transitional/stale GFX1013 lifecycle state: {gfx_state}"
    else:
        gfx_status = "DEFECT"
        gfx_detail = f"unsafe GFX1013 lifecycle state: {gfx_state}"
    checks["qualification_identity"] = _check_payload(
        gfx_status,
        gfx_detail,
        kernel=qualification.get("kernel"),
        gfx1013_state=gfx_state,
    )
    statuses.append(gfx_status)
    _write_text(evidence / "qualification-identity.json", json.dumps(qualification, indent=2, sort_keys=True))

    verify_path = args.libexec / "verify.sh"
    if not verify_path.is_file():
        checks["bc250_verify"] = _check_payload("HARNESS", f"missing verifier: {verify_path}")
        statuses.append("HARNESS")
    else:
        verify = run_command([str(verify_path)], timeout=600)
        write_command_evidence(evidence / "bc250-verify.txt", verify)
        status = "PASS" if verify.returncode == 0 else "DEFECT"
        checks["bc250_verify"] = _check_payload(status, f"bc250 verify rc={verify.returncode}")
        statuses.append(status)

    rpm_verify = run_command(["rpm", "-V", PACKAGE_NAME], timeout=120)
    write_command_evidence(evidence / "rpm-verify.txt", rpm_verify)
    rpm_clean = rpm_verify.returncode == 0 and not rpm_verify.stdout.strip() and not rpm_verify.stderr.strip()
    rpm_status = "PASS" if rpm_clean else "DEFECT"
    checks["rpm_verify"] = _check_payload(rpm_status, "rpm -V clean" if rpm_clean else "rpm -V reported drift")
    statuses.append(rpm_status)

    failed = run_command(["systemctl", "--failed", "--no-legend", "--plain"], timeout=30)
    write_command_evidence(evidence / "failed-units.txt", failed)
    if failed.returncode not in (0, 1):
        failed_status = "HARNESS"
        failed_detail = f"failed-unit query rc={failed.returncode}"
    elif failed.stdout.strip():
        failed_status = "DEFECT"
        failed_detail = "failed systemd units present"
    else:
        failed_status = "PASS"
        failed_detail = "no failed systemd units"
    checks["failed_units"] = _check_payload(failed_status, failed_detail)
    statuses.append(failed_status)

    try:
        topology_ok, topology = normal_topology_status()
        topology_status = "PASS" if topology_ok else "DEFECT"
        checks["normal_topology"] = _check_payload(
            topology_status,
            "normal topology restored" if topology_ok else "normal topology not restored",
            observed=topology,
        )
        statuses.append(topology_status)
        _write_text(evidence / "normal-topology.json", json.dumps(topology, indent=2, sort_keys=True))
    except QualificationError as exc:
        topology_status = "HARNESS"
        checks["normal_topology"] = _check_payload(topology_status, str(exc))
        statuses.append(topology_status)

    try:
        tika_status, tika_checks = _tika_smoke(evidence)
    except QualificationError as exc:
        tika_status, tika_checks = "HARNESS", {"bootstrap": _check_payload("HARNESS", str(exc))}
    checks["tika_4_1_smoke"] = {"status": tika_status, "checks": tika_checks}
    statuses.append(tika_status)

    token_file = args.token_file.resolve() if args.token_file is not None else DEFAULT_OWUI_TOKEN
    rag_status = "INCOMPLETE"
    if token_file.is_file():
        benchmark = args.libexec / "benchmark.sh"
        if benchmark.is_file():
            rag_output = evidence / "owui-rag-smoke"
            rag = run_command(
                [
                    str(benchmark),
                    "owui-rag",
                    "bc250-office-documents",
                    "--token-file",
                    str(token_file),
                    "--output-dir",
                    str(rag_output),
                ],
                timeout=900,
            )
            write_command_evidence(evidence / "owui-rag-smoke-command.txt", rag)
            if rag.returncode == 0:
                rag_status = "PASS"
                rag_detail = (
                    "bounded Open WebUI RAG ingest/retrieve smoke passed "
                    "and synthetic state cleanup completed"
                )
            elif rag.returncode == 3:
                rag_status = "DEFECT"
                rag_detail = "Open WebUI RAG smoke completed with a product/quality defect"
            else:
                rag_status = "HARNESS"
                rag_detail = f"Open WebUI RAG smoke/cleanup failed rc={rag.returncode}"
        else:
            rag_status = "HARNESS"
            rag_detail = f"missing benchmark dispatcher: {benchmark}"
    else:
        rag_detail = f"Open WebUI token unavailable: {token_file}"
    checks["owui_rag_smoke"] = _check_payload(rag_status, rag_detail)
    statuses.append(rag_status)

    restoration_status = (
        "PASS"
        if rpm_status == "PASS" and topology_status == "PASS" and rag_status == "PASS"
        else "DEFECT"
    )
    restoration = {
        "status": restoration_status,
        "rpm_verify": rpm_status,
        "normal_topology": topology_status,
        "owui_rag_cleanup": rag_status,
    }

    source: dict[str, object] | None = None
    if args.source_artifact is not None:
        source_path = args.source_artifact.resolve()
        source = {
            "path": str(source_path),
            "sha256": sha256_path(source_path),
            "size": source_path.stat().st_size,
        }

    # Scan only the text evidence created by this package-owned capture. High-confidence
    # token patterns are sufficient for a safety stop without echoing the secret itself.
    evidence_files = [path for path in evidence.rglob("*") if path.is_file()]
    findings = scan_secrets(evidence_files)
    secret_status = "SAFETY" if findings else "PASS"
    statuses.append(secret_status)
    _write_text(
        evidence / "secret-scan.txt",
        json.dumps({"status": secret_status, "findings": findings}, indent=2, sort_keys=True),
    )

    result = _result_priority(statuses)
    gate = {
        "schema": PACKAGE_GATE_SCHEMA,
        "schema_version": 2,
        "created_at": utc_now(),
        "authority": "bc250 package-gate capture; result derived from package-owned live checks",
        "candidate": {
            **candidate,
            "path": str(candidate_path),
            "sha256": candidate_sha,
            "size": candidate_path.stat().st_size,
        },
        "installed": installed,
        "qualification_identity": qualification,
        "source_artifact": source,
        "checks": checks,
        "cleanup_restoration": restoration,
        "safety_secret": {
            "status": secret_status,
            "finding_count": len(findings),
        },
        "result": result,
        "exit_code": RESULT_TO_RC[result],
    }
    atomic_write_json(output / "gate.json", gate)
    _closed_manifest(output)

    print(f"Package gate: {result}")
    print(f"Candidate:    {candidate['nevra']}")
    print(f"Installed:    {installed['nevra']}")
    print(f"Restoration:  {restoration_status}")
    print(f"Safety/secret:{' ' if secret_status else ''}{secret_status}")
    print(f"Artifact:     {output}")
    return RESULT_TO_RC[result]


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if os.geteuid() != 0:
        print("ERROR: package-gate capture requires root (run with sudo).", file=sys.stderr)
        return 2
    try:
        if args.command == "capture":
            return capture(args)
    except QualificationError as exc:
        print(f"{exc.result}: {exc}", file=sys.stderr)
        return exc.rc
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
