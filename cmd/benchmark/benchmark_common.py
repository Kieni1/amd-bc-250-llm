#!/usr/bin/env python3
"""Shared helpers for BC-250 benchmarks.

Stdlib-only by design: these helpers are installed with the RPM and must work on
an otherwise minimal Fedora host. API shapes target Ollama 0.33.3.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request

STANDARD_OLLAMA_VERSION = "0.33.3"
DEFAULT_TIMEOUT = 900.0
DEFAULT_TELEMETRY_INTERVAL = 0.5
TEMP_THRESHOLDS = (80.0, 83.0, 85.0)
RESULT_SCHEMA_VERSION = 1
VALID_OUTCOMES = {"pass", "quality-fail", "infra-fail", "skipped"}
VALID_RESULT_TYPES = {"measurement", "qualification"}


PACKAGE_NAME = "bc250-llm-server"
BENCHMARK_METADATA_VERSION = 1


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def package_identity() -> dict[str, str]:
    """Return installed package identity, falling back to the source tree."""
    try:
        result = subprocess.run(
            [
                "rpm",
                "-q",
                "--qf",
                "%{NAME}\t%{VERSION}\t%{RELEASE}\t%{ARCH}",
                PACKAGE_NAME,
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        result = None
    if result is not None and result.returncode == 0:
        parts = result.stdout.strip().split("\t")
        if len(parts) == 4:
            name, version, release, arch = parts
            return {
                "name": name,
                "version": version,
                "release": release,
                "arch": arch,
                "nevra": f"{name}-{version}-{release}.{arch}",
            }

    root = Path(__file__).resolve().parents[2]
    version = "unknown"
    release = "unknown"
    try:
        version = (root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        pass
    try:
        spec = (root / "packaging" / "bc250-llm-server.spec").read_text(encoding="utf-8")
        match = re.search(r"^Release:\s*([^%\s]+)", spec, re.MULTILINE)
        if match:
            release = match.group(1)
    except OSError:
        pass
    return {
        "name": PACKAGE_NAME,
        "version": version,
        "release": release,
        "arch": "source",
        "nevra": f"{PACKAGE_NAME}-{version}-{release}",
    }


def fixture_metadata(*sources: Path) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for source in sources:
        source = Path(source)
        if source.is_file():
            try:
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
            except OSError:
                digest = ""
            items.append({"name": source.name, "sha256": digest})
    return items


def benchmark_metadata(
    category: str,
    *,
    benchmark_version: str,
    models: list[dict[str, Any]] | None = None,
    fixtures: list[dict[str, str]] | None = None,
    options: dict[str, Any] | None = None,
    runtimes: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build the small common metadata envelope for canonical benchmark evidence."""
    data: dict[str, Any] = {
        "metadata_version": BENCHMARK_METADATA_VERSION,
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "category": category,
        "benchmark_version": benchmark_version,
        "started_at": iso_now(),
        "finished_at": None,
        "package": package_identity(),
        "kernel": os.uname().release,
        "models": models or [],
        "fixtures": fixtures or [],
        "options": options or {},
        "runtimes": runtimes or [],
    }
    data.update(extra)
    return data


def write_benchmark_metadata(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def finalize_benchmark_metadata(path: Path) -> None:
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    fixtures_dir = path.parent / "fixtures"
    if fixtures_dir.is_dir():
        fixtures: list[dict[str, str]] = []
        for fixture in sorted(item for item in fixtures_dir.rglob("*") if item.is_file()):
            try:
                digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
            except OSError:
                digest = ""
            fixtures.append(
                {
                    "name": fixture.relative_to(fixtures_dir).as_posix(),
                    "sha256": digest,
                }
            )
        data["fixtures"] = fixtures
    data["finished_at"] = iso_now()
    write_benchmark_metadata(path, data)


@dataclass(frozen=True)
class BenchmarkPaths:
    root: Path
    results_jsonl: Path
    summary_json: Path
    summary_txt: Path
    meta_json: Path
    csv_export: Path
    fixtures_dir: Path


_ACTIVE_BENCHMARK_PATHS: BenchmarkPaths | None = None
_ACTIVE_BENCHMARK_CATEGORY = ""


def prepare_result_dir(category: str, output_dir: str | Path | None = None) -> BenchmarkPaths:
    """Create one isolated result directory for a benchmark invocation."""
    global _ACTIVE_BENCHMARK_PATHS, _ACTIVE_BENCHMARK_CATEGORY
    _ACTIVE_BENCHMARK_PATHS = None
    _ACTIVE_BENCHMARK_CATEGORY = ""
    if output_dir is None:
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
        root = Path("bc250-results") / f"{stamp}-{category}"
    else:
        root = Path(output_dir)
    if root.exists() and any(root.iterdir()):
        raise BenchmarkError(f"result directory is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    fixtures = root / "fixtures"
    fixtures.mkdir(exist_ok=True)
    paths = BenchmarkPaths(
        root=root,
        results_jsonl=root / "results.jsonl",
        summary_json=root / "summary.json",
        summary_txt=root / "summary.txt",
        meta_json=root / "meta.json",
        csv_export=root / "results.csv",
        fixtures_dir=fixtures,
    )
    _ACTIVE_BENCHMARK_PATHS = paths
    _ACTIVE_BENCHMARK_CATEGORY = category
    return paths


def copy_fixtures(paths: BenchmarkPaths, *sources: Path) -> None:
    """Copy deterministic benchmark inputs once beside the canonical case stream."""
    for source in sources:
        source = Path(source)
        target = paths.fixtures_dir / source.name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)


def append_result(path: Path, data: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")


def result_record(
    *,
    category: str,
    model: str,
    case_id: str,
    outcome: str,
    result_type: str,
    failure_kinds: Iterable[str] = (),
    diagnostics: Iterable[str] = (),
    checks: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build the small common case envelope used by benchmark JSONL output."""
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"invalid benchmark outcome: {outcome}")
    if result_type not in VALID_RESULT_TYPES:
        raise ValueError(f"invalid benchmark result type: {result_type}")
    record: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "category": category,
        "model": model,
        "case_id": case_id,
        "outcome": outcome,
        "result_type": result_type,
        "failure_kinds": list(dict.fromkeys(failure_kinds)),
        "diagnostics": list(dict.fromkeys(diagnostics)),
        "checks": checks or {},
        "metrics": metrics or {},
    }
    record.update(extra)
    return record



def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_values(records: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in records:
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            continue
        value = _number(metrics.get(key))
        if value is not None:
            values.append(value)
    return values


def chronological_resource_aggregate(
    records: Iterable[dict[str, Any]], *, nested_metrics: bool = False
) -> dict[str, float | None]:
    """Aggregate sequential resource samples without inventing additive UMA pools.

    Swap start/end are chronological run boundaries: the first observed start and
    last observed end. Peak is the maximum observed peak, and delta is measured
    from the run start to that peak. Per-case temperature p95 values cannot be
    merged into a true run-wide p95, so the aggregate names that statistic
    explicitly as max-case-p95.
    """
    rows = list(records)

    def metric(row: dict[str, Any], key: str) -> float | None:
        source: Any = row.get("metrics") if nested_metrics else row
        if not isinstance(source, dict):
            return None
        return _number(source.get(key))

    def values(key: str) -> list[float]:
        return [value for row in rows if (value := metric(row, key)) is not None]

    starts = values("swap_used_start_mib")
    peaks = values("swap_used_max_mib")
    ends = values("swap_used_end_mib")
    swap_start = starts[0] if starts else None
    swap_peak = max(peaks) if peaks else None
    swap_end = ends[-1] if ends else None
    swap_delta = (
        max(0.0, swap_peak - swap_start)
        if swap_start is not None and swap_peak is not None
        else None
    )
    return {
        "temp_max_c": max(values("temp_max_c"), default=None),
        "temp_p95_max_case_c": max(values("temp_p95_c"), default=None),
        "mem_available_min_mib": min(values("mem_available_min_mib"), default=None),
        "swap_used_start_mib": swap_start,
        "swap_used_max_mib": swap_peak,
        "swap_used_end_mib": swap_end,
        "swap_peak_delta_mib": swap_delta,
        "resident_size_bytes": max(values("resident_size_bytes"), default=None),
        "vram_used_max_bytes": max(values("vram_used_max_bytes"), default=None),
        "gtt_used_max_bytes": max(values("gtt_used_max_bytes"), default=None),
        "gpu_clock_min_mhz": min(values("gpu_clock_min_mhz"), default=None),
        "gpu_clock_max_mhz": max(values("gpu_clock_max_mhz"), default=None),
    }


def category_aggregates(records: list[dict[str, Any]], category: str) -> dict[str, Any]:
    """Return a small category-specific aggregate section for canonical summaries."""
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        by_model.setdefault(str(row.get("model") or "unknown"), []).append(row)
    aggregates: dict[str, Any] = {}

    if category == "generation":
        models: dict[str, Any] = {}
        for model, rows in by_model.items():
            ok = [row for row in rows if row.get("outcome") == "pass"]
            short = [row for row in ok if row.get("test") == "short"]
            short_tps = _metric_values(short, "tokens_per_second")
            cold = [row for row in ok if row.get("test") == "cold_chat"]
            warm = [row for row in ok if row.get("test") == "warm_chat"]
            prefill = [row for row in ok if row.get("test") == "prefill"]
            resource_rows = ok
            resources = chronological_resource_aggregate(
                resource_rows, nested_metrics=True
            )
            mean_decode = statistics.fmean(short_tps) if short_tps else None
            cv = None
            if len(short_tps) >= 2 and mean_decode and mean_decode > 0:
                cv = statistics.stdev(short_tps) / mean_decode * 100.0
            diagnostics: dict[str, int] = {}
            for row in rows:
                for name in row.get("diagnostics", []):
                    diagnostics[str(name)] = diagnostics.get(str(name), 0) + 1
            models[model] = {
                "decode_mean_tps": mean_decode,
                "decode_cv_pct": cv,
                "cold_wall_s": (_metric_values(cold, "wall_duration_s") or [None])[0],
                "warm_answer_latency_s": (
                    statistics.fmean(_metric_values(warm, "time_to_first_answer_s"))
                    if _metric_values(warm, "time_to_first_answer_s") else None
                ),
                "prefill_tps": (
                    statistics.fmean(_metric_values(prefill, "prompt_tokens_per_second"))
                    if _metric_values(prefill, "prompt_tokens_per_second") else None
                ),
                "resident_size_bytes": resources["resident_size_bytes"],
                "mem_available_min_mib": resources["mem_available_min_mib"],
                "swap_start_mib": resources["swap_used_start_mib"],
                "swap_peak_mib": resources["swap_used_max_mib"],
                "swap_end_mib": resources["swap_used_end_mib"],
                "swap_peak_delta_mib": resources["swap_peak_delta_mib"],
                "temp_max_c": resources["temp_max_c"],
                "temp_p95_max_case_c": resources["temp_p95_max_case_c"],
                "diagnostics": dict(sorted(diagnostics.items())),
            }
        aggregates["models"] = models
    elif category == "embeddings":
        models: dict[str, Any] = {}
        summary_keys = (
            "recall_at_1", "recall_at_3", "mrr", "cross_recall_at_1",
            "cross_mrr", "hard_recall_at_1", "mean_target_margin",
            "min_target_margin", "cold_load_s", "warm_input_tps",
            "warm_wall_s", "resident_size_bytes", "allocated_context",
            "mem_available_min_mib", "swap_used_start_mib",
            "swap_used_max_mib", "swap_used_end_mib",
            "swap_peak_delta_mib", "temp_max_c", "temp_p95_c",
        )
        for model, rows in by_model.items():
            aggregate_rows = [row for row in rows if row.get("case_id") == "aggregate"]
            if aggregate_rows:
                metrics = aggregate_rows[-1].get("metrics") or {}
                models[model] = {key: metrics.get(key) for key in summary_keys}
            else:
                quals = [row for row in rows if row.get("case_id") == "qualification"]
                if quals:
                    metrics = quals[-1].get("metrics") or {}
                    models[model] = {key: metrics.get(key) for key in (
                        "recall_at_1", "recall_at_3", "mrr", "hard_recall_at_1"
                    )}
                measurements = [row for row in rows if row.get("result_type") == "measurement"]
                margins = _metric_values(measurements, "target_margin")
                if margins:
                    models.setdefault(model, {})["mean_target_margin"] = statistics.fmean(margins)
                    models[model]["min_target_margin"] = min(margins)
        aggregates["models"] = models
    elif category == "ocr":
        models: dict[str, Any] = {}
        for model, rows in by_model.items():
            models[model] = {}
            for key in ("word_f1", "char_similarity", "field_recall", "field_order_score", "structure_score", "table_signal", "wall_s"):
                values = _metric_values(rows, key)
                if values:
                    models[model][f"mean_{key}"] = statistics.fmean(values)
        aggregates["models"] = models
    elif category in {"task", "translation", "agent", "usecase", "rag-quality"}:
        models: dict[str, Any] = {}
        for model, rows in by_model.items():
            quals = [row for row in rows if row.get("result_type") == "qualification"]
            if not quals:
                continue
            model_failures: dict[str, int] = {}
            model_diagnostics: dict[str, int] = {}
            for row in quals:
                for name in row.get("failure_kinds", []):
                    model_failures[str(name)] = model_failures.get(str(name), 0) + 1
                for name in row.get("diagnostics", []):
                    model_diagnostics[str(name)] = model_diagnostics.get(str(name), 0) + 1
            models[model] = {
                "passed": sum(row.get("outcome") == "pass" for row in quals),
                "quality_failed": sum(row.get("outcome") == "quality-fail" for row in quals),
                "total": len(quals),
                "failure_kinds": dict(sorted(model_failures.items())),
                "diagnostics": dict(sorted(model_diagnostics.items())),
            }
        aggregates["models"] = models
    elif category in {"rag-cycle", "concurrency"}:
        if records:
            latest = records[-1]
            aggregates["checks"] = latest.get("checks", {})
            aggregates["metrics"] = latest.get("metrics", {})
    elif category == "num-batch":
        aggregates["candidates"] = [
            {
                "model": row.get("model"),
                "num_batch": row.get("num_batch"),
                "outcome": row.get("outcome"),
                "prompt_eval_s": (row.get("metrics") or {}).get("prompt_eval_s"),
                "wall_s": (row.get("metrics") or {}).get("wall_s"),
            }
            for row in records
            if row.get("case_id", "").startswith("num-batch-")
        ]
    elif category == "owui-embedding-batch":
        aggregates["candidates"] = [
            {
                "batch": row.get("batch"),
                "outcome": row.get("outcome"),
                "process_wall_s": (row.get("metrics") or {}).get("process_wall_s"),
            }
            for row in records
            if row.get("batch") is not None and "cleanup" not in str(row.get("case_id"))
        ]
    elif category in {"owui-chunk-min", "owui-system-context"}:
        key = "chunk_min_size_target" if category == "owui-chunk-min" else "setting"
        grouped: dict[str, dict[str, int]] = {}
        for row in records:
            value = row.get(key)
            if value is None:
                continue
            bucket = grouped.setdefault(str(value), {"pass": 0, "quality-fail": 0, "infra-fail": 0})
            outcome = str(row.get("outcome"))
            if outcome in bucket:
                bucket[outcome] += 1
        aggregates["candidates"] = grouped
    elif records:
        aggregates["measurement_cases"] = len(
            [row for row in records if row.get("result_type") == "measurement"]
        )
    return aggregates


def _fmt_aggregate(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def aggregate_summary_lines(category: str, aggregates: dict[str, Any]) -> list[str]:
    if not aggregates:
        return []
    lines = ["", "Category aggregates"]
    models = aggregates.get("models")
    if isinstance(models, dict):
        for model, values in models.items():
            lines.append(f"  {model}")
            if isinstance(values, dict):
                for key, value in values.items():
                    if value is not None and value != {}:
                        lines.append(f"    {key:<24} {_fmt_aggregate(value)}")
    else:
        for key, value in aggregates.items():
            if isinstance(value, dict):
                lines.append(f"  {key}")
                for subkey, subvalue in value.items():
                    if subvalue is not None:
                        lines.append(f"    {subkey:<24} {_fmt_aggregate(subvalue)}")
            elif isinstance(value, list):
                lines.append(f"  {key}")
                for item in value:
                    if isinstance(item, dict):
                        rendered = " ".join(
                            f"{name}={_fmt_aggregate(item_value)}"
                            for name, item_value in item.items()
                            if item_value is not None
                        )
                        lines.append(f"    {rendered}")
                    else:
                        lines.append(f"    {_fmt_aggregate(item)}")
            else:
                lines.append(f"  {key:<26} {_fmt_aggregate(value)}")
    return lines


def write_result_summary(jsonl_path: Path, *, category: str) -> tuple[Path, Path]:
    """Write machine/human summaries beside a canonical JSONL case stream."""
    records: list[dict[str, Any]] = []
    if jsonl_path.exists():
        for line_no, line in enumerate(
            jsonl_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BenchmarkError(
                    f"{jsonl_path}:{line_no}: invalid JSONL record: {exc.msg}"
                ) from exc
            if not isinstance(row, dict):
                raise BenchmarkError(
                    f"{jsonl_path}:{line_no}: benchmark record is not an object"
                )
            if row.get("schema_version") != RESULT_SCHEMA_VERSION:
                raise BenchmarkError(
                    f"{jsonl_path}:{line_no}: unsupported result schema version"
                )
            for key in ("category", "model", "case_id"):
                if not isinstance(row.get(key), str) or not row[key]:
                    raise BenchmarkError(
                        f"{jsonl_path}:{line_no}: missing/invalid {key}"
                    )
            if row.get("outcome") not in VALID_OUTCOMES:
                raise BenchmarkError(
                    f"{jsonl_path}:{line_no}: missing/invalid outcome"
                )
            if row.get("result_type") not in VALID_RESULT_TYPES:
                raise BenchmarkError(
                    f"{jsonl_path}:{line_no}: missing/invalid result_type"
                )
            for key in ("failure_kinds", "diagnostics"):
                if not isinstance(row.get(key), list):
                    raise BenchmarkError(
                        f"{jsonl_path}:{line_no}: {key} must be an array"
                    )
            for key in ("checks", "metrics"):
                if not isinstance(row.get(key), dict):
                    raise BenchmarkError(
                        f"{jsonl_path}:{line_no}: {key} must be an object"
                    )
            records.append(row)
    counts = {name: 0 for name in ("pass", "quality-fail", "infra-fail", "skipped")}
    type_counts = {name: 0 for name in ("measurement", "qualification")}
    qualification_counts = {name: 0 for name in ("pass", "quality-fail", "skipped")}
    failures: dict[str, int] = {}
    infra_failures: dict[str, int] = {}
    diagnostics: dict[str, int] = {}
    for row in records:
        outcome = str(row["outcome"])
        result_type = str(row["result_type"])
        counts[outcome] += 1
        type_counts[result_type] += 1
        if result_type == "qualification" and outcome in qualification_counts:
            qualification_counts[outcome] += 1
        if result_type == "qualification" and outcome == "quality-fail":
            for name in row.get("failure_kinds", []):
                failures[str(name)] = failures.get(str(name), 0) + 1
        if outcome == "infra-fail":
            for name in row.get("failure_kinds", []):
                infra_failures[str(name)] = infra_failures.get(str(name), 0) + 1
        for name in row.get("diagnostics", []):
            diagnostics[str(name)] = diagnostics.get(str(name), 0) + 1
    quality = "not-run"
    if qualification_counts["pass"] or qualification_counts["quality-fail"]:
        quality = (
            "mixed"
            if qualification_counts["pass"] and qualification_counts["quality-fail"]
            else ("fail" if qualification_counts["quality-fail"] else "pass")
        )
    infrastructure = "fail" if counts["infra-fail"] else (
        "pass" if records else "not-run"
    )
    aggregates = category_aggregates(records, category)
    summary = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "category": category,
        "cases": len(records),
        "counts": counts,
        "result_types": type_counts,
        "qualification_counts": qualification_counts,
        "infrastructure": infrastructure,
        "quality": quality,
        "failure_kinds": dict(sorted(failures.items())),
        "infrastructure_failure_kinds": dict(sorted(infra_failures.items())),
        "diagnostics": dict(sorted(diagnostics.items())),
        "aggregates": aggregates,
    }
    if jsonl_path.name == "results.jsonl":
        summary_json = jsonl_path.parent / "summary.json"
        summary_txt = jsonl_path.parent / "summary.txt"
    else:
        summary_json = jsonl_path.with_suffix(".summary.json")
        summary_txt = jsonl_path.with_suffix(".summary.txt")
    summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"BC-250 benchmark summary: {category}",
        "",
        f"Cases          {len(records)}",
        f"Infrastructure {infrastructure.upper()}",
        f"Quality        {quality.upper()}",
        f"Pass           {counts['pass']}",
        f"Measurements   {type_counts['measurement']}",
        f"Qualifications {type_counts['qualification']}",
        f"Qual pass      {qualification_counts['pass']}",
        f"Quality-fail   {qualification_counts['quality-fail']}",
        f"Qual skipped   {qualification_counts['skipped']}",
        f"Infra-fail     {counts['infra-fail']}",
    ]
    if failures:
        lines += ["", "Failure kinds"] + [
            f"  {name:<20} {count}" for name, count in sorted(failures.items())
        ]
    if diagnostics:
        lines += ["", "Diagnostics"] + [
            f"  {name:<20} {count}" for name, count in sorted(diagnostics.items())
        ]
    lines += aggregate_summary_lines(category, aggregates)
    summary_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary_json, summary_txt


class BenchmarkError(RuntimeError):
    pass


def finalize_active_infrastructure_failure(
    exc: BaseException,
    *,
    benchmark_version: str = "8.0",
    failure_kind: str = "runtime-api",
) -> bool:
    """Finalize an initialized benchmark directory after an unhandled infra error.

    Benchmark commands are single-invocation processes. ``prepare_result_dir``
    records the current invocation so the outer command handler can preserve
    canonical evidence even when a runtime/API error interrupts category-local
    control flow before its normal summary path. Returns False when no result
    directory had been initialized yet.
    """
    paths = _ACTIVE_BENCHMARK_PATHS
    category = _ACTIVE_BENCHMARK_CATEGORY
    if paths is None or not category:
        return False

    if not paths.meta_json.exists():
        write_benchmark_metadata(
            paths.meta_json,
            benchmark_metadata(
                category,
                benchmark_version=benchmark_version,
                options={"failure_finalized_by": "outer-command-handler"},
            ),
        )

    append_result(
        paths.results_jsonl,
        result_record(
            category=category,
            model="benchmark",
            case_id="benchmark-infrastructure-failure",
            result_type="measurement",
            outcome="infra-fail",
            failure_kinds=[failure_kind],
            error=str(exc),
            error_type=type(exc).__name__,
        ),
    )
    finalize_benchmark_metadata(paths.meta_json)
    write_result_summary(paths.results_jsonl, category=category)
    return True


class OllamaClient:
    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        base_url = base_url.strip()
        if "://" not in base_url:
            base_url = f"http://{base_url}"
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def json_request(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        method: str | None = None,
    ) -> dict[str, Any]:
        data = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(
            self._url(path),
            data=data,
            headers=headers,
            method=method or ("POST" if payload is not None else "GET"),
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise BenchmarkError(
                f"Ollama {path} returned HTTP {exc.code}: {body}"
            ) from exc
        except OSError as exc:
            raise BenchmarkError(
                f"Ollama request failed for {self._url(path)}: {exc}"
            ) from exc
        if not body.strip():
            return {}
        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise BenchmarkError(f"Ollama {path} returned invalid JSON") from exc
        if isinstance(result, dict) and result.get("error"):
            raise BenchmarkError(str(result["error"]))
        if not isinstance(result, dict):
            raise BenchmarkError(f"Ollama {path} returned unexpected JSON type")
        return result

    def ndjson_request(self, path: str, payload: dict[str, Any]):
        """Yield Ollama newline-delimited JSON records from a streaming request."""
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self._url(path),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                for raw in response:
                    if not raw.strip():
                        continue
                    try:
                        item = json.loads(raw.decode("utf-8"))
                    except json.JSONDecodeError as exc:
                        raise BenchmarkError(
                            f"Ollama {path} returned invalid streaming JSON"
                        ) from exc
                    if isinstance(item, dict) and item.get("error"):
                        raise BenchmarkError(str(item["error"]))
                    if not isinstance(item, dict):
                        raise BenchmarkError(
                            f"Ollama {path} returned unexpected streaming JSON type"
                        )
                    yield item
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise BenchmarkError(
                f"Ollama {path} returned HTTP {exc.code}: {body}"
            ) from exc
        except OSError as exc:
            raise BenchmarkError(
                f"Ollama streaming request failed for {self._url(path)}: {exc}"
            ) from exc

    def version(self) -> str:
        return str(self.json_request("/api/version").get("version", "unknown"))

    def tags(self) -> list[dict[str, Any]]:
        return list(self.json_request("/api/tags").get("models", []))

    def show(self, model: str) -> dict[str, Any]:
        return self.json_request("/api/show", {"model": model})

    def ps(self) -> list[dict[str, Any]]:
        return list(self.json_request("/api/ps").get("models", []))

    def stop(self, model: str) -> bool:
        """Request model unload, falling back to the Ollama 0.33.3 HTTP path."""
        env = os.environ.copy()
        env["OLLAMA_HOST"] = self.base_url
        try:
            result = subprocess.run(
                ["ollama", "stop", model],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                timeout=30,
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        # Ollama documents an empty /api/generate request with keep_alive=0 as
        # the HTTP unload path. This remains valid in 0.33.3.
        try:
            self.json_request(
                "/api/generate", {"model": model, "keep_alive": 0, "stream": False}
            )
            return True
        except BenchmarkError:
            # Embedding-only or multimodal registrations can reject generation.
            # The caller decides whether a failed unload is fatal for its lane.
            return False

    def model_loaded(self, model: str) -> bool:
        """Return whether /api/ps currently reports this exact model."""
        normalized = model.removesuffix(":latest")
        return any(
            str(row.get("name") or row.get("model") or "").removesuffix(":latest")
            == normalized
            for row in self.ps()
        )

    def wait_unloaded(self, model: str, timeout: float = 30.0) -> bool:
        """Return True only after /api/ps confirms that the model is absent."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if not self.model_loaded(model):
                    return True
            except BenchmarkError:
                return False
            time.sleep(0.25)
        return False

    def ensure_unloaded(self, model: str, timeout: float = 30.0) -> None:
        """Require a confirmed unload; return immediately when already absent."""
        try:
            if not self.model_loaded(model):
                return
        except BenchmarkError as exc:
            raise BenchmarkError(
                f"cannot verify model residency before unload: {model}"
            ) from exc
        if not self.stop(model):
            raise BenchmarkError(f"could not request unload for {model}")
        if not self.wait_unloaded(model, timeout):
            raise BenchmarkError(f"model remained loaded after {timeout:.0f}s: {model}")

    def digest(self, model: str) -> str:
        normalized = model.removesuffix(":latest")
        for row in self.tags():
            name = str(row.get("name") or row.get("model") or "").removesuffix(
                ":latest"
            )
            if name == normalized:
                return str(row.get("digest") or "")
        return ""

    def runtime_state(self, model: str) -> dict[str, Any]:
        normalized = model.removesuffix(":latest")
        try:
            rows = self.ps()
        except BenchmarkError:
            rows = []
        for row in rows:
            name = str(row.get("name") or row.get("model") or "").removesuffix(
                ":latest"
            )
            if name == normalized:
                return {
                    "resident_size_bytes": row.get("size"),
                    "resident_vram_bytes": row.get("size_vram"),
                    "allocated_context": row.get("context_length"),
                }
        return {
            "resident_size_bytes": None,
            "resident_vram_bytes": None,
            "allocated_context": None,
        }


def read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def read_meminfo() -> tuple[float | None, float | None]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, rest = line.split(":", 1)
            match = re.search(r"(\d+)", rest)
            if match:
                values[key] = int(match.group(1))
    except OSError:
        return None, None
    available = values.get("MemAvailable")
    total = values.get("SwapTotal")
    free = values.get("SwapFree")
    available_mib = available / 1024 if available is not None else None
    swap_used_mib = (
        (total - free) / 1024 if total is not None and free is not None else None
    )
    return available_mib, swap_used_mib


def discover_amdgpu_device(drm_root: Path = Path("/sys/class/drm")) -> Path | None:
    """Return the BC-250/AMDGPU DRM device used for benchmark telemetry.

    BC-250 appliances normally expose one AMD DRM card. Prefer the boot VGA
    device if multiple AMD cards exist. BC250_DRM_CARD=cardN can override the
    automatic choice without changing benchmark output schemas.
    """
    forced = os.environ.get("BC250_DRM_CARD", "").strip()
    candidates: list[Path] = []
    if forced:
        card = drm_root / forced
        if (card / "device").exists():
            candidates.append(card / "device")
    else:
        for card in sorted(drm_root.glob("card[0-9]*")):
            device = card / "device"
            if not device.exists():
                continue
            try:
                vendor = (
                    (device / "vendor").read_text(encoding="utf-8").strip().casefold()
                )
            except OSError:
                continue
            if vendor == "0x1002":
                candidates.append(device)
    if not candidates:
        return None
    candidates.sort(
        key=lambda device: (read_int(device / "boot_vga") != 1, device.parent.name)
    )
    return candidates[0]


def amdgpu_edge_temperature(device: Path | None) -> tuple[str, float | None]:
    if device is None:
        return "", None
    hwmons = sorted((device / "hwmon").glob("hwmon*"))
    for hwmon in hwmons:
        try:
            name = (hwmon / "name").read_text(encoding="utf-8").strip().casefold()
        except OSError:
            name = ""
        if name and name != "amdgpu":
            continue
        inputs = sorted(hwmon.glob("temp*_input"))
        if not inputs:
            continue
        chosen: Path | None = None
        label = ""
        for input_path in inputs:
            label_path = input_path.with_name(
                input_path.name.replace("_input", "_label")
            )
            try:
                current_label = label_path.read_text(encoding="utf-8").strip()
            except OSError:
                current_label = ""
            if current_label.casefold() == "edge":
                chosen, label = input_path, current_label
                break
        if chosen is None:
            # AMDGPU temp1 is the on-die GPU temperature. On cards that expose
            # labels this is normally "edge"; older ASICs may omit the label.
            temp1 = hwmon / "temp1_input"
            chosen = temp1 if temp1.exists() else inputs[0]
            label_path = chosen.with_name(chosen.name.replace("_input", "_label"))
            try:
                label = label_path.read_text(encoding="utf-8").strip()
            except OSError:
                label = "edge" if chosen.name == "temp1_input" else chosen.stem
        raw = read_int(chosen)
        if raw is None:
            continue
        value = raw / 1000.0 if abs(raw) > 1000 else float(raw)
        return f"{device.parent.name}/amdgpu/{label or chosen.stem}", value
    return "", None


def current_gpu_clock_mhz(device: Path | None) -> float | None:
    if device is None:
        return None
    try:
        text = (device / "pp_dpm_sclk").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if "*" not in line:
            continue
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(MHz|Mhz|mhz)", line)
        if match:
            return float(match.group(1))
    return None


def device_sysfs_int(device: Path | None, name: str) -> int | None:
    return read_int(device / name) if device is not None else None


@dataclass
class TelemetrySample:
    timestamp: float
    temp_c: float | None
    temp_label: str
    gpu_busy_pct: float | None
    gpu_clock_mhz: float | None
    vram_used_bytes: int | None
    gtt_used_bytes: int | None
    mem_available_mib: float | None
    swap_used_mib: float | None


class TelemetrySampler:
    def __init__(self, interval: float = DEFAULT_TELEMETRY_INTERVAL) -> None:
        self.interval = max(interval, 0.1)
        self.samples: list[TelemetrySample] = []
        self.gpu_device = discover_amdgpu_device()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> TelemetrySample:
        temp_label, temp_c = amdgpu_edge_temperature(self.gpu_device)
        busy_raw = device_sysfs_int(self.gpu_device, "gpu_busy_percent")
        mem_available, swap_used = read_meminfo()
        return TelemetrySample(
            timestamp=time.monotonic(),
            temp_c=temp_c,
            temp_label=temp_label,
            gpu_busy_pct=float(busy_raw) if busy_raw is not None else None,
            gpu_clock_mhz=current_gpu_clock_mhz(self.gpu_device),
            vram_used_bytes=device_sysfs_int(self.gpu_device, "mem_info_vram_used"),
            gtt_used_bytes=device_sysfs_int(self.gpu_device, "mem_info_gtt_used"),
            mem_available_mib=mem_available,
            swap_used_mib=swap_used,
        )

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self.samples.append(self._sample())

    def start(self) -> TelemetrySampler:
        self.samples.append(self._sample())
        self._thread = threading.Thread(
            target=self._loop, name="bc250-telemetry", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval * 3 + 1)
        self.samples.append(self._sample())
        return self.summary()

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            return empty_telemetry()
        temps = [sample.temp_c for sample in self.samples if sample.temp_c is not None]
        busy = [
            sample.gpu_busy_pct
            for sample in self.samples
            if sample.gpu_busy_pct is not None
        ]
        clocks = [
            sample.gpu_clock_mhz
            for sample in self.samples
            if sample.gpu_clock_mhz is not None
        ]
        vrams = [
            sample.vram_used_bytes
            for sample in self.samples
            if sample.vram_used_bytes is not None
        ]
        gtts = [
            sample.gtt_used_bytes
            for sample in self.samples
            if sample.gtt_used_bytes is not None
        ]
        mems = [
            sample.mem_available_mib
            for sample in self.samples
            if sample.mem_available_mib is not None
        ]
        swaps = [
            sample.swap_used_mib
            for sample in self.samples
            if sample.swap_used_mib is not None
        ]

        threshold_seconds = {threshold: 0.0 for threshold in TEMP_THRESHOLDS}
        for previous, current in zip(self.samples, self.samples[1:]):
            delta = max(0.0, current.timestamp - previous.timestamp)
            if previous.temp_c is None:
                continue
            for threshold in TEMP_THRESHOLDS:
                if previous.temp_c >= threshold:
                    threshold_seconds[threshold] += delta

        peak_label = ""
        if temps:
            peak_sample = max(
                (sample for sample in self.samples if sample.temp_c is not None),
                key=lambda sample: float(sample.temp_c),
            )
            peak_label = peak_sample.temp_label

        return {
            "telemetry_samples": len(self.samples),
            "telemetry_duration_s": max(
                0.0, self.samples[-1].timestamp - self.samples[0].timestamp
            ),
            "temp_max_c": max(temps) if temps else None,
            "temp_p95_c": percentile(temps, 95) if temps else None,
            "seconds_ge_80c": threshold_seconds[80.0],
            "seconds_ge_83c": threshold_seconds[83.0],
            "seconds_ge_85c": threshold_seconds[85.0],
            "temp_peak_label": peak_label,
            "gpu_busy_max_pct": max(busy) if busy else None,
            "gpu_clock_min_mhz": min(clocks) if clocks else None,
            "gpu_clock_max_mhz": max(clocks) if clocks else None,
            "vram_used_max_bytes": max(vrams) if vrams else None,
            "gtt_used_max_bytes": max(gtts) if gtts else None,
            "mem_available_min_mib": min(mems) if mems else None,
            "swap_used_start_mib": swaps[0] if swaps else None,
            "swap_used_max_mib": max(swaps) if swaps else None,
            "swap_used_end_mib": swaps[-1] if swaps else None,
            "swap_peak_delta_mib": (max(swaps) - swaps[0]) if swaps else None,
        }


def empty_telemetry() -> dict[str, Any]:
    return {
        "telemetry_samples": 0,
        "telemetry_duration_s": 0.0,
        "temp_max_c": None,
        "temp_p95_c": None,
        "seconds_ge_80c": 0.0,
        "seconds_ge_83c": 0.0,
        "seconds_ge_85c": 0.0,
        "temp_peak_label": "",
        "gpu_busy_max_pct": None,
        "gpu_clock_min_mhz": None,
        "gpu_clock_max_mhz": None,
        "vram_used_max_bytes": None,
        "gtt_used_max_bytes": None,
        "mem_available_min_mib": None,
        "swap_used_start_mib": None,
        "swap_used_max_mib": None,
        "swap_used_end_mib": None,
        "swap_peak_delta_mib": None,
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def normalize_words(text: str) -> list[str]:
    return re.findall(r"[\wÀ-ÖØ-öø-ÿ'-]+", text.casefold(), flags=re.UNICODE)


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise BenchmarkError(
            f"embedding dimension mismatch: {len(left)} != {len(right)}"
        )
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def mean(values: Iterable[float]) -> float:
    data = list(values)
    return statistics.fmean(data) if data else 0.0
