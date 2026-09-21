#!/usr/bin/env python3
"""Validate the carried CU live-manager patch against the exact pinned source."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
UPSTREAMS = ROOT / "packaging/upstreams.toml"
NOTICES = ROOT / "licenses/THIRD_PARTY_NOTICES.md"
PATCH = ROOT / "patches/cu-live-manager-rpm-paths.patch"
SOURCES = ROOT / "sources"


class ValidationError(RuntimeError):
    pass


def load_live_manager_pin(root: Path = ROOT) -> dict[str, object]:
    path = root / "packaging/upstreams.toml"
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValidationError(f"cannot read upstream source manifest: {error}") from error

    sources = document.get("sources")
    if document.get("schema") != 1 or not isinstance(sources, list):
        raise ValidationError("upstream source manifest has an unsupported schema")

    matches = [
        source
        for source in sources
        if isinstance(source, dict) and source.get("id") == "live_manager"
    ]
    if len(matches) != 1:
        raise ValidationError("upstream source manifest must contain exactly one live_manager pin")
    source = matches[0]
    commit = source.get("commit")
    archive = source.get("archive")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValidationError("live_manager commit is not a full 40-character revision")
    if not isinstance(archive, str) or "{commit}" not in archive:
        raise ValidationError("live_manager archive template does not contain {commit}")
    return source


def validate_notice_revision(root: Path, commit: str) -> None:
    try:
        text = (root / "licenses/THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    except OSError as error:
        raise ValidationError(f"cannot read third-party notices: {error}") from error
    match = re.search(
        r"(?ms)^## CU live manager\s*$\n(?P<body>.*?)(?=^##\s|\Z)", text
    )
    if match is None:
        raise ValidationError("third-party notices are missing the CU live manager section")
    revisions = re.findall(r"`([0-9a-f]{40})`", match.group("body"))
    if revisions != [commit]:
        recorded = ", ".join(revisions) if revisions else "none"
        raise ValidationError(
            f"CU live-manager notice revision differs from pinned source: {recorded} != {commit}"
        )


def find_source_root(extract_root: Path) -> Path:
    scripts = list(extract_root.rglob("bc250-cu-live-manager.sh"))
    if len(scripts) != 1:
        raise ValidationError(
            "pinned live-manager archive must contain exactly one bc250-cu-live-manager.sh"
        )
    return scripts[0].parent


def run_patch(source_root: Path, patch_path: Path, *, dry_run: bool) -> None:
    patch_binary = shutil.which("patch")
    if patch_binary is None:
        raise ValidationError("patch executable is required for upstream patch validation")
    command = [patch_binary, "--batch", "--forward", "-p1"]
    if dry_run:
        command.append("--dry-run")
    command.extend(["-i", str(patch_path)])
    result = subprocess.run(
        command,
        cwd=source_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        phase = "dry-run" if dry_run else "apply"
        raise ValidationError(f"live-manager patch {phase} failed: {detail}")


def validate_patched_semantics(script_path: Path) -> None:
    try:
        text = script_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValidationError(f"cannot read patched live-manager source: {error}") from error

    required = (
        'SERVICE_BIN="/usr/bin/bc250-cu-live-manager"',
        "/usr/sbin/reboot",
        '[ -x "$SERVICE_BIN" ] || die "packaged service executable is missing: $SERVICE_BIN"',
    )
    for snippet in required:
        if snippet not in text:
            raise ValidationError(
                f"patched live-manager source is missing intended behavior: {snippet}"
            )

    forbidden = (
        "systemctl reboot",
        'source_path="$(readlink -f "$0")"',
        'rm -f "$SERVICE_PATH" "$SERVICE_BIN"',
    )
    for snippet in forbidden:
        if snippet in text:
            raise ValidationError(
                f"patched live-manager source retains obsolete behavior: {snippet}"
            )


def validate_live_manager(root: Path = ROOT, sources_dir: Path | None = None) -> str:
    pin = load_live_manager_pin(root)
    commit = str(pin["commit"])
    validate_notice_revision(root, commit)

    archive_name = str(pin["archive"]).format(commit=commit)
    archive_path = (sources_dir or root / "sources") / archive_name
    patch_path = root / "patches/cu-live-manager-rpm-paths.patch"
    if not archive_path.is_file():
        raise ValidationError(f"pinned live-manager source archive is missing: {archive_path}")
    if not patch_path.is_file():
        raise ValidationError(f"carried live-manager patch is missing: {patch_path}")

    with tempfile.TemporaryDirectory(prefix="bc250-live-manager-patch-") as temporary:
        extract_root = Path(temporary)
        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                archive.extractall(extract_root, filter="data")
        except (OSError, tarfile.TarError) as error:
            raise ValidationError(f"cannot extract pinned live-manager source: {error}") from error

        source_root = find_source_root(extract_root)
        run_patch(source_root, patch_path, dry_run=True)
        run_patch(source_root, patch_path, dry_run=False)
        validate_patched_semantics(source_root / "bc250-cu-live-manager.sh")

    return commit


def main() -> int:
    try:
        commit = validate_live_manager()
    except ValidationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Upstream patch/provenance checks passed for live_manager {commit}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
