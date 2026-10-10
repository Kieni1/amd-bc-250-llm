#!/usr/bin/env python3
"""Reboot-aware, exact-identity GFX1013 LLM A/B benchmark campaign.

This is intentionally a small inference screen, not a model-quality tournament.
It records A1 stock, B GFX1013, and A2 restored-stock control phases using the
same package, kernel, model digests and deterministic synthetic workload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark_common import (
    BenchmarkError,
    OllamaClient,
    TelemetrySampler,
    model_policy_path,
    request_policy_for_model,
)

SCHEMA = "bc250.gfx1013-ab.v1"
REPORT_SCHEMA = "bc250.gfx1013-ab-report.v1"
DEFAULT_ROOT = Path("/var/lib/bc250-llm-server/gfx1013/benchmarks")
DEFAULT_GFX_HELPER = Path("/usr/libexec/bc250-llm-server/gfx1013.sh")
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
PHASES = ("stock", "gfx", "restored")
EXPECTED_GFX_STATE = {"stock": "DISABLED", "gfx": "ENABLED", "restored": "DISABLED"}
ROLE_IDS = {
    "standard": "bc250-office-standard",
    "advanced": "bc250-office-advanced",
    "deep": "bc250-office-deep-reasoning",
}
GPU_FAULT_RE = re.compile(
    r"ring.*timeout|gpu reset|device lost|vm fault|compute ring|amdgpu.*fault|"
    r"amdgpu.*page fault|gpu.*page fault|gpu recovery|amdgpu.*failed to resume|"
    r"amdgpu.*ras.*error",
    re.IGNORECASE,
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stamp_now() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def atomic_json(path: Path, payload: object, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def closed_manifest(directory: Path) -> None:
    rows: list[str] = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise BenchmarkError(f"refusing symlink in benchmark evidence: {path}")
        if not path.is_file() or path.name == "SHA256SUMS":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{digest}  {path.relative_to(directory).as_posix()}")
    target = directory / "SHA256SUMS"
    target.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    os.chmod(target, 0o600)


def verify_closed_manifest(directory: Path) -> None:
    manifest = directory / "SHA256SUMS"
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise BenchmarkError(f"closed evidence manifest is missing: {manifest}") from exc
    recorded: dict[str, str] = {}
    for line in lines:
        if not line:
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise BenchmarkError(f"malformed evidence manifest row: {manifest}")
        digest, relative = match.groups()
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative in recorded:
            raise BenchmarkError(f"unsafe/duplicate evidence manifest path: {relative}")
        recorded[relative] = digest
    actual: set[str] = set()
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise BenchmarkError(f"refusing symlink in benchmark evidence: {path}")
        if path.is_file() and path.name != "SHA256SUMS":
            actual.add(path.relative_to(directory).as_posix())
    if actual != set(recorded):
        missing = sorted(actual - set(recorded))
        extra = sorted(set(recorded) - actual)
        raise BenchmarkError(
            f"evidence manifest is not closed: unlisted={missing or 'none'} missing={extra or 'none'}"
        )
    for relative, expected in recorded.items():
        observed = hashlib.sha256((directory / relative).read_bytes()).hexdigest()
        if observed != expected:
            raise BenchmarkError(f"evidence checksum mismatch: {directory / relative}")


def _sigterm_interrupt(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def run(argv: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BenchmarkError(f"cannot run {' '.join(argv)}: {exc}") from exc


def package_nevra() -> str:
    result = run(
        ["rpm", "-q", "--qf", "%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\\n", "bc250-llm-server"]
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise BenchmarkError("cannot establish installed bc250-llm-server NEVRA")
    return result.stdout.strip().splitlines()[0]


def gfx_status(helper: Path) -> dict[str, Any]:
    result = run([str(helper), "status", "--json"])
    if result.returncode != 0:
        raise BenchmarkError(result.stderr.strip() or "GFX1013 status failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BenchmarkError("GFX1013 status returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise BenchmarkError("GFX1013 status JSON is not an object")
    return payload


def model_roles(include_deep: bool) -> dict[str, dict[str, Any]]:
    try:
        document = json.loads(model_policy_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot read package model policy: {exc}") from exc
    models = document.get("models") if isinstance(document, dict) else None
    if not isinstance(models, list):
        raise BenchmarkError("package model policy has no models list")
    by_id = {item.get("id"): item for item in models if isinstance(item, dict)}
    roles = ["standard", "advanced"] + (["deep"] if include_deep else [])
    resolved: dict[str, dict[str, Any]] = {}
    for role in roles:
        item = by_id.get(ROLE_IDS[role])
        if not isinstance(item, dict) or not item.get("base_model_id"):
            raise BenchmarkError(f"package model policy does not resolve {role} role")
        resolved[role] = {
            "role_id": ROLE_IDS[role],
            "name": str(item.get("name") or ROLE_IDS[role]),
            "model": str(item["base_model_id"]),
        }
    return resolved


def prompt_text() -> str:
    lines = [
        (
            f"Office record {index:03d}: project BC250-{index:04d} has a dated review, "
            f"department owner, CHF {1000 + index * 17} budget line, delivery checkpoint, "
            "risk note, and a requirement to preserve the exact reference identifier."
        )
        for index in range(1, 97)
    ]
    return "\n".join(lines) + "\nSummarize the operational pattern in five concise bullet points."


def memory_psi() -> dict[str, int | float | None]:
    result: dict[str, int | float | None] = {
        "some_avg10": None,
        "full_avg10": None,
        "some_total_us": None,
        "full_total_us": None,
    }
    try:
        lines = Path("/proc/pressure/memory").read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        prefix = parts[0]
        if prefix not in {"some", "full"}:
            continue
        values = dict(item.split("=", 1) for item in parts[1:] if "=" in item)
        try:
            result[f"{prefix}_avg10"] = float(values["avg10"])
        except (KeyError, ValueError):
            pass
        try:
            result[f"{prefix}_total_us"] = int(values["total"])
        except (KeyError, ValueError):
            pass
    return result


def service_restarts() -> int | None:
    result = run(["systemctl", "show", "ollama.service", "-p", "NRestarts", "--value"], timeout=10)
    try:
        return int(result.stdout.strip()) if result.returncode == 0 else None
    except ValueError:
        return None


def gpu_fault_lines(since: str) -> tuple[list[str], str | None]:
    result = run(["journalctl", "-k", "-b", "--since", since, "--no-pager", "-o", "short-iso"], timeout=30)
    if result.returncode != 0:
        return [], result.stderr.strip() or f"journalctl rc={result.returncode}"
    return [line for line in result.stdout.splitlines() if GPU_FAULT_RE.search(line)], None


def num(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def ns_s(value: Any) -> float | None:
    parsed = num(value)
    return parsed / 1e9 if parsed is not None else None


def safe_rate(count: Any, seconds: Any) -> float | None:
    c, s = num(count), num(seconds)
    return c / s if c is not None and s is not None and s > 0 else None


def think_value(model: str, policy: dict[str, Any]) -> bool | str | None:
    if "think" in policy:
        return policy["think"]
    if "gpt-oss" in model.casefold():
        return "medium"
    return None


def build_payload(model: str, prompt: str, num_predict: int) -> dict[str, Any]:
    policy = request_policy_for_model(model)
    options: dict[str, Any] = {"num_predict": num_predict}
    for key in (
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "presence_penalty",
        "repeat_penalty",
    ):
        if key in policy:
            options[key] = policy[key]
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "keep_alive": str(policy.get("keep_alive") or "5m"),
        "options": options,
    }
    think = think_value(model, policy)
    if think is not None:
        payload["think"] = think
    return payload


def run_stream(
    client: OllamaClient,
    model: str,
    prompt: str,
    *,
    num_predict: int,
    telemetry_interval: float,
) -> dict[str, Any]:
    payload = build_payload(model, prompt, num_predict)
    sampler = TelemetrySampler(telemetry_interval).start()
    started = time.monotonic()
    first_content: float | None = None
    first_answer: float | None = None
    final: dict[str, Any] | None = None
    answer_chars = 0
    thinking_chars = 0
    digest = hashlib.sha256()
    try:
        for item in client.ndjson_request("/api/generate", payload):
            now = time.monotonic()
            response = str(item.get("response") or "")
            thinking = str(item.get("thinking") or "")
            if (response or thinking) and first_content is None:
                first_content = now - started
            if response and first_answer is None:
                first_answer = now - started
            if response:
                answer_chars += len(response)
                digest.update(response.encode("utf-8", errors="replace"))
            if thinking:
                thinking_chars += len(thinking)
                digest.update(thinking.encode("utf-8", errors="replace"))
            if item.get("done") is True:
                final = item
    finally:
        wall_s = time.monotonic() - started
        telemetry = sampler.stop()
    if final is None:
        raise BenchmarkError(f"Ollama stream for {model} ended without done=true")
    if answer_chars + thinking_chars == 0:
        raise BenchmarkError(f"Ollama stream for {model} produced no answer or thinking content")
    eval_s = ns_s(final.get("eval_duration"))
    prompt_s = ns_s(final.get("prompt_eval_duration"))
    total_s = ns_s(final.get("total_duration"))
    load_s = ns_s(final.get("load_duration"))
    state = client.runtime_state(model)
    metrics: dict[str, Any] = {
        "wall_s": wall_s,
        "load_s": load_s,
        "total_s": total_s,
        "prompt_eval_count": final.get("prompt_eval_count"),
        "prompt_eval_s": prompt_s,
        "prompt_tps": safe_rate(final.get("prompt_eval_count"), prompt_s),
        "eval_count": final.get("eval_count"),
        "eval_s": eval_s,
        "generation_tps": safe_rate(final.get("eval_count"), eval_s),
        "ttfc_s": first_content,
        "ttfa_s": first_answer,
        "answer_chars": answer_chars,
        "thinking_chars": thinking_chars,
        "output_sha256": digest.hexdigest(),
        "done_reason": str(final.get("done_reason") or "unknown"),
        **state,
        **telemetry,
    }
    return metrics


def median(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [value for row in rows if (value := num(row.get(key))) is not None]
    return statistics.median(values) if values else None


def cv_pct(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [value for row in rows if (value := num(row.get(key))) is not None]
    if len(values) < 2:
        return None
    mean = statistics.fmean(values)
    return statistics.stdev(values) / mean * 100.0 if mean else None


def aggregate_role(cold: dict[str, Any], warm: list[dict[str, Any]]) -> dict[str, Any]:
    all_rows = [cold, *warm]
    values = lambda key: [v for row in all_rows if (v := num(row.get(key))) is not None]
    swap_starts = values("swap_used_start_mib")
    swap_peaks = values("swap_used_max_mib")
    mem_mins = values("mem_available_min_mib")
    return {
        "cold_load_s": num(cold.get("load_s")),
        "cold_ttfc_s": num(cold.get("ttfc_s")),
        "cold_ttfa_s": num(cold.get("ttfa_s")),
        "prompt_tps_median": median(warm, "prompt_tps"),
        "generation_tps_median": median(warm, "generation_tps"),
        "ttfc_s_median": median(warm, "ttfc_s"),
        "ttfa_s_median": median(warm, "ttfa_s"),
        "prompt_tps_cv_pct": cv_pct(warm, "prompt_tps"),
        "generation_tps_cv_pct": cv_pct(warm, "generation_tps"),
        "allocated_context": max(values("allocated_context"), default=None),
        "resident_size_bytes": max(values("resident_size_bytes"), default=None),
        "resident_vram_bytes": max(values("resident_vram_bytes"), default=None),
        "mem_available_min_mib": min(mem_mins) if mem_mins else None,
        "swap_used_start_mib": swap_starts[0] if swap_starts else None,
        "swap_used_max_mib": max(swap_peaks) if swap_peaks else None,
        "swap_peak_delta_mib": (
            max(0.0, max(swap_peaks) - swap_starts[0]) if swap_peaks and swap_starts else None
        ),
        "temp_max_c": max(values("temp_max_c"), default=None),
        "temp_p95_max_case_c": max(values("temp_p95_c"), default=None),
        "gpu_clock_min_mhz": min(values("gpu_clock_min_mhz"), default=None),
        "gpu_clock_max_mhz": max(values("gpu_clock_max_mhz"), default=None),
    }


def phase_identity(status: dict[str, Any]) -> dict[str, Any]:
    upstream = status.get("upstream") if isinstance(status.get("upstream"), dict) else {}
    kernel = status.get("kernel") if isinstance(status.get("kernel"), dict) else {}
    boot = status.get("boot") if isinstance(status.get("boot"), dict) else {}
    return {
        "package_nevra": package_nevra(),
        "kernel": os.uname().release,
        "gfx_state": status.get("state"),
        "gfx_profile": status.get("profile"),
        "gfx_upstream_version": upstream.get("version"),
        "gfx_upstream_commit": upstream.get("commit"),
        "prepared_kernel": kernel.get("prepared"),
        "patched_boot_running": boot.get("patched_running"),
        "private_radv_present": status.get("private_radv_present"),
        "private_icd_present": status.get("private_icd_present"),
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BenchmarkError(f"{path} is not a JSON object")
    return payload


def ensure_campaign_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)


def active_pointer(root: Path) -> Path:
    return root / "active-campaign"


def set_active(root: Path, campaign: Path) -> None:
    pointer = active_pointer(root)
    pointer.write_text(campaign.name + "\n", encoding="utf-8")
    os.chmod(pointer, 0o600)


def resolve_campaign(root: Path, supplied: Path | None, *, create: bool = False) -> Path:
    ensure_campaign_root(root)
    if supplied is not None:
        candidate = supplied.resolve()
        root_resolved = root.resolve()
        if candidate.parent != root_resolved:
            raise BenchmarkError("campaign directory must be a direct child of the benchmark root")
        if create:
            return candidate
        if not candidate.is_dir():
            raise BenchmarkError(f"campaign directory does not exist: {candidate}")
        return candidate
    if create:
        return root / f"campaign-{stamp_now()}"
    pointer = active_pointer(root)
    if not pointer.is_file():
        raise BenchmarkError("no active GFX1013 benchmark campaign; run 'benchmark stock' first")
    name = pointer.read_text(encoding="utf-8").strip()
    candidate = (root / name).resolve()
    root_resolved = root.resolve()
    if candidate.parent != root_resolved or not candidate.is_dir():
        raise BenchmarkError("active GFX1013 benchmark campaign pointer is invalid")
    return candidate


def create_campaign(
    campaign: Path,
    *,
    include_deep: bool,
    repeats: int,
    num_predict: int,
    telemetry_interval: float,
    roles: dict[str, dict[str, Any]],
    client: OllamaClient,
    identity: dict[str, Any],
) -> dict[str, Any]:
    model_rows: dict[str, Any] = {}
    for role, info in roles.items():
        digest = client.digest(info["model"])
        if not digest:
            raise BenchmarkError(f"required {role} model is not registered in Ollama: {info['model']}")
        model_rows[role] = {**info, "digest": digest}
    campaign.mkdir(parents=True, exist_ok=False)
    os.chmod(campaign, 0o700)
    prompt = prompt_text()
    (campaign / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    os.chmod(campaign / "prompt.txt", 0o600)
    payload = {
        "schema": SCHEMA,
        "schema_version": 1,
        "created_at": utc_now(),
        "purpose": "same-package stock vs GFX1013 LLM performance screen",
        "identity": identity,
        "include_deep": include_deep,
        "repeats": repeats,
        "num_predict": num_predict,
        "telemetry_interval_s": telemetry_interval,
        "ollama_url": client.base_url,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "models": model_rows,
        "phases": {phase: "PENDING" for phase in PHASES},
    }
    atomic_json(campaign / "campaign.json", payload)
    return payload


def verify_campaign_identity(campaign: dict[str, Any], identity: dict[str, Any]) -> None:
    baseline = campaign.get("identity") if isinstance(campaign.get("identity"), dict) else {}
    for key in ("package_nevra", "kernel"):
        if baseline.get(key) != identity.get(key):
            raise BenchmarkError(
                f"campaign {key} changed: baseline={baseline.get(key)!r} current={identity.get(key)!r}"
            )


def verify_model_digests(campaign: dict[str, Any], client: OllamaClient) -> None:
    models = campaign.get("models")
    if not isinstance(models, dict):
        raise BenchmarkError("campaign models are missing")
    for role, row in models.items():
        if not isinstance(row, dict):
            raise BenchmarkError(f"campaign role {role} is malformed")
        model = str(row.get("model") or "")
        expected = str(row.get("digest") or "")
        observed = client.digest(model)
        if not expected or observed != expected:
            raise BenchmarkError(
                f"model digest changed for {role}: expected={expected or 'missing'} observed={observed or 'missing'}"
            )


def phase_run(
    args: argparse.Namespace,
    phase: str,
) -> int:
    if os.geteuid() != 0:
        raise BenchmarkError("benchmark phase capture requires root (run with sudo)")
    helper = Path(os.environ.get("BC250_GFX1013_HELPER", DEFAULT_GFX_HELPER))
    status = gfx_status(helper)
    state = str(status.get("state") or "")
    if state != EXPECTED_GFX_STATE[phase]:
        raise BenchmarkError(
            f"phase {phase} requires GFX1013 state {EXPECTED_GFX_STATE[phase]}, "
            f"observed {state or 'unknown'}"
        )
    boot = status.get("boot") if isinstance(status.get("boot"), dict) else {}
    if phase in {"stock", "restored"} and bool(boot.get("patched_running")):
        raise BenchmarkError(
            f"phase {phase} requires a real stock boot, not a still-loaded patched boot"
        )

    service = run(["systemctl", "is-active", "ollama.service"], timeout=10)
    if service.returncode != 0 or service.stdout.strip() != "active":
        raise BenchmarkError("ollama.service must be active for the GFX1013 benchmark")

    root = args.root.resolve()
    client = OllamaClient(args.ollama_url, timeout=args.timeout)
    version = client.version()
    identity = phase_identity(status)
    if phase == "stock":
        campaign_dir = resolve_campaign(root, args.campaign_dir, create=True)
        roles = model_roles(args.include_deep)
        campaign = create_campaign(
            campaign_dir,
            include_deep=args.include_deep,
            repeats=args.repeats,
            num_predict=args.num_predict,
            telemetry_interval=args.telemetry_interval,
            roles=roles,
            client=client,
            identity=identity,
        )
        set_active(root, campaign_dir)
    else:
        campaign_dir = resolve_campaign(root, args.campaign_dir)
        campaign = read_json(campaign_dir / "campaign.json")
        verify_campaign_identity(campaign, identity)
        verify_model_digests(campaign, client)
        expected_deep = bool(campaign.get("include_deep"))
        if args.include_deep != expected_deep and args.include_deep_explicit:
            raise BenchmarkError("--include-deep choice must match the stock phase campaign")

    phase_path = campaign_dir / phase
    if phase_path.exists():
        raise BenchmarkError(f"phase evidence already exists: {phase_path}")
    running = list(campaign_dir.glob(f".{phase}.running-*"))
    if running:
        raise BenchmarkError(
            f"unfinished {phase} capture exists ({running[0].name}); review it before retrying"
        )
    working_path = campaign_dir / f".{phase}.running-{os.getpid()}"
    working_path.mkdir(mode=0o700)

    campaign = read_json(campaign_dir / "campaign.json")
    models = campaign["models"]
    prompt = (campaign_dir / "prompt.txt").read_text(encoding="utf-8").rstrip("\n")
    repeats = int(campaign["repeats"])
    num_predict = int(campaign["num_predict"])
    telemetry_interval = float(campaign["telemetry_interval_s"])

    phase_started = utc_now()
    journal_since = f"@{time.time():.3f}"
    psi_before = memory_psi()
    restarts_before = service_restarts()
    residency = client.snapshot_residency()
    role_results: dict[str, Any] = {}
    residency_restoration = "NOT_ATTEMPTED"
    try:
        try:
            for role, row in models.items():
                model = str(row["model"])
                client.ensure_unloaded(model, timeout=60)
                time.sleep(0.5)
                cold = run_stream(
                    client,
                    model,
                    prompt,
                    num_predict=num_predict,
                    telemetry_interval=telemetry_interval,
                )
                warm: list[dict[str, Any]] = []
                for _ in range(repeats):
                    warm.append(
                        run_stream(
                            client,
                            model,
                            prompt,
                            num_predict=num_predict,
                            telemetry_interval=telemetry_interval,
                        )
                    )
                role_results[role] = {
                    "model": model,
                    "digest": row["digest"],
                    "cold": cold,
                    "warm": warm,
                    "aggregate": aggregate_role(cold, warm),
                }
                client.ensure_unloaded(model, timeout=60)
        finally:
            try:
                client.restore_residency(residency, timeout=60)
                residency_restoration = "PASS"
            except BenchmarkError as exc:
                residency_restoration = f"FAIL: {exc}"

        psi_after = memory_psi()
        restarts_after = service_restarts()
        faults, journal_error = gpu_fault_lines(journal_since)
        (working_path / "gpu-faults.txt").write_text(
            "\n".join(faults) + ("\n" if faults else ""),
            encoding="utf-8",
        )
        os.chmod(working_path / "gpu-faults.txt", 0o600)
        phase_payload = {
            "schema": SCHEMA,
            "schema_version": 1,
            "phase": phase,
            "started_at": phase_started,
            "finished_at": utc_now(),
            "identity": identity,
            "gfx_status": status,
            "ollama_version": version,
            "roles": role_results,
            "memory_psi_before": psi_before,
            "memory_psi_after": psi_after,
            "memory_psi_delta_total_us": {
                key: (
                    int(psi_after[key]) - int(psi_before[key])
                    if isinstance(psi_after.get(key), int)
                    and isinstance(psi_before.get(key), int)
                    else None
                )
                for key in ("some_total_us", "full_total_us")
            },
            "ollama_nrestarts_before": restarts_before,
            "ollama_nrestarts_after": restarts_after,
            "ollama_restart_delta": (
                restarts_after - restarts_before
                if restarts_before is not None and restarts_after is not None
                else None
            ),
            "gpu_fault_count": len(faults),
            "gpu_journal_error": journal_error,
            "residency_restoration": residency_restoration,
        }
        atomic_json(working_path / "phase.json", phase_payload)
        closed_manifest(working_path)
        os.replace(working_path, phase_path)
    except (Exception, KeyboardInterrupt) as exc:
        if working_path.is_dir():
            try:
                atomic_json(
                    working_path / "failure.json",
                    {
                        "schema": SCHEMA,
                        "phase": phase,
                        "started_at": phase_started,
                        "failed_at": utc_now(),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "identity": identity,
                        "gfx_status": status,
                        "residency_restoration": residency_restoration,
                    },
                )
                closed_manifest(working_path)
                failed_path = campaign_dir / f"failed-{phase}-{stamp_now()}-{os.getpid()}"
                os.replace(working_path, failed_path)
            except OSError:
                pass
        campaign["phases"][phase] = "FAILED"
        campaign["updated_at"] = utc_now()
        atomic_json(campaign_dir / "campaign.json", campaign)
        closed_manifest(campaign_dir)
        raise

    campaign["phases"][phase] = "CAPTURED"
    campaign["updated_at"] = utc_now()
    atomic_json(campaign_dir / "campaign.json", campaign)
    closed_manifest(campaign_dir)
    print(f"GFX1013 benchmark phase {phase}: CAPTURED")
    print(f"Campaign: {campaign_dir}")
    for role, result in role_results.items():
        agg = result["aggregate"]
        print(
            f"  {role:8s} prefill={fmt(agg.get('prompt_tps_median'))} tok/s "
            f"decode={fmt(agg.get('generation_tps_median'))} tok/s "
            f"TTFC={fmt(agg.get('ttfc_s_median'))} s"
        )
    if phase == "stock":
        print("Next: prepare/boot/enable GFX1013, then run 'sudo bc250 gfx1013 benchmark gfx'.")
    elif phase == "gfx":
        print("Next: disable GFX1013, reboot stock, then run 'sudo bc250 gfx1013 benchmark restored'.")
    else:
        print("Next: run 'sudo bc250 gfx1013 benchmark report'.")
    return 0


def fmt(value: Any, digits: int = 2) -> str:
    parsed = num(value)
    return "n/a" if parsed is None else f"{parsed:.{digits}f}"


def delta_pct(stock: Any, gfx: Any, *, lower_is_better: bool = False) -> float | None:
    a, b = num(stock), num(gfx)
    if a is None or b is None or a == 0:
        return None
    return ((a - b) / a * 100.0) if lower_is_better else ((b - a) / a * 100.0)


def compare_role(stock: dict[str, Any], gfx: dict[str, Any], restored: dict[str, Any] | None) -> dict[str, Any]:
    a = stock["aggregate"]
    b = gfx["aggregate"]
    a2 = restored["aggregate"] if restored is not None else None
    comparisons = {
        "prompt_tps_gain_pct": delta_pct(a.get("prompt_tps_median"), b.get("prompt_tps_median")),
        "generation_tps_gain_pct": delta_pct(a.get("generation_tps_median"), b.get("generation_tps_median")),
        "ttfc_improvement_pct": delta_pct(a.get("ttfc_s_median"), b.get("ttfc_s_median"), lower_is_better=True),
        "ttfa_improvement_pct": delta_pct(a.get("ttfa_s_median"), b.get("ttfa_s_median"), lower_is_better=True),
        "cold_load_improvement_pct": delta_pct(a.get("cold_load_s"), b.get("cold_load_s"), lower_is_better=True),
        "mem_available_min_delta_mib": (
            num(b.get("mem_available_min_mib")) - num(a.get("mem_available_min_mib"))
            if num(b.get("mem_available_min_mib")) is not None and num(a.get("mem_available_min_mib")) is not None
            else None
        ),
        "swap_peak_delta_change_mib": (
            num(b.get("swap_peak_delta_mib")) - num(a.get("swap_peak_delta_mib"))
            if num(b.get("swap_peak_delta_mib")) is not None and num(a.get("swap_peak_delta_mib")) is not None
            else None
        ),
        "temp_max_delta_c": (
            num(b.get("temp_max_c")) - num(a.get("temp_max_c"))
            if num(b.get("temp_max_c")) is not None and num(a.get("temp_max_c")) is not None
            else None
        ),
    }
    restored_drift = None
    if a2 is not None:
        restored_drift = {
            "prompt_tps_vs_a1_pct": delta_pct(a.get("prompt_tps_median"), a2.get("prompt_tps_median")),
            "generation_tps_vs_a1_pct": delta_pct(a.get("generation_tps_median"), a2.get("generation_tps_median")),
            "ttfc_vs_a1_pct": delta_pct(a.get("ttfc_s_median"), a2.get("ttfc_s_median"), lower_is_better=True),
        }
    return {
        "model": stock["model"],
        "digest": stock["digest"],
        "a1_stock": a,
        "b_gfx": b,
        "a2_restored": a2,
        "delta": comparisons,
        "a2_control_drift": restored_drift,
    }


def recommendation(report: dict[str, Any]) -> dict[str, Any]:
    roles = report.get("roles") if isinstance(report.get("roles"), dict) else {}
    gains: list[float] = []
    blockers: list[str] = []
    if not report.get("a2_restored_present"):
        blockers.append("A2 restored-stock control has not been captured")

    for role, row in roles.items():
        if not isinstance(row, dict):
            blockers.append(f"{role} comparison evidence is malformed")
            continue
        delta = row.get("delta") if isinstance(row.get("delta"), dict) else {}
        p = num(delta.get("prompt_tps_gain_pct"))
        g = num(delta.get("generation_tps_gain_pct"))
        for metric, value in (("prompt", p), ("generation", g)):
            if value is None:
                blockers.append(f"{role} {metric} throughput evidence is missing")
                continue
            gains.append(value)
            if value < -3.0:
                blockers.append(f"{role} {metric} throughput regressed {value:.1f}%")

        a1 = row.get("a1_stock") if isinstance(row.get("a1_stock"), dict) else {}
        b = row.get("b_gfx") if isinstance(row.get("b_gfx"), dict) else {}
        a2 = row.get("a2_restored") if isinstance(row.get("a2_restored"), dict) else None
        for label, aggregate in (("A1", a1), ("B", b)):
            for metric in ("prompt_tps_cv_pct", "generation_tps_cv_pct"):
                value = num(aggregate.get(metric))
                if value is None:
                    blockers.append(f"{role} {label} {metric} evidence is missing")
                elif value > 10.0:
                    blockers.append(f"{role} {label} run spread is high ({metric}={value:.1f}%)")

        mem_min = num(b.get("mem_available_min_mib"))
        if mem_min is None:
            blockers.append(f"{role} GFX MemAvailable evidence is missing")
        elif mem_min < 128.0:
            blockers.append(f"{role} GFX MemAvailable fell below the 128 MiB hard floor")
        swap_gfx = num(b.get("swap_peak_delta_mib"))
        swap_stock = num(a1.get("swap_peak_delta_mib"))
        if swap_gfx is None or swap_stock is None:
            blockers.append(f"{role} swap-growth evidence is missing")
        elif swap_gfx - swap_stock > 128.0:
            blockers.append(
                f"{role} GFX added {swap_gfx - swap_stock:.0f} MiB more peak swap growth than stock"
            )
        temp = num(b.get("temp_max_c"))
        if temp is None:
            blockers.append(f"{role} GFX GPU temperature evidence is missing")
        elif temp >= 85.0:
            blockers.append(f"{role} GFX GPU temperature reached {temp:.1f} C")

        if a2 is not None:
            drift = row.get("a2_control_drift")
            drift = drift if isinstance(drift, dict) else {}
            for metric in ("prompt_tps_vs_a1_pct", "generation_tps_vs_a1_pct"):
                value = num(drift.get(metric))
                if value is None:
                    blockers.append(f"{role} A2 {metric} evidence is missing")
                elif abs(value) > 5.0:
                    blockers.append(
                        f"{role} restored-stock control drifted {value:+.1f}% for {metric}"
                    )

    phase_meta = (
        ("A1 stock", report.get("a1_stock_meta")),
        ("B GFX", report.get("b_gfx_meta")),
        ("A2 restored", report.get("a2_restored_meta")),
    )
    for label, raw in phase_meta:
        if label.startswith("A2") and not report.get("a2_restored_present"):
            continue
        meta = raw if isinstance(raw, dict) else {}
        if meta.get("gpu_journal_error"):
            blockers.append(f"{label} GPU-fault journal evidence is unavailable")
        faults = meta.get("gpu_fault_count")
        if faults is None:
            blockers.append(f"{label} GPU-fault count is missing")
        elif int(faults) > 0:
            blockers.append(f"GPU fault signatures were observed in {label}")
        restarts = meta.get("ollama_restart_delta")
        if restarts is None:
            blockers.append(f"{label} ollama.service restart evidence is missing")
        elif int(restarts) > 0:
            blockers.append(f"ollama.service restarted during {label}")
        if str(meta.get("residency_restoration")) != "PASS":
            blockers.append(f"model residency restoration failed after {label}")

    meaningful = any(value >= 5.0 for value in gains)
    state = "PROMOTION_CANDIDATE" if meaningful and not blockers else "KEEP_OPTIONAL"
    return {
        "state": state,
        "meaningful_gain_threshold_pct": 5.0,
        "throughput_regression_floor_pct": -3.0,
        "repeatability_cv_ceiling_pct": 10.0,
        "a2_control_drift_ceiling_pct": 5.0,
        "hard_memavailable_floor_mib": 128,
        "gpu_temperature_ceiling_c": 85.0,
        "meaningful_performance_signal": meaningful,
        "blockers": blockers,
        "regressions": blockers,
        "note": (
            "This is a bounded performance/safety screen only. Product-quality evidence and "
            "operator review remain required before any future default-on decision."
        ),
    }


def report_campaign(args: argparse.Namespace) -> int:
    campaign_dir = resolve_campaign(args.root.resolve(), args.campaign_dir)
    verify_closed_manifest(campaign_dir)
    campaign = read_json(campaign_dir / "campaign.json")
    stock_path = campaign_dir / "stock/phase.json"
    gfx_path = campaign_dir / "gfx/phase.json"
    if not stock_path.is_file() or not gfx_path.is_file():
        raise BenchmarkError("report requires both stock (A1) and gfx (B) phase evidence")
    stock = read_json(stock_path)
    gfx = read_json(gfx_path)
    restored = (
        read_json(campaign_dir / "restored/phase.json")
        if (campaign_dir / "restored/phase.json").is_file()
        else None
    )
    verify_closed_manifest(campaign_dir / "stock")
    verify_closed_manifest(campaign_dir / "gfx")
    if restored is not None:
        verify_closed_manifest(campaign_dir / "restored")
    phases = campaign.get("phases") if isinstance(campaign.get("phases"), dict) else {}
    if phases.get("stock") != "CAPTURED" or phases.get("gfx") != "CAPTURED":
        raise BenchmarkError("campaign state does not mark both A1 stock and B GFX as CAPTURED")
    if restored is not None and phases.get("restored") != "CAPTURED":
        raise BenchmarkError("A2 phase.json exists but campaign state is not CAPTURED")

    models = campaign.get("models") if isinstance(campaign.get("models"), dict) else {}
    roles: dict[str, Any] = {}
    for role, expected in models.items():
        if not isinstance(expected, dict):
            raise BenchmarkError(f"campaign role identity is malformed: {role}")
        if role not in stock.get("roles", {}) or role not in gfx.get("roles", {}):
            raise BenchmarkError(f"phase evidence missing role {role}")
        stock_role = stock["roles"][role]
        gfx_role = gfx["roles"][role]
        a2_role = restored.get("roles", {}).get(role) if restored else None
        for label, observed in (("A1", stock_role), ("B", gfx_role), ("A2", a2_role)):
            if observed is None and label == "A2" and restored is None:
                continue
            if not isinstance(observed, dict):
                raise BenchmarkError(f"{label} phase evidence is malformed for role {role}")
            if observed.get("model") != expected.get("model") or observed.get("digest") != expected.get("digest"):
                raise BenchmarkError(f"{label} model identity mismatch for role {role}")
        roles[role] = compare_role(stock_role, gfx_role, a2_role)
    meta_keys = (
        "gpu_fault_count",
        "gpu_journal_error",
        "ollama_restart_delta",
        "memory_psi_delta_total_us",
        "residency_restoration",
    )
    payload: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "schema_version": 1,
        "created_at": utc_now(),
        "campaign": str(campaign_dir),
        "identity": campaign.get("identity"),
        "roles": roles,
        "a1_stock_meta": {key: stock.get(key) for key in meta_keys},
        "b_gfx_meta": {key: gfx.get(key) for key in meta_keys},
        "a2_restored_meta": (
            {key: restored.get(key) for key in meta_keys} if restored is not None else None
        ),
        "a2_restored_present": restored is not None,
    }
    payload["recommendation"] = recommendation(payload)
    atomic_json(campaign_dir / "report.json", payload)
    lines = [
        "BC-250 GFX1013 LLM A/B report",
        f"Campaign: {campaign_dir}",
        f"Package: {campaign.get('identity', {}).get('package_nevra', 'unknown')}",
        f"Kernel: {campaign.get('identity', {}).get('kernel', 'unknown')}",
        "",
    ]
    for role, row in roles.items():
        delta = row["delta"]
        lines.extend(
            [
                f"{role.upper()}",
                f"  prompt processing: {fmt(delta.get('prompt_tps_gain_pct'), 1)}%",
                f"  generation:        {fmt(delta.get('generation_tps_gain_pct'), 1)}%",
                f"  TTFC improvement:  {fmt(delta.get('ttfc_improvement_pct'), 1)}%",
                f"  cold-load improve: {fmt(delta.get('cold_load_improvement_pct'), 1)}%",
                f"  MemAvailable delta:{fmt(delta.get('mem_available_min_delta_mib'), 0)} MiB",
                f"  swap-peak change:  {fmt(delta.get('swap_peak_delta_change_mib'), 0)} MiB",
                f"  max-temp change:   {fmt(delta.get('temp_max_delta_c'), 1)} C",
                "",
            ]
        )
    rec = payload["recommendation"]
    lines.append(f"Performance screen: {rec['state']}")
    for item in rec["blockers"]:
        lines.append(f"  - {item}")
    if restored is None:
        lines.append("A2 restored-stock control: NOT CAPTURED (required for promotion-candidate status)")
    else:
        lines.append("A2 restored-stock control: CAPTURED")
    lines.append(rec["note"])
    text = "\n".join(lines) + "\n"
    (campaign_dir / "report.txt").write_text(text, encoding="utf-8")
    os.chmod(campaign_dir / "report.txt", 0o600)
    closed_manifest(campaign_dir)
    print(text, end="")
    return 0


def status_campaign(args: argparse.Namespace) -> int:
    campaign_dir = resolve_campaign(args.root.resolve(), args.campaign_dir)
    campaign = read_json(campaign_dir / "campaign.json")
    payload = {
        "schema": SCHEMA,
        "campaign": str(campaign_dir),
        "identity": campaign.get("identity"),
        "models": campaign.get("models"),
        "phases": campaign.get("phases"),
        "report_present": (campaign_dir / "report.json").is_file(),
    }
    if args.json:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(f"GFX1013 benchmark campaign: {campaign_dir}")
        for phase in PHASES:
            print(f"  {phase:8s}: {payload['phases'].get(phase, 'UNKNOWN')}")
        print(f"  report  : {'present' if payload['report_present'] else 'absent'}")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="bc250 gfx1013 benchmark",
        description="Capture and compare same-package stock/GFX1013 LLM performance phases.",
    )
    result.add_argument("--root", type=Path, default=Path(os.environ.get("BC250_GFX1013_BENCH_ROOT", DEFAULT_ROOT)), help=argparse.SUPPRESS)
    sub = result.add_subparsers(dest="command", required=True)
    for phase in PHASES:
        phase_parser = sub.add_parser(phase, help=f"capture {phase} phase")
        phase_parser.add_argument("--campaign-dir", type=Path, help="explicit campaign directory; later phases default to the active campaign")
        phase_parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
        phase_parser.add_argument("--timeout", type=float, default=900.0)
        phase_parser.add_argument("--repeats", type=int, default=3, help="warm repetitions; stock phase fixes this for the campaign")
        phase_parser.add_argument("--num-predict", type=int, default=192, help="bounded decode tokens; stock phase fixes this for the campaign")
        phase_parser.add_argument("--telemetry-interval", type=float, default=0.5, help="seconds; stock phase fixes this for the campaign")
        phase_parser.add_argument("--include-deep", action="store_true", help="include optional Deep role in addition to Standard + Advanced")
    status = sub.add_parser("status", help="show active campaign phase state")
    status.add_argument("--campaign-dir", type=Path, help="explicit campaign directory; defaults to active")
    status.add_argument("--json", action="store_true")
    report = sub.add_parser("report", help="compare captured A1 stock and B GFX phases; include A2 when available")
    report.add_argument("--campaign-dir", type=Path, help="explicit campaign directory; defaults to active")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    # Track whether --include-deep was explicitly present so later phases can inherit stock configuration.
    args.include_deep_explicit = "--include-deep" in (argv if argv is not None else sys.argv[1:])
    try:
        if args.command in PHASES:
            if args.repeats < 2:
                raise BenchmarkError("--repeats must be at least 2 so run spread can be measured")
            if args.num_predict < 32:
                raise BenchmarkError("--num-predict must be at least 32")
            if args.telemetry_interval < 0.1:
                raise BenchmarkError("--telemetry-interval must be at least 0.1 seconds")
            previous_sigterm = signal.signal(signal.SIGTERM, _sigterm_interrupt)
            try:
                return phase_run(args, args.command)
            finally:
                signal.signal(signal.SIGTERM, previous_sigterm)
        if args.command == "report":
            return report_campaign(args)
        if args.command == "status":
            return status_campaign(args)
    except BenchmarkError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ERROR: benchmark interrupted; partial evidence was sealed where possible.", file=sys.stderr)
        return 130
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
