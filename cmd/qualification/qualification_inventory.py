#!/usr/bin/env python3
"""Inventory and safely prune package-owned qualification evidence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from resilience_common import (
        QualificationError,
        qualification_identity,
        query_installed_rpm,
    )
except ImportError as exc:  # pragma: no cover - packaged bootstrap path
    print(f"ERROR: qualification common module unavailable: {exc}", file=sys.stderr)
    raise SystemExit(2) from None

SCHEMA = "bc250.qualification-inventory.v1"
PACKAGE_GATE_ROOT = Path(os.environ.get("BC250_PACKAGE_GATE_ROOT", "/var/lib/bc250-llm-server/package-gates"))
RESILIENCE_ROOT = Path(os.environ.get("BC250_RESILIENCE_ROOT", "/var/lib/bc250-llm-server/resilience"))
GFX_BENCH_ROOT = Path(os.environ.get("BC250_GFX1013_BENCH_ROOT", "/var/lib/bc250-llm-server/gfx1013/benchmarks"))
KNOWN_ROOTS = {
    "package-gate": PACKAGE_GATE_ROOT,
    "resilience": RESILIENCE_ROOT,
    "gfx1013-benchmark": GFX_BENCH_ROOT,
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: Any, fallback: Path) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            pass
    return datetime.fromtimestamp(fallback.stat().st_mtime, tz=UTC)


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def directory_size(path: Path) -> int:
    total = 0
    for current in path.rglob("*"):
        try:
            if current.is_file() and not current.is_symlink():
                total += current.stat().st_size
        except OSError:
            continue
    return total


def current_model_digests() -> dict[str, str] | None:
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/tags",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, UnicodeError, json.JSONDecodeError):
        return None
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return None
    result: dict[str, str] = {}
    for row in models:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("model") or "")
        digest = str(row.get("digest") or "")
        if name and digest:
            result[name] = digest
    return result


def current_context() -> tuple[dict[str, Any] | None, str | None, dict[str, str] | None]:
    model_digests = current_model_digests()
    try:
        identity = qualification_identity()
        installed = query_installed_rpm()
        return identity, installed.get("nevra"), model_digests
    except QualificationError:
        return None, None, model_digests


def app_identity_match(recorded: Any, current: dict[str, Any] | None) -> str:
    if current is None:
        return "UNKNOWN"
    if not isinstance(recorded, dict):
        return "UNKNOWN"
    return "CURRENT" if recorded == current else "STALE"


def scan_package_gates(current: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = PACKAGE_GATE_ROOT
    if not root.is_dir():
        return rows
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.is_symlink():
            continue
        gate = load_json(path / "gate.json")
        if gate is None:
            rows.append(base_row("package-gate", path, None, "UNKNOWN", "BROKEN", False, "gate.json unreadable"))
            continue
        result = str(gate.get("result") or "UNKNOWN")
        row = base_row(
            "package-gate",
            path,
            gate.get("created_at"),
            app_identity_match(gate.get("qualification_identity"), current),
            result,
            True,
            "closed package-gate artifact",
        )
        rows.append(row)
    return rows


def scan_resilience(current: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = RESILIENCE_ROOT
    if not root.is_dir():
        return rows
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.is_symlink():
            continue
        state = load_json(path / "state.json")
        if state is None:
            rows.append(base_row("resilience", path, None, "UNKNOWN", "BROKEN", False, "state.json unreadable"))
            continue
        result = str(state.get("result") or "UNKNOWN")
        phase = str(state.get("phase") or "UNKNOWN")
        terminal = phase == "complete" or result in {"DEFECT", "SAFETY"}
        detail = f"phase={phase}"
        rows.append(
            base_row(
                "resilience",
                path,
                state.get("created_at"),
                app_identity_match(state.get("qualification_identity"), current),
                result,
                terminal,
                detail,
            )
        )
    return rows


def benchmark_applicability(
    campaign: dict[str, Any],
    current_nevra: str | None,
    model_digests: dict[str, str] | None,
) -> str:
    if current_nevra is None:
        return "UNKNOWN"
    identity = campaign.get("identity") if isinstance(campaign.get("identity"), dict) else {}
    recorded = str(identity.get("package_nevra") or "")
    # Benchmark campaigns use the human rpm -q NEVRA without an explicit epoch,
    # while qualification common uses an epoch-bearing normalized identity.
    current_short = current_nevra.replace("-0:", "-")
    if recorded != current_short or identity.get("kernel") != os.uname().release:
        return "STALE"
    models = campaign.get("models") if isinstance(campaign.get("models"), dict) else {}
    if not models:
        return "UNKNOWN"
    if model_digests is None:
        return "UNKNOWN"
    for row in models.values():
        if not isinstance(row, dict):
            return "UNKNOWN"
        model = str(row.get("model") or "")
        digest = str(row.get("digest") or "")
        if not model or not digest:
            return "UNKNOWN"
        if model_digests.get(model) != digest:
            return "STALE"
    return "CURRENT"


def scan_gfx_benchmarks(
    current_nevra: str | None,
    model_digests: dict[str, str] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = GFX_BENCH_ROOT
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("campaign-*")):
        if not path.is_dir() or path.is_symlink():
            continue
        campaign = load_json(path / "campaign.json")
        if campaign is None:
            rows.append(base_row("gfx1013-benchmark", path, None, "UNKNOWN", "BROKEN", False, "campaign.json unreadable"))
            continue
        phases = campaign.get("phases") if isinstance(campaign.get("phases"), dict) else {}
        report = load_json(path / "report.json")
        result = "INCOMPLETE"
        terminal = False
        detail = "phases=" + ",".join(f"{key}:{phases.get(key, 'PENDING')}" for key in ("stock", "gfx", "restored"))
        if report is not None:
            rec = report.get("recommendation") if isinstance(report.get("recommendation"), dict) else {}
            result = str(rec.get("state") or "COMPLETE")
            terminal = bool(
                phases.get("stock") == "CAPTURED"
                and phases.get("gfx") == "CAPTURED"
                and phases.get("restored") == "CAPTURED"
            )
        rows.append(
            base_row(
                "gfx1013-benchmark",
                path,
                campaign.get("created_at"),
                benchmark_applicability(campaign, current_nevra, model_digests),
                result,
                terminal,
                detail,
            )
        )
    return rows


def base_row(
    kind: str,
    path: Path,
    created_at: Any,
    applicability: str,
    result: str,
    terminal: bool,
    detail: str,
) -> dict[str, Any]:
    created = parse_time(created_at, path)
    return {
        "kind": kind,
        "path": str(path),
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "applicability": applicability,
        "result": result,
        "terminal": terminal,
        "detail": detail,
        "size_bytes": directory_size(path),
    }


def inventory() -> list[dict[str, Any]]:
    current, current_nevra, model_digests = current_context()
    rows = [
        *scan_package_gates(current),
        *scan_resilience(current),
        *scan_gfx_benchmarks(current_nevra, model_digests),
    ]
    return sorted(rows, key=lambda row: str(row["created_at"]), reverse=True)


def human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{value}B"


def cmd_list(args: argparse.Namespace) -> int:
    rows = inventory()
    payload = {"schema": SCHEMA, "created_at": utc_now(), "count": len(rows), "items": rows}
    if args.json:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    if not rows:
        print("No package-owned qualification evidence found.")
        return 0
    print("BC-250 qualification evidence")
    for row in rows:
        print(
            f"{row['created_at']}  {row['kind']:<20} {row['result']:<20} "
            f"{row['applicability']:<7} {human_size(int(row['size_bytes'])):>8}  {row['path']}"
        )
    return 0


def safe_candidate(path: Path, kind: str) -> bool:
    root = KNOWN_ROOTS[kind].resolve()
    if path.is_symlink():
        return False
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return False
    return resolved.parent == root and resolved.is_dir()


def clean_candidates(rows: list[dict[str, Any]], *, older_than_days: int, keep_latest: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    chosen: list[dict[str, Any]] = []
    for kind in KNOWN_ROOTS:
        group = [row for row in rows if row["kind"] == kind]
        group.sort(key=lambda row: str(row["created_at"]), reverse=True)
        protected = {row["path"] for row in group[:keep_latest]}
        for row in group:
            if row["path"] in protected or not row["terminal"]:
                continue
            created = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00")).astimezone(UTC)
            if created > cutoff:
                continue
            chosen.append(row)
    return chosen


def cmd_clean(args: argparse.Namespace) -> int:
    if args.apply and os.geteuid() != 0:
        print("ERROR: qualification clean --apply requires root (run with sudo).", file=sys.stderr)
        return 2
    rows = inventory()
    candidates = clean_candidates(rows, older_than_days=args.older_than_days, keep_latest=args.keep_latest)
    total = sum(int(row["size_bytes"]) for row in candidates)
    action = "DELETE" if args.apply else "DRY-RUN"
    print(f"Qualification cleanup: {action}")
    print(f"Policy: terminal evidence older than {args.older_than_days} days; keep latest {args.keep_latest} per kind")
    if not candidates:
        print("No evidence qualifies for cleanup.")
        return 0
    for row in candidates:
        path = Path(str(row["path"]))
        if not safe_candidate(path, str(row["kind"])):
            print(f"ERROR: refusing unsafe cleanup path: {path}", file=sys.stderr)
            return 2
        print(f"  {human_size(int(row['size_bytes'])):>8}  {row['kind']:<20} {path}")
    print(f"Total: {human_size(total)}")
    if not args.apply:
        print("No files were removed. Re-run with --apply to re-evaluate and apply this policy.")
        return 0
    for row in candidates:
        shutil.rmtree(Path(str(row["path"])))
    print(f"Removed {len(candidates)} terminal evidence director{'y' if len(candidates) == 1 else 'ies'}.")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="bc250 qualification",
        description="Inventory and safely prune package-owned qualification evidence.",
    )
    sub = result.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="list package-gate, resilience and GFX benchmark evidence")
    listing.add_argument("--json", action="store_true")
    clean = sub.add_parser("clean", help="prune old terminal evidence; dry-run by default")
    clean.add_argument("--older-than-days", type=int, default=30)
    clean.add_argument("--keep-latest", type=int, default=2)
    clean.add_argument("--apply", action="store_true", help="actually remove the selected evidence")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "clean":
        if args.older_than_days < 0 or args.keep_latest < 1:
            print("ERROR: --older-than-days must be >= 0 and --keep-latest must be >= 1", file=sys.stderr)
            return 2
        return cmd_clean(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
