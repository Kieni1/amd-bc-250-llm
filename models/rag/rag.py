#!/usr/bin/env python3
"""BC-250 local RAG corpus lifecycle and batch-preparation helper.

The human-review boundary is deliberate: automation writes only to working/.
Only reviewed documents can be activated and only active/*.md is ingested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import rag_import as importer

DEFAULT_ROOT = importer.DEFAULT_ROOT
DEFAULT_AGENT_URL = os.environ.get("BC250_RAG_AGENT_URL", "http://127.0.0.1:11436").rstrip("/")
DEFAULT_AGENT_MODEL = os.environ.get(
    "BC250_RAG_AGENT_MODEL", "agentic-ornith15-9b-ornith-q5-k-m"
)
DEFAULT_MAX_CHARS = int(os.environ.get("BC250_RAG_MAX_CHARS", "50000"))
INBOX_LANES = ("german", "french", "bilingual")
COLLECTION_DIRS = ("sources", "working", "active", "superseded")
PDF_EXTENSIONS = {".pdf"}


def die(message: str) -> None:
    raise ValueError(message)


def collection_path(root: Path, scope: str, collection: str) -> Path:
    if scope not in importer.SCOPES:
        die(f"scope must be one of: {', '.join(importer.SCOPES)}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", collection):
        die("collection must contain only letters, numbers, dot, underscore or hyphen")
    return root / scope / collection


def ensure_collection(root: Path, scope: str, collection: str) -> Path:
    base = collection_path(root, scope, collection)
    # Confidential corpora stay root-private by default. Public here means the
    # source material is public; the appliance still does not expose the tree.
    mode = 0o700 if scope == "confidential" else 0o750
    for path in (base, *(base / name for name in COLLECTION_DIRS), base / "inbox"):
        if path.is_symlink():
            die(f"RAG lifecycle directory must not be a symlink: {path}")
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(mode)
    for lane in INBOX_LANES:
        path = base / "inbox" / lane
        if path.is_symlink():
            die(f"RAG inbox lane must not be a symlink: {path}")
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(mode)
    return base


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def slug(value: str, fallback: str = "document") -> str:
    value = value.lower().strip()
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    value = re.sub(r"\b(de|fr|de-ch|fr-ch|german|french|deutsch|francais|français|bilingual|bilingue)\b", " ", value)
    value = re.sub(r"\b20\d{2}[-_.]?\d{2}[-_.]?\d{2}\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value[:90] or fallback


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def bool_value(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def split_markdown(path: Path) -> tuple[dict[str, object], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        die(f"{path}: missing YAML front matter")
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        die(f"{path}: unterminated YAML front matter")
    return importer.front_matter(path), "".join(lines[end + 1 :]).lstrip("\n")


def render_markdown(meta: dict[str, object], body: str) -> str:
    ordered = (
        "document_id", "document_family", "title", "organisation", "language",
        "authority_role", "document_type", "edition", "approved_on", "effective_from",
        "status", "review_required", "translation_of", "source_file", "source_sha256",
        "normalization",
    )
    lines = ["---"]
    for key in ordered:
        if key not in meta or meta[key] in {None, ""}:
            continue
        value = meta[key]
        if key == "review_required":
            lines.append(f"{key}: {'true' if bool_value(value) else 'false'}")
        else:
            lines.append(f"{key}: {yaml_quote(str(value))}")
    for key in sorted(k for k in meta if k.startswith("bc250_") and k not in ordered):
        value = meta[key]
        if value not in {None, ""}:
            lines.append(f"{key}: {yaml_quote(str(value))}")
    relation = meta.get("relation")
    if isinstance(relation, dict) and relation:
        lines.append("relation:")
        for key in ("type", "counterpart", "source_language"):
            if relation.get(key):
                lines.append(f"  {key}: {yaml_quote(str(relation[key]))}")
    lines.extend(("---", "", body.rstrip(), ""))
    return "\n".join(lines)


def source_text(pdf: Path) -> tuple[int, str]:
    for command in ("pdfinfo", "pdftotext"):
        if shutil.which(command) is None:
            die(f"{command} is unavailable; install the package dependency poppler-utils")
    info = subprocess.run(["pdfinfo", str(pdf)], text=True, capture_output=True, check=False)
    pages = 0
    if info.returncode == 0:
        match = re.search(r"(?m)^Pages:\s+(\d+)\s*$", info.stdout)
        if match:
            pages = int(match.group(1))
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        die(f"pdftotext failed for {pdf.name}: {result.stderr.strip() or 'unknown error'}")
    return pages, result.stdout.replace("\x0c", "\n\n")


def require_local_agent_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        die("prepare-batch requires a loopback-only agent URL; document text is never sent to a remote model endpoint")


def agent_ready(url: str) -> bool:
    try:
        with urlopen(url + "/api/tags", timeout=3) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def agent_models(url: str) -> set[str]:
    try:
        with urlopen(url + "/api/tags", timeout=5) as response:
            data = json.loads(response.read() or b"{}")
    except (OSError, URLError, json.JSONDecodeError) as exc:
        die(f"cannot query local agent lane at {url}: {exc}")
    models = data.get("models", []) if isinstance(data, dict) else []
    return {
        str(item.get("name", "")).removesuffix(":latest")
        for item in models
        if isinstance(item, dict) and item.get("name")
    }


def enter_agent_if_needed(url: str) -> bool:
    if agent_ready(url):
        return False
    if os.geteuid() != 0:
        die("the agent lane is inactive; rerun prepare-batch with sudo so BC-250 can enter exclusive agent mode")
    command = shutil.which("bc250-agent-mode") or "/usr/libexec/bc250-llm-server/agent-mode.sh"
    result = subprocess.run([command, "enter"], text=True, check=False)
    if result.returncode != 0 or not agent_ready(url):
        die("exclusive agent mode did not become ready on port 11436")
    return True


def restore_normal_if_needed(switched: bool) -> None:
    if not switched:
        return
    command = shutil.which("bc250-agent-mode") or "/usr/libexec/bc250-llm-server/agent-mode.sh"
    result = subprocess.run([command, "normal"], text=True, check=False)
    if result.returncode != 0:
        print("WARNING: automatic restoration of normal Ollama topology failed; run sudo bc250-agent-mode normal", file=sys.stderr)


def normalize_prompt(text: str, language: str, bilingual: bool) -> str:
    language_name = "German" if language.startswith("de") else "French"
    bilingual_rule = (
        f"The source is bilingual. Extract and normalize ONLY the {language_name} source text; "
        "do not translate the other language into it. Preserve every substantive clause in this language."
        if bilingual
        else f"The source is expected to be {language_name}. Do not translate it."
    )
    return f"""You are a careful local document-ingestion editor for a private German/French RAG corpus.

Return ONLY normalized Markdown body text, beginning with one '# ' document title. Do not return YAML or a code fence.

Rules:
- Preserve the complete substantive source wording. Do not summarize, paraphrase, interpret or invent text.
- Preserve original legal/article numbering exactly. Never replace source identifiers with editorial numbering.
- Use ##/### only for real document sections. Use bold labels for clauses/articles where helpful.
- Preserve dates, amounts, percentages, currency, names, identifiers and legal references exactly.
- Remove repeated decorative page headers/footers and layout-only noise.
- Join words broken only by PDF line wrapping. Preserve genuine compound hyphens.
- Repair only obvious extraction artifacts. Do not silently correct source grammar or legal wording.
- Keep tables readable in Markdown when practical.
- If extraction is ambiguous, retain the text rather than guessing.
- Do not add commentary, a summary, evaluation questions or processing notes.
- {bilingual_rule}

SOURCE EXTRACTION START
{text}
SOURCE EXTRACTION END
"""


def call_agent(url: str, model: str, prompt: str) -> str:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "10m",
            "options": {"temperature": 0, "num_ctx": 32768, "num_predict": 16384},
        }
    ).encode("utf-8")
    request = Request(url + "/api/generate", data=payload, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=1800) as response:
            data = json.loads(response.read() or b"{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        die(f"agent generation failed: HTTP {exc.code}: {detail}")
    except (OSError, URLError, json.JSONDecodeError) as exc:
        die(f"agent generation failed: {exc}")
    if not isinstance(data, dict) or not str(data.get("response", "")).strip():
        die("agent returned no normalized Markdown")
    if data.get("done_reason") in {"length", "max_tokens"}:
        die("agent output hit its generation limit; leave this document for manual/chapter-split processing")
    output = str(data["response"]).strip()
    if output.startswith("```"):
        output = re.sub(r"^```(?:markdown)?\s*", "", output, flags=re.IGNORECASE)
        output = re.sub(r"\s*```$", "", output)
    return output.strip() + "\n"


def title_from_body(body: str, fallback: str) -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", body)
    return match.group(1).strip() if match else fallback


def critical_tokens(text: str) -> set[str]:
    patterns = (
        r"\b\d{1,4}(?:[.'’ ]\d{3})*(?:[.,]\d+)?\s*%?\b",
        r"\b(?:CHF|EUR|USD)\s*\d[\d'’., ]*\b",
        r"\b(?:Art\.|Artikel|article|al\.|Abs\.)\s*\d+[A-Za-z.-]*\b",
        r"\b[A-Z]{2}\d{2}[A-Z0-9 ]{10,30}\b",
    )
    found: set[str] = set()
    for pattern in patterns:
        found.update(match.group(0).strip() for match in re.finditer(pattern, text, flags=re.IGNORECASE))
    return found


def fidelity_note(source: str, body: str, bilingual: bool) -> str:
    if bilingual:
        return "bilingual source: automated whole-source token coverage not scored; visual/manual review required"
    expected = critical_tokens(source)
    missing = sorted(token for token in expected if token not in body)
    if not expected:
        return "no critical numeric/legal tokens detected for automated coverage check"
    if not missing:
        return f"critical-token coverage PASS ({len(expected)}/{len(expected)})"
    preview = ", ".join(missing[:5])
    return f"critical-token coverage REVIEW ({len(expected)-len(missing)}/{len(expected)}); missing examples: {preview}"


def provisional_family(source: Path) -> str:
    return slug(source.stem)


def unique_working_path(working: Path, family: str, language: str, digest: str) -> Path:
    base = f"{family}_{language}_review.md"
    candidate = working / base
    if not candidate.exists():
        return candidate
    return working / f"{family}_{language}_{digest[:8]}_review.md"


def write_draft(base: Path, source: Path, source_sha: str, body: str, language: str, role: str, *, bilingual: bool, translation_of: str = "") -> Path:
    family = provisional_family(source)
    path = unique_working_path(base / "working", family, language, source_sha)
    title = title_from_body(body, source.stem)
    meta: dict[str, object] = {
        "document_id": f"{family}_{language}",
        "document_family": family,
        "title": title,
        "language": language,
        "authority_role": role,
        "status": "currentness-not-verified",
        "review_required": True,
        "source_file": source.name,
        "source_sha256": source_sha,
        "normalization": "Local agent-assisted extraction cleanup; source wording intended to be preserved; human approval required before activation",
    }
    if translation_of:
        meta["translation_of"] = translation_of
    path.write_text(render_markdown(meta, body), encoding="utf-8")
    path.chmod(0o640)
    return path


def store_source(base: Path, source: Path, digest: str) -> Path:
    destination = base / "sources" / source.name
    if destination.exists():
        if sha256(destination) != digest:
            die(f"source filename collision with different content: {destination.name}")
        source.unlink()
        return destination
    source.replace(destination)
    destination.chmod(0o640)
    return destination


def prepare_one(base: Path, source: Path, lane: str, url: str, model: str, max_chars: int) -> list[Path]:
    if source.suffix.lower() not in PDF_EXTENSIONS:
        die(f"unsupported inbox file type for automated preparation: {source.name}; currently PDF only")
    pages, text = source_text(source)
    compact = re.sub(r"\s+", "", text)
    print(f"\nSource: {source.name}")
    print(f"  lane:       {lane}")
    print(f"  pages:      {pages or 'unknown'}")
    print(f"  characters: {len(text):,}")
    if len(compact) < 300:
        die("little/no selectable text detected; leave in inbox and use the local OCR workflow before activation")
    if len(text) > max_chars:
        die(f"extraction is {len(text):,} characters, above the safe single-pass limit {max_chars:,}; split at a genuine document/chapter boundary and retry")
    digest = sha256(source)
    outputs: list[tuple[str, str, str]] = []
    if lane == "german":
        outputs.append(("de-CH", "authoritative", call_agent(url, model, normalize_prompt(text, "de-CH", False))))
    elif lane == "french":
        outputs.append(("fr-CH", "translation", call_agent(url, model, normalize_prompt(text, "fr-CH", False))))
    else:
        outputs.append(("de-CH", "authoritative", call_agent(url, model, normalize_prompt(text, "de-CH", True))))
        outputs.append(("fr-CH", "translation", call_agent(url, model, normalize_prompt(text, "fr-CH", True))))

    stored = store_source(base, source, digest)
    drafts: list[Path] = []
    german_name = ""
    for language, role, body in outputs:
        if language == "de-CH":
            draft = write_draft(base, stored, digest, body, language, role, bilingual=lane == "bilingual")
            german_name = draft.name
        else:
            draft = write_draft(base, stored, digest, body, language, role, bilingual=lane == "bilingual", translation_of=german_name)
        drafts.append(draft)
        print(f"  draft:      {draft.name}")
        print(f"  integrity:  {fidelity_note(text, body, lane == 'bilingual')}")
    return drafts


def cmd_init(args: argparse.Namespace) -> None:
    base = ensure_collection(args.root.resolve(), args.scope, args.collection)
    print(f"Initialized RAG collection: {base}")
    print("Inbox lanes:")
    for lane in INBOX_LANES:
        print(f"  {base / 'inbox' / lane}")
    print("\nPlace source PDFs in german/, french/ or bilingual/, then run:")
    print(f"  sudo bc250-rag prepare-batch {args.scope} {args.collection}")


def cmd_prepare(args: argparse.Namespace) -> None:
    require_local_agent_url(args.agent_url)
    base = ensure_collection(args.root.resolve(), args.scope, args.collection)
    pending = [(lane, path) for lane in INBOX_LANES for path in sorted((base / "inbox" / lane).iterdir()) if path.is_file()]
    print(f"RAG batch preparation: {args.scope}/{args.collection}")
    print(f"Pending inbox files: {len(pending)}")
    if not pending:
        print("Nothing to prepare.")
        return
    if args.dry_run:
        for lane, path in pending:
            print(f"  {lane:9s} {path.name}")
        print("\nDry run only; no files or runtime state changed.")
        return
    switched = enter_agent_if_needed(args.agent_url)
    try:
        available = agent_models(args.agent_url)
        if args.model.removesuffix(":latest") not in available:
            die(f"agent model is not registered on :11436: {args.model}; install it with sudo bc250-model apply agentic {args.model}")
        prepared = 0
        failed = 0
        for lane, path in pending:
            try:
                prepared += len(prepare_one(base, path, lane, args.agent_url, args.model, args.max_chars))
            except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
                failed += 1
                print(f"  REVIEW/FAILED: {exc}", file=sys.stderr)
        print("\nBatch summary")
        print(f"  input files:      {len(pending)}")
        print(f"  Markdown drafts:  {prepared}")
        print(f"  files needing manual/OCR/split review: {failed}")
        print(f"  working folder:   {base / 'working'}")
        print("\nAutomation stops here by design. Review metadata/content before activation.")
        print(f"Next: sudo bc250-rag review {args.scope} {args.collection}")
    finally:
        restore_normal_if_needed(switched)


def find_counterpart(base: Path, family: str, language: str, source_sha: str = "") -> str:
    if not language.lower().startswith("fr"):
        return ""
    family_matches: list[str] = []
    source_matches: list[str] = []
    for folder in (base / "working", base / "active"):
        for path in folder.glob("*.md"):
            try:
                meta = importer.front_matter(path)
            except (OSError, ValueError):
                continue
            if not str(meta.get("language", "")).lower().startswith("de"):
                continue
            if str(meta.get("document_family", "")) == family:
                family_matches.append(path.name)
            if source_sha and str(meta.get("source_sha256", "")) == source_sha:
                source_matches.append(path.name)
    if len(family_matches) == 1:
        return family_matches[0]
    return source_matches[0] if len(source_matches) == 1 else ""


def ask(label: str, current: str) -> str:
    value = input(f"{label} [{current}]: ").strip()
    return value or current


def cmd_review(args: argparse.Namespace) -> None:
    base = collection_path(args.root.resolve(), args.scope, args.collection)
    working = base / "working"
    if not sys.stdin.isatty():
        die("review is interactive; run it from a terminal")
    docs = sorted(working.glob("*.md"))
    if not docs:
        print("No working Markdown drafts to review.")
        return
    for index, path in enumerate(docs, 1):
        meta, body = split_markdown(path)
        if not bool_value(meta.get("review_required", True)) and not args.all:
            continue
        print(f"\n[{index}/{len(docs)}] {path.name}")
        print(f"  source:     {meta.get('source_file', '')}")
        print(f"  language:   {meta.get('language', '')}")
        print(f"  title:      {meta.get('title', '')}")
        print(f"  family:     {meta.get('document_family', '')}")
        print(f"  authority:  {meta.get('authority_role', meta.get('authority', ''))}")
        title = ask("Title", str(meta.get("title", "")))
        family = ask("Document family", str(meta.get("document_family", "")))
        effective = ask("Effective date (YYYY-MM-DD; blank if unknown)", str(meta.get("effective_from", "")))
        edition = ask("Edition/version (optional)", str(meta.get("edition", "")))
        role = ask("Authority role (authoritative|translation)", str(meta.get("authority_role", meta.get("authority", ""))))
        if role == "original":
            role = "authoritative"
        metadata_valid = True
        if not title.strip():
            print("  Title may not be empty; keeping review_required=true.")
            metadata_valid = False
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", family):
            print("  Document family must use only letters, numbers, dot, underscore or hyphen; keeping review_required=true.")
            metadata_valid = False
        if role not in {"authoritative", "translation"}:
            print("  Authority role must be authoritative or translation; keeping review_required=true.")
            metadata_valid = False
        translation = str(meta.get("translation_of", ""))
        if role == "translation":
            known_names = {p.name for folder in (base / "working", base / "active") for p in docs_in(folder)}
            suggested = find_counterpart(
                base, family, str(meta.get("language", "")), str(meta.get("source_sha256", ""))
            )
            if translation not in known_names:
                translation = suggested
            translation = ask("Translation of", translation)
        meta.update({"title": title, "document_family": family, "authority_role": role})
        meta.pop("authority", None)
        if effective:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", effective):
                print("  Invalid date format; keeping review_required=true.")
                metadata_valid = False
            else:
                meta["effective_from"] = effective
        elif "effective_from" in meta:
            meta.pop("effective_from")
        if edition:
            meta["edition"] = edition
        if translation:
            meta["translation_of"] = translation
        ready = input("Mark reviewed and ready for activation? [y/N]: ").strip().lower() in {"y", "yes"}
        if ready and not metadata_valid:
            ready = False
        if ready and not (effective or edition):
            print("  Cannot mark ready without an effective date or edition/version.")
            ready = False
        meta["review_required"] = not ready
        identity = effective or (slug(edition, "edition") if edition else "review")
        language = str(meta.get("language", "und"))
        safe_family = family if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", family) else slug(family)
        meta["document_id"] = f"{safe_family}_{language}_{identity}"
        target = working / f"{safe_family}_{language}_{identity}.md"
        path.write_text(render_markdown(meta, body), encoding="utf-8")
        if target != path:
            if target.exists():
                die(f"review rename would overwrite existing file: {target.name}")
            path.rename(target)
            path = target
        print(f"  saved: {path.name} ({'READY' if ready else 'REVIEW REQUIRED'})")


def docs_in(folder: Path) -> list[Path]:
    return sorted(path for path in folder.glob("*.md") if path.is_file() and not path.is_symlink())


def validate_collection(base: Path, *, include_working: bool = False) -> tuple[int, int]:
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: dict[str, Path] = {}
    seen_active: dict[tuple[str, str], Path] = {}
    folders = [base / "active"] + ([base / "working"] if include_working else [])
    for folder in folders:
        for path in docs_in(folder):
            try:
                meta = importer.front_matter(path)
                source_file = str(meta.get("source_file", ""))
                source_digest = str(meta.get("source_sha256", ""))
                if not source_file or not importer.SHA256_RE.fullmatch(source_digest):
                    die("missing/invalid source_file or source_sha256")
                importer._resolve_source(path if folder.name == "active" else base / "active" / path.name, source_file, source_digest)
                document_id = str(meta.get("document_id", ""))
                family = str(meta.get("document_family", ""))
                language = str(meta.get("language", ""))
                if not document_id or not family or not language:
                    die("document_id, document_family and language are required")
                previous = seen_ids.get(document_id)
                if previous:
                    die(f"duplicate document_id also used by {previous.name}")
                seen_ids[document_id] = path
                if folder.name == "active":
                    if bool_value(meta.get("review_required", False)):
                        die("active document still has review_required=true")
                    key = (family, language)
                    previous = seen_active.get(key)
                    if previous:
                        die(f"multiple active revisions for document_family/language; also {previous.name}")
                    seen_active[key] = path
                if str(meta.get("status", "")) == "currentness-not-verified":
                    warnings.append(f"{path.name}: currentness has not been independently verified")
                role = str(meta.get("authority_role", meta.get("authority", "")))
                if role == "translation":
                    counterpart = str(meta.get("translation_of", ""))
                    if not counterpart:
                        warnings.append(f"{path.name}: translation has no translation_of counterpart yet")
                    else:
                        counterpart_paths = (base / "active" / counterpart, base / "working" / counterpart)
                        if not any(candidate.is_file() for candidate in counterpart_paths):
                            warnings.append(f"{path.name}: translation_of target does not exist: {counterpart}")
            except (OSError, ValueError) as exc:
                errors.append(f"{path}: {exc}")
    for item in errors:
        print(f"FAIL: {item}")
    for item in warnings:
        print(f"WARN: {item}")
    return len(errors), len(warnings)


def cmd_validate(args: argparse.Namespace) -> None:
    base = collection_path(args.root.resolve(), args.scope, args.collection)
    errors, warnings = validate_collection(base, include_working=args.include_working)
    active_count = len(docs_in(base / "active"))
    print(f"\nValidation: {active_count} active document(s), {errors} failure(s), {warnings} warning(s)")
    if errors:
        raise RuntimeError("RAG collection validation failed")


def referenced_sources(base: Path, exclude: Path | None = None) -> set[str]:
    result: set[str] = set()
    for folder in (base / "active", base / "working"):
        for path in docs_in(folder):
            if exclude is not None and path == exclude:
                continue
            try:
                value = str(importer.front_matter(path).get("source_file", ""))
            except (OSError, ValueError):
                continue
            if value:
                result.add(value)
    return result


def supersede_path(base: Path, path: Path) -> None:
    meta = importer.front_matter(path)
    target = base / "superseded" / path.name
    if target.exists():
        stamp = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
        target = target.with_name(f"{target.stem}_{stamp}{target.suffix}")
    path.replace(target)
    source_name = str(meta.get("source_file", ""))
    if source_name and source_name not in referenced_sources(base):
        source = base / "sources" / source_name
        if source.is_file():
            destination = base / "superseded" / source.name
            if not destination.exists():
                source.replace(destination)
    print(f"  superseded: {target.name}")


def cmd_activate(args: argparse.Namespace) -> None:
    base = collection_path(args.root.resolve(), args.scope, args.collection)
    candidates = docs_in(base / "working")
    if args.files:
        wanted = set(args.files)
        candidates = [p for p in candidates if p.name in wanted]
        missing = wanted - {p.name for p in candidates}
        if missing:
            die("working file(s) not found: " + ", ".join(sorted(missing)))
    elif not args.all_ready:
        die("specify one or more working filenames or use --all-ready")
    ready: list[tuple[Path, dict[str, object]]] = []
    for path in candidates:
        meta = importer.front_matter(path)
        if bool_value(meta.get("review_required", True)):
            if args.files:
                die(f"{path.name}: review_required=true; run bc250-rag review first")
            continue
        ready.append((path, meta))
    if not ready:
        print("No reviewed working documents are ready for activation.")
        return
    print(f"Activation plan: {len(ready)} document(s)")
    for path, meta in ready:
        family = str(meta.get("document_family", ""))
        language = str(meta.get("language", ""))
        prior = []
        for active in docs_in(base / "active"):
            active_meta = importer.front_matter(active)
            if str(active_meta.get("document_family", "")) == family and str(active_meta.get("language", "")) == language:
                prior.append(active)
        print(f"  activate {path.name}")
        for old in prior:
            print(f"    replaces {old.name}")
    if not args.yes:
        if not sys.stdin.isatty():
            die("activation confirmation requires a terminal or --yes")
        if input("Proceed? [y/N]: ").strip().lower() not in {"y", "yes"}:
            print("Cancelled.")
            return
    for path, meta in ready:
        family = str(meta.get("document_family", ""))
        language = str(meta.get("language", ""))
        for old in list(docs_in(base / "active")):
            active_meta = importer.front_matter(old)
            if str(active_meta.get("document_family", "")) == family and str(active_meta.get("language", "")) == language:
                supersede_path(base, old)
        destination = base / "active" / path.name
        path.replace(destination)
        print(f"  activated:  {destination.name}")
    errors, warnings = validate_collection(base)
    print(f"Activation complete: {errors} failure(s), {warnings} warning(s).")
    if errors:
        raise RuntimeError("post-activation validation failed")


def cmd_supersede(args: argparse.Namespace) -> None:
    base = collection_path(args.root.resolve(), args.scope, args.collection)
    if Path(args.file).name != args.file:
        die("active Markdown must be specified by filename, not a path")
    path = base / "active" / args.file
    if not path.is_file() or path.is_symlink():
        die(f"active Markdown not found: {args.file}")
    supersede_path(base, path)


def cmd_status(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    scopes = [args.scope] if args.scope else list(importer.SCOPES)
    found = False
    for scope in scopes:
        scope_dir = root / scope
        if not scope_dir.is_dir():
            continue
        collections = [collection_path(root, scope, args.collection)] if args.collection else sorted(p for p in scope_dir.iterdir() if p.is_dir())
        for base in collections:
            if not base.is_dir():
                continue
            found = True
            print(f"\n[{scope.upper()}] {base.name}")
            counts = {name: len([p for p in (base / name).iterdir() if p.is_file()]) if (base / name).is_dir() else 0 for name in ("sources", "working", "active", "superseded")}
            inbox_counts = {lane: len([p for p in (base / "inbox" / lane).iterdir() if p.is_file()]) if (base / "inbox" / lane).is_dir() else 0 for lane in INBOX_LANES}
            print(f"  sources:    {counts['sources']:4d}")
            print(f"  working:    {counts['working']:4d}")
            print(f"  active:     {counts['active']:4d}")
            print(f"  superseded: {counts['superseded']:4d}")
            print("  inbox:      " + ", ".join(f"{lane}={count}" for lane, count in inbox_counts.items()))
            review = 0
            families: dict[str, set[str]] = {}
            for path in docs_in(base / "working"):
                try:
                    meta = importer.front_matter(path)
                    review += int(bool_value(meta.get("review_required", True)))
                except (OSError, ValueError):
                    review += 1
            for path in docs_in(base / "active"):
                try:
                    meta = importer.front_matter(path)
                except (OSError, ValueError):
                    continue
                families.setdefault(str(meta.get("document_family", "")), set()).add(str(meta.get("language", "")))
            paired = sum(1 for langs in families.values() if any(v.startswith("de") for v in langs) and any(v.startswith("fr") for v in langs))
            print(f"  review required: {review}")
            print(f"  active DE/FR paired families: {paired}")
    if not found:
        print(f"No RAG collections found below {root}.")


def validate_lifecycle_root(root: Path) -> tuple[int, int, int]:
    collections = 0
    errors = 0
    warnings = 0
    for scope in importer.SCOPES:
        scope_dir = root / scope
        if not scope_dir.is_dir():
            continue
        for base in sorted(path for path in scope_dir.iterdir() if path.is_dir()):
            if not (base / "active").is_dir():
                continue
            collections += 1
            collection_errors, collection_warnings = validate_collection(base)
            errors += collection_errors
            warnings += collection_warnings
    return collections, errors, warnings


def cmd_ingest(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    collections, errors, warnings = validate_lifecycle_root(root)
    print(f"Pre-ingestion lifecycle validation: {collections} collection(s), {errors} failure(s), {warnings} warning(s)")
    if errors:
        die("RAG lifecycle validation failed; no Open WebUI changes were attempted")
    run_ingest(args)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bc250-rag",
        description="Prepare, review, validate, activate and ingest the local BC-250 RAG corpus. Automation never promotes working drafts to active without human approval.",
    )
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=f"corpus root (default: {DEFAULT_ROOT})")
    sub = p.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create one public/confidential collection and its three batch inbox lanes")
    init.add_argument("scope", choices=importer.SCOPES)
    init.add_argument("collection")

    prep = sub.add_parser("prepare-batch", help="locally extract and agent-normalize PDFs from german/french/bilingual inboxes into working/")
    prep.add_argument("scope", choices=importer.SCOPES)
    prep.add_argument("collection")
    prep.add_argument("--model", default=DEFAULT_AGENT_MODEL)
    prep.add_argument("--agent-url", default=DEFAULT_AGENT_URL)
    prep.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, help=f"safe single-pass extraction limit (default: {DEFAULT_MAX_CHARS})")
    prep.add_argument("--dry-run", action="store_true")

    review = sub.add_parser("review", help="interactively correct titles/metadata and mark working drafts ready")
    review.add_argument("scope", choices=importer.SCOPES)
    review.add_argument("collection")
    review.add_argument("--all", action="store_true", help="also revisit drafts already marked reviewed")

    validate = sub.add_parser("validate", help="validate active corpus provenance, uniqueness and review state")
    validate.add_argument("scope", choices=importer.SCOPES)
    validate.add_argument("collection")
    validate.add_argument("--include-working", action="store_true")

    activate = sub.add_parser("activate", help="atomically promote reviewed working Markdown and supersede prior same-family/language revisions")
    activate.add_argument("scope", choices=importer.SCOPES)
    activate.add_argument("collection")
    activate.add_argument("files", nargs="*")
    activate.add_argument("--all-ready", action="store_true")
    activate.add_argument("--yes", action="store_true")

    sup = sub.add_parser("supersede", help="remove one active Markdown revision from ingestion while retaining audit evidence")
    sup.add_argument("scope", choices=importer.SCOPES)
    sup.add_argument("collection")
    sup.add_argument("file")

    status = sub.add_parser("status", help="show collection lifecycle counts and DE/FR pairing status")
    status.add_argument("scope", nargs="?", choices=importer.SCOPES)
    status.add_argument("collection", nargs="?")

    ingest = sub.add_parser("ingest", help="validate and incrementally sync all active Markdown to Open WebUI")
    ingest.add_argument("--url", default=importer.DEFAULT_URL)
    ingest.add_argument("--token-file")
    ingest.add_argument("--prune", action="store_true")
    ingest.add_argument("--timeout", type=int, default=600)

    # Compatibility commands for the existing bc250-rag-import interface.
    plan = sub.add_parser("plan", help="legacy compatibility: print the existing importer plan")
    plan.add_argument("legacy_root", nargs="?", type=Path)
    sync = sub.add_parser("sync", help="legacy compatibility: sync using the existing importer contract")
    sync.add_argument("legacy_root", nargs="?", type=Path)
    sync.add_argument("--url", default=importer.DEFAULT_URL)
    sync.add_argument("--token-file")
    sync.add_argument("--prune", action="store_true")
    sync.add_argument("--timeout", type=int, default=600)
    return p


def run_ingest(args: argparse.Namespace, *, plan_only: bool = False) -> None:
    root = (getattr(args, "legacy_root", None) or args.root).resolve()
    docs, warnings = importer.discover(root)
    if plan_only:
        importer.print_plan(root, docs, warnings)
    else:
        importer.sync(root, docs, warnings, args)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        commands = {
            "init": cmd_init,
            "prepare-batch": cmd_prepare,
            "review": cmd_review,
            "validate": cmd_validate,
            "activate": cmd_activate,
            "supersede": cmd_supersede,
            "status": cmd_status,
        }
        if args.command in commands:
            commands[args.command](args)
        elif args.command == "ingest":
            cmd_ingest(args)
        elif args.command == "plan":
            run_ingest(args, plan_only=True)
        elif args.command == "sync":
            run_ingest(args)
        return 0
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
