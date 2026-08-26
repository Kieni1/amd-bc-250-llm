#!/usr/bin/env python3
"""Metadata-aware Open WebUI knowledge importer for the BC-250 document tree."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_ROOT = Path(os.environ.get("BC250_RAG_ROOT", "/srv/bc250-documents"))
DEFAULT_URL = os.environ.get("OPEN_WEBUI_URL", "http://127.0.0.1:3000").rstrip("/")
SCOPES = ("public", "confidential")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


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
        suffix = "Originals" if self.lane == "original" else "Français"
        return f"[{self.scope.upper()}] {self.collection} — {suffix}"

    @property
    def kb_description(self) -> str:
        base = f"BC-250 managed RAG import from {self.scope}/{self.collection}/active."
        if self.lane == "original":
            return base + " Authoritative German originals; use for German and English queries."
        return base + " French translations; use for French queries. German originals remain authoritative on conflict."


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def front_matter(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing YAML front matter")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("unterminated YAML front matter") from exc

    data: dict[str, object] = {}
    section: str | None = None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        match = re.match(r"^\s*([A-Za-z0-9_-]+):(?:\s*(.*))?$", raw)
        if not match:
            continue
        key, value = match.group(1), (match.group(2) or "")
        if indent == 0:
            section = key if not value else None
            if value:
                data[key] = _unquote(value)
            elif key == "relation":
                data[key] = {}
        elif section == "relation" and isinstance(data.get("relation"), dict):
            data["relation"][key] = _unquote(value)  # type: ignore[index]
    return data


def route(meta: dict[str, object]) -> tuple[str, str]:
    language = str(meta.get("language", "")).strip()
    authority = str(meta.get("authority", "")).strip().lower()
    relation = meta.get("relation") if isinstance(meta.get("relation"), dict) else {}
    rel_type = str(relation.get("type", "")).strip().lower() if isinstance(relation, dict) else ""
    source_language = str(relation.get("source_language", "")).strip().lower() if isinstance(relation, dict) else ""
    lang = language.lower()

    if authority:
        if authority not in {"original", "translation"}:
            raise ValueError("authority must be original or translation")
        lane = authority
    elif lang.startswith("de"):
        lane = "original"
    elif lang.startswith("fr") and rel_type == "translation-pair" and source_language.startswith("de"):
        lane = "translation"
    else:
        raise ValueError("cannot infer authority; add authority: original|translation")

    if lane == "original" and lang.startswith("fr"):
        raise ValueError("French documents must use authority: translation")
    if lane == "translation" and not lang.startswith("fr"):
        raise ValueError("translation documents must be French in this branch")
    return lane, language


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_source(active_file: Path, source_file: str, expected: str) -> tuple[Path, str | None]:
    sources = active_file.parent.parent / "sources"
    named = sources / source_file
    if named.is_file() and _sha256(named).lower() == expected.lower():
        return named, None
    if not sources.is_dir():
        raise ValueError(f"missing sources directory: {sources}")

    matches = [p for p in sources.iterdir() if p.is_file() and _sha256(p).lower() == expected.lower()]
    if len(matches) == 1:
        return matches[0], f"source_file names {source_file!r}, checksum matches {matches[0].name!r}"
    if named.is_file():
        raise ValueError(f"source SHA-256 mismatch: {named.name}")
    raise ValueError(f"source_file not found and checksum did not identify one source: {source_file}")


def discover(root: Path) -> tuple[list[Document], list[str]]:
    docs: list[Document] = []
    warnings: list[str] = []
    errors: list[str] = []
    for scope in SCOPES:
        scope_dir = root / scope
        if not scope_dir.exists():
            continue
        for collection_dir in sorted(p for p in scope_dir.iterdir() if p.is_dir()):
            active = collection_dir / "active"
            if not active.is_dir():
                continue
            nested = [p for p in active.rglob("*.md") if p.parent != active]
            if nested:
                errors.append(f"{active}: nested active directories are not supported yet")
                continue
            for path in sorted(active.glob("*.md")):
                try:
                    meta = front_matter(path)
                    lane, language = route(meta)
                    source_file = str(meta.get("source_file", "")).strip()
                    source_sha256 = str(meta.get("source_sha256", "")).strip().lower()
                    if not source_file:
                        raise ValueError("missing source_file")
                    if not SHA256_RE.fullmatch(source_sha256):
                        raise ValueError("source_sha256 must be a 64-character SHA-256")
                    _, warning = _resolve_source(path, source_file, source_sha256)
                    if warning:
                        warnings.append(f"{path}: {warning}")
                    docs.append(Document(path, scope, collection_dir.name, lane, language, source_file, source_sha256))
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
    print("The Français knowledge base is a translation aid; German Originals remain authoritative.")


class OpenWebUI:
    def __init__(self, base_url: str, token: str, timeout: int = 600):
        self.base = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: object | None = None, headers: dict[str, str] | None = None) -> object:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)
        request = Request(self.base + path, data=body, method=method, headers=request_headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"Open WebUI {method} {path} failed: HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Open WebUI is unreachable at {self.base}: {exc.reason}") from exc
        return json.loads(raw) if raw else {}

    def knowledge(self, name: str, description: str) -> dict[str, object]:
        result = self._request("GET", f"/api/v1/knowledge/search?query={quote(name)}&page=1")
        items = result.get("items", []) if isinstance(result, dict) else []
        exact = [item for item in items if isinstance(item, dict) and item.get("name") == name]
        if len(exact) > 1:
            raise RuntimeError(f"multiple knowledge bases have the exact name {name!r}")
        if exact:
            if exact[0].get("write_access") is False:
                raise RuntimeError(f"API-key owner does not have write access to {name!r}")
            return exact[0]
        created = self._request("POST", "/api/v1/knowledge/create", {"name": name, "description": description})
        if not isinstance(created, dict) or not created.get("id"):
            raise RuntimeError(f"failed to create knowledge base {name!r}")
        print(f"  created knowledge base: {name}")
        return created

    def diff(self, knowledge_id: str, docs: list[Document]) -> dict[str, object]:
        manifest = [
            {"filename": doc.path.name, "path": "", "checksum": _sha256(doc.path), "size": doc.path.stat().st_size}
            for doc in docs
        ]
        result = self._request("POST", f"/api/v1/knowledge/{knowledge_id}/sync/diff", {"manifest": manifest})
        if not isinstance(result, dict):
            raise RuntimeError("invalid sync diff response")
        return result

    def upload(self, knowledge_id: str, doc: Document) -> None:
        content = doc.path.read_bytes()
        file_hash = hashlib.sha256(content).hexdigest()
        metadata = json.dumps({"knowledge_id": knowledge_id, "file_hash": file_hash})
        boundary = "----bc250-" + uuid.uuid4().hex
        mime = mimetypes.guess_type(doc.path.name)[0] or "text/markdown"
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\n\r\n{metadata}\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{doc.path.name}\"\r\nContent-Type: {mime}\r\n\r\n".encode(),
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
                result = json.loads(response.read() or b"{}")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"upload failed for {doc.path.name}: HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Open WebUI is unreachable at {self.base}: {exc.reason}") from exc
        file_id = str(result.get("id", "")) if isinstance(result, dict) else ""
        if not file_id:
            raise RuntimeError(f"Open WebUI returned no file id for {doc.path.name}")
        status_result = self._request("GET", f"/api/v1/files/{file_id}/process/status")
        status = status_result.get("status") if isinstance(status_result, dict) else None
        if status != "completed":
            detail = status_result.get("error") if isinstance(status_result, dict) else None
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"Open WebUI processing did not complete for {doc.path.name} (status={status!r}){suffix}")

    def cleanup(self, knowledge_id: str, file_ids: list[str]) -> None:
        if file_ids:
            self._request("POST", f"/api/v1/knowledge/{knowledge_id}/sync/cleanup", {"file_ids": file_ids, "dir_ids": []})


def token_from(args: argparse.Namespace) -> str:
    if args.token_file:
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
    else:
        token = os.environ.get("OPEN_WEBUI_API_KEY", "").strip()
    if not token:
        raise ValueError("provide --token-file or OPEN_WEBUI_API_KEY")
    return token


def sync(root: Path, docs: list[Document], warnings: list[str], args: argparse.Namespace) -> None:
    print_plan(root, docs, warnings)
    api = OpenWebUI(args.url, token_from(args), args.timeout)
    grouped = groups(docs)
    by_key = {(doc.kb_name, doc.path.name): doc for doc in docs}

    for name, members in sorted(grouped.items()):
        print(f"\nSyncing {name}")
        kb = api.knowledge(name, members[0].kb_description)
        kb_id = str(kb["id"])
        diff = api.diff(kb_id, members)
        added = diff.get("added", []) if isinstance(diff.get("added"), list) else []
        modified = diff.get("modified", []) if isinstance(diff.get("modified"), list) else []
        deleted = diff.get("deleted", []) if isinstance(diff.get("deleted"), list) else []
        unchanged = int(diff.get("unmodified_count", 0) or 0)
        print(f"  {len(added)} added, {len(modified)} changed, {unchanged} unchanged, {len(deleted)} stale remote")

        for item in added:
            doc = by_key[(name, str(item["filename"]))]
            print(f"  upload:  {doc.path.name}")
            api.upload(kb_id, doc)
        for item in modified:
            doc = by_key[(name, str(item["filename"]))]
            print(f"  replace: {doc.path.name}")
            api.upload(kb_id, doc)
            api.cleanup(kb_id, [str(item["stale_file_id"])])

        if deleted:
            if args.prune:
                ids = [str(item["file_id"]) for item in deleted if isinstance(item, dict) and item.get("file_id")]
                print(f"  prune:   {len(ids)} stale remote file(s)")
                api.cleanup(kb_id, ids)
            else:
                print("  NOTE: stale remote files kept; rerun with --prune to remove them explicitly.")

    print("\nSync complete. Review Open WebUI Knowledge permissions before exposing any collection to other users.")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bc250-rag-import",
        description="Validate and sync active Markdown documents into language/authority-separated Open WebUI knowledge bases.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="validate metadata/source provenance and show routing without contacting Open WebUI")
    plan.add_argument("root", nargs="?", type=Path, default=DEFAULT_ROOT)
    apply = sub.add_parser("sync", help="incrementally upload changed active Markdown documents")
    apply.add_argument("root", nargs="?", type=Path, default=DEFAULT_ROOT)
    apply.add_argument("--url", default=DEFAULT_URL, help=f"Open WebUI URL (default: {DEFAULT_URL})")
    apply.add_argument("--token-file", help="root-readable file containing an Open WebUI API key")
    apply.add_argument("--prune", action="store_true", help="remove remote files no longer present locally")
    apply.add_argument("--timeout", type=int, default=600, help="per-request timeout in seconds")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    try:
        docs, warnings = discover(root)
        if args.command == "plan":
            print_plan(root, docs, warnings)
        else:
            sync(root, docs, warnings, args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
