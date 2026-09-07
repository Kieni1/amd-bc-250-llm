#!/usr/bin/env python3
"""Explicit Ollama runtime/coexistence benchmarks for BC-250."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from benchmark_common import (
    STANDARD_OLLAMA_VERSION,
    BenchmarkError,
    OllamaClient,
    TelemetrySampler,
    append_result,
    benchmark_metadata,
    finalize_benchmark_metadata,
    fixture_metadata,
    prepare_result_dir,
    result_record,
    write_benchmark_metadata,
    write_result_summary,
)

DEFAULT_TIMEOUT = 900.0
DEFAULT_MAIN_URL = "http://127.0.0.1:11434"
DEFAULT_EMBED_URL = "http://127.0.0.1:11437"


def write_runtime_meta(
    paths: Any,
    category: str,
    *,
    runtime_models: list[tuple[str, str]],
    options: dict[str, Any],
    fixtures: list[Path] | None = None,
) -> None:
    models: list[dict[str, Any]] = []
    runtimes: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for url, model in runtime_models:
        client = OllamaClient(url)
        models.append({"model": model, "digest": client.digest(model), "runtime_url": client.base_url})
        if client.base_url not in seen_urls:
            version = client.version()
            runtimes.append({
                "kind": "ollama",
                "url": client.base_url,
                "version": version,
                "package_standard_version": STANDARD_OLLAMA_VERSION,
            })
            seen_urls.add(client.base_url)
    write_benchmark_metadata(
        paths.meta_json,
        benchmark_metadata(
            category,
            benchmark_version="8.0",
            models=models,
            fixtures=fixture_metadata(*(fixtures or [])),
            options=options,
            runtimes=runtimes,
        ),
    )


def finish(paths: Any, category: str) -> None:
    _summary_json, summary_txt = write_result_summary(paths.results_jsonl, category=category)
    finalize_benchmark_metadata(paths.meta_json)
    print(
        f"Result directory: {paths.root}\nCanonical: {paths.results_jsonl}\n"
        f"Summary: {summary_txt}"
    )

class Failure(RuntimeError):
    pass


class JsonClient:
    def __init__(self, base: str, token: str | None = None, timeout: float = DEFAULT_TIMEOUT):
        self.base = base.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, payload: Any | None = None) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(
            self.base + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise Failure(f"{method} {path}: HTTP {exc.code}: {detail}") from exc
        except OSError as exc:
            raise Failure(f"{method} {path}: {exc}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise Failure(f"{method} {path}: non-JSON response") from exc

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: Any) -> Any:
        return self.request("POST", path, payload)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)


def ns(value: Any) -> float | None:
    try:
        return float(value) / 1e9
    except (TypeError, ValueError):
        return None


def synthetic_prompt(sentences: int) -> str:
    body = "\n".join(
        f"Office record sentence {i} contains contract BC250-{i:04d}, a dated policy item, "
        "department, CHF amount, payment deadline and procedural qualification."
        for i in range(1, sentences + 1)
    )
    return body + "\nSummarize the operational pattern in two short sentences."


def ollama_unload(client: JsonClient, model: str) -> None:
    try:
        client.post(
            "/api/generate",
            {"model": model, "prompt": "", "stream": False, "keep_alive": 0},
        )
    except Failure:
        pass


def wait_ollama(client: JsonClient, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            client.get("/api/tags")
            return
        except Failure:
            time.sleep(2)
    raise Failure(f"Ollama at {client.base} did not become ready")


def parse_batches(raw: str) -> list[int | None]:
    batches: list[int | None] = []
    for item in raw.split(","):
        value = item.strip().casefold()
        if not value:
            continue
        if value == "auto":
            batches.append(None)
            continue
        number = int(value)
        if number < 1:
            raise ValueError("num_batch values must be positive or 'auto'")
        batches.append(number)
    if not batches:
        raise ValueError("at least one num_batch candidate is required")
    return batches


def cmd_num_batch(args: argparse.Namespace) -> int:
    paths = prepare_result_dir("num-batch", args.output_dir)
    prompt = synthetic_prompt(args.sentences)
    (paths.fixtures_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    client = JsonClient(args.main_url, timeout=args.timeout)
    batches = parse_batches(args.batches)
    write_runtime_meta(
        paths,
        "num-batch",
        runtime_models=[(args.main_url, model) for model in args.models],
        options={
            "candidates": ["auto" if value is None else value for value in batches],
            "num_ctx": args.num_ctx,
            "num_predict": args.num_predict,
            "sentences": args.sentences,
            "request_timeout_s": args.timeout,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        },
        fixtures=[paths.fixtures_dir / "prompt.txt"],
    )
    failed = False
    for model in args.models:
        for batch in batches:
            label = "auto" if batch is None else str(batch)
            options: dict[str, Any] = {
                "temperature": 0,
                "num_predict": args.num_predict,
                "num_ctx": args.num_ctx,
            }
            if batch is not None:
                options["num_batch"] = batch
            started = time.monotonic()
            try:
                wait_ollama(client)
                ollama_unload(client, model)
                time.sleep(1)
                response = client.post(
                    "/api/generate",
                    {
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "keep_alive": "2m",
                        "options": options,
                    },
                )
                metrics = {
                    "wall_s": time.monotonic() - started,
                    "load_s": ns(response.get("load_duration")),
                    "prompt_eval_count": response.get("prompt_eval_count"),
                    "prompt_eval_s": ns(response.get("prompt_eval_duration")),
                    "eval_count": response.get("eval_count"),
                    "eval_s": ns(response.get("eval_duration")),
                    "total_s": ns(response.get("total_duration")),
                }
                append_result(
                    paths.results_jsonl,
                    result_record(
                        category="num-batch",
                        model=model,
                        case_id=f"num-batch-{label}",
                        result_type="measurement",
                        outcome="pass",
                        metrics=metrics,
                        num_batch=label,
                        done_reason=response.get("done_reason", ""),
                    ),
                )
                print(
                    f"{model} num_batch={label}: "
                    f"prompt={metrics['prompt_eval_s']}s wall={metrics['wall_s']:.2f}s"
                )
            except Failure as exc:
                failed = True
                append_result(
                    paths.results_jsonl,
                    result_record(
                        category="num-batch",
                        model=model,
                        case_id=f"num-batch-{label}",
                        result_type="measurement",
                        outcome="infra-fail",
                        failure_kinds=["runtime-api"],
                        metrics={"wall_s": time.monotonic() - started},
                        num_batch=label,
                        error=str(exc),
                    ),
                )
                print(f"{model} num_batch={label}: ERROR {exc}", file=sys.stderr)
    finish(paths, "num-batch")
    return 1 if failed else 0


def cmd_concurrency(args: argparse.Namespace) -> int:
    paths = prepare_result_dir("concurrency", args.output_dir)
    main = JsonClient(args.main_url, timeout=args.timeout)
    embed_client = JsonClient(args.embed_url, timeout=args.timeout)
    prompt = synthetic_prompt(args.sentences)
    (paths.fixtures_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    write_runtime_meta(
        paths,
        "concurrency",
        runtime_models=[(args.main_url, args.model), (args.embed_url, args.embed_model)],
        options={
            "main_url": args.main_url,
            "embed_url": args.embed_url,
            "embed_requests": args.embed_requests,
            "sentences": args.sentences,
            "request_timeout_s": args.timeout,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        },
        fixtures=[paths.fixtures_dir / "prompt.txt"],
    )
    ollama_unload(main, args.model)

    def generation() -> dict[str, Any]:
        started = time.monotonic()
        response = main.post(
            "/api/generate",
            {
                "model": args.model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": "5m",
                "options": {
                    "temperature": 0,
                    "num_predict": 32,
                    "num_ctx": 32768,
                },
            },
        )
        return {
            "ok": True,
            "wall_s": time.monotonic() - started,
            "prompt_eval_count": response.get("prompt_eval_count"),
            "prompt_eval_s": ns(response.get("prompt_eval_duration")),
            "eval_s": ns(response.get("eval_duration")),
        }

    def embeddings() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index in range(args.embed_requests):
            started = time.monotonic()
            response = embed_client.post(
                "/api/embed",
                {
                    "model": args.embed_model,
                    "input": [f"Query: concurrent embedding request {index}"],
                    "keep_alive": "10m",
                },
            )
            rows.append(
                {
                    "index": index,
                    "wall_s": time.monotonic() - started,
                    "ok": bool(response.get("embeddings")),
                }
            )
            time.sleep(0.25)
        return rows

    sampler = TelemetrySampler().start()
    started = time.monotonic()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            generation_future = pool.submit(generation)
            embedding_future = pool.submit(embeddings)
            generation_result = generation_future.result()
            embedding_results = embedding_future.result()
        telemetry = sampler.stop()
    except Failure as exc:
        telemetry = sampler.stop()
        append_result(
            paths.results_jsonl,
            result_record(
                category="concurrency",
                model=args.model,
                case_id="main-plus-embedding",
                result_type="measurement",
                outcome="infra-fail",
                failure_kinds=["runtime-api"],
                metrics={
                    "wall_s": time.monotonic() - started,
                    "mem_available_min_mib": telemetry.get("mem_available_min_mib"),
                    "swap_peak_delta_mib": telemetry.get("swap_peak_delta_mib"),
                },
                embed_model=args.embed_model,
                error=str(exc),
                telemetry=telemetry,
            ),
        )
        finish(paths, "concurrency")
        return 1

    embeddings_ok = all(row["ok"] for row in embedding_results)
    ok = bool(generation_result["ok"] and embeddings_ok)
    append_result(
        paths.results_jsonl,
        result_record(
            category="concurrency",
            model=args.model,
            case_id="main-plus-embedding",
            result_type="measurement",
            outcome="pass" if ok else "infra-fail",
            failure_kinds=[] if ok else ["runtime-api"],
            checks={"generation": generation_result["ok"], "embeddings": embeddings_ok},
            metrics={
                "wall_s": time.monotonic() - started,
                "generation_wall_s": generation_result["wall_s"],
                "embedding_wall_s_mean": (
                    sum(row["wall_s"] for row in embedding_results)
                    / len(embedding_results)
                    if embedding_results
                    else 0.0
                ),
                "mem_available_min_mib": telemetry.get("mem_available_min_mib"),
                "swap_used_start_mib": telemetry.get("swap_used_start_mib"),
                "swap_used_max_mib": telemetry.get("swap_used_max_mib"),
                "swap_used_end_mib": telemetry.get("swap_used_end_mib"),
                "swap_peak_delta_mib": telemetry.get("swap_peak_delta_mib"),
                "temp_max_c": telemetry.get("temp_max_c"),
            },
            embed_model=args.embed_model,
            generation=generation_result,
            embeddings=embedding_results,
            telemetry=telemetry,
        ),
    )
    finish(paths, "concurrency")
    return 0 if ok else 1

def add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", help="result directory; must be empty")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="bc250-benchmark",
        description="Explicit BC-250 Ollama runtime/coexistence benchmarks.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    num_batch = sub.add_parser("num-batch", help="compare explicit Ollama num_batch candidates")
    num_batch.add_argument("models", nargs="+", help="registered model names")
    num_batch.add_argument("--main-url", default=DEFAULT_MAIN_URL)
    num_batch.add_argument("--batches", default="auto,512,256,128")
    num_batch.add_argument("--sentences", type=int, default=704)
    num_batch.add_argument("--num-predict", type=int, default=16)
    num_batch.add_argument("--num-ctx", type=int, default=32768)
    num_batch.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    add_output(num_batch)
    num_batch.set_defaults(func=cmd_num_batch)

    concurrency = sub.add_parser(
        "concurrency", help="main-generation plus embedding-lane coexistence"
    )
    concurrency.add_argument("model")
    concurrency.add_argument("embed_model")
    concurrency.add_argument("--main-url", default=DEFAULT_MAIN_URL)
    concurrency.add_argument("--embed-url", default=DEFAULT_EMBED_URL)
    concurrency.add_argument("--sentences", type=int, default=352)
    concurrency.add_argument("--embed-requests", type=int, default=8)
    concurrency.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    add_output(concurrency)
    concurrency.set_defaults(func=cmd_concurrency)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BenchmarkError, Failure, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
