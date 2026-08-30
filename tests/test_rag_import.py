from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "models/rag/rag_import.py"

spec = importlib.util.spec_from_file_location("bc250_rag_import", SCRIPT)
assert spec and spec.loader
rag = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rag
spec.loader.exec_module(rag)


class RagImportTests(unittest.TestCase):
    def make_doc(
        self,
        root: Path,
        scope: str,
        name: str,
        language: str,
        source_language: str,
        source_name: str,
        authority: str = "",
    ) -> Path:
        base = root / scope / "COLLECTION"
        active = base / "active"
        sources = base / "sources"
        active.mkdir(parents=True, exist_ok=True)
        sources.mkdir(parents=True, exist_ok=True)
        source = sources / source_name
        source.write_bytes((name + " source").encode())
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        authority_line = f'authority: "{authority}"\n' if authority else ""
        doc = active / name
        doc.write_text(
            "---\n"
            f'document_id: "{name}"\n'
            f'language: "{language}"\n'
            f"{authority_line}"
            f'source_file: "{source_name}"\n'
            f'source_sha256: "{digest}"\n'
            "relation:\n"
            '  type: "translation-pair"\n'
            '  counterpart: "counterpart.md"\n'
            f'  source_language: "{source_language}"\n'
            "---\n\nBody\n",
            encoding="utf-8",
        )
        return doc

    def test_de_original_and_fr_translation_route_to_separate_knowledge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_doc(root, "public", "de.md", "de-CH", "de-CH", "de.pdf")
            self.make_doc(root, "public", "fr.md", "fr-CH", "de-CH", "fr.pdf")
            docs, warnings = rag.discover(root)
            self.assertEqual(warnings, [])
            self.assertEqual({doc.lane for doc in docs}, {"original", "translation"})
            self.assertEqual(
                {doc.kb_name for doc in docs},
                {"[PUBLIC] COLLECTION — Originals", "[PUBLIC] COLLECTION — Français"},
            )

    def test_explicit_english_original_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_doc(
                root, "public", "en.md", "en", "en", "en.pdf", authority="original"
            )
            docs, warnings = rag.discover(root)
            self.assertEqual(warnings, [])
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].lane, "original")
            self.assertEqual(docs[0].kb_name, "[PUBLIC] COLLECTION — Originals")

    def test_source_filename_drift_is_tolerated_only_when_sha_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = self.make_doc(
                root, "confidential", "de.md", "de-CH", "de-CH", "actual.pdf"
            )
            text = doc.read_text(encoding="utf-8").replace(
                'source_file: "actual.pdf"', 'source_file: "old-name.pdf"'
            )
            doc.write_text(text, encoding="utf-8")
            docs, warnings = rag.discover(root)
            self.assertEqual(len(docs), 1)
            self.assertEqual(len(warnings), 1)
            self.assertIn("checksum matches 'actual.pdf'", warnings[0])

    def test_source_file_cannot_escape_sources_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = self.make_doc(root, "public", "de.md", "de-CH", "de-CH", "de.pdf")
            outside = root / "outside.pdf"
            outside.write_bytes(b"outside")
            digest = hashlib.sha256(outside.read_bytes()).hexdigest()
            text = doc.read_text(encoding="utf-8")
            text = re.sub(
                r'source_file: "[^"]+"', 'source_file: "../../outside.pdf"', text
            )
            text = re.sub(r'source_sha256: "[^"]+"', f'source_sha256: "{digest}"', text)
            doc.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source_file must be a filename"):
                rag.discover(root)

    def test_active_and_source_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = self.make_doc(root, "public", "de.md", "de-CH", "de-CH", "de.pdf")
            source = doc.parent.parent / "sources/de.pdf"
            target = root / "outside.pdf"
            target.write_bytes(source.read_bytes())
            source.unlink()
            source.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "must not be a symlink"):
                rag.discover(root)

    def test_front_matter_rejects_unsupported_or_duplicate_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.md"
            path.write_text(
                "---\nlanguage: de-CH\nlanguage: fr-CH\n---\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "duplicate front-matter key"):
                rag.front_matter(path)
            path.write_text(
                "---\nlanguage: de-CH\nunknown: value\n---\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "unsupported front-matter key"):
                rag.front_matter(path)

    def test_plan_needs_no_api_key_and_sync_contract_is_incremental(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_doc(root, "public", "de.md", "de-CH", "de-CH", "de.pdf")
            result = subprocess.run(
                [str(SCRIPT), "plan", str(root)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[PUBLIC] COLLECTION — Originals", result.stdout)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("/sync/diff", source)
        self.assertIn("process_in_background=false", source)
        self.assertIn("/process/status", source)
        self.assertIn("--prune", source)
        self.assertNotIn("sqlite", source.lower())

    def test_prune_knows_both_generated_lanes_even_when_one_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_doc(root, "public", "de.md", "de-CH", "de-CH", "de.pdf")
            expected = rag.expected_knowledge(root)
            self.assertEqual(
                set(expected),
                {"[PUBLIC] COLLECTION — Originals", "[PUBLIC] COLLECTION — Français"},
            )
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("set(grouped) | (set(expected) if args.prune else set())", source)

    def test_importer_is_packaged_and_document_root_is_operator_owned(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
        tmpfiles = (ROOT / "packaging/bc250-llm-server.tmpfiles").read_text(
            encoding="utf-8"
        )
        self.assertIn("models/rag/rag_import.py\t{libexec}/rag-import", manifest)
        self.assertIn('"rag-import|$LIBEXEC/rag-import"', dispatcher)
        self.assertIn("d /srv/bc250-documents 0750 root root -", tmpfiles)


if __name__ == "__main__":
    unittest.main()
