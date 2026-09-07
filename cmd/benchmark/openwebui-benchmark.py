#!/usr/bin/env python3
"""Explicit Open WebUI RAG/tuning benchmarks with verified restoration."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

from benchmark_common import (
    STANDARD_OLLAMA_VERSION,
    BenchmarkError,
    OllamaClient,
    append_result,
    benchmark_metadata,
    finalize_active_infrastructure_failure,
    finalize_benchmark_metadata,
    fixture_metadata,
    prepare_result_dir,
    result_record,
    write_benchmark_metadata,
    write_result_summary,
)

DEFAULT_TIMEOUT = 900.0
DEFAULT_OWUI_URL = "http://127.0.0.1:3000"
DEFAULT_MAIN_URL = "http://127.0.0.1:11434"
DEFAULT_EMBED_URL = "http://127.0.0.1:11437"
SYSCTX_DROPIN = Path(
    "/etc/containers/systemd/open-webui.container.d/95-bc250-benchmark.conf"
)


def simple_meta(paths: Any, category: str, **fields: Any) -> None:
    model = str(fields.get("model") or "")
    model_runtime_url = str(fields.get("model_runtime_url") or DEFAULT_MAIN_URL)
    options = {key: value for key, value in fields.items() if key != "model_runtime_url"}
    models: list[dict[str, Any]] = []
    runtimes: list[dict[str, Any]] = [
        {"kind": "open-webui", "url": str(fields.get("url") or DEFAULT_OWUI_URL)}
    ]
    if model:
        try:
            timeout = float(fields.get("request_timeout_s") or DEFAULT_TIMEOUT)
            ollama = OllamaClient(model_runtime_url, timeout)
            version = ollama.version()
            models.append(
                {
                    "model": model,
                    "digest": ollama.digest(model),
                    "runtime_url": ollama.base_url,
                }
            )
            runtimes.append(
                {
                    "kind": "ollama",
                    "url": ollama.base_url,
                    "version": version,
                    "package_standard_version": STANDARD_OLLAMA_VERSION,
                }
            )
        except BenchmarkError:
            models.append(
                {"model": model, "digest": "", "runtime_url": model_runtime_url}
            )
    fixtures = [
        Path(value)
        for key, value in fields.items()
        if key.endswith("_fixture") and value
    ]
    write_benchmark_metadata(
        paths.meta_json,
        benchmark_metadata(
            category,
            benchmark_version="8.0",
            models=models,
            fixtures=fixture_metadata(*fixtures),
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


class RestorationFailure(Failure):
    """Temporary application state could not be proven restored/removed."""


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


def token_from(path: str) -> str:
    token = Path(path).read_text(encoding="utf-8").strip()
    if not token:
        raise Failure("Open WebUI API key file is empty")
    return token


def owui_client(args: argparse.Namespace) -> JsonClient:
    return JsonClient(args.url, token_from(args.token_file), timeout=args.timeout)


def require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Failure(f"{context}: expected JSON object")
    return value


def embedding_config(data: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "RAG_EMBEDDING_ENGINE",
        "RAG_EMBEDDING_MODEL",
        "RAG_EMBEDDING_BATCH_SIZE",
        "ENABLE_ASYNC_EMBEDDING",
        "RAG_EMBEDDING_CONCURRENT_REQUESTS",
        "ollama_config",
    )
    return {key: data.get(key) for key in keys}


def rag_config(data: dict[str, Any]) -> dict[str, Any]:
    return {"CHUNK_MIN_SIZE_TARGET": data.get("CHUNK_MIN_SIZE_TARGET")}


def multipart_upload(client: JsonClient, path: Path, knowledge_id: str) -> dict[str, Any]:
    content = path.read_bytes()
    metadata = json.dumps(
        {"knowledge_id": knowledge_id, "file_hash": hashlib.sha256(content).hexdigest()}
    )
    boundary = "----bc250-bench-" + uuid.uuid4().hex
    mime = mimetypes.guess_type(path.name)[0] or "text/markdown"
    body = b"".join(
        [
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"'
                f"\r\n\r\n{metadata}\r\n"
            ).encode(),
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="{path.name}"\r\nContent-Type: {mime}\r\n\r\n'
            ).encode(),
            content,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
        "Authorization": f"Bearer {client.token}",
    }
    req = urllib.request.Request(
        client.base + "/api/v1/files/?process=true&process_in_background=false",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=client.timeout) as response:
            result = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise Failure(f"upload: HTTP {exc.code}: {detail}") from exc
    result = require_object(result, "Open WebUI upload")
    file_id = result.get("id")
    if not file_id:
        raise Failure("upload returned no file id")
    status = require_object(
        client.get(f"/api/v1/files/{file_id}/process/status"),
        "Open WebUI file processing status",
    )
    if status.get("status") != "completed":
        raise Failure(f"file processing status={status!r}")
    return result


def create_kb(client: JsonClient, name: str) -> dict[str, Any]:
    kb = require_object(
        client.post(
            "/api/v1/knowledge/create",
            {
                "name": name,
                "description": (
                    "Temporary BC-250 benchmark knowledge base; safe to delete."
                ),
            },
        ),
        "Open WebUI knowledge create",
    )
    if not kb.get("id"):
        raise Failure("knowledge create returned no id")
    return kb


def _is_not_found(exc: Failure) -> bool:
    return "HTTP 404" in str(exc)


def knowledge_present(client: JsonClient, name: str, kb_id: str) -> bool:
    result = require_object(
        client.get(f"/api/v1/knowledge/search?query={quote(name)}&page=1"),
        "Open WebUI knowledge search",
    )
    items = result.get("items", [])
    if not isinstance(items, list):
        raise Failure("Open WebUI knowledge search: invalid items")
    return any(
        isinstance(item, dict) and str(item.get("id") or "") == kb_id
        for item in items
    )


def file_present(client: JsonClient, file_id: str) -> bool:
    try:
        client.get(f"/api/v1/files/{file_id}/process/status")
    except Failure as exc:
        if _is_not_found(exc):
            return False
        raise
    return True


def cleanup_kb(
    client: JsonClient,
    kb_id: str | None,
    file_id: str | None,
    kb_name: str | None = None,
) -> None:
    """Delete temporary OWUI state and prove it disappeared."""
    failures: list[str] = []
    if kb_id:
        try:
            client.delete(f"/api/v1/knowledge/{kb_id}/delete")
            if kb_name:
                for _ in range(5):
                    if not knowledge_present(client, kb_name, kb_id):
                        break
                    time.sleep(0.2)
                else:
                    failures.append(f"knowledge {kb_id} still present after delete")
        except Failure as exc:
            failures.append(str(exc))
    if file_id:
        try:
            client.delete(f"/api/v1/files/{file_id}")
            for _ in range(5):
                if not file_present(client, file_id):
                    break
                time.sleep(0.2)
            else:
                failures.append(f"file {file_id} still present after delete")
        except Failure as exc:
            failures.append(str(exc))
    if failures:
        raise RestorationFailure(
            "temporary Open WebUI cleanup failed: " + "; ".join(failures)
        )


def restore_config(
    client: JsonClient,
    paths: Any,
    category: str,
    model: str,
    endpoint: str,
    payload: dict[str, Any],
    read_endpoint: str,
    extractor: Callable[[dict[str, Any]], dict[str, Any]],
) -> bool:
    """Restore one OWUI config object and verify it by readback."""
    try:
        client.post(endpoint, payload)
        restored = extractor(
            require_object(client.get(read_endpoint), f"{category} restoration readback")
        )
        if restored != payload:
            raise Failure(
                f"{category} restoration mismatch: expected={payload!r} actual={restored!r}"
            )
    except Failure as exc:
        append_result(
            paths.results_jsonl,
            result_record(
                category=category,
                model=model,
                case_id="restoration",
                result_type="measurement",
                outcome="infra-fail",
                failure_kinds=["restoration"],
                error=str(exc),
            ),
        )
        return False
    return True


def chat(
    client: JsonClient,
    model: str,
    kb_id: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    return client.post(
        "/api/chat/completions",
        {
            "model": model,
            "messages": messages,
            "files": [{"type": "collection", "id": kb_id, "status": "processed"}],
            "stream": False,
            "background_tasks": {
                "title_generation": False,
                "tags_generation": False,
                "follow_up_generation": False,
            },
        },
    )


def response_text(result: dict[str, Any]) -> str:
    choices = result.get("choices") if isinstance(result, dict) else None
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    return str(message.get("content") or "")


def usage_row(result: dict[str, Any]) -> dict[str, Any]:
    usage = result.get("usage") if isinstance(result, dict) else {}
    if not isinstance(usage, dict):
        usage = {}
    keys = (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_token/s",
        "response_token/s",
        "total_duration",
        "load_duration",
        "prompt_eval_count",
        "prompt_eval_duration",
        "eval_count",
        "eval_duration",
    )
    return {key: usage.get(key) for key in keys}


def source_meta(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    keys = ("sources", "citations", "context_chunks_with_source", "context")
    return {key: result[key] for key in keys if result.get(key)}


def make_batch_doc(path: Path) -> None:
    parts = ["# BC-250 embedding batch fixture\n"]
    for index in range(1, 181):
        parts.append(
            f"## Record {index}\nContract BAT-{index:04d} belongs to Department "
            f"{index % 11}, has a payment deadline of {10 + index % 20} days, amount "
            f"CHF {1000 + index * 7}.00, and procedure code PROC-{index % 17:02d}. "
            "This paragraph exists to create realistic local embedding work without "
            "external downloads.\n"
        )
    path.write_text("\n".join(parts), encoding="utf-8")


def make_chunk_doc(path: Path) -> None:
    path.write_text(
        """# Office handbook

## Zurich lease
The current Zurich lease reference is ZH-CURRENT-7721. The notice period is six months.

## Archive note
The archived Zurich lease reference ZH-OLD-6610 is superseded and must not be used for current notices.

## Invoice 2026-0441
Invoice reference INV-2026-0441 is CHF 18,740.00 and is due within 30 days.

## Invoice 2026-0447
Invoice reference INV-2026-0447 is CHF 18,470.00 and is due within 14 days.

## Procurement
Purchase order PO-88217 requires two approvals above CHF 25,000.

## Privacy
Confidential personnel documents may not be copied to public collections.
""",
        encoding="utf-8",
    )


def make_sysctx_doc(path: Path) -> None:
    filler = " ".join(
        ["The operational appendix contains stable office wording for cache measurement."]
        * 350
    )
    path.write_text(
        "# Contract cache fixture\n\n"
        "The active contract reference is CACHE-ZH-9917. The notice period is six months. "
        "The payment deadline is 30 days. The responsible unit is Facility Operations. "
        "The archived reference CACHE-ZH-1204 must not be used.\n\n"
        f"## Stable appendix\n{filler}\n",
        encoding="utf-8",
    )


def rag_turns() -> list[tuple[str, list[str]]]:
    return [
        (
            (
                "According to the document, what are the active contract reference and notice "
                "period? Answer briefly with a citation."
            ),
            ["CACHE-ZH-9917", "six"],
        ),
        (
            (
                "And what is the payment deadline and responsible unit? Answer briefly with a "
                "citation."
            ),
            ["30", "Facility Operations"],
        ),
        (
            "Repeat only the active reference and payment deadline, with a citation.",
            ["CACHE-ZH-9917", "30"],
        ),
    ]


def run_owui_rag_case(
    client: JsonClient,
    paths: Any,
    model: str,
    label: str,
    category: str = "owui-rag",
    result_type: str = "qualification",
) -> int:
    document = paths.fixtures_dir / f"rag-{label}.md"
    make_sysctx_doc(document)
    kb_id = file_id = None
    kb_name = f"BC250 benchmark {label} {uuid.uuid4().hex[:8]}"
    failures = 0
    try:
        kb = create_kb(client, kb_name)
        kb_id = str(kb["id"])
        uploaded = multipart_upload(client, document, kb_id)
        file_id = str(uploaded["id"])
        messages: list[dict[str, str]] = []
        for index, (question, required) in enumerate(rag_turns(), start=1):
            messages.append({"role": "user", "content": question})
            started = time.monotonic()
            result = chat(client, model, kb_id, messages)
            wall = time.monotonic() - started
            text = response_text(result)
            fact_ok = all(value.casefold() in text.casefold() for value in required)
            source_ok = bool(source_meta(result))
            archive_leak = "CACHE-ZH-1204" in text
            ok = fact_ok and source_ok and not archive_leak
            failures += int(not ok)
            failure_kinds: list[str] = []
            if not fact_ok:
                failure_kinds.append("answer")
            if not source_ok:
                failure_kinds.append("citation")
            if archive_leak:
                failure_kinds.append("source-leakage")
            append_result(
                paths.results_jsonl,
                result_record(
                    category=category,
                    model=model,
                    case_id=f"{label}-turn-{index}",
                    result_type=result_type,
                    outcome="pass" if ok else "quality-fail",
                    failure_kinds=failure_kinds,
                    checks={
                        "answer": fact_ok,
                        "citation": source_ok,
                        "no_archive_leak": not archive_leak,
                    },
                    metrics={"wall_s": wall, **usage_row(result)},
                    setting=label,
                    required=required,
                    response=text,
                    source_meta=source_meta(result),
                ),
            )
            messages.append({"role": "assistant", "content": text})
    finally:
        cleanup_kb(client, kb_id, file_id, kb_name)
    return failures


def cmd_owui_rag(args: argparse.Namespace) -> int:
    paths = prepare_result_dir("owui-rag", args.output_dir)
    client = owui_client(args)
    simple_meta(
        paths,
        "owui-rag",
        url=args.url,
        model=args.model,
        request_timeout_s=getattr(args, "timeout", DEFAULT_TIMEOUT),
    )
    try:
        failures = run_owui_rag_case(client, paths, args.model, "packaged")
    except Failure as exc:
        failure_kind = "restoration" if isinstance(exc, RestorationFailure) else "runtime-api"
        append_result(
            paths.results_jsonl,
            result_record(
                category="owui-rag",
                model=args.model,
                case_id="packaged-runtime",
                result_type="qualification",
                outcome="infra-fail",
                failure_kinds=[failure_kind],
                error=str(exc),
            ),
        )
        finish(paths, "owui-rag")
        return 1
    finish(paths, "owui-rag")
    return 3 if failures else 0


def cmd_owui_embedding_batch(args: argparse.Namespace) -> int:
    paths = prepare_result_dir("owui-embedding-batch", args.output_dir)
    client = owui_client(args)
    original = embedding_config(
        require_object(
            client.get("/api/v1/retrieval/embedding"),
            "Open WebUI embedding configuration",
        )
    )
    model = str(original.get("RAG_EMBEDDING_MODEL") or "open-webui")
    document = paths.fixtures_dir / "embedding-batch.md"
    make_batch_doc(document)
    simple_meta(
        paths,
        "owui-embedding-batch",
        url=args.url,
        model=model,
        model_runtime_url=DEFAULT_EMBED_URL,
        original_config=original,
        batches=args.batches,
        request_timeout_s=getattr(args, "timeout", DEFAULT_TIMEOUT),
    )
    failed = False
    try:
        for batch in args.batches:
            config = dict(original)
            config["RAG_EMBEDDING_BATCH_SIZE"] = batch
            client.post("/api/v1/retrieval/embedding/update", config)
            kb_id = file_id = None
            kb_name = f"BC250 embedding batch {batch} {uuid.uuid4().hex[:8]}"
            started = time.monotonic()
            try:
                kb = create_kb(client, kb_name)
                kb_id = str(kb["id"])
                uploaded = multipart_upload(client, document, kb_id)
                file_id = str(uploaded["id"])
                append_result(
                    paths.results_jsonl,
                    result_record(
                        category="owui-embedding-batch",
                        model=model,
                        case_id=f"batch-{batch}",
                        result_type="measurement",
                        outcome="pass",
                        metrics={"process_wall_s": time.monotonic() - started},
                        batch=batch,
                    ),
                )
            except Failure as exc:
                failed = True
                append_result(
                    paths.results_jsonl,
                    result_record(
                        category="owui-embedding-batch",
                        model=model,
                        case_id=f"batch-{batch}",
                        result_type="measurement",
                        outcome="infra-fail",
                        failure_kinds=["runtime-api"],
                        metrics={"process_wall_s": time.monotonic() - started},
                        batch=batch,
                        error=str(exc),
                    ),
                )
            finally:
                try:
                    cleanup_kb(client, kb_id, file_id, kb_name)
                except Failure as exc:
                    failed = True
                    append_result(
                        paths.results_jsonl,
                        result_record(
                            category="owui-embedding-batch",
                            model=model,
                            case_id=f"batch-{batch}-cleanup",
                            result_type="measurement",
                            outcome="infra-fail",
                            failure_kinds=["restoration"],
                            error=str(exc),
                        ),
                    )
    finally:
        restored = restore_config(
            client,
            paths,
            "owui-embedding-batch",
            model,
            "/api/v1/retrieval/embedding/update",
            original,
            "/api/v1/retrieval/embedding",
            embedding_config,
        )
        failed = failed or not restored
    finish(paths, "owui-embedding-batch")
    return 1 if failed else 0


def chunk_cases() -> list[tuple[str, list[str]]]:
    return [
        (
            "What is the current Zurich lease reference and notice period?",
            ["ZH-CURRENT-7721", "six"],
        ),
        (
            "What amount and deadline belong to invoice INV-2026-0447?",
            ["18,470", "14"],
        ),
        (
            "Which invoice is CHF 18,740.00 and what is its deadline?",
            ["INV-2026-0441", "30"],
        ),
        ("What approval rule applies above CHF 25,000?", ["two", "25,000"]),
    ]


def cmd_owui_chunk_min(args: argparse.Namespace) -> int:
    paths = prepare_result_dir("owui-chunk-min", args.output_dir)
    client = owui_client(args)
    original = rag_config(
        require_object(
            client.get("/api/v1/retrieval/config"),
            "Open WebUI retrieval configuration",
        )
    )
    document = paths.fixtures_dir / "chunk-min.md"
    make_chunk_doc(document)
    simple_meta(
        paths,
        "owui-chunk-min",
        url=args.url,
        model=args.model,
        original_config=original,
        targets=args.targets,
        request_timeout_s=getattr(args, "timeout", DEFAULT_TIMEOUT),
    )
    infra_failed = False
    quality_failed = False
    try:
        for target in args.targets:
            client.post(
                "/api/v1/retrieval/config/update", {"CHUNK_MIN_SIZE_TARGET": target}
            )
            kb_id = file_id = None
            kb_name = f"BC250 chunk {target} {uuid.uuid4().hex[:8]}"
            try:
                kb = create_kb(client, kb_name)
                kb_id = str(kb["id"])
                uploaded = multipart_upload(client, document, kb_id)
                file_id = str(uploaded["id"])
                for index, (question, required) in enumerate(chunk_cases(), start=1):
                    started = time.monotonic()
                    result = chat(
                        client,
                        args.model,
                        kb_id,
                        [
                            {
                                "role": "user",
                                "content": question
                                + " Answer briefly and cite the supplied source.",
                            }
                        ],
                    )
                    wall = time.monotonic() - started
                    text = response_text(result)
                    answer_ok = all(
                        needle.casefold() in text.casefold() for needle in required
                    )
                    citation_ok = bool(source_meta(result))
                    ok = answer_ok and citation_ok
                    quality_failed = quality_failed or not ok
                    failures = []
                    if not answer_ok:
                        failures.append("answer")
                    if not citation_ok:
                        failures.append("citation")
                    append_result(
                        paths.results_jsonl,
                        result_record(
                            category="owui-chunk-min",
                            model=args.model,
                            case_id=f"chunk-{target}-case-{index}",
                            result_type="measurement",
                            outcome="pass" if ok else "quality-fail",
                            failure_kinds=failures,
                            checks={"answer": answer_ok, "citation": citation_ok},
                            metrics={"wall_s": wall, **usage_row(result)},
                            chunk_min_size_target=target,
                            question=question,
                            required=required,
                            response=text,
                            source_meta=source_meta(result),
                        ),
                    )
            except Failure as exc:
                infra_failed = True
                append_result(
                    paths.results_jsonl,
                    result_record(
                        category="owui-chunk-min",
                        model=args.model,
                        case_id=f"chunk-{target}-runtime",
                        result_type="measurement",
                        outcome="infra-fail",
                        failure_kinds=["runtime-api"],
                        chunk_min_size_target=target,
                        error=str(exc),
                    ),
                )
            finally:
                try:
                    cleanup_kb(client, kb_id, file_id, kb_name)
                except Failure as exc:
                    infra_failed = True
                    append_result(
                        paths.results_jsonl,
                        result_record(
                            category="owui-chunk-min",
                            model=args.model,
                            case_id=f"chunk-{target}-cleanup",
                            result_type="measurement",
                            outcome="infra-fail",
                            failure_kinds=["restoration"],
                            error=str(exc),
                        ),
                    )
    finally:
        restored = restore_config(
            client,
            paths,
            "owui-chunk-min",
            args.model,
            "/api/v1/retrieval/config/update",
            original,
            "/api/v1/retrieval/config",
            rag_config,
        )
        infra_failed = infra_failed or not restored
    finish(paths, "owui-chunk-min")
    if infra_failed:
        return 1
    return 3 if quality_failed else 0


def command_ok(*args: str) -> str:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise Failure(f"{' '.join(args)} failed: {detail}")
    return result.stdout


def current_sysctx() -> str:
    output = command_ok(
        "podman",
        "inspect",
        "open-webui",
        "--format",
        "{{range .Config.Env}}{{println .}}{{end}}",
    )
    values = [
        line.split("=", 1)[1]
        for line in output.splitlines()
        if line.startswith("RAG_SYSTEM_CONTEXT=")
    ]
    return values[-1] if values else ""


def wait_owui(url: str, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/", timeout=4):
                return
        except OSError:
            time.sleep(1)
    raise Failure("Open WebUI did not become ready after restart")


def sysctx_restoration_matches(original: str, restored: str) -> bool:
    """Compare the effective system-context state, including an absent value."""
    return restored.casefold() == original.casefold()


def set_sysctx(value: str, url: str) -> None:
    SYSCTX_DROPIN.parent.mkdir(parents=True, exist_ok=True)
    SYSCTX_DROPIN.write_text(
        f"[Container]\nEnvironment=RAG_SYSTEM_CONTEXT={value}\n",
        encoding="utf-8",
    )
    os.chmod(SYSCTX_DROPIN, 0o644)
    command_ok("systemctl", "daemon-reload")
    command_ok("systemctl", "restart", "open-webui.service")
    wait_owui(url)
    actual = current_sysctx().casefold()
    if actual != value.casefold():
        raise Failure(f"RAG_SYSTEM_CONTEXT expected={value} actual={actual or 'missing'}")


def cmd_owui_system_context(args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        raise Failure("owui-system-context requires root")
    paths = prepare_result_dir("owui-system-context", args.output_dir)
    client = owui_client(args)
    backup = paths.root / "original-sysctx-dropin.conf"
    dropin_existed = SYSCTX_DROPIN.exists()
    if dropin_existed:
        shutil.copy2(SYSCTX_DROPIN, backup)
    original_value = current_sysctx()
    simple_meta(
        paths,
        "owui-system-context",
        url=args.url,
        model=args.model,
        original_value=original_value,
        benchmark_dropin_preexisted=dropin_existed,
        request_timeout_s=getattr(args, "timeout", DEFAULT_TIMEOUT),
    )
    infra_failed = False
    quality_failed = False
    restore_error: Failure | None = None
    try:
        for value in ("false", "true"):
            try:
                set_sysctx(value, args.url)
                failures = run_owui_rag_case(
                    client,
                    paths,
                    args.model,
                    value,
                    category="owui-system-context",
                    result_type="measurement",
                )
                quality_failed = quality_failed or failures > 0
            except Failure as exc:
                infra_failed = True
                append_result(
                    paths.results_jsonl,
                    result_record(
                        category="owui-system-context",
                        model=args.model,
                        case_id=f"{value}-runtime",
                        result_type="measurement",
                        outcome="infra-fail",
                        failure_kinds=[
                            "restoration"
                            if isinstance(exc, RestorationFailure)
                            else "runtime-api"
                        ],
                        setting=value,
                        error=str(exc),
                    ),
                )
                break
    finally:
        try:
            if dropin_existed:
                shutil.copy2(backup, SYSCTX_DROPIN)
            else:
                SYSCTX_DROPIN.unlink(missing_ok=True)
            command_ok("systemctl", "daemon-reload")
            command_ok("systemctl", "restart", "open-webui.service")
            wait_owui(args.url)
            restored = current_sysctx()
            if not sysctx_restoration_matches(original_value, restored):
                raise RestorationFailure(
                    "Open WebUI system-context restoration mismatch: "
                    f"expected={original_value} actual={restored or 'missing'}"
                )
        except Failure as exc:
            restore_error = exc
    if restore_error is not None:
        append_result(
            paths.results_jsonl,
            result_record(
                category="owui-system-context",
                model=args.model,
                case_id="restoration",
                result_type="measurement",
                outcome="infra-fail",
                failure_kinds=["restoration"],
                error=str(restore_error),
            ),
        )
        infra_failed = True
    finish(paths, "owui-system-context")
    if infra_failed:
        return 1
    return 3 if quality_failed else 0


def add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", help="result directory; must be empty")


def add_owui(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default=DEFAULT_OWUI_URL)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    add_output(parser)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="bc250-benchmark",
        description="Explicit Open WebUI RAG/tuning benchmarks with restoration.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    owui_rag = sub.add_parser("owui-rag", help="qualify the currently packaged OWUI RAG path")
    add_owui(owui_rag)
    owui_rag.add_argument("model")
    owui_rag.set_defaults(func=cmd_owui_rag)

    embedding_batch = sub.add_parser(
        "owui-embedding-batch", help="compare OWUI embedding batch sizes"
    )
    add_owui(embedding_batch)
    embedding_batch.add_argument("--batches", type=int, nargs="+", default=[1, 4, 8, 16])
    embedding_batch.set_defaults(func=cmd_owui_embedding_batch)

    chunk_min = sub.add_parser("owui-chunk-min", help="compare OWUI chunk minimum sizes")
    add_owui(chunk_min)
    chunk_min.add_argument("model")
    chunk_min.add_argument("--targets", type=int, nargs="+", default=[0, 500, 750, 1000])
    chunk_min.set_defaults(func=cmd_owui_chunk_min)

    system_context = sub.add_parser(
        "owui-system-context",
        help="root-only false/true RAG_SYSTEM_CONTEXT A/B with restoration",
    )
    add_owui(system_context)
    system_context.add_argument("model")
    system_context.set_defaults(func=cmd_owui_system_context)

    args = parser.parse_args()
    return int(args.func(args))


def entrypoint() -> int:
    try:
        return main()
    except KeyboardInterrupt as exc:
        finalize_active_infrastructure_failure(exc, failure_kind="interrupted")
        print("ERROR: benchmark interrupted.", file=sys.stderr)
        return 130
    except (BenchmarkError, Failure, OSError, ValueError) as exc:
        finalize_active_infrastructure_failure(exc)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(entrypoint())
