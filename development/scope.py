#!/usr/bin/env python3
"""BC-250 development-scope helper.

Routine development should operate on active components plus crossed boundaries while
frozen/archive-only components are verified by deterministic tree hash. This preserves
the full source tree without repeatedly loading or testing stable domains.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "development" / "DEVELOPMENT-SCOPE.json"
HASHED_STATUSES = {"frozen", "archive_only"}
VALID_STATUSES = {"active", "boundary_active", "frozen", "archive_only"}


def load_manifest() -> dict:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise RuntimeError(f"unsupported development scope schema: {data.get('schema_version')!r}")
    return data


def ignored_generated_path(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return "__pycache__" in rel.parts or path.suffix in {".pyc", ".pyo"}


@lru_cache(maxsize=1)
def all_source_files() -> tuple[Path, ...]:
    return tuple(
        path
        for path in ROOT.rglob("*")
        if (path.is_file() or path.is_symlink()) and not ignored_generated_path(path)
    )


def matching_files(patterns: list[str]) -> list[Path]:
    files: dict[str, Path] = {}
    for pattern in patterns:
        for path in all_source_files():
            rel = path.relative_to(ROOT).as_posix()
            if fnmatch.fnmatchcase(rel, pattern):
                files[rel] = path
    return [files[key] for key in sorted(files)]


def component_hash(component: dict) -> tuple[str, list[str]]:
    paths = matching_files(component.get("paths", []))
    digest = hashlib.sha256()
    rels: list[str] = []
    for path in paths:
        rel = path.relative_to(ROOT).as_posix()
        rels.append(rel)
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(path.readlink().as_posix().encode("utf-8"))
        else:
            digest.update(b"file\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(b"\n")
    return digest.hexdigest(), rels


def matching_components(manifest: dict, rel: str) -> list[tuple[str, dict]]:
    matches = []
    for name, component in manifest["components"].items():
        if any(fnmatch.fnmatchcase(rel, pattern) for pattern in component.get("paths", [])):
            matches.append((name, component))
    return matches


def cmd_summary(manifest: dict) -> int:
    grouped: dict[str, list[str]] = {status: [] for status in VALID_STATUSES}
    for name, component in manifest["components"].items():
        grouped[component["status"]].append(name)
    for status in ("active", "boundary_active", "frozen", "archive_only"):
        print(f"{status}:")
        for name in sorted(grouped[status]):
            print(f"  - {name}: {manifest['components'][name]['description']}")
    return 0


def cmd_check(manifest: dict, quiet: bool) -> int:
    failures: list[str] = []
    release = manifest.get("release", {})
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
    match = re.search(r"^Release:\s*([^%\s]+)", spec, re.MULTILINE)
    rpm_release = match.group(1) if match else None
    nvr = f"bc250-llm-server-{version}-{rpm_release}" if rpm_release else None
    if release.get("version") != version:
        failures.append(f"manifest version {release.get('version')!r} != VERSION {version!r}")
    if release.get("rpm_release") != rpm_release:
        failures.append(f"manifest RPM release {release.get('rpm_release')!r} != spec Release {rpm_release!r}")
    if release.get("nvr") != nvr:
        failures.append(f"manifest NVR {release.get('nvr')!r} != source NVR {nvr!r}")

    for name, component in manifest.get("components", {}).items():
        status = component.get("status")
        if status not in VALID_STATUSES:
            failures.append(f"{name}: invalid status {status!r}")
            continue
        for field in ("paths", "watch_paths"):
            for pattern in component.get(field, []):
                if not matching_files([pattern]):
                    failures.append(f"{name}: {field} pattern matches no files: {pattern}")
        digest, files = component_hash(component)
        if not files:
            failures.append(f"{name}: path patterns match no files")
        expected = component.get("baseline_sha256")
        if status in HASHED_STATUSES:
            if not expected or expected == "TO_BE_FILLED":
                failures.append(f"{name}: missing frozen/archive baseline_sha256")
            elif digest != expected:
                failures.append(
                    f"{name}: {status} tree changed: expected {expected}, got {digest}; "
                    "thaw/update the component deliberately before continuing"
                )
        elif expected:
            failures.append(f"{name}: {status} component must not carry baseline_sha256")
        if not quiet:
            suffix = f" sha256={digest}" if status in HASHED_STATUSES else ""
            print(f"{name}: {status} files={len(files)}{suffix}")

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1
    if not quiet:
        print("Development scope check passed.")
    return 0


def cmd_map(manifest: dict, paths: list[str]) -> int:
    if not paths:
        paths = [line.strip() for line in sys.stdin if line.strip()]
    if not paths:
        print("ERROR: provide repository-relative paths or pipe them on stdin", file=sys.stderr)
        return 2

    touched: dict[str, dict] = {}
    watched: dict[str, set[str]] = {}
    unclassified: list[str] = []
    for raw in paths:
        rel = raw.strip().removeprefix("./")
        matches = matching_components(manifest, rel)
        labels = []
        for name, component in matches:
            touched[name] = component
            labels.append(f"{name}[{component['status']}]")
        for name, component in manifest["components"].items():
            if component.get("status") != "frozen":
                continue
            if any(fnmatch.fnmatchcase(rel, pattern) for pattern in component.get("watch_paths", [])):
                watched.setdefault(name, set()).add(rel)
                labels.append(f"{name}[boundary-watch]")
        if not labels:
            unclassified.append(rel)
            print(f"{rel}: UNCLASSIFIED")
            continue
        print(f"{rel}: {', '.join(labels)}")

    print("\nAffected development scope:")
    tests: set[str] = set()
    needs_thaw = False
    for name in sorted(touched):
        component = touched[name]
        status = component["status"]
        print(f"  {name}: {status}")
        tests.update(component.get("focused_tests", []))
        if status in HASHED_STATUSES:
            needs_thaw = True
            print("    ACTION: thaw deliberately before editing; update baseline only after focused validation.")
        for trigger in component.get("thaw_if", []):
            print(f"    thaw trigger: {trigger}")
        for interface in component.get("boundary_interfaces", []):
            print(f"    boundary: {interface}")

    if watched:
        print("\nFrozen boundary watches (review interface only; do not thaw automatically):")
        for name in sorted(watched):
            component = manifest["components"][name]
            print(f"  {name}: {', '.join(sorted(watched[name]))}")
            for trigger in component.get("thaw_if", []):
                print(f"    thaw if: {trigger}")

    if tests:
        print("\nFocused test modules:")
        for test in sorted(tests):
            print(f"  {test}")
    if unclassified:
        print("\nWARNING: unclassified changed paths require manual scope review:")
        for rel in unclassified:
            print(f"  {rel}")
    return 3 if needs_thaw else 0


def cmd_hash(manifest: dict, name: str) -> int:
    component = manifest.get("components", {}).get(name)
    if component is None:
        print(f"ERROR: unknown component {name!r}", file=sys.stderr)
        return 2
    digest, files = component_hash(component)
    print(f"{name} {digest} files={len(files)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("summary", help="show active/boundary/frozen/archive components")
    check = sub.add_parser("check", help="verify manifest and frozen/archive tree hashes")
    check.add_argument("--quiet", action="store_true")
    mapper = sub.add_parser("map", help="map changed repository paths to development components")
    mapper.add_argument("paths", nargs="*")
    hasher = sub.add_parser("hash", help="print the current tree hash for one component")
    hasher.add_argument("component")
    args = parser.parse_args()

    manifest = load_manifest()
    if args.command == "summary":
        return cmd_summary(manifest)
    if args.command == "check":
        return cmd_check(manifest, args.quiet)
    if args.command == "map":
        return cmd_map(manifest, args.paths)
    if args.command == "hash":
        return cmd_hash(manifest, args.component)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
