#!/usr/bin/env python3
"""Report and explicitly reclaim BC-250 package-owned model/build storage."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

GGUF = Path(os.environ.get("BC250_GGUF_ROOT", "/var/lib/bc250-llm-server/gguf"))
OLLAMA = Path(os.environ.get("BC250_OLLAMA_ROOT", "/var/lib/bc250-llm-server/ollama"))
CU_CACHE = Path(os.environ.get("BC250_40CU_CACHE", "/var/cache/bc250-llm-server/40cu"))
SERVICES = ("ollama.service", "ollama-task.service", "ollama-embedding.service", "ollama-agent.service", "open-webui.service")


def human(value: int) -> str:
    return f"{value / 1024**3:.1f} GiB"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def state_pairs() -> list[tuple[Path, Path, str]]:
    pairs: list[tuple[Path, Path, str]] = []
    if not GGUF.is_dir() or not OLLAMA.is_dir():
        return pairs
    # One checksum may exist in more than one Ollama lane, so retain every blob.
    by_hash: dict[str, list[Path]] = {}
    for path in OLLAMA.glob("*/blobs/sha256-*"):
        if path.is_file():
            by_hash.setdefault(path.name.removeprefix("sha256-"), []).append(path)
    for state_path in GGUF.rglob("*.gguf.bc250.json"):
        source = state_path.with_name(state_path.name.removesuffix(".bc250.json"))
        try:
            state = json.loads(state_path.read_text())
            checksum = state["sha256"]
        except (OSError, KeyError, json.JSONDecodeError, TypeError):
            continue
        if source.is_file() and len(checksum) == 64:
            for blob in by_hash.get(checksum, ()): 
                pairs.append((source, blob, checksum))
    return pairs


def tree_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) if root.is_dir() else 0


def blob_referenced(blob: Path) -> bool:
    digest_name = blob.name.removeprefix("sha256-")
    manifests = blob.parents[1] / "manifests"
    if len(digest_name) != 64 or not manifests.is_dir():
        return False
    needle = f"sha256:{digest_name}"
    for manifest in manifests.rglob("*"):
        if manifest.is_file():
            try:
                if needle in manifest.read_text(errors="replace"):
                    return True
            except OSError:
                continue
    return False


def stale_cu_caches() -> list[Path]:
    if not CU_CACHE.is_dir():
        return []
    return [p for p in CU_CACHE.iterdir() if p.is_dir() and not Path("/usr/lib/modules", p.name).is_dir()]


def status() -> int:
    free = shutil.disk_usage(GGUF if GGUF.exists() else "/").free
    pairs = state_pairs()
    print("BC-250 storage")
    print(f"  filesystem free:       {human(free)}")
    print(f"  GGUF logical bytes:    {human(tree_bytes(GGUF))}")
    print(f"  Ollama logical bytes:  {human(tree_bytes(OLLAMA))}")
    print(f"  dedupe candidate pairs:{len(pairs):9d}")
    print(f"  duplicate logical data:{human(sum(src.stat().st_size for src, _blob, _sha in pairs))}")
    stale = stale_cu_caches()
    print(f"  stale 40-CU caches:    {len(stale):9d}")
    for path in stale:
        print(f"    {path.name}")
    print("Note: after XFS dedupe, du may count shared extents twice; df shows reclaimed capacity.")
    return 0


def require_root() -> None:
    if os.geteuid() != 0:
        raise SystemExit("ERROR: run with sudo/root")


def xfs_ready() -> None:
    for command in ("findmnt", "xfs_info", "xfs_io"):
        if not shutil.which(command):
            raise SystemExit(f"ERROR: required command missing: {command}")
    if os.stat(GGUF).st_dev != os.stat(OLLAMA).st_dev:
        raise SystemExit("ERROR: GGUF and Ollama stores are on different filesystems")
    fstype = subprocess.check_output(["findmnt", "-n", "-o", "FSTYPE", "-T", str(GGUF)], text=True).strip()
    mount = subprocess.check_output(["findmnt", "-n", "-o", "TARGET", "-T", str(GGUF)], text=True).strip()
    if fstype != "xfs" or "reflink=1" not in subprocess.check_output(["xfs_info", mount], text=True):
        raise SystemExit("ERROR: verified XFS reflink=1 filesystem required")


def active_services() -> list[str]:
    return [
        unit for unit in SERVICES
        if subprocess.run(["systemctl", "is-active", "--quiet", unit], check=False).returncode == 0
    ]


def restore_services(active: list[str]) -> list[str]:
    failed = []
    for unit in (*SERVICES[:-1], "open-webui.service"):
        if unit in active and subprocess.run(["systemctl", "start", unit], check=False).returncode != 0:
            failed.append(unit)
    for unit in active:
        if subprocess.run(["systemctl", "is-active", "--quiet", unit], check=False).returncode != 0:
            failed.append(unit)
    return sorted(set(failed))


def quiesce_services() -> list[str]:
    active = active_services()
    stopped: list[str] = []
    try:
        for unit in ("open-webui.service", *SERVICES[:-1]):
            if unit in active:
                subprocess.run(["systemctl", "stop", unit], check=True)
                stopped.append(unit)
        remaining = active_services()
        if remaining:
            raise RuntimeError(f"services still active after stop: {', '.join(remaining)}")
        return active
    except Exception as exc:
        failed = restore_services(active)
        detail = f"; restoration failed: {', '.join(failed)}" if failed else ""
        raise RuntimeError(f"could not quiesce model services: {exc}{detail}") from exc


def dedupe(yes: bool) -> int:
    require_root(); xfs_ready()
    pairs = state_pairs()
    if not pairs:
        print("No package-managed GGUF/Ollama duplicate pairs found.")
        return 0
    print(f"Verified candidates: {len(pairs)} pair(s), {human(sum(p[0].stat().st_size for p in pairs))} logical duplicate data.")
    if not yes and input("Type DEDUPLICATE to share identical XFS extents: ") != "DEDUPLICATE":
        print("Cancelled."); return 0
    before = shutil.disk_usage(GGUF).free
    active = quiesce_services()
    error: Exception | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="bc250-dedupe-", dir="/var/tmp") as temp:
            alias = Path(temp, "source")
            for index, (source, blob, checksum) in enumerate(pairs, 1):
                if source.stat().st_size != blob.stat().st_size or digest(source) != checksum:
                    raise RuntimeError(f"source/blob state changed for {source}")
                alias.unlink(missing_ok=True); alias.symlink_to(source)
                size = source.stat().st_size
                for offset in range(0, size, 16 * 1024**2):
                    length = min(16 * 1024**2, size - offset)
                    subprocess.run(["xfs_io", "-c", f"dedupe -q {alias} {offset} {offset} {length}", str(blob)], check=True)
                print(f"  [{index}/{len(pairs)}] {source.name}")
        os.sync()
    except (OSError, ValueError) as exc:
        error = exc
    failed = restore_services(active)
    if failed:
        raise RuntimeError(f"failed to restore previously active services: {', '.join(failed)}") from error
    if error:
        raise error
    after = shutil.disk_usage(GGUF).free
    print(f"Filesystem capacity recovered: {human(max(0, after - before))}")
    return 0


def prune_sources(yes: bool) -> int:
    require_root()
    candidates: dict[Path, tuple[Path, str]] = {}
    for source, blob, checksum in state_pairs():
        if Path("mtp") in source.relative_to(GGUF).parents or not blob_referenced(blob):
            continue
        candidates.setdefault(source, (blob, checksum))
    print(f"Validated registered source candidates: {len(candidates)}")
    if not yes and input("Type PRUNE-SOURCES to remove these offline GGUF source copies: ") != "PRUNE-SOURCES":
        print("Cancelled."); return 0
    removed = 0
    for source, (blob, checksum) in candidates.items():
        if digest(source) != checksum or digest(blob) != checksum:
            print(f"  skip changed/unverified: {source}")
            continue
        removed += source.stat().st_size
        source.unlink()
        source.with_name(source.name + ".bc250.json").unlink(missing_ok=True)
        print(f"  removed {source}")
    print(f"Removed offline source data: {human(removed)}")
    return 0


def prune_40cu(yes: bool) -> int:
    require_root()
    stale = stale_cu_caches()
    if not stale:
        print("No 40-CU cache for removed kernels found."); return 0
    for path in stale: print(f"  {path}")
    if not yes and input("Type PRUNE-40CU to remove only the listed obsolete-kernel caches: ") != "PRUNE-40CU":
        print("Cancelled."); return 0
    for path in stale: shutil.rmtree(path)
    print(f"Removed {len(stale)} obsolete 40-CU cache tree(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="bc250-storage")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    for name in ("dedupe", "prune-sources", "prune-40cu"):
        child = sub.add_parser(name); child.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    return {"status": status, "dedupe": lambda: dedupe(args.yes), "prune-sources": lambda: prune_sources(args.yes), "prune-40cu": lambda: prune_40cu(args.yes)}[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
