"""BC-250 runtime compatibility guard for the pinned Open WebUI/Tika path.

Open WebUI 0.12.5's Tika 4 loader treats an HTTP 2xx response without a usable
``tk:content`` field as the literal placeholder ``<No text content found>``.
That placeholder is then non-empty and can be stored/indexed as if extraction
succeeded.  BC-250 keeps the upstream image immutable and applies this narrow
request-layer guard through Python's normal ``sitecustomize`` hook instead.

The guard is deliberately scoped to the Tika 4 Markdown endpoint used by the
pinned Open WebUI release.  It leaves all other requests untouched and turns
only missing/blank/placeholder extraction responses into an HTTP-style failure
that the upstream loader already handles correctly.
"""

from __future__ import annotations

from typing import Any

TIKA4_MARKDOWN_SUFFIX = "/tika/json/md"
NO_TEXT_PLACEHOLDER = "<No text content found>"
NO_USABLE_TEXT_REASON = (
    "Document extraction failed: no usable text was found. "
    "The file may be empty, corrupted, image-only, or unsupported."
)
DUPLICATE_CONTENT_REASON = (
    "Duplicate document content — this content is already present in the "
    "knowledge collection."
)


def _tika4_markdown_url(url: object) -> bool:
    return isinstance(url, str) and url.rstrip("/").endswith(TIKA4_MARKDOWN_SUFFIX)


def _usable_tika4_content(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    content = payload.get("tk:content")
    if not isinstance(content, str):
        return False
    normalized = content.strip()
    return bool(normalized) and normalized != NO_TEXT_PLACEHOLDER


class _OpenWebUIErrorMessagesProxy:
    """Override only BC-250-owned UX wording while preserving upstream errors."""

    def __init__(self, upstream: Any) -> None:
        self._upstream = upstream

    def __getattr__(self, name: str) -> Any:
        return getattr(self._upstream, name)

    @property
    def DUPLICATE_CONTENT(self) -> str:
        return DUPLICATE_CONTENT_REASON


def install_openwebui_error_wording() -> None:
    """Install narrow wording overrides for the pinned Open WebUI backend."""
    try:
        from open_webui import constants as openwebui_constants
    except ImportError:
        # The compatibility hook may be imported before Open WebUI is available.
        # Leave application import failures to Open WebUI itself.
        return

    current = openwebui_constants.ERROR_MESSAGES
    if isinstance(current, _OpenWebUIErrorMessagesProxy):
        return
    openwebui_constants.ERROR_MESSAGES = _OpenWebUIErrorMessagesProxy(current)


def install_tika_empty_content_guard(requests_module: Any | None = None) -> None:
    """Install the narrow Tika-4 empty-content guard exactly once."""
    if requests_module is None:
        try:
            import requests as requests_module  # type: ignore[no-redef]
        except ImportError:
            # Open WebUI owns the requests dependency.  If it is unavailable,
            # leave the application to report its own dependency failure.
            return

    original_put = requests_module.put
    if getattr(original_put, "_bc250_tika_empty_content_guard", False):
        return

    def guarded_put(url: object, *args: Any, **kwargs: Any) -> Any:
        response = original_put(url, *args, **kwargs)
        if not _tika4_markdown_url(url) or not getattr(response, "ok", False):
            return response
        try:
            payload = response.json()
        except ValueError:
            # requests raises a ValueError-compatible JSON decode exception;
            # preserve the upstream response/evidence instead of rewriting it.
            return response
        if _usable_tika4_content(payload):
            return response

        # requests.Response.ok is derived from status_code.  Turning this one
        # semantically-empty 2xx into 422 routes execution through Open WebUI's
        # existing Tika error path without replacing the upstream loader.
        response.status_code = 422
        response.reason = NO_USABLE_TEXT_REASON
        return response

    guarded_put._bc250_tika_empty_content_guard = True  # type: ignore[attr-defined]
    requests_module.put = guarded_put


install_openwebui_error_wording()
install_tika_empty_content_guard()
