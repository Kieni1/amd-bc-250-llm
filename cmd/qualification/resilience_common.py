"""Shared helpers for package-gate and resilience qualification tooling."""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

PACKAGE_NAME = "bc250-llm-server"
PACKAGE_GATE_SCHEMA = "bc250.package-gate.v2"
RESILIENCE_PLAN_SCHEMA = "bc250.resilience-plan.v1"
RESILIENCE_STATE_SCHEMA = "bc250.resilience-state.v1"
MANAGED_SWAP = Path("/var/lib/bc250-llm-server/swap/bc250-llm.swap")
DEFAULT_LIBEXEC = Path("/usr/libexec/bc250-llm-server")
QUALIFICATION_CONFIG_PATHS = (
    Path("/etc/cyan-skillfish-governor-smu/config.toml"),
    Path("/etc/bc250-llm-server/mtp-models.toml"),
    Path("/etc/bc250-llm-server/models.d"),
    Path("/etc/systemd/system/ollama.service.d/70-bc250-gfx1013.conf"),
)

RESULT_TO_RC = {
    "PASS": 0,
    "HARNESS": 2,
    "DEFECT": 3,
    "INCOMPLETE": 4,
    "SAFETY": 5,
    "INTERRUPTED": 130,
}
RC_TO_RESULT = {
    0: "PASS",
    2: "HARNESS",
    3: "DEFECT",
    4: "INCOMPLETE",
    5: "SAFETY",
    130: "INTERRUPTED",
}


class QualificationError(RuntimeError):
    """Controlled qualification failure carrying a result taxonomy value."""

    def __init__(self, message: str, result: str = "HARNESS") -> None:
        super().__init__(message)
        self.result = result
        self.rc = RESULT_TO_RC[result]


@dataclasses.dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclasses.dataclass(frozen=True)
class SwapRefreshResult:
    status: str
    detail: str
    priority: int | None = None
    restored: bool = True


@dataclasses.dataclass(frozen=True)
class GateValidation:
    gate: dict[str, object]
    manifest_sha256: str


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: object, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def run_command(
    argv: Sequence[str],
    *,
    input_text: str | None = None,
    timeout: int = 120,
    env: dict[str, str] | None = None,
) -> CommandResult:
    try:
        completed = subprocess.run(
            list(argv),
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except (FileNotFoundError, PermissionError) as exc:
        raise QualificationError(f"cannot execute {argv[0]}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise QualificationError(f"command timed out after {timeout}s: {' '.join(argv)}") from exc
    return CommandResult(tuple(argv), completed.returncode, completed.stdout, completed.stderr)


def package_identity_from_fields(fields: str) -> dict[str, str]:
    parts = fields.strip().split("|")
    if len(parts) != 5 or not all(parts):
        raise QualificationError(f"unexpected RPM identity response: {fields!r}")
    name, epoch, version, release, arch = parts
    return {
        "name": name,
        "epoch": epoch,
        "version": version,
        "release": release,
        "arch": arch,
        "nevra": f"{name}-{epoch}:{version}-{release}.{arch}",
    }


def query_candidate_rpm(path: Path) -> dict[str, str]:
    result = run_command(
        [
            "rpm",
            "-qp",
            "--qf",
            "%{NAME}|%{EPOCHNUM}|%{VERSION}|%{RELEASE}|%{ARCH}\\n",
            str(path),
        ]
    )
    if result.returncode != 0:
        raise QualificationError(f"candidate RPM query failed: {result.stderr.strip() or result.stdout.strip()}")
    identity = package_identity_from_fields(result.stdout)
    if identity["name"] != PACKAGE_NAME:
        raise QualificationError(f"candidate RPM is {identity['name']}, expected {PACKAGE_NAME}", "INCOMPLETE")
    return identity


def query_installed_rpm() -> dict[str, str]:
    result = run_command(
        [
            "rpm",
            "-q",
            "--qf",
            "%{NAME}|%{EPOCHNUM}|%{VERSION}|%{RELEASE}|%{ARCH}\\n",
            PACKAGE_NAME,
        ]
    )
    if result.returncode != 0:
        raise QualificationError(
            f"installed candidate query failed: {result.stderr.strip() or result.stdout.strip()}",
            "INCOMPLETE",
        )
    return package_identity_from_fields(result.stdout)


def write_command_evidence(path: Path, result: CommandResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = [
        f"argv={json.dumps(result.argv)}",
        f"returncode={result.returncode}",
        "--- stdout ---",
        result.stdout.rstrip("\n"),
        "--- stderr ---",
        result.stderr.rstrip("\n"),
        "",
    ]
    path.write_text("\n".join(text), encoding="utf-8")
    os.chmod(path, 0o600)



def _path_tree_identity(path: Path) -> object:
    if not path.exists():
        return {"status": "missing"}
    if path.is_symlink():
        return {"status": "symlink", "target": os.readlink(path)}
    if path.is_file():
        return {"status": "file", "sha256": sha256_path(path)}
    if path.is_dir():
        entries: dict[str, object] = {}
        for child in sorted(path.rglob("*")):
            relative = child.relative_to(path).as_posix()
            if child.is_symlink():
                entries[relative] = {"type": "symlink", "target": os.readlink(child)}
            elif child.is_file():
                entries[relative] = {"type": "file", "sha256": sha256_path(child)}
            elif child.is_dir():
                entries[relative] = {"type": "dir"}
        return {"status": "directory", "entries": entries}
    return {"status": "other"}


def qualification_config_identity(paths: Iterable[Path] = QUALIFICATION_CONFIG_PATHS) -> dict[str, object]:
    return {str(path): _path_tree_identity(path) for path in paths}


def gfx1013_identity(libexec: Path | None = None) -> dict[str, object]:
    libexec = libexec or Path(os.environ.get("BC250_LIBEXEC", DEFAULT_LIBEXEC))
    helper = libexec / "gfx1013.sh"
    if not helper.is_file():
        raise QualificationError(f"GFX1013 status helper is missing: {helper}", "INCOMPLETE")
    result = run_command([str(helper), "status", "--json"], timeout=60)
    if result.returncode != 0:
        raise QualificationError(
            f"GFX1013 status failed: {result.stderr.strip() or result.stdout.strip() or f'rc={result.returncode}'}",
            "INCOMPLETE",
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise QualificationError(f"GFX1013 status returned invalid JSON: {exc}", "INCOMPLETE") from exc
    if not isinstance(payload, dict) or payload.get("schema") != "bc250.gfx1013-status.v1":
        raise QualificationError("GFX1013 status returned an unrecognized schema", "INCOMPLETE")
    package = payload.get("package") if isinstance(payload.get("package"), dict) else {}
    kernel = payload.get("kernel") if isinstance(payload.get("kernel"), dict) else {}
    vulkan = payload.get("vulkan") if isinstance(payload.get("vulkan"), dict) else {}
    return {
        "state": payload.get("state"),
        "profile": payload.get("profile"),
        "upstream": payload.get("upstream"),
        "source_identity_ok": payload.get("source_identity_ok"),
        "prepared_package_nevra": package.get("prepared_nevra"),
        "prepared_kernel": kernel.get("prepared"),
        "enabled_recorded": payload.get("enabled_recorded"),
        "ollama_private_radv_override": payload.get("ollama_private_radv_override"),
        "private_radv_present": payload.get("private_radv_present"),
        "private_icd_present": payload.get("private_icd_present"),
        "vulkan": vulkan,
    }


def qualification_identity(libexec: Path | None = None) -> dict[str, object]:
    libexec = libexec or Path(os.environ.get("BC250_LIBEXEC", DEFAULT_LIBEXEC))
    return {
        "installed_package": query_installed_rpm(),
        "kernel": os.uname().release,
        "configuration": qualification_config_identity(),
        "gfx1013": gfx1013_identity(libexec),
    }


def parse_swapon_output(text: str) -> list[tuple[Path, int]]:
    entries: list[tuple[Path, int]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.rsplit(None, 1)
        if len(parts) != 2:
            raise QualificationError(f"cannot parse swapon entry: {line!r}")
        name, priority_text = parts
        try:
            priority = int(priority_text)
        except ValueError as exc:
            raise QualificationError(f"invalid swap priority in swapon output: {line!r}") from exc
        entries.append((Path(name), priority))
    return entries


def active_swaps() -> list[tuple[Path, int]]:
    result = run_command(["swapon", "--show=NAME,PRIO", "--noheadings", "--raw"])
    if result.returncode != 0:
        raise QualificationError(
            f"cannot inspect active swap: {result.stderr.strip() or result.stdout.strip()}",
            "HARNESS",
        )
    return parse_swapon_output(result.stdout)


def _block_interrupt_signals() -> contextlib.AbstractContextManager[None]:
    @contextlib.contextmanager
    def manager() -> Iterable[None]:
        signals = {signal.SIGINT, signal.SIGTERM}
        old_mask = None
        if hasattr(signal, "pthread_sigmask"):
            old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, signals)
        try:
            yield
        finally:
            if old_mask is not None:
                signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)

    return manager()


def refresh_managed_swap(
    *,
    managed_path: Path = MANAGED_SWAP,
    runner=run_command,
) -> SwapRefreshResult:
    """Refresh only the package-owned disk swap, restoring it in a mandatory finally.

    SIGINT/SIGTERM are blocked for the critical deactivation/restoration window so an
    interrupt can only be delivered after restoration has been attempted.
    """

    with _block_interrupt_signals():
        query = runner(["swapon", "--show=NAME,PRIO", "--noheadings", "--raw"])
        if query.returncode != 0:
            return SwapRefreshResult("HARNESS", "active swap state unavailable", restored=False)
        try:
            entries = parse_swapon_output(query.stdout)
        except QualificationError as exc:
            return SwapRefreshResult("HARNESS", str(exc), restored=False)
        matches = [(path, priority) for path, priority in entries if path == managed_path]
        if not matches:
            return SwapRefreshResult("PASS", "managed disk swap is inactive; refresh not needed")
        if len(matches) != 1:
            return SwapRefreshResult("HARNESS", "managed disk swap appeared more than once", restored=False)
        path, priority = matches[0]
        deactivated = False
        restoration = None
        try:
            off = runner(["swapoff", str(path)])
            if off.returncode != 0:
                detail = off.stderr.strip() or off.stdout.strip() or f"rc={off.returncode}"
                return SwapRefreshResult("HARNESS", f"managed swapoff failed: {detail}", priority, True)
            deactivated = True
            return SwapRefreshResult("PASS", "managed disk swap refreshed", priority, True)
        finally:
            if deactivated:
                restoration = runner(["swapon", "--priority", str(priority), str(path)])
                if restoration.returncode != 0:
                    detail = restoration.stderr.strip() or restoration.stdout.strip() or f"rc={restoration.returncode}"
                    # A return from the try block is superseded by this explicit failure.
                    raise QualificationError(
                        f"managed swap restoration failed after successful swapoff: {detail}",
                        "HARNESS",
                    )


def service_active_state(unit: str) -> str:
    result = run_command(["systemctl", "is-active", unit], timeout=30)
    value = result.stdout.strip()
    if value:
        return value
    if result.returncode == 3:
        return "inactive"
    return f"unknown(rc={result.returncode})"


def restore_normal_topology() -> tuple[bool, dict[str, object]]:
    steps: dict[str, object] = {}
    stop_agent = run_command(["systemctl", "stop", "ollama-agent.service"], timeout=60)
    steps["stop_agent_rc"] = stop_agent.returncode
    start_normal = run_command(
        [
            "systemctl",
            "start",
            "ollama.service",
            "ollama-task.service",
            "ollama-embedding.service",
        ],
        timeout=120,
    )
    steps["start_normal_rc"] = start_normal.returncode
    healthy, observed = normal_topology_status()
    steps["observed"] = observed
    return healthy, steps


def normal_topology_status() -> tuple[bool, dict[str, str]]:
    expected = {
        "ollama.service": "active",
        "ollama-task.service": "active",
        "ollama-embedding.service": "active",
        # Agent is exclusive. In normal topology, inactive is healthy and expected.
        "ollama-agent.service": "inactive",
    }
    observed = {unit: service_active_state(unit) for unit in expected}
    healthy = all(observed[unit] == wanted for unit, wanted in expected.items())
    return healthy, observed


def _manifest_entries(manifest: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", raw)
        if not match:
            raise QualificationError(f"invalid SHA256SUMS line {number}", "INCOMPLETE")
        digest, relative = match.groups()
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or relative == "SHA256SUMS":
            raise QualificationError(f"unsafe SHA256SUMS path: {relative}", "INCOMPLETE")
        if relative in entries:
            raise QualificationError(f"duplicate SHA256SUMS path: {relative}", "INCOMPLETE")
        entries[relative] = digest
    return entries


def validate_closed_manifest(directory: Path) -> str:
    manifest = directory / "SHA256SUMS"
    if not manifest.is_file():
        raise QualificationError("package-gate SHA256SUMS is missing", "INCOMPLETE")
    entries = _manifest_entries(manifest)
    actual_files: set[str] = set()
    for path in directory.rglob("*"):
        if path == manifest:
            continue
        if path.is_symlink():
            raise QualificationError(f"package-gate contains symlink: {path.relative_to(directory)}", "INCOMPLETE")
        if path.is_file():
            actual_files.add(path.relative_to(directory).as_posix())
    if set(entries) != actual_files:
        missing = sorted(actual_files - set(entries))
        extra = sorted(set(entries) - actual_files)
        raise QualificationError(
            f"package-gate manifest is not closed (unlisted={missing}, missing={extra})",
            "INCOMPLETE",
        )
    for relative, expected in entries.items():
        observed = sha256_path(directory / relative)
        if observed != expected:
            raise QualificationError(f"package-gate checksum mismatch: {relative}", "INCOMPLETE")
    return sha256_path(manifest)


def validate_package_gate(directory: Path, *, require_pass: bool = True) -> GateValidation:
    manifest_sha = validate_closed_manifest(directory)
    gate_path = directory / "gate.json"
    try:
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationError(f"cannot read package-gate gate.json: {exc}", "INCOMPLETE") from exc
    if gate.get("schema") != PACKAGE_GATE_SCHEMA:
        raise QualificationError(f"unrecognized package-gate schema: {gate.get('schema')!r}", "INCOMPLETE")
    result = gate.get("result")
    if result not in RESULT_TO_RC:
        raise QualificationError(f"unrecognized package-gate result: {result!r}", "INCOMPLETE")
    if require_pass and result != "PASS":
        raise QualificationError(f"package-gate result is {result}, not PASS", str(result))
    return GateValidation(gate, manifest_sha)


SECRET_PATTERNS = {
    "openai-style-key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "bearer-token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{24,}=*", re.IGNORECASE),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
}


def scan_secrets(paths: Iterable[Path]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise QualificationError(f"cannot secret-scan {path}: {exc}") from exc
        for name, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append(
                    {
                        "file": str(path),
                        "pattern": name,
                        "offset": match.start(),
                    }
                )
    return findings


def source_identity(paths: Iterable[Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in paths:
        result[path.name] = sha256_path(path)
    return result


def rc_result(returncode: int) -> str:
    return RC_TO_RESULT.get(returncode, "HARNESS")
