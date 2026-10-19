#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind one selected GitHub build as BC-250 release artifact authority")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    if evidence.get("schema") != "bc250.release-evidence.v2":
        raise SystemExit("ERROR: release selection requires bc250.release-evidence.v2")
    if evidence.get("producer") != "github-actions" or not evidence.get("release_authority"):
        raise SystemExit("ERROR: release selection requires an explicitly selected GitHub Actions authority build")
    github = evidence.get("github", {})
    if github.get("event_name") != "workflow_dispatch":
        raise SystemExit("ERROR: release selection requires workflow_dispatch")
    required = ("commit_sha", "run_id", "run_attempt", "workflow", "workflow_ref")
    missing = [name for name in required if not github.get(name)]
    if missing:
        raise SystemExit(f"ERROR: release selection missing GitHub identity: {', '.join(missing)}")

    binaries = [r for r in evidence["artifacts"]["binary_rpms"] if "-debuginfo-" not in r.get("nevra", "") and "-debugsource-" not in r.get("nevra", "")]
    sources = evidence["artifacts"]["source_rpms"]
    if len(binaries) != 1 or len(sources) != 1:
        raise SystemExit("ERROR: release selection requires exactly one main binary RPM and one SRPM")
    binary = binaries[0]
    source = sources[0]
    record = {
        "schema": "bc250.release-selection.v1",
        "commit": github["commit_sha"],
        "github_run_id": github["run_id"],
        "github_run_attempt": github["run_attempt"],
        "workflow": github["workflow"],
        "workflow_ref": github["workflow_ref"],
        "nevra": binary["nevra"],
        "rpm_sha256": binary["sha256"],
        "srpm_sha256": source["sha256"],
        "source0_sha256": evidence["inputs"]["source0"]["sha256"],
        "spec_sha256": evidence["inputs"]["spec"]["sha256"],
        "release_contract_sha256": evidence["inputs"]["release_contract"]["sha256"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Release selection written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
