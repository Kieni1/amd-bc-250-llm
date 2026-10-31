from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import types
import unittest
import zipfile
from pathlib import Path

from tests import dependency_depth_harness as DEPTH

ROOT = Path(__file__).resolve().parent.parent


class _GuardResponse:
    def __init__(self, payload: object, *, status_code: int = 200, json_error: bool = False) -> None:
        self.payload = payload
        self.status_code = status_code
        self.reason = "OK"
        self.json_error = json_error

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> object:
        if self.json_error:
            raise ValueError("invalid json")
        return self.payload


def _load_tika_guard(response: _GuardResponse):
    fake_requests = types.ModuleType("requests")

    def fake_put(url: object, *args: object, **kwargs: object) -> _GuardResponse:
        del url, args, kwargs
        return response

    fake_requests.put = fake_put  # type: ignore[attr-defined]
    old_requests = sys.modules.get("requests")
    sys.modules["requests"] = fake_requests
    try:
        path = ROOT / "config/openwebui/runtime/sitecustomize.py"
        spec = importlib.util.spec_from_file_location("bc250_openwebui_sitecustomize_test", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if old_requests is None:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = old_requests
    return module, fake_requests


class RagBaselineTests(unittest.TestCase):
    def test_bash_completion_exposes_current_rag_lifecycle_and_remote_safety_flags(self) -> None:
        completion = (ROOT / "packaging/completions/bc250.bash").read_text(encoding="utf-8")
        for command in ("init", "prepare-batch", "review", "validate", "activate", "supersede", "status", "ingest"):
            self.assertIn(command, completion)
        self.assertIn("--allow-remote", completion)
        self.assertIn("--allow-confidential-remote", completion)

    def test_packaged_open_webui_rag_defaults(self) -> None:
        desired = json.loads(
            (ROOT / "config/openwebui/desired-state.json").read_text(encoding="utf-8")
        )
        embedding = desired["embedding"]
        rag = desired["rag"]
        self.assertEqual(embedding["RAG_EMBEDDING_ENGINE"], "ollama")
        self.assertEqual(embedding["RAG_EMBEDDING_MODEL"], "embed-jina-v5-small-retrieval-q4-k-m")
        self.assertEqual(embedding["ollama_config"]["url"], "http://host.containers.internal:11437")
        self.assertEqual(embedding["RAG_EMBEDDING_BATCH_SIZE"], 1)
        self.assertFalse(embedding["ENABLE_ASYNC_EMBEDDING"])
        self.assertEqual(embedding["RAG_EMBEDDING_CONCURRENT_REQUESTS"], 1)
        self.assertEqual(embedding["RAG_EMBEDDING_QUERY_PREFIX"], "Query: ")
        self.assertEqual(embedding["RAG_EMBEDDING_CONTENT_PREFIX"], "Document: ")
        self.assertEqual(rag["TEXT_SPLITTER"], "token")
        self.assertEqual(rag["CHUNK_SIZE"], 1500)
        self.assertEqual(rag["CHUNK_OVERLAP"], 200)
        self.assertTrue(rag["ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER"])
        self.assertEqual(rag["TOP_K"], 4)
        self.assertEqual(rag["RELEVANCE_THRESHOLD"], 0)
        self.assertFalse(rag["ENABLE_RAG_HYBRID_SEARCH"])
        self.assertEqual(rag["CHUNK_MIN_SIZE_TARGET"], 0)
        self.assertEqual(rag["CONTENT_EXTRACTION_ENGINE"], "tika")
        self.assertEqual(rag["TIKA_SERVER_VERSION"], "4")

        quadlet = (ROOT / "config/containers/open-webui.container").read_text(encoding="utf-8")
        for line in (
            'Environment="RAG_EMBEDDING_QUERY_PREFIX=Query: "',
            'Environment="RAG_EMBEDDING_CONTENT_PREFIX=Document: "',
            "Environment=ENABLE_KNOWLEDGE_FILE_RETENTION=false",
            "Environment=RAG_FILE_MAX_SIZE=128",
            "Environment=RAG_FILE_MAX_COUNT=20",
            "Environment=RAG_SYSTEM_CONTEXT=false",
            "Environment=RAG_EMBEDDING_BUFFER_SIZE=1000",
        ):
            self.assertIn(line, quadlet)
        for persisted in ("RAG_EMBEDDING_MODEL=", "CHUNK_SIZE=", "RAG_TOP_K="):
            self.assertNotIn(persisted, quadlet)

    def test_openwebui_tika_guard_is_packaged_and_mounted_read_only(self) -> None:
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(encoding="utf-8")
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn(
            "Volume=/var/lib/bc250-llm-server/openwebui-runtime:/opt/bc250-openwebui-shim:ro,Z",
            quadlet,
        )
        self.assertIn("Environment=PYTHONPATH=/opt/bc250-openwebui-shim:/app/backend", quadlet)
        self.assertIn(
            "config/openwebui/runtime/sitecustomize.py\t/var/lib/bc250-llm-server/openwebui-runtime/sitecustomize.py",
            manifest,
        )

    def test_openwebui_tika_guard_rejects_missing_blank_and_placeholder_content(self) -> None:
        for payload in (
            {},
            {"resourceName": "corrupt.docx"},
            {"tk:content": ""},
            {"tk:content": "   \n\t"},
            {"tk:content": "<No text content found>"},
            {"tk:content": "  <No text content found>  "},
        ):
            with self.subTest(payload=payload):
                response = _GuardResponse(payload)
                module, requests = _load_tika_guard(response)
                guarded = requests.put("http://tika:9998/tika/json/md")  # type: ignore[attr-defined]
                self.assertEqual(guarded.status_code, 422)
                self.assertEqual(guarded.reason, module.NO_USABLE_TEXT_REASON)

    def test_openwebui_tika_guard_preserves_real_extraction_and_unrelated_requests(self) -> None:
        real = _GuardResponse({"tk:content": "Recovered office text"})
        _, requests = _load_tika_guard(real)
        self.assertEqual(
            requests.put("http://tika:9998/tika/json/md").status_code,  # type: ignore[attr-defined]
            200,
        )

        unrelated = _GuardResponse({})
        _, requests = _load_tika_guard(unrelated)
        self.assertEqual(
            requests.put("http://example.invalid/api").status_code,  # type: ignore[attr-defined]
            200,
        )


    def test_openwebui_duplicate_content_wording_is_explicit(self) -> None:
        response = _GuardResponse({"tk:content": "usable"})
        fake_package = types.ModuleType("open_webui")
        fake_constants = types.ModuleType("open_webui.constants")

        class UpstreamErrors:
            DUPLICATE_CONTENT = "Duplicate content detected. Please provide unique content to proceed."
            EMPTY_CONTENT = "empty"

        fake_constants.ERROR_MESSAGES = UpstreamErrors
        fake_package.constants = fake_constants
        old_package = sys.modules.get("open_webui")
        old_constants = sys.modules.get("open_webui.constants")
        sys.modules["open_webui"] = fake_package
        sys.modules["open_webui.constants"] = fake_constants
        try:
            module, _requests = _load_tika_guard(response)
            self.assertEqual(
                fake_constants.ERROR_MESSAGES.DUPLICATE_CONTENT,
                module.DUPLICATE_CONTENT_REASON,
            )
            self.assertEqual(fake_constants.ERROR_MESSAGES.EMPTY_CONTENT, "empty")
            module.install_openwebui_error_wording()
            self.assertEqual(
                fake_constants.ERROR_MESSAGES.DUPLICATE_CONTENT,
                module.DUPLICATE_CONTENT_REASON,
            )
        finally:
            if old_package is None:
                sys.modules.pop("open_webui", None)
            else:
                sys.modules["open_webui"] = old_package
            if old_constants is None:
                sys.modules.pop("open_webui.constants", None)
            else:
                sys.modules["open_webui.constants"] = old_constants

    def test_dependency_depth_duplicate_rejection_is_expected_policy(self) -> None:
        self.assertTrue(
            DEPTH.expected_duplicate_rejection(
                "failed",
                "400: Duplicate content detected. Please provide unique content to proceed.",
            )
        )
        self.assertFalse(DEPTH.expected_duplicate_rejection("failed", "embedding failed"))
        self.assertTrue(
            DEPTH.expected_duplicate_rejection(
                "failed", DEPTH.OPENWEBUI_DUPLICATE_CONTENT_MESSAGES[1]
            )
        )
        self.assertFalse(
            DEPTH.expected_duplicate_rejection(
                "completed", DEPTH.OPENWEBUI_DUPLICATE_CONTENT_MESSAGES[0]
            )
        )

    def test_openwebui_tika_guard_preserves_existing_http_and_json_failures(self) -> None:
        upstream_failure = _GuardResponse({}, status_code=500)
        _, requests = _load_tika_guard(upstream_failure)
        self.assertEqual(
            requests.put("http://tika:9998/tika/json/md").status_code,  # type: ignore[attr-defined]
            500,
        )

        invalid_json = _GuardResponse({}, json_error=True)
        _, requests = _load_tika_guard(invalid_json)
        self.assertEqual(
            requests.put("http://tika:9998/tika/json/md").status_code,  # type: ignore[attr-defined]
            200,
        )

    def test_openwebui_tika_guard_installation_is_idempotent(self) -> None:
        response = _GuardResponse({"tk:content": "real"})
        module, requests = _load_tika_guard(response)
        first_put = requests.put  # type: ignore[attr-defined]
        module.install_tika_empty_content_guard(requests)
        self.assertIs(requests.put, first_put)  # type: ignore[attr-defined]

    def test_dependency_depth_tika_marker_oracle_normalizes_markdown_escapes(self) -> None:
        raw = DEPTH.DOCX_MARKER.replace("_", r"\_")
        self.assertTrue(DEPTH.tika_marker_present(raw, DEPTH.DOCX_MARKER))
        self.assertEqual(DEPTH.normalize_tika_markdown(raw), DEPTH.DOCX_MARKER)
        narrow = DEPTH.normalize_tika_markdown(r"path\\name and \q stay; BC250\_DEPTH")
        self.assertIn(r"path\\name", narrow)
        self.assertIn(r"\q", narrow)
        self.assertIn("BC250_DEPTH", narrow)

    def test_dependency_depth_xlsx_oracle_is_unambiguous(self) -> None:
        payload = DEPTH.minimal_xlsx_bytes()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertEqual(sheet.count(DEPTH.XLSX_MARKER), 1)
        self.assertIn(f"Validation code: {DEPTH.XLSX_MARKER}", sheet)
        self.assertNotIn("Exact marker", sheet)

    def test_dependency_depth_malformed_fixture_classes_are_distinct(self) -> None:
        wrong_extension = b"Readable text saved with a .docx name\n"
        valid = DEPTH.minimal_docx_bytes()
        truncated = DEPTH.truncate_zip_central_directory(valid)
        corrupt = b"\x00\xffBC250_CORRUPT_BINARY\x10\x11"
        empty = b""

        self.assertIn(b"Readable text", wrong_extension)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(valid)))
        self.assertIn(b"word/document.xml", valid)
        self.assertIn(DEPTH.DOCX_MARKER.encode(), valid)
        self.assertFalse(zipfile.is_zipfile(io.BytesIO(truncated)))
        self.assertIn(b"word/document.xml", truncated)
        self.assertIn(DEPTH.DOCX_MARKER.encode(), truncated)
        self.assertFalse(zipfile.is_zipfile(io.BytesIO(corrupt)))
        self.assertTrue(corrupt)
        self.assertEqual(empty, b"")

    def test_rag_guide_uses_real_packaged_models_and_commands(self) -> None:
        guide = (ROOT / "docs/RAG.md").read_text(encoding="utf-8")
        model_names = set()
        for path in (ROOT / "models/modelfiles").glob("*.Modelfile"):
            match = re.search(
                r"(?m)^# Ollama model:\s*(\S+)\s*$", path.read_text(encoding="utf-8")
            )
            self.assertIsNotNone(match, path.name)
            model_names.add(match.group(1))
        for name in (
            "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl",
            "embed-jina-v5-small-retrieval-q4-k-m",
            "embed-qwen3-0.6b-q8-0",
        ):
            self.assertIn(name, model_names)
            self.assertIn(name, guide)
        for command in (
            "bc250 model",
            "bc250 ocr",
            "bc250 document",
            "bc250 status",
            "bc250 verify",
        ):
            self.assertIn(command, guide)
        self.assertIn("bc250 document ingest", guide)
        for lifecycle in (
            "init", "prepare-batch", "review", "validate", "activate",
            "supersede", "status", "ingest",
        ):
            self.assertIn(lifecycle, guide)

    def test_package_contains_no_office_document_payloads(self) -> None:
        forbidden = {
            ".pdf",
            ".doc",
            ".docx",
            ".odt",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".rtf",
        }
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        found = []
        for line in manifest.splitlines():
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) >= 4 and Path(fields[2]).suffix.lower() in forbidden:
                found.append(fields[2])
        self.assertEqual(found, [])

    def test_verify_reports_rag_without_loading_embedding_model(self) -> None:
        verify = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        self.assertIn('section "Managed documents"', verify)
        self.assertIn("RAG_EMBEDDING_MODEL", verify)
        self.assertIn("CONTENT_EXTRACTION_ENGINE", verify)
        self.assertIn("/api/tags", verify)
        self.assertNotIn("/api/embed", verify)

    def test_rag_pilot_template_is_placeholder_only_and_packaged(self) -> None:
        template = (ROOT / "examples/document/pilot-evaluation.tsv").read_text(
            encoding="utf-8"
        )
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn("[GERMAN_SEARCHABLE_PDF]", template)
        self.assertIn("[UNANSWERED_CONTROL]", template)
        self.assertNotIn("Customer project A", template)
        self.assertIn(
            "examples/document/pilot-evaluation.tsv\t{share}/examples/document/pilot-evaluation.tsv",
            manifest,
        )
        self.assertIn(
            "examples/document/document-template.md\t{share}/examples/document/document-template.md",
            manifest,
        )


if __name__ == "__main__":
    unittest.main()
