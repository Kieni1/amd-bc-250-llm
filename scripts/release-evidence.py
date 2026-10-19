#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rpm_nevra(path: Path) -> str:
    result = subprocess.run(
        ["rpm", "-qp", "--qf", "%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def file_record(path: Path, *, include_nevra: bool = False) -> dict:
    record = {"file": path.name, "sha256": sha256(path)}
    if include_nevra:
        record["nevra"] = rpm_nevra(path)
    return record



def command_version(argv: list[str]) -> str | None:
    if not shutil.which(argv[0]):
        return None
    result = subprocess.run(argv, text=True, capture_output=True, check=False)
    text = (result.stdout or result.stderr).strip()
    return text.splitlines()[0] if text else None


def build_environment() -> dict:
    fedora_release = None
    fedora_path = Path("/etc/fedora-release")
    if fedora_path.exists():
        fedora_release = fedora_path.read_text(encoding="utf-8").strip()
    return {
        "fedora_release": fedora_release,
        "container_image": os.environ.get("BC250_BUILD_IMAGE_REF"),
        "tools": {
            "rpm": command_version(["rpm", "--version"]),
            "rpmbuild": command_version(["rpmbuild", "--version"]),
            "rpmlint": command_version(["rpmlint", "--version"]),
            "python": command_version(["python3", "--version"]),
            "ruff": command_version(["ruff", "--version"]),
            "shellcheck": command_version(["shellcheck", "--version"]),
            "gcc": command_version(["gcc", "--version"]),
            "cargo": command_version(["cargo", "--version"]),
            "rustc": command_version(["rustc", "--version"]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write BC-250 release artifact evidence")
    parser.add_argument("--source0", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--dist", required=True, type=Path)
    parser.add_argument("--source-identity", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    binaries = sorted(args.dist.glob("*.x86_64.rpm"))
    sources = sorted(args.dist.glob("*.src.rpm"))
    if not binaries or not sources:
        raise SystemExit("ERROR: release evidence requires binary and source RPM artifacts")

    source_identity = json.loads(args.source_identity.read_text(encoding="utf-8"))
    github = {
        "actions": os.environ.get("GITHUB_ACTIONS") == "true",
        "event_name": os.environ.get("GITHUB_EVENT_NAME"),
        "commit_sha": os.environ.get("GITHUB_SHA") or source_identity.get("commit"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "workflow": os.environ.get("GITHUB_WORKFLOW"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "ref": os.environ.get("GITHUB_REF"),
    }
    release_authority = os.environ.get("BC250_RELEASE_AUTHORITY") == "true"
    if release_authority and not github["actions"]:
        raise SystemExit("ERROR: release authority may only be selected from GitHub Actions")
    if release_authority and github["event_name"] != "workflow_dispatch":
        raise SystemExit("ERROR: release authority requires an explicit workflow_dispatch run")
    evidence = {
        "schema": "bc250.release-evidence.v2",
        "producer": "github-actions" if github["actions"] else "local-fedora",
        "release_authority": release_authority,
        "github": github,
        "environment": build_environment(),
        "source_identity": source_identity,
        "inputs": {
            "source0": file_record(args.source0),
            "spec": file_record(args.spec),
            "release_contract": file_record(args.contract),
        },
        "artifacts": {
            "binary_rpms": [file_record(path, include_nevra=True) for path in binaries],
            "source_rpms": [file_record(path, include_nevra=True) for path in sources],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inputs_manifest = args.dist / "SHA256SUMS.inputs"
    inputs_manifest.write_text(
        f"{sha256(args.source0)}  {args.source0.name}\n{sha256(args.spec)}  {args.spec.name}\n",
        encoding="utf-8",
    )
    print(f"Release evidence written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
