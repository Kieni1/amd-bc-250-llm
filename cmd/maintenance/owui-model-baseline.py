#!/usr/bin/env python3
"""Apply package-owned Open WebUI model parameters that cannot live in Modelfiles."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

QWEN_MODEL = "prod-qwen35-9b-unsloth-q6-k:latest"
QWEN_NAME = "Office – Advanced (Qwen3.5 9B)"


class BaselineError(RuntimeError):
    pass


def api_request(
    base_url: str,
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    allow_not_found: bool = False,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(base_url.rstrip("/") + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
    except HTTPError as exc:
        if allow_not_found and exc.code == 404:
            return None
        detail = exc.read().decode("utf-8", "replace")
        raise BaselineError(f"Open WebUI {method} {path} failed: HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise BaselineError(f"Open WebUI is unreachable at {base_url}: {exc.reason}") from exc
    return json.loads(raw) if raw else None


def _provider_model(base_url: str, token: str, model_id: str) -> dict[str, Any]:
    result = api_request(base_url, token, "GET", "/api/models?refresh=true")
    rows = result.get("data", []) if isinstance(result, dict) else []
    for row in rows:
        if isinstance(row, dict) and row.get("id") == model_id:
            return row
    raise BaselineError(
        f"provider model {model_id!r} is not visible in Open WebUI; install/register it first"
    )


def _workspace_model(base_url: str, token: str, model_id: str) -> dict[str, Any] | None:
    query = urlencode({"id": model_id})
    result = api_request(
        base_url,
        token,
        "GET",
        f"/api/v1/models/model?{query}",
        allow_not_found=True,
    )
    return result if isinstance(result, dict) else None


def qwen_form(provider: dict[str, Any], current: dict[str, Any] | None) -> dict[str, Any]:
    params = dict((current or {}).get("params") or {})
    custom = params.get("custom_params") or {}
    if isinstance(custom, str):
        try:
            custom = json.loads(custom)
        except json.JSONDecodeError:
            custom = {}
    if not isinstance(custom, dict):
        custom = {}
    custom["think"] = False
    params["custom_params"] = custom
    return {
        "id": QWEN_MODEL,
        "base_model_id": None,
        "name": (current or {}).get("name") or provider.get("name") or QWEN_NAME,
        "meta": dict((current or {}).get("meta") or {}),
        "params": params,
        # Open WebUI 0.11.2's update path expects this field even when empty.
        "access_grants": list((current or {}).get("access_grants") or []),
        "is_active": bool((current or {}).get("is_active", True)),
    }


def apply_baseline(base_url: str, token: str) -> str:
    provider = _provider_model(base_url, token, QWEN_MODEL)
    current = _workspace_model(base_url, token, QWEN_MODEL)
    form = qwen_form(provider, current)
    endpoint = "/api/v1/models/model/update" if current else "/api/v1/models/create"
    result = api_request(base_url, token, "POST", endpoint, form)
    if not isinstance(result, dict) or result.get("id") != QWEN_MODEL:
        raise BaselineError("Open WebUI did not return the configured Qwen model record")
    return "updated" if current else "created"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply the BC-250 Open WebUI production model baseline."
    )
    parser.add_argument("--url", default=os.environ.get("OWUI_URL", "http://127.0.0.1:3000"))
    args = parser.parse_args()
    token = os.environ.get("OWUI_API_KEY", "").strip()
    if not token or token == "REPLACE_WITH_ADMIN_API_KEY":
        print("ERROR: OWUI_API_KEY must contain an Open WebUI administrator API key.", file=sys.stderr)
        return 2
    try:
        action = apply_baseline(args.url, token)
    except (BaselineError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"{action} {QWEN_MODEL}: Open WebUI custom parameter think=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
