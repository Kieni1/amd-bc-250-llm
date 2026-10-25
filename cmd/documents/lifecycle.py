#!/usr/bin/env python3
"""BC-250 managed document corpus lifecycle and batch-preparation helper.

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
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import importer

DEFAULT_ROOT = importer.DEFAULT_ROOT
DEFAULT_AGENT_URL = os.environ.get("BC250_RAG_AGENT_URL", "http://127.0.0.1:11436").rstrip("/")
DEFAULT_AGENT_MODEL = os.environ.get(
    "BC250_RAG_AGENT_MODEL", "agentic-ornith15-9b-ornith-q5-k-m"
)
DEFAULT_MAX_CHARS = int(os.environ.get("BC250_RAG_MAX_CHARS", "50000"))
DEFAULT_OWUI_TOKEN_FILE = Path("/var/lib/bc250-llm-server/secrets/openwebui-admin.key")
INBOX_LANES = ("german", "french", "bilingual")
COLLECTION_DIRS = ("sources", "working", "active", "superseded")
SOURCE_EXTENSIONS = {".pdf", ".docx"}
DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
REASONING_MARKER_RE = re.compile(r"</?think(?:\s|>)|<\|/?think\|>", re.IGNORECASE)


class DeferredPreparation(RuntimeError):
    """Expected manual deferral, not an automated processing failure."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class AgentGenerationLimit(RuntimeError):
    """The local normalizer exhausted generation before returning usable content."""


def die(message: str) -> None:
    raise ValueError(message)


def collection_path(root: Path, scope: str, collection: str) -> Path:
    if scope not in importer.SCOPES:
        die(f"scope must be one of: {', '.join(importer.SCOPES)}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", collection):
        die(
            f"invalid collection identifier {collection!r}; use only letters, numbers, dot, underscore or hyphen"
        )
    return root / scope / collection


def ensure_collection(root: Path, scope: str, collection: str) -> Path:
    base = collection_path(root, scope, collection)
    # Confidential corpora stay root-private by default. Public here means the
    # source material is public; the appliance still does not expose the tree.
    mode = 0o700 if scope == "confidential" else 0o750
    for path in (base, *(base / name for name in COLLECTION_DIRS), base / "inbox"):
        if path.is_symlink():
            die(f"document lifecycle directory must not be a symlink: {path}")
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(mode)
    for lane in INBOX_LANES:
        path = base / "inbox" / lane
        if path.is_symlink():
            die(f"document inbox lane must not be a symlink: {path}")
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
        "document_id", "revision_id", "document_family", "title", "organisation", "language",
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


def pdf_source_text(pdf: Path) -> tuple[int, str]:
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


def _docx_text_from_paragraph(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == f"{{{DOCX_NS['w']}}}t":
            parts.append(node.text or "")
        elif node.tag == f"{{{DOCX_NS['w']}}}tab":
            parts.append("\t")
        elif node.tag in {f"{{{DOCX_NS['w']}}}br", f"{{{DOCX_NS['w']}}}cr"}:
            parts.append("\n")
    text = "".join(parts).strip()
    if not text:
        return ""
    style = paragraph.find("./w:pPr/w:pStyle", DOCX_NS)
    style_name = style.get(f"{{{DOCX_NS['w']}}}val", "") if style is not None else ""
    heading = re.fullmatch(r"Heading([1-6])", style_name, re.IGNORECASE)
    if heading:
        return "#" * int(heading.group(1)) + " " + text
    if paragraph.find("./w:pPr/w:numPr", DOCX_NS) is not None:
        return "- " + text
    return text


def docx_source_text(docx: Path) -> tuple[int, str]:
    """Extract readable DOCX text with lightweight structural hints.

    The local Agent remains responsible for normalization. This extractor deliberately
    uses only the OOXML package itself so managed DOCX preparation does not depend on a
    remote service or an additional Python library.
    """
    try:
        with zipfile.ZipFile(docx) as archive:
            raw = archive.read("word/document.xml")
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        die(f"cannot read DOCX source {docx.name}: {exc}")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        die(f"cannot parse DOCX source {docx.name}: {exc}")
    body = root.find(".//w:body", DOCX_NS)
    if body is None:
        die(f"DOCX source has no document body: {docx.name}")
    blocks: list[str] = []
    for child in body:
        local = child.tag.rsplit("}", 1)[-1]
        if local == "p":
            text = _docx_text_from_paragraph(child)
            if text:
                blocks.append(text)
        elif local == "tbl":
            for row in child.findall("./w:tr", DOCX_NS):
                cells: list[str] = []
                for cell in row.findall("./w:tc", DOCX_NS):
                    value = " ".join(
                        part
                        for paragraph in cell.findall(".//w:p", DOCX_NS)
                        if (part := _docx_text_from_paragraph(paragraph))
                    )
                    cells.append(value)
                if any(cells):
                    blocks.append(" | ".join(cells))
    return 0, "\n\n".join(blocks) + ("\n" if blocks else "")


def source_text(source: Path) -> tuple[int, str]:
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        return pdf_source_text(source)
    if suffix == ".docx":
        return docx_source_text(source)
    die(
        f"unsupported inbox file type for automated preparation: {source.name}; "
        "supported managed sources are PDF and DOCX"
    )


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
    command = shutil.which("bc250")
    if not command:
        die("bc250 dispatcher is required to enter exclusive agent mode")
    result = subprocess.run([command, "advanced", "agent", "enter"], text=True, check=False)
    if result.returncode != 0 or not agent_ready(url):
        die("exclusive agent mode did not become ready on port 11436")
    return True


def restore_normal_if_needed(switched: bool) -> str | None:
    if not switched:
        return None
    command = shutil.which("bc250")
    if not command:
        return (
            "bc250 dispatcher is unavailable; normal Ollama topology was not restored. "
            "Run sudo bc250 advanced agent normal before continuing."
        )
    result = subprocess.run([command, "advanced", "agent", "normal"], text=True, check=False)
    if result.returncode != 0:
        return (
            "automatic restoration of normal Ollama topology failed. "
            "Run sudo bc250 advanced agent normal before continuing."
        )
    return None


def normalize_prompt(
    text: str, language: str, bilingual: bool, *, chunk_index: int = 1, chunk_total: int = 1
) -> str:
    language_name = "German" if language.startswith("de") else "French"
    bilingual_rule = (
        f"The source is bilingual. Extract and normalize ONLY the {language_name} source text; "
        "do not translate the other language into it. Preserve every substantive clause in this language."
        if bilingual
        else f"The source is expected to be {language_name}. Do not translate it."
    )
    chunk_rule = (
        "Return ONLY normalized Markdown body text, beginning with one '# ' document title."
        if chunk_total == 1 or chunk_index == 1
        else "Return ONLY normalized Markdown continuation text for this chunk. Do not repeat the document title."
    )
    chunk_context = (
        ""
        if chunk_total == 1
        else f"This is source chunk {chunk_index} of {chunk_total}. Preserve this chunk completely; do not summarize material from other chunks."
    )
    return f"""You are a careful local document-ingestion editor for a private German/French managed-document corpus.

{chunk_rule} Do not return YAML or a code fence.
{chunk_context}

Rules:
- Preserve the complete substantive source wording. Do not summarize, paraphrase, interpret or invent text.
- Preserve original legal/article numbering exactly. Never replace source identifiers with editorial numbering.
- Use ##/### only for real document sections. Use bold labels for clauses/articles where helpful.
- Preserve dates, amounts, percentages, currency, names, identifiers and legal references exactly.
- Do not remove unique codes, identifiers, article references, markers, numbers or alphanumeric labels as layout noise.
- Remove repeated decorative page headers/footers only when their repeated/decorative nature is clear. When uncertain, preserve the source text.
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


def final_agent_content(data: object) -> str:
    if not isinstance(data, dict):
        die("agent returned an invalid response object")
    if data.get("done") is not True:
        die("agent response did not report terminal completion")
    if str(data.get("done_reason", "")).lower() in {"length", "max_tokens"}:
        raise AgentGenerationLimit("agent output hit its generation limit before usable normalized content")
    message = data.get("message")
    if not isinstance(message, dict):
        die("agent response did not contain a chat message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        die("agent returned no normalized Markdown final content")
    output = content.strip()
    if REASONING_MARKER_RE.search(output):
        die("agent final content contains native reasoning markers; refusing contaminated document draft")
    lines = [line for line in output.splitlines() if line.strip()]
    if lines and re.match(r"^\s*(```|~~~)", lines[0]):
        die(
            "agent final content is wrapped in a Markdown fence; "
            "refusing output that violates the raw-Markdown contract"
        )
    return output + "\n"


def call_agent(url: str, model: str, prompt: str, *, think: bool = True) -> str:
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": think,
            "keep_alive": "10m",
            "options": {"temperature": 0, "num_ctx": 32768, "num_predict": 16384},
        }
    ).encode("utf-8")
    request = Request(url + "/api/chat", data=payload, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=1800) as response:
            data = json.loads(response.read() or b"{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        die(f"agent generation failed: HTTP {exc.code}: {detail}")
    except (OSError, URLError, json.JSONDecodeError) as exc:
        die(f"agent generation failed: {exc}")
    return final_agent_content(data)



def split_source_chunks(text: str, max_chars: int) -> list[str]:
    """Split source text at paragraph/line boundaries without dropping content."""
    if max_chars < 1000:
        die("--max-chars must be at least 1000")
    if len(text) <= max_chars:
        return [text]
    paragraphs = re.split(r"(\n\s*\n)", text)
    chunks: list[str] = []
    current = ""
    for part in paragraphs:
        if not part:
            continue
        if len(current) + len(part) <= max_chars:
            current += part
            continue
        if current.strip():
            chunks.append(current.strip() + "\n")
            current = ""
        while len(part) > max_chars:
            cut = part.rfind("\n", 0, max_chars + 1)
            if cut < max_chars // 2:
                cut = part.rfind(" ", 0, max_chars + 1)
            if cut < max_chars // 2:
                cut = max_chars
            chunks.append(part[:cut].strip() + "\n")
            part = part[cut:].lstrip()
        current = part
    if current.strip():
        chunks.append(current.strip() + "\n")
    return chunks


def normalize_source_text(
    url: str, model: str, text: str, language: str, bilingual: bool, max_chars: int
) -> str:
    chunks = split_source_chunks(text, max_chars)
    outputs: list[str] = []
    for index, chunk in enumerate(chunks, 1):
        prompt = normalize_prompt(
            chunk, language, bilingual, chunk_index=index, chunk_total=len(chunks)
        )
        try:
            normalized = call_agent(url, model, prompt, think=True)
        except AgentGenerationLimit:
            print(
                f"  normalizer: chunk {index}/{len(chunks)} exhausted reasoning/output budget; retrying once without extended thinking",
                file=sys.stderr,
            )
            try:
                normalized = call_agent(url, model, prompt, think=False)
            except AgentGenerationLimit as exc:
                raise DeferredPreparation(
                    "normalization incomplete",
                    f"chunk {index}/{len(chunks)} exhausted the local Agent generation budget twice; source remains in inbox",
                ) from exc
        if index > 1:
            normalized = re.sub(r"\A\s*#\s+[^\n]+\n+", "", normalized, count=1)
        outputs.append(normalized.strip())
    return "\n\n".join(part for part in outputs if part).rstrip() + "\n"


def title_from_body(body: str, fallback: str) -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", body)
    return match.group(1).strip() if match else fallback


def critical_tokens(text: str) -> set[str]:
    patterns = (
        (r"\b\d{1,4}(?:[.'’ ]\d{3})*(?:[.,]\d+)?\s*%?\b", re.IGNORECASE),
        (r"\b(?:CHF|EUR|USD)\s*\d[\d'’., ]*\b", re.IGNORECASE),
        (r"\b(?:Art\.|Artikel|article|al\.|Abs\.)\s*\d+[A-Za-z.-]*\b", re.IGNORECASE),
        (r"\b[A-Z]{2}\d{2}[A-Z0-9 ]{10,30}\b", 0),
        (r"\b(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b", 0),
    )
    found: set[str] = set()
    for pattern, flags in patterns:
        found.update(match.group(0).strip() for match in re.finditer(pattern, text, flags=flags))
    return found


def fidelity_note(source: str, body: str, bilingual: bool) -> str:
    return fidelity_assessment(source, body, bilingual)[1]


def fidelity_assessment(source: str, body: str, bilingual: bool) -> tuple[str, str]:
    if bilingual:
        return (
            "review",
            "bilingual source: automated whole-source token coverage not scored; visual/manual review required",
        )
    expected = critical_tokens(source)
    missing = sorted(token for token in expected if token not in body)
    if not expected:
        return (
            "not-scored",
            "no critical numeric/legal tokens detected for automated coverage check",
        )
    if not missing:
        return "pass", f"critical-token coverage PASS ({len(expected)}/{len(expected)})"
    preview = ", ".join(missing[:5])
    return (
        "review",
        f"critical-token coverage REVIEW ({len(expected)-len(missing)}/{len(expected)}); missing examples: {preview}",
    )


def provisional_family(source: Path) -> str:
    return slug(source.stem)


def stable_document_id(family: str, language: str) -> str:
    return f"{family}_{language}"


def revision_id_for(document_id: str, source_sha: str) -> str:
    return f"{document_id}_sha256_{source_sha.lower()}"


def unique_working_path(working: Path, family: str, language: str, digest: str) -> tuple[Path, bool]:
    candidates = (
        working / f"{family}_{language}_review.md",
        working / f"{family}_{language}_{digest[:8]}_review.md",
    )
    for candidate in candidates:
        if not candidate.exists():
            return candidate, False
        if candidate.is_symlink() or not candidate.is_file():
            die(f"working draft path is not a regular file: {candidate.name}")
        try:
            meta = importer.front_matter(candidate)
        except (OSError, ValueError) as exc:
            die(f"cannot safely reuse existing working draft {candidate.name}: {exc}")
        if str(meta.get("source_sha256", "")).lower() == digest.lower():
            return candidate, True
    die(
        "working draft collision: both the normal and digest-qualified review filenames "
        f"already contain different source material for {family}/{language}"
    )


def write_draft(
    base: Path,
    source: Path,
    source_sha: str,
    body: str,
    language: str,
    role: str,
    *,
    bilingual: bool,
    translation_of: str = "",
    fidelity_status: str = "",
    fidelity_note_text: str = "",
) -> tuple[Path, bool]:
    family = provisional_family(source)
    path, existed = unique_working_path(base / "working", family, language, source_sha)
    if existed:
        return path, False
    title = title_from_body(body, source.stem)
    document_id = stable_document_id(family, language)
    meta: dict[str, object] = {
        "document_id": document_id,
        "revision_id": revision_id_for(document_id, source_sha),
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
    if fidelity_status:
        meta["bc250_fidelity_status"] = fidelity_status
        meta["bc250_fidelity_note"] = fidelity_note_text
    path.write_text(render_markdown(meta, body), encoding="utf-8")
    path.chmod(0o640)
    return path, True


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
    if source.suffix.lower() not in SOURCE_EXTENSIONS:
        die(
            f"unsupported inbox file type for automated preparation: {source.name}; "
            "supported managed sources are PDF and DOCX"
        )
    pages, text = source_text(source)
    compact = re.sub(r"\s+", "", text)
    print(f"\nSource: {source.name}")
    print(f"  lane:       {lane}")
    print(f"  pages:      {pages or ('n/a' if source.suffix.lower() == '.docx' else 'unknown')}")
    print(f"  characters: {len(text):,}")
    if len(compact) < 300:
        kind = "OCR required" if source.suffix.lower() == ".pdf" else "insufficient text"
        advice = (
            "little/no selectable text detected; leave in inbox and use the local OCR workflow before managed preparation"
            if source.suffix.lower() == ".pdf"
            else "little/no readable text was extracted from the DOCX; inspect the source before retrying"
        )
        raise DeferredPreparation(kind, advice)
    digest = sha256(source)
    outputs: list[tuple[str, str, str]] = []
    if lane == "german":
        outputs.append((
            "de-CH", "authoritative",
            normalize_source_text(url, model, text, "de-CH", False, max_chars),
        ))
    elif lane == "french":
        outputs.append((
            "fr-CH", "translation",
            normalize_source_text(url, model, text, "fr-CH", False, max_chars),
        ))
    else:
        outputs.append((
            "de-CH", "authoritative",
            normalize_source_text(url, model, text, "de-CH", True, max_chars),
        ))
        outputs.append((
            "fr-CH", "translation",
            normalize_source_text(url, model, text, "fr-CH", True, max_chars),
        ))

    for language, _role, _body in outputs:
        unique_working_path(base / "working", provisional_family(source), language, digest)

    stored = store_source(base, source, digest)
    drafts: list[Path] = []
    german_revision_id = ""
    for language, role, body in outputs:
        fidelity_status, fidelity_note_text = fidelity_assessment(
            text, body, lane == "bilingual"
        )
        if language == "de-CH":
            draft, created = write_draft(
                base,
                stored,
                digest,
                body,
                language,
                role,
                bilingual=lane == "bilingual",
                fidelity_status=fidelity_status,
                fidelity_note_text=fidelity_note_text,
            )
            german_revision_id = importer.revision_identity(importer.front_matter(draft))
        else:
            draft, created = write_draft(
                base,
                stored,
                digest,
                body,
                language,
                role,
                bilingual=lane == "bilingual",
                translation_of=german_revision_id,
                fidelity_status=fidelity_status,
                fidelity_note_text=fidelity_note_text,
            )
        drafts.append(draft)
        suffix = "" if created else " (existing draft; unchanged)"
        print(f"  draft:      {draft.name}{suffix}")
        if created:
            print(f"  integrity:  {fidelity_note_text}")
    return drafts


def cmd_init(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    requested = collection_path(root, args.scope, args.collection)
    existed = requested.is_dir()
    base = ensure_collection(root, args.scope, args.collection)
    state = "already present / converged" if existed else "created"
    print(f"Document collection ready: {base} ({state})")
    print("Inbox lanes:")
    for lane in INBOX_LANES:
        print(f"  {base / 'inbox' / lane}")
    print("\nPlace source PDF or DOCX files in german/, french/ or bilingual/, then run:")
    print(f"  sudo bc250 document prepare-batch {args.scope} {args.collection}")


def cmd_prepare(args: argparse.Namespace) -> None:
    require_local_agent_url(args.agent_url)
    base = ensure_collection(args.root.resolve(), args.scope, args.collection)
    pending: list[tuple[str, Path]] = []
    for lane in INBOX_LANES:
        folder = base / "inbox" / lane
        for path in sorted(folder.iterdir()):
            if path.is_symlink():
                die(f"Document inbox entries must not be symlinks: {path}")
            if path.is_file():
                pending.append((lane, path))
    print(f"Document batch preparation: {args.scope}/{args.collection}")
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
    restore_error: str | None = None
    deferred = 0
    failed = 0
    try:
        available = agent_models(args.agent_url)
        if args.model.removesuffix(":latest") not in available:
            die(
                f"agent model is not registered on :11436: {args.model}; "
                f"install it with sudo bc250 model apply agentic {args.model}"
            )
        prepared_files = 0
        drafts = 0
        for lane, path in pending:
            try:
                created = prepare_one(
                    base, path, lane, args.agent_url, args.model, args.max_chars
                )
                prepared_files += 1
                drafts += len(created)
            except DeferredPreparation as exc:
                deferred += 1
                print(f"  DEFERRED — {exc.kind}: {path.name}", file=sys.stderr)
                print(f"    {exc}", file=sys.stderr)
            except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
                failed += 1
                print(f"  ERROR — processing failed: {path.name}", file=sys.stderr)
                print(f"    {exc}", file=sys.stderr)
        print("\nBatch summary")
        print(f"  input files:      {len(pending)}")
        print(f"  prepared:         {prepared_files}")
        print(f"  Markdown drafts:  {drafts}")
        print(f"  deferred/manual:  {deferred}")
        print(f"  failed:           {failed}")
        print(f"  working folder:   {base / 'working'}")
        print("\nAutomation stops here by design. Review metadata/content before activation.")
        print(f"Next: sudo bc250 document review {args.scope} {args.collection}")
    finally:
        restore_error = restore_normal_if_needed(switched)
        if restore_error and sys.exc_info()[0] is not None:
            print(f"ERROR: {restore_error}", file=sys.stderr)

    if restore_error:
        raise RuntimeError(restore_error)
    if failed or deferred:
        parts = []
        if failed:
            parts.append(f"{failed} failed")
        if deferred:
            parts.append(f"{deferred} deferred/manual")
        raise RuntimeError(
            "batch preparation incomplete (" + ", ".join(parts) + "); resolve the listed inputs and retry"
        )


def find_counterpart(base: Path, family: str, language: str, source_sha: str = "") -> str:
    if not language.lower().startswith("fr"):
        return ""
    family_matches: list[str] = []
    source_matches: list[str] = []
    for folder in (base / "working", base / "active"):
        for path in docs_in(folder):
            try:
                meta = importer.front_matter(path)
                lane, _ = importer.route(meta)
            except (OSError, ValueError):
                continue
            if lane != "original":
                continue
            revision_id = importer.revision_identity(meta)
            if not revision_id:
                continue
            if str(meta.get("document_family", "")) == family:
                family_matches.append(revision_id)
            if source_sha and str(meta.get("source_sha256", "")) == source_sha:
                source_matches.append(revision_id)
    if len(family_matches) == 1:
        return family_matches[0]
    return source_matches[0] if len(source_matches) == 1 else ""


def ask(label: str, current: str) -> str:
    value = input(f"{label} [{current}]: ").strip()
    return value or current


def known_revisions(base: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for folder in (base / "working", base / "active"):
        for path in docs_in(folder):
            try:
                meta = importer.front_matter(path)
            except (OSError, ValueError):
                continue
            revision_id = importer.revision_identity(meta)
            if revision_id:
                result[revision_id] = path
    return result


def normalize_translation_reference(base: Path, value: str) -> str:
    """Convert legacy filename references to revision IDs when they are unambiguous."""
    value = value.strip()
    if not value:
        return ""
    revisions = known_revisions(base)
    if value in revisions:
        return value
    matches = [path for path in revisions.values() if path.name == value]
    if len(matches) == 1:
        return importer.revision_identity(importer.front_matter(matches[0]))
    return value


def source_integrity_status(base: Path, meta: dict[str, object]) -> tuple[bool, str]:
    """Return a concise provenance result for the source referenced by one draft."""
    source_file = str(meta.get("source_file", "")).strip()
    source_sha = str(meta.get("source_sha256", "")).strip()
    if not source_file:
        return False, "FAIL (source_file is missing)"
    if not importer.SHA256_RE.fullmatch(source_sha):
        return False, "FAIL (source_sha256 is missing or invalid)"
    try:
        resolved, warning = importer._resolve_source(
            base / "active" / "_review-provenance.md", source_file, source_sha
        )
    except (OSError, ValueError) as exc:
        return False, f"FAIL ({exc})"
    detail = f"MATCH ({source_sha[:12]}…; {resolved.name})"
    if warning:
        detail += f" — {warning}"
    return True, detail


def cmd_review(args: argparse.Namespace) -> None:
    base = collection_path(args.root.resolve(), args.scope, args.collection)
    working = base / "working"
    if not sys.stdin.isatty():
        die("review is interactive; run it from a terminal")
    docs = docs_in(working)
    if not docs:
        print("No working Markdown drafts to review.")
        return
    review_docs: list[Path] = []
    for path in docs:
        meta = importer.front_matter(path)
        if args.all or bool_value(meta.get("review_required", True)):
            review_docs.append(path)
    if not review_docs:
        print("No working Markdown drafts require review.")
        return
    for index, path in enumerate(review_docs, 1):
        meta, body = split_markdown(path)
        print(f"\n[{index}/{len(review_docs)}] {path.name}")
        source_ok, source_state = source_integrity_status(base, meta)
        print(f"  source:      {meta.get('source_file', '')}")
        print(f"  source SHA:  {source_state}")
        print(f"  language:    {meta.get('language', '')}")
        print(f"  title:       {meta.get('title', '')}")
        print(f"  family:      {meta.get('document_family', '')}")
        print(f"  authority:   {meta.get('authority_role', meta.get('authority', ''))}")
        print(f"  document:    {meta.get('document_id', '')}")
        print(f"  revision:    {importer.revision_identity(meta)}")
        print(f"  effective:   {meta.get('effective_from', '') or '(not set)'}")
        print(f"  edition:     {meta.get('edition', '') or '(not set)'}")
        print(f"  currentness: {meta.get('status', '') or '(not set)'}")
        translation_ref = str(meta.get("translation_of", "")).strip()
        if translation_ref:
            print(f"  translated:  {translation_ref}")
        fidelity_status = str(meta.get("bc250_fidelity_status", "")).strip().lower()
        fidelity_note_text = str(meta.get("bc250_fidelity_note", "")).strip()
        if fidelity_status == "review":
            meta.pop("bc250_fidelity_acknowledged", None)
        if fidelity_status:
            print(f"  fidelity:   {fidelity_status}")
            if fidelity_note_text:
                print(f"              {fidelity_note_text}")
        source_name = str(meta.get("source_file", "")).strip()
        if source_name:
            print(f"  source path: {base / 'sources' / source_name}")
        print(f"  draft path:  {path}")
        if not getattr(args, "metadata_only", False):
            lines = body.rstrip().splitlines()
            visible = lines if getattr(args, "full_body", False) else lines[:40]
            print("\n--- Normalized draft content ---")
            print("\n".join(visible) if visible else "(empty draft body)")
            if len(visible) < len(lines):
                print(f"... {len(lines) - len(visible)} more line(s); rerun with --full-body or inspect the draft path above.")
            print("--- End draft content ---\n")
            print("Semantic approval requires comparing the complete normalized draft with the source document.")
        title = ask("Title", str(meta.get("title", "")))
        family = ask("Document family", str(meta.get("document_family", "")))
        effective = ask(
            "Effective date (YYYY-MM-DD; or provide edition/version below)",
            str(meta.get("effective_from", "")),
        )
        edition = ask(
            "Edition/version (required when effective date is blank)",
            str(meta.get("edition", "")),
        )
        role = ask(
            "Authority role (authoritative|translation)",
            str(meta.get("authority_role", meta.get("authority", ""))),
        )
        if role == "original":
            role = "authoritative"
        metadata_valid = source_ok
        if not source_ok:
            print("  Source provenance must be repaired before this draft can be marked ready.")
        if not title.strip():
            print("  Title may not be empty; keeping review_required=true.")
            metadata_valid = False
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", family):
            print(
                "  Document family must use only letters, numbers, dot, underscore or hyphen; "
                "keeping review_required=true."
            )
            metadata_valid = False
        if role not in {"authoritative", "translation"}:
            print("  Authority role must be authoritative or translation; keeping review_required=true.")
            metadata_valid = False

        language = str(meta.get("language", "und"))
        safe_family = (
            family
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", family)
            else slug(family)
        )
        source_sha = str(meta.get("source_sha256", ""))
        document_id = stable_document_id(safe_family, language)
        revision_id = (
            revision_id_for(document_id, source_sha)
            if importer.SHA256_RE.fullmatch(source_sha)
            else importer.revision_identity(meta)
        )
        meta.update(
            {
                "title": title,
                "document_family": family,
                "authority_role": role,
                "document_id": document_id,
                "revision_id": revision_id,
            }
        )
        meta.pop("authority", None)

        try:
            lane, _ = importer.route(meta)
        except ValueError as exc:
            print(f"  {exc}; keeping review_required=true.")
            metadata_valid = False
            lane = ""

        translation = normalize_translation_reference(
            base, str(meta.get("translation_of", ""))
        )
        if lane == "translation":
            revisions = known_revisions(base)
            suggested = find_counterpart(base, family, language, source_sha)
            if translation not in revisions:
                translation = suggested
            translation = ask("German revision ID translated from", translation)
            translation = normalize_translation_reference(base, translation)
            if not translation:
                print("  A French translation must reference its German revision ID; keeping review_required=true.")
                metadata_valid = False
            elif translation not in known_revisions(base):
                print("  Referenced German revision ID was not found; keeping review_required=true.")
                metadata_valid = False
            meta["translation_of"] = translation
        else:
            meta.pop("translation_of", None)

        if effective:
            try:
                importer.validate_iso_date(effective, "effective_from")
            except ValueError as exc:
                print(f"  {exc}; keeping review_required=true.")
                metadata_valid = False
            else:
                meta["effective_from"] = effective
        elif "effective_from" in meta:
            meta.pop("effective_from")
        if edition:
            meta["edition"] = edition

        try:
            importer.validate_document_metadata(meta, active=False)
        except ValueError as exc:
            print(f"  Metadata validation: {exc}; keeping review_required=true.")
            metadata_valid = False

        ready = input("Mark reviewed and ready for activation? [y/N]: ").strip().lower() in {"y", "yes"}
        if ready and not metadata_valid:
            ready = False
        if ready and not (effective or edition):
            print("  Cannot mark ready without an effective date or edition/version.")
            ready = False
        if ready and fidelity_status == "review":
            acknowledged = input(
                "Fidelity check requires manual review. Confirm you compared the source and accept this draft? [y/N]: "
            ).strip().lower() in {"y", "yes"}
            if not acknowledged:
                print("  Fidelity review was not acknowledged; keeping review_required=true.")
                meta.pop("bc250_fidelity_acknowledged", None)
                ready = False
            else:
                meta["bc250_fidelity_acknowledged"] = "true"
        elif fidelity_status != "review":
            meta.pop("bc250_fidelity_acknowledged", None)
        meta["review_required"] = not ready
        identity = effective or (slug(edition, "edition") if edition else "review")
        target = working / f"{safe_family}_{language}_{identity}.md"
        path.write_text(render_markdown(meta, body), encoding="utf-8")
        if target != path:
            if target.exists():
                die(f"review rename would overwrite existing file: {target.name}")
            path.rename(target)
            path = target
        print(f"  saved: {path.name} ({'READY' if ready else 'REVIEW REQUIRED'})")


def docs_in(folder: Path) -> list[Path]:
    if folder.is_symlink():
        die(f"Managed document directory must not be a symlink: {folder}")
    result: list[Path] = []
    for path in sorted(folder.glob("*.md")):
        if path.is_symlink():
            die(f"Managed document Markdown must not be a symlink: {path}")
        if path.is_file():
            result.append(path)
    return result


def validate_entries(
    base: Path,
    entries: list[tuple[Path, str]],
    *,
    emit: bool = True,
    forbidden_legacy_names: set[str] | None = None,
) -> tuple[int, int]:
    """Validate a real or projected corpus state without mutating it."""
    errors: list[str] = []
    warnings: list[str] = []
    records: list[dict[str, object]] = []
    seen_revisions: dict[str, Path] = {}
    seen_active: dict[tuple[str, str], Path] = {}
    seen_active_names: dict[str, Path] = {}

    for path, state in entries:
        try:
            meta, body = split_markdown(path)
            if REASONING_MARKER_RE.search(body):
                die("document body contains native reasoning markers (<think>/thinking delimiters)")
            lane, language = importer.validate_document_metadata(
                meta, active=state == "active"
            )
            source_file = str(meta.get("source_file", ""))
            source_digest = str(meta.get("source_sha256", ""))
            if not source_file or not importer.SHA256_RE.fullmatch(source_digest):
                die("missing/invalid source_file or source_sha256")
            importer._resolve_source(
                base / "active" / path.name, source_file, source_digest
            )
            family = str(meta.get("document_family", ""))
            revision_id = importer.revision_identity(meta)
            previous_revision = seen_revisions.get(revision_id)
            if previous_revision:
                die(
                    f"duplicate revision identity also used by {previous_revision.name}: {revision_id}"
                )
            seen_revisions[revision_id] = path
            if state == "active":
                key = (family, language)
                previous = seen_active.get(key)
                if previous:
                    die(
                        "multiple active revisions for document_family/language; "
                        f"also {previous.name}"
                    )
                seen_active[key] = path
                prior_name = seen_active_names.get(path.name)
                if prior_name:
                    die(f"duplicate active filename also used by {prior_name}")
                seen_active_names[path.name] = path
            if str(meta.get("status", "")) == "currentness-not-verified":
                warnings.append(
                    f"{path.name}: currentness has not been independently verified"
                )
            records.append(
                {
                    "path": path,
                    "state": state,
                    "meta": meta,
                    "lane": lane,
                    "language": language,
                    "family": family,
                    "revision_id": revision_id,
                }
            )
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: {exc}")

    by_revision = {str(record["revision_id"]): record for record in records}
    by_name = {Path(record["path"]).name: record for record in records}
    for record in records:
        if record["lane"] != "translation":
            continue
        path = Path(record["path"])
        meta = record["meta"]
        assert isinstance(meta, dict)
        counterpart = str(meta.get("translation_of", "")).strip()
        must_resolve = record["state"] == "active" or not bool_value(
            meta.get("review_required", True)
        )
        if not counterpart:
            message = f"{path.name}: French translation has no German revision ID in translation_of"
            (errors if must_resolve else warnings).append(message)
            continue
        target = by_revision.get(counterpart)
        if target is None and counterpart in by_name:
            if forbidden_legacy_names and counterpart in forbidden_legacy_names:
                errors.append(
                    f"{path.name}: legacy translation_of filename {counterpart!r} would "
                    "retarget a changed revision; re-review the translation and store the "
                    "German revision ID"
                )
                continue
            target = by_name[counterpart]
            warnings.append(
                f"{path.name}: translation_of uses legacy filename {counterpart!r}; "
                "re-review it to store the German revision ID"
            )
        if target is None:
            message = (
                f"{path.name}: translation_of target does not exist in the proposed corpus: "
                f"{counterpart}"
            )
            (errors if must_resolve else warnings).append(message)
            continue
        if target["lane"] != "original" or not str(target["language"]).lower().startswith("de"):
            errors.append(
                f"{path.name}: translation_of must reference an authoritative German revision"
            )
            continue
        if target["family"] != record["family"]:
            errors.append(
                f"{path.name}: translation_of references a different document_family "
                f"({target['family']} != {record['family']})"
            )

    if emit:
        for item in errors:
            print(f"FAIL: {item}")
        for item in warnings:
            print(f"WARN: {item}")
    return len(errors), len(warnings)


def validate_collection(
    base: Path, *, include_working: bool = False, emit: bool = True
) -> tuple[int, int]:
    entries = [(path, "active") for path in docs_in(base / "active")]
    if include_working:
        entries.extend((path, "working") for path in docs_in(base / "working"))
    return validate_entries(base, entries, emit=emit)


def cmd_validate(args: argparse.Namespace) -> None:
    base = collection_path(args.root.resolve(), args.scope, args.collection)
    errors, warnings = validate_collection(base, include_working=args.include_working)
    active_count = len(docs_in(base / "active"))
    print(f"\nValidation: {active_count} active document(s), {errors} failure(s), {warnings} warning(s)")
    if errors:
        raise RuntimeError("Managed document collection validation failed")


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


def unique_superseded_target(base: Path, path: Path, reserved: set[Path]) -> Path:
    target = base / "superseded" / path.name
    if not target.exists() and target not in reserved:
        return target
    stamp = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    target = target.with_name(f"{target.stem}_{stamp}{target.suffix}")
    counter = 2
    while target.exists() or target in reserved:
        target = target.with_name(f"{path.stem}_{stamp}_{counter}{path.suffix}")
        counter += 1
    return target


def transaction_move(source: Path, destination: Path, journal: list[tuple[Path, Path]]) -> None:
    if not source.exists() or source.is_symlink():
        raise RuntimeError(f"transaction source disappeared or is unsafe: {source}")
    if destination.exists():
        raise RuntimeError(f"transaction destination already exists: {destination}")
    source.rename(destination)
    journal.append((source, destination))


def rollback_moves(journal: list[tuple[Path, Path]]) -> list[str]:
    failures: list[str] = []
    for original, moved in reversed(journal):
        try:
            if original.exists():
                failures.append(f"rollback destination unexpectedly exists: {original}")
                continue
            if not moved.exists():
                failures.append(f"rollback source is missing: {moved}")
                continue
            moved.rename(original)
        except OSError as exc:
            failures.append(f"{moved} -> {original}: {exc}")
    return failures


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

    ready: list[tuple[Path, dict[str, object], tuple[str, str]]] = []
    targets: dict[tuple[str, str], Path] = {}
    for path in candidates:
        meta = importer.front_matter(path)
        if bool_value(meta.get("review_required", True)):
            if args.files:
                die(f"{path.name}: review_required=true; run bc250 document review first")
            continue
        _lane, language = importer.validate_document_metadata(meta, active=True)
        family = str(meta.get("document_family", ""))
        key = (family, language)
        previous = targets.get(key)
        if previous:
            die(
                "activation is ambiguous: multiple reviewed working documents target "
                f"{family}/{language}: {previous.name}, {path.name}; no files changed"
            )
        targets[key] = path
        ready.append((path, meta, key))

    if not ready:
        print("No reviewed working documents are ready for activation.")
        return

    active_docs = docs_in(base / "active")
    active_meta: dict[Path, dict[str, object]] = {
        path: importer.front_matter(path) for path in active_docs
    }
    replaced: list[Path] = []
    for active in active_docs:
        meta = active_meta[active]
        key = (str(meta.get("document_family", "")), str(meta.get("language", "")))
        if key in targets:
            replaced.append(active)

    replaced_set = set(replaced)
    projected = [
        (path, "active") for path in active_docs if path not in replaced_set
    ] + [(path, "active") for path, _meta, _key in ready]
    errors, warnings = validate_entries(
        base, projected, forbidden_legacy_names={path.name for path in replaced}
    )
    if errors:
        raise RuntimeError(
            "activation plan validation failed; no files were changed"
        )

    print(f"Activation plan: {len(ready)} document(s)")
    for path, _meta, key in ready:
        print(f"  activate {path.name}")
        for old in replaced:
            old_meta = active_meta[old]
            old_key = (
                str(old_meta.get("document_family", "")),
                str(old_meta.get("language", "")),
            )
            if old_key == key:
                print(f"    replaces {old.name}")
    if warnings:
        print(f"  projected validation warnings: {warnings}")
    if not args.yes:
        if not sys.stdin.isatty():
            die("activation confirmation requires a terminal or --yes")
        if input("Proceed with this all-or-nothing activation? [y/N]: ").strip().lower() not in {"y", "yes"}:
            print("Cancelled; no files changed.")
            return

    remaining_working = [
        path for path in docs_in(base / "working") if path not in {item[0] for item in ready}
    ]
    referenced_after: set[str] = set()
    for path, _state in projected:
        referenced_after.add(str(importer.front_matter(path).get("source_file", "")))
    for path in remaining_working:
        referenced_after.add(str(importer.front_matter(path).get("source_file", "")))
    referenced_after.discard("")

    reserved: set[Path] = set()
    old_moves: list[tuple[Path, Path]] = []
    for old in replaced:
        destination = unique_superseded_target(base, old, reserved)
        reserved.add(destination)
        old_moves.append((old, destination))

    candidate_moves = [
        (path, base / "active" / path.name) for path, _meta, _key in ready
    ]
    source_moves: list[tuple[Path, Path]] = []
    seen_source_names: set[str] = set()
    for old in replaced:
        source_name = str(active_meta[old].get("source_file", ""))
        if (
            not source_name
            or source_name in referenced_after
            or source_name in seen_source_names
        ):
            continue
        seen_source_names.add(source_name)
        source = base / "sources" / source_name
        destination = base / "superseded" / source_name
        if source.is_file() and not source.is_symlink() and not destination.exists():
            source_moves.append((source, destination))

    journal: list[tuple[Path, Path]] = []
    try:
        for source, destination in old_moves:
            transaction_move(source, destination, journal)
        for source, destination in candidate_moves:
            transaction_move(source, destination, journal)
        for source, destination in source_moves:
            transaction_move(source, destination, journal)
        post_errors, post_warnings = validate_collection(base, emit=False)
        if post_errors:
            raise RuntimeError(
                f"post-activation validation found {post_errors} failure(s)"
            )
    except (OSError, RuntimeError, ValueError) as exc:
        rollback_failures = rollback_moves(journal)
        if rollback_failures:
            raise RuntimeError(
                "activation transaction failed and rollback was incomplete: "
                + str(exc)
                + "; "
                + "; ".join(rollback_failures)
            ) from exc
        raise RuntimeError(
            f"activation transaction failed; all filesystem moves were rolled back: {exc}"
        ) from exc

    for old, destination in old_moves:
        print(f"  superseded: {destination.name}")
    for _source, destination in candidate_moves:
        print(f"  activated:  {destination.name}")
    print(
        f"Activation complete: 0 failure(s), {post_warnings} warning(s). "
        "The requested batch committed as one transaction."
    )


def cmd_supersede(args: argparse.Namespace) -> None:
    base = collection_path(args.root.resolve(), args.scope, args.collection)
    if Path(args.file).name != args.file:
        die("active Markdown must be specified by filename, not a path")
    path = base / "active" / args.file
    if not path.is_file() or path.is_symlink():
        die(f"active Markdown not found: {args.file}")

    projected = [
        (candidate, "active")
        for candidate in docs_in(base / "active")
        if candidate != path
    ]
    errors, warnings = validate_entries(base, projected)
    if errors:
        raise RuntimeError(
            "supersede would leave the active corpus invalid; no files were changed"
        )

    meta = importer.front_matter(path)
    target = unique_superseded_target(base, path, set())
    source_name = str(meta.get("source_file", ""))
    source_move: tuple[Path, Path] | None = None
    if source_name and source_name not in referenced_sources(base, exclude=path):
        source = base / "sources" / source_name
        destination = base / "superseded" / source_name
        if source.is_file() and not source.is_symlink() and not destination.exists():
            source_move = (source, destination)

    journal: list[tuple[Path, Path]] = []
    try:
        transaction_move(path, target, journal)
        if source_move:
            transaction_move(source_move[0], source_move[1], journal)
        post_errors, post_warnings = validate_collection(base, emit=False)
        if post_errors:
            raise RuntimeError(
                f"post-supersede validation found {post_errors} failure(s)"
            )
    except (OSError, RuntimeError, ValueError) as exc:
        rollback_failures = rollback_moves(journal)
        if rollback_failures:
            raise RuntimeError(
                "supersede transaction failed and rollback was incomplete: "
                + str(exc)
                + "; "
                + "; ".join(rollback_failures)
            ) from exc
        raise RuntimeError(
            f"supersede transaction failed; all filesystem moves were rolled back: {exc}"
        ) from exc

    print(f"  superseded: {target.name}")
    if warnings or post_warnings:
        print(f"  validation warnings: {post_warnings}")



def knowledge_sync_summary(root: Path, args: argparse.Namespace) -> dict[str, int | str]:
    docs, warnings = importer.discover(root)
    importer.validate_sync_endpoint(
        args.url,
        docs,
        root=root,
        allow_remote=bool(getattr(args, "allow_remote", False)),
        allow_confidential_remote=bool(getattr(args, "allow_confidential_remote", False)),
    )
    token_file = getattr(args, "token_file", None)
    if not token_file and DEFAULT_OWUI_TOKEN_FILE.is_file():
        token_file = str(DEFAULT_OWUI_TOKEN_FILE)
    if token_file:
        token = importer.read_protected_token_file(Path(token_file))
    else:
        token = os.environ.get("OPEN_WEBUI_API_KEY", "").strip()
        if not token:
            die("Knowledge sync inspection requires --token-file or OPEN_WEBUI_API_KEY")
    api = importer.OpenWebUI(args.url, token, args.timeout)
    grouped = importer.groups(docs)
    expected = importer.expected_knowledge(root)
    totals = {"added": 0, "modified": 0, "deleted": 0, "unchanged": 0, "missing": 0}
    for name in sorted(set(grouped) | set(expected)):
        members = grouped.get(name, [])
        kb = api.find_knowledge(name)
        if kb is None:
            if members:
                totals["missing"] += 1
            continue
        kb_id = kb.get("id") if isinstance(kb, dict) else None
        if not isinstance(kb_id, str) or not kb_id.strip():
            raise RuntimeError(f"Open WebUI knowledge response for {name!r} is missing a valid id")
        diff = importer.validate_diff_result(api.diff(kb_id, members))
        totals["added"] += len(diff.get("added", []))
        totals["modified"] += len(diff.get("modified", []))
        totals["deleted"] += len(diff.get("deleted", []))
        totals["unchanged"] += int(diff.get("unmodified_count", 0) or 0)
    totals["warnings"] = len(warnings)
    pending = totals["added"] + totals["modified"] + totals["deleted"] + totals["missing"]
    totals["state"] = "CURRENT" if pending == 0 else "CHANGES PENDING"
    return totals

def cmd_status(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    if args.scope and args.collection:
        requested = collection_path(root, args.scope, args.collection)
        if not requested.is_dir():
            die(f"Document collection not found: {args.scope}/{args.collection}")
    scopes = [args.scope] if args.scope else list(importer.SCOPES)
    found = False
    for scope in scopes:
        scope_dir = root / scope
        if not scope_dir.is_dir():
            continue
        collections = (
            [collection_path(root, scope, args.collection)]
            if args.collection
            else sorted(p for p in scope_dir.iterdir() if p.is_dir())
        )
        for base in collections:
            if not base.is_dir():
                continue
            found = True
            working_docs = docs_in(base / "working")
            active_docs = docs_in(base / "active")
            print(f"\n[{scope.upper()}] {base.name}")
            counts = {
                name: len([p for p in (base / name).iterdir() if p.is_file()])
                if (base / name).is_dir()
                else 0
                for name in ("sources", "working", "active", "superseded")
            }
            inbox_counts = {
                lane: len([p for p in (base / "inbox" / lane).iterdir() if p.is_file()])
                if (base / "inbox" / lane).is_dir()
                else 0
                for lane in INBOX_LANES
            }
            inbox_total = sum(inbox_counts.values())

            awaiting_review = 0
            ready = 0
            fidelity_pending = 0
            active_currentness_unverified = 0
            families: dict[str, set[str]] = {}
            for path in working_docs:
                try:
                    meta = importer.front_matter(path)
                except (OSError, ValueError):
                    awaiting_review += 1
                    continue
                if bool_value(meta.get("review_required", True)):
                    awaiting_review += 1
                else:
                    ready += 1
                fidelity_status = str(meta.get("bc250_fidelity_status", "")).strip().lower()
                fidelity_ack = bool_value(meta.get("bc250_fidelity_acknowledged", False))
                if fidelity_status == "review" and not fidelity_ack:
                    fidelity_pending += 1
            for path in active_docs:
                try:
                    meta = importer.front_matter(path)
                except (OSError, ValueError):
                    continue
                families.setdefault(str(meta.get("document_family", "")), set()).add(
                    str(meta.get("language", ""))
                )
                active_currentness_unverified += int(
                    str(meta.get("status", "")).strip() == "currentness-not-verified"
                )
            paired = sum(
                1
                for langs in families.values()
                if any(v.startswith("de") for v in langs)
                and any(v.startswith("fr") for v in langs)
            )
            errors, warnings = validate_collection(
                base, include_working=True, emit=False
            )
            health = "FAIL" if errors else ("WARN" if warnings else "PASS")
            print(f"  Active:               {counts['active']}")
            print(f"  Needs review:         {awaiting_review}")
            print(f"  Ready to activate:    {ready}")
            print(f"  Inbox pending:        {inbox_total}")
            print(f"  Superseded:           {counts['superseded']}")
            print(f"  Currentness review:   {active_currentness_unverified}")
            print(f"  DE/FR paired families: {paired}")
            print(
                f"  Lifecycle validation: {health} "
                f"({errors} failure(s), {warnings} warning(s))"
            )
            if getattr(args, "verbose", False):
                print(f"  Sources:              {counts['sources']}")
                print(f"  Fidelity review:      {fidelity_pending}")
                print(
                    "  Inbox lanes:          "
                    + ", ".join(f"{lane}={count}" for lane, count in inbox_counts.items())
                )
    if not found:
        print(f"No document collections found below {root}.")
    if getattr(args, "knowledge", False):
        sync = knowledge_sync_summary(root, args)
        print("\nKnowledge sync")
        print(f"  State:     {sync['state']}")
        print(
            "  Pending:   "
            f"{sync['added']} add / {sync['modified']} update / "
            f"{sync['deleted']} stale / {sync['missing']} missing knowledge base(s)"
        )
        print(f"  Unchanged: {sync['unchanged']}")
        if sync.get("warnings"):
            print(f"  Local discovery warnings: {sync['warnings']}")
    else:
        print("\nKnowledge sync: NOT INSPECTED")
        print("  Run with --knowledge and an administrator API key for a read-only diff.")


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
        die("Managed document lifecycle validation failed; no Open WebUI changes were attempted")
    run_ingest(args)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bc250 document",
        description="Prepare, review, validate, activate and sync the local BC-250 managed document corpus. Automation never promotes working drafts to active without human approval.",
    )
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=f"corpus root (default: {DEFAULT_ROOT})")
    sub = p.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create one collection in the selected public/confidential scope with three language inboxes")
    init.add_argument("scope", choices=importer.SCOPES)
    init.add_argument("collection")

    prep = sub.add_parser("prepare-batch", help="extract and locally normalize PDF/DOCX sources into review drafts under working/")
    prep.add_argument("scope", choices=importer.SCOPES)
    prep.add_argument("collection")
    prep.add_argument("--model", default=DEFAULT_AGENT_MODEL, help="local Agent model used only for normalization")
    prep.add_argument("--agent-url", default=DEFAULT_AGENT_URL, help=f"loopback Agent endpoint (default: {DEFAULT_AGENT_URL})")
    prep.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, help=f"maximum extracted characters per normalization chunk (default: {DEFAULT_MAX_CHARS})")
    prep.add_argument("--dry-run", action="store_true", help="list pending sources without changing files or runtime topology")

    review = sub.add_parser(
        "review",
        help="interactively verify provenance/metadata/fidelity and mark working drafts ready",
    )
    review.add_argument("scope", choices=importer.SCOPES)
    review.add_argument("collection")
    review.add_argument("--all", action="store_true", help="also revisit drafts already marked reviewed")
    review_display = review.add_mutually_exclusive_group()
    review_display.add_argument("--full-body", action="store_true", help="print the complete normalized draft body during review")
    review_display.add_argument("--metadata-only", action="store_true", help="suppress normalized-content preview (not recommended for semantic approval)")

    validate = sub.add_parser("validate", help="validate active corpus provenance, uniqueness and review state")
    validate.add_argument("scope", choices=importer.SCOPES)
    validate.add_argument("collection")
    validate.add_argument("--include-working", action="store_true")

    activate = sub.add_parser("activate", help="transactionally promote a validated batch of reviewed working Markdown and roll back ordinary runtime move failures")
    activate.add_argument("scope", choices=importer.SCOPES)
    activate.add_argument("collection")
    activate.add_argument("files", nargs="*", help="specific reviewed working Markdown files to activate")
    activate.add_argument("--all-ready", action="store_true", help="activate every working draft already marked ready")
    activate.add_argument("--yes", action="store_true", help="apply the validated activation plan without confirmation")

    sup = sub.add_parser("supersede", help="supersede one active Markdown revision while retaining audit evidence")
    sup.add_argument("scope", choices=importer.SCOPES)
    sup.add_argument("collection")
    sup.add_argument("file")

    status = sub.add_parser(
        "status",
        help="show lifecycle counts, review/currentness state and validation health",
    )
    status.add_argument("scope", nargs="?", choices=importer.SCOPES)
    status.add_argument("collection", nargs="?")
    status.add_argument("--verbose", action="store_true", help="show source, fidelity and per-inbox detail")
    status.add_argument("--knowledge", action="store_true", help="perform a read-only Open WebUI Knowledge diff and report sync state")
    status.add_argument("--url", default=importer.DEFAULT_URL, help=f"Open WebUI URL for --knowledge (default: {importer.DEFAULT_URL})")
    status.add_argument("--token-file", help="protected Open WebUI administrator API-key file for --knowledge")
    status.add_argument("--timeout", type=int, default=60, help="per-request timeout for --knowledge (default: 60 seconds)")
    status.add_argument("--allow-remote", action="store_true", help="permit read-only Knowledge inspection against non-loopback Open WebUI")
    status.add_argument("--allow-confidential-remote", action="store_true", help="also permit confidential-scope Knowledge inspection on a remote endpoint")

    ingest = sub.add_parser("ingest", help="validate and incrementally synchronize active Markdown with Open WebUI Knowledge")
    ingest.add_argument("--url", default=importer.DEFAULT_URL, help=f"Open WebUI URL (default: {importer.DEFAULT_URL})")
    ingest.add_argument("--token-file", help="protected Open WebUI administrator API-key file")
    ingest.add_argument(
        "--allow-remote",
        action="store_true",
        help="explicitly permit non-loopback Open WebUI; credentials and document content leave the appliance",
    )
    ingest.add_argument(
        "--allow-confidential-remote",
        action="store_true",
        help="also permit confidential-scope documents on an explicitly enabled remote endpoint",
    )
    ingest.add_argument("--prune", action="store_true", help="remove stale remote managed-document files after successful replacement/sync")
    ingest.add_argument("--timeout", type=int, default=600, help="per-request Open WebUI timeout in seconds (default: 600)")

    return p


def run_ingest(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    docs, warnings = importer.discover(root)
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
        return 0
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
