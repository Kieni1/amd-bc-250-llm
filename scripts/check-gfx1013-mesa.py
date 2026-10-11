#!/usr/bin/env python3
"""Validate the package GFX1013 Mesa patch against the exact Fedora 44 source."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METADATA = ROOT / "gfx1013/upstream/MESA-SOURCE"
PATCH = ROOT / "gfx1013/upstream/patches/mesa/0001-gfx1013-compute-queue-fix.patch"
CACHE_DIR = ROOT / "sources/gfx1013"

EXPECTED = {
    "version": "26.2.4",
    "fedora_release": "1.fc44",
    "srpm_nevra": "mesa-26.2.4-1.fc44.src",
    "srpm_url": (
        "https://kojipkgs.fedoraproject.org/packages/mesa/26.2.4/1.fc44/"
        "src/mesa-26.2.4-1.fc44.src.rpm"
    ),
    "source0": "mesa-26.2.4.tar.xz",
    "source0_sha256": "bce5f7fbebb934373b86c999a064d52fb5065878dc57f287f95346648ec832e9",
}


class ValidationError(RuntimeError):
    pass


def run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            input=input_bytes,
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise ValidationError(f"cannot execute {argv[0]}: {error}") from error


def require_command(name: str) -> str:
    command = shutil.which(name)
    if command is None:
        raise ValidationError(f"required command is unavailable: {name}")
    return command


def read_metadata(path: Path = METADATA) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValidationError(f"cannot read Mesa source metadata: {error}") from error

    metadata: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key or not value:
            raise ValidationError(f"malformed Mesa source metadata line: {raw!r}")
        if key in metadata:
            raise ValidationError(f"duplicate Mesa source metadata key: {key}")
        metadata[key] = value
    if metadata != EXPECTED:
        raise ValidationError(
            "Mesa source metadata differs from the accepted Fedora 44 baseline: "
            f"{metadata!r} != {EXPECTED!r}"
        )
    return metadata


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ValidationError(f"cannot hash {path}: {error}") from error
    return digest.hexdigest()


def fetch_srpm(metadata: dict[str, str], *, allow_fetch: bool) -> Path:
    target = CACHE_DIR / f"mesa-{metadata['version']}-{metadata['fedora_release']}.src.rpm"
    if target.is_file():
        return target
    if not allow_fetch:
        raise ValidationError(
            f"exact Fedora Mesa SRPM is missing: {target}; run 'make sources' first"
        )
    curl = require_command("curl")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    temporary.unlink(missing_ok=True)
    result = run(
        [curl, "--fail", "--location", "--retry", "3", "--output", str(temporary), metadata["srpm_url"]]
    )
    if result.returncode != 0:
        temporary.unlink(missing_ok=True)
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise ValidationError(f"cannot download exact Fedora Mesa SRPM: {detail}")
    temporary.replace(target)
    return target


def validate_srpm_identity(srpm: Path, metadata: dict[str, str]) -> None:
    rpm = require_command("rpm")
    # Source RPM headers may retain the architecture of the machine that built
    # the SRPM (for example i686/x86_64).  `%{ARCH}` therefore cannot be used
    # to prove that a package is a source RPM.  Validate NEVR separately and
    # require the RPM SOURCEPACKAGE marker instead.
    query = run(
        [
            rpm,
            "-qp",
            "--qf",
            "%{NAME}-%{VERSION}-%{RELEASE}\n%{SOURCEPACKAGE}\n",
            str(srpm),
        ]
    )
    if query.returncode != 0:
        raise ValidationError("cannot query Fedora Mesa SRPM identity")
    fields = query.stdout.decode("utf-8", errors="replace").splitlines()
    if len(fields) != 2:
        raise ValidationError("Fedora Mesa SRPM identity query returned an unexpected result")
    identity, source_package = fields
    expected_nevr = metadata["srpm_nevra"].removesuffix(".src")
    if identity != expected_nevr:
        raise ValidationError(
            f"Fedora Mesa SRPM NEVR mismatch: {identity!r} != {expected_nevr!r}"
        )
    if source_package != "1":
        raise ValidationError(
            f"Fedora Mesa package is not marked as a source RPM (SOURCEPACKAGE={source_package!r})"
        )
    verify = run([rpm, "-K", str(srpm)])
    output = (verify.stdout + verify.stderr).decode("utf-8", errors="replace")
    if verify.returncode != 0 or "NOT OK" in output or "NOKEY" in output:
        raise ValidationError(f"Fedora Mesa SRPM signature verification failed: {output.strip()}")


def extract_srpm(srpm: Path, destination: Path) -> None:
    rpm2cpio = require_command("rpm2cpio")
    cpio = require_command("cpio")
    try:
        with subprocess.Popen(
            [rpm2cpio, str(srpm)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as converted:
            if converted.stdout is None:
                raise ValidationError("rpm2cpio stdout pipe is unavailable")
            extracted = subprocess.run(
                [cpio, "-idm", "--quiet"],
                cwd=destination,
                stdin=converted.stdout,
                capture_output=True,
                check=False,
            )
            converted.stdout.close()
            converter_stderr = converted.stderr.read() if converted.stderr is not None else b""
            converter_rc = converted.wait()
    except OSError as error:
        raise ValidationError(f"cannot extract Fedora Mesa SRPM: {error}") from error
    if converter_rc != 0:
        detail = converter_stderr.decode("utf-8", errors="replace").strip()
        raise ValidationError(f"rpm2cpio failed for Fedora Mesa SRPM: {detail}")
    if extracted.returncode != 0:
        detail = extracted.stderr.decode("utf-8", errors="replace").strip()
        raise ValidationError(f"cannot extract Fedora Mesa SRPM: {detail}")


def prepare_fedora_tree(srpm: Path, metadata: dict[str, str], temporary: Path) -> Path:
    rpmbuild = require_command("rpmbuild")
    extracted = temporary / "srpm"
    extracted.mkdir()
    extract_srpm(srpm, extracted)

    specs = list(extracted.glob("*.spec"))
    if len(specs) != 1:
        raise ValidationError(f"Fedora Mesa SRPM must contain exactly one spec file, found {len(specs)}")
    source0 = extracted / metadata["source0"]
    if not source0.is_file():
        raise ValidationError(f"Fedora Mesa SRPM is missing expected Source0: {metadata['source0']}")
    actual_source0_sha = sha256(source0)
    if actual_source0_sha != metadata["source0_sha256"]:
        raise ValidationError(
            f"Mesa Source0 SHA-256 mismatch: {actual_source0_sha} != {metadata['source0_sha256']}"
        )

    topdir = temporary / "rpmbuild"
    sources = topdir / "SOURCES"
    specs_dir = topdir / "SPECS"
    for directory in (sources, specs_dir, topdir / "BUILD", topdir / "BUILDROOT", topdir / "RPMS", topdir / "SRPMS"):
        directory.mkdir(parents=True, exist_ok=True)
    for item in extracted.iterdir():
        if item.suffix == ".spec":
            shutil.copy2(item, specs_dir / item.name)
        else:
            shutil.copy2(item, sources / item.name)

    result = run(
        [
            rpmbuild,
            "-bp",
            "--nodeps",
            "--define",
            f"_topdir {topdir}",
            str(specs_dir / specs[0].name),
        ]
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise ValidationError(f"Fedora Mesa %prep failed: {detail}")

    candidates = list((topdir / "BUILD").rglob("src/amd/common/ac_gpu_info.c"))
    if len(candidates) != 1:
        raise ValidationError(
            "Fedora Mesa %prep must produce exactly one src/amd/common/ac_gpu_info.c "
            f"(found {len(candidates)})"
        )
    return candidates[0].parents[3]


def validate_pre_patch_semantics(source: Path) -> None:
    text = source.read_text(encoding="utf-8")
    queue_guard = (
        "   /* GFX1013 is known to have broken compute queue */\n"
        "   if (device_info.family == FAMILY_NV && ASICREV_IS(device_info.external_rev, GFX1013)) {\n"
        "      info->ip[AMD_IP_COMPUTE].num_queues = 0;\n"
        "   }\n"
    )
    if text.count(queue_guard) != 1:
        marker = "GFX1013 is known to have broken compute queue"
        start = text.find(marker)
        context = "<marker absent>"
        if start >= 0:
            context = text[max(0, start - 180) : start + 420].strip()
        raise ValidationError(
            "Fedora Mesa baseline no longer contains exactly one expected post-enumeration "
            "GFX1013 compute-queue disable block; observed context: "
            f"{context!r}"
        )
    if "info->family == CHIP_TONGA;" not in text:
        raise ValidationError("Fedora Mesa baseline no longer contains the expected async-compute workaround")

    marker = "/* Fix incorrect IP versions reported by the kernel. */"
    start = text.find(marker)
    if start < 0:
        raise ValidationError("Fedora Mesa baseline is missing the IP-version correction section")
    window = text[start : start + 1200]
    if "ASICREV_IS(device_info->external_rev, GFX1013)" not in window:
        raise ValidationError(
            "Fedora Mesa baseline does not contain the upstreamed GFX1013 IP-version correction"
        )


def apply_patch(source_root: Path, *, dry_run: bool) -> None:
    patch = require_command("patch")
    argv = [patch, "--batch", "--forward", "--fuzz=0", "-p1"]
    if dry_run:
        argv.append("--dry-run")
    argv.extend(["-i", str(PATCH)])
    result = run(argv, cwd=source_root)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        phase = "dry-run" if dry_run else "apply"
        raise ValidationError(f"GFX1013 Mesa patch {phase} failed with zero fuzz: {detail}")


def validate_post_patch_semantics(source: Path) -> None:
    text = source.read_text(encoding="utf-8")
    if "GFX1013 is known to have broken compute queue" in text:
        raise ValidationError("patched Mesa still rejects the GFX1013 compute queue")
    needle = (
        "info->has_async_compute_threadgroup_bug = info->family == CHIP_ICELAND ||\n"
        "                                             info->family == CHIP_TONGA ||\n"
        "                                             info->family == CHIP_GFX1013;"
    )
    if needle not in text:
        raise ValidationError("patched Mesa is missing the GFX1013 async-compute workaround")


def validate(*, allow_fetch: bool) -> str:
    metadata = read_metadata()
    if not PATCH.is_file():
        raise ValidationError(f"GFX1013 Mesa patch is missing: {PATCH}")
    srpm = fetch_srpm(metadata, allow_fetch=allow_fetch)
    validate_srpm_identity(srpm, metadata)

    with tempfile.TemporaryDirectory(prefix="bc250-gfx1013-mesa-") as name:
        temporary = Path(name)
        source_root = prepare_fedora_tree(srpm, metadata, temporary)
        source = source_root / "src/amd/common/ac_gpu_info.c"
        validate_pre_patch_semantics(source)
        apply_patch(source_root, dry_run=True)
        apply_patch(source_root, dry_run=False)
        validate_post_patch_semantics(source)

    return metadata["srpm_nevra"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="download the exact Fedora Mesa SRPM when it is not already cached",
    )
    args = parser.parse_args()
    try:
        identity = validate(allow_fetch=args.fetch)
    except (ValidationError, OSError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"GFX1013 Mesa patch/provenance check passed for {identity} with zero fuzz.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
