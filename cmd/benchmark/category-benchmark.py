#!/usr/bin/env python3
"""Category-specific BC-250 benchmarks for retrieval, OCR, tasks, agents, and acceptance."""

from __future__ import annotations

import argparse
import ast
import base64
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from benchmark_common import (
    STANDARD_OLLAMA_VERSION,
    BenchmarkError,
    OllamaClient,
    TelemetrySampler,
    append_result,
    benchmark_metadata,
    copy_fixtures,
    cosine,
    finalize_active_infrastructure_failure,
    finalize_benchmark_metadata,
    fixture_metadata,
    mean,
    normalize_words,
    prepare_result_dir,
    result_record,
    write_benchmark_metadata,
    write_result_summary,
)

SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_FIXTURES = SCRIPT_DIR.parent.parent / "examples" / "benchmark"
INSTALLED_FIXTURES = (
    Path(os.environ.get("BC250_SHARE", "/usr/share/bc250-llm-server")) / "benchmark"
)
FIXTURE_ROOT = (
    Path(os.environ.get("BC250_BENCH_FIXTURES", ""))
    if os.environ.get("BC250_BENCH_FIXTURES")
    else (INSTALLED_FIXTURES if INSTALLED_FIXTURES.exists() else SOURCE_FIXTURES)
)
TELEMETRY_INTERVAL = float(os.environ.get("TELEMETRY_INTERVAL", "0.5"))
KEEP_ALIVE = os.environ.get("KEEP_ALIVE", "30m")
INSTALLED_OWUI_DESIRED_STATE = (
    Path(os.environ.get("BC250_SHARE", "/usr/share/bc250-llm-server"))
    / "openwebui"
    / "desired-state.json"
)
SOURCE_OWUI_DESIRED_STATE = SCRIPT_DIR.parent.parent / "config" / "openwebui" / "desired-state.json"


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def ns_to_s(value: Any) -> float:
    return safe_float(value) / 1_000_000_000.0


def process_seconds(response: dict[str, Any]) -> float:
    return max(
        0.0,
        ns_to_s(response.get("total_duration"))
        - ns_to_s(response.get("load_duration")),
    )


def choose_models(client: OllamaClient, explicit: list[str], prefix: str) -> list[str]:
    if explicit:
        return explicit
    names = [str(row.get("name") or row.get("model") or "") for row in client.tags()]
    return [name for name in names if name.removesuffix(":latest").startswith(prefix)]


def model_meta(client: OllamaClient, model: str) -> dict[str, Any]:
    try:
        show = client.show(model)
    except BenchmarkError:
        show = {}
    details = show.get("details") if isinstance(show.get("details"), dict) else {}
    return {
        "model": model,
        "digest": client.digest(model),
        "family": details.get("family", ""),
        "parameter_size": details.get("parameter_size", ""),
        "quantization_level": details.get("quantization_level", ""),
        "runtime_url": client.base_url,
    }


def write_meta(
    path: Path,
    client: OllamaClient,
    category: str,
    models: list[str],
    fixture: Path,
    *,
    options: dict[str, Any] | None = None,
) -> None:
    version = client.version()
    effective_options: dict[str, Any] = {
        "telemetry_interval_s": TELEMETRY_INTERVAL,
        "request_timeout_s": client.timeout,
        "keep_alive": KEEP_ALIVE,
    }
    effective_options.update(options or {})
    data = benchmark_metadata(
        category,
        benchmark_version="8.0",
        models=[model_meta(client, model) for model in models],
        fixtures=fixture_metadata(fixture),
        options=effective_options,
        runtimes=[
            {
                "kind": "ollama",
                "url": client.base_url,
                "version": version,
                "package_standard_version": STANDARD_OLLAMA_VERSION,
            }
        ],
    )
    write_benchmark_metadata(path, data)
    if version != STANDARD_OLLAMA_VERSION:
        print(
            f"WARNING: Ollama {version} differs from package standard {STANDARD_OLLAMA_VERSION}",
            file=sys.stderr,
        )



def print_result_paths(paths: Any, summary_txt: Path) -> None:
    finalize_benchmark_metadata(paths.meta_json)
    print(
        f"Result directory: {paths.root}\nCanonical: {paths.results_jsonl}\n"
        f"Summary: {summary_txt}\nCSV export: {paths.csv_export}"
    )

def embedding_scheme(model: str) -> tuple[str, str, str]:
    lower = model.lower()
    forced_query = os.environ.get("EMBED_QUERY_PREFIX")
    forced_doc = os.environ.get("EMBED_CONTENT_PREFIX")
    if forced_query is not None or forced_doc is not None:
        return forced_query or "", forced_doc or "", "environment"
    if "jina" in lower:
        return "Query: ", "Document: ", "jina-v5"
    if "qwen3" in lower and "embed" in lower:
        return (
            "Instruct: Retrieve relevant passages from German, French, and English office documents that answer the query.\nQuery: ",
            "",
            "qwen3-embedding",
        )
    return "", "", "none"


def embedding_qualification_checks(
    metrics: dict[str, Any], policy: dict[str, Any]
) -> dict[str, bool]:
    return {
        "recall_at_3": metrics["recall_at_3"] >= float(policy["min_recall_at_3"]),
        "mrr": metrics["mrr"] >= float(policy["min_mrr"]),
        "hard_recall_at_1": metrics["hard_recall_at_1"]
        >= float(policy["min_hard_recall_at_1"]),
    }


def embed(
    client: OllamaClient, model: str, inputs: list[str], keep_alive: Any = KEEP_ALIVE
) -> dict[str, Any]:
    return client.json_request(
        "/api/embed",
        {"model": model, "input": inputs, "truncate": False, "keep_alive": keep_alive},
    )


def benchmark_embeddings(args: argparse.Namespace) -> int:
    client = OllamaClient(args.ollama_url, args.timeout)
    fixture = Path(args.fixture or FIXTURE_ROOT / "embedding-office.json")
    corpus = json.loads(fixture.read_text(encoding="utf-8"))
    documents = corpus["documents"]
    queries = corpus["queries"]
    models = choose_models(client, args.models, "embed-")
    if not models:
        raise BenchmarkError("no embedding models found")

    paths = prepare_result_dir("embeddings", args.output_dir)
    csv_path, jsonl_path, meta_path = paths.csv_export, paths.results_jsonl, paths.meta_json
    copy_fixtures(paths, fixture)
    write_meta(
        meta_path, client, "embeddings", models, fixture,
        options={
            "repeats": args.repeats,
            "query_prefix_override": os.environ.get("EMBED_QUERY_PREFIX"),
            "content_prefix_override": os.environ.get("EMBED_CONTENT_PREFIX"),
        },
    )
    fields = [
        "timestamp", "model", "prefix_scheme", "recall_at_1", "recall_at_3",
        "mrr", "cross_recall_at_1", "cross_mrr", "hard_recall_at_1",
        "mean_target_margin", "min_target_margin", "documents", "queries",
        "dimensions", "cold_load_s", "quality_wall_s", "warm_input_tps",
        "warm_wall_s", "resident_size_bytes", "resident_vram_bytes",
        "allocated_context", "temp_max_c", "temp_p95_c", "seconds_ge_80c",
        "seconds_ge_83c", "seconds_ge_85c", "gpu_busy_max_pct",
        "gpu_clock_min_mhz", "gpu_clock_max_mhz", "vram_used_max_bytes",
        "gtt_used_max_bytes", "mem_available_min_mib", "swap_used_start_mib",
        "swap_used_max_mib", "swap_used_end_mib", "swap_peak_delta_mib",
    ]
    quality_failed = False
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for model in models:
            print(f"\n=== embedding: {model} ===")
            client.ensure_unloaded(model)
            try:
                query_prefix, doc_prefix, scheme = embedding_scheme(model)
                doc_inputs = [doc_prefix + item["text"] for item in documents]
                query_inputs = [query_prefix + item["text"] for item in queries]
                sampler = TelemetrySampler(TELEMETRY_INTERVAL).start()
                try:
                    quality_start = time.monotonic()
                    doc_response = embed(client, model, doc_inputs)
                    cold_load_s = ns_to_s(doc_response.get("load_duration"))
                    query_response = embed(client, model, query_inputs)
                    doc_vectors = doc_response.get("embeddings", [])
                    query_vectors = query_response.get("embeddings", [])
                    quality_wall_s = time.monotonic() - quality_start
                    if len(doc_vectors) != len(documents) or len(query_vectors) != len(queries):
                        raise BenchmarkError(f"{model}: embedding count does not match fixture")
                    ranks: list[int] = []
                    cross_ranks: list[int] = []
                    hard_ranks: list[int] = []
                    margins: list[float] = []
                    for query_item, vector in zip(queries, query_vectors):
                        scored = sorted(
                            (
                                (cosine(vector, doc_vector), doc["id"])
                                for doc, doc_vector in zip(documents, doc_vectors)
                            ),
                            reverse=True,
                        )
                        ranked_ids = [doc_id for _score, doc_id in scored]
                        rank = ranked_ids.index(query_item["target"]) + 1
                        ranks.append(rank)
                        if query_item.get("kind") == "cross": cross_ranks.append(rank)
                        if query_item.get("hard"): hard_ranks.append(rank)
                        target_score = next(score for score, doc_id in scored if doc_id == query_item["target"])
                        competitor = max(score for score, doc_id in scored if doc_id != query_item["target"])
                        margin = target_score - competitor
                        margins.append(margin)
                        append_result(jsonl_path, result_record(
                            category="embeddings", model=model, case_id=query_item["id"],
                            outcome="pass", result_type="measurement",
                            metrics={
                                "rank": rank,
                                "target_margin": margin,
                                "target_in_top3": rank <= 3,
                            },
                            timestamp=iso_now(), target=query_item["target"], rank=rank,
                            top3=scored[:3], prefix_scheme=scheme, hard=bool(query_item.get("hard")),
                        ))
                    warm_tps: list[float] = []
                    warm_walls: list[float] = []
                    for repeat in range(args.repeats):
                        start_time = time.monotonic()
                        response = embed(client, model, doc_inputs)
                        wall = time.monotonic() - start_time
                        seconds = process_seconds(response)
                        count = int(response.get("prompt_eval_count") or 0)
                        warm_tps.append(count / seconds if seconds > 0 else 0.0)
                        warm_walls.append(wall)
                        print(f"  warm {repeat + 1}/{args.repeats}: {warm_tps[-1]:.1f} input tok/s, {wall:.3f}s")
                finally:
                    telemetry = sampler.stop()
                state = client.runtime_state(model)
                row = {
                    "timestamp": iso_now(), "model": model, "prefix_scheme": scheme,
                    "recall_at_1": mean(1.0 if rank <= 1 else 0.0 for rank in ranks),
                    "recall_at_3": mean(1.0 if rank <= 3 else 0.0 for rank in ranks),
                    "mrr": mean(1.0 / rank for rank in ranks),
                    "cross_recall_at_1": mean(1.0 if rank <= 1 else 0.0 for rank in cross_ranks),
                    "cross_mrr": mean(1.0 / rank for rank in cross_ranks),
                    "hard_recall_at_1": mean(1.0 if rank <= 1 else 0.0 for rank in hard_ranks),
                    "mean_target_margin": mean(margins),
                    "min_target_margin": min(margins) if margins else 0.0,
                    "documents": len(documents), "queries": len(queries),
                    "dimensions": len(doc_vectors[0]) if doc_vectors else 0,
                    "cold_load_s": cold_load_s, "quality_wall_s": quality_wall_s,
                    "warm_input_tps": mean(warm_tps), "warm_wall_s": mean(warm_walls),
                    **state, **{key: telemetry.get(key) for key in fields if key in telemetry},
                }
                aggregate_metric_keys = (
                    "recall_at_1", "recall_at_3", "mrr",
                    "cross_recall_at_1", "cross_mrr", "hard_recall_at_1",
                    "mean_target_margin", "min_target_margin", "documents",
                    "queries", "dimensions", "cold_load_s", "quality_wall_s",
                    "warm_input_tps", "warm_wall_s", "resident_size_bytes",
                    "resident_vram_bytes", "allocated_context", "temp_max_c",
                    "temp_p95_c", "mem_available_min_mib", "swap_used_start_mib",
                    "swap_used_max_mib", "swap_used_end_mib",
                    "swap_peak_delta_mib",
                )
                append_result(
                    jsonl_path,
                    result_record(
                        category="embeddings",
                        model=model,
                        case_id="aggregate",
                        outcome="pass",
                        result_type="measurement",
                        metrics={key: row.get(key) for key in aggregate_metric_keys},
                        prefix_scheme=scheme,
                        timestamp=row["timestamp"],
                    ),
                )
                qualification = corpus.get("qualification")
                if isinstance(qualification, dict):
                    policy_model = str(qualification.get("model") or "").removesuffix(":latest")
                    if model.removesuffix(":latest") == policy_model:
                        checks = embedding_qualification_checks(row, qualification)
                        qualified = all(checks.values())
                        quality_failed = quality_failed or not qualified
                        append_result(
                            jsonl_path,
                            result_record(
                                category="embeddings",
                                model=model,
                                case_id="qualification",
                                outcome="pass" if qualified else "quality-fail",
                                result_type="qualification",
                                failure_kinds=[] if qualified else ["retrieval"],
                                checks=checks,
                                metrics={
                                    "recall_at_1": row["recall_at_1"],
                                    "recall_at_3": row["recall_at_3"],
                                    "mrr": row["mrr"],
                                    "hard_recall_at_1": row["hard_recall_at_1"],
                                },
                                qualification_policy=qualification,
                                timestamp=iso_now(),
                            ),
                        )
                writer.writerow(row); handle.flush()
                print(
                    f"  quality: R@1={row['recall_at_1']:.3f} "
                    f"R@3={row['recall_at_3']:.3f} MRR={row['mrr']:.3f} "
                    f"hard-R@1={row['hard_recall_at_1']:.3f}"
                )
                print(
                    f"  separation: mean-margin={row['mean_target_margin']:.3f} "
                    f"min-margin={row['min_target_margin']:.3f}"
                )
                print(
                    f"  resources: Tmax={fmt(telemetry.get('temp_max_c'), 'C')} "
                    f"MemAvailable-min={fmt(telemetry.get('mem_available_min_mib'), 'MiB')}"
                )
            finally:
                try: client.ensure_unloaded(model)
                except BenchmarkError as exc: print(f"WARNING: {exc}", file=sys.stderr)
    _sj, summary_txt = write_result_summary(jsonl_path, category="embeddings")
    print_result_paths(paths, summary_txt)
    return 3 if quality_failed else 0


# Task generation is package policy, not an upstream-default approximation.
# The exact prompt templates live in the package-owned Open WebUI desired state and
# are consumed by both Open WebUI and this direct benchmark. This prevents a model
# from qualifying against one prompt contract and then regressing on the live route.
TASK_NUM_PREDICT = {
    # Open WebUI v0.11.3 falls back to max_tokens=1000 for title generation
    # when TASK_MODEL_PARAMS is empty. The other packaged task paths inherit
    # the model's 128-token generation limit.
    "title": 1000,
    "tags": 128,
    "query": 128,
}

TASK_PROMPT_KEYS = {
    "title": ("TITLE_GENERATION_PROMPT_TEMPLATE", 2),
    "tags": ("TAGS_GENERATION_PROMPT_TEMPLATE", 6),
    "query": ("QUERY_GENERATION_PROMPT_TEMPLATE", 6),
}


def task_prompt_state_path() -> Path:
    return (
        INSTALLED_OWUI_DESIRED_STATE
        if INSTALLED_OWUI_DESIRED_STATE.is_file()
        else SOURCE_OWUI_DESIRED_STATE
    )


def task_prompt_templates() -> dict[str, str]:
    path = task_prompt_state_path()
    try:
        desired = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot read task prompt policy {path}: {exc}") from exc
    task = desired.get("task") if isinstance(desired, dict) else None
    if not isinstance(task, dict):
        raise BenchmarkError(f"invalid task prompt policy in {path}")
    templates: dict[str, str] = {}
    for task_type, (key, _limit) in TASK_PROMPT_KEYS.items():
        value = task.get(key)
        if not isinstance(value, str) or not value.strip():
            raise BenchmarkError(f"task prompt policy {path} is missing {key}")
        templates[task_type] = value
    return templates


def task_prompt(
    case: dict[str, Any], templates: dict[str, str] | None = None
) -> str:
    messages = case.get("messages") or [
        {"role": "user", "content": case.get("input", "")}
    ]
    task_type = str(case.get("type") or "")
    if task_type not in TASK_PROMPT_KEYS:
        raise BenchmarkError(f"unsupported task type: {task_type!r}")
    _key, limit = TASK_PROMPT_KEYS[task_type]
    history = "\n".join(
        f"{str(message.get('role', 'user')).upper()}: {message.get('content', '')!s}"
        for message in messages[-limit:]
    )
    prompt_templates = templates if templates is not None else task_prompt_templates()
    template = prompt_templates[task_type]
    rendered = template.replace(f"{{{{MESSAGES:END:{limit}}}}}", history)
    rendered = rendered.replace(
        "{{CURRENT_DATE}}", datetime.now().astimezone().date().isoformat()
    )
    if "{{MESSAGES:" in rendered or "{{CURRENT_DATE}}" in rendered:
        raise BenchmarkError(
            f"unexpanded placeholder in package task prompt for {task_type}"
        )
    return rendered


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Parse the JSON object the way Open WebUI does for task responses."""
    stripped = text.strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        value = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def strict_json_object(text: str) -> bool:
    try:
        return isinstance(json.loads(text.strip()), dict)
    except json.JSONDecodeError:
        return False


LANGUAGE_MARKERS = {
    "de": {"und", "der", "die", "das", "für", "mit", "suche", "dokument", "vertrag", "datenschutz", "kündigung", "zahlung", "analyse", "bitte", "rechnung", "monate", "frist", "nicht", "zulässig", "unterlagen", "referenz"},
    "fr": {"le", "la", "les", "de", "des", "du", "et", "pour", "avec", "traduction", "règlement", "frais", "voyage", "justificatifs", "veuillez", "facture", "mois", "résiliation", "référence", "documents", "ne", "pas"},
    "en": {"the", "and", "of", "for", "with", "translation", "task", "document", "privacy", "analysis", "review", "management", "extraction"},
}


def task_language_hint(text: str, expected: str) -> str:
    words = set(normalize_words(text))
    scores = {
        language: len(words & markers) for language, markers in LANGUAGE_MARKERS.items()
    }
    best = max(scores.values(), default=0)
    if best == 0:
        return "unknown"
    winners = {language for language, score in scores.items() if score == best}
    if winners == {expected}:
        return "match"
    if expected not in winners:
        return "other"
    return "unknown"


def task_language_decision(
    text: str, expected: str, *, required: bool, semantic_ok: bool
) -> tuple[str, bool]:
    """Return language evidence without penalizing language-neutral technical tags."""
    hint = task_language_hint(text, expected)
    passed = (
        (not required)
        or hint == "match"
        or (hint == "unknown" and semantic_ok)
    )
    return hint, passed


def keyword_score(text: str, keywords: list[str]) -> float:
    words = set(normalize_words(text))
    hits = 0
    for keyword in keywords:
        key = keyword.casefold()
        if key in text.casefold() or any(
            word.startswith(key[: max(4, len(key) - 2)]) for word in words
        ):
            hits += 1
    return hits / len(keywords) if keywords else 1.0


def task_value_text(parsed: dict[str, Any] | None, task_type: str) -> str:
    if parsed is None:
        return ""
    if task_type == "title":
        value = parsed.get("title")
        return value if isinstance(value, str) else ""
    key = "tags" if task_type == "tags" else "queries"
    value = parsed.get(key)
    if not isinstance(value, list):
        return ""
    return " ".join(item for item in value if isinstance(item, str))


def semantic_groups_score(text: str, groups: list[list[str]]) -> tuple[int, int]:
    folded = acceptance_text(text)
    matched = sum(
        1
        for group in groups
        if any(acceptance_text(term) in folded for term in group)
    )
    return matched, len(groups)


def task_request_options(case: dict[str, Any]) -> dict[str, Any]:
    """Return the explicit Open WebUI-compatible task request budget."""
    return {"num_predict": TASK_NUM_PREDICT.get(str(case.get("type")), 128)}


def benchmark_task(args: argparse.Namespace) -> int:
    client = OllamaClient(args.ollama_url, args.timeout)
    fixture = Path(args.fixture or FIXTURE_ROOT / "task-cases.json")
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    models = choose_models(client, args.models, "task-")
    if not models:
        raise BenchmarkError("no task models found")
    paths = prepare_result_dir("task", args.output_dir)
    csv_path, jsonl_path, meta_path = paths.csv_export, paths.results_jsonl, paths.meta_json
    prompt_policy = task_prompt_state_path()
    prompt_templates = task_prompt_templates()
    copy_fixtures(paths, fixture, prompt_policy)
    write_meta(
        meta_path,
        client,
        "task",
        models,
        fixture,
        options={
            # Task requests explicitly unload after every response. Record the
            # actual request contract instead of the benchmark-wide 30m default.
            "keep_alive": 0,
            "num_predict_by_task": TASK_NUM_PREDICT,
            "prompt_policy": str(prompt_policy),
            "prompt_templates_sha256": hashlib.sha256(
                json.dumps(
                    prompt_templates,
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest(),
        },
    )

    fields = [
        "timestamp", "model", "case_id", "task", "language", "passed",
        "valid_json", "strict_json", "structure_ok", "language_hint",
        "language_required", "language_pass", "semantic_groups",
        "semantic_required", "semantic_ok", "keyword_score", "wall_s",
        "load_s", "eval_count", "done_reason", "temp_max_c",
        "mem_available_min_mib", "swap_used_max_mib",
    ]
    total = passed = 0
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for model in models:
            print(f"\n=== task: {model} ===")
            scores: list[float] = []
            for case in cases:
                prompt = task_prompt(case, prompt_templates)
                options = task_request_options(case)
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "keep_alive": 0,
                    "options": options,
                }
                sampler = TelemetrySampler(TELEMETRY_INTERVAL).start()
                start_time = time.monotonic()
                try:
                    response = client.json_request("/api/chat", payload)
                except BenchmarkError:
                    client.stop(model)
                    client.wait_unloaded(model)
                    raise
                finally:
                    wall = time.monotonic() - start_time
                    telemetry = sampler.stop()
                message = response.get("message") if isinstance(response.get("message"), dict) else {}
                content = str(message.get("content") or "")
                thinking = str(message.get("thinking") or response.get("thinking") or "")
                parsed = parse_json_object(content)
                valid_json = parsed is not None
                strict_json = strict_json_object(content)
                value_text = task_value_text(parsed, case["type"])
                structure_ok = False
                if parsed is not None:
                    if case["type"] == "title":
                        title = parsed.get("title")
                        structure_ok = isinstance(title, str) and 1 <= len(title.split()) <= 8
                    elif case["type"] == "tags":
                        tags = parsed.get("tags")
                        structure_ok = (
                            isinstance(tags, list)
                            and 1 <= len(tags) <= 6
                            and all(isinstance(x, str) for x in tags)
                        )
                    else:
                        queries = parsed.get("queries")
                        structure_ok = (
                            isinstance(queries, list)
                            and 1 <= len(queries) <= 3
                            and all(isinstance(x, str) for x in queries)
                        )
                groups = case.get("semantic_groups", [])
                semantic_groups, _ = semantic_groups_score(value_text, groups)
                semantic_required = int(case.get("min_semantic_groups", 0))
                semantic_ok = semantic_groups >= semantic_required
                language_required = bool(
                    case.get("language_required", case["type"] in {"title", "query"})
                )
                # Language-neutral product names, identifiers, and unavoidable technical
                # terms may be indeterminate; relevant indeterminate output is accepted,
                # but clear other-language output is not.
                language_hint, language_pass = task_language_decision(
                    value_text,
                    case["language"],
                    required=language_required,
                    semantic_ok=semantic_ok,
                )
                score = keyword_score(value_text, case.get("keywords", []))
                ok = structure_ok and language_pass and semantic_ok
                total += 1
                passed += int(ok)
                scores.append(score if structure_ok else 0.0)
                done_reason = str(response.get("done_reason") or "")
                failures: list[str] = []
                if not content.strip():
                    failures.append("empty-output")
                elif not valid_json or not structure_ok:
                    failures.append("format-contract")
                if not language_pass:
                    failures.append("language")
                if not semantic_ok:
                    failures.append("relevance")
                diagnostics: list[str] = []
                if done_reason == "length":
                    diagnostics.append("output-budget")
                    if not content.strip() and thinking.strip():
                        diagnostics.append("thinking-budget")
                row = {
                    "timestamp": iso_now(), "model": model, "case_id": case["id"],
                    "task": case["type"], "language": case["language"],
                    "passed": int(ok), "valid_json": int(valid_json),
                    "strict_json": int(strict_json), "structure_ok": int(structure_ok),
                    "language_hint": language_hint, "language_required": int(language_required),
                    "language_pass": int(language_pass), "semantic_groups": semantic_groups,
                    "semantic_required": semantic_required, "semantic_ok": int(semantic_ok),
                    "keyword_score": f"{score:.3f}", "wall_s": f"{wall:.3f}",
                    "load_s": f"{ns_to_s(response.get('load_duration')):.3f}",
                    "eval_count": response.get("eval_count", 0), "done_reason": done_reason,
                    "temp_max_c": telemetry.get("temp_max_c"),
                    "mem_available_min_mib": telemetry.get("mem_available_min_mib"),
                    "swap_used_max_mib": telemetry.get("swap_used_max_mib"),
                }
                writer.writerow(row)
                append_result(jsonl_path, result_record(
                    category="task", model=model, case_id=case["id"],
                    result_type="qualification", outcome="pass" if ok else "quality-fail", failure_kinds=failures,
                    diagnostics=diagnostics,
                    checks={"structure": structure_ok, "language": language_pass, "relevance": semantic_ok},
                    metrics={"keyword_score": score, "semantic_groups": semantic_groups, "wall_s": wall, "load_s": ns_to_s(response.get("load_duration")), "eval_count": response.get("eval_count", 0)},
                    timestamp=iso_now(), case=case, response=content, thinking=thinking,
                    valid_json=valid_json, strict_json=strict_json, language_hint=language_hint,
                    telemetry=telemetry, request_options=options, keep_alive=0,
                    done_reason=done_reason,
                ))
                print(
                    f"  {case['id']}: structure={structure_ok} "
                    f"lang={language_hint}/{language_pass} "
                    f"semantic={semantic_groups}/{semantic_required} "
                    f"pass={ok} wall={wall:.2f}s"
                )
            print(f"  mean keyword diagnostic: {mean(scores):.3f}")
    _summary_json, summary_txt = write_result_summary(jsonl_path, category="task")
    print(f"\nTask acceptance: {passed}/{total} passed")
    print_result_paths(paths, summary_txt)
    return 0 if passed == total else 3

def clean_code_output(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    match = re.fullmatch(r"```[^\n]*\n(.*?)\n```", text, flags=re.DOTALL)
    return (match.group(1) if match else text).strip()


def _executable_ast_nodes(scope: ast.AST) -> list[ast.AST]:
    """Walk one executable scope without treating nested definitions as evidence."""
    nodes: list[ast.AST] = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if node is scope:
                for statement in node.body:
                    self.visit(statement)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            if node is scope:
                for statement in node.body:
                    self.visit(statement)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

        def visit_Lambda(self, node: ast.Lambda) -> None:
            return

        def generic_visit(self, node: ast.AST) -> None:
            nodes.append(node)
            super().generic_visit(node)

    visitor = Visitor()
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        visitor.visit(scope)
    else:
        for statement in getattr(scope, "body", []):
            visitor.visit(statement)
    return nodes


def _raise_name(node: ast.Raise) -> str | None:
    if node.exc is None:
        return None
    exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
    return exc.id if isinstance(exc, ast.Name) else None


def _body_raises(statements: list[ast.stmt], exception: str) -> bool:
    module = ast.Module(body=statements, type_ignores=[])
    return any(
        isinstance(node, ast.Raise) and _raise_name(node) == exception
        for node in _executable_ast_nodes(module)
    )


def _out_of_range_bounds(test: ast.AST, bounds: list[int]) -> set[int]:
    """Return configured bounds used by a simple out-of-range condition."""
    if not bounds:
        return set()
    lower, upper = min(bounds), max(bounds)
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        constants = {
            part.value
            for part in ast.walk(test.operand)
            if isinstance(part, ast.Constant)
            and isinstance(part.value, int)
            and not isinstance(part.value, bool)
        }
        if lower in constants and upper in constants:
            return {lower, upper}

    guarded: set[int] = set()
    for comparison in ast.walk(test):
        if not isinstance(comparison, ast.Compare) or len(comparison.ops) != 1:
            continue
        left, right = comparison.left, comparison.comparators[0]
        operator = comparison.ops[0]
        if isinstance(right, ast.Constant) and right.value == lower and isinstance(operator, ast.Lt):
            guarded.add(lower)
        if isinstance(left, ast.Constant) and left.value == lower and isinstance(operator, ast.Gt):
            guarded.add(lower)
        if isinstance(right, ast.Constant) and right.value == upper and isinstance(operator, ast.Gt):
            guarded.add(upper)
        if isinstance(left, ast.Constant) and left.value == upper and isinstance(operator, ast.Lt):
            guarded.add(upper)
    return guarded


def _python_has_range_raise(
    nodes: list[ast.AST], *, bounds: list[int], exception: str
) -> bool:
    """Require each configured out-of-range boundary to lead to the exception."""
    guarded: set[int] = set()
    for node in nodes:
        if isinstance(node, ast.If) and _body_raises(node.body, exception):
            guarded.update(_out_of_range_bounds(node.test, bounds))
    return all(value in guarded for value in bounds)


def _python_has_dedup(nodes: list[ast.AST]) -> bool:
    """Recognize common duplicate-removal idioms without executing code."""
    for node in nodes:
        if isinstance(node, (ast.SetComp, ast.DictComp)):
            return True
        if isinstance(node, ast.Compare) and any(
            isinstance(operator, ast.NotIn) for operator in node.ops
        ):
            return True
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "set":
                return True
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "fromkeys"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "dict"
            ):
                return True
    return False


def _stripped_name(node: ast.AST) -> str | None:
    """Return the source name for ``name`` or ``name.strip()`` expressions."""
    if isinstance(node, ast.Name):
        return node.id
    if (
        isinstance(node, ast.Call)
        and not node.args
        and not node.keywords
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "strip"
        and isinstance(node.func.value, ast.Name)
    ):
        return node.func.value.id
    return None


def _blank_test_names(test: ast.AST) -> set[str]:
    """Return names explicitly tested as blank by a simple condition."""
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        name = _stripped_name(test.operand)
        return {name} if name else set()
    if isinstance(test, ast.Compare) and len(test.ops) == len(test.comparators) == 1:
        if not isinstance(test.ops[0], ast.Eq):
            return set()
        left, right = test.left, test.comparators[0]
        if isinstance(right, ast.Constant) and right.value == "":
            name = _stripped_name(left)
            return {name} if name else set()
        if isinstance(left, ast.Constant) and left.value == "":
            name = _stripped_name(right)
            return {name} if name else set()
    return set()


def _python_has_blank_skip(function: ast.AST) -> bool:
    """Recognize split-loop guards that skip empty or whitespace-only items."""
    for loop in ast.walk(function):
        if not isinstance(loop, (ast.For, ast.AsyncFor)) or not isinstance(loop.target, ast.Name):
            continue
        if not (
            isinstance(loop.iter, ast.Call)
            and isinstance(loop.iter.func, ast.Attribute)
            and loop.iter.func.attr == "split"
        ):
            continue
        source_names = {loop.target.id}
        stripped_aliases: set[str] = set()
        for statement in loop.body:
            if (
                isinstance(statement, (ast.Assign, ast.AnnAssign))
                and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Attribute)
                and statement.value.func.attr == "strip"
                and isinstance(statement.value.func.value, ast.Name)
                and statement.value.func.value.id in source_names
            ):
                targets = (
                    statement.targets
                    if isinstance(statement, ast.Assign)
                    else [statement.target]
                )
                stripped_aliases.update(
                    target.id for target in targets if isinstance(target, ast.Name)
                )
            if not isinstance(statement, ast.If):
                continue
            blank_names = _blank_test_names(statement.test)
            accepted_names = source_names | stripped_aliases
            if blank_names & accepted_names and any(
                isinstance(node, ast.Continue) for node in statement.body
            ):
                # A bare source-name check (``if not item``) does not ignore
                # whitespace-only fields. Require strip() either in the test or
                # through an alias assigned from the split item.
                test_uses_strip = any(
                    isinstance(node, ast.Attribute) and node.attr == "strip"
                    for node in ast.walk(statement.test)
                )
                if test_uses_strip or bool(blank_names & stripped_aliases):
                    return True
    return False


def _python_contract(body: str, case: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return problems
    required_function = case.get("python_function")
    function = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == required_function
        ),
        None,
    )
    if required_function and function is None:
        return [f"missing function: {required_function}"]

    scope: ast.AST = function if function is not None else tree
    nodes = _executable_ast_nodes(scope)
    calls: set[str] = set()
    raises: set[str] = set()
    comparison_constants: set[int] = set()
    for node in nodes:
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                calls.add(func.id)
            elif isinstance(func, ast.Attribute):
                calls.add(func.attr)
        if isinstance(node, ast.Raise):
            name = _raise_name(node)
            if name:
                raises.add(name)
        if isinstance(node, ast.Compare):
            for part in (node.left, *node.comparators):
                if (
                    isinstance(part, ast.Constant)
                    and isinstance(part.value, int)
                    and not isinstance(part.value, bool)
                ):
                    comparison_constants.add(part.value)
    for name in case.get("python_calls", []):
        if name not in calls:
            problems.append(f"missing call: {name}")
    for name in case.get("python_raises", []):
        if name not in raises:
            problems.append(f"missing raise: {name}")
    for value in case.get("python_compare_constants", []):
        if int(value) not in comparison_constants:
            problems.append(f"missing comparison boundary: {value}")
    range_guard = case.get("python_range_guard")
    if isinstance(range_guard, dict):
        bounds = [int(value) for value in range_guard.get("bounds", [])]
        exception = str(range_guard.get("exception") or "ValueError")
        if bounds and not _python_has_range_raise(nodes, bounds=bounds, exception=exception):
            problems.append(
                "missing associated range guard: "
                + ", ".join(str(value) for value in bounds)
                + f" -> {exception}"
            )
    if case.get("python_require_dedup") and not _python_has_dedup(nodes):
        problems.append("missing duplicate removal")
    if case.get("python_require_blank_skip") and not _python_has_blank_skip(scope):
        problems.append("missing blank-item skip")
    return problems


def _bash_missing_arg_guard(body: str) -> bool:
    """Recognize branch-local missing-argument guards used by this fixture."""
    for match in re.finditer(
        r"\bif\s+(?P<condition>[\s\S]*?)\bthen\b(?P<branch>[\s\S]*?)\bfi\b",
        body,
    ):
        condition = match.group("condition")
        branch = match.group("branch")
        missing = bool(
            re.search(r"\$#.{0,50}-(?:ne\s+1|eq\s+0|lt\s+1)\b", condition)
            or re.search(r'-z\s+[\'"]?(?:\$1|\$\{1(?::-[^}]*)?\})', condition)
        )
        if missing and re.search(r"\bexit\s+2\b", branch):
            return True
    for match in re.finditer(
        r"\bcase\s+[^\n]*\$#[^\n]*\bin\b(?P<body>[\s\S]*?)\besac\b",
        body,
    ):
        if re.search(
            r"(?:^|[;\n]\s*)0\s*\)[\s\S]*?\bexit\s+2\b",
            match.group("body"),
        ):
            return True
    return False


def _bash_glob_no_match_safe(body: str) -> bool:
    if re.search(r"\bshopt\s+-s\s+[^\n]*\bnullglob\b", body):
        return True
    return bool(
        re.search(
            r"""(?:\[\[?|test)\s+-(?:e|f)\s+['"]?\$[A-Za-z_][A-Za-z0-9_]*['"]?"""
            r"[^\n]*(?:\|\|\s*continue|&&\s*(?:basename|printf|echo))",
            body,
        )
    )


def _bash_contract(body: str, case: dict[str, Any]) -> list[str]:
    if case.get("bash_contract") != "modelfile-list":
        return []
    problems: list[str] = []
    if not _bash_missing_arg_guard(body):
        problems.append("missing guarded argument check with exit 2")

    quoted_glob = re.search(
        r'"\$(?:\{[^}]+\}|[A-Za-z_][A-Za-z0-9_]*|1)"/\*\.Modelfile',
        body,
    )
    find_direct = (
        re.search(r'\bfind\s+"[^"\n]*\$[^"\n]*"', body)
        and re.search(r"(?:^|\s)-maxdepth\s+1\b", body)
        and re.search(r"""(?:^|\s)-name\s+['"]\*\.Modelfile['"]""", body)
    )
    if not (quoted_glob or find_direct):
        problems.append("missing space-safe direct-directory Modelfile selection")
    elif quoted_glob and not _bash_glob_no_match_safe(body):
        problems.append("glob is not safe when no Modelfile matches")

    # Accept only explicit basename-producing forms. A bare ``basename`` token
    # is insufficient: it must occur in command position so constructs such as
    # ``echo basename "$f"`` cannot satisfy the contract. The sed/awk forms are
    # deliberately narrow and must actually strip/select the final path field.
    basename_command = re.search(
        r"(?:^|[;{}\n]|&&|\|\||\||\(|\))\s*"
        r"(?:(?:then|do|else|elif|if|while|until)\s+)?"
        r"(?:command\s+)?basename(?=\s|$)",
        body,
        re.MULTILINE,
    )
    sed_basename = re.search(
        r"\bsed(?:\s+-[A-Za-z]+)*\s+['\"]s(?P<delim>[^A-Za-z0-9\s\\])\.\*/(?P=delim)(?P=delim)['\"]",
        body,
    )
    awk_basename = re.search(
        r"\bawk\s+-F\s*['\"]?/['\"]?\s+['\"]\{[^{}\n]*\bprint\s+\$NF\b[^{}\n]*\}['\"]",
        body,
    )
    if not (
        basename_command
        or re.search(r"%f", body)
        or re.search(r"\$\{[^}]+##\*/\}", body)
        or sed_basename
        or awk_basename
    ):
        problems.append("missing basename extraction")
    if not re.search(r"\bsort\b", body):
        problems.append("missing sort")
    if "*.Modelfile" not in body:
        problems.append("missing *.Modelfile filter")
    return problems

def evaluate_agent_output(text: str, case: dict[str, Any]) -> dict[str, Any]:
    stripped = text.strip()
    body = clean_code_output(text)
    fenced = stripped.startswith("```")
    format_ok = bool(body) and not (case.get("raw_only") and fenced)
    problems: list[str] = []
    if not body:
        problems.append("empty final answer")
    validator = case["validator"]
    parsed_json: dict[str, Any] | None = None
    syntax_ok = False
    if body:
        try:
            if validator == "python":
                ast.parse(body)
            elif validator == "bash":
                result = subprocess.run(
                    ["bash", "-n"], input=body, text=True, capture_output=True,
                    check=False, timeout=5
                )
                if result.returncode:
                    raise ValueError(result.stderr.strip() or "bash -n failed")
            elif validator == "json":
                value = json.loads(body)
                if not isinstance(value, dict):
                    raise ValueError("top-level JSON is not an object")
                parsed_json = value
            else:
                raise ValueError(f"unknown validator: {validator}")
            syntax_ok = True
        except (SyntaxError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            problems.append(f"syntax: {exc}")
    folded = acceptance_text(body)
    missing = [term for term in case.get("required", []) if acceptance_text(term) not in folded]
    if missing:
        problems.append("missing required: " + ", ".join(missing))
    for group in case.get("required_any", []):
        if not any(acceptance_text(term) in folded for term in group):
            problems.append("missing one-of: " + " | ".join(group))
    forbidden = [term for term in case.get("forbidden", []) if acceptance_text(term) in folded]
    if forbidden:
        problems.append("forbidden present: " + ", ".join(forbidden))
    if validator == "python" and syntax_ok:
        problems.extend(_python_contract(body, case))
    if validator == "bash" and syntax_ok:
        problems.extend(_bash_contract(body, case))
    if case.get("raw_only") and fenced:
        problems.append("raw-only response was wrapped in a Markdown fence")
    if parsed_json is not None:
        missing_keys = [key for key in case.get("json_keys", []) if key not in parsed_json]
        if missing_keys:
            problems.append("missing JSON keys: " + ", ".join(missing_keys))
        bad_arrays = [key for key in case.get("json_array_keys", []) if not isinstance(parsed_json.get(key), list)]
        if bad_arrays:
            problems.append("JSON keys are not arrays: " + ", ".join(bad_arrays))
    requirement_problems = [
        problem
        for problem in problems
        if not problem.startswith("syntax:")
        and "Markdown fence" not in problem
        and problem != "empty final answer"
    ]
    requirements_ok = not requirement_problems
    accepted = format_ok and syntax_ok and requirements_ok
    return {
        "body": body,
        "format_ok": format_ok,
        "syntax_ok": syntax_ok,
        "requirements_ok": requirements_ok,
        "accepted": accepted,
        "problems": problems,
    }


def agent_options(case: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {"num_predict": int(case.get("num_predict", 384))}
    raw = os.environ.get("AGENT_TEMPERATURE", "").strip()
    if raw:
        options["temperature"] = float(raw)
    return options


def benchmark_agent(args: argparse.Namespace) -> int:
    client = OllamaClient(args.ollama_url, args.timeout)
    fixture = Path(args.fixture or FIXTURE_ROOT / "agent-cases.json")
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    models = choose_models(client, args.models, "agentic-")
    if not models:
        raise BenchmarkError("no agentic models found")
    paths = prepare_result_dir("agent", args.output_dir)
    csv_path, jsonl_path, meta_path = paths.csv_export, paths.results_jsonl, paths.meta_json
    copy_fixtures(paths, fixture)
    write_meta(
        meta_path, client, "agent", models, fixture,
        options={
            "temperature_override": (
                float(os.environ["AGENT_TEMPERATURE"])
                if os.environ.get("AGENT_TEMPERATURE", "").strip() else None
            )
        },
    )
    fields = [
        "timestamp", "model", "case_id", "validator", "format_ok", "syntax_ok",
        "requirements_ok", "accepted", "validation_error",
        "answer_started", "answer_chars", "thinking_chars", "wall_s", "load_s",
        "eval_count", "done_reason", "temp_max_c", "mem_available_min_mib",
        "swap_used_max_mib",
    ]
    total = passed = 0
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for model in models:
            print(f"\n=== agent: {model} ===")
            client.ensure_unloaded(model)
            try:
                for case in cases:
                    payload = {
                        "model": model,
                        "messages": [{"role": "user", "content": case["prompt"]}],
                        "stream": False,
                        "options": agent_options(case),
                    }
                    sampler = TelemetrySampler(TELEMETRY_INTERVAL).start()
                    start_time = time.monotonic()
                    try:
                        response = client.json_request("/api/chat", payload)
                    finally:
                        wall = time.monotonic() - start_time
                        telemetry = sampler.stop()
                    message = response.get("message") if isinstance(response.get("message"), dict) else {}
                    content = str(message.get("content") or "")
                    thinking = str(message.get("thinking") or response.get("thinking") or "")
                    result = evaluate_agent_output(content, case)
                    accepted = bool(result["accepted"])
                    total += 1
                    passed += int(accepted)
                    done_reason = str(response.get("done_reason") or "")
                    failures: list[str] = []
                    if not content.strip(): failures.append("empty-output")
                    if not result["format_ok"] and content.strip(): failures.append("format-contract")
                    if not result["syntax_ok"] and content.strip(): failures.append("syntax")
                    if not result["requirements_ok"] and content.strip(): failures.append("requirements")
                    diagnostics: list[str] = []
                    if done_reason == "length":
                        diagnostics.append("output-budget")
                        if not content.strip() and thinking.strip(): diagnostics.append("thinking-budget")
                    error = "; ".join(result["problems"])
                    row = {
                        "timestamp": iso_now(), "model": model, "case_id": case["id"], "validator": case["validator"],
                        "format_ok": int(bool(result["format_ok"])), "syntax_ok": int(bool(result["syntax_ok"])),
                        "requirements_ok": int(bool(result["requirements_ok"])), "accepted": int(accepted),
                        "validation_error": error,
                        "answer_started": int(bool(content.strip())), "answer_chars": len(content), "thinking_chars": len(thinking),
                        "wall_s": f"{wall:.3f}", "load_s": f"{ns_to_s(response.get('load_duration')):.3f}",
                        "eval_count": response.get("eval_count", 0), "done_reason": done_reason,
                        "temp_max_c": telemetry.get("temp_max_c"), "mem_available_min_mib": telemetry.get("mem_available_min_mib"),
                        "swap_used_max_mib": telemetry.get("swap_used_max_mib"),
                    }
                    writer.writerow(row)
                    append_result(
                        jsonl_path,
                        result_record(
                            category="agent",
                            model=model,
                            case_id=case["id"],
                            result_type="qualification",
                            outcome="pass" if accepted else "quality-fail",
                            failure_kinds=failures,
                            diagnostics=diagnostics,
                            checks={
                                "format": bool(result["format_ok"]),
                                "syntax": bool(result["syntax_ok"]),
                                "requirements": bool(result["requirements_ok"]),
                            },
                            metrics={
                                "wall_s": wall,
                                "eval_count": response.get("eval_count", 0),
                                "answer_chars": len(content),
                                "thinking_chars": len(thinking),
                            },
                            timestamp=iso_now(),
                            case=case,
                            response=content,
                            thinking=thinking,
                            validation_error=error,
                            telemetry=telemetry,
                        ),
                    )
                    print(
                        f"  {case['id']}: format={result['format_ok']} "
                        f"syntax={result['syntax_ok']} "
                        f"requirements={result['requirements_ok']} "
                        f"accepted={accepted} wall={wall:.2f}s"
                    )
            finally:
                try:
                    client.ensure_unloaded(model)
                except BenchmarkError as exc:
                    print(f"WARNING: {exc}", file=sys.stderr)
    _summary_json, summary_txt = write_result_summary(jsonl_path, category="agent")
    print(f"\nAgent acceptance: {passed}/{total} passed")
    print_result_paths(paths, summary_txt)
    return 0 if passed == total else 3


OCR_PROMPTS = {
    # GLM-OCR uses its trained recognition trigger. Ovis accepts a natural-language
    # extraction instruction. Both are scored against the same text/structure goals.
    "glm": "Text Recognition:",
    "ovis": (
        "Extract all readable text in natural human reading order. Preserve the "
        "source exactly without translation or paraphrasing. Preserve table row "
        "and column associations when possible."
    ),
}


def ocr_kind(model: str) -> str:
    lower = model.lower()
    if "glm-ocr" in lower:
        return "glm"
    if "ovisocr" in lower:
        return "ovis"
    return "generic"


class _OCRTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)


def canonical_ocr_text(text: str) -> str:
    """Canonical plain text for fidelity scoring; structure uses raw output."""
    parser = _OCRTextExtractor()
    try:
        parser.feed(text)
        plain = " ".join(parser.parts) if parser.parts else text
    except (AssertionError, UnicodeError, ValueError):
        plain = text
    plain = re.sub(r"```[^\n]*|```", " ", plain)
    plain = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", plain)
    plain = plain.replace("|", " ").replace("`", "")
    return " ".join(plain.split())


def normalize_for_match(text: str) -> str:
    return " ".join(text.casefold().split())


def levenshtein_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for index, left_char in enumerate(left, 1):
        current = [index]
        for column, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def ocr_structure_score(output: str, case: dict[str, Any]) -> float:
    """Score whether important row/field associations remain locally recoverable."""
    groups = case.get("structure_groups", [])
    if not groups:
        return 1.0
    folded = normalize_for_match(output)
    window = int(case.get("structure_window", 240))
    matched = 0
    for group in groups:
        cursor = 0
        first = last = -1
        ok = True
        for term in group:
            needle = normalize_for_match(str(term))
            pos = folded.find(needle, cursor)
            if pos < 0:
                ok = False
                break
            if first < 0:
                first = pos
            last = pos + len(needle)
            cursor = last
        if ok and first >= 0 and last - first <= window:
            matched += 1
    return matched / len(groups)


def ocr_table_signal(output: str) -> float:
    folded = output.casefold()
    if "<table" in folded and "<tr" in folded:
        return 1.0
    lines = [line for line in output.splitlines() if line.count("|") >= 2]
    return 1.0 if len(lines) >= 2 else 0.0


def ocr_scores(
    output: str, case: dict[str, Any]
) -> tuple[float, float, float, float, float, float, float, float]:
    canonical_output = canonical_ocr_text(output)
    output_words = normalize_words(canonical_output)
    expected_words = normalize_words(case["expected_text"])
    overlap = sum((Counter(output_words) & Counter(expected_words)).values())
    word_precision = (
        overlap / len(output_words)
        if output_words
        else (1.0 if not expected_words else 0.0)
    )
    word_recall = overlap / len(expected_words) if expected_words else 1.0
    word_f1 = (
        (2 * word_precision * word_recall / (word_precision + word_recall))
        if word_precision + word_recall
        else 0.0
    )
    normalized_output = normalize_for_match(canonical_output)
    normalized_expected = normalize_for_match(case["expected_text"])
    edit_distance = levenshtein_distance(normalized_output, normalized_expected)
    char_similarity = 1.0 - edit_distance / max(
        len(normalized_output), len(normalized_expected), 1
    )
    char_similarity = max(0.0, char_similarity)
    folded = canonical_output.casefold()
    fields = case.get("required_fields", [])
    field_recall = (
        sum(1 for field in fields if field.casefold() in folded) / len(fields)
        if fields
        else 1.0
    )
    cursor = ordered_hits = 0
    for field in fields:
        needle = field.casefold()
        pos = folded.find(needle, cursor)
        if pos >= 0:
            ordered_hits += 1
            cursor = pos + len(needle)
    field_order_score = ordered_hits / len(fields) if fields else 1.0
    return (
        word_precision,
        word_recall,
        word_f1,
        char_similarity,
        field_recall,
        field_order_score,
        ocr_structure_score(output, case),
        ocr_table_signal(output),
    )


def benchmark_ocr(args: argparse.Namespace) -> int:
    client = OllamaClient(args.ollama_url, args.timeout)
    manifest = Path(args.fixture or FIXTURE_ROOT / "ocr" / "manifest.json")
    fixture_dir = manifest.parent
    cases = json.loads(manifest.read_text(encoding="utf-8"))
    models = choose_models(client, args.models, "exp-")
    models = [model for model in models if ocr_kind(model) != "generic"]
    if not models:
        raise BenchmarkError("no packaged OCR models found")

    paths = prepare_result_dir("ocr", args.output_dir)
    csv_path, jsonl_path, meta_path = paths.csv_export, paths.results_jsonl, paths.meta_json
    copy_fixtures(paths, fixture_dir)
    write_meta(meta_path, client, "ocr", models, manifest)

    fields = [
        "timestamp",
        "model",
        "case_id",
        "language",
        "word_precision",
        "word_recall",
        "word_f1",
        "char_similarity",
        "field_recall",
        "field_order_score",
        "structure_score",
        "table_signal",
        "wall_s",
        "load_s",
        "prompt_eval_count",
        "eval_count",
        "done_reason",
        "resident_size_bytes",
        "resident_vram_bytes",
        "allocated_context",
        "temp_max_c",
        "temp_p95_c",
        "seconds_ge_80c",
        "seconds_ge_83c",
        "seconds_ge_85c",
        "gpu_busy_max_pct",
        "gpu_clock_min_mhz",
        "gpu_clock_max_mhz",
        "vram_used_max_bytes",
        "gtt_used_max_bytes",
        "mem_available_min_mib",
        "swap_used_max_mib",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for model in models:
            kind = ocr_kind(model)
            prompt = OCR_PROMPTS[kind]
            print(f"\n=== OCR: {model} ({kind}) ===")
            client.ensure_unloaded(model)
            try:
                for case in cases:
                    image_path = fixture_dir / case["file"]
                    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
                    message = {"role": "user", "content": prompt, "images": [encoded]}
                    payload: dict[str, Any] = {
                        "model": model,
                        "messages": [message],
                        "stream": False,
                        "keep_alive": KEEP_ALIVE,
                    }
                    # OvisOCR2 is trained for direct extraction rather than a
                    # visible reasoning trace.
                    if kind == "ovis":
                        payload["think"] = False
                    sampler = TelemetrySampler(TELEMETRY_INTERVAL).start()
                    start = time.monotonic()
                    try:
                        response = client.json_request("/api/chat", payload)
                    finally:
                        wall = time.monotonic() - start
                        telemetry = sampler.stop()
                    content = str((response.get("message") or {}).get("content") or "")
                    (
                        word_precision,
                        word_recall,
                        word_f1,
                        char_similarity,
                        field_recall,
                        field_order_score,
                        structure_score,
                        table_signal,
                    ) = ocr_scores(content, case)
                    state = client.runtime_state(model)
                    row = {
                        "timestamp": iso_now(),
                        "model": model,
                        "case_id": case["id"],
                        "language": case["language"],
                        "word_precision": f"{word_precision:.3f}",
                        "word_recall": f"{word_recall:.3f}",
                        "word_f1": f"{word_f1:.3f}",
                        "char_similarity": f"{char_similarity:.3f}",
                        "field_recall": f"{field_recall:.3f}",
                        "field_order_score": f"{field_order_score:.3f}",
                        "structure_score": f"{structure_score:.3f}",
                        "table_signal": f"{table_signal:.3f}",
                        "wall_s": f"{wall:.3f}",
                        "load_s": f"{ns_to_s(response.get('load_duration')):.3f}",
                        "prompt_eval_count": response.get("prompt_eval_count", 0),
                        "eval_count": response.get("eval_count", 0),
                        "done_reason": response.get("done_reason", ""),
                        **state,
                        **{
                            key: telemetry.get(key)
                            for key in fields
                            if key in telemetry
                        },
                    }
                    writer.writerow(row)
                    handle.flush()
                    append_result(
                        jsonl_path,
                        result_record(
                            category="ocr",
                            model=model,
                            case_id=case["id"],
                            result_type="measurement",
                            outcome="pass",
                            diagnostics=(
                                ["thermal"]
                                if safe_float(telemetry.get("seconds_ge_80c")) > 0
                                else []
                            ),
                            metrics={
                                "word_precision": word_precision,
                                "word_recall": word_recall,
                                "word_f1": word_f1,
                                "char_similarity": char_similarity,
                                "field_recall": field_recall,
                                "field_order_score": field_order_score,
                                "structure_score": structure_score,
                                "table_signal": table_signal,
                                "wall_s": wall,
                                "load_s": ns_to_s(response.get("load_duration")),
                                "prompt_eval_count": response.get("prompt_eval_count", 0),
                                "eval_count": response.get("eval_count", 0),
                                "done_reason": response.get("done_reason", ""),
                                "mem_available_min_mib": telemetry.get(
                                    "mem_available_min_mib"
                                ),
                                "swap_peak_delta_mib": telemetry.get(
                                    "swap_peak_delta_mib"
                                ),
                                "temp_max_c": telemetry.get("temp_max_c"),
                            },
                            timestamp=iso_now(),
                            language=case["language"],
                            prompt_kind=kind,
                            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                            response=content,
                            telemetry=telemetry,
                        ),
                    )
                    print(
                        f"  {case['id']}: word-F1={word_f1:.3f} chars={char_similarity:.3f} "
                        f"fields={field_recall:.3f} order={field_order_score:.3f} "
                        f"structure={structure_score:.3f} table={table_signal:.0f} wall={wall:.2f}s "
                        f"Tmax={fmt(telemetry.get('temp_max_c'), 'C')}"
                    )
            finally:
                try:
                    client.ensure_unloaded(model)
                except BenchmarkError as exc:
                    print(f"WARNING: {exc}", file=sys.stderr)
    _summary_json, summary_txt = write_result_summary(jsonl_path, category="ocr")
    print_result_paths(paths, summary_txt)
    return 0



def _acceptance_ok(text: str, case: dict[str, Any]) -> tuple[bool, list[str]]:
    folded = acceptance_text(text)
    missing = [term for term in case.get("required", []) if acceptance_text(term) not in folded]
    choices = case.get("required_any", [])
    if choices and not any(acceptance_text(term) in folded for term in choices):
        missing.append("one of: " + " | ".join(choices))
    present_forbidden = [term for term in case.get("forbidden", []) if acceptance_text(term) in folded]
    problems = [f"missing {term}" for term in missing]
    problems.extend(f"forbidden {term}" for term in present_forbidden)
    return not problems, problems


def rag_case_checks(
    content: str, case: dict[str, Any], *, target_rank: int, top_k: int
) -> tuple[bool, bool, bool, list[str]]:
    answer_ok, problems = _acceptance_ok(content, case)
    retrieval_ok = target_rank <= top_k
    source_cited = f"[{case['target']}]".casefold() in content.casefold()
    if not source_cited:
        problems.append(f"missing source [{case['target']}]")
    return retrieval_ok, answer_ok, source_cited, problems

def acceptance_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(
        str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-"})
    )
    text = re.sub(r"(?<=\d)[\s.,'’](?=\d)", "", text)
    return " ".join(text.casefold().split())


def numeric_values(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for raw in re.findall(r"(?<![\w-])\d(?:[\d\s.,'’]*\d)?(?![\w-])", text):
        token = raw.strip().replace(" ", "").replace("'", "").replace("’", "")
        if not token:
            continue
        last_dot = token.rfind(".")
        last_comma = token.rfind(",")
        decimal_pos = max(last_dot, last_comma)
        if decimal_pos >= 0 and len(token) - decimal_pos - 1 == 2:
            whole = re.sub(r"[.,]", "", token[:decimal_pos]) or "0"
            token = whole + "." + token[decimal_pos + 1 :]
        else:
            token = re.sub(r"[.,]", "", token)
        try:
            values.add(Decimal(token))
        except InvalidOperation:
            continue
    return values


def translation_prompt_profile(model: str) -> str:
    lower = model.casefold()
    if "hunyuan-mt" in lower:
        return "hunyuan-mt-upstream"
    if "translate-gemma" in lower:
        return "translate-gemma-current-source"
    return "generic-explicit"


def translation_prompt(case: dict[str, Any]) -> str:
    names = {"de": "German", "fr": "French", "en": "English"}
    source = names.get(case["source_language"], case["source_language"])
    target = names.get(case["target_language"], case["target_language"])
    return (
        f"Translate from {source} to {target}. Translate every ordinary-language "
        "source word. Preserve names, identifiers, reference numbers, and numeric "
        "amounts. Preserve the calendar value of dates while rendering ordinary date "
        f"wording naturally in {target}. Return only the translation.\n\n{case['input']}"
    )


def translation_messages(case: dict[str, Any], model: str) -> list[dict[str, str]]:
    names = {"de": "German", "fr": "French", "en": "English"}
    source = names.get(case["source_language"], case["source_language"])
    target = names.get(case["target_language"], case["target_language"])
    profile = translation_prompt_profile(model)
    if profile == "hunyuan-mt-upstream":
        return [{
            "role": "user",
            "content": (
                f"Translate the following segment into {target}, without additional "
                f"explanation.\n\n{case['input']}"
            ),
        }]
    if profile == "translate-gemma-current-source":
        system = (
            f"TASK: Translate {source} office and business text into {target}.\n"
            "STYLE: Preserve the source register and formality.\n"
            "Translate only CURRENT_SOURCE. Preserve meaning, names, numbers, "
            "terminology, negations, qualifications and document structure. Return "
            "only the final translation without labels or commentary."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": f"[CURRENT_SOURCE]\n{case['input']}"},
        ]
    return [{"role": "user", "content": translation_prompt(case)}]


def translation_failure_kinds(
    content: str,
    *,
    language_ok: bool,
    source_leakage_ok: bool,
    semantic_ok: bool,
    preserved_ok: bool,
) -> list[str]:
    failures: list[str] = []
    if not content.strip():
        failures.append("empty-output")
    if not language_ok:
        failures.append("language")
    if not source_leakage_ok:
        failures.append("source-leakage")
    if not semantic_ok:
        failures.append("semantic")
    if not preserved_ok:
        failures.append("preservation")
    return failures


def translation_content_checks(
    content: str, case: dict[str, Any]
) -> tuple[bool, bool, bool, bool]:
    folded = acceptance_text(content)
    required_ok = all(
        acceptance_text(term) in folded for term in case.get("required", [])
    )
    choices = case.get("required_any", [])
    if choices:
        required_ok = required_ok and any(
            acceptance_text(term) in folded for term in choices
        )
    forbidden_ok = not any(
        acceptance_text(term) in folded for term in case.get("forbidden", [])
    )
    preserved_ok = all(
        acceptance_text(term) in folded for term in case.get("preserve", [])
    )
    expected_numbers = {Decimal(str(value)) for value in case.get("numeric_values", [])}
    if expected_numbers:
        preserved_ok = preserved_ok and expected_numbers.issubset(numeric_values(content))
    meaningful_ok = len(normalize_words(content)) >= int(case.get("min_words", 6))
    return required_ok, forbidden_ok, preserved_ok, meaningful_ok


def benchmark_translation(args: argparse.Namespace) -> int:
    client = OllamaClient(args.ollama_url, args.timeout)
    fixture = Path(args.fixture or FIXTURE_ROOT / "translation-office.json")
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    models = args.models or [
        os.environ.get("TRANSLATION_MODEL", "prod-lfm25-8b-a1b-liquidai-q6-k")
    ]
    available = {
        str(row.get("name") or row.get("model") or "").removesuffix(":latest")
        for row in client.tags()
    }
    missing = [
        model for model in models if model.removesuffix(":latest") not in available
    ]
    if missing:
        raise BenchmarkError(
            "translation models are not registered: " + ", ".join(missing)
        )

    paths = prepare_result_dir("translation", args.output_dir)
    csv_path, jsonl_path, meta_path = paths.csv_export, paths.results_jsonl, paths.meta_json
    copy_fixtures(paths, fixture)
    translation_num_predict = int(os.environ.get("TRANSLATION_NUM_PREDICT", "1024"))
    if translation_num_predict <= 0:
        raise BenchmarkError("TRANSLATION_NUM_PREDICT must be a positive integer")
    write_meta(
        meta_path, client, "translation", models, fixture,
        options={
            "explicit_direction": True,
            "num_predict_default": translation_num_predict,
            "prompt_profiles": {model: translation_prompt_profile(model) for model in models},
        },
    )
    fields = [
        "timestamp",
        "model",
        "case_id",
        "source_language",
        "target_language",
        "passed",
        "meaningful_ok",
        "required_ok",
        "forbidden_ok",
        "preserved_ok",
        "language_hint",
        "language_ok",
        "answer_chars",
        "thinking_chars",
        "wall_s",
        "load_s",
        "eval_count",
        "done_reason",
        "temp_max_c",
        "mem_available_min_mib",
        "swap_used_max_mib",
    ]
    total = passed = 0
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for model in models:
            print(f"\n=== translation: {model} ===")
            client.ensure_unloaded(model)
            try:
                for case in cases:
                    total += 1
                    payload = {
                        "model": model,
                        "messages": translation_messages(case, model),
                        "stream": False,
                        "keep_alive": KEEP_ALIVE,
                        "options": {
                            "num_predict": int(case.get("num_predict", translation_num_predict))
                        },
                    }
                    sampler = TelemetrySampler(TELEMETRY_INTERVAL).start()
                    start_time = time.monotonic()
                    try:
                        response = client.json_request("/api/chat", payload)
                    finally:
                        wall = time.monotonic() - start_time
                        telemetry = sampler.stop()

                    message = (
                        response.get("message")
                        if isinstance(response.get("message"), dict)
                        else {}
                    )
                    content = str(message.get("content") or "")
                    thinking = str(message.get("thinking") or "")
                    (
                        required_ok,
                        forbidden_ok,
                        preserved_ok,
                        meaningful_ok,
                    ) = translation_content_checks(content, case)
                    language_hint = task_language_hint(
                        content, case["target_language"]
                    )
                    language_ok = language_hint == "match"
                    semantic_ok = required_ok and meaningful_ok
                    ok = (
                        bool(content.strip())
                        and language_ok
                        and semantic_ok
                        and forbidden_ok
                        and preserved_ok
                    )
                    passed += int(ok)

                    done_reason = str(response.get("done_reason") or "")
                    failures = translation_failure_kinds(
                        content,
                        language_ok=language_ok,
                        source_leakage_ok=forbidden_ok,
                        semantic_ok=semantic_ok,
                        preserved_ok=preserved_ok,
                    )
                    diagnostics: list[str] = []
                    if done_reason == "length":
                        diagnostics.append("output-budget")
                        if not content.strip() and thinking.strip():
                            diagnostics.append("thinking-budget")

                    row = {
                        "timestamp": iso_now(),
                        "model": model,
                        "case_id": case["id"],
                        "source_language": case["source_language"],
                        "target_language": case["target_language"],
                        "passed": int(ok),
                        "meaningful_ok": int(meaningful_ok),
                        "required_ok": int(required_ok),
                        "forbidden_ok": int(forbidden_ok),
                        "preserved_ok": int(preserved_ok),
                        "language_hint": language_hint,
                        "language_ok": int(language_ok),
                        "answer_chars": len(content),
                        "thinking_chars": len(thinking),
                        "wall_s": f"{wall:.3f}",
                        "load_s": f"{ns_to_s(response.get('load_duration')):.3f}",
                        "eval_count": response.get("eval_count", 0),
                        "done_reason": done_reason,
                        "temp_max_c": telemetry.get("temp_max_c"),
                        "mem_available_min_mib": telemetry.get(
                            "mem_available_min_mib"
                        ),
                        "swap_used_max_mib": telemetry.get("swap_used_max_mib"),
                    }
                    writer.writerow(row)
                    handle.flush()
                    append_result(
                        jsonl_path,
                        result_record(
                            category="translation",
                            model=model,
                            case_id=case["id"],
                            result_type="qualification",
                            outcome="pass" if ok else "quality-fail",
                            failure_kinds=failures,
                            diagnostics=diagnostics,
                            checks={
                                "language": language_ok,
                                "semantic": semantic_ok,
                                "preservation": preserved_ok,
                                "source_leakage": forbidden_ok,
                            },
                            metrics={
                                "wall_s": wall,
                                "eval_count": response.get("eval_count", 0),
                                "answer_chars": len(content),
                            },
                            timestamp=iso_now(),
                            source_language=case["source_language"],
                            target_language=case["target_language"],
                            response=content,
                            thinking=thinking,
                            telemetry=telemetry,
                        ),
                    )
                    print(
                        f"  {case['id']}: pass={ok} lang={language_hint} "
                        f"semantic={semantic_ok} preserve={preserved_ok} "
                        f"wall={wall:.2f}s"
                    )
            finally:
                try:
                    client.ensure_unloaded(model)
                except BenchmarkError as exc:
                    print(f"WARNING: {exc}", file=sys.stderr)

    _summary_json, summary_txt = write_result_summary(
        jsonl_path, category="translation"
    )
    print(f"\nTranslation acceptance: {passed}/{total} passed")
    print_result_paths(paths, summary_txt)
    return 0 if passed == total else 3


def _usecase_result_record(
    *,
    case: dict[str, Any],
    model: str,
    row: dict[str, Any],
    ok: bool,
    problems: list[str],
    content: str,
    thinking: str,
    telemetry: dict[str, Any],
    wall: float,
    done_reason: str,
) -> dict[str, Any]:
    failures = [] if ok else (["empty-output"] if not content.strip() else ["semantic"])
    diagnostics: list[str] = []
    if done_reason == "length":
        diagnostics.append("output-budget")
        if not content.strip() and thinking.strip():
            diagnostics.append("thinking-budget")
    return result_record(
        category="usecase",
        model=model,
        case_id=case["id"],
        result_type="qualification",
        outcome="pass" if ok else "quality-fail",
        failure_kinds=failures,
        diagnostics=diagnostics,
        checks={"acceptance": ok},
        metrics={"wall_s": wall, "answer_chars": len(content)},
        timestamp=row["timestamp"],
        passed=bool(ok),
        problems=problems,
        prompt=case["prompt"],
        response=content,
        thinking=thinking,
        telemetry=telemetry,
        done_reason=done_reason,
    )

def benchmark_usecase(args: argparse.Namespace) -> int:
    client = OllamaClient(args.ollama_url, args.timeout)
    fixture = Path(args.fixture or FIXTURE_ROOT / "usecase-office.json")
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    requested = {model.removesuffix(":latest") for model in args.models}
    if requested:
        cases = [
            case
            for case in cases
            if case["model"].removesuffix(":latest") in requested
        ]
    if not cases:
        raise BenchmarkError("no production acceptance cases selected")

    available = {
        str(row.get("name") or row.get("model") or "").removesuffix(":latest")
        for row in client.tags()
    }
    missing_models = sorted(
        {
            case["model"]
            for case in cases
            if case["model"].removesuffix(":latest") not in available
        }
    )
    if missing_models:
        raise BenchmarkError(
            "acceptance models are not registered: " + ", ".join(missing_models)
        )

    models = list(dict.fromkeys(case["model"] for case in cases))
    paths = prepare_result_dir("usecase", args.output_dir)
    csv_path, jsonl_path, meta_path = paths.csv_export, paths.results_jsonl, paths.meta_json
    copy_fixtures(paths, fixture)
    write_meta(meta_path, client, "usecase", models, fixture)
    fields = [
        "timestamp",
        "case_id",
        "model",
        "passed",
        "answer_started",
        "answer_chars",
        "thinking_chars",
        "wall_s",
        "load_s",
        "done_reason",
        "problems",
    ]
    passed = 0
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            model = case["model"]
            print(f"\n=== usecase: {case['id']} ({model}) ===")
            client.ensure_unloaded(model)
            try:
                payload: dict[str, Any] = {
                    "model": model,
                    "messages": [{"role": "user", "content": case["prompt"]}],
                    "stream": False,
                    "keep_alive": KEEP_ALIVE,
                    "options": {"num_predict": 512},
                }
                if "think" in case:
                    payload["think"] = case["think"]
                sampler = TelemetrySampler(TELEMETRY_INTERVAL).start()
                start = time.monotonic()
                try:
                    response = client.json_request("/api/chat", payload)
                finally:
                    wall = time.monotonic() - start
                    telemetry = sampler.stop()

                message = (
                    response.get("message")
                    if isinstance(response.get("message"), dict)
                    else {}
                )
                content = str(message.get("content") or "")
                thinking = str(
                    message.get("thinking") or response.get("thinking") or ""
                )
                ok, problems = _acceptance_ok(content, case)
                passed += int(ok)
                row = {
                    "timestamp": iso_now(),
                    "case_id": case["id"],
                    "model": model,
                    "passed": int(ok),
                    "answer_started": int(bool(content.strip())),
                    "answer_chars": len(content),
                    "thinking_chars": len(thinking),
                    "wall_s": f"{wall:.3f}",
                    "load_s": f"{ns_to_s(response.get('load_duration')):.3f}",
                    "done_reason": response.get("done_reason", ""),
                    "problems": "; ".join(problems),
                }
                writer.writerow(row)
                handle.flush()
                done_reason = str(response.get("done_reason") or "")
                append_result(
                    jsonl_path,
                    _usecase_result_record(
                        case=case,
                        model=model,
                        row=row,
                        ok=ok,
                        problems=problems,
                        content=content,
                        thinking=thinking,
                        telemetry=telemetry,
                        wall=wall,
                        done_reason=done_reason,
                    ),
                )
                print(
                    f"  pass={ok} wall={wall:.2f}s "
                    f"problems={row['problems'] or 'none'}"
                )
            finally:
                try:
                    client.ensure_unloaded(model)
                except BenchmarkError as exc:
                    print(f"WARNING: {exc}", file=sys.stderr)

    _sj, summary_txt = write_result_summary(jsonl_path, category="usecase")
    print(f"\nAcceptance: {passed}/{len(cases)} passed")
    print_result_paths(paths, summary_txt)
    return 0 if passed == len(cases) else 3


def rag_cycle_outcome(answer_ok: bool, answer_model_still_loaded: bool) -> tuple[str, list[str], int]:
    """Classify RAG coexistence separately from answer quality."""
    if not answer_model_still_loaded:
        return "infra-fail", ["coexistence"], 1
    if not answer_ok:
        return "quality-fail", ["answer"], 3
    return "pass", [], 0


def benchmark_rag_cycle(args: argparse.Namespace) -> int:
    answer_client = OllamaClient(args.ollama_url, args.timeout)
    embed_url = args.embedding_ollama_url
    embed_client = OllamaClient(embed_url, args.timeout)
    fixture = Path(args.fixture or FIXTURE_ROOT / "rag-cycle.json")
    case = json.loads(fixture.read_text(encoding="utf-8"))
    if args.models and len(args.models) != 2:
        raise BenchmarkError(
            "rag requires zero models or exactly EMBED_MODEL ANSWER_MODEL"
        )
    embed_model = (
        args.models[0]
        if args.models
        else os.environ.get(
            "RAG_EMBED_MODEL", "embed-jina-v5-small-retrieval-q4-k-m"
        )
    )
    answer_model = (
        args.models[1]
        if args.models
        else os.environ.get(
            "RAG_ANSWER_MODEL", "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl"
        )
    )
    embed_available = {
        str(row.get("name") or row.get("model") or "").removesuffix(":latest")
        for row in embed_client.tags()
    }
    answer_available = {
        str(row.get("name") or row.get("model") or "").removesuffix(":latest")
        for row in answer_client.tags()
    }
    if embed_model.removesuffix(":latest") not in embed_available:
        raise BenchmarkError(f"RAG embedding model is not registered on {embed_url}: {embed_model}")
    if answer_model.removesuffix(":latest") not in answer_available:
        raise BenchmarkError(f"RAG answer model is not registered on {args.ollama_url}: {answer_model}")

    paths = prepare_result_dir("rag-cycle", args.output_dir)
    csv_path, jsonl_path, meta_path = paths.csv_export, paths.results_jsonl, paths.meta_json
    copy_fixtures(paths, fixture)
    write_meta(
        meta_path, answer_client, "rag-cycle", [answer_model], fixture,
        options={"embedding_ollama_url": embed_url},
    )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    embed_version = embed_client.version()
    meta.setdefault("runtimes", []).append({
        "kind": "ollama",
        "url": embed_client.base_url,
        "version": embed_version,
        "package_standard_version": STANDARD_OLLAMA_VERSION,
    })
    meta.setdefault("models", []).append(model_meta(embed_client, embed_model))
    write_benchmark_metadata(meta_path, meta)

    embed_client.ensure_unloaded(embed_model)
    answer_client.ensure_unloaded(answer_model)
    sampler = TelemetrySampler(TELEMETRY_INTERVAL).start()
    try:
        warm_payload = {
            "model": answer_model,
            "messages": [{"role": "user", "content": "Reply only: ready"}],
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": {"num_predict": 16},
        }
        prime = answer_client.json_request("/api/chat", warm_payload)
        warm_start = time.monotonic()
        warm = answer_client.json_request("/api/chat", warm_payload)
        warm_wall = time.monotonic() - warm_start

        query_prefix, _doc_prefix, scheme = embedding_scheme(embed_model)
        cycle_start = time.monotonic()
        embed_start = time.monotonic()
        emb = embed(embed_client, embed_model, [query_prefix + case["query"]])
        embed_wall = time.monotonic() - embed_start
        answer_still_loaded = answer_client.model_loaded(answer_model)

        prompt = (
            "Use only this retrieved context:\n"
            f"{case['retrieved_context']}\n\nQuestion: {case['question']}"
        )
        answer_start = time.monotonic()
        answer = answer_client.json_request(
            "/api/chat",
            {
                "model": answer_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "keep_alive": KEEP_ALIVE,
                "options": {"num_predict": 256},
            },
        )
        answer_wall = time.monotonic() - answer_start
        cycle_wall = time.monotonic() - cycle_start
    finally:
        telemetry = sampler.stop()
        for client, model in ((embed_client, embed_model), (answer_client, answer_model)):
            try:
                client.ensure_unloaded(model)
            except BenchmarkError as exc:
                print(f"WARNING: {exc}", file=sys.stderr)

    content = str((answer.get("message") or {}).get("content") or "")
    ok = all(term.casefold() in content.casefold() for term in case.get("required", []))
    row = {
        "timestamp": iso_now(),
        "embed_model": embed_model,
        "answer_model": answer_model,
        "embedding_scheme": scheme,
        "initial_answer_load_s": round(ns_to_s(prime.get("load_duration")), 3),
        "warm_answer_wall_s": round(warm_wall, 3),
        "warm_answer_load_s": round(ns_to_s(warm.get("load_duration")), 3),
        "embed_wall_s": round(embed_wall, 3),
        "embed_load_s": round(ns_to_s(emb.get("load_duration")), 3),
        "answer_still_loaded_after_embed": answer_still_loaded,
        "post_embed_answer_wall_s": round(answer_wall, 3),
        "post_embed_answer_load_s": round(ns_to_s(answer.get("load_duration")), 3),
        "cycle_wall_s": round(cycle_wall, 3),
        "answer_ok": ok,
        "answer_chars": len(content),
        "temp_max_c": telemetry.get("temp_max_c"),
        "mem_available_min_mib": telemetry.get("mem_available_min_mib"),
    }
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    outcome, failure_kinds, exit_rc = rag_cycle_outcome(ok, answer_still_loaded)
    append_result(
        jsonl_path,
        result_record(
            category="rag-cycle",
            model=answer_model,
            case_id=str(case.get("id") or "coexistence"),
            result_type="qualification",
            outcome=outcome,
            failure_kinds=failure_kinds,
            checks={
                "answer": ok,
                "answer_model_still_loaded": answer_still_loaded,
            },
            metrics={
                key: value
                for key, value in row.items()
                if key not in {"timestamp", "embed_model", "answer_model"}
            },
            timestamp=row["timestamp"],
            embed_model=embed_model,
            embedding_scheme=scheme,
            query=case["query"],
            response=content,
            telemetry=telemetry,
        ),
    )
    print(
        f"RAG cycle: warm-answer={warm_wall:.2f}s embed={embed_wall:.2f}s "
        f"post-embed-answer={answer_wall:.2f}s total={cycle_wall:.2f}s "
        f"answer-still-loaded={answer_still_loaded} answer_ok={ok}"
    )
    _summary_json, summary_txt = write_result_summary(jsonl_path, category="rag-cycle")
    print_result_paths(paths, summary_txt)
    return exit_rc

def benchmark_rag_quality(args: argparse.Namespace) -> int:
    answer_client = OllamaClient(args.ollama_url, args.timeout)
    embed_url = args.embedding_ollama_url
    embed_client = OllamaClient(embed_url, args.timeout)
    fixture = Path(args.fixture or FIXTURE_ROOT / "rag-quality-office.json")
    spec = json.loads(fixture.read_text(encoding="utf-8"))
    corpus_path = fixture.parent / spec.get("corpus_file", "embedding-office.json")
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    documents = corpus["documents"]
    cases = spec["cases"]
    if args.models and len(args.models) != 2:
        raise BenchmarkError(
            "rag-quality requires zero models or exactly EMBED_MODEL ANSWER_MODEL"
        )
    embed_model = args.models[0] if args.models else os.environ.get(
        "RAG_EMBED_MODEL", "embed-jina-v5-small-retrieval-q4-k-m"
    )
    answer_model = args.models[1] if args.models else os.environ.get(
        "RAG_ANSWER_MODEL", "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl"
    )
    embed_available = {
        str(row.get("name") or row.get("model") or "").removesuffix(":latest")
        for row in embed_client.tags()
    }
    answer_available = {
        str(row.get("name") or row.get("model") or "").removesuffix(":latest")
        for row in answer_client.tags()
    }
    if embed_model.removesuffix(":latest") not in embed_available:
        raise BenchmarkError(f"RAG-quality embedding model is not registered on {embed_url}: {embed_model}")
    if answer_model.removesuffix(":latest") not in answer_available:
        raise BenchmarkError(f"RAG-quality answer model is not registered on {args.ollama_url}: {answer_model}")

    top_k = int(os.environ.get("RAG_QUALITY_TOP_K", str(spec.get("top_k", 8))))
    default_num_predict = int(os.environ.get("RAG_QUALITY_NUM_PREDICT", "1024"))
    think_policy = args.think
    if top_k < 1:
        raise BenchmarkError("RAG_QUALITY_TOP_K must be at least 1")
    if default_num_predict < 1:
        raise BenchmarkError("RAG_QUALITY_NUM_PREDICT must be at least 1")
    query_prefix, doc_prefix, scheme = embedding_scheme(embed_model)
    embed_client.ensure_unloaded(embed_model)
    answer_client.ensure_unloaded(answer_model)
    doc_vectors = embed(
        embed_client, embed_model, [doc_prefix + item["text"] for item in documents]
    ).get("embeddings", [])
    query_vectors = embed(
        embed_client, embed_model, [query_prefix + item["question"] for item in cases]
    ).get("embeddings", [])
    if len(doc_vectors) != len(documents) or len(query_vectors) != len(cases):
        raise BenchmarkError("RAG-quality embedding count does not match fixture")
    embed_client.ensure_unloaded(embed_model)

    paths = prepare_result_dir("rag-quality", args.output_dir)
    csv_path, jsonl_path, meta_path = paths.csv_export, paths.results_jsonl, paths.meta_json
    copy_fixtures(paths, fixture, corpus_path)
    write_meta(
        meta_path, answer_client, "rag-quality", [answer_model], fixture,
        options={
            "embedding_ollama_url": embed_url,
            "rag_quality_top_k": top_k,
            "rag_quality_num_predict_default": default_num_predict,
            "rag_quality_think_policy": think_policy,
        },
    )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    embed_version = embed_client.version()
    meta.setdefault("runtimes", []).append({
        "kind": "ollama",
        "url": embed_client.base_url,
        "version": embed_version,
        "package_standard_version": STANDARD_OLLAMA_VERSION,
    })
    meta.setdefault("models", []).append(model_meta(embed_client, embed_model))
    meta["fixtures"] = fixture_metadata(fixture, corpus_path)
    write_benchmark_metadata(meta_path, meta)
    fields = [
        "timestamp", "case_id", "embed_model", "answer_model", "embedding_scheme",
        "target_rank", "retrieval_ok", "answer_ok", "source_cited", "passed",
        "failure_kinds", "num_predict", "think_policy", "answer_chars", "thinking_chars", "done_reason",
        "wall_s", "load_s", "temp_max_c", "mem_available_min_mib", "swap_peak_delta_mib",
    ]
    passed = 0
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case, query_vector in zip(cases, query_vectors):
            scored = sorted(
                (
                    (cosine(query_vector, doc_vector), doc)
                    for doc, doc_vector in zip(documents, doc_vectors)
                ),
                key=lambda pair: pair[0],
                reverse=True,
            )
            ranked_ids = [doc["id"] for _score, doc in scored]
            target_rank = ranked_ids.index(case["target"]) + 1
            selected = scored[:top_k]
            context = "\n\n".join(
                f"[{doc['id']}] {doc['text']}" for _score, doc in selected
            )
            prompt = (
                "Answer only from the retrieved office-document context below. "
                "When versions conflict, follow the date/place/version requested by the question. "
                "Do not substitute a similar invoice, office, or archived rule. "
                "Cite the supporting source id in square brackets.\n\n"
                f"{context}\n\nQuestion: {case['question']}"
            )
            num_predict = int(case.get("num_predict", default_num_predict))
            sampler = TelemetrySampler(TELEMETRY_INTERVAL).start()
            start = time.monotonic()
            request = {
                "model": answer_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "keep_alive": KEEP_ALIVE,
                "options": {"num_predict": num_predict},
            }
            if think_policy != "auto":
                request["think"] = think_policy == "true"
            try:
                response = answer_client.json_request("/api/chat", request)
            finally:
                wall = time.monotonic() - start
                telemetry = sampler.stop()
            message = (
                response.get("message")
                if isinstance(response.get("message"), dict)
                else {}
            )
            content = str(message.get("content") or "")
            thinking = str(message.get("thinking") or "")
            retrieval_ok, answer_ok, source_cited, problems = rag_case_checks(
                content, case, target_rank=target_rank, top_k=top_k
            )
            ok = retrieval_ok and answer_ok and source_cited
            done_reason = str(response.get("done_reason") or "")
            thinking_exhausted = (
                not content.strip() and bool(thinking.strip()) and done_reason == "length"
            )
            failure_kinds: list[str] = []
            if not retrieval_ok:
                failure_kinds.append("retrieval")
            if not answer_ok:
                failure_kinds.append("answer")
            if not source_cited:
                failure_kinds.append("citation")
            diagnostics: list[str] = []
            if thinking_exhausted:
                diagnostics.extend(["thinking-budget", "output-budget"])
            elif done_reason == "length":
                diagnostics.append("output-budget")
            passed += int(ok)
            row = {
                "timestamp": iso_now(),
                "case_id": case["id"],
                "embed_model": embed_model,
                "answer_model": answer_model,
                "embedding_scheme": scheme,
                "target_rank": target_rank,
                "retrieval_ok": int(retrieval_ok),
                "answer_ok": int(answer_ok),
                "source_cited": int(source_cited),
                "passed": int(ok),
                "failure_kinds": ";".join(failure_kinds),
                "num_predict": num_predict,
                "think_policy": think_policy,
                "answer_chars": len(content),
                "thinking_chars": len(thinking),
                "done_reason": done_reason,
                "wall_s": f"{wall:.3f}",
                "load_s": f"{ns_to_s(response.get('load_duration')):.3f}",
                "temp_max_c": telemetry.get("temp_max_c"),
                "mem_available_min_mib": telemetry.get("mem_available_min_mib"),
                "swap_peak_delta_mib": telemetry.get("swap_peak_delta_mib"),
            }
            writer.writerow(row)
            handle.flush()
            append_result(
                jsonl_path,
                result_record(
                    category="rag-quality",
                    model=answer_model,
                    case_id=case["id"],
                    result_type="qualification",
                    outcome="pass" if ok else "quality-fail",
                    failure_kinds=failure_kinds,
                    diagnostics=diagnostics,
                    checks={
                        "retrieval": retrieval_ok,
                        "answer": answer_ok,
                        "citation": source_cited,
                    },
                    metrics={
                        "target_rank": target_rank,
                        "num_predict": num_predict,
                        "answer_chars": len(content),
                        "thinking_chars": len(thinking),
                        "wall_s": wall,
                        "load_s": ns_to_s(response.get("load_duration")),
                        "mem_available_min_mib": telemetry.get(
                            "mem_available_min_mib"
                        ),
                        "swap_peak_delta_mib": telemetry.get(
                            "swap_peak_delta_mib"
                        ),
                        "temp_max_c": telemetry.get("temp_max_c"),
                    },
                    timestamp=iso_now(),
                    embed_model=embed_model,
                    embedding_scheme=scheme,
                    think_policy=think_policy,
                    question=case["question"],
                    target=case["target"],
                    top=[(round(score, 6), doc["id"]) for score, doc in selected],
                    response=content,
                    thinking=thinking,
                    problems=problems,
                    done_reason=done_reason,
                    telemetry=telemetry,
                ),
            )
            print(
                f"  {case['id']}: rank={target_rank} retrieval={retrieval_ok} "
                f"answer={answer_ok} cited={source_cited} pass={ok} "
                f"failures={','.join(failure_kinds) or 'none'} think={think_policy}"
            )
    try:
        answer_client.ensure_unloaded(answer_model)
    except BenchmarkError as exc:
        print(f"WARNING: {exc}", file=sys.stderr)
    _summary_json, summary_txt = write_result_summary(
        jsonl_path, category="rag-quality"
    )
    print(f"\nRAG quality acceptance: {passed}/{len(cases)} passed")
    print_result_paths(paths, summary_txt)
    return 0 if passed == len(cases) else 3


def fmt(value: Any, suffix: str) -> str:
    if value is None or value == "":
        return "n/a"
    try:
        return f"{float(value):.1f}{suffix}"
    except (TypeError, ValueError):
        return f"{value}{suffix}"


def add_common(parser: argparse.ArgumentParser, default_url: str) -> None:
    parser.add_argument(
        "models",
        nargs="*",
        help="registered model names; default discovers the category",
    )
    parser.add_argument(
        "--ollama-url", default=os.environ.get("OLLAMA_URL", default_url)
    )
    parser.add_argument(
        "--timeout", type=float, default=float(os.environ.get("REQUEST_TIMEOUT", "900"))
    )
    parser.add_argument("--fixture", help="override packaged fixture/manifest")
    parser.add_argument("--output-dir", help="result directory; must be empty")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="bc250-benchmark",
        description="Category-specific BC-250 benchmark suites for Ollama 0.33.3.",
    )
    sub = parser.add_subparsers(dest="category", required=True)
    emb = sub.add_parser(
        "embeddings", help="multilingual retrieval quality + throughput"
    )
    add_common(emb, "http://127.0.0.1:11437")
    emb.add_argument(
        "--repeats", type=int, default=int(os.environ.get("EMBED_REPEATS", "2"))
    )
    task = sub.add_parser(
        "task", help="Open WebUI 0.11.3-compatible title/tag/query tasks"
    )
    add_common(task, "http://127.0.0.1:11435")
    agent = sub.add_parser(
        "agent", help="coding/agent static contract acceptance + runtime"
    )
    add_common(agent, "http://127.0.0.1:11436")
    ocr = sub.add_parser(
        "ocr", help="office OCR accuracy + runtime on packaged fixtures"
    )
    add_common(ocr, "http://127.0.0.1:11434")
    usecase = sub.add_parser(
        "usecase", help="one role-defining acceptance case per production model"
    )
    add_common(usecase, "http://127.0.0.1:11434")
    translation = sub.add_parser(
        "translation", help="DE/FR office translation acceptance"
    )
    add_common(translation, "http://127.0.0.1:11434")
    rag = sub.add_parser(
        "rag-cycle",
        help="measure dedicated embedding activity while the main answer model stays resident",
    )
    add_common(rag, "http://127.0.0.1:11434")
    rag.add_argument(
        "--embedding-ollama-url",
        default=os.environ.get("EMBEDDING_OLLAMA_URL", "http://127.0.0.1:11437"),
    )
    rag_quality = sub.add_parser(
        "rag-quality", help="embedding retrieval plus grounded-answer acceptance"
    )
    add_common(rag_quality, "http://127.0.0.1:11434")
    rag_quality.add_argument(
        "--embedding-ollama-url",
        default=os.environ.get("EMBEDDING_OLLAMA_URL", "http://127.0.0.1:11437"),
    )
    rag_quality.add_argument(
        "--think", choices=("auto", "true", "false"), default="auto"
    )
    args = parser.parse_args()

    if args.category == "embeddings":
        return benchmark_embeddings(args)
    if args.category == "task":
        return benchmark_task(args)
    if args.category == "agent":
        return benchmark_agent(args)
    if args.category == "ocr":
        return benchmark_ocr(args)
    if args.category == "usecase":
        return benchmark_usecase(args)
    if args.category == "translation":
        return benchmark_translation(args)
    if args.category == "rag-cycle":
        return benchmark_rag_cycle(args)
    if args.category == "rag-quality":
        return benchmark_rag_quality(args)
    return 2


def entrypoint() -> int:
    try:
        return main()
    except KeyboardInterrupt as exc:
        finalize_active_infrastructure_failure(exc, failure_kind="interrupted")
        print("ERROR: benchmark interrupted.", file=sys.stderr)
        return 130
    except (BenchmarkError, OSError, json.JSONDecodeError) as exc:
        finalize_active_infrastructure_failure(exc)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(entrypoint())
