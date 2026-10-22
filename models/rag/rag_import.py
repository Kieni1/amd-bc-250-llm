"""Metadata-aware Open WebUI knowledge importer for the BC-250 document tree."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import stat
import sys
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

DEFAULT_ROOT = Path(os.environ.get("BC250_RAG_ROOT", "/srv/bc250-documents"))
DEFAULT_URL = os.environ.get("OPEN_WEBUI_URL", "http://127.0.0.1:3000").rstrip("/")
SCOPES = ("public", "confidential")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
TOP_LEVEL_KEYS = {
    "document_id",
    "revision_id",
    "document_family",
    "title",
    "organisation",
    "language",
    "document_type",
    "edition",
    "approved_on",
    "effective_from",
    "status",
    "review_required",
    "authority",
    "authority_role",
    "translation_of",
    "source_file",
    "source_sha256",
    "normalization",
    "relation",
}
RELATION_KEYS = {"type", "counterpart", "source_language"}


def knowledge_name(scope: str, collection: str, lane: str) -> str:
    suffix = "Originals" if lane == "original" else "Français"
    return f"[{scope.upper()}] {collection} — {suffix}"


def knowledge_description(scope: str, collection: str, lane: str) -> str:
    base = f"BC-250 managed RAG import from {scope}/{collection}/active."
    if lane == "original":
        return (
            base
            + " Authoritative German originals; use for German and English queries."
        )
    return (
        base
        + " French translations; use for French queries. German originals remain authoritative on conflict."
    )


@dataclass(frozen=True)
class Document:
    path: Path
    scope: str
    collection: str
    lane: str
    language: str
    source_file: str
    source_sha256: str

    @property
    def kb_name(self) -> str:
        return knowledge_name(self.scope, self.collection, self.lane)

    @property
    def kb_description(self) -> str:
        return knowledge_description(self.scope, self.collection, self.lane)


def _unquote(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    if value.startswith('"'):
        if not value.endswith('"'):
            raise ValueError("unterminated double-quoted front-matter scalar")
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid double-quoted front-matter scalar: {exc.msg}") from exc
        if not isinstance(decoded, str):
            raise ValueError("front-matter quoted scalar must decode to a string")
        return decoded
    if value.startswith("'"):
        if not value.endswith("'"):
            raise ValueError("unterminated single-quoted front-matter scalar")
        return value[1:-1].replace("''", "'")
    if value.endswith(('"', "'")):
        raise ValueError("mismatched quote in front-matter scalar")
    return value


def validate_iso_date(value: object, field: str) -> str:
    """Return a real ISO calendar date or raise a metadata error."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be a real YYYY-MM-DD calendar date") from exc
    if parsed.isoformat() != text:
        raise ValueError(f"{field} must use canonical YYYY-MM-DD form")
    return text


def front_matter(path: Path) -> dict[str, object]:
    """Parse the deliberately small YAML subset documented for RAG metadata."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing YAML front matter")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("unterminated YAML front matter") from exc

    data: dict[str, object] = {}
    section: str | None = None
    for line_number, raw in enumerate(lines[1:end], 2):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        leading = raw[: len(raw) - len(raw.lstrip())]
        if "\t" in leading:
            raise ValueError(f"unsupported YAML indentation on line {line_number}")
        indent = len(leading)
        if indent not in {0, 2}:
            raise ValueError(f"unsupported YAML indentation on line {line_number}")
        match = re.fullmatch(r"\s*([A-Za-z0-9_-]+):(?:\s*(.*))?", raw)
        if not match:
            raise ValueError(f"unsupported YAML syntax on line {line_number}")
        key, value = match.group(1), (match.group(2) or "")
        if indent == 0:
            if key not in TOP_LEVEL_KEYS and not key.startswith("bc250_"):
                raise ValueError(f"unsupported front-matter key: {key}")
            if key in data:
                raise ValueError(f"duplicate front-matter key: {key}")
            if not value:
                if key != "relation":
                    raise ValueError(f"only relation may be a nested section: {key}")
                data[key] = {}
                section = key
            else:
                data[key] = _unquote(value)
                section = None
            continue
        if section != "relation" or not isinstance(data.get("relation"), dict):
            raise ValueError(f"nested key outside relation on line {line_number}")
        if key not in RELATION_KEYS:
            raise ValueError(f"unsupported relation key: {key}")
        relation = data["relation"]
        assert isinstance(relation, dict)
        if key in relation:
            raise ValueError(f"duplicate relation key: {key}")
        if not value:
            raise ValueError(f"relation value must be scalar: {key}")
        relation[key] = _unquote(value)
    return data


def revision_identity(meta: dict[str, object]) -> str:
    """Return the exact revision identity, accepting legacy metadata on upgrade."""
    return str(meta.get("revision_id") or meta.get("document_id") or "").strip()


def route(meta: dict[str, object]) -> tuple[str, str]:
    """Return managed-corpus lane/language using the package authority policy.

    German is the sole authoritative source language for the managed corpus.
    French documents are translations.  Legacy ``authority: original`` remains
    readable, but it is subject to the same language policy.
    """
    language = str(meta.get("language", "")).strip()
    authority = str(meta.get("authority_role", meta.get("authority", ""))).strip().lower()
    relation = meta.get("relation") if isinstance(meta.get("relation"), dict) else {}
    rel_type = (
        str(relation.get("type", "")).strip().lower()
        if isinstance(relation, dict)
        else ""
    )
    source_language = (
        str(relation.get("source_language", "")).strip().lower()
        if isinstance(relation, dict)
        else ""
    )
    lang = language.lower()

    if not language:
        raise ValueError("language is required")

    if authority:
        if authority in {"original", "authoritative"}:
            lane = "original"
        elif authority == "translation":
            lane = "translation"
        else:
            raise ValueError("authority_role must be authoritative/original or translation")
    elif lang.startswith("de"):
        lane = "original"
    elif (
        lang.startswith("fr")
        and rel_type == "translation-pair"
        and source_language.startswith("de")
    ):
        lane = "translation"
    else:
        raise ValueError(
            "cannot infer managed-corpus authority; German must be authoritative and French must be translation"
        )

    if lane == "original" and not lang.startswith("de"):
        raise ValueError("authoritative managed-corpus documents must be German")
    if lane == "translation" and not lang.startswith("fr"):
        raise ValueError("translation managed-corpus documents must be French")
    return lane, language


def validate_document_metadata(
    meta: dict[str, object], *, active: bool = False
) -> tuple[str, str]:
    """Validate metadata rules shared by lifecycle validation and ingestion."""
    lane, language = route(meta)
    document_id = str(meta.get("document_id", "")).strip()
    family = str(meta.get("document_family", "")).strip()
    if not document_id or not family:
        raise ValueError("document_id and document_family are required")
    if not revision_identity(meta):
        raise ValueError("revision_id (or legacy document_id) is required")
    for field in ("approved_on", "effective_from"):
        if str(meta.get(field, "")).strip():
            validate_iso_date(meta[field], field)
    if active and str(meta.get("review_required", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise ValueError("active Markdown must not have review_required=true")
    translation_of = str(meta.get("translation_of", "")).strip()
    if lane == "translation" and active and not translation_of:
        raise ValueError("active French translation must reference a German revision ID in translation_of")
    if lane == "original" and translation_of:
        raise ValueError("authoritative German document must not set translation_of")
    relation = meta.get("relation") if isinstance(meta.get("relation"), dict) else {}
    if lane == "translation" and relation:
        relation_type = str(relation.get("type", "")).strip().lower()
        source_language = str(relation.get("source_language", "")).strip().lower()
        if relation_type and relation_type != "translation-pair":
            raise ValueError("French translation relation.type must be translation-pair")
        if source_language and not (
            source_language.startswith("de") or source_language == "german"
        ):
            raise ValueError("French translation relation.source_language must be German")
    fidelity_status = str(meta.get("bc250_fidelity_status", "")).strip().lower()
    fidelity_note = str(meta.get("bc250_fidelity_note", "")).strip()
    if fidelity_status and fidelity_status not in {"pass", "review", "not-scored"}:
        raise ValueError("bc250_fidelity_status must be pass, review or not-scored")
    if fidelity_status and not fidelity_note:
        raise ValueError("bc250_fidelity_note is required when bc250_fidelity_status is set")
    if active and fidelity_status == "review":
        acknowledged = str(meta.get("bc250_fidelity_acknowledged", "")).strip().lower()
        if acknowledged not in {"1", "true", "yes", "on"}:
            raise ValueError(
                "active document with bc250_fidelity_status=review requires explicit "
                "bc250_fidelity_acknowledged=true"
            )
    return lane, language


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_source(
    active_file: Path, source_file: str, expected: str
) -> tuple[Path, str | None]:
    if Path(source_file).name != source_file or source_file in {".", ".."}:
        raise ValueError("source_file must be a filename inside sources/")
    sources = active_file.parent.parent / "sources"
    if sources.is_symlink():
        raise ValueError(f"sources directory must not be a symlink: {sources}")
    if not sources.is_dir():
        raise ValueError(f"missing sources directory: {sources}")
    named = sources / source_file
    if named.is_symlink():
        raise ValueError(f"source_file must not be a symlink: {source_file}")
    if named.is_file() and _sha256(named).lower() == expected.lower():
        return named, None

    matches = [
        p
        for p in sources.iterdir()
        if p.is_file() and not p.is_symlink() and _sha256(p).lower() == expected.lower()
    ]
    if len(matches) == 1:
        return matches[
            0
        ], f"source_file names {source_file!r}, checksum matches {matches[0].name!r}"
    if named.is_file():
        raise ValueError(f"source SHA-256 mismatch: {named.name}")
    raise ValueError(
        f"source_file not found and checksum did not identify one source: {source_file}"
    )


def discover(root: Path) -> tuple[list[Document], list[str]]:
    docs: list[Document] = []
    warnings: list[str] = []
    errors: list[str] = []
    for scope in SCOPES:
        scope_dir = root / scope
        if scope_dir.is_symlink():
            errors.append(f"{scope_dir}: scope directory must not be a symlink")
            continue
        if not scope_dir.exists():
            continue
        for collection_dir in sorted(p for p in scope_dir.iterdir() if p.is_dir()):
            if collection_dir.is_symlink():
                errors.append(
                    f"{collection_dir}: collection directory must not be a symlink"
                )
                continue
            active = collection_dir / "active"
            if active.is_symlink():
                errors.append(f"{active}: active directory must not be a symlink")
                continue
            if not active.is_dir():
                continue
            nested = [p for p in active.rglob("*.md") if p.parent != active]
            if nested:
                errors.append(
                    f"{active}: nested active directories are not supported yet"
                )
                continue
            for path in sorted(active.glob("*.md")):
                try:
                    if path.is_symlink():
                        raise ValueError("active Markdown must not be a symlink")
                    meta = front_matter(path)
                    lane, language = validate_document_metadata(meta, active=True)
                    source_file = str(meta.get("source_file", "")).strip()
                    source_sha256 = str(meta.get("source_sha256", "")).strip().lower()
                    if not source_file:
                        raise ValueError("missing source_file")
                    if not SHA256_RE.fullmatch(source_sha256):
                        raise ValueError("source_sha256 must be a 64-character SHA-256")
                    _, warning = _resolve_source(path, source_file, source_sha256)
                    if warning:
                        warnings.append(f"{path}: {warning}")
                    docs.append(
                        Document(
                            path,
                            scope,
                            collection_dir.name,
                            lane,
                            language,
                            source_file,
                            source_sha256,
                        )
                    )
                except (OSError, UnicodeError, ValueError) as exc:
                    errors.append(f"{path}: {exc}")
    if errors:
        raise ValueError("\n".join(errors))
    return docs, warnings


def groups(docs: list[Document]) -> dict[str, list[Document]]:
    result: dict[str, list[Document]] = {}
    for doc in docs:
        result.setdefault(doc.kb_name, []).append(doc)
    return result


def validate_diff_result(result: object) -> dict[str, object]:
    """Validate the Open WebUI incremental-sync response before using it."""
    if not isinstance(result, dict):
        raise TypeError("invalid sync diff response")
    for key in ("added", "modified", "deleted"):
        value = result.get(key, [])
        if not isinstance(value, list):
            raise TypeError(f"Open WebUI sync diff field {key!r} must be a list")
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise TypeError(f"Open WebUI sync diff {key}[{index}] must be an object")
            if key in {"added", "modified"}:
                filename = item.get("filename")
                if not isinstance(filename, str) or not filename:
                    raise RuntimeError(
                        f"Open WebUI sync diff {key}[{index}] is missing a valid filename"
                    )
            id_key = "stale_file_id" if key == "modified" else "file_id"
            if key in {"modified", "deleted"}:
                file_id = item.get(id_key)
                if not isinstance(file_id, str) or not file_id:
                    raise RuntimeError(
                        f"Open WebUI sync diff {key}[{index}] is missing a valid {id_key}"
                    )
    if "unmodified_count" in result:
        try:
            unchanged = int(result["unmodified_count"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "Open WebUI sync diff unmodified_count must be an integer"
            ) from exc
        if unchanged < 0:
            raise RuntimeError(
                "Open WebUI sync diff unmodified_count must not be negative"
            )
    return result


def expected_knowledge(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for scope in SCOPES:
        scope_dir = root / scope
        if not scope_dir.is_dir():
            continue
        for collection_dir in sorted(p for p in scope_dir.iterdir() if p.is_dir()):
            if not (collection_dir / "active").is_dir():
                continue
            for lane in ("original", "translation"):
                result[knowledge_name(scope, collection_dir.name, lane)] = (
                    knowledge_description(scope, collection_dir.name, lane)
                )
    return result


def print_plan(root: Path, docs: list[Document], warnings: list[str]) -> None:
    print(f"Document root: {root}")
    if not docs:
        print("No active Markdown documents found.")
    for name, members in sorted(groups(docs).items()):
        print(f"\n{name}: {len(members)} document(s)")
        for doc in members:
            print(f"  {doc.language:5s}  {doc.path.name}")
    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  - {warning}")
    print("\nRouting: German/English queries -> Originals; French queries -> Français.")
    print(
        "The Français knowledge base is a translation aid; German Originals remain authoritative."
    )


class OpenWebUI:
    def __init__(self, base_url: str, token: str, timeout: int = 600):
        self.base = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        payload: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> object:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)
        request = Request(
            self.base + path, data=body, method=method, headers=request_headers
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise RuntimeError(
                f"Open WebUI {method} {path} failed: HTTP {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                f"Open WebUI is unreachable at {self.base}: {exc.reason}"
            ) from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Open WebUI {method} {path} returned invalid JSON"
            ) from exc

    def find_knowledge(self, name: str) -> dict[str, object] | None:
        exact: list[dict[str, object]] = []
        page = 1
        seen = 0
        while True:
            result = self._request(
                "GET", f"/api/v1/knowledge/search?query={quote(name)}&page={page}"
            )
            if not isinstance(result, dict):
                raise TypeError("Open WebUI knowledge search response must be an object")
            items = result.get("items", [])
            if not isinstance(items, list):
                raise TypeError(
                    "Open WebUI knowledge search response field 'items' must be a list"
                )
            if any(not isinstance(item, dict) for item in items):
                raise TypeError("Open WebUI knowledge search response items must be objects")
            exact.extend(
                item
                for item in items
                if item.get("name") == name
            )
            seen += len(items)
            total_raw = result.get("total")
            try:
                total = int(total_raw) if total_raw is not None else seen
            except (TypeError, ValueError):
                total = seen
            if not items or seen >= total:
                break
            page += 1
            if page > 10000:
                raise RuntimeError("knowledge search pagination exceeded safety limit")
        if len(exact) > 1:
            raise RuntimeError(f"multiple knowledge bases have the exact name {name!r}")
        if not exact:
            return None
        if exact[0].get("write_access") is False:
            raise RuntimeError(f"API-key owner does not have write access to {name!r}")
        if not isinstance(exact[0].get("id"), str) or not str(exact[0]["id"]).strip():
            raise RuntimeError(f"Open WebUI knowledge search response for {name!r} is missing a valid id")
        return exact[0]

    def knowledge(self, name: str, description: str) -> dict[str, object]:
        existing = self.find_knowledge(name)
        if existing is not None:
            return existing
        created = self._request(
            "POST",
            "/api/v1/knowledge/create",
            {"name": name, "description": description},
        )
        if (
            not isinstance(created, dict)
            or not isinstance(created.get("id"), str)
            or not str(created["id"]).strip()
        ):
            raise RuntimeError(f"failed to create knowledge base {name!r}")
        print(f"  created knowledge base: {name}")
        return created

    def diff(self, knowledge_id: str, docs: list[Document]) -> dict[str, object]:
        manifest = [
            {
                "filename": doc.path.name,
                "path": "",
                "checksum": _sha256(doc.path),
                "size": doc.path.stat().st_size,
            }
            for doc in docs
        ]
        result = self._request(
            "POST",
            f"/api/v1/knowledge/{knowledge_id}/sync/diff",
            {"manifest": manifest},
        )
        return validate_diff_result(result)

    def upload(self, knowledge_id: str, doc: Document) -> None:
        content = doc.path.read_bytes()
        file_hash = hashlib.sha256(content).hexdigest()
        metadata = json.dumps({"knowledge_id": knowledge_id, "file_hash": file_hash})
        boundary = "----bc250-" + uuid.uuid4().hex
        mime = mimetypes.guess_type(doc.path.name)[0] or "text/markdown"
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n{metadata}\r\n'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{doc.path.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode(),
            content,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        body = b"".join(parts)
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        request = Request(
            self.base + "/api/v1/files/?process=true&process_in_background=false",
            data=body,
            method="POST",
            headers=headers,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise RuntimeError(
                f"upload failed for {doc.path.name}: HTTP {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                f"Open WebUI is unreachable at {self.base}: {exc.reason}"
            ) from exc
        try:
            result = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Open WebUI upload returned invalid JSON for {doc.path.name}"
            ) from exc
        file_id = str(result.get("id", "")) if isinstance(result, dict) else ""
        if not file_id:
            raise RuntimeError(f"Open WebUI returned no file id for {doc.path.name}")
        status_result = self._request("GET", f"/api/v1/files/{file_id}/process/status")
        if not isinstance(status_result, dict):
            raise TypeError(
                f"Open WebUI returned an invalid processing-status response for {doc.path.name}"
            )
        status = status_result.get("status")
        if status != "completed":
            detail = status_result.get("error")
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(
                f"Open WebUI processing did not complete for {doc.path.name} (status={status!r}){suffix}"
            )

    def cleanup(self, knowledge_id: str, file_ids: list[str]) -> None:
        if file_ids:
            self._request(
                "POST",
                f"/api/v1/knowledge/{knowledge_id}/sync/cleanup",
                {"file_ids": file_ids, "dir_ids": []},
            )


def is_loopback_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def validate_sync_endpoint(
    url: str,
    docs: list[Document],
    *,
    root: Path | None = None,
    allow_remote: bool = False,
    allow_confidential_remote: bool = False,
) -> None:
    if is_loopback_url(url):
        return
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid Open WebUI URL: {url!r}")
    if not allow_remote:
        raise ValueError(
            "RAG ingest is loopback-only by default; remote Open WebUI requires --allow-remote "
            "because API credentials, document content and knowledge metadata leave the appliance"
        )
    has_confidential = any(doc.scope == "confidential" for doc in docs)
    if root is not None:
        confidential_root = root / "confidential"
        if confidential_root.is_dir():
            has_confidential = has_confidential or any(
                (collection / "active").is_dir()
                for collection in confidential_root.iterdir()
                if collection.is_dir() and not collection.is_symlink()
            )
    if has_confidential and not allow_confidential_remote:
        raise ValueError(
            "remote RAG ingest may access or modify confidential-scope knowledge state; "
            "add --allow-confidential-remote together with --allow-remote only after explicitly "
            "accepting off-appliance disclosure"
        )


def read_protected_token_file(path: Path) -> str:
    """Read a credential file only when it is private, regular and not a symlink."""
    if path.is_symlink():
        raise ValueError(f"Open WebUI API key file must not be a symlink: {path}")
    try:
        info = path.stat()
    except OSError as exc:
        raise ValueError(f"cannot stat Open WebUI API key file {path}: {exc}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Open WebUI API key file must be a regular file: {path}")
    if info.st_mode & 0o077:
        raise ValueError(
            f"Open WebUI API key file must not be group/world accessible: {path} "
            f"(mode {stat.S_IMODE(info.st_mode):04o})"
        )
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"cannot read Open WebUI API key file {path}: {exc}") from exc
    if not token:
        raise ValueError(f"Open WebUI API key file is empty: {path}")
    return token


def token_from(args: object) -> str:
    if args.token_file:
        return read_protected_token_file(Path(args.token_file))
    token = os.environ.get("OPEN_WEBUI_API_KEY", "").strip()
    if not token:
        raise ValueError("provide --token-file or OPEN_WEBUI_API_KEY")
    return token


def sync(
    root: Path, docs: list[Document], warnings: list[str], args: object
) -> None:
    validate_sync_endpoint(
        args.url,
        docs,
        root=root,
        allow_remote=bool(getattr(args, "allow_remote", False)),
        allow_confidential_remote=bool(getattr(args, "allow_confidential_remote", False)),
    )
    print_plan(root, docs, warnings)
    if not is_loopback_url(args.url):
        print(
            "WARNING: remote RAG ingest explicitly enabled; API credentials, document content and "
            "knowledge metadata may leave this appliance, and remote knowledge state may be modified.",
            file=sys.stderr,
        )
    api = OpenWebUI(args.url, token_from(args), args.timeout)
    grouped = groups(docs)
    expected = expected_knowledge(root)
    by_key = {(doc.kb_name, doc.path.name): doc for doc in docs}
    names = set(grouped) | (set(expected) if args.prune else set())

    for name in sorted(names):
        members = grouped.get(name, [])
        print(f"\nSyncing {name}")
        if members:
            kb = api.knowledge(name, members[0].kb_description)
        else:
            kb = api.find_knowledge(name)
            if kb is None:
                print(
                    "  empty local lane and no remote knowledge base; nothing to prune"
                )
                continue
        kb_id_raw = kb.get("id") if isinstance(kb, dict) else None
        if not isinstance(kb_id_raw, str) or not kb_id_raw.strip():
            raise RuntimeError(
                f"Open WebUI knowledge response for {name!r} is missing a valid id"
            )
        kb_id = kb_id_raw
        diff = validate_diff_result(api.diff(kb_id, members))
        added = diff.get("added", [])
        modified = diff.get("modified", [])
        deleted = diff.get("deleted", [])
        assert isinstance(added, list) and isinstance(modified, list) and isinstance(deleted, list)
        unchanged = int(diff.get("unmodified_count", 0) or 0)
        print(
            f"  {len(added)} added, {len(modified)} changed, {unchanged} unchanged, {len(deleted)} stale remote"
        )

        for item in added:
            assert isinstance(item, dict)
            filename = str(item["filename"])
            doc = by_key.get((name, filename))
            if doc is None:
                raise RuntimeError(
                    f"Open WebUI sync diff added references unknown local file {filename!r} in {name!r}"
                )
            print(f"  upload:  {doc.path.name}")
            api.upload(kb_id, doc)
        for item in modified:
            assert isinstance(item, dict)
            filename = str(item["filename"])
            doc = by_key.get((name, filename))
            if doc is None:
                raise RuntimeError(
                    f"Open WebUI sync diff modified references unknown local file {filename!r} in {name!r}"
                )
            print(f"  replace: {doc.path.name}")
            api.upload(kb_id, doc)
            try:
                api.cleanup(kb_id, [str(item["stale_file_id"])])
            except RuntimeError as exc:
                raise RuntimeError(
                    f"replacement upload succeeded for {doc.path.name}, but stale remote cleanup failed; "
                    "the new copy was kept and the old copy may still exist. Fix the API/permission problem "
                    "and rerun ingest; do not use --prune unless unrelated local deletions should also be removed."
                ) from exc

        if deleted:
            if args.prune:
                ids = [
                    str(item["file_id"])
                    for item in deleted
                    if isinstance(item, dict) and item.get("file_id")
                ]
                print(f"  prune:   {len(ids)} stale remote file(s)")
                api.cleanup(kb_id, ids)
            else:
                print(
                    "  NOTE: stale remote files kept; rerun with --prune to remove them explicitly."
                )

    print(
        "\nSync complete. Review Open WebUI Knowledge permissions before exposing any collection to other users."
    )
