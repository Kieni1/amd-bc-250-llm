#!/usr/bin/env python3
"""Category-specific BC-250 benchmarks for embeddings, OCR, task, and agent models."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark_common import (
    STANDARD_OLLAMA_VERSION,
    BenchmarkError,
    OllamaClient,
    TelemetrySampler,
    cosine,
    mean,
    normalize_words,
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
    }


def append_jsonl(path: Path, data: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")


def write_meta(
    path: Path, client: OllamaClient, category: str, models: list[str], fixture: Path
) -> None:
    data = {
        "started_at": iso_now(),
        "category": category,
        "ollama_url": client.base_url,
        "ollama_version": client.version(),
        "package_standard_ollama_version": STANDARD_OLLAMA_VERSION,
        "fixture": str(fixture),
        "models": [model_meta(client, model) for model in models],
        "telemetry_interval_s": TELEMETRY_INTERVAL,
    }
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if data["ollama_version"] != STANDARD_OLLAMA_VERSION:
        print(
            f"WARNING: Ollama {data['ollama_version']} differs from package standard {STANDARD_OLLAMA_VERSION}",
            file=sys.stderr,
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

    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    csv_path = Path(args.output or f"results_embeddings_{stamp}.csv")
    jsonl_path = csv_path.with_suffix(".jsonl")
    meta_path = csv_path.with_suffix(".meta.json")
    write_meta(meta_path, client, "embeddings", models, fixture)

    fields = [
        "timestamp",
        "model",
        "prefix_scheme",
        "recall_at_1",
        "recall_at_3",
        "mrr",
        "cross_recall_at_1",
        "cross_mrr",
        "documents",
        "queries",
        "dimensions",
        "cold_load_s",
        "quality_wall_s",
        "warm_input_tps",
        "warm_wall_s",
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

                    if len(doc_vectors) != len(documents) or len(query_vectors) != len(
                        queries
                    ):
                        raise BenchmarkError(
                            f"{model}: embedding count does not match fixture"
                        )

                    ranks: list[int] = []
                    cross_ranks: list[int] = []
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
                        if query_item.get("kind") == "cross":
                            cross_ranks.append(rank)
                        append_jsonl(
                            jsonl_path,
                            {
                                "timestamp": iso_now(),
                                "category": "embedding",
                                "model": model,
                                "query_id": query_item["id"],
                                "target": query_item["target"],
                                "rank": rank,
                                "top3": scored[:3],
                                "prefix_scheme": scheme,
                            },
                        )

                    warm_tps: list[float] = []
                    warm_walls: list[float] = []
                    for repeat in range(args.repeats):
                        start = time.monotonic()
                        response = embed(client, model, doc_inputs)
                        wall = time.monotonic() - start
                        seconds = process_seconds(response)
                        count = int(response.get("prompt_eval_count") or 0)
                        warm_tps.append(count / seconds if seconds > 0 else 0.0)
                        warm_walls.append(wall)
                        print(
                            f"  warm {repeat + 1}/{args.repeats}: {warm_tps[-1]:.1f} input tok/s, {wall:.3f}s"
                        )
                finally:
                    telemetry = sampler.stop()
                state = client.runtime_state(model)
                row = {
                    "timestamp": iso_now(),
                    "model": model,
                    "prefix_scheme": scheme,
                    "recall_at_1": mean(1.0 if rank <= 1 else 0.0 for rank in ranks),
                    "recall_at_3": mean(1.0 if rank <= 3 else 0.0 for rank in ranks),
                    "mrr": mean(1.0 / rank for rank in ranks),
                    "cross_recall_at_1": mean(
                        1.0 if rank <= 1 else 0.0 for rank in cross_ranks
                    ),
                    "cross_mrr": mean(1.0 / rank for rank in cross_ranks),
                    "documents": len(documents),
                    "queries": len(queries),
                    "dimensions": len(doc_vectors[0]) if doc_vectors else 0,
                    "cold_load_s": cold_load_s,
                    "quality_wall_s": quality_wall_s,
                    "warm_input_tps": mean(warm_tps),
                    "warm_wall_s": mean(warm_walls),
                    **state,
                    **{key: telemetry.get(key) for key in fields if key in telemetry},
                }
                writer.writerow(row)
                handle.flush()
                print(
                    f"  quality: R@1={row['recall_at_1']:.3f} R@3={row['recall_at_3']:.3f} "
                    f"MRR={row['mrr']:.3f} cross-MRR={row['cross_mrr']:.3f}"
                )
                print(
                    f"  resources: Tmax={fmt(telemetry.get('temp_max_c'), 'C')} "
                    f"MemAvailable-min={fmt(telemetry.get('mem_available_min_mib'), 'MiB')}"
                )
            finally:
                try:
                    client.ensure_unloaded(model)
                except BenchmarkError as exc:
                    print(f"WARNING: {exc}", file=sys.stderr)

    print(f"\nResults: {csv_path}\nDetails: {jsonl_path}\nMeta:    {meta_path}")
    return 0


# Mirrors the behavior/shape of Open WebUI v0.11.1's default title/tag/query
# task templates without vendoring the full upstream prose into this package.
def task_prompt(case: dict[str, Any]) -> str:
    messages = case.get("messages") or [
        {"role": "user", "content": case.get("input", "")}
    ]

    def history(limit: int) -> str:
        return "\n".join(
            f"{str(message.get('role', 'user')).upper()}: {message.get('content', '')!s}"
            for message in messages[-limit:]
        )

    if case["type"] == "title":
        return f"""### Task:
Generate a concise title summarizing the chat history.
Keep it to 2-4 words when possible, use the chat's primary language, and do not use emojis or decorative formatting.
Return only one raw JSON object: {{\"title\": \"short title\"}}
### Chat History (Open WebUI 0.11.1: latest 2 messages):
<chat_history>
{history(2)}
</chat_history>"""
    if case["type"] == "tags":
        return f"""### Task:
Generate 1-3 broad theme tags plus 1-3 specific subtopic tags in the chat's primary language.
If the chat has fewer than 3 messages or is too diverse, return only {{\"tags\": [\"General\"]}}.
Otherwise return only one raw JSON object: {{\"tags\": [\"tag1\", \"tag2\"]}}
### Chat History (Open WebUI 0.11.1: latest 6 messages):
<chat_history>
{history(6)}
</chat_history>"""
    current_date = datetime.now().astimezone().date().isoformat()
    return f"""### Task:
Generate 1-3 broad, relevant retrieval queries in the language of the chat when useful; err on the side of generating useful queries.
If no useful retrieval is possible, return an empty list. Today's date is {current_date}.
Return only one raw JSON object: {{\"queries\": [\"query1\", \"query2\"]}}
### Chat History (Open WebUI 0.11.1: latest 6 messages):
<chat_history>
{history(6)}
</chat_history>"""


def parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text.strip())
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


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


def benchmark_task(args: argparse.Namespace) -> int:
    client = OllamaClient(args.ollama_url, args.timeout)
    fixture = Path(args.fixture or FIXTURE_ROOT / "task-cases.json")
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    models = choose_models(client, args.models, "task-")
    if not models:
        raise BenchmarkError("no task models found")
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    csv_path = Path(args.output or f"results_task_{stamp}.csv")
    jsonl_path = csv_path.with_suffix(".jsonl")
    meta_path = csv_path.with_suffix(".meta.json")
    write_meta(meta_path, client, "task", models, fixture)

    fields = [
        "timestamp",
        "model",
        "case_id",
        "task",
        "language",
        "valid_json",
        "structure_ok",
        "keyword_score",
        "wall_s",
        "load_s",
        "eval_count",
        "done_reason",
        "temp_max_c",
        "mem_available_min_mib",
        "swap_used_max_mib",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for model in models:
            print(f"\n=== task: {model} ===")
            scores: list[float] = []
            for case in cases:
                prompt = task_prompt(case)
                # Open WebUI v0.11.1 uses chat completions for task prompts. The
                # isolated service has OLLAMA_KEEP_ALIVE=0; keep_alive=0 here
                # deliberately reproduces its load/unload behaviour.
                options: dict[str, Any] = {}
                if case["type"] == "title":
                    # v0.11.1 with empty TASK_MODEL_PARAMS supplies a
                    # generous title max-token cap.
                    options["num_predict"] = 1000
                else:
                    options["num_predict"] = 128
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "keep_alive": 0,
                    "options": options,
                }
                sampler = TelemetrySampler(TELEMETRY_INTERVAL).start()
                start = time.monotonic()
                try:
                    response = client.json_request("/api/chat", payload)
                except BaseException:
                    client.stop(model)
                    client.wait_unloaded(model)
                    raise
                finally:
                    wall = time.monotonic() - start
                    telemetry = sampler.stop()
                content = str((response.get("message") or {}).get("content") or "")
                parsed = parse_json_object(content)
                valid_json = parsed is not None
                structure_ok = False
                if parsed is not None:
                    if case["type"] == "title":
                        title = parsed.get("title")
                        structure_ok = (
                            isinstance(title, str) and 1 <= len(title.split()) <= 8
                        )
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
                            and len(queries) <= 3
                            and all(isinstance(x, str) for x in queries)
                        )
                score = keyword_score(content, case.get("keywords", []))
                scores.append(score if structure_ok else 0.0)
                writer.writerow(
                    {
                        "timestamp": iso_now(),
                        "model": model,
                        "case_id": case["id"],
                        "task": case["type"],
                        "language": case["language"],
                        "valid_json": int(valid_json),
                        "structure_ok": int(structure_ok),
                        "keyword_score": f"{score:.3f}",
                        "wall_s": f"{wall:.3f}",
                        "load_s": f"{ns_to_s(response.get('load_duration')):.3f}",
                        "eval_count": response.get("eval_count", 0),
                        "done_reason": response.get("done_reason", ""),
                        "temp_max_c": telemetry.get("temp_max_c"),
                        "mem_available_min_mib": telemetry.get("mem_available_min_mib"),
                        "swap_used_max_mib": telemetry.get("swap_used_max_mib"),
                    }
                )
                append_jsonl(
                    jsonl_path,
                    {
                        "timestamp": iso_now(),
                        "category": "task",
                        "model": model,
                        "case": case,
                        "response": content,
                        "valid_json": valid_json,
                        "structure_ok": structure_ok,
                        "keyword_score": score,
                        "wall_s": wall,
                        "telemetry": telemetry,
                    },
                )
                print(
                    f"  {case['id']}: json={valid_json} structure={structure_ok} keyword={score:.2f} "
                    f"wall={wall:.2f}s Tmax={fmt(telemetry.get('temp_max_c'), 'C')}"
                )
            print(f"  mean task score: {mean(scores):.3f}")
    print(f"\nResults: {csv_path}\nDetails: {jsonl_path}\nMeta:    {meta_path}")
    return 0


def clean_code_output(text: str) -> str:
    text = re.sub(
        r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE
    ).strip()
    match = re.fullmatch(r"```[^\n]*\n(.*?)\n```", text, flags=re.DOTALL)
    return (match.group(1) if match else text).strip()


def validate_agent_output(text: str, case: dict[str, Any]) -> tuple[bool, bool, str]:
    body = clean_code_output(text)
    validator = case["validator"]
    error = ""
    try:
        if validator == "python":
            compile(body, f"<{case['id']}>", "exec")
        elif validator == "bash":
            result = subprocess.run(
                ["bash", "-n"],
                input=body,
                text=True,
                capture_output=True,
                check=False,
                timeout=5,
            )
            if result.returncode:
                raise ValueError(result.stderr.strip() or "bash -n failed")
        elif validator == "json":
            if not isinstance(json.loads(body), dict):
                raise ValueError("top-level JSON is not an object")
        else:
            raise ValueError(f"unknown validator: {validator}")
        syntax_ok = True
    except (
        SyntaxError,
        ValueError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as exc:
        syntax_ok, error = False, str(exc)
    folded = body.casefold()
    requirements_ok = all(
        term.casefold() in folded for term in case.get("required", [])
    )
    return syntax_ok, requirements_ok, error


def agent_options(case: dict[str, Any]) -> dict[str, Any]:
    """Use deployed agent sampling unless an explicit benchmark override is requested."""
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
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    csv_path = Path(args.output or f"results_agent_{stamp}.csv")
    jsonl_path = csv_path.with_suffix(".jsonl")
    meta_path = csv_path.with_suffix(".meta.json")
    write_meta(meta_path, client, "agent", models, fixture)
    fields = [
        "timestamp",
        "model",
        "case_id",
        "validator",
        "syntax_ok",
        "requirements_ok",
        "correctness_ok",
        "wall_s",
        "load_s",
        "eval_count",
        "done_reason",
        "temp_max_c",
        "mem_available_min_mib",
        "swap_used_max_mib",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for model in models:
            print(f"\n=== agent: {model} ===")
            client.ensure_unloaded(model)
            try:
                for case in cases:
                    # Do not override keep_alive here: the isolated agent service
                    # owns that policy (5m in the packaged service definition).
                    payload = {
                        "model": model,
                        "messages": [{"role": "user", "content": case["prompt"]}],
                        "stream": False,
                        "options": agent_options(case),
                    }
                    sampler = TelemetrySampler(TELEMETRY_INTERVAL).start()
                    start = time.monotonic()
                    try:
                        response = client.json_request("/api/chat", payload)
                    finally:
                        wall = time.monotonic() - start
                        telemetry = sampler.stop()
                    content = str((response.get("message") or {}).get("content") or "")
                    syntax_ok, requirements_ok, error = validate_agent_output(
                        content, case
                    )
                    correctness_ok = syntax_ok and requirements_ok
                    writer.writerow(
                        {
                            "timestamp": iso_now(),
                            "model": model,
                            "case_id": case["id"],
                            "validator": case["validator"],
                            "syntax_ok": int(syntax_ok),
                            "requirements_ok": int(requirements_ok),
                            "correctness_ok": int(correctness_ok),
                            "wall_s": f"{wall:.3f}",
                            "load_s": f"{ns_to_s(response.get('load_duration')):.3f}",
                            "eval_count": response.get("eval_count", 0),
                            "done_reason": response.get("done_reason", ""),
                            "temp_max_c": telemetry.get("temp_max_c"),
                            "mem_available_min_mib": telemetry.get(
                                "mem_available_min_mib"
                            ),
                            "swap_used_max_mib": telemetry.get("swap_used_max_mib"),
                        }
                    )
                    handle.flush()
                    append_jsonl(
                        jsonl_path,
                        {
                            "timestamp": iso_now(),
                            "category": "agent",
                            "model": model,
                            "case": case,
                            "response": content,
                            "syntax_ok": syntax_ok,
                            "requirements_ok": requirements_ok,
                            "correctness_ok": correctness_ok,
                            "validation_error": error,
                            "wall_s": wall,
                            "telemetry": telemetry,
                        },
                    )
                    print(
                        f"  {case['id']}: syntax={syntax_ok} requirements={requirements_ok} wall={wall:.2f}s"
                    )
            finally:
                try:
                    client.ensure_unloaded(model)
                except BenchmarkError as exc:
                    print(f"WARNING: {exc}", file=sys.stderr)
    print(f"\nResults: {csv_path}\nDetails: {jsonl_path}\nMeta:    {meta_path}")
    return 0


OCR_PROMPTS = {
    "glm": "Text Recognition:",
    "dots": """Please output the document layout and text in human reading order. Include each element's category and text; format tables as HTML, formulas as LaTeX, and other text as Markdown. Preserve the original text exactly without translation.""",
    "ovis": """Extract all readable content from the image in natural human reading order and output one Markdown document. Format formulas as LaTeX and tables as HTML. Preserve the original text without translation or paraphrasing.""",
    "chandra": """Convert this office document image to structured Markdown. Preserve the original language, reading order, headings, tables, form fields, names, dates, numbers and reference identifiers. Do not translate or summarize.""",
}


def ocr_kind(model: str) -> str:
    lower = model.lower()
    if "glm-ocr" in lower:
        return "glm"
    if "dots-ocr" in lower or "dots.ocr" in lower:
        return "dots"
    if "ovisocr" in lower:
        return "ovis"
    if "chandra" in lower:
        return "chandra"
    return "generic"


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


def ocr_scores(
    output: str, case: dict[str, Any]
) -> tuple[float, float, float, float, float, float]:
    output_words = normalize_words(output)
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
    normalized_output = normalize_for_match(output)
    normalized_expected = normalize_for_match(case["expected_text"])
    edit_distance = levenshtein_distance(normalized_output, normalized_expected)
    char_similarity = 1.0 - edit_distance / max(
        len(normalized_output), len(normalized_expected), 1
    )
    char_similarity = max(0.0, char_similarity)
    folded = output.casefold()
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

    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    csv_path = Path(args.output or f"results_ocr_{stamp}.csv")
    jsonl_path = csv_path.with_suffix(".jsonl")
    meta_path = csv_path.with_suffix(".meta.json")
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
                    # OvisOCR2 and Chandra are Qwen3.5-derived OCR models trained for
                    # direct extraction rather than a visible reasoning trace.
                    if kind in {"ovis", "chandra"}:
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
                    append_jsonl(
                        jsonl_path,
                        {
                            "timestamp": iso_now(),
                            "category": "ocr",
                            "model": model,
                            "case": case["id"],
                            "prompt": prompt,
                            "response": content,
                            "word_precision": word_precision,
                            "word_recall": word_recall,
                            "word_f1": word_f1,
                            "char_similarity": char_similarity,
                            "field_recall": field_recall,
                            "field_order_score": field_order_score,
                            "telemetry": telemetry,
                        },
                    )
                    print(
                        f"  {case['id']}: word-F1={word_f1:.3f} chars={char_similarity:.3f} "
                        f"fields={field_recall:.3f} order={field_order_score:.3f} wall={wall:.2f}s "
                        f"Tmax={fmt(telemetry.get('temp_max_c'), 'C')}"
                    )
            finally:
                try:
                    client.ensure_unloaded(model)
                except BenchmarkError as exc:
                    print(f"WARNING: {exc}", file=sys.stderr)
    print(f"\nResults: {csv_path}\nDetails: {jsonl_path}\nMeta:    {meta_path}")
    return 0


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
    parser.add_argument("--output", help="CSV output path")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="bc250-benchmark",
        description="Category-specific BC-250 benchmark suites for Ollama 0.32.15.",
    )
    sub = parser.add_subparsers(dest="category", required=True)
    emb = sub.add_parser(
        "embeddings",
        aliases=["embedding"],
        help="multilingual retrieval quality + throughput",
    )
    add_common(emb, "http://127.0.0.1:11434")
    emb.add_argument(
        "--repeats", type=int, default=int(os.environ.get("EMBED_REPEATS", "2"))
    )
    task = sub.add_parser(
        "task", help="Open WebUI 0.11.1-compatible title/tag/query tasks"
    )
    add_common(task, "http://127.0.0.1:11435")
    agent = sub.add_parser(
        "agent", aliases=["coding"], help="coding/agent output correctness + runtime"
    )
    add_common(agent, "http://127.0.0.1:11436")
    ocr = sub.add_parser(
        "ocr", help="office OCR accuracy + runtime on packaged fixtures"
    )
    add_common(ocr, "http://127.0.0.1:11434")
    args = parser.parse_args()

    try:
        if args.category in {"embeddings", "embedding"}:
            return benchmark_embeddings(args)
        if args.category == "task":
            return benchmark_task(args)
        if args.category in {"agent", "coding"}:
            return benchmark_agent(args)
        if args.category == "ocr":
            return benchmark_ocr(args)
    except (BenchmarkError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
