#!/usr/bin/env python3
"""Report and explicitly reclaim BC-250 package-owned model/build storage."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat as statmod
import subprocess
import tempfile
from pathlib import Path

GGUF = Path(os.environ.get("BC250_GGUF_ROOT", "/var/lib/bc250-llm-server/gguf"))
OLLAMA = Path(os.environ.get("BC250_OLLAMA_ROOT", "/var/lib/bc250-llm-server/ollama"))
CU_CACHE = Path(os.environ.get("BC250_40CU_CACHE", "/var/cache/bc250-llm-server/40cu"))
INSTALLED_MODEL_DIR = Path("/usr/share/bc250-llm-server/model-management/modelfiles")
OPERATOR_MODEL_DIR = Path("/etc/bc250-llm-server/models.d")
RETIRED_CATALOG = Path("/usr/share/bc250-llm-server/model-management/retired-models.json")
SERVICES = ("ollama.service", "ollama-task.service", "ollama-embedding.service", "ollama-agent.service", "open-webui.service")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
DEDUPE_CHUNK_BYTES = 16 * 1024**2


def human(value: int) -> str:
    return f"{value / 1024**3:.1f} GiB"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def load_json(path: Path) -> dict | list:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def state_pairs() -> list[tuple[Path, Path, str, Path, dict]]:
    pairs: list[tuple[Path, Path, str, Path, dict]] = []
    if not GGUF.is_dir() or not OLLAMA.is_dir():
        return pairs
    by_hash: dict[str, list[Path]] = {}
    for path in OLLAMA.glob("*/blobs/sha256-*"):
        if path.is_file():
            by_hash.setdefault(path.name.removeprefix("sha256-"), []).append(path)
    for state_path in GGUF.rglob("*.gguf.bc250.json"):
        source = state_path.with_name(state_path.name.removesuffix(".bc250.json"))
        state = load_json(state_path)
        if not isinstance(state, dict):
            continue
        checksum = str(state.get("sha256", ""))
        if source.is_file() and SHA256_RE.fullmatch(checksum):
            for blob in by_hash.get(checksum, ()):
                pairs.append((source, blob, checksum, state_path, state))
    return pairs


def tree_bytes(root: Path) -> int | None:
    try:
        root_stat = root.stat()
    except FileNotFoundError:
        return 0
    except PermissionError:
        return None
    if not statmod.S_ISDIR(root_stat.st_mode):
        return 0
    if not os.access(root, os.R_OK | os.X_OK):
        return None
    total = 0

    def raise_walk_error(error: OSError) -> None:
        raise error

    try:
        for directory, _dirs, files in os.walk(root, onerror=raise_walk_error):
            for filename in files:
                total += (Path(directory) / filename).stat().st_size
    except PermissionError:
        return None
    return total


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


def parse_modelfile_identity(path: Path) -> tuple[str, Path] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    name_match = re.search(r"^# Ollama model:\s*(\S+)\s*$", text, re.MULTILINE)
    from_match = re.search(r"^FROM\s+(/\S+\.gguf)\s*$", text, re.MULTILINE)
    if not name_match or not from_match:
        return None
    return name_match.group(1), Path(from_match.group(1))


def source_names() -> dict[Path, str]:
    result: dict[Path, str] = {}
    roots = [INSTALLED_MODEL_DIR, OPERATOR_MODEL_DIR]
    local = Path(__file__).resolve().parents[2] / "models" / "modelfiles"
    if local.is_dir():
        roots.insert(0, local)
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob("*.Modelfile"):
            parsed = parse_modelfile_identity(path)
            if parsed:
                name, source = parsed
                result[source] = name
    local_retired = Path(__file__).resolve().parents[2] / "models" / "retired-models.json"
    retired = load_json(local_retired if local_retired.is_file() else RETIRED_CATALOG)
    if isinstance(retired, dict):
        for item in retired.get("models", []):
            if isinstance(item, dict) and item.get("source") and item.get("name"):
                result[Path(item["source"])] = str(item["name"])
    return result


def source_label(source: Path, state: dict, names: dict[Path, str]) -> str:
    return str(state.get("model_name") or names.get(source) or source.name)


def stat_signature(path: Path) -> dict[str, int]:
    value = path.stat()
    return {
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
        "inode": value.st_ino,
    }


def source_checksum_valid(source: Path, checksum: str, state: dict) -> bool:
    current = stat_signature(source)
    if (
        state.get("schema") in {2, 3}
        and state.get("size") == current["size"]
        and state.get("mtime_ns") == current["mtime_ns"]
        and state.get("ctime_ns") == current["ctime_ns"]
        and SHA256_RE.fullmatch(checksum)
    ):
        return True
    return digest(source) == checksum


def dedupe_key(blob: Path) -> str:
    return f"{blob.parents[1].name}/{blob.name}"


def dedupe_record_matches(source: Path, blob: Path, state: dict) -> bool:
    records = state.get("dedupe")
    if not isinstance(records, dict):
        return False
    record = records.get(dedupe_key(blob))
    return isinstance(record, dict) and record.get("source") == stat_signature(source) and record.get("blob") == stat_signature(blob)


def write_dedupe_record(state_path: Path, source: Path, blob: Path, state: dict) -> None:
    latest = load_json(state_path)
    updated = dict(latest if isinstance(latest, dict) else state)
    records = dict(updated.get("dedupe") or {})
    records[dedupe_key(blob)] = {
        "source": stat_signature(source),
        "blob": stat_signature(blob),
    }
    updated["dedupe"] = records
    original = state_path.stat()
    temporary = state_path.with_name(f".{state_path.name}.tmp")
    temporary.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chown(temporary, original.st_uid, original.st_gid)
    os.chmod(temporary, original.st_mode & 0o777)
    os.replace(temporary, state_path)


def status() -> int:
    free = shutil.disk_usage(GGUF if GGUF.exists() else "/").free
    gguf_bytes = tree_bytes(GGUF)
    ollama_bytes = tree_bytes(OLLAMA)
    inaccessible = gguf_bytes is None or ollama_bytes is None
    print("BC-250 storage")
    print(f"  filesystem free:       {human(free)}")
    if inaccessible:
        print("  GGUF logical bytes:    unavailable (permission denied)")
        print("  Ollama logical bytes:  unavailable (permission denied)")
        print("  verified source/blob pairs: unavailable")
        print("  pending dedupe:        unavailable")
        print("  potential reclaimable: unavailable")
        print("Detailed storage accounting requires elevated privileges.")
        print("Run: sudo bc250-storage status")
        return 1
    pairs = state_pairs()
    live_pairs = [pair for pair in pairs if blob_referenced(pair[1])]
    transient_pairs = [pair for pair in pairs if not blob_referenced(pair[1])]
    pending = [
        pair
        for pair in live_pairs
        if not dedupe_record_matches(pair[0], pair[1], pair[4])
    ]
    print(f"  GGUF logical bytes:    {human(gguf_bytes or 0)}")
    print(f"  Ollama logical bytes:  {human(ollama_bytes or 0)}")
    print(f"  verified live source/blob pairs:{len(live_pairs):7d}")
    print(f"  dedupe state recorded:{len(live_pairs) - len(pending):9d}")
    print(f"  dedupe state unrecorded:{len(pending):7d}")
    print(f"  unrecorded logical data:{human(sum(src.stat().st_size for src, *_ in pending))}")
    print(f"  unreferenced source-hash blobs:{len(transient_pairs):5d}")
    print(f"  unreferenced logical data:{human(sum(src.stat().st_size for src, *_ in transient_pairs))}")
    stale = stale_cu_caches()
    print(f"  stale 40-CU caches:    {len(stale):9d}")
    for path in stale:
        print(f"    {path.name}")
    print("Note: logical byte totals include reflink-shared extents; df reports physical free capacity.")
    if transient_pairs:
        print("Unreferenced source-hash blobs are not dedupe targets; normal Ollama startup pruning can remove them.")
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
    return [unit for unit in SERVICES if subprocess.run(["systemctl", "is-active", "--quiet", unit], check=False).returncode == 0]


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
    try:
        for unit in ("open-webui.service", *SERVICES[:-1]):
            if unit in active:
                subprocess.run(["systemctl", "stop", unit], check=True)
        remaining = active_services()
        if remaining:
            raise RuntimeError(f"services still active after stop: {', '.join(remaining)}")
        return active
    except Exception as exc:
        failed = restore_services(active)
        detail = f"; restoration failed: {', '.join(failed)}" if failed else ""
        raise RuntimeError(f"could not quiesce model services: {exc}{detail}") from exc


def dedupe_pair(alias: Path, blob: Path, size: int) -> int:
    """Deduplicate one source/blob pair with one xfs_io process.

    Keep the field-tested 16 MiB FIDEDUPERANGE size, but batch every range for
    the pair into one xfs_io invocation. This avoids thousands of process
    launches while preserving the conservative range size used on BC-250.
    """
    command = ["xfs_io"]
    ranges = 0
    for offset in range(0, size, DEDUPE_CHUNK_BYTES):
        length = min(DEDUPE_CHUNK_BYTES, size - offset)
        command.extend(
            ["-c", f"dedupe -q {alias} {offset} {offset} {length}"]
        )
        ranges += 1
    command.append(str(blob))
    subprocess.run(command, check=True)
    return ranges


def dedupe(yes: bool) -> int:
    require_root(); xfs_ready()
    all_pairs = state_pairs()
    live_pairs = [pair for pair in all_pairs if blob_referenced(pair[1])]
    pairs = [
        pair
        for pair in live_pairs
        if not dedupe_record_matches(pair[0], pair[1], pair[4])
    ]
    if not pairs:
        if live_pairs:
            print(f"All {len(live_pairs)} verified live source/blob pair(s) are already recorded as deduplicated.")
        else:
            print("No package-managed GGUF/Ollama duplicate pairs found.")
        return 0
    names = source_names()
    print(f"Unrecorded dedupe pairs: {len(pairs)} pair(s), {human(sum(p[0].stat().st_size for p in pairs))} logical data.")
    for index, (source, blob, _checksum, _state_path, state) in enumerate(pairs, 1):
        print(f"  {index:2d}) {source_label(source, state, names)} [{blob.parents[1].name}]")
    if not yes and input("Type DEDUPLICATE to share identical XFS extents: ") != "DEDUPLICATE":
        print("Cancelled."); return 0
    before = shutil.disk_usage(GGUF).free
    active = quiesce_services()
    try:
        with tempfile.TemporaryDirectory(prefix="bc250-dedupe-", dir="/var/tmp") as temp:
            alias = Path(temp, "source")
            for index, (source, blob, checksum, state_path, state) in enumerate(pairs, 1):
                if source.stat().st_size != blob.stat().st_size or not source_checksum_valid(source, checksum, state):
                    raise RuntimeError(f"source/blob state changed for {source_label(source, state, names)}")
                alias.unlink(missing_ok=True); alias.symlink_to(source)
                size = source.stat().st_size
                ranges = (size + DEDUPE_CHUNK_BYTES - 1) // DEDUPE_CHUNK_BYTES
                label = source_label(source, state, names)
                print(
                    f"  [{index}/{len(pairs)}] {label} [{blob.parents[1].name}] "
                    f"{human(size)} in {ranges} batched 16 MiB range(s)...",
                    flush=True,
                )
                dedupe_pair(alias, blob, size)
                write_dedupe_record(state_path, source, blob, state)
                print(f"      recorded dedupe state for {label}")
        os.sync()
    finally:
        failed = restore_services(active)
        if failed:
            raise RuntimeError(f"failed to restore previously active services: {', '.join(failed)}")
    after = shutil.disk_usage(GGUF).free
    print(f"Filesystem capacity recovered: {human(max(0, after - before))}")
    return 0


def prune_sources(yes: bool) -> int:
    require_root()
    candidates: dict[Path, tuple[Path, str, dict]] = {}
    for source, blob, checksum, _state_path, state in state_pairs():
        if Path("mtp") in source.relative_to(GGUF).parents or not blob_referenced(blob):
            continue
        candidates.setdefault(source, (blob, checksum, state))
    names = source_names()
    print(f"Validated registered source candidates: {len(candidates)}")
    total = sum(source.stat().st_size for source in candidates)
    for index, (source, (blob, _checksum, state)) in enumerate(candidates.items(), 1):
        print(f"  {index:2d}) {source_label(source, state, names)} [{blob.parents[1].name}] {human(source.stat().st_size)}")
    print(f"Offline GGUF source data selected: {human(total)}")
    if not yes and input("Type PRUNE-SOURCES to remove these offline GGUF source copies: ") != "PRUNE-SOURCES":
        print("Cancelled."); return 0
    removed = 0
    for source, (blob, checksum, state) in candidates.items():
        if not source_checksum_valid(source, checksum, state) or digest(blob) != checksum:
            print(f"  skip changed/unverified: {source_label(source, state, names)}")
            continue
        removed += source.stat().st_size
        source.unlink()
        source.with_name(source.name + ".bc250.json").unlink(missing_ok=True)
        print(f"  removed {source_label(source, state, names)}: {source}")
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
