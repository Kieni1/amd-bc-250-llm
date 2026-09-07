#!/usr/bin/env python3
"""Generation benchmark for BC-250 Ollama models.

The benchmark has two deliberate modes:

* neutral (default): one neutral SYSTEM override and deterministic sampling so
  different models see comparable instructions;
* production: no SYSTEM/sampling override, so the registered Modelfile is
  exercised as deployed.

Request shapes target Ollama 0.33.3.  The implementation is stdlib-only.
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
from datetime import datetime, timezone
from typing import Any

from benchmark_common import (
    DEFAULT_TELEMETRY_INTERVAL,
    STANDARD_OLLAMA_VERSION,
    BenchmarkError,
    OllamaClient,
    TelemetrySampler,
    append_result,
    benchmark_metadata,
    chronological_resource_aggregate,
    finalize_benchmark_metadata,
    fixture_metadata,
    prepare_result_dir,
    result_record,
    write_benchmark_metadata,
    write_result_summary,
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
    "swap_used_start_mib",
    "swap_used_max_mib",
    "swap_used_end_mib",
    "swap_peak_delta_mib",
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
    """Return omit|true|false|low|medium|high|max for Ollama 0.33.3."""
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
        # Ollama 0.33.3 GenerateRequest.System explicitly overrides the
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


def budget_diagnostics(
    metrics: dict[str, Any], requested: int, thinking: str
) -> list[str]:
    """Classify output exhaustion without inventing thinking exhaustion."""
    if not answer_budget_warning(metrics, requested):
        return []
    diagnostics = ["output-budget"]
    if thinking.strip():
        diagnostics.append("thinking-budget")
    return diagnostics


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
        # Automation/revalidation should never expand just because an operator added
        # more experimental models. Noninteractive discovery therefore benchmarks
        # production registrations only unless the caller names models explicitly or
        # deliberately opts into the full comparison pool.
        include_experiments = os.environ.get("BENCH_INCLUDE_EXPERIMENTS", "0").casefold() in {
            "1", "true", "yes", "y", "on"
        }
        if not include_experiments:
            production = [
                name for name in names
                if name.rsplit("/", 1)[-1].removesuffix(":latest").startswith("prod-")
            ]
            if production:
                return production
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


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="bc250-benchmark generation",
        description="BC-250 generation benchmark for Ollama 0.33.3.",
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
    parser.add_argument("--output-dir", help="result directory; must be empty")
    parser.add_argument(
        "--profile",
        choices=("compare", "edge", "thermal"),
        default="compare",
    )
    parser.add_argument(
        "--mode",
        choices=("neutral", "production"),
        default="neutral",
    )
    parser.add_argument(
        "--think",
        choices=("auto", "omit", "true", "false", "low", "medium", "high", "max"),
        default="auto",
    )
    args = parser.parse_args()

    profile = args.profile
    defaults = {
        "compare": {
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
        "edge": {
            "short": 256,
            "prefill": 24,
            "context": 96,
            "long": 2048,
            "latency": 64,
            "latency_thinking": 384,
            "repeats": 1,
            "latency_repeats": 1,
            "filler": 110,
            "ctx": [22, 88, 220],
        },
        "thermal": {
            "short": 256,
            "prefill": 16,
            "context": 64,
            "long": 3072,
            "latency": 64,
            "latency_thinking": 384,
            "repeats": 1,
            "latency_repeats": 1,
            "filler": 110,
            "ctx": [220],
        },
    }[profile]
    mode = args.mode
    think_requested = args.think

    num_short = int(os.environ.get("NUM_PREDICT_SHORT", defaults["short"]))
    num_prefill = int(os.environ.get("NUM_PREDICT_PREFILL", defaults["prefill"]))
    num_context = int(os.environ.get("NUM_PREDICT_CONTEXT", defaults["context"]))
    num_long = int(os.environ.get("NUM_PREDICT_LONG", defaults["long"]))
    num_warm_prefix = int(os.environ.get("NUM_PREDICT_WARM_PREFIX", "24"))
    warm_prefix_sentences = int(os.environ.get("WARM_PREFIX_SENTENCES", "352"))
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
        profile == "compare",
        interactive_prompt="Run context-capacity curve too?",
    )
    run_thermal = bool_setting(
        "RUN_THERMAL",
        profile == "thermal",
        interactive_prompt="Run sustained-load thermal test too?",
    )
    run_warm_prefix = bool_setting("RUN_WARM_PREFIX", False)
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

    paths = prepare_result_dir("generation", args.output_dir)
    csv_path, jsonl_path, meta_path = (
        paths.csv_export,
        paths.results_jsonl,
        paths.meta_json,
    )
    prompt_fixture = paths.fixtures_dir / "generation-prompts.json"
    prompt_fixture.write_text(
        json.dumps(
            {
                "neutral_system": NEUTRAL_SYSTEM,
                "short_prompt": SHORT_PROMPT,
                "chat_prompt": CHAT_PROMPT,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    model_metadata: list[dict[str, Any]] = []
    for model in models:
        try:
            show = client.show(model)
        except BenchmarkError:
            show = {}
        details = show.get("details") if isinstance(show.get("details"), dict) else {}
        model_metadata.append(
            {
                "model": model,
                "digest": client.digest(model),
                "family": details.get("family", ""),
                "parameter_size": details.get("parameter_size", ""),
                "quantization_level": details.get("quantization_level", ""),
                "runtime_url": client.base_url,
                "think_policy": resolve_think_policy(model, think_requested),
                "latency_num_predict": latency_budget(
                    num_latency,
                    num_latency_thinking,
                    resolve_think_policy(model, think_requested),
                    model,
                ),
            }
        )
    meta = benchmark_metadata(
        "generation",
        benchmark_version="8.0",
        models=model_metadata,
        fixtures=fixture_metadata(prompt_fixture),
        options={
            "profile": profile,
            "mode": mode,
            "think_mode_requested": think_requested,
            "telemetry_interval_s": telemetry_interval,
            "run_latency": run_latency,
            "run_context": run_context,
            "run_thermal": run_thermal,
            "run_warm_prefix": run_warm_prefix,
            "num_predict_short": num_short,
            "num_predict_prefill": num_prefill,
            "num_predict_context": num_context,
            "num_predict_long": num_long,
            "repeats": repeats,
            "latency_repeats": latency_repeats,
            "prefill_sentences": filler_sentences,
            "ctx_points": ctx_points,
            "keep_alive": keep_alive,
            "early_eos_fraction": early_fraction,
            "request_timeout_s": client.timeout,
            "thermal_windows": thermal_windows,
            "warm_prefix_sentences": warm_prefix_sentences,
            "warm_prefix_num_predict": num_warm_prefix,
            "latency_num_predict_non_thinking": num_latency,
            "latency_num_predict_reasoning_capable": num_latency_thinking,
            "prefill_cache_mode": "cold-runner",
            "board_note": board_note,
        },
        runtimes=[
            {
                "kind": "ollama",
                "url": client.base_url,
                "version": version,
                "package_standard_version": STANDARD_OLLAMA_VERSION,
            }
        ],
        neutral_system_sha256=(
            hashlib.sha256(NEUTRAL_SYSTEM.encode()).hexdigest()
            if mode == "neutral" else None
        ),
    )
    write_benchmark_metadata(meta_path, meta)

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
        diagnostics: list[str] = []
        if early_stop_warning(metrics, requested, early_fraction):
            diagnostics.append("early-stop")
        diagnostics.extend(
            budget_diagnostics(metrics, requested, str(detail.get("thinking") or ""))
        )
        if extra_warning:
            diagnostics.append("context-truncation")
        if float(metrics.get("seconds_ge_80c") or 0) > 0:
            diagnostics.append("thermal")
        request = detail.get("request") if isinstance(detail.get("request"), dict) else {}
        prompt_text = ""
        if isinstance(request.get("prompt"), str):
            prompt_text = request["prompt"]
        elif isinstance(request.get("messages"), list):
            prompt_text = "\n".join(
                str(item.get("content") or "")
                for item in request["messages"]
                if isinstance(item, dict)
            )
        request_meta = {
            key: value
            for key, value in request.items()
            if key not in {"prompt", "messages"}
        }
        append_result(
            jsonl_path,
            result_record(
                category="generation",
                model=model,
                case_id=f"{test}-{run}",
                result_type="measurement",
                outcome="pass",
                diagnostics=diagnostics,
                metrics=metrics,
                timestamp=row["timestamp"],
                test=test,
                run=run,
                bench_mode=mode,
                think_policy=think_policy,
                requested_tokens=requested,
                prompt_sha256=hashlib.sha256(prompt_text.encode()).hexdigest(),
                request=request_meta,
                response=detail.get("response", ""),
                thinking=detail.get("thinking", ""),
                notes=warnings,
            ),
        )
        suffix = f" WARNING: {warning}" if warning else ""
        print(
            f"    {test}#{run}: wall={fmt(metrics.get('wall_duration_s'))}s "
            f"gen={fmt(metrics.get('tokens_per_second'))} tok/s "
            f"prompt={fmt(metrics.get('prompt_tokens_per_second'))} tok/s "
            f"Tmax={fmt(metrics.get('temp_max_c'), 1)}C "
            f"MemAvail-min={fmt(metrics.get('mem_available_min_mib'), 0)}MiB{suffix}"
        )

    infra_failed = False
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

                # Ollama 0.33.0 made prompt-cache restore/reuse more reliable.
                # Start prefill/context measurements from an unloaded runner so
                # shared filler prefixes do not turn the curve into a cache-hit test.
                client.ensure_unloaded(model)
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
                        client.ensure_unloaded(model)
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

                if run_warm_prefix:
                    # This lane deliberately keeps the runner loaded and changes
                    # only the suffix after a byte-identical office-document prefix.
                    # It complements the cold-runner prefill/context curve rather
                    # than contaminating it with Ollama prefix-cache reuse.
                    shared_prefix = make_filler(warm_prefix_sentences)
                    client.ensure_unloaded(model)
                    cold_prompt = (
                        shared_prefix
                        + "\n\nQuestion A: State one concise risk when a policy document is outdated."
                    )
                    warm_prompt = (
                        shared_prefix
                        + "\n\nQuestion B: State one concise benefit of checking the current policy version."
                    )
                    metrics, _telemetry, detail = run_generate(
                        client, model, cold_prompt, num_warm_prefix, mode,
                        think_policy, keep_alive, telemetry_interval,
                    )
                    record(
                        model, "prefix_cold", 1, metrics, detail,
                        num_warm_prefix, think_policy,
                    )
                    metrics, _telemetry, detail = run_generate(
                        client, model, warm_prompt, num_warm_prefix, mode,
                        think_policy, keep_alive, telemetry_interval,
                    )
                    record(
                        model, "prefix_warm", 1, metrics, detail,
                        num_warm_prefix, think_policy,
                    )

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

            except BenchmarkError as exc:
                infra_failed = True
                error_row = {
                    "timestamp": iso_now(),
                    "model": model,
                    "label": short_name(model),
                    "test": "runtime",
                    "run": 0,
                    "status": "error",
                    "bench_mode": mode,
                    "think_policy": think_policy,
                }
                rows.append(error_row)
                writer.writerow(error_row)
                csv_handle.flush()
                append_result(
                    jsonl_path,
                    result_record(
                        category="generation",
                        model=model,
                        case_id="runtime",
                        result_type="measurement",
                        outcome="infra-fail",
                        failure_kinds=["runtime-api"],
                        error=str(exc),
                    ),
                )
                print(f"    ERROR: {exc}", file=sys.stderr)
            finally:
                try:
                    client.ensure_unloaded(model)
                except BenchmarkError as exc:
                    print(f"WARNING: {exc}", file=sys.stderr)

    finalize_benchmark_metadata(meta_path)

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
        resources = chronological_resource_aggregate(model_rows)
        mean_tps = statistics.fmean(short_tps) if short_tps else 0.0
        cv = (
            statistics.stdev(short_tps) / mean_tps * 100.0
            if len(short_tps) >= 2 and mean_tps > 0
            else 0.0
        )
        cold_rows = [row for row in model_rows if row["test"] == "cold_chat"]
        cold_wall = cold_rows[0].get("wall_duration_s") if cold_rows else None
        warm_rows = [row for row in model_rows if row["test"] == "warm_chat"]
        warm_answer = [
            float(row["time_to_first_answer_s"])
            for row in warm_rows
            if row.get("time_to_first_answer_s") not in (None, "")
        ]
        prefill_rows = [row for row in model_rows if row["test"] == "prefill"]
        prefill_tps = [
            float(row["prompt_tokens_per_second"])
            for row in prefill_rows
            if row.get("prompt_tokens_per_second") not in (None, "")
        ]
        max_temp = resources["temp_max_c"]
        p95_temp = resources["temp_p95_max_case_c"]
        thermal_flag = (
            " THERMAL-LIMIT" if max_temp is not None and max_temp >= 85.0 else ""
        )
        resident_gib = (
            None
            if resources["resident_size_bytes"] is None
            else resources["resident_size_bytes"] / (1024**3)
        )
        model_records = []
        if jsonl_path.exists():
            for line in jsonl_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("model") == model:
                    model_records.append(row)
        warning_counts: dict[str, int] = {}
        for record_row in model_records:
            for warning in record_row.get("diagnostics", []):
                warning_counts[str(warning)] = warning_counts.get(str(warning), 0) + 1
        warning_text = ",".join(
            f"{name}={count}" for name, count in sorted(warning_counts.items())
        ) or "none"
        print(
            f"  {short_name(model):32s} decode={mean_tps:7.2f} tok/s "
            f"CV={cv:4.1f}% cold={fmt(cold_wall, 1):>5s}s "
            f"warm-answer={fmt(statistics.fmean(warm_answer) if warm_answer else None, 2):>5s}s "
            f"prefill={fmt(statistics.fmean(prefill_tps) if prefill_tps else None, 1):>6s} tok/s"
        )
        print(
            f"    resident={fmt(resident_gib, 2):>5s}GiB "
            f"Mem-min={fmt(resources['mem_available_min_mib'], 0):>6s}MiB "
            f"swap={fmt(resources['swap_used_start_mib'], 0)}/"
            f"{fmt(resources['swap_used_max_mib'], 0)}/"
            f"{fmt(resources['swap_used_end_mib'], 0)}MiB "
            f"delta={fmt(resources['swap_peak_delta_mib'], 0)}MiB "
            f"max-case-p95/max={fmt(p95_temp, 1)}/{fmt(max_temp, 1)}C{thermal_flag}"
        )
        print(f"    warnings={warning_text}")
    print(
        "\nResource headroom is informational on BC-250 unified memory; "
        "VRAM/GTT counters are diagnostic, not additive pools."
    )
    _summary_json, summary_txt = write_result_summary(
        jsonl_path, category="generation"
    )
    print(
        f"Result directory: {paths.root}\nCanonical: {jsonl_path}\n"
        f"Summary: {summary_txt}\nCSV export: {csv_path}"
    )
    return 1 if infra_failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BenchmarkError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
