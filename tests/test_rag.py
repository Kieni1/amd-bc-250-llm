from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class RagBaselineTests(unittest.TestCase):
    def test_packaged_open_webui_rag_defaults(self) -> None:
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(
            encoding="utf-8"
        )
        expected = (
            "Environment=RAG_EMBEDDING_ENGINE=ollama",
            "Environment=RAG_EMBEDDING_MODEL=embed-jina-v5-small-retrieval-q4-k-m",
            "Environment=RAG_OLLAMA_BASE_URL=http://host.containers.internal:11437",
            "Environment=RAG_TEXT_SPLITTER=token",
            "Environment=CHUNK_SIZE=1500",
            "Environment=CHUNK_OVERLAP=200",
            "Environment=ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER=true",
            "Environment=RAG_TOP_K=8",
            "Environment=RAG_RELEVANCE_THRESHOLD=0",
            'Environment="RAG_TEMPLATE=Answer the user from the supplied context.',
            "Environment=ENABLE_RAG_HYBRID_SEARCH=false",
            "Environment=ENABLE_ASYNC_EMBEDDING=false",
            "Environment=ENABLE_RETRIEVAL_QUERY_GENERATION=false",
            'Environment="RAG_EMBEDDING_QUERY_PREFIX=Query: "',
            'Environment="RAG_EMBEDDING_CONTENT_PREFIX=Document: "',
            "Environment=CONTENT_EXTRACTION_ENGINE=tika",
            "Environment=TIKA_SERVER_URL=http://tika:9998",
            "Environment=TIKA_SERVER_VERSION=3",
            "Environment=ENABLE_KNOWLEDGE_FILE_RETENTION=false",
            "Environment=RAG_FILE_MAX_SIZE=128",
            "Environment=RAG_FILE_MAX_COUNT=20",
            "Environment=RAG_EMBEDDING_BATCH_SIZE=1",
            "Environment=CHUNK_MIN_SIZE_TARGET=0",
            "Environment=RAG_SYSTEM_CONTEXT=false",
        )
        for line in expected:
            self.assertIn(line, quadlet)

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
            "bc250-model",
            "bc250-ocr",
            "bc250-rag-import",
            "bc250-status",
            "bc250-verify",
        ):
            self.assertIn(command, guide)

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
        self.assertIn('section "Documents / RAG"', verify)
        self.assertIn("RAG_EMBEDDING_MODEL", verify)
        self.assertIn("CONTENT_EXTRACTION_ENGINE", verify)
        self.assertIn("/api/tags", verify)
        self.assertNotIn("/api/embed", verify)

    def test_rag_pilot_template_is_placeholder_only_and_packaged(self) -> None:
        template = (ROOT / "examples/rag/pilot-evaluation.tsv").read_text(
            encoding="utf-8"
        )
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn("[GERMAN_SEARCHABLE_PDF]", template)
        self.assertIn("[UNANSWERED_CONTROL]", template)
        self.assertNotIn("Customer project A", template)
        self.assertIn(
            "examples/rag/pilot-evaluation.tsv\t{share}/examples/rag/pilot-evaluation.tsv",
            manifest,
        )
        self.assertIn(
            "examples/rag/document-template.md\t{share}/examples/rag/document-template.md",
            manifest,
        )


if __name__ == "__main__":
    unittest.main()
