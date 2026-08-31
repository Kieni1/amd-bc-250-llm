#!/usr/bin/env python3
"""Generation benchmark for BC-250 Ollama models.

The benchmark has two deliberate modes:

* neutral (default): one neutral SYSTEM override and deterministic sampling so
  different models see comparable instructions;
* production: no SYSTEM/sampling override, so the registered Modelfile is
  exercised as deployed.

Request shapes target Ollama 0.32.15.  The implementation is stdlib-only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark_common import (
    DEFAULT_TELEMETRY_INTERVAL,
    STANDARD_OLLAMA_VERSION,
    BenchmarkError,
    OllamaClient,
    TelemetrySampler,
)

NEUTRAL_SYSTEM = os.environ.get(
    "NEUTRAL_SYSTEM_PROMPT",
    "You are a general-purpose assistant. Follow the user's instructions accurately and completely. "
    "Respond in the language requested by the user; otherwise use the language of the user's request. "
    "Do not assume a specialized role unless the user asks for one.",
)
SHORT_PROMPT = os.environ.get(
    "BENCH_PROMPT",
    "Explain three advantages and three disadvantages of remote work for a medium-sized office. "
    "Use around 500 words, include concrete examples, and finish with a short conclusion.",
)
CHAT_PROMPT = os.environ.get(
    "CHAT_PROMPT",
    "In one concise paragraph, explain one benefit and one risk of remote work and state a practical next action.",
)

TELEMETRY_FIELDS = [
    "telemetry_samples",
    "telemetry_duration_s",
    "temp_max_c",
    "temp_p95_c",
    "seconds_ge_80c",
    "seconds_ge_83c",
    "seconds_ge_85c",
    "temp_peak_label",
    "gpu_busy_max_pct",
    "gpu_clock_min_mhz",
    "gpu_clock_max_mhz",
    "vram_used_max_bytes",
    "gtt_used_max_bytes",
    "mem_available_min_mib",
    "swap_used_max_mib",
]

CSV_FIELDS = [
    "timestamp",
    "model",
    "label",
    "test",
    "run",
    "status",
    "bench_mode",
    "think_policy",
    "eval_count",
    "eval_duration_s",
    "tokens_per_second",
    "prompt_eval_count",
    "prompt_eval_duration_s",
    "prompt_tokens_per_second",
    "total_duration_s",
    "load_duration_s",
    "wall_duration_s",
    "time_to_first_content_s",
    "time_to_first_answer_s",
    "answer_started",
    "answer_chars",
    "thinking_chars",
    "done_reason",
    "server_overhead_s",
    "client_overhead_s",
    "resident_size_bytes",
    "resident_vram_bytes",
    "allocated_context",
    *TELEMETRY_FIELDS,
]


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ns_to_s(value: Any) -> float:
    try:
        return float(value or 0) / 1_000_000_000.0
    except (TypeError, ValueError):
        return 0.0


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else 0.0


def short_name(model: str) -> str:
    name = model.rsplit("/", 1)[-1].removesuffix(":latest")
    for suffix in ("-GGUF", "-gguf", "-Instruct", "-instruct"):
        name = name.removesuffix(suffix)
    return name


def prompt_variant(prompt: str, variant: int = 0) -> str:
    """Vary prompt tokens without adding semantic benchmark metadata.

    A few leading blank lines keep repeated requests from being byte-identical
    without giving reasoning models a request id or other text to interpret.
    """
    return "\n" * (1 + variant % 7) + prompt


def latency_budget(base: int, thinking: int, think_policy: str, model: str = "") -> int:
    """Use a larger shared cap when reasoning can still consume answer space.

    LFM2.5 was measured emitting native reasoning even when Ollama received
    think:false, so keep its latency fixture on the reasoning-capable budget.
    """
    if think_policy == "false" and "lfm" not in model.casefold():
        return base
    return thinking


def make_filler(sentences: int) -> str:
    return " ".join(
        f"Office document sentence {index} records a dated policy item, reference number, responsible department, payment term, and procedural note."
        for index in range(1, sentences + 1)
    )


def resolve_think_policy(model: str, requested: str) -> str:
    """Return omit|true|false|low|medium|high|max for Ollama 0.32.15."""
    if requested != "auto":
        return requested
    lower = model.casefold()
    if "gpt-oss" in lower:
        return "medium"
    # The packaged stock Qwen3.5 profile uses upstream non-thinking sampling.
    if "qwen35" in lower and not any(
        token in lower for token in ("defiant", "fable", "heretic")
    ):
        return "false"
    if "qwen3-4b" in lower:
        return "false"
    # Gemma4 mode is selected by its SYSTEM token; LFM/Ornith/other native families
    # have native/template reasoning behaviour that should not be flattened by
    # a generic boolean in a cross-family benchmark.
    return "omit"


def think_value(policy: str) -> bool | str | None:
    if policy == "omit":
        return None
    if policy == "true":
        return True
    if policy == "false":
        return False
    return policy


def options_for(mode: str, num_predict: int) -> dict[str, Any]:
    if mode == "neutral":
        return {"temperature": 0, "num_predict": num_predict}
    return {"num_predict": num_predict}


def generate_payload(
    model: str,
    prompt: str,
    num_predict: int,
    mode: str,
    think_policy: str,
    keep_alive: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
        "options": options_for(mode, num_predict),
    }
    if mode == "neutral":
        # Ollama 0.32.15 GenerateRequest.System explicitly overrides the
        # registered Modelfile SYSTEM. Do not use raw=true: model renderers and
        # templates remain part of the runtime being benchmarked.
        payload["system"] = NEUTRAL_SYSTEM
    value = think_value(think_policy)
    if value is not None:
        payload["think"] = value
    return payload


def chat_payload(
    model: str,
    prompt: str,
    num_predict: int,
    mode: str,
    think_policy: str,
    keep_alive: str,
) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if mode == "neutral":
        messages.append({"role": "system", "content": NEUTRAL_SYSTEM})
    messages.append({"role": "user", "content": prompt})
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": keep_alive,
        "options": options_for(mode, num_predict),
    }
    value = think_value(think_policy)
    if value is not None:
        payload["think"] = value
    return payload


def response_metrics(response: dict[str, Any], wall_s: float) -> dict[str, Any]:
    eval_s = ns_to_s(response.get("eval_duration"))
    prompt_s = ns_to_s(response.get("prompt_eval_duration"))
    total_s = ns_to_s(response.get("total_duration"))
    load_s = ns_to_s(response.get("load_duration"))
    eval_count = int(response.get("eval_count") or 0)
    prompt_count = int(response.get("prompt_eval_count") or 0)
    server_overhead = max(0.0, total_s - load_s - prompt_s - eval_s)
    return {
        "eval_count": eval_count,
        "eval_duration_s": eval_s,
        "tokens_per_second": safe_div(eval_count, eval_s),
        "prompt_eval_count": prompt_count,
        "prompt_eval_duration_s": prompt_s,
        "prompt_tokens_per_second": safe_div(prompt_count, prompt_s),
        "total_duration_s": total_s,
        "load_duration_s": load_s,
        "wall_duration_s": wall_s,
        "done_reason": str(response.get("done_reason") or "unknown"),
        "server_overhead_s": server_overhead,
        "client_overhead_s": max(0.0, wall_s - total_s),
    }


def run_generate(
    client: OllamaClient,
    model: str,
    prompt: str,
    num_predict: int,
    mode: str,
    think_policy: str,
    keep_alive: str,
    telemetry_interval: float,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    payload = generate_payload(
        model, prompt, num_predict, mode, think_policy, keep_alive
    )
    sampler = TelemetrySampler(telemetry_interval).start()
    start = time.monotonic()
    try:
        response = client.json_request("/api/generate", payload)
    finally:
        wall = time.monotonic() - start
        telemetry = sampler.stop()
    metrics = response_metrics(response, wall)
    metrics.update(client.runtime_state(model))
    metrics.update(telemetry)
    detail = {
        "request": payload,
        "response": response.get("response", ""),
        "thinking": response.get("thinking", ""),
    }
    return metrics, telemetry, detail


def run_chat_stream(
    client: OllamaClient,
    model: str,
    prompt: str,
    num_predict: int,
    mode: str,
    think_policy: str,
    keep_alive: str,
    telemetry_interval: float,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    payload = chat_payload(model, prompt, num_predict, mode, think_policy, keep_alive)
    sampler = TelemetrySampler(telemetry_interval).start()
    started = time.monotonic()
    first_content: float | None = None
    first_answer: float | None = None
    content_parts: list[str] = []
    thinking_parts: list[str] = []
    final: dict[str, Any] = {}
    try:
        for item in client.ndjson_request("/api/chat", payload):
            now = time.monotonic()
            message = (
                item.get("message") if isinstance(item.get("message"), dict) else {}
            )
            content = str(message.get("content") or item.get("response") or "")
            thinking = str(message.get("thinking") or item.get("thinking") or "")
            if (content or thinking) and first_content is None:
                first_content = now
            if content and first_answer is None:
                first_answer = now
            if content:
                content_parts.append(content)
            if thinking:
                thinking_parts.append(thinking)
            if item.get("done") is True:
                final = item
    finally:
        wall = time.monotonic() - started
        telemetry = sampler.stop()
    if not final:
        raise BenchmarkError(
            f"{model}: streaming chat ended without a final done record"
        )
    metrics = response_metrics(final, wall)
    metrics["time_to_first_content_s"] = (
        None if first_content is None else first_content - started
    )
    metrics["time_to_first_answer_s"] = (
        None if first_answer is None else first_answer - started
    )
    answer = "".join(content_parts)
    thinking = "".join(thinking_parts)
    metrics["answer_started"] = bool(answer)
    metrics["answer_chars"] = len(answer)
    metrics["thinking_chars"] = len(thinking)
    metrics.update(client.runtime_state(model))
    metrics.update(telemetry)
    detail = {
        "request": payload,
        "response": answer,
        "thinking": thinking,
    }
    return metrics, telemetry, detail


def write_jsonl(path: Path, data: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")


def csv_row(
    model: str,
    test: str,
    run: int,
    mode: str,
    think_policy: str,
    metrics: dict[str, Any],
    status: str = "ok",
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "timestamp": iso_now(),
        "model": model,
        "label": short_name(model),
        "test": test,
        "run": run,
        "status": status,
        "bench_mode": mode,
        "think_policy": think_policy,
        "time_to_first_content_s": metrics.get("time_to_first_content_s"),
        "time_to_first_answer_s": metrics.get("time_to_first_answer_s"),
    }
    row.update({field: metrics.get(field) for field in CSV_FIELDS if field not in row})
    return row


def early_stop_warning(
    metrics: dict[str, Any], requested: int, fraction: float
) -> str | None:
    # done_reason=length means Ollama honoured the requested generation cap;
    # only a short stop is evidence of an early EOS/EOT worth investigating.
    count = int(metrics.get("eval_count") or 0)
    reason = str(metrics.get("done_reason") or "")
    if reason == "stop" and count < requested * fraction:
        return f"early stop: generated {count}/{requested} tokens (done_reason=stop)"
    return None


def context_truncation_warning(previous: int, current: int) -> str | None:
    if previous >= 0 and current <= previous:
        return (
            "prompt_eval_count stopped growing "
            f"({previous} -> {current}); possible context truncation"
        )
    return None


def answer_budget_warning(metrics: dict[str, Any], requested: int) -> str | None:
    if (
        metrics.get("answer_started") is False
        and str(metrics.get("done_reason") or "") == "length"
    ):
        return f"no final answer before {requested}-token generation cap"
    return None


def select_models(client: OllamaClient, explicit: list[str]) -> list[str]:
    if explicit:
        return explicit
    names = [str(row.get("name") or row.get("model") or "") for row in client.tags()]
    names = [
        name
        for name in names
        if name
        and not any(token in name.casefold() for token in ("embed-", "ocr", "task-"))
    ]
    if not names:
        raise BenchmarkError("no generation models found")
    if not sys.stdin.isatty():
        return names
    print("Available generation models:")
    for index, name in enumerate(names):
        print(f"  {index:2d}) {name}")
    selection = input("Indices (e.g. 0,2-4) or Enter for all: ").strip()
    if not selection:
        return names
    chosen: list[str] = []
    for part in selection.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start, end = [int(value) for value in part.split("-", 1)]
            except ValueError:
                continue
            for index in range(start, end + 1):
                if 0 <= index < len(names):
                    chosen.append(names[index])
        else:
            try:
                index = int(part)
            except ValueError:
                continue
            if 0 <= index < len(names):
                chosen.append(names[index])
    unique = list(dict.fromkeys(chosen))
    if not unique:
        raise BenchmarkError("no valid models selected")
    return unique


def bool_setting(
    name: str, default: bool, *, interactive_prompt: str | None = None
) -> bool:
    raw = os.environ.get(name)
    if raw is not None:
        return raw.casefold() in {"1", "true", "yes", "y", "on"}
    if interactive_prompt and sys.stdin.isatty():
        suffix = "[Y/n]" if default else "[y/N]"
        answer = input(f"{interactive_prompt} {suffix}: ").strip().casefold()
        if not answer:
            return default
        return answer in {"1", "true", "yes", "y", "on"}
    return default


def fmt(value: Any, digits: int = 2) -> str:
    if value is None or value == "":
        return "n/a"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def aggregate_resource(rows: Iterable[dict[str, Any]]) -> dict[str, float | None]:
    values = list(rows)

    def extrema(key: str, fn: Any) -> float | None:
        found = [float(row[key]) for row in values if row.get(key) not in (None, "")]
        return fn(found) if found else None

    return {
        "temp_max_c": extrema("temp_max_c", max),
        "temp_p95_max_c": extrema("temp_p95_c", max),
        "mem_available_min_mib": extrema("mem_available_min_mib", min),
        "swap_used_max_mib": extrema("swap_used_max_mib", max),
        "vram_used_max_bytes": extrema("vram_used_max_bytes", max),
        "gtt_used_max_bytes": extrema("gtt_used_max_bytes", max),
        "gpu_clock_min_mhz": extrema("gpu_clock_min_mhz", min),
        "gpu_clock_max_mhz": extrema("gpu_clock_max_mhz", max),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="bc250-benchmark",
        description="BC-250 generation benchmark for Ollama 0.32.15.",
    )
    parser.add_argument(
        "models",
        nargs="*",
        help="registered model names; default is interactive discovery",
    )
    parser.add_argument(
        "--ollama-url",
        default=os.environ.get(
            "OLLAMA_URL", os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        ),
    )
    parser.add_argument("--output", help="CSV output path")
    args = parser.parse_args()

    profile = os.environ.get("BENCH_PROFILE", "moderate").casefold()
    if profile not in {"moderate", "conservative"}:
        raise BenchmarkError("BENCH_PROFILE must be moderate or conservative")
    defaults = {
        "moderate": {
            "short": 384,
            "prefill": 32,
            "context": 128,
            "long": 3072,
            "latency": 96,
            "latency_thinking": 512,
            "repeats": 3,
            "latency_repeats": 2,
            "filler": 220,
            "ctx": [44, 176, 352, 704],
        },
        "conservative": {
            "short": 256,
            "prefill": 24,
            "context": 96,
            "long": 2048,
            "latency": 64,
            "latency_thinking": 384,
            "repeats": 2,
            "latency_repeats": 1,
            "filler": 110,
            "ctx": [22, 88, 220],
        },
    }[profile]
    # TODO (future release): production mode currently keeps deployment SYSTEM/sampling
    # but still uses the generic generation workload. Add role-specific office/RAG/
    # translation fixtures separately; do not turn the neutral suite into a role benchmark.
    mode = os.environ.get("BENCH_MODE", "neutral").casefold()
    if mode not in {"neutral", "production"}:
        raise BenchmarkError("BENCH_MODE must be neutral or production")
    think_requested = os.environ.get("THINK_MODE", "auto").casefold()
    if think_requested not in {
        "auto",
        "omit",
        "true",
        "false",
        "low",
        "medium",
        "high",
        "max",
    }:
        raise BenchmarkError(
            "THINK_MODE must be auto, omit, true, false, low, medium, high, or max"
        )

    num_short = int(os.environ.get("NUM_PREDICT_SHORT", defaults["short"]))
    num_prefill = int(os.environ.get("NUM_PREDICT_PREFILL", defaults["prefill"]))
    num_context = int(os.environ.get("NUM_PREDICT_CONTEXT", defaults["context"]))
    num_long = int(os.environ.get("NUM_PREDICT_LONG", defaults["long"]))
    latency_override = os.environ.get("NUM_PREDICT_LATENCY")
    num_latency = int(latency_override or defaults["latency"])
    num_latency_thinking = int(
        os.environ.get(
            "NUM_PREDICT_LATENCY_THINKING",
            latency_override or defaults["latency_thinking"],
        )
    )
    repeats = int(os.environ.get("REPEATS", defaults["repeats"]))
    latency_repeats = int(
        os.environ.get("LATENCY_REPEATS", defaults["latency_repeats"])
    )
    filler_sentences = int(os.environ.get("PREFILL_SENTENCES", defaults["filler"]))
    ctx_points = [
        int(value)
        for value in os.environ.get(
            "CTX_POINTS", " ".join(str(value) for value in defaults["ctx"])
        ).split()
    ]
    telemetry_interval = float(
        os.environ.get("TELEMETRY_INTERVAL", str(DEFAULT_TELEMETRY_INTERVAL))
    )
    keep_alive = os.environ.get("KEEP_ALIVE", "30m")
    early_fraction = float(os.environ.get("EARLY_EOS_FRACTION", "0.10"))
    run_latency = bool_setting("RUN_LATENCY", True)
    run_context = bool_setting(
        "RUN_CONTEXT",
        profile == "moderate",
        interactive_prompt="Run context-capacity curve too?",
    )
    run_thermal = bool_setting(
        "RUN_THERMAL", False, interactive_prompt="Run sustained-load thermal test too?"
    )
    thermal_windows = int(os.environ.get("THROTTLE_WINDOWS", "3"))

    client = OllamaClient(
        args.ollama_url, float(os.environ.get("REQUEST_TIMEOUT", "900"))
    )
    version = client.version()
    if version != STANDARD_OLLAMA_VERSION:
        print(
            f"WARNING: Ollama {version} differs from package standard {STANDARD_OLLAMA_VERSION}",
            file=sys.stderr,
        )
    models = select_models(client, args.models)
    board_note = os.environ.get("BOARD_NOTE", "")
    if not board_note and sys.stdin.isatty():
        board_note = input(
            "Board/cooling/governor note for this run [optional]: "
        ).strip()

    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    csv_path = Path(args.output or f"results_generation_{stamp}.csv")
    jsonl_path = csv_path.with_suffix(".jsonl")
    meta_path = csv_path.with_suffix(".meta.json")
    started = iso_now()
    meta = {
        "started_at": started,
        "category": "generation",
        "benchmark_version": "7.3",
        "bench_mode": mode,
        "ollama_url": client.base_url,
        "ollama_version": version,
        "package_standard_ollama_version": STANDARD_OLLAMA_VERSION,
        "neutral_system_prompt": NEUTRAL_SYSTEM if mode == "neutral" else None,
        "neutral_system_sha256": hashlib.sha256(NEUTRAL_SYSTEM.encode()).hexdigest()
        if mode == "neutral"
        else None,
        "think_mode_requested": think_requested,
        "telemetry_interval_s": telemetry_interval,
        "profile": profile,
        "run_latency": run_latency,
        "run_context": run_context,
        "run_thermal": run_thermal,
        "latency_num_predict_non_thinking": num_latency,
        "latency_num_predict_reasoning_capable": num_latency_thinking,
        "board_note": board_note,
        "models": [],
    }
    for model in models:
        try:
            show = client.show(model)
        except BenchmarkError:
            show = {}
        details = show.get("details") if isinstance(show.get("details"), dict) else {}
        meta["models"].append(
            {
                "model": model,
                "digest": client.digest(model),
                "family": details.get("family", ""),
                "parameter_size": details.get("parameter_size", ""),
                "quantization_level": details.get("quantization_level", ""),
                "think_policy": resolve_think_policy(model, think_requested),
                "latency_num_predict": latency_budget(
                    num_latency,
                    num_latency_thinking,
                    resolve_think_policy(model, think_requested),
                    model,
                ),
            }
        )
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rows: list[dict[str, Any]] = []
    long_prompt = (
        make_filler(filler_sentences)
        + " Given all of the above office-document context, "
        + SHORT_PROMPT
    )

    def record(
        model: str,
        test: str,
        run: int,
        metrics: dict[str, Any],
        detail: dict[str, Any],
        requested: int,
        think_policy: str,
        extra_warning: str | None = None,
    ) -> None:
        row = csv_row(model, test, run, mode, think_policy, metrics)
        rows.append(row)
        writer.writerow(row)
        csv_handle.flush()
        warnings = [
            value
            for value in (
                early_stop_warning(metrics, requested, early_fraction),
                answer_budget_warning(metrics, requested),
                extra_warning,
            )
            if value
        ]
        warning = "; ".join(warnings) or None
        write_jsonl(
            jsonl_path,
            {
                "timestamp": row["timestamp"],
                "category": "generation",
                "model": model,
                "test": test,
                "run": run,
                "bench_mode": mode,
                "think_policy": think_policy,
                "requested_tokens": requested,
                "warning": warning,
                "metrics": metrics,
                **detail,
            },
        )
        suffix = f" WARNING: {warning}" if warning else ""
        print(
            f"    {test}#{run}: wall={fmt(metrics.get('wall_duration_s'))}s "
            f"gen={fmt(metrics.get('tokens_per_second'))} tok/s "
            f"prompt={fmt(metrics.get('prompt_tokens_per_second'))} tok/s "
            f"Tmax={fmt(metrics.get('temp_max_c'), 1)}C "
            f"MemAvail-min={fmt(metrics.get('mem_available_min_mib'), 0)}MiB{suffix}"
        )

    with csv_path.open("w", newline="", encoding="utf-8") as csv_handle:
        writer = csv.DictWriter(csv_handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for model in models:
            think_policy = resolve_think_policy(model, think_requested)
            print(
                f"\n=== {short_name(model)} ({model}) | mode={mode} think={think_policy} ==="
            )

            try:
                if run_latency:
                    latency_tokens = latency_budget(
                        num_latency, num_latency_thinking, think_policy, model
                    )
                    client.ensure_unloaded(model)
                    metrics, _telemetry, detail = run_chat_stream(
                        client,
                        model,
                        prompt_variant(CHAT_PROMPT, 0),
                        latency_tokens,
                        mode,
                        think_policy,
                        keep_alive,
                        telemetry_interval,
                    )
                    record(
                        model,
                        "cold_chat",
                        1,
                        metrics,
                        detail,
                        latency_tokens,
                        think_policy,
                    )
                    for run in range(1, latency_repeats + 1):
                        metrics, _telemetry, detail = run_chat_stream(
                            client,
                            model,
                            prompt_variant(CHAT_PROMPT, run),
                            latency_tokens,
                            mode,
                            think_policy,
                            keep_alive,
                            telemetry_interval,
                        )
                        record(
                            model,
                            "warm_chat",
                            run,
                            metrics,
                            detail,
                            latency_tokens,
                            think_policy,
                        )

                # Warm model before throughput comparisons so model load does not
                # dominate the short-generation measurement.
                try:
                    run_generate(
                        client,
                        model,
                        prompt_variant(SHORT_PROMPT, 6),
                        32,
                        mode,
                        think_policy,
                        keep_alive,
                        telemetry_interval,
                    )
                except BenchmarkError as exc:
                    print(f"    warmup failed: {exc}", file=sys.stderr)

                for run in range(1, repeats + 1):
                    metrics, _telemetry, detail = run_generate(
                        client,
                        model,
                        prompt_variant(SHORT_PROMPT, run),
                        num_short,
                        mode,
                        think_policy,
                        keep_alive,
                        telemetry_interval,
                    )
                    record(
                        model, "short", run, metrics, detail, num_short, think_policy
                    )

                metrics, _telemetry, detail = run_generate(
                    client,
                    model,
                    prompt_variant(long_prompt, 0),
                    num_prefill,
                    mode,
                    think_policy,
                    keep_alive,
                    telemetry_interval,
                )
                record(model, "prefill", 1, metrics, detail, num_prefill, think_policy)

                if run_context:
                    previous_prompt_count = -1
                    for point in ctx_points:
                        prompt = (
                            make_filler(point)
                            + " Given all of the above context, "
                            + SHORT_PROMPT
                        )
                        metrics, _telemetry, detail = run_generate(
                            client,
                            model,
                            prompt_variant(prompt, 0),
                            num_context,
                            mode,
                            think_policy,
                            keep_alive,
                            telemetry_interval,
                        )
                        prompt_count = int(metrics.get("prompt_eval_count") or 0)
                        context_warning = context_truncation_warning(
                            previous_prompt_count, prompt_count
                        )
                        allocated = metrics.get("allocated_context")
                        context_note = None
                        if (
                            isinstance(allocated, int)
                            and prompt_count + num_context >= allocated
                        ):
                            context_note = (
                                f"ctx point approaches allocated context {allocated}"
                            )
                        if context_warning:
                            print(f"    WARNING: {context_warning}", file=sys.stderr)
                        if context_note:
                            print(f"    NOTE: {context_note}", file=sys.stderr)
                        detail["context_warning"] = context_warning
                        detail["context_note"] = context_note
                        record(
                            model,
                            f"ctx_{point}",
                            1,
                            metrics,
                            detail,
                            num_context,
                            think_policy,
                            context_warning,
                        )
                        previous_prompt_count = prompt_count

                if run_thermal:
                    window_tokens = max(1, num_long // max(1, thermal_windows))
                    first_tps: float | None = None
                    last_tps: float | None = None
                    for window in range(1, thermal_windows + 1):
                        metrics, _telemetry, detail = run_generate(
                            client,
                            model,
                            prompt_variant(SHORT_PROMPT, window),
                            window_tokens,
                            mode,
                            think_policy,
                            keep_alive,
                            telemetry_interval,
                        )
                        record(
                            model,
                            f"thermal_w{window}",
                            1,
                            metrics,
                            detail,
                            window_tokens,
                            think_policy,
                        )
                        tps = float(metrics.get("tokens_per_second") or 0)
                        if first_tps is None:
                            first_tps = tps
                        last_tps = tps
                    if first_tps and last_tps is not None:
                        drop = (first_tps - last_tps) / first_tps * 100.0
                        print(
                            f"    thermal decode drift: {first_tps:.2f} -> {last_tps:.2f} tok/s ({drop:+.1f}%)"
                        )

            finally:
                try:
                    client.ensure_unloaded(model)
                except BenchmarkError as exc:
                    print(f"WARNING: {exc}", file=sys.stderr)

    meta["finished_at"] = iso_now()
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("\n=== Summary ===")
    for model in models:
        model_rows = [
            row for row in rows if row["model"] == model and row["status"] == "ok"
        ]
        short_tps = [
            float(row["tokens_per_second"])
            for row in model_rows
            if row["test"] == "short" and row.get("tokens_per_second") not in (None, "")
        ]
        resources = aggregate_resource(model_rows)
        mean_tps = statistics.fmean(short_tps) if short_tps else 0.0
        max_temp = resources["temp_max_c"]
        thermal_flag = (
            " THERMAL-LIMIT" if max_temp is not None and max_temp >= 85.0 else ""
        )
        print(
            f"  {short_name(model):36s} short={mean_tps:7.2f} tok/s  "
            f"Tmax={fmt(max_temp, 1):>5s}C  MemAvail-min={fmt(resources['mem_available_min_mib'], 0):>6s}MiB  "
            f"swap-max={fmt(resources['swap_used_max_mib'], 0):>5s}MiB{thermal_flag}"
        )
    print(
        "\nResource headroom is informational on BC-250 unified memory; do not add VRAM/GTT/host figures as independent pools."
    )
    print(f"Results: {csv_path}\nDetails: {jsonl_path}\nMeta:    {meta_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BenchmarkError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
