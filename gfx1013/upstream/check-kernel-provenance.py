#!/usr/bin/env python3
"""Locate and fingerprint the Fedora-prepared AMDGPU source used by BC-250 patches."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def patch_targets(patch_dir: Path) -> list[str]:
    targets: set[str] = set()
    for patch in sorted(patch_dir.glob("*.patch")):
        for line in patch.read_text(encoding="utf-8", errors="strict").splitlines():
            if not line.startswith(("--- ", "+++ ")):
                continue
            token = line[4:].split("\t", 1)[0].split(" ", 1)[0]
            if token == "/dev/null":
                continue
            if token.startswith(("a/", "b/")):
                token = token[2:]
            if token.startswith("drivers/gpu/drm/amd/"):
                targets.add(token)
    if not targets:
        raise SystemExit("no AMDGPU target files were found in the package patch set")
    return sorted(targets)


def root_for_match(match: Path, target: str) -> Path:
    root = match
    for _ in Path(target).parts:
        root = root.parent
    return root


def prepared_roots(build_root: Path, targets: list[str]) -> list[Path]:
    first = targets[0]
    basename = Path(first).name
    roots: set[Path] = set()
    for match in build_root.rglob(basename):
        if not match.is_file():
            continue
        root = root_for_match(match, first)
        try:
            if (root / first).resolve() != match.resolve():
                continue
        except OSError:
            continue
        if all((root / target).is_file() for target in targets):
            roots.add(root.resolve())
    return sorted(roots)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared-build-root", type=Path, required=True)
    parser.add_argument("--patch-dir", type=Path, required=True)
    parser.add_argument("--root-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    build_root = args.prepared_build_root.resolve()
    if not build_root.is_dir():
        raise SystemExit(f"Fedora kernel %prep BUILD root is missing: {build_root}")

    targets = patch_targets(args.patch_dir)
    roots = prepared_roots(build_root, targets)
    if len(roots) != 1:
        display = ", ".join(str(path) for path in roots[:10]) or "<none>"
        raise SystemExit(
            "Fedora kernel %prep must produce exactly one source tree containing every "
            f"BC-250 AMDGPU patch target; found {len(roots)}: {display}"
        )
    prepared_root = roots[0]

    manifest: list[str] = []
    for target in targets:
        path = prepared_root / target
        if not path.is_file():
            raise SystemExit(f"Fedora-prepared kernel source is missing BC-250 patch target: {target}")
        manifest.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {target}")

    payload = "\n".join(manifest) + "\n"
    manifest_sha = hashlib.sha256(payload.encode()).hexdigest()
    relative_root = prepared_root.relative_to(build_root)
    args.output.write_text(
        "mode=fedora-prepared-source\n"
        f"prepared_root={relative_root}\n"
        f"target_count={len(targets)}\n"
        f"target_manifest_sha256={manifest_sha}\n"
        + payload,
        encoding="utf-8",
    )
    args.root_output.write_text(str(prepared_root) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
