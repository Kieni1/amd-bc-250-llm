#!/usr/bin/env python3
"""Fetch the pinned third-party archives needed by rpmbuild.

Normal builds reuse non-empty files in sources/.  This intentionally keeps
source acquisition separate from release-artifact checksums: the pinned commit
URLs identify upstream revisions, while the generated SRPM records the exact
bytes used for a build.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib


ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "packaging/upstreams.toml"
SOURCE_DIR = ROOT / "sources"
WORK_DIR = ROOT / "build/source-work"


class SourceError(RuntimeError):
    pass


def load_sources() -> list[dict]:
    try:
        with LOCK.open("rb") as stream:
            document = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise SourceError(f"cannot read {LOCK}: {error}") from error

    sources = document.get("sources")
    if document.get("schema") != 1 or not isinstance(sources, list):
        raise SourceError(f"invalid source manifest: {LOCK}")

    required = ("id", "label", "commit", "url", "archive")
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise SourceError("each source entry must be a TOML table")
        for key in required:
            value = source.get(key)
            if not isinstance(value, str) or not value:
                raise SourceError(f"source entry has invalid {key!r}")
        source_id = source["id"]
        if source_id in seen:
            raise SourceError(f"duplicate source id: {source_id}")
        seen.add(source_id)
        commit = source["commit"]
        if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
            raise SourceError(f"{source_id}: commit must be a full lowercase SHA-1")
        if source.get("cargo_vendor") and not isinstance(source.get("vendor_archive"), str):
            raise SourceError(f"{source_id}: cargo_vendor requires vendor_archive")
    return sources


def expand(value: str, source: dict) -> str:
    return value.format(commit=source["commit"])


def source_files(sources: list[dict]) -> list[Path]:
    files: list[Path] = []
    for source in sources:
        files.append(SOURCE_DIR / expand(source["archive"], source))
        if source.get("cargo_vendor"):
            files.append(SOURCE_DIR / expand(source["vendor_archive"], source))
    return files


def display_path(path: Path) -> Path:
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def download(source: dict, archive: Path, *, force: bool) -> None:
    if archive.is_file() and archive.stat().st_size and not force:
        print(f"Using cached {display_path(archive)}")
        return
    curl = shutil.which("curl")
    if curl is None:
        raise SourceError("curl is required to fetch missing sources")

    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{archive.name}.",
        dir=SOURCE_DIR,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
    try:
        subprocess.run(
            [
                curl,
                "--fail",
                "--location",
                "--retry",
                "3",
                "--retry-all-errors",
                "--proto",
                "=https",
                "--tlsv1.2",
                "--output",
                str(temporary),
                expand(source["url"], source),
            ],
            check=True,
        )
        if temporary.stat().st_size == 0:
            raise SourceError(f"download produced an empty archive: {archive.name}")
        os.replace(temporary, archive)
        print(f"Fetched {display_path(archive)}")
    finally:
        temporary.unlink(missing_ok=True)


def prepare_cargo_vendor(source: dict, archive: Path, *, force: bool) -> Path:
    vendor = SOURCE_DIR / expand(source["vendor_archive"], source)
    if vendor.is_file() and vendor.stat().st_size and not force:
        print(f"Using cached {display_path(vendor)}")
        return vendor

    for command in ("cargo", "tar"):
        if shutil.which(command) is None:
            raise SourceError(f"{command} is required to create the Cargo vendor archive")

    work = WORK_DIR / source["id"]
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    subprocess.run(
        ["tar", "-xzf", str(archive), "-C", str(work), "--strip-components=1"],
        check=True,
    )
    shutil.rmtree(work / "vendor", ignore_errors=True)
    shutil.rmtree(work / ".cargo", ignore_errors=True)
    (work / ".cargo").mkdir()
    config = subprocess.run(
        ["cargo", "vendor", "--locked", "vendor"],
        cwd=work,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
    (work / ".cargo/config.toml").write_text(config, encoding="utf-8")

    temporary = vendor.with_name(f".{vendor.name}.tmp")
    try:
        subprocess.run(
            [
                "tar",
                "--sort=name",
                "--format=gnu",
                "--mtime=@0",
                "--owner=0",
                "--group=0",
                "--numeric-owner",
                "-cJf",
                str(temporary),
                "vendor",
                ".cargo/config.toml",
            ],
            cwd=work,
            check=True,
        )
        os.replace(temporary, vendor)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Created {display_path(vendor)}")
    return vendor


def prepare(source: dict, *, force: bool) -> None:
    archive = SOURCE_DIR / expand(source["archive"], source)
    print(f"Preparing {source['label']} ({source['commit']})")
    download(source, archive, force=force)
    if source.get("cargo_vendor"):
        prepare_cargo_vendor(source, archive, force=force)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="source ids; default: all")
    parser.add_argument("--force", action="store_true", help="replace selected cached files")
    parser.add_argument("--print-files", action="store_true", help="print RPM source paths")
    parser.add_argument("--check", action="store_true", help="check that all source files exist")
    args = parser.parse_args()

    sources = load_sources()
    if args.print_files:
        print(" ".join(str(path.relative_to(ROOT)) for path in source_files(sources)))
        return 0

    requested = set(args.ids)
    unknown = requested - {source["id"] for source in sources}
    if unknown:
        raise SourceError(f"unknown source ids: {', '.join(sorted(unknown))}")
    selected = [source for source in sources if not requested or source["id"] in requested]

    if args.check:
        missing = [
            str(path.relative_to(ROOT))
            for path in source_files(selected)
            if not path.is_file() or path.stat().st_size == 0
        ]
        if missing:
            raise SourceError(f"missing source files: {', '.join(missing)}")
        print(f"Source cache ready: {len(source_files(selected))} file(s)")
        return 0

    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    for source in selected:
        prepare(source, force=args.force)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, SourceError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
