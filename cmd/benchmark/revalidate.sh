#!/usr/bin/env bash
# BC-250 package revalidation harness v3.5
#
# Intended target: bc250-llm-server 0.10.0 on Fedora 44; release suffix is not hard-coded.
# `start` launches a systemd worker that spans reboots. The kernel lane dynamically
# optionally compares the running/default kernel's TTM-only baseline with the historical
# full profile, then restores its exact arguments after two normal reboots. Per-phase reports are
# retained; temporary OWUI/RAG and exclusive-agent state is restored on every exit.
# The supplied OWUI credential remains under /run and is never included in reports.
set -Eeuo pipefail
umask 0077

HARNESS_VERSION=3.5
TARGET_VERSION=0.10.0
TARGET_RELEASE_PREFIX=${TARGET_RELEASE_PREFIX:-}
HARDWARE_PCI_ID=1002:13fe

STATE_ROOT=/var/lib/bc250-llm-server/revalidation
WORK=$STATE_ROOT/work
REPORT_DIR=$STATE_ROOT/results
RUN_DIR=/run/bc250-llm-server/revalidation
UNIT=bc250-revalidation.service
UNIT_PATH=/etc/systemd/system/$UNIT
LOCK=/run/lock/bc250-llm-server-revalidation.lock
HARNESS_COPY=$WORK/harness.sh
HELPER=$WORK/owui-test-helper.py

PHASE_FILE=$WORK/phase
STAGE_FILE=$WORK/stage
HEARTBEAT_FILE=$WORK/heartbeat
RUN_ID_FILE=$WORK/run-id
EVENTS=$WORK/events.log
RAW=$WORK/results
PHASE_REPORT_DIR=$WORK/phase-reports
SETTINGS_FILE=$WORK/settings.env
OWUI_CONFIG_SAVE=$WORK/owui-original-config.json
SYSCTX_STATE=$WORK/sysctx-state
SYSCTX_BACKUP=$WORK/sysctx-dropin.original
SYSCTX_DROPIN=/etc/containers/systemd/open-webui.container.d/99-bc250-revalidation.conf
OWUI_TOKEN=$RUN_DIR/owui-token
OWUI_TOKEN_SOURCE_FILE=$WORK/owui-token-source-path
TARGET_KERNEL_FILE=$WORK/target-kernel
ORIGINAL_ARGS_FILE=$WORK/original-kernel-args.txt
FAILURE_RC_FILE=$WORK/failure-rc
FAILURE_GUARD=$WORK/failure-handler-active

PARAM_REGEX='^(amdgpu\.gttsize|ttm\.pages_limit|ttm\.page_pool_size|amdgpu\.ppfeaturemask)='
PARAM_NAMES='amdgpu.gttsize ttm.pages_limit ttm.page_pool_size amdgpu.ppfeaturemask'
PACKAGE_BASELINE_PROFILE='ttm.pages_limit=4194304 ttm.page_pool_size=4194304'
LEGACY_FULL_PROFILE='amdgpu.gttsize=14750 ttm.pages_limit=4194304 ttm.page_pool_size=4194304 amdgpu.ppfeaturemask=0xffffffff'

# Optional/repeated checks. Routine runs default to no reboot and no repeated governor/
# keepalive/warm-prefix qualification. Enable those lanes only when the relevant kernel,
# governor, or residency policy changed. Values present at `start` are persisted for the
# detached worker. With sudo, prefer `sudo env RUN_FOO=1 bash ... start`.
RUN_KERNEL_REVALIDATION=${RUN_KERNEL_REVALIDATION:-0}
RUN_GOVERNOR_REVALIDATION=${RUN_GOVERNOR_REVALIDATION:-0}
RUN_KEEPALIVE_EXPIRY=${RUN_KEEPALIVE_EXPIRY:-0}
RUN_PRODUCTION_GENERATION=${RUN_PRODUCTION_GENERATION:-1}
RUN_WARM_PREFIX=${RUN_WARM_PREFIX:-0}
RUN_NUM_BATCH=${RUN_NUM_BATCH:-1}
RUN_AGENT=${RUN_AGENT:-1}
RUN_OWUI_TUNING=${RUN_OWUI_TUNING:-1}
RUN_EMBED_BATCH_SWEEP=${RUN_EMBED_BATCH_SWEEP:-1}
RUN_CHUNK_MIN_SWEEP=${RUN_CHUNK_MIN_SWEEP:-1}
RUN_RAG_SYSTEM_CONTEXT=${RUN_RAG_SYSTEM_CONTEXT:-1}
RUN_CONCURRENCY=${RUN_CONCURRENCY:-1}
RUN_OCR=${RUN_OCR:-0}

# Dedicated edge-case model. The harness skips it cleanly when not installed.
GPT_OSS_MODEL=${GPT_OSS_MODEL:-prod-gpt-oss20b-ggml-org-mxfp4}
E2B_MODEL=${E2B_MODEL:-prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl}
E4B_MODEL=${E4B_MODEL:-prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl}
EMBED_MODEL=${EMBED_MODEL:-embed-jina-v5-small-retrieval-q4-k-m}
TASK_MODEL=${TASK_MODEL:-task-gemma3-1b-unsloth-ud-q4-k-xl}

usage() {
  cat <<'USAGE'
Usage:
  sudo bc250-revalidate start [--owui-token-file FILE] [--kernel-ab] [--governor-ab] [--keepalive-expiry]
  sudo bc250-revalidate status
  sudo bc250-revalidate abort
  sudo bc250-revalidate cleanup

Recommended authenticated start:
  sudo install -m 600 /dev/null /root/owui-test.key
  sudoedit /root/owui-test.key  # paste a temporary Open WebUI admin API key
  sudo bc250-revalidate start --owui-token-file /root/owui-test.key

With RUN_KERNEL_REVALIDATION=1, the worker performs a focused two-reboot A/B:
current TTM-only baseline -> historical full profile -> exact original profile. The exact running kernel is selected
at start; there is no release-specific kernel string in the harness.

Routine default: no kernel-profile reboots, no repeated governor A/B, no 10-minute
keepalive-expiry wait, and no generic warm-prefix lane. Enable those only when needed.

Without an Open WebUI key the core Ollama/service/model tests still run, while
API-driven OWUI drift, embedding-batch, chunk-min and RAG_SYSTEM_CONTEXT tests
are reported as skipped.

Optional qualification lanes can be enabled explicitly:
  sudo bc250-revalidate start --kernel-ab
  sudo bc250-revalidate start --governor-ab
  sudo bc250-revalidate start --keepalive-expiry

Environment overrides remain available, for example:
  sudo env RUN_PRODUCTION_GENERATION=0 RUN_CHUNK_MIN_SWEEP=0 \
    bc250-revalidate start --owui-token-file /root/owui-test.key

The worker never stores the supplied key itself under /var or inside the final bundle.
When --owui-token-file is used, only the source FILE PATH is retained under the root-only
work directory so the key can be re-copied into /run (tmpfs), including after each kernel
reboot. Keep the source token file until the run is complete, then delete it.
USAGE
}

need_root() {
  [[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "ERROR: run with sudo/root." >&2; exit 1; }
}

now() { date --iso-8601=seconds; }

run_id() { cat "$RUN_ID_FILE" 2>/dev/null || true; }

set_phase() {
  printf '%s\n' "$1" > "$PHASE_FILE"
  progress "$2"
}

progress() {
  local msg="$1" ts
  ts="$(now)"
  printf '%s\n' "$msg" > "$STAGE_FILE"
  printf '%s\n' "$ts" > "$HEARTBEAT_FILE"
  printf '%s  phase=%s  %s\n' "$ts" "$(cat "$PHASE_FILE" 2>/dev/null || echo unknown)" "$msg" | tee -a "$EVENTS"
}

abort_requested() {
  [[ -e $WORK/ABORT ]]
}

check_abort() {
  abort_requested || return 0
  progress "operator abort requested"
  return 130
}

command_exists() { command -v "$1" >/dev/null 2>&1; }

save_settings() {
  local name
  : > "$SETTINGS_FILE"
  for name in \
    RUN_KERNEL_REVALIDATION RUN_GOVERNOR_REVALIDATION \
    RUN_KEEPALIVE_EXPIRY RUN_PRODUCTION_GENERATION RUN_WARM_PREFIX RUN_NUM_BATCH \
    RUN_AGENT RUN_OWUI_TUNING RUN_EMBED_BATCH_SWEEP RUN_CHUNK_MIN_SWEEP \
    RUN_RAG_SYSTEM_CONTEXT RUN_CONCURRENCY RUN_OCR \
    GPT_OSS_MODEL E2B_MODEL E4B_MODEL EMBED_MODEL TASK_MODEL; do
    printf '%s=%q\n' "$name" "${!name}" >> "$SETTINGS_FILE"
  done
  chmod 0600 "$SETTINGS_FILE"
}

load_settings() {
  [[ -f $SETTINGS_FILE ]] && source "$SETTINGS_FILE"
}


refresh_owui_token() {
  install -d -m 0700 "$RUN_DIR"
  if [[ -r $OWUI_TOKEN_SOURCE_FILE ]]; then
    local source
    source="$(cat "$OWUI_TOKEN_SOURCE_FILE")"
    rm -f "$OWUI_TOKEN"
    if [[ -n $source && -r $source ]]; then
      install -m 0600 "$source" "$OWUI_TOKEN"
      return 0
    fi
    progress "WARNING: saved OWUI token source is no longer readable; authenticated OWUI tests will be skipped"
  fi
  # An OWUI_API_KEY supplied via the environment exists only for the initial boot;
  # leave its already-created /run copy intact until a reboot naturally removes it.
  return 0
}

validate_owui_token() {
  [[ -s $OWUI_TOKEN ]] || return 0
  local token
  token="$(<"$OWUI_TOKEN")"
  [[ -n $token ]] || { echo "ERROR: supplied Open WebUI credential is empty." >&2; return 1; }
  # The tuning lanes require administrator access to /ollama/config. Validate it
  # before detaching/rebooting so a bad key cannot waste an entire kernel A/B run.
  if ! curl -fsS --connect-timeout 2 --max-time 10       -H "Authorization: Bearer $token"       http://127.0.0.1:3000/ollama/config >/dev/null 2>&1; then
    echo "ERROR: supplied Open WebUI credential was rejected by the admin configuration API." >&2
    echo "       Use a current admin Bearer credential/API key, or omit it to skip authenticated OWUI tuning." >&2
    return 1
  fi
}

api_ready() {
  local port="$1"
  curl -fsS --connect-timeout 2 --max-time 4 "http://127.0.0.1:${port}/api/tags" >/dev/null 2>&1
}

wait_api() {
  local port="$1" attempts="${2:-45}" i
  for ((i=1; i<=attempts; i++)); do
    api_ready "$port" && return 0
    sleep 1
  done
  return 1
}

model_registered() {
  local port="$1" model="$2"
  curl -fsS "http://127.0.0.1:${port}/api/tags" 2>/dev/null | \
    jq -e --arg m "$model" 'any(.models[]?; (.name | sub(":latest$"; "")) == $m)' >/dev/null 2>&1
}

first_registered() {
  local port="$1" prefix="$2"
  curl -fsS "http://127.0.0.1:${port}/api/tags" 2>/dev/null | \
    jq -r --arg p "$prefix" '[.models[]?.name | sub(":latest$"; "") | select(startswith($p))][0] // empty'
}

installed_prod_models() {
  curl -fsS http://127.0.0.1:11434/api/tags 2>/dev/null | \
    jq -r '.models[]?.name | sub(":latest$"; "") | select(startswith("prod-"))' | sort -u
}

write_helper() {
  cat > "$HELPER" <<'PY'
#!/usr/bin/env python3
"""Local-only helpers for the BC-250 0.10.0 revalidation harness."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


class Failure(RuntimeError):
    pass


class JsonClient:
    def __init__(self, base: str, token: str | None = None, timeout: float = 900):
        self.base = base.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, payload: Any | None = None, headers: dict[str, str] | None = None) -> Any:
        data = None
        merged = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            merged["Content-Type"] = "application/json"
        if self.token:
            merged["Authorization"] = f"Bearer {self.token}"
        if headers:
            merged.update(headers)
        req = urllib.request.Request(self.base + path, data=data, headers=merged, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
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


def ns(v: Any) -> float | None:
    try:
        return float(v) / 1e9
    except (TypeError, ValueError):
        return None


def ollama_unload(client: JsonClient, model: str) -> None:
    try:
        client.post("/api/generate", {"model": model, "stream": False, "keep_alive": 0})
    except Failure:
        pass


def wait_ready(client: JsonClient, timeout: float = 90) -> None:
    try:
        client.get("/api/tags")
        return
    except Failure:
        subprocess.run(
            ["systemctl", "restart", "ollama.service"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            client.get("/api/tags")
            return
        except Failure:
            time.sleep(2)
    raise Failure("main Ollama did not recover before the next diagnostic candidate")


def synthetic_prompt(sentences: int) -> str:
    return "\n".join(
        f"Office record sentence {i} contains contract BC250-{i:04d}, a dated policy item, department, CHF amount, payment deadline and procedural qualification."
        for i in range(1, sentences + 1)
    ) + "\nSummarize the operational pattern in two short sentences."


def cmd_embed_warm(args: argparse.Namespace) -> int:
    c = JsonClient(args.url)
    result = c.post("/api/embed", {"model": args.model, "input": ["Query: BC-250 embedding residency check"], "keep_alive": args.keep_alive})
    if not result.get("embeddings"):
        raise Failure("embedding API returned no vectors")
    print(json.dumps({"status": "ok", "model": args.model, "keep_alive": args.keep_alive, "vectors": len(result["embeddings"])}, sort_keys=True))
    return 0


def cmd_num_batch(args: argparse.Namespace) -> int:
    c = JsonClient(args.url, timeout=args.timeout)
    prompt = synthetic_prompt(args.sentences)
    rows: list[dict[str, Any]] = []
    batches: list[int | None] = [None, 512, 256, 128]
    for model in args.models:
        for batch in batches:
            options: dict[str, Any] = {"temperature": 0, "num_predict": args.num_predict, "num_ctx": args.num_ctx}
            if batch is not None:
                options["num_batch"] = batch
            payload = {"model": model, "prompt": prompt, "stream": False, "keep_alive": "2m", "options": options}
            started = time.monotonic()
            row: dict[str, Any] = {"model": model, "num_batch": "auto" if batch is None else batch}
            try:
                wait_ready(c)
                ollama_unload(c, model)
                time.sleep(1)
                result = c.post("/api/generate", payload)
                row.update({
                    "status": "ok",
                    "wall_s": time.monotonic() - started,
                    "load_s": ns(result.get("load_duration")),
                    "prompt_eval_count": result.get("prompt_eval_count"),
                    "prompt_eval_s": ns(result.get("prompt_eval_duration")),
                    "eval_count": result.get("eval_count"),
                    "eval_s": ns(result.get("eval_duration")),
                    "total_s": ns(result.get("total_duration")),
                    "done_reason": result.get("done_reason"),
                })
            except Exception as exc:  # diagnostic sweep should retain later rows
                row.update({"status": "error", "wall_s": time.monotonic() - started, "error": str(exc)})
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False, sort_keys=True), flush=True)
    Path(args.output).write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n")
    return 0 if all(r["status"] == "ok" for r in rows) else 1


def cmd_concurrency(args: argparse.Namespace) -> int:
    main = JsonClient(args.main_url, timeout=args.timeout)
    emb = JsonClient(args.embed_url, timeout=args.timeout)
    prompt = synthetic_prompt(args.sentences)
    ollama_unload(main, args.model)

    def generation() -> dict[str, Any]:
        start = time.monotonic()
        r = main.post("/api/generate", {
            "model": args.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "5m",
            "options": {"temperature": 0, "num_predict": 32, "num_ctx": 32768},
        })
        return {"wall_s": time.monotonic() - start, "prompt_eval_count": r.get("prompt_eval_count"), "prompt_eval_s": ns(r.get("prompt_eval_duration")), "eval_s": ns(r.get("eval_duration"))}

    def embeddings() -> list[dict[str, Any]]:
        rows = []
        for i in range(args.embed_requests):
            start = time.monotonic()
            r = emb.post("/api/embed", {"model": args.embed_model, "input": [f"Query: concurrent embedding request {i}"], "keep_alive": "10m"})
            rows.append({"i": i, "wall_s": time.monotonic() - start, "ok": bool(r.get("embeddings"))})
            time.sleep(0.25)
        return rows

    start = time.monotonic()
    out: dict[str, Any] = {"model": args.model, "embed_model": args.embed_model}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            gf = pool.submit(generation)
            ef = pool.submit(embeddings)
            out["generation"] = gf.result()
            out["embeddings"] = ef.result()
        out["status"] = "ok" if all(x["ok"] for x in out["embeddings"]) else "error"
    except Exception as exc:
        out.update({"status": "error", "error": str(exc)})
    out["wall_s"] = time.monotonic() - start
    Path(args.output).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return 0 if out.get("status") == "ok" else 1


def token_from(path: str) -> str:
    token = Path(path).read_text().strip()
    if not token:
        raise Failure("Open WebUI token file is empty")
    return token


def emb_selected(data: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "RAG_EMBEDDING_ENGINE", "RAG_EMBEDDING_MODEL", "RAG_EMBEDDING_BATCH_SIZE",
        "ENABLE_ASYNC_EMBEDDING", "RAG_EMBEDDING_CONCURRENT_REQUESTS", "ollama_config",
    ]
    return {k: data.get(k) for k in keys}


def rag_selected(data: dict[str, Any]) -> dict[str, Any]:
    keys = ["CHUNK_MIN_SIZE_TARGET"]
    return {k: data.get(k) for k in keys}


def owui_client(args: argparse.Namespace) -> JsonClient:
    return JsonClient(args.url, token_from(args.token_file), timeout=args.timeout)


def cmd_save_config(args: argparse.Namespace) -> int:
    c = owui_client(args)
    out = {"embedding": emb_selected(c.get("/api/v1/retrieval/embedding")), "rag": rag_selected(c.get("/api/v1/retrieval/config"))}
    Path(args.output).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    return 0


def cmd_restore_config(args: argparse.Namespace) -> int:
    c = owui_client(args)
    data = json.loads(Path(args.input).read_text())
    c.post("/api/v1/retrieval/embedding/update", data["embedding"])
    c.post("/api/v1/retrieval/config/update", data["rag"])
    return 0


def multipart_upload(c: JsonClient, path: Path, knowledge_id: str) -> dict[str, Any]:
    content = path.read_bytes()
    metadata = json.dumps({"knowledge_id": knowledge_id, "file_hash": hashlib.sha256(content).hexdigest()})
    boundary = "----bc250-reval-" + uuid.uuid4().hex
    mime = mimetypes.guess_type(path.name)[0] or "text/markdown"
    body = b"".join([
        f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n{metadata}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"}
    if c.token:
        headers["Authorization"] = f"Bearer {c.token}"
    req = urllib.request.Request(c.base + "/api/v1/files/?process=true&process_in_background=false", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=c.timeout) as r:
            result = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise Failure(f"upload: HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
    fid = result.get("id")
    if not fid:
        raise Failure("upload returned no file id")
    status = c.get(f"/api/v1/files/{fid}/process/status")
    if status.get("status") != "completed":
        raise Failure(f"file processing status={status!r}")
    return result


def create_kb(c: JsonClient, name: str) -> dict[str, Any]:
    kb = c.post("/api/v1/knowledge/create", {"name": name, "description": "Temporary BC-250 revalidation knowledge base; safe to delete."})
    if not kb.get("id"):
        raise Failure("knowledge create returned no id")
    return kb


def cleanup_kb(c: JsonClient, kb_id: str | None, file_id: str | None) -> None:
    if kb_id:
        try:
            c.delete(f"/api/v1/knowledge/{kb_id}/delete")
        except Exception:
            pass
    if file_id:
        try:
            c.delete(f"/api/v1/files/{file_id}")
        except Exception:
            pass


def chat(c: JsonClient, model: str, kb_id: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    return c.post("/api/chat/completions", {
        "model": model,
        "messages": messages,
        "files": [{"type": "collection", "id": kb_id, "status": "processed"}],
        "stream": False,
        "background_tasks": {"title_generation": False, "tags_generation": False, "follow_up_generation": False},
    })


def response_text(result: dict[str, Any]) -> str:
    try:
        return str(result["choices"][0]["message"]["content"])
    except Exception:
        return ""


def usage_row(result: dict[str, Any]) -> dict[str, Any]:
    u = result.get("usage") if isinstance(result, dict) else {}
    if not isinstance(u, dict):
        u = {}
    return {k: u.get(k) for k in ["prompt_tokens", "completion_tokens", "total_tokens", "prompt_token/s", "response_token/s", "total_duration", "load_duration", "prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration"]}


def source_meta(result: dict[str, Any]) -> dict[str, Any]:
    """Retain retrieval/citation metadata when the tagged OWUI response exposes it."""
    if not isinstance(result, dict):
        return {}
    keys = ("sources", "citations", "context_chunks_with_source", "context")
    return {key: result[key] for key in keys if key in result}


def make_batch_doc(path: Path) -> None:
    parts = ["# BC-250 embedding batch fixture\n"]
    for i in range(1, 181):
        parts.append(f"## Record {i}\nContract BAT-{i:04d} belongs to Department {i % 11}, has a payment deadline of {10 + i % 20} days, amount CHF {1000 + i * 7}.00, and procedure code PROC-{i % 17:02d}. This paragraph exists to create realistic local embedding work without external downloads.\n")
    path.write_text("\n".join(parts))


def make_chunk_doc(path: Path) -> None:
    path.write_text("""# Office handbook\n\n## Zurich lease\nThe current Zurich lease reference is ZH-CURRENT-7721. The notice period is six months.\n\n## Archive note\nThe archived Zurich lease reference ZH-OLD-6610 is superseded and must not be used for current notices.\n\n## Invoice 2026-0441\nInvoice reference INV-2026-0441 is CHF 18,740.00 and is due within 30 days.\n\n## Invoice 2026-0447\nInvoice reference INV-2026-0447 is CHF 18,470.00 and is due within 14 days.\n\n## Procurement\nPurchase order PO-88217 requires two approvals above CHF 25,000.\n\n## Privacy\nConfidential personnel documents may not be copied to public collections.\n""")


def cmd_embedding_batch(args: argparse.Namespace) -> int:
    c = owui_client(args)
    original = emb_selected(c.get("/api/v1/retrieval/embedding"))
    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    doc = work / "embedding-batch.md"; make_batch_doc(doc)
    rows = []
    try:
        for batch in (1, 4, 8, 16):
            cfg = dict(original); cfg["RAG_EMBEDDING_BATCH_SIZE"] = batch
            c.post("/api/v1/retrieval/embedding/update", cfg)
            kb_id = file_id = None
            row = {"batch": batch}
            try:
                kb = create_kb(c, f"BC250 revalidation embed batch {batch} {uuid.uuid4().hex[:8]}")
                kb_id = str(kb["id"])
                start = time.monotonic(); up = multipart_upload(c, doc, kb_id); elapsed = time.monotonic() - start
                file_id = str(up["id"])
                row.update({"status": "ok", "process_wall_s": elapsed, "file_id": file_id})
            except Exception as exc:
                row.update({"status": "error", "error": str(exc)})
            finally:
                cleanup_kb(c, kb_id, file_id)
            rows.append(row); print(json.dumps(row, sort_keys=True), flush=True)
    finally:
        c.post("/api/v1/retrieval/embedding/update", original)
    Path(args.output).write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n")
    return 0


def cmd_chunk_min(args: argparse.Namespace) -> int:
    c = owui_client(args)
    original = rag_selected(c.get("/api/v1/retrieval/config"))
    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    doc = work / "chunk-min.md"; make_chunk_doc(doc)
    tests = [
        ("What is the current Zurich lease reference and notice period?", ["ZH-CURRENT-7721", "six"]),
        ("What amount and deadline belong to invoice INV-2026-0447?", ["18,470", "14"]),
        ("Which invoice is CHF 18,740.00 and what is its deadline?", ["INV-2026-0441", "30"]),
        ("What approval rule applies above CHF 25,000?", ["two", "25,000"]),
    ]
    rows = []
    try:
        for target in (0, 500, 750, 1000):
            c.post("/api/v1/retrieval/config/update", {"CHUNK_MIN_SIZE_TARGET": target})
            kb_id = file_id = None
            row: dict[str, Any] = {"chunk_min_size_target": target, "cases": []}
            try:
                kb = create_kb(c, f"BC250 revalidation chunk {target} {uuid.uuid4().hex[:8]}"); kb_id = str(kb["id"])
                start = time.monotonic(); up = multipart_upload(c, doc, kb_id); row["process_wall_s"] = time.monotonic() - start; file_id = str(up["id"])
                passes = 0
                for question, needles in tests:
                    start = time.monotonic(); result = chat(c, args.model, kb_id, [{"role": "user", "content": question + " Answer briefly and cite the supplied source."}]); wall = time.monotonic() - start
                    text = response_text(result); ok = all(n.casefold() in text.casefold() for n in needles)
                    passes += int(ok)
                    row["cases"].append({"question": question, "required": needles, "pass": ok, "wall_s": wall, "usage": usage_row(result), "source_meta": source_meta(result), "answer": text})
                row.update({"status": "ok", "passes": passes, "total_cases": len(tests)})
            except Exception as exc:
                row.update({"status": "error", "error": str(exc)})
            finally:
                cleanup_kb(c, kb_id, file_id)
            rows.append(row); print(json.dumps({k:v for k,v in row.items() if k != "cases"}, sort_keys=True), flush=True)
    finally:
        c.post("/api/v1/retrieval/config/update", original)
    Path(args.output).write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n")
    return 0


def make_sysctx_doc(path: Path) -> None:
    filler = " ".join(["The operational appendix contains stable office wording for cache measurement."] * 350)
    path.write_text(f"""# Contract cache fixture\n\nThe active contract reference is CACHE-ZH-9917. The notice period is six months. The payment deadline is 30 days. The responsible unit is Facility Operations. The archived reference CACHE-ZH-1204 must not be used.\n\n## Stable appendix\n{filler}\n""")


def cmd_rag_sysctx(args: argparse.Namespace) -> int:
    c = owui_client(args)
    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    doc = work / f"rag-sysctx-{args.label}.md"; make_sysctx_doc(doc)
    kb_id = file_id = None
    out: dict[str, Any] = {"label": args.label, "turns": []}
    try:
        kb = create_kb(c, f"BC250 revalidation sysctx {args.label} {uuid.uuid4().hex[:8]}"); kb_id = str(kb["id"])
        start = time.monotonic(); up = multipart_upload(c, doc, kb_id); out["process_wall_s"] = time.monotonic() - start; file_id = str(up["id"])
        messages: list[dict[str, str]] = []
        questions = [
            ("According to the document, what are the active contract reference and notice period? Answer briefly with a citation.", ["CACHE-ZH-9917", "six"]),
            ("And what is the payment deadline and responsible unit? Answer briefly with a citation.", ["30", "Facility Operations"]),
            ("Repeat only the active reference and payment deadline, with a citation.", ["CACHE-ZH-9917", "30"]),
        ]
        passes = 0
        for idx, (q, required) in enumerate(questions, 1):
            messages.append({"role": "user", "content": q})
            start = time.monotonic(); result = chat(c, args.model, kb_id, messages); wall = time.monotonic() - start
            text = response_text(result)
            fact_ok = all(x.casefold() in text.casefold() for x in required)
            archive_leak = "CACHE-ZH-1204" in text
            ok = fact_ok and not archive_leak
            passes += int(ok)
            out["turns"].append({"turn": idx, "required": required, "pass": ok, "archive_leak": archive_leak, "wall_s": wall, "usage": usage_row(result), "source_meta": source_meta(result), "answer": text})
            messages.append({"role": "assistant", "content": text})
        out["passes"] = passes
        out["total_turns"] = len(questions)
        out["status"] = "ok" if passes == len(questions) else "quality-fail"
    except Exception as exc:
        out.update({"status": "error", "error": str(exc)})
    finally:
        cleanup_kb(c, kb_id, file_id)
    Path(args.output).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k:v for k,v in out.items() if k != "turns"}, sort_keys=True))
    return 0 if out.get("status") == "ok" else 1


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    x = sub.add_parser("embed-warm"); x.add_argument("--url", default="http://127.0.0.1:11437"); x.add_argument("--model", required=True); x.add_argument("--keep-alive", default="10m"); x.set_defaults(fn=cmd_embed_warm)
    x = sub.add_parser("num-batch"); x.add_argument("--url", default="http://127.0.0.1:11434"); x.add_argument("--models", nargs="+", required=True); x.add_argument("--sentences", type=int, default=704); x.add_argument("--num-predict", type=int, default=16); x.add_argument("--num-ctx", type=int, default=32768); x.add_argument("--timeout", type=float, default=900); x.add_argument("--output", required=True); x.set_defaults(fn=cmd_num_batch)
    x = sub.add_parser("concurrency"); x.add_argument("--main-url", default="http://127.0.0.1:11434"); x.add_argument("--embed-url", default="http://127.0.0.1:11437"); x.add_argument("--model", required=True); x.add_argument("--embed-model", required=True); x.add_argument("--sentences", type=int, default=352); x.add_argument("--embed-requests", type=int, default=8); x.add_argument("--timeout", type=float, default=900); x.add_argument("--output", required=True); x.set_defaults(fn=cmd_concurrency)

    def owui_common(x: argparse.ArgumentParser) -> None:
        x.add_argument("--url", default="http://127.0.0.1:3000"); x.add_argument("--token-file", required=True); x.add_argument("--timeout", type=float, default=900)
    x = sub.add_parser("save-config"); owui_common(x); x.add_argument("--output", required=True); x.set_defaults(fn=cmd_save_config)
    x = sub.add_parser("restore-config"); owui_common(x); x.add_argument("--input", required=True); x.set_defaults(fn=cmd_restore_config)
    x = sub.add_parser("embedding-batch"); owui_common(x); x.add_argument("--work", required=True); x.add_argument("--output", required=True); x.set_defaults(fn=cmd_embedding_batch)
    x = sub.add_parser("chunk-min"); owui_common(x); x.add_argument("--work", required=True); x.add_argument("--output", required=True); x.add_argument("--model", required=True); x.set_defaults(fn=cmd_chunk_min)
    x = sub.add_parser("rag-sysctx"); owui_common(x); x.add_argument("--work", required=True); x.add_argument("--output", required=True); x.add_argument("--model", required=True); x.add_argument("--label", required=True); x.set_defaults(fn=cmd_rag_sysctx)

    args = p.parse_args()
    return int(args.fn(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Failure, KeyboardInterrupt) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
PY
  chmod 0700 "$HELPER"
}


canonical_profile_string() {
  local input="$1"
  tr ' ' '\n' <<<"$input" | grep -E "$PARAM_REGEX" | sed '/^$/d' | sort -u || true
}

current_relevant_args() {
  tr ' ' '\n' < /proc/cmdline | grep -E "$PARAM_REGEX" | sort -u || true
}

saved_original_args() {
  cat "$ORIGINAL_ARGS_FILE" 2>/dev/null || true
}

saved_original_args_string() {
  paste -sd' ' "$ORIGINAL_ARGS_FILE" 2>/dev/null || true
}

target_kernel() {
  cat "$TARGET_KERNEL_FILE" 2>/dev/null || true
}

check_running_kernel() {
  local target expected
  target="$(target_kernel)"
  [[ -n $target ]] || { echo "ERROR: target kernel was not saved." >&2; return 1; }
  expected="${target##*/vmlinuz-}"
  [[ $(uname -r) == "$expected" ]] || {
    echo "ERROR: running kernel $(uname -r) != saved test kernel $expected" >&2
    return 1
  }
}

verify_running_profile() {
  local expected="$1" current expected_canon
  current="$(current_relevant_args)"
  expected_canon="$(canonical_profile_string "$expected")"
  if [[ $current != "$expected_canon" ]]; then
    {
      echo 'EXPECTED:'
      printf '%s\n' "$expected_canon"
      echo 'CURRENT:'
      printf '%s\n' "$current"
    } >&2
    return 1
  fi
}

apply_profile_next_boot() {
  local profile="$1" target
  target="$(target_kernel)"
  [[ -n $target ]] || { echo "ERROR: target kernel missing" >&2; return 1; }
  progress "configuring next boot profile on ${target##*/}: ${profile:-<none>}"
  grubby --update-kernel="$target" --remove-args="$PARAM_NAMES"
  if [[ -n $profile ]]; then
    grubby --update-kernel="$target" --args="$profile"
  fi
  grubby --info="$target" > "$RAW/grubby-next-$(cat "$PHASE_FILE")-$(date +%s).txt" 2>&1 || true
}

restore_original_next_boot() {
  apply_profile_next_boot "$(saved_original_args_string)"
}

kernel_profile_modified() {
  [[ -r $ORIGINAL_ARGS_FILE ]] || return 1
  [[ $(current_relevant_args) != "$(saved_original_args)" ]]
}

request_reboot() {
  local next_phase="$1"
  printf '%s\n' "$next_phase" > "$PHASE_FILE"
  progress "requesting reboot; next phase=$next_phase"
  sync
  systemctl reboot --no-block
  exit 0
}

install_unit() {
  cat > "$UNIT_PATH" <<EOFUNIT
[Unit]
Description=BC-250 0.10.0 kernel/pipeline/settings revalidation v${HARNESS_VERSION}
After=network-online.target cyan-skillfish-governor-smu.service ollama.service open-webui.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/bash $HARNESS_COPY worker
TimeoutStartSec=infinity
TimeoutStopSec=120
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOFUNIT
  systemctl daemon-reload
  systemctl enable "$UNIT" >/dev/null
}

preflight() {
  local cmd missing=0 pkg
  for cmd in curl jq python3 rpm systemctl journalctl podman sensors vulkaninfo timeout flock tar lspci bc250-status bc250-verify bc250-benchmark bc250-agent-mode bc250-openwebui-setup; do
    if ! command_exists "$cmd"; then
      echo "ERROR: missing required command: $cmd" >&2
      missing=1
    fi
  done
  if ((RUN_KERNEL_REVALIDATION)); then
    for cmd in grubby bc250-memory-profile bc250-cu-status; do
      if ! command_exists "$cmd"; then
        echo "ERROR: kernel revalidation requires: $cmd" >&2
        missing=1
      fi
    done
  fi
  if ((RUN_GOVERNOR_REVALIDATION)); then
    command_exists cyan-skillfish-performance-mode || {
      echo "ERROR: governor revalidation requires cyan-skillfish-performance-mode" >&2
      missing=1
    }
  fi
  ((missing == 0)) || return 1
  lspci -Dnn 2>/dev/null | grep -iF "[$HARDWARE_PCI_ID]" >/dev/null || {
    echo "ERROR: BC-250 PCI device [$HARDWARE_PCI_ID] was not detected." >&2
    return 1
  }
  pkg="$(rpm -q bc250-llm-server 2>/dev/null || true)"
  [[ $pkg == bc250-llm-server-${TARGET_VERSION}-* ]] || {
    echo "ERROR: expected bc250-llm-server ${TARGET_VERSION}; installed: ${pkg:-not installed}" >&2
    return 1
  }
  if [[ -n $TARGET_RELEASE_PREFIX && $pkg != *"${TARGET_RELEASE_PREFIX}"* ]]; then
    echo "WARN: package release differs from requested ${TARGET_RELEASE_PREFIX}: $pkg" >&2
  fi
  [[ $(systemctl is-active ollama-agent.service 2>/dev/null || true) != active ]] || {
    echo "INFO: agent mode is currently active; start will restore normal mode first."
  }
  df -h / /var/lib/bc250-llm-server
}

start_run() {
  need_root
  local token_file=""
  shift || true
  while (($#)); do
    case "$1" in
      --owui-token-file)
        [[ $# -ge 2 ]] || { echo "ERROR: --owui-token-file requires a path" >&2; exit 2; }
        token_file="$2"; shift 2 ;;
      --kernel-ab)
        RUN_KERNEL_REVALIDATION=1; shift ;;
      --governor-ab)
        RUN_GOVERNOR_REVALIDATION=1; shift ;;
      --keepalive-expiry)
        RUN_KEEPALIVE_EXPIRY=1; shift ;;
      -h|--help) usage; exit 0 ;;
      *) echo "ERROR: unknown start option: $1" >&2; usage >&2; exit 2 ;;
    esac
  done
  preflight
  if [[ -n $token_file && ! -r $token_file ]]; then
    echo "ERROR: cannot read OWUI token file: $token_file" >&2
    exit 1
  fi
  if systemctl is-active --quiet "$UNIT" 2>/dev/null; then
    echo "ERROR: $UNIT is already running." >&2
    exit 1
  fi
  if [[ -d $WORK && -f $PHASE_FILE && $(cat "$PHASE_FILE" 2>/dev/null) != "done" && $(cat "$PHASE_FILE" 2>/dev/null) != "failed" ]]; then
    echo "ERROR: existing unfinished session under $WORK. Use status/abort/cleanup first." >&2
    exit 1
  fi

  rm -rf "$WORK" "$RUN_DIR"
  install -d -m 0700 "$WORK" "$RAW" "$PHASE_REPORT_DIR" "$RUN_DIR"
  install -d -m 0700 "$STATE_ROOT" "$REPORT_DIR"
  install -m 0700 "$0" "$HARNESS_COPY"
  save_settings
  : > "$EVENTS"
  printf 'initializing\n' > "$PHASE_FILE"
  printf 'start requested\n' > "$STAGE_FILE"
  printf '%s\n' "$(now)" > "$HEARTBEAT_FILE"
  printf '%s-%s\n' "$(date +%Y%m%dT%H%M%S%z)" "$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \n')" > "$RUN_ID_FILE"
  if [[ -n $token_file ]]; then
    printf '%s\n' "$(readlink -f -- "$token_file")" > "$OWUI_TOKEN_SOURCE_FILE"
    chmod 0600 "$OWUI_TOKEN_SOURCE_FILE"
    install -m 0600 "$token_file" "$OWUI_TOKEN"
  elif [[ -n ${OWUI_API_KEY:-} ]]; then
    printf '%s\n' "$OWUI_API_KEY" > "$OWUI_TOKEN"
    chmod 0600 "$OWUI_TOKEN"
    if ((RUN_KERNEL_REVALIDATION)); then
      echo "WARN: OWUI_API_KEY from the environment cannot survive reboot; use --owui-token-file for authenticated OWUI tests." >&2
    fi
  fi
  validate_owui_token
  write_helper

  # Capture the kernel target before detaching. This intentionally follows the
  # actual running/default kernel and contains no release-specific kernel name.
  if ((RUN_KERNEL_REVALIDATION)); then
    local target default current expected
    target="/boot/vmlinuz-$(uname -r)"
    default="$(grubby --default-kernel)"
    [[ -e $target ]] || { echo "ERROR: running kernel image not found: $target" >&2; exit 1; }
    [[ ${default##*/} == "${target##*/}" ]] || {
      echo "ERROR: running kernel is not the grubby default; boot the default kernel first." >&2
      exit 1
    }
    current="$(current_relevant_args)"
    expected="$(canonical_profile_string "$PACKAGE_BASELINE_PROFILE")"
    if [[ $current != "$expected" ]]; then
      {
        echo 'ERROR: current relevant kernel arguments do not match the 0.10.0 TTM-only package baseline.'
        echo 'EXPECTED:'; printf '%s\n' "$expected"
        echo 'CURRENT:'; printf '%s\n' "$current"
      } >&2
      exit 1
    fi
    printf '%s\n' "$target" > "$TARGET_KERNEL_FILE"
    printf '%s\n' "$current" > "$ORIGINAL_ARGS_FILE"
    chmod 0600 "$TARGET_KERNEL_FILE" "$ORIGINAL_ARGS_FILE"
    printf 'kernel-baseline\n' > "$PHASE_FILE"
    progress "kernel target=${target##*/}; exact original relevant args saved; other kernel entries will not be modified"
  else
    printf 'pipeline-start\n' > "$PHASE_FILE"
    progress "kernel revalidation disabled; starting application pipeline on $(uname -r)"
  fi

  install_unit
  systemctl reset-failed "$UNIT" >/dev/null 2>&1 || true
  systemctl start --no-block "$UNIT"
  echo "Started run_id=$(run_id)"
  if ((RUN_KERNEL_REVALIDATION)); then
    echo "The worker will reboot twice while comparing the current TTM-only profile with the historical full profile, then continue with application tests."
  fi
  echo "Status: sudo bash $HARNESS_COPY status"
  echo "Journal: sudo journalctl -fu $UNIT"
  echo "Final bundles: $REPORT_DIR"
}

capture_cmd() {
  local file="$1"; shift
  { echo '$' "$@"; "$@"; } > "$file" 2>&1 || echo "command_rc=$?" >> "$file"
}

snapshot() {
  local label="$1" dir="$RAW/$1"
  progress "capturing snapshot: $label"
  install -d -m 0700 "$dir"
  {
    echo "timestamp=$(now)"
    echo "kernel=$(uname -r)"
    echo "package=$(rpm -q bc250-llm-server 2>/dev/null || true)"
    echo "cmdline=$(cat /proc/cmdline)"
    echo "current_relevant_args=$(current_relevant_args | paste -sd' ' -)"
    [[ ! -r $TARGET_KERNEL_FILE ]] || echo "target_kernel=$(target_kernel)"
    for f in \
      /sys/module/amdgpu/parameters/gttsize \
      /sys/module/amdgpu/parameters/ppfeaturemask \
      /sys/module/ttm/parameters/pages_limit \
      /sys/module/ttm/parameters/page_pool_size; do
      [[ -r $f ]] && echo "$f=$(cat "$f")" || true
    done
    for d in /sys/class/drm/card*/device; do
      [[ -r $d/vendor && $(cat "$d/vendor" 2>/dev/null) == 0x1002 ]] || continue
      for f in mem_info_vram_total mem_info_vram_used mem_info_gtt_total mem_info_gtt_used; do
        [[ -r $d/$f ]] && echo "$f=$(cat "$d/$f")"
      done
      break
    done
  } > "$dir/kernel-profile.txt" 2>&1
  capture_cmd "$dir/kernel-rpms.txt" rpm -q kernel-core mesa-vulkan-drivers vulkan-loader vulkan-tools
  command_exists grubby && capture_cmd "$dir/grubby-all.txt" grubby --info=ALL || true
  command_exists bc250-memory-profile && capture_cmd "$dir/memory-profile.txt" bc250-memory-profile status || true
  command_exists bc250-cu-status && capture_cmd "$dir/cu-status.txt" bc250-cu-status || true
  if [[ -r /etc/cyan-skillfish-governor-smu/config.toml ]]; then
    cp -a /etc/cyan-skillfish-governor-smu/config.toml "$dir/governor-config.toml"
  fi
  command_exists cyan-skillfish-performance-mode && capture_cmd "$dir/performance-mode.txt" cyan-skillfish-performance-mode --status || true
  capture_cmd "$dir/bc250-status.txt" bc250-status
  if [[ -s $OWUI_TOKEN ]]; then
    OWUI_API_KEY="$(<"$OWUI_TOKEN")" bc250-verify > "$dir/bc250-verify.txt" 2>&1 || echo "command_rc=$?" >> "$dir/bc250-verify.txt"
    OWUI_API_KEY="$(<"$OWUI_TOKEN")" bc250-openwebui-setup status > "$dir/openwebui-status-auth.txt" 2>&1 || echo "command_rc=$?" >> "$dir/openwebui-status-auth.txt"
  else
    capture_cmd "$dir/bc250-verify.txt" bc250-verify
    capture_cmd "$dir/openwebui-status.txt" bc250-openwebui-setup status
  fi
  capture_cmd "$dir/agent-mode.txt" bc250-agent-mode status
  capture_cmd "$dir/systemctl.txt" systemctl --no-pager --full status ollama.service ollama-task.service ollama-embedding.service ollama-agent.service open-webui.service tika.service nginx.service
  for port in 11434 11435 11436 11437; do
    curl -fsS "http://127.0.0.1:$port/api/version" > "$dir/ollama-$port-version.json" 2>&1 || true
    curl -fsS "http://127.0.0.1:$port/api/tags" > "$dir/ollama-$port-tags.json" 2>&1 || true
    curl -fsS "http://127.0.0.1:$port/api/ps" > "$dir/ollama-$port-ps.json" 2>&1 || true
  done
  podman inspect open-webui --format '{{json .State}}' > "$dir/openwebui-container-state.json" 2>&1 || true
  podman inspect open-webui --format '{{.ImageName}}' > "$dir/openwebui-container-image.txt" 2>&1 || true
  capture_cmd "$dir/free.txt" free -h
  capture_cmd "$dir/swapon.txt" swapon --show
  capture_cmd "$dir/sensors.txt" sensors
  capture_cmd "$dir/vulkan.txt" vulkaninfo --summary
  journalctl -b --no-pager -n 1200 -u ollama.service -u ollama-task.service -u ollama-embedding.service -u ollama-agent.service -u open-webui.service > "$dir/services-journal.txt" 2>&1 || true
  journalctl -k -b --no-pager -n 1200 > "$dir/kernel-journal.txt" 2>&1 || true
}

write_phase_report() {
  local label="$1" scope="$2" stamp file
  stamp="$(date +%Y%m%dT%H%M%S)"
  file="$PHASE_REPORT_DIR/$(run_id)-${label}-${stamp}.txt"
  {
    echo "# BC-250 0.10.0 revalidation v${HARNESS_VERSION} phase report"
    echo "generated=$(now)"
    echo "run_id=$(run_id)"
    echo "phase=$(cat "$PHASE_FILE")"
    echo "stage=$(cat "$STAGE_FILE")"
    echo "kernel=$(uname -r)"
    echo "package=$(rpm -q bc250-llm-server 2>/dev/null || true)"
    echo "current_relevant_args=$(current_relevant_args | paste -sd' ' -)"
    if [[ -r $TARGET_KERNEL_FILE ]]; then
      echo "target_kernel=$(target_kernel)"
      echo "saved_original_args=$(saved_original_args | paste -sd' ' -)"
    fi
    echo
    echo "## Events"
    cat "$EVENTS"
    echo
    echo "## Phase files: $scope"
    if [[ -d $RAW/$scope ]]; then
      while IFS= read -r f; do
        echo
        echo "===== BEGIN FILE: ${f#"$WORK"/} ====="
        case "$f" in
          *.png|*.jpg|*.jpeg|*.tar|*.gz) echo "[binary omitted from text report]" ;;
          *) cat "$f" 2>/dev/null || true ;;
        esac
        echo "===== END FILE: ${f#"$WORK"/} ====="
      done < <(find "$RAW/$scope" -type f -print | sort)
    fi
  } > "$file"
  chmod 0644 "$file"
  progress "immutable phase report written: $file"
}

sample_loop() {
  local out="$1" dev="" hw="" temp="" power="" clock="" gtt="" mem="" swap=""
  local d h label f
  for d in /sys/class/drm/card*/device; do
    [[ -r $d/vendor && $(cat "$d/vendor" 2>/dev/null) == 0x1002 ]] || continue
    dev="$d"
    break
  done
  if [[ -n $dev ]]; then
    for h in "$dev"/hwmon/hwmon*; do
      [[ -d $h ]] || continue
      hw="$h"
      break
    done
  fi
  printf 'timestamp\tclock_mhz\ttemp_c\tsmu_power_w\tgtt_used_mib\tmemavailable_mib\tswap_used_mib\n' > "$out"
  while :; do
    clock=""; temp=""; power=""; gtt=""; mem=""; swap=""
    if [[ -n $dev && -r $dev/pp_dpm_sclk ]]; then
      clock="$(awk '/\*/{gsub("Mhz", "", $2); print $2; exit}' "$dev/pp_dpm_sclk" 2>/dev/null || true)"
    fi
    if [[ -n $hw ]]; then
      # Prefer edge, then junction, then temp1.
      for label in edge junction; do
        for f in "$hw"/temp*_label; do
          [[ -r $f ]] || continue
          if [[ $(cat "$f" 2>/dev/null) == "$label" ]]; then
            f="${f%_label}_input"
            [[ -r $f ]] && temp="$(awk '{printf "%.1f", $1/1000}' "$f" 2>/dev/null || true)"
            break 2
          fi
        done
      done
      [[ -n $temp || ! -r $hw/temp1_input ]] || temp="$(awk '{printf "%.1f", $1/1000}' "$hw/temp1_input" 2>/dev/null || true)"
      [[ ! -r $hw/power1_average ]] || power="$(awk '{printf "%.2f", $1/1000000}' "$hw/power1_average" 2>/dev/null || true)"
    fi
    if [[ -n $dev && -r $dev/mem_info_gtt_used ]]; then
      gtt="$(awk '{printf "%.1f", $1/1048576}' "$dev/mem_info_gtt_used" 2>/dev/null || true)"
    fi
    mem="$(awk '/^MemAvailable:/{printf "%.1f", $2/1024}' /proc/meminfo 2>/dev/null || true)"
    swap="$(awk '/^SwapTotal:/{t=$2}/^SwapFree:/{f=$2}END{printf "%.1f", (t-f)/1024}' /proc/meminfo 2>/dev/null || true)"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(date +%s.%N)" "$clock" "$temp" "$power" "$gtt" "$mem" "$swap" >> "$out"
    sleep 0.5
  done
}

SAMPLER_PID=""

start_sampler() {
  local out="$1"
  stop_sampler "${SAMPLER_PID:-}"
  sample_loop "$out" >/dev/null 2>&1 &
  SAMPLER_PID=$!
}

stop_sampler() {
  local pid="${1:-${SAMPLER_PID:-}}"
  [[ -n $pid ]] || return 0
  kill "$pid" >/dev/null 2>&1 || true
  wait "$pid" 2>/dev/null || true
  if [[ ${SAMPLER_PID:-} == "$pid" ]]; then
    SAMPLER_PID=""
  fi
}

worker_exit_cleanup() {
  stop_sampler "${SAMPLER_PID:-}"
  performance_off
}

run_bench_at() {
  local scope="$1" label="$2"; shift 2
  local dir="$RAW/$scope/$label" rc sampler_pid
  install -d -m 0700 "$dir"
  progress "benchmark starting: $scope/$label"
  start_sampler "$dir/sampler.tsv"
  sampler_pid="$SAMPLER_PID"
  # bc250-benchmark uses nonzero statuses for quality/acceptance failures.
  # Treat that status as test data, not as a harness infrastructure failure.
  if (cd "$dir" && timeout 45m "$@") > "$dir/benchmark-console.txt" 2>&1; then
    rc=0
  else
    rc=$?
  fi
  stop_sampler "$sampler_pid"
  printf '%s\n' "$rc" > "$dir/benchmark-exit-status.txt"
  case "$rc" in
    0) printf 'pass\n' > "$dir/benchmark-outcome.txt" ;;
    3) printf 'quality-fail\n' > "$dir/benchmark-outcome.txt" ;;
    124|137) printf 'timeout-or-killed\n' > "$dir/benchmark-outcome.txt" ;;
    *) printf 'nonzero-%s\n' "$rc" > "$dir/benchmark-outcome.txt" ;;
  esac
  progress "benchmark finished: $scope/$label rc=$rc outcome=$(cat "$dir/benchmark-outcome.txt")"
  case "$rc" in
    0|3) return 0 ;;
    *) return "$rc" ;;
  esac
}

run_bench() {
  run_bench_at pipeline "$@"
}


pick_kernel_models() {
  local available model count=0
  available="$(installed_prod_models || true)"
  for model in \
    prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl \
    prod-lfm25-8b-a1b-liquidai-q6-k \
    prod-gpt-oss20b-ggml-org-mxfp4; do
    if grep -Fxq "$model" <<<"$available"; then
      printf '%s\n' "$model"
      count=$((count + 1))
    fi
  done
  if ((count == 0)) && [[ -n $available ]]; then
    head -n 3 <<<"$available"
  fi
}

pick_governor_models() {
  local available model count=0
  available="$(installed_prod_models || true)"
  for model in \
    prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl \
    prod-lfm25-8b-a1b-liquidai-q6-k \
    prod-qwen35-9b-unsloth-q6-k; do
    if grep -Fxq "$model" <<<"$available"; then
      printf '%s\n' "$model"
      count=$((count + 1))
      ((count >= 2)) && return 0
    fi
  done
  if ((count == 0)) && [[ -n $available ]]; then
    head -n 2 <<<"$available"
  fi
}

run_kernel_profile_benchmark() {
  local scope="$1" label="$2"
  local -a models=()
  mapfile -t models < <(pick_kernel_models)
  if ((${#models[@]} == 0)); then
    install -d -m 0700 "$RAW/$scope/benchmark"
    echo 'SKIP: no production models registered on main Ollama' > "$RAW/$scope/benchmark/benchmark-skipped.txt"
    return 0
  fi
  run_bench_at "$scope" benchmark env \
    BOARD_NOTE="bc250-revalidation-v${HARNESS_VERSION} kernel=$label running=$(uname -r)" \
    BENCH_MODE=neutral BENCH_PROFILE=conservative \
    RUN_LATENCY=0 RUN_CONTEXT=1 RUN_THERMAL=0 REPEATS=1 \
    PREFILL_SENTENCES=220 CTX_POINTS='352 704' \
    NUM_PREDICT_SHORT=96 NUM_PREDICT_PREFILL=16 NUM_PREDICT_CONTEXT=48 \
    REQUEST_TIMEOUT=1200 \
    bc250-benchmark generation "${models[@]}"
}

performance_off() {
  command_exists cyan-skillfish-performance-mode || return 0
  cyan-skillfish-performance-mode --off >/dev/null 2>&1 || true
}

run_governor_benchmark() {
  local label="$1" action="$2" frequency="${3:-}" scope="kernel-restored/governor-$1"
  local -a models=()
  install -d -m 0700 "$RAW/$scope"
  mapfile -t models < <(pick_governor_models)
  if ((${#models[@]} == 0)); then
    echo 'SKIP: no production models registered on main Ollama' > "$RAW/$scope/skipped.txt"
    return 0
  fi

  performance_off
  case "$action" in
    busy) : ;;
    performance)
      if ! cyan-skillfish-performance-mode --on > "$RAW/$scope/mode-set.txt" 2>&1; then
        echo 'SKIP: performance mode could not be enabled' >> "$RAW/$scope/mode-set.txt"
        return 0
      fi
      ;;
    fixed)
      if ! cyan-skillfish-performance-mode --fixed-frequency "$frequency" > "$RAW/$scope/mode-set.txt" 2>&1; then
        echo "SKIP: fixed frequency $frequency MHz could not be enabled" >> "$RAW/$scope/mode-set.txt"
        performance_off
        return 0
      fi
      ;;
    *) echo "ERROR: unknown governor action $action" >&2; return 1 ;;
  esac
  sleep 2
  cyan-skillfish-performance-mode --status > "$RAW/$scope/mode-status.txt" 2>&1 || true
  run_bench_at "$scope" benchmark env \
    BOARD_NOTE="bc250-revalidation-v${HARNESS_VERSION} governor=$label running=$(uname -r)" \
    BENCH_MODE=neutral BENCH_PROFILE=conservative \
    RUN_LATENCY=0 RUN_CONTEXT=0 RUN_THERMAL=0 REPEATS=1 \
    PREFILL_SENTENCES=352 NUM_PREDICT_SHORT=96 NUM_PREDICT_PREFILL=24 \
    REQUEST_TIMEOUT=1200 \
    bc250-benchmark generation "${models[@]}"
  performance_off
}

phase_kernel_baseline() {
  set_phase kernel-baseline "testing current TTM-only kernel baseline on $(uname -r)"
  check_running_kernel
  verify_running_profile "$(saved_original_args_string)"
  ensure_normal_mode
  snapshot kernel-baseline/snapshot
  run_kernel_profile_benchmark kernel-baseline current-ttm-only
  write_phase_report kernel-baseline-ttm-only kernel-baseline
  apply_profile_next_boot "$LEGACY_FULL_PROFILE"
  request_reboot kernel-full
}

phase_kernel_full() {
  set_phase kernel-full "testing historical full memory profile on $(uname -r)"
  check_running_kernel
  verify_running_profile "$LEGACY_FULL_PROFILE"
  ensure_normal_mode
  snapshot kernel-full/snapshot
  run_kernel_profile_benchmark kernel-full legacy-full
  write_phase_report kernel-legacy-full-profile kernel-full
  restore_original_next_boot
  request_reboot kernel-restored
}

phase_kernel_restored() {
  set_phase kernel-restored "verifying exact original TTM-only profile and governor behavior"
  check_running_kernel
  verify_running_profile "$(saved_original_args_string)"
  ensure_normal_mode
  snapshot kernel-restored/before-governor
  if ((RUN_GOVERNOR_REVALIDATION)); then
    run_governor_benchmark busy-flag-current busy
    run_governor_benchmark performance-max performance
    run_governor_benchmark fixed-1750 fixed 1750
    run_governor_benchmark fixed-1850 fixed 1850
    performance_off
  else
    install -d -m 0700 "$RAW/kernel-restored"
    echo 'SKIP: RUN_GOVERNOR_REVALIDATION=0' > "$RAW/kernel-restored/governor-skipped.txt"
  fi
  snapshot kernel-restored/final
  write_phase_report kernel-restored-governor-results kernel-restored
}


phase_governor_current_only() {
  set_phase governor-current "testing governor behavior on current kernel $(uname -r) without kernel-profile A/B"
  ensure_normal_mode
  snapshot kernel-restored/before-governor
  run_governor_benchmark busy-flag-current busy
  run_governor_benchmark performance-max performance
  run_governor_benchmark fixed-1750 fixed 1750
  run_governor_benchmark fixed-1850 fixed 1850
  performance_off
  snapshot kernel-restored/final
  write_phase_report current-kernel-governor-results kernel-restored
}

unload_model() {
  local port="$1" model="$2" payload
  payload="$(jq -nc --arg model "$model" '{model:$model,prompt:"",stream:false,keep_alive:0}')"
  curl -fsS --connect-timeout 2 --max-time 30 \
    -H 'Content-Type: application/json' -d "$payload" \
    "http://127.0.0.1:${port}/api/generate" >/dev/null 2>&1 || true
}

warm_embedding() {
  [[ -x $HELPER ]] || return 1
  model_registered 11437 "$EMBED_MODEL" || return 1
  "$HELPER" embed-warm --model "$EMBED_MODEL" --keep-alive 10m
}

ensure_normal_mode() {
  if systemctl cat ollama-agent.service >/dev/null 2>&1; then
    bc250-agent-mode leave >/dev/null 2>&1 || true
  fi
  systemctl start ollama.service >/dev/null
  systemctl cat ollama-task.service >/dev/null 2>&1 && systemctl start ollama-task.service >/dev/null || true
  systemctl cat ollama-embedding.service >/dev/null 2>&1 && systemctl start ollama-embedding.service >/dev/null || true
  systemctl start tika.service open-webui.service nginx.service >/dev/null
  wait_api 11434 45 || return 1
  if systemctl cat ollama-task.service >/dev/null 2>&1; then
    wait_api 11435 45 || return 1
  fi
  if systemctl cat ollama-embedding.service >/dev/null 2>&1; then
    wait_api 11437 45 || return 1
  fi
  local i
  for i in {1..60}; do
    curl -fsS --connect-timeout 2 --max-time 4 http://127.0.0.1:3000/ >/dev/null 2>&1 && break
    sleep 1
  done
  curl -fsS --connect-timeout 2 --max-time 4 http://127.0.0.1:3000/ >/dev/null 2>&1 || return 1
  curl -fsS --connect-timeout 2 --max-time 4 http://127.0.0.1/ >/dev/null 2>&1 || return 1
}

container_env_value() {
  local key="$1"
  podman inspect open-webui --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | \
    awk -F= -v k="$key" '$1==k{v=$2} END{print v}'
}

check_openwebui_bootstrap_env() {
  local out="$RAW/baseline/openwebui-bootstrap-contract.txt" key expected actual failures=0
  : > "$out"
  while IFS='|' read -r key expected; do
    actual="$(container_env_value "$key")"
    printf '%s expected=%s actual=%s\n' "$key" "$expected" "${actual:-missing}" >> "$out"
    if [[ ${actual,,} != "${expected,,}" ]]; then
      failures=$((failures + 1))
    fi
  done <<'EOFENV'
OFFLINE_MODE|true
HF_HUB_OFFLINE|1
ENABLE_OPENAI_API|false
ENABLE_DIRECT_CONNECTIONS|false
ENABLE_CODE_EXECUTION|false
ENABLE_CODE_INTERPRETER|false
RAG_EMBEDDING_ENGINE|ollama
RAG_EMBEDDING_MODEL|embed-jina-v5-small-retrieval-q4-k-m
RAG_OLLAMA_BASE_URL|http://host.containers.internal:11437
RAG_EMBEDDING_BATCH_SIZE|1
ENABLE_ASYNC_EMBEDDING|false
CHUNK_MIN_SIZE_TARGET|0
RAG_SYSTEM_CONTEXT|false
CONTENT_EXTRACTION_ENGINE|tika
EOFENV
  printf 'failures=%d\n' "$failures" >> "$out"
  ((failures == 0))
}

phase_baseline() {
  set_phase baseline "restoring and validating normal mode"
  ensure_normal_mode
  [[ $(systemctl is-active ollama-agent.service 2>/dev/null || true) != active ]]
  install -d -m 0700 "$RAW/baseline"
  check_openwebui_bootstrap_env
  snapshot baseline
  write_phase_report normal-pipeline-baseline baseline
}

phase_pipeline() {
  set_phase pipeline "testing normal main/task/embedding pipeline"
  local all_roles=1 kdir m sampler_pid unloaded_at=""
  local -a prod=()
  install -d -m 0700 "$RAW/pipeline"

  if model_registered 11437 "$EMBED_MODEL"; then
    warm_embedding > "$RAW/pipeline/embed-warm.txt" 2>&1
    # Routine appliance revalidation checks the promoted embedding model only.
    # Alternate embedding comparisons belong in an explicit model-evaluation run.
    run_bench embeddings bc250-benchmark embeddings "$EMBED_MODEL"
  else
    echo "SKIP: $EMBED_MODEL is not registered on 11437" > "$RAW/pipeline/embeddings-skipped.txt"
  fi

  if api_ready 11435 && model_registered 11435 "$TASK_MODEL"; then
    # The LFM task candidate is already exhausted; routine qualification should
    # test the actual promoted Open WebUI task model instead of repeating it.
    run_bench task bc250-benchmark task "$TASK_MODEL"
  else
    echo "SKIP: promoted task model $TASK_MODEL is not available on 11435" > "$RAW/pipeline/task-skipped.txt"
  fi

  if model_registered 11434 prod-lfm25-8b-a1b-liquidai-q6-k; then
    run_bench translation-implicit bc250-benchmark translation
    run_bench translation-explicit env TRANSLATION_EXPLICIT_DIRECTION=1 bc250-benchmark translation
  else
    echo "SKIP: production LFM translation model not installed" > "$RAW/pipeline/translation-skipped.txt"
  fi

  if model_registered 11437 "$EMBED_MODEL" && model_registered 11434 "$E4B_MODEL"; then
    warm_embedding >/dev/null 2>&1 || true
    run_bench rag-quality bc250-benchmark rag-quality "$EMBED_MODEL" "$E4B_MODEL"
  else
    echo "SKIP: Jina/E4B pair not fully installed" > "$RAW/pipeline/rag-quality-skipped.txt"
  fi

  mapfile -t prod < <(installed_prod_models)
  if ((RUN_PRODUCTION_GENERATION)) && ((${#prod[@]})); then
    warm_embedding >/dev/null 2>&1 || true
    run_bench production-generation env BENCH_MODE=production BENCH_PROFILE=conservative RUN_THERMAL=0 REPEATS=1 bc250-benchmark generation "${prod[@]}"
    api_ready 11434 || ensure_normal_mode
  fi

  # Role acceptance is useful only when the complete production set is present.
  for m in "$E2B_MODEL" "$E4B_MODEL" prod-lfm25-8b-a1b-liquidai-q6-k prod-qwen35-9b-unsloth-q6-k "$GPT_OSS_MODEL"; do
    model_registered 11434 "$m" || all_roles=0
  done
  ((all_roles)) && run_bench production-usecase bc250-benchmark usecase || echo "SKIP: complete production role set not installed" > "$RAW/pipeline/usecase-skipped.txt"

  if ((RUN_WARM_PREFIX)) && model_registered 11434 "$E4B_MODEL"; then
    warm_embedding >/dev/null 2>&1 || true
    run_bench warm-prefix env BENCH_MODE=production BENCH_PROFILE=conservative RUN_LATENCY=0 RUN_CONTEXT=0 RUN_THERMAL=0 RUN_WARM_PREFIX=1 REPEATS=1 bc250-benchmark generation "$E4B_MODEL"
  fi

  if model_registered 11434 "$GPT_OSS_MODEL"; then
    warm_embedding >/dev/null 2>&1 || true
    run_bench gpt-oss-embedding-headroom env BENCH_MODE=production BENCH_PROFILE=conservative RUN_LATENCY=0 RUN_CONTEXT=1 RUN_THERMAL=0 REPEATS=1 PREFILL_SENTENCES=352 CTX_POINTS='352 704' NUM_PREDICT_PREFILL=16 NUM_PREDICT_CONTEXT=32 bc250-benchmark generation "$GPT_OSS_MODEL"
    api_ready 11434 || ensure_normal_mode
  else
    echo "SKIP: $GPT_OSS_MODEL not installed; this remains the main post-deployment memory edge case" > "$RAW/pipeline/gpt-oss-skipped.txt"
  fi

  if ((RUN_CONCURRENCY)) && model_registered 11434 "$E2B_MODEL" && model_registered 11437 "$EMBED_MODEL"; then
    progress "testing simultaneous E2B generation + dedicated embedding requests"
    start_sampler "$RAW/pipeline/concurrency-sampler.tsv"
    sampler_pid="$SAMPLER_PID"
    "$HELPER" concurrency --model "$E2B_MODEL" --embed-model "$EMBED_MODEL" --output "$RAW/pipeline/concurrency.json" > "$RAW/pipeline/concurrency-console.txt" 2>&1 || true
    stop_sampler "$sampler_pid"
  fi

  if ((RUN_OCR)) && [[ -n $(first_registered 11434 exp-glm-ocr-) ]]; then
    run_bench ocr bc250-benchmark ocr
  fi

  if ((RUN_KEEPALIVE_EXPIRY)) && model_registered 11437 "$EMBED_MODEL"; then
    progress "testing dedicated embedding 10-minute keepalive"
    kdir="$RAW/pipeline/embedding-keepalive"
    install -d -m 0700 "$kdir"
    warm_embedding > "$kdir/warm.txt" 2>&1
    curl -fsS http://127.0.0.1:11437/api/ps > "$kdir/ps-t0.json"
    sleep 60
    curl -fsS http://127.0.0.1:11437/api/ps > "$kdir/ps-t60.json"
    if jq -e --arg m "$EMBED_MODEL" 'any(.models[]?; (.name | sub(":latest$"; "")) == $m)' "$kdir/ps-t60.json" >/dev/null; then
      echo "resident_t60=yes" >> "$kdir/embedding-keepalive-result.txt"
    else
      echo "resident_t60=no" >> "$kdir/embedding-keepalive-result.txt"
    fi
    progress "embedding still expected resident at t+60s; waiting to observe expiry after the 10-minute keepalive"
    sleep 540
    for elapsed in 600 610 620 630 640 650 660 670 680 690 700 710 720; do
      curl -fsS http://127.0.0.1:11437/api/ps > "$kdir/ps-t${elapsed}.json"
      if ! jq -e --arg m "$EMBED_MODEL" 'any(.models[]?; (.name | sub(":latest$"; "")) == $m)' "$kdir/ps-t${elapsed}.json" >/dev/null; then
        unloaded_at="$elapsed"
        break
      fi
      sleep 10
    done
    if [[ -n $unloaded_at ]]; then
      echo "unloaded_by_s=$unloaded_at" >> "$kdir/embedding-keepalive-result.txt"
    else
      echo "resident_t720=yes" >> "$kdir/embedding-keepalive-result.txt"
    fi
  fi

  snapshot pipeline/final
  write_phase_report normal-pipeline-results pipeline
}

phase_num_batch() {
  set_phase num-batch "testing Ollama long-prefill num_batch candidates"
  local dir="$RAW/num-batch"
  install -d -m 0700 "$dir"
  if ((!RUN_NUM_BATCH)); then
    echo "SKIP: RUN_NUM_BATCH=0" > "$dir/skipped.txt"
  else
    local models=()
    # This diagnostic exists for the large-model/long-prefill edge case.
    # E2B is not a useful proxy; skip the sweep unless GPT-OSS is installed.
    model_registered 11434 "$GPT_OSS_MODEL" && models+=("$GPT_OSS_MODEL")
    if ((${#models[@]})); then
      progress "num_batch sweep: ${models[*]}"
      local sampler_pid rc
      start_sampler "$dir/sampler.tsv"
      sampler_pid="$SAMPLER_PID"
      if timeout 60m "$HELPER" num-batch --models "${models[@]}" --output "$dir/num-batch-results.jsonl" > "$dir/num-batch-console.txt" 2>&1; then
        rc=0
      else
        rc=$?
      fi
      stop_sampler "$sampler_pid"
      echo "$rc" > "$dir/num-batch-exit-status.txt"
    else
      echo "SKIP: GPT-OSS is not registered; num_batch sweep is not useful on E2B alone" > "$dir/skipped.txt"
    fi
  fi
  api_ready 11434 || ensure_normal_mode
  snapshot num-batch/final
  write_phase_report num-batch-results num-batch
}

phase_agent() {
  set_phase agent "testing exclusive coding/agent mode"
  local agent_model dir="$RAW/agent" port
  install -d -m 0700 "$dir"
  if ((!RUN_AGENT)) || ! systemctl cat ollama-agent.service >/dev/null 2>&1; then
    echo "SKIP: agent lane not installed or RUN_AGENT=0" > "$dir/skipped.txt"
  else
    bc250-agent-mode enter > "$dir/agent-mode-enter.txt" 2>&1
    wait_api 11436 45
    for port in 11434 11435 11437; do
      if api_ready "$port"; then
        echo "ERROR: normal Ollama port $port remained available in agent mode." >&2
        return 1
      fi
    done
    bc250-agent-mode status > "$dir/agent-mode-active-status.txt" 2>&1
    snapshot agent/active
    agent_model="$(first_registered 11436 agentic-)"
    if [[ -n $agent_model ]]; then
      run_bench_at agent benchmark env OLLAMA_URL=http://127.0.0.1:11436 bc250-benchmark agent "$agent_model"
    else
      echo "SKIP: no registered agentic model on 11436" > "$dir/agent-model-skipped.txt"
    fi
    bc250-agent-mode leave > "$dir/agent-mode-leave.txt" 2>&1
    wait_api 11434 45
    systemctl cat ollama-task.service >/dev/null 2>&1 && wait_api 11435 45 || true
    systemctl cat ollama-embedding.service >/dev/null 2>&1 && wait_api 11437 45 || true
    [[ $(systemctl is-active ollama-agent.service 2>/dev/null || true) != active ]]
  fi
  snapshot agent/restored
  write_phase_report agent-mode-results agent
}

save_sysctx_state() {
  install -d -m 0755 "$(dirname "$SYSCTX_DROPIN")"
  if [[ -e $SYSCTX_DROPIN ]]; then
    echo present > "$SYSCTX_STATE"
    cp -a "$SYSCTX_DROPIN" "$SYSCTX_BACKUP"
  else
    echo absent > "$SYSCTX_STATE"
    rm -f "$SYSCTX_BACKUP"
  fi
  podman inspect open-webui --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | awk -F= '$1=="RAG_SYSTEM_CONTEXT"{print $2; exit}' > "$WORK/sysctx-original-value" || true
}

set_sysctx() {
  local value="$1"
  cat > "$SYSCTX_DROPIN" <<EOFCTX
[Container]
Environment=RAG_SYSTEM_CONTEXT=$value
EOFCTX
  chmod 0644 "$SYSCTX_DROPIN"
  systemctl daemon-reload
  systemctl restart open-webui.service
  local i actual=""
  for i in {1..60}; do
    curl -fsS --connect-timeout 2 --max-time 4 http://127.0.0.1:3000/ >/dev/null 2>&1 && break
    sleep 1
  done
  actual="$(podman inspect open-webui --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | awk -F= '$1=="RAG_SYSTEM_CONTEXT"{v=$2} END{print v}')"
  [[ ${actual,,} == "${value,,}" ]] || { echo "ERROR: Open WebUI RAG_SYSTEM_CONTEXT expected=$value actual=${actual:-missing}" >&2; return 1; }
}

restore_sysctx() {
  [[ -f $SYSCTX_STATE ]] || return 0
  if [[ $(cat "$SYSCTX_STATE") == present && -f $SYSCTX_BACKUP ]]; then
    cp -a "$SYSCTX_BACKUP" "$SYSCTX_DROPIN"
  else
    rm -f "$SYSCTX_DROPIN"
  fi
  systemctl daemon-reload
  systemctl restart open-webui.service >/dev/null 2>&1 || true
  for _ in {1..60}; do
    curl -fsS --connect-timeout 2 --max-time 4 http://127.0.0.1:3000/ >/dev/null 2>&1 && break
    sleep 1
  done
}

restore_owui_api_config() {
  [[ -s $OWUI_TOKEN && -s $OWUI_CONFIG_SAVE && -x $HELPER ]] || return 0
  "$HELPER" restore-config --token-file "$OWUI_TOKEN" --input "$OWUI_CONFIG_SAVE" >/dev/null 2>&1 || true
}

phase_owui() {
  set_phase owui "testing Open WebUI API baseline and RAG tuning candidates"
  local dir="$RAW/owui" key rc sampler_pid
  install -d -m 0700 "$dir"
  if ((!RUN_OWUI_TUNING)) || [[ ! -s $OWUI_TOKEN ]]; then
    echo "SKIP: authenticated OWUI tuning tests require --owui-token-file and RUN_OWUI_TUNING=1" > "$dir/skipped.txt"
    snapshot owui/skipped
    write_phase_report openwebui-rag-tuning-results owui
    return 0
  fi

  if ! validate_owui_token > "$dir/token-recheck.txt" 2>&1; then
    echo "SKIP: Open WebUI credential is no longer valid; authenticated tuning was not run" > "$dir/skipped.txt"
    snapshot owui/skipped-invalid-token
    write_phase_report openwebui-rag-tuning-results owui
    return 0
  fi
  key="$(<"$OWUI_TOKEN")"
  OWUI_API_KEY="$key" bc250-openwebui-setup status > "$dir/package-drift-before.txt" 2>&1 || true
  "$HELPER" save-config --token-file "$OWUI_TOKEN" --output "$OWUI_CONFIG_SAVE"

  if ((RUN_EMBED_BATCH_SWEEP)); then
    progress "Open WebUI embedding batch sweep 1/4/8/16"
    start_sampler "$dir/embedding-batch-sampler.tsv"
    sampler_pid="$SAMPLER_PID"
    if timeout --signal=INT --kill-after=30s 60m "$HELPER" embedding-batch --token-file "$OWUI_TOKEN" --work "$dir/embed-batch-work" --output "$dir/embedding-batch.jsonl" > "$dir/embedding-batch-console.txt" 2>&1; then
      rc=0
    else
      rc=$?
    fi
    stop_sampler "$sampler_pid"
    echo "$rc" > "$dir/embedding-batch-exit-status.txt"
  fi

  if ((RUN_CHUNK_MIN_SWEEP)) && model_registered 11434 "$E4B_MODEL"; then
    progress "Open WebUI CHUNK_MIN_SIZE_TARGET sweep 0/500/750/1000"
    start_sampler "$dir/chunk-min-sampler.tsv"
    sampler_pid="$SAMPLER_PID"
    if timeout --signal=INT --kill-after=30s 60m "$HELPER" chunk-min --token-file "$OWUI_TOKEN" --work "$dir/chunk-min-work" --model "$E4B_MODEL" --output "$dir/chunk-min.jsonl" > "$dir/chunk-min-console.txt" 2>&1; then
      rc=0
    else
      rc=$?
    fi
    stop_sampler "$sampler_pid"
    echo "$rc" > "$dir/chunk-min-exit-status.txt"
  fi

  # Helper sweeps restore their own field, then restore the exact original selected
  # API config once more before the environment-level system-context A/B.
  restore_owui_api_config

  if ((RUN_RAG_SYSTEM_CONTEXT)) && model_registered 11434 "$E4B_MODEL"; then
    save_sysctx_state
    progress "RAG_SYSTEM_CONTEXT=false API conversation"
    set_sysctx false
    unload_model 11434 "$E4B_MODEL"
    snapshot owui/sysctx-false-before
    start_sampler "$dir/rag-system-context-false-sampler.tsv"
    sampler_pid="$SAMPLER_PID"
    if timeout --signal=INT --kill-after=30s 45m "$HELPER" rag-sysctx --token-file "$OWUI_TOKEN" --work "$dir/sysctx-work" --model "$E4B_MODEL" --label false --output "$dir/rag-system-context-false.json" > "$dir/rag-system-context-false-console.txt" 2>&1; then
      rc=0
    else
      rc=$?
    fi
    stop_sampler "$sampler_pid"
    echo "$rc" > "$dir/rag-system-context-false-exit-status.txt"

    progress "RAG_SYSTEM_CONTEXT=true API conversation"
    set_sysctx true
    unload_model 11434 "$E4B_MODEL"
    snapshot owui/sysctx-true-before
    start_sampler "$dir/rag-system-context-true-sampler.tsv"
    sampler_pid="$SAMPLER_PID"
    if timeout --signal=INT --kill-after=30s 45m "$HELPER" rag-sysctx --token-file "$OWUI_TOKEN" --work "$dir/sysctx-work" --model "$E4B_MODEL" --label true --output "$dir/rag-system-context-true.json" > "$dir/rag-system-context-true-console.txt" 2>&1; then
      rc=0
    else
      rc=$?
    fi
    stop_sampler "$sampler_pid"
    echo "$rc" > "$dir/rag-system-context-true-exit-status.txt"

    restore_sysctx
    rm -f "$SYSCTX_STATE"
    progress "RAG_SYSTEM_CONTEXT original Quadlet state restored"
  fi

  restore_owui_api_config
  OWUI_API_KEY="$key" bc250-openwebui-setup status > "$dir/package-drift-after.txt" 2>&1 || true
  snapshot owui/restored
  write_phase_report openwebui-rag-tuning-results owui
}

create_summary() {
  local out="$WORK/revalidation-summary.txt"
  {
    echo "BC-250 0.10.0 revalidation v$HARNESS_VERSION"
    echo "run_id=$(run_id)"
    echo "finished=$(now)"
    echo "package=$(rpm -q bc250-llm-server 2>/dev/null || true)"
    echo "kernel=$(uname -r)"
    echo
    if [[ -r $TARGET_KERNEL_FILE ]]; then
      echo "kernel_target=$(target_kernel)"
      echo "kernel_original_relevant_args=$(saved_original_args | paste -sd' ' -)"
      echo
    fi
    echo "Key result locations:"
    find "$RAW" -type f \( -name 'results*.csv' -o -name '*-results.jsonl' -o -name 'concurrency.json' -o -name 'embedding-batch.jsonl' -o -name 'chunk-min.jsonl' -o -name 'rag-system-context-*.json' -o -name 'embedding-keepalive-result.txt' \) -printf '  %p\n' | sort
    echo
    echo "Interpretation notes:"
    echo "- Optional kernel A/B reuses the original compact benchmark shape for cross-kernel comparison; the package default remains TTM-only."
    echo "- legacy-full is a diagnostic comparison profile only, not a recommendation. The redundant no-gtt/full-ppfeaturemask lane was retired after repeated equivalence."
    echo "- Compare production/GPT-OSS results with embedding 11437 warm; do not add Linux+GTT+Ollama memory as separate pools."
    echo "- Translation acceptance is quality data: a benchmark exit 3 must not abort the harness. Inspect direction/language and preservation failures separately."
    echo "- Embedding reports include allocated_context/resident_size; flag unexpectedly large context residency because the dedicated lane is intended to stay small."
    echo "- num_batch is diagnostic: prefer the largest stable/default setting unless 128/256 materially improves long-prefill reliability with acceptable speed."
    echo "- embedding batch 1/4/8/16: compare process_wall_s, errors, memory pressure and service logs; do not promote on speed alone."
    echo "- CHUNK_MIN_SIZE_TARGET: prefer 0 unless a nonzero target improves the deterministic cases without losing facts/citations."
    echo "- RAG quality records retrieval_ok, answer/thinking sizes and done_reason separately; length exhaustion with correct retrieval is not a retrieval failure."
    echo "- RAG_SYSTEM_CONTEXT: focus on turns 2/3 prompt_eval_duration and wall_s plus answer/citation correctness; turn 1 includes cold/load noise."
    echo "- Agent mode must show only 11436 during its active snapshot and must restore normal lanes afterward."
  } > "$out"
}

FINAL_BUNDLE=""

create_final_bundle() {
  local bundle tmp
  bundle="$REPORT_DIR/$(run_id)-bc250-revalidation-results.tar.gz"
  tmp="${bundle}.tmp.$$"
  create_summary
  progress "creating final bundle"
  # Do not bundle OWUI_CONFIG_SAVE: a customized provider config could contain a secret.
  local -a items=(events.log phase stage heartbeat run-id settings.env revalidation-summary.txt results phase-reports)
  [[ ! -e $TARGET_KERNEL_FILE ]] || items+=(target-kernel)
  [[ ! -e $ORIGINAL_ARGS_FILE ]] || items+=(original-kernel-args.txt)
  [[ ! -e $FAILURE_RC_FILE ]] || items+=(failure-rc)
  rm -f "$tmp"
  tar -C "$WORK" -czf "$tmp" "${items[@]}"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$bundle"
  FINAL_BUNDLE="$bundle"
  progress "final bundle written: $bundle"
}

restore_all() {
  local had_errexit=0
  [[ $- == *e* ]] && had_errexit=1
  set +e
  if command_exists bc250-agent-mode; then bc250-agent-mode leave >/dev/null 2>&1; fi
  restore_sysctx
  restore_owui_api_config
  rm -f "$OWUI_TOKEN"
  if ((had_errexit)); then set -e; else set +e; fi
}

disable_worker_for_future_boots() {
  systemctl disable "$UNIT" >/dev/null 2>&1 || true
}

cleanup_transient_run() {
  local bundle="${FINAL_BUNDLE:-}"
  disable_worker_for_future_boots
  rm -f "$OWUI_TOKEN" "$UNIT_PATH"
  systemctl daemon-reload >/dev/null 2>&1 || true
  rm -rf "$WORK" "$RUN_DIR"
  [[ -z $bundle ]] || echo "Final bundle: $bundle"
}

finish_failed_run() {
  local rc="$1" label="$2" snapshot_needed="${3:-1}"
  printf '%s\n' "$rc" > "$FAILURE_RC_FILE"
  performance_off
  restore_all
  ensure_normal_mode >/dev/null 2>&1 || true
  if ((snapshot_needed)); then
    snapshot "$label"
    write_phase_report "$label-results" "$label"
  fi
  printf 'failed\n' > "$PHASE_FILE"
  create_final_bundle
  cleanup_transient_run
  exit "$rc"
}

recover_kernel_or_finish_failure() {
  local rc="$1" label="$2" snapshot_taken=0
  printf '%s\n' "$rc" > "$FAILURE_RC_FILE"
  performance_off
  restore_all

  # The target entry may already contain the next candidate profile even while the
  # currently running /proc/cmdline still shows the original profile. Always put
  # the exact saved arguments back on that target before deciding whether a
  # recovery reboot is required.
  if [[ -r $ORIGINAL_ARGS_FILE && -r $TARGET_KERNEL_FILE ]]; then
    snapshot "$label"
    write_phase_report "$label-results" "$label"
    snapshot_taken=1
    if ! restore_original_next_boot; then
      progress "CRITICAL: could not restore saved kernel arguments; manual recovery required"
      printf 'failed-manual-kernel-recovery\n' > "$PHASE_FILE"
      create_final_bundle
      cleanup_transient_run
      exit "$rc"
    fi
    if kernel_profile_modified; then
      printf 'recovery\n' > "$PHASE_FILE"
      progress "exact original kernel arguments configured after $label; rebooting for recovery verification"
      sync
      systemctl reboot --no-block
      exit 0
    fi
  fi
  finish_failed_run "$rc" "$label" "$((1 - snapshot_taken))"
}

worker_fail() {
  local rc="${1:-1}"
  trap - ERR TERM INT
  set +e
  # ERR is inherited into functions/subshells because the harness uses errtrace.
  # An on-disk guard prevents nested/parent handlers from repeating cleanup.
  if ! mkdir "$FAILURE_GUARD" 2>/dev/null; then
    exit "$rc"
  fi
  progress "worker failure rc=$rc; restoring temporary state"
  recover_kernel_or_finish_failure "$rc" failure
}

worker_abort() {
  trap - ERR TERM INT
  set +e
  printf 'abort\n' > "$WORK/ABORT"
  progress "worker interrupted/aborted; restoring temporary state"
  recover_kernel_or_finish_failure 130 aborted
}

phase_recovery() {
  local rc=1
  [[ -r $FAILURE_RC_FILE ]] && rc="$(cat "$FAILURE_RC_FILE")"
  set_phase recovery "verifying exact original kernel profile after recovery reboot"
  check_running_kernel
  verify_running_profile "$(saved_original_args_string)"
  performance_off
  restore_all
  ensure_normal_mode
  snapshot recovery
  write_phase_report kernel-recovery-results recovery
  printf 'failed-recovered\n' > "$PHASE_FILE"
  progress "recovery complete; original kernel profile and normal mode restored"
  create_final_bundle
  cleanup_transient_run
  trap - ERR TERM INT
  exit "$rc"
}

run_pipeline_sequence() {
  phase_baseline
  check_abort
  phase_pipeline
  check_abort
  phase_num_batch
  check_abort
  phase_agent
  check_abort
  phase_owui
  set_phase final "restoring original temporary state and capturing final snapshot"
  restore_all
  ensure_normal_mode
  performance_off
  if [[ -r $ORIGINAL_ARGS_FILE ]]; then
    verify_running_profile "$(saved_original_args_string)"
  fi
  snapshot final
  write_phase_report final-restored-state final
  printf 'done\n' > "$PHASE_FILE"
  progress "all tests complete; normal mode active; exact kernel/temporary OWUI state restored"
  create_final_bundle
  cleanup_transient_run
  trap - ERR TERM INT
}

worker() {
  need_root
  exec 9>"$LOCK"
  flock -n 9 || { echo "ERROR: another worker holds $LOCK" >&2; exit 1; }
  rm -rf "$FAILURE_GUARD"
  trap 'worker_fail $?' ERR
  trap worker_abort TERM INT
  trap worker_exit_cleanup EXIT
  load_settings
  write_helper
  refresh_owui_token
  progress "worker started pid=$$ boot_id=$(cat /proc/sys/kernel/random/boot_id) kernel=$(uname -r)"

  case "$(cat "$PHASE_FILE" 2>/dev/null || echo unknown)" in
    kernel-baseline) phase_kernel_baseline ;;
    kernel-full) phase_kernel_full ;;
    kernel-restored)
      phase_kernel_restored
      run_pipeline_sequence
      ;;
    pipeline-start)
      ((RUN_GOVERNOR_REVALIDATION)) && phase_governor_current_only
      run_pipeline_sequence
      ;;
    recovery) phase_recovery ;;
    done|failed|failed-recovered)
      disable_worker_for_future_boots
      echo "Run already stopped at phase=$(cat "$PHASE_FILE")."
      ;;
    *) echo "ERROR: unknown phase: $(cat "$PHASE_FILE" 2>/dev/null || echo missing)" >&2; return 1 ;;
  esac
}

status_run() {
  need_root
  echo "harness_version=$HARNESS_VERSION"
  echo "target_version=$TARGET_VERSION"
  echo "run_id=$(run_id)"
  echo "phase=$(cat "$PHASE_FILE" 2>/dev/null || echo none)"
  echo "stage=$(cat "$STAGE_FILE" 2>/dev/null || echo none)"
  echo "heartbeat=$(cat "$HEARTBEAT_FILE" 2>/dev/null || echo none)"
  echo "kernel=$(uname -r)"
  echo "target_kernel=$(target_kernel)"
  echo "current_relevant_args=$(current_relevant_args | paste -sd' ' -)"
  echo "saved_original_args=$(saved_original_args | paste -sd' ' -)"
  echo "service=$(systemctl is-active "$UNIT" 2>/dev/null || true)"
  echo "phase_reports=$(find "$PHASE_REPORT_DIR" -maxdepth 1 -type f -name "$(run_id)-*.txt" 2>/dev/null | wc -l)"
  echo "latest_phase_report=$(find "$PHASE_REPORT_DIR" -maxdepth 1 -type f -name "$(run_id)-*.txt" -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)"
  echo "latest_bundle=$(find "$REPORT_DIR" -maxdepth 1 -type f -name '*-bc250-revalidation-results.tar.gz' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)"
  if [[ -f $RAW/pipeline/embedding-keepalive/embedding-keepalive-result.txt ]]; then
    cat "$RAW/pipeline/embedding-keepalive/embedding-keepalive-result.txt"
  fi
}

abort_run() {
  need_root
  [[ -d $WORK ]] || { echo "No run state found."; exit 0; }
  touch "$WORK/ABORT"
  if systemctl is-active --quiet "$UNIT" 2>/dev/null; then
    systemctl kill --kill-who=main --signal=TERM "$UNIT" || true
  else
    set +e
    recover_kernel_or_finish_failure 130 aborted
  fi
  echo "Abort requested; the worker will restore the exact saved kernel/temporary state before stopping."
}

cleanup_run() {
  need_root
  if systemctl is-active --quiet "$UNIT" 2>/dev/null; then
    echo "ERROR: worker is still active; abort it first." >&2
    exit 1
  fi
  restore_all || true
  disable_worker_for_future_boots
  rm -f "$UNIT_PATH"
  systemctl daemon-reload
  systemctl reset-failed "$UNIT" >/dev/null 2>&1 || true
  rm -rf "$WORK" "$RUN_DIR"
  echo "Removed revalidation work state/unit. Result bundles under $REPORT_DIR were retained."
}

case "${1:-}" in
  start) start_run "$@" ;;
  worker) worker ;;
  status) status_run ;;
  abort) abort_run ;;
  cleanup) cleanup_run ;;
  help|-h|--help|'') usage ;;
  *) usage >&2; exit 2 ;;
esac
