#!/usr/bin/env python3
"""Download, verify, and prepare the RPM's pinned upstream source archives."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib


ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "packaging/upstreams.toml"
SOURCE_DIR = ROOT / "sources"
BUILD_DIR = ROOT / "build"


class SourceError(RuntimeError):
    pass


def load_sources() -> list[dict]:
    with LOCK.open("rb") as stream:
        document = tomllib.load(stream)
    if document.get("schema") != 1 or not isinstance(document.get("sources"), list):
        raise SourceError(f"invalid source lock: {LOCK}")
    sources = document["sources"]
    seen: set[str] = set()
    for source in sources:
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id or source_id in seen:
            raise SourceError(f"invalid or duplicate source id: {source_id!r}")
        seen.add(source_id)
        commit = source.get("commit", "")
        checksum = source.get("sha256", "")
        if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
            raise SourceError(f"{source_id}: commit must be a full lowercase SHA-1")
        if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
            raise SourceError(f"{source_id}: invalid sha256")
    return sources


def expand(value: str, source: dict) -> str:
    return value.format(commit=source["commit"])


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def verify_archive(source: dict, archive: Path) -> None:
    actual = digest(archive)
    if actual != source["sha256"]:
        raise SourceError(f"{archive}: sha256 {actual} does not match the source lock")
    required = {expand(item, source) for item in source.get("required", [])}
    with tarfile.open(archive, "r:gz") as bundle:
        names: set[str] = set()
        for member in bundle.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise SourceError(f"{archive}: unsafe archive path {member.name!r}")
            names.add(member.name.rstrip("/"))
    missing = sorted(required - names)
    if missing:
        raise SourceError(f"{archive}: missing required members: {', '.join(missing)}")


def download(source: dict, archive: Path) -> None:
    if archive.is_file() and archive.stat().st_size:
        return
    curl = shutil.which("curl")
    if curl is None:
        raise SourceError("curl is required")
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{archive.name}.", dir=SOURCE_DIR, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        command = [
            curl,
            "--fail",
            "--location",
            "--retry",
            "3",
            "--retry-all-errors",
            "--proto",
            "=https",
            "--tlsv1.2",
            "--connect-timeout",
            "20",
            "--output",
            str(temporary),
            expand(source["url"], source),
        ]
        subprocess.run(command, check=True)
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)


def write_checksum_file(paths: list[Path], output: Path) -> None:
    lines = [f"{digest(path)}  {path.name}\n" for path in paths]
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text("".join(lines), encoding="utf-8")
    os.replace(temporary, output)


def prepare_governor_vendor(source: dict, archive: Path) -> Path:
    vendor = SOURCE_DIR / expand(source["vendor_archive"], source)
    work = BUILD_DIR / "governor-source"
    if not vendor.is_file() or not vendor.stat().st_size:
        for command in ("cargo", "tar"):
            if shutil.which(command) is None:
                raise SourceError(f"{command} is required to vendor governor dependencies")
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        subprocess.run(
            ["tar", "-xzf", str(archive), "-C", str(work), "--strip-components=1"],
            check=True,
        )
        cargo_dir = work / ".cargo"
        shutil.rmtree(work / "vendor", ignore_errors=True)
        shutil.rmtree(cargo_dir, ignore_errors=True)
        cargo_dir.mkdir()
        config = subprocess.run(
            ["cargo", "vendor", "--locked", "vendor"],
            cwd=work,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
        (cargo_dir / "config.toml").write_text(config, encoding="utf-8")
        temporary = vendor.with_name(f".{vendor.name}.tmp")
        subprocess.run(
            ["tar", "-cJf", str(temporary), "vendor", ".cargo/config.toml"],
            cwd=work,
            check=True,
        )
        os.replace(temporary, vendor)
    return vendor


def prepare(source: dict) -> None:
    archive = SOURCE_DIR / expand(source["archive"], source)
    print(f"Preparing {source['label']} at {source['commit']}")
    download(source, archive)
    verify_archive(source, archive)
    outputs = [archive]
    if source.get("cargo_vendor"):
        outputs.append(prepare_governor_vendor(source, archive))
        checksum_file = SOURCE_DIR / "governor-sources.sha256"
    else:
        checksum_file = SOURCE_DIR / f"{archive.name}.sha256"
    write_checksum_file(outputs, checksum_file)
    print(f"Prepared {', '.join(str(path) for path in outputs)}")


def output_files(sources: list[dict]) -> list[Path]:
    files: list[Path] = []
    for source in sources:
        files.append(Path("sources") / expand(source["archive"], source))
        if source.get("cargo_vendor"):
            files.append(Path("sources") / expand(source["vendor_archive"], source))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="source ids; default: all")
    parser.add_argument("--print-files", action="store_true")
    args = parser.parse_args()
    sources = load_sources()
    if args.print_files:
        print(" ".join(str(path) for path in output_files(sources)))
        return 0
    requested = set(args.ids)
    unknown = requested - {source["id"] for source in sources}
    if unknown:
        raise SourceError(f"unknown source ids: {', '.join(sorted(unknown))}")
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    for source in sources:
        if not requested or source["id"] in requested:
            prepare(source)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, SourceError, tarfile.TarError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
