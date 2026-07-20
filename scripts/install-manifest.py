#!/usr/bin/env python3
"""Install the RPM payload and generate its explicit RPM file list."""

from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path
import shutil
import subprocess
import sys


class ManifestError(RuntimeError):
    pass


def parse_defines(values: list[str]) -> dict[str, str]:
    definitions: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ManifestError(f"invalid --define value: {value!r}")
        key, definition = value.split("=", 1)
        if not key or not definition:
            raise ManifestError(f"invalid --define value: {value!r}")
        definitions[key] = definition.rstrip("/")
    return definitions


def load_manifest(path: Path) -> list[tuple[int, str, str, str, str]]:
    entries: list[tuple[int, str, str, str, str]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = raw_line.split("\t")
        if len(fields) != 4:
            raise ManifestError(f"{path}:{line_number}: expected four tab-separated fields")
        kind, mode, source, destination = (field.strip() for field in fields)
        if kind not in {"file", "config", "dir", "ghost", "text", "aliases"}:
            raise ManifestError(f"{path}:{line_number}: unknown entry type {kind!r}")
        try:
            int(mode, 8)
        except ValueError as error:
            raise ManifestError(f"{path}:{line_number}: invalid mode {mode!r}") from error
        entries.append((line_number, kind, mode, source, destination))
    return entries


def expand(value: str, definitions: dict[str, str], line_number: int) -> str:
    try:
        return value.format_map(definitions)
    except KeyError as error:
        raise ManifestError(f"manifest line {line_number}: undefined placeholder {error.args[0]!r}") from error


def build_path(buildroot: Path, destination: str) -> Path:
    if not destination.startswith("/") or destination == "/":
        raise ManifestError(f"unsafe manifest destination: {destination!r}")
    target = buildroot / destination.lstrip("/")
    if buildroot.resolve() not in target.resolve().parents:
        raise ManifestError(f"destination escapes buildroot: {destination!r}")
    return target


def rpm_line(kind: str, mode: str, destination: str) -> str:
    if kind == "config":
        return f"%config(noreplace) {destination}"
    if kind == "ghost":
        return f"%ghost %config(noreplace) %attr({mode},root,root) {destination}"
    if kind == "dir":
        return f"%dir %attr({mode},root,root) {destination}"
    return destination


def source_matches(source_root: Path, pattern: str, line_number: int) -> list[Path]:
    if pattern == "-":
        return []
    matches = [Path(item) for item in sorted(glob.glob(str(source_root / pattern)))]
    if not matches:
        raise ManifestError(f"manifest line {line_number}: source does not match: {pattern}")
    if any(not path.is_file() for path in matches):
        raise ManifestError(f"manifest line {line_number}: source patterns must match files only")
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--buildroot", type=Path)
    parser.add_argument("--filelist", type=Path)
    parser.add_argument("--define", action="append", default=[])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    definitions = parse_defines(args.define)
    entries = load_manifest(args.manifest)
    if args.check:
        for line_number, kind, _mode, source, destination in entries:
            expand(destination, definitions, line_number)
            if kind in {"file", "config", "aliases"}:
                source_matches(args.source_root, expand(source, definitions, line_number), line_number)
        print(f"Install manifest valid: {len(entries)} entries")
        return 0
    if args.buildroot is None or args.filelist is None:
        parser.error("--buildroot and --filelist are required unless --check is used")

    buildroot = args.buildroot.resolve()
    buildroot.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}

    def record(kind: str, mode: str, destination: str) -> None:
        line = rpm_line(kind, mode, destination)
        previous = files.get(destination)
        if previous is not None and previous != line:
            raise ManifestError(f"conflicting manifest ownership for {destination}")
        files[destination] = line

    for line_number, kind, mode, source_template, destination_template in entries:
        source_value = expand(source_template, definitions, line_number)
        destination = expand(destination_template, definitions, line_number)
        target = build_path(buildroot, destination)

        if kind == "dir":
            target.mkdir(parents=True, exist_ok=True)
            os.chmod(target, int(mode, 8))
            record(kind, mode, destination)
            continue
        if kind == "ghost":
            record(kind, mode, destination)
            continue
        if kind == "text":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source_value + "\n", encoding="utf-8")
            os.chmod(target, int(mode, 8))
            record("file", mode, destination)
            continue

        sources = source_matches(args.source_root, source_value, line_number)
        if kind == "aliases":
            if len(sources) != 1:
                raise ManifestError(f"manifest line {line_number}: aliases requires one dispatcher")
            result = subprocess.run(
                [str(sources[0]), "--list-aliases"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            )
            target.mkdir(parents=True, exist_ok=True)
            for alias in result.stdout.splitlines():
                if not alias or "/" in alias:
                    raise ManifestError(f"invalid dispatcher alias: {alias!r}")
                alias_destination = f"{destination.rstrip('/')}/bc250-{alias}"
                alias_target = build_path(buildroot, alias_destination)
                alias_target.unlink(missing_ok=True)
                alias_target.symlink_to("bc250")
                record("file", mode, alias_destination)
            continue

        destination_is_directory = destination.endswith("/") or len(sources) > 1
        if len(sources) > 1 and not destination.endswith("/"):
            raise ManifestError(f"manifest line {line_number}: glob destination must end with '/'")
        for source_path in sources:
            file_destination = (
                f"{destination.rstrip('/')}/{source_path.name}"
                if destination_is_directory
                else destination
            )
            file_target = build_path(buildroot, file_destination)
            file_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, file_target)
            os.chmod(file_target, int(mode, 8))
            record(kind, mode, file_destination)

    args.filelist.parent.mkdir(parents=True, exist_ok=True)
    lines = [files[path] for path in sorted(files)]
    temporary = args.filelist.with_name(f".{args.filelist.name}.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary, args.filelist)
    print(f"Installed {len(files)} payload paths; wrote {args.filelist}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ManifestError, OSError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
