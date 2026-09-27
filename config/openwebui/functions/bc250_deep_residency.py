"""BC-250 Deep admission guard: evict competing lanes before GPT-OSS starts."""

import json
from urllib import error, request

DEEP_MODELS = {
    "bc250-office-deep-reasoning",
    "prod-gpt-oss20b-ggml-org-mxfp4:latest",
}
TASK_URL = "http://host.containers.internal:11435"
EMBED_URL = "http://host.containers.internal:11437"
TIMEOUT = 20


def _json_call(base: str, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with request.urlopen(req, timeout=TIMEOUT) as response:
            body = response.read().decode("utf-8")
    except (OSError, error.URLError) as exc:
        raise RuntimeError(f"BC-250 Deep residency check failed for {base}{path}: {exc}") from exc
    if not body:
        return {}
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise TypeError(f"BC-250 Deep residency check returned invalid JSON from {base}{path}")
    return parsed


def _resident_models(base: str) -> list[str]:
    payload = _json_call(base, "/api/ps")
    models = payload.get("models", [])
    if not isinstance(models, list):
        raise TypeError(f"BC-250 Deep residency check could not parse {base}/api/ps")
    result: list[str] = []
    for item in models:
        if isinstance(item, dict):
            name = item.get("name") or item.get("model")
            if isinstance(name, str) and name:
                result.append(name)
    return result


def _unload_task(model: str) -> None:
    _json_call(TASK_URL, "/api/generate", {"model": model, "prompt": "", "stream": False, "keep_alive": 0})


def _unload_embedding(model: str) -> None:
    _json_call(EMBED_URL, "/api/embed", {"model": model, "input": "", "keep_alive": 0})


def ensure_competing_lanes_clear() -> None:
    for model in _resident_models(EMBED_URL):
        _unload_embedding(model)
    remaining_embed = _resident_models(EMBED_URL)
    if remaining_embed:
        raise RuntimeError(
            "BC-250 Deep startup deferred: embedding residency could not be cleared: "
            + ", ".join(remaining_embed)
        )

    for model in _resident_models(TASK_URL):
        _unload_task(model)
    remaining_task = _resident_models(TASK_URL)
    if remaining_task:
        raise RuntimeError(
            "BC-250 Deep startup deferred: task residency could not be cleared: "
            + ", ".join(remaining_task)
        )


class Filter:
    async def inlet(self, body: dict) -> dict:
        model_id = body.get("model")
        if model_id not in DEEP_MODELS:
            raise ValueError(f"BC-250 Deep residency filter attached to unexpected model: {model_id!r}")
        ensure_competing_lanes_clear()
        return body
