"""Reusable fixture/oracle helpers for BC-250 dependency-depth tests.

These helpers encode corrections discovered during the Open WebUI/Tika A-C
DEVICE campaign.  They stay source-test-only: package runtime behavior is
implemented elsewhere, while future qualification harnesses can reuse these
unambiguous fixture/oracle semantics.
"""

from __future__ import annotations

import io
import re
import zipfile

MARKDOWN_ESCAPE_RE = re.compile(r"\\([`*_{}\[\]()#+.!|>\-])")
XLSX_MARKER = "BC250_DEPTH_XLSX_OK"
DOCX_MARKER = "BC250_DEPTH_DOCX_OK"
OPENWEBUI_DUPLICATE_CONTENT_MESSAGES = (
    "Duplicate content detected. Please provide unique content to proceed.",
    "Duplicate document content — this content is already present in the knowledge collection.",
)


def normalize_tika_markdown(text: str) -> str:
    """Normalize only Markdown punctuation escapes emitted by Tika's md endpoint."""
    return MARKDOWN_ESCAPE_RE.sub(r"\1", text)


def tika_marker_present(raw_text: str, marker: str) -> bool:
    return marker in raw_text or marker in normalize_tika_markdown(raw_text)


def minimal_xlsx_bytes() -> bytes:
    """Build an XLSX whose requested validation answer appears only once."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Validation" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Validation code: {XLSX_MARKER}</t></is></c></row></sheetData>
</worksheet>""",
        )
    return output.getvalue()


def minimal_docx_bytes() -> bytes:
    """Build a small uncompressed DOCX so truncated local entries stay inspectable."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/document.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{DOCX_MARKER}</w:t></w:r></w:p></w:body></w:document>""",
        )
    return output.getvalue()


def truncate_zip_central_directory(payload: bytes) -> bytes:
    marker = b"PK\x01\x02"
    position = payload.find(marker)
    if position < 0:
        raise AssertionError("fixture has no ZIP central directory")
    return payload[:position]


def expected_duplicate_rejection(status: str, error: str | None) -> bool:
    """Recognize Open WebUI's intentional duplicate-content policy outcome."""
    return (
        status == "failed"
        and bool(error)
        and any(message in error for message in OPENWEBUI_DUPLICATE_CONTENT_MESSAGES)
    )
