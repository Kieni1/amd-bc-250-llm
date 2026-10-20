from __future__ import annotations

import hashlib
import importlib.util
import io
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "models/rag/rag_import.py"
LIFECYCLE = ROOT / "models/rag/rag.py"

spec = importlib.util.spec_from_file_location("bc250_rag_import", SCRIPT)
assert spec and spec.loader
rag = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rag
spec.loader.exec_module(rag)

lifecycle_spec = importlib.util.spec_from_file_location("bc250_rag_lifecycle", LIFECYCLE)
assert lifecycle_spec and lifecycle_spec.loader
lifecycle = importlib.util.module_from_spec(lifecycle_spec)
sys.modules[lifecycle_spec.name] = lifecycle
_previous_rag_import = sys.modules.get("rag_import")
sys.modules["rag_import"] = rag
try:
    lifecycle_spec.loader.exec_module(lifecycle)
finally:
    if _previous_rag_import is None:
        sys.modules.pop("rag_import", None)
    else:
        sys.modules["rag_import"] = _previous_rag_import


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

    def test_front_matter_rejects_tab_indentation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.md"
            path.write_text("---\n\tlanguage: de-CH\n---\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported YAML indentation"):
                rag.front_matter(path)
            path.write_text(
                "---\nrelation:\n  \ttype: translation-pair\n---\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unsupported YAML indentation"):
                rag.front_matter(path)

    def test_knowledge_lookup_follows_pagination_and_checks_exact_name(self) -> None:
        api = rag.OpenWebUI("http://example.invalid", "token")
        pages = {
            1: {"items": [{"id": "other", "name": "Other"}], "total": 2},
            2: {"items": [{"id": "wanted", "name": "Wanted", "write_access": True}], "total": 2},
        }

        def fake_request(method, path, payload=None, headers=None):
            self.assertEqual(method, "GET")
            page = int(path.rsplit("page=", 1)[1])
            return pages[page]

        with patch.object(api, "_request", side_effect=fake_request):
            result = api.find_knowledge("Wanted")
        self.assertEqual(result["id"], "wanted")

    def test_knowledge_lookup_rejects_duplicate_exact_names_across_pages(self) -> None:
        api = rag.OpenWebUI("http://example.invalid", "token")
        pages = {
            1: {"items": [{"id": "a", "name": "Wanted"}], "total": 2},
            2: {"items": [{"id": "b", "name": "Wanted"}], "total": 2},
        }
        with (
            patch.object(
                api,
                "_request",
                side_effect=lambda _method, path, _payload=None, _headers=None: pages[
                    int(path.rsplit("page=", 1)[1])
                ],
            ),
            self.assertRaisesRegex(RuntimeError, "multiple knowledge bases"),
        ):
            api.find_knowledge("Wanted")

    def test_main_handles_invalid_sync_response_type_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stderr = io.StringIO()
            with (
                patch.object(
                    lifecycle, "run_ingest", side_effect=TypeError("invalid sync diff response")
                ),
                redirect_stderr(stderr),
            ):
                result = lifecycle.main(["--root", tmp, "ingest"])
        self.assertEqual(result, 2)
        self.assertIn("ERROR: invalid sync diff response", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_sync_token_file_must_be_private_nonempty_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp) / "owui-token"
            token_file.write_text("secret\n", encoding="utf-8")
            token_file.chmod(0o600)
            args = type("Args", (), {"token_file": str(token_file)})()
            self.assertEqual(rag.token_from(args), "secret")
            token_file.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "group/world accessible"):
                rag.token_from(args)
            token_file.chmod(0o600)
            token_file.write_text("\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "API key file is empty"):
                rag.token_from(args)
            token_file.write_text("secret\n", encoding="utf-8")
            link = Path(tmp) / "owui-link"
            link.symlink_to(token_file)
            link_args = type("Args", (), {"token_file": str(link)})()
            with self.assertRaisesRegex(ValueError, "must not be a symlink"):
                rag.token_from(link_args)
            directory = Path(tmp) / "token-dir"
            directory.mkdir()
            dir_args = type("Args", (), {"token_file": str(directory)})()
            with self.assertRaisesRegex(ValueError, "regular file"):
                rag.token_from(dir_args)

    def test_sync_endpoint_is_loopback_default_with_explicit_remote_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_doc(root, "public", "de.md", "de-CH", "de-CH", "de.pdf")
            public_docs, _ = rag.discover(root)
            for url in (
                "http://127.0.0.1:3000",
                "http://localhost:3000",
                "http://[::1]:3000",
            ):
                rag.validate_sync_endpoint(url, public_docs)
            with self.assertRaisesRegex(ValueError, "loopback-only by default"):
                rag.validate_sync_endpoint("https://owui.example.invalid", public_docs)
            rag.validate_sync_endpoint(
                "https://owui.example.invalid", public_docs, allow_remote=True
            )

            self.make_doc(
                root,
                "confidential",
                "secret.md",
                "de-CH",
                "de-CH",
                "secret.pdf",
            )
            mixed_docs, _ = rag.discover(root)
            with self.assertRaisesRegex(ValueError, "confidential documents"):
                rag.validate_sync_endpoint(
                    "https://owui.example.invalid", mixed_docs, allow_remote=True
                )
            rag.validate_sync_endpoint(
                "https://owui.example.invalid",
                mixed_docs,
                allow_remote=True,
                allow_confidential_remote=True,
            )

            empty_root = Path(tmp) / "empty-confidential"
            (empty_root / "confidential" / "EMPTY" / "active").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "confidential documents"):
                rag.validate_sync_endpoint(
                    "https://owui.example.invalid",
                    [],
                    root=empty_root,
                    allow_remote=True,
                )

    def test_sync_transactions_preserve_replacement_before_cleanup_and_prune_boundary(self) -> None:
        class FakeApi:
            def __init__(self, diff_result, *, fail_upload=False, fail_cleanup=False):
                self.diff_result = diff_result
                self.fail_upload = fail_upload
                self.fail_cleanup = fail_cleanup
                self.calls = []

            def knowledge(self, name, description):
                self.calls.append(("knowledge", name))
                return {"id": "kb"}

            def find_knowledge(self, name):
                self.calls.append(("find", name))
                return {"id": "kb"}

            def diff(self, knowledge_id, docs):
                self.calls.append(("diff", knowledge_id, tuple(d.path.name for d in docs)))
                return self.diff_result

            def upload(self, knowledge_id, doc):
                self.calls.append(("upload", doc.path.name))
                if self.fail_upload:
                    raise RuntimeError("upload failed")

            def cleanup(self, knowledge_id, file_ids):
                self.calls.append(("cleanup", tuple(file_ids)))
                if self.fail_cleanup:
                    raise RuntimeError("cleanup failed")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.make_doc(root, "public", "de.md", "de-CH", "de-CH", "de.pdf")
            docs, warnings = rag.discover(root)
            self.assertEqual(warnings, [])
            def run(fake, *, prune=False):
                args = type(
                    "Args",
                    (),
                    {
                        "url": "http://127.0.0.1:3000",
                        "token_file": None,
                        "timeout": 5,
                        "prune": prune,
                        "allow_remote": False,
                        "allow_confidential_remote": False,
                    },
                )()
                with (
                    patch.object(rag, "OpenWebUI", return_value=fake),
                    patch.object(rag, "token_from", return_value="secret"),
                    redirect_stdout(io.StringIO()),
                ):
                    rag.sync(root, docs, [], args)

            added = FakeApi({"added": [{"filename": path.name}], "modified": [], "deleted": []})
            run(added)
            self.assertEqual([c[0] for c in added.calls if c[0] in {"upload", "cleanup"}], ["upload"])

            modified = FakeApi({"added": [], "modified": [{"filename": path.name, "stale_file_id": "old"}], "deleted": []})
            run(modified)
            self.assertEqual([c[0] for c in modified.calls if c[0] in {"upload", "cleanup"}], ["upload", "cleanup"])
            self.assertIn(("cleanup", ("old",)), modified.calls)

            failed_upload = FakeApi({"added": [], "modified": [{"filename": path.name, "stale_file_id": "old"}], "deleted": []}, fail_upload=True)
            with self.assertRaisesRegex(RuntimeError, "upload failed"):
                run(failed_upload)
            self.assertFalse(any(c[0] == "cleanup" for c in failed_upload.calls))

            stale = {"added": [], "modified": [], "deleted": [{"file_id": "gone"}]}
            no_prune = FakeApi(stale)
            run(no_prune, prune=False)
            self.assertFalse(any(c[0] == "cleanup" for c in no_prune.calls))

            prune = FakeApi(stale)
            run(prune, prune=True)
            self.assertIn(("cleanup", ("gone",)), prune.calls)

            cleanup_failure = FakeApi({"added": [], "modified": [{"filename": path.name, "stale_file_id": "old"}], "deleted": []}, fail_cleanup=True)
            with self.assertRaisesRegex(RuntimeError, "replacement upload succeeded"):
                run(cleanup_failure)
            events = [c[0] for c in cleanup_failure.calls if c[0] in {"upload", "cleanup"}]
            self.assertEqual(events, ["upload", "cleanup"])

    def test_empty_local_lane_prune_converges_remote_lane(self) -> None:
        class FakeApi:
            def __init__(self):
                self.cleanups = []
            def find_knowledge(self, _name):
                return {"id": "kb"}
            def diff(self, _knowledge_id, _docs):
                return {"added": [], "modified": [], "deleted": [{"file_id": "stale"}]}
            def cleanup(self, _knowledge_id, file_ids):
                self.cleanups.append(tuple(file_ids))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "public" / "COLLECTION" / "active").mkdir(parents=True)
            args = type(
                "Args",
                (),
                {
                    "url": "http://127.0.0.1:3000",
                    "token_file": None,
                    "timeout": 5,
                    "prune": True,
                    "allow_remote": False,
                    "allow_confidential_remote": False,
                },
            )()
            fake = FakeApi()
            with (
                patch.object(rag, "OpenWebUI", return_value=fake),
                patch.object(rag, "token_from", return_value="secret"),
                redirect_stdout(io.StringIO()),
            ):
                rag.sync(root, [], [], args)
            self.assertEqual(fake.cleanups, [("stale",), ("stale",)])

    def test_plan_needs_no_api_key_and_sync_contract_is_incremental(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_doc(root, "public", "de.md", "de-CH", "de-CH", "de.pdf")
            docs, warnings = rag.discover(root)
            output = io.StringIO()
            with redirect_stdout(output):
                rag.print_plan(root, docs, warnings)
            self.assertIn("[PUBLIC] COLLECTION — Originals", output.getvalue())
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("/sync/diff", source)
        self.assertIn("process_in_background=false", source)
        self.assertIn("/process/status", source)
        self.assertIn("--prune", source)
        self.assertNotIn("sqlite", source.lower())
        self.assertNotIn("argparse.ArgumentParser", source)
        self.assertNotIn('prog="bc250 rag ingest"', source)

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


    def test_lifecycle_init_creates_three_inbox_lanes_and_dry_run_is_nonmutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = subprocess.run(
                [sys.executable, str(LIFECYCLE), "--root", str(root), "init", "public", "COLLECTION"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RAG collection ready", result.stdout)
            self.assertIn("(created)", result.stdout)
            again = subprocess.run(
                [sys.executable, str(LIFECYCLE), "--root", str(root), "init", "public", "COLLECTION"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("already present / converged", again.stdout)
            base = root / "public" / "COLLECTION"
            for name in ("sources", "working", "active", "superseded"):
                self.assertTrue((base / name).is_dir())
            for lane in ("german", "french", "bilingual"):
                self.assertTrue((base / "inbox" / lane).is_dir())
            source = base / "inbox" / "german" / "example.pdf"
            source.write_bytes(b"not parsed during dry run")
            dry = subprocess.run(
                [sys.executable, str(LIFECYCLE), "--root", str(root), "prepare-batch", "public", "COLLECTION", "--dry-run"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("german", dry.stdout)
            self.assertIn("example.pdf", dry.stdout)
            self.assertTrue(source.exists())
            remote = subprocess.run(
                [sys.executable, str(LIFECYCLE), "--root", str(root), "prepare-batch", "public", "COLLECTION", "--agent-url", "https://example.invalid", "--dry-run"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(remote.returncode, 2)
            self.assertIn("loopback-only agent URL", remote.stderr)
            missing = subprocess.run(
                [sys.executable, str(LIFECYCLE), "--root", str(root), "status", "public", "MISSING"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(missing.returncode, 0, missing.stderr)
            self.assertIn("RAG collection not found: public/MISSING", missing.stdout)
            invalid = subprocess.run(
                [sys.executable, str(LIFECYCLE), "--root", str(root), "init", "public", "bad/name"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(invalid.returncode, 2)
            self.assertIn("'bad/name'", invalid.stderr)
            private = subprocess.run(
                [sys.executable, str(LIFECYCLE), "--root", str(root), "init", "confidential", "PRIVATE"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(private.returncode, 0, private.stderr)
            self.assertEqual((root / "confidential" / "PRIVATE").stat().st_mode & 0o777, 0o700)

    def test_lifecycle_activation_requires_reviewed_metadata_and_supersedes_prior_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "public" / "COLLECTION"
            for name in ("sources", "working", "active", "superseded"):
                (base / name).mkdir(parents=True, exist_ok=True)
            source = base / "sources" / "reglement.pdf"
            source.write_bytes(b"authoritative source")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            template = """---\ndocument_id: \"{document_id}\"\ndocument_family: \"family\"\ntitle: \"{title}\"\nlanguage: \"de-CH\"\nauthority_role: \"authoritative\"\neffective_from: \"{date}\"\nstatus: \"active\"\nreview_required: false\nsource_file: \"reglement.pdf\"\nsource_sha256: \"{digest}\"\n---\n\n# {title}\n"""
            old = base / "active" / "family_de-CH_2025-01-01.md"
            old.write_text(template.format(document_id="family_de-CH_2025-01-01", title="Old", date="2025-01-01", digest=digest), encoding="utf-8")
            new = base / "working" / "family_de-CH_2026-01-01.md"
            new.write_text(template.format(document_id="family_de-CH_2026-01-01", title="New", date="2026-01-01", digest=digest), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(LIFECYCLE), "--root", str(root), "activate", "public", "COLLECTION", new.name, "--yes"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue((base / "active" / new.name).is_file())
            self.assertFalse(old.exists())
            self.assertTrue(any((base / "superseded").glob("family_de-CH_2025-01-01*.md")))
            self.assertTrue(source.exists())
            pending = base / "working" / "pending.md"
            pending.write_text(
                template.format(document_id="pending", title="Pending", date="2027-01-01", digest=digest).replace(
                    "review_required: false", "review_required: true"
                ),
                encoding="utf-8",
            )
            status = subprocess.run(
                [sys.executable, str(LIFECYCLE), "--root", str(root), "status", "public", "COLLECTION"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("working awaiting review: 1", status.stdout)

    def test_lifecycle_agent_output_integrity_and_deferral_taxonomy(self) -> None:
        lifecycle_source = LIFECYCLE.read_text(encoding="utf-8")
        self.assertIn('url + "/api/chat"', lifecycle_source)
        self.assertIn('"think": True', lifecycle_source)
        self.assertNotIn('url + "/api/generate"', lifecycle_source)
        prompt = lifecycle.normalize_prompt("FR-MARKER-8520", "fr-CH", False)
        self.assertIn("Do not remove unique codes, identifiers", prompt)
        clean = {
            "done": True,
            "done_reason": "stop",
            "message": {
                "thinking": "FR-MARKER-8520 appears in the source but I might omit it",
                "content": "# Titre\n\nTexte final sans le code.\n",
            },
        }
        final = lifecycle.final_agent_content(clean)
        self.assertEqual(final, "# Titre\n\nTexte final sans le code.\n")
        self.assertIn("REVIEW", lifecycle.fidelity_note("FR-MARKER-8520", final, False))
        kept = lifecycle.final_agent_content(
            {
                "done": True,
                "done_reason": "stop",
                "message": {"thinking": "private reasoning", "content": "# Titre\n\nFR-MARKER-8520\n"},
            }
        )
        self.assertIn("PASS", lifecycle.fidelity_note("FR-MARKER-8520", kept, False))
        for response in (
            {"done": True, "done_reason": "stop", "message": {"content": "# T\n</think>\nBody"}},
            {"done": True, "done_reason": "length", "message": {"content": "# T\nBody"}},
            {"done": True, "done_reason": "stop", "message": {"content": ""}},
            {"done": True, "done_reason": "stop", "message": {"content": "```markdown\n# T\n```"}},
        ):
            with self.assertRaises(ValueError):
                lifecycle.final_agent_content(response)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            source = base / "sources" / "source.pdf"
            source.write_bytes(b"source")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            contaminated = base / "working" / "bad.md"
            contaminated.write_text(
                "---\n"
                'document_id: "bad"\n'
                'document_family: "bad"\n'
                'title: "Bad"\n'
                'language: "de-CH"\n'
                'authority_role: "authoritative"\n'
                'review_required: true\n'
                'source_file: "source.pdf"\n'
                f'source_sha256: "{digest}"\n'
                "---\n\n# Bad\n\n<think>leaked</think>\n",
                encoding="utf-8",
            )
            validation_output = io.StringIO()
            with redirect_stdout(validation_output):
                errors, _warnings = lifecycle.validate_collection(base, include_working=True)
            self.assertEqual(errors, 1)
            self.assertIn("native reasoning markers", validation_output.getvalue())

            inbox = base / "inbox" / "german" / "scan.pdf"
            inbox.write_bytes(b"scan")
            args = type("Args", (), {
                "root": root, "scope": "public", "collection": "COLLECTION",
                "agent_url": "http://127.0.0.1:11436", "model": "agentic-ornith15-9b-ornith-q5-k-m",
                "max_chars": 50000, "dry_run": False,
            })()
            out = io.StringIO()
            err = io.StringIO()
            with patch.object(lifecycle, "enter_agent_if_needed", return_value=False), \
                 patch.object(lifecycle, "agent_models", return_value={"agentic-ornith15-9b-ornith-q5-k-m"}), \
                 patch.object(lifecycle, "prepare_one", side_effect=lifecycle.DeferredPreparation("OCR required", "little/no selectable text")), \
                 redirect_stdout(out), redirect_stderr(err):
                lifecycle.cmd_prepare(args)
            self.assertIn("DEFERRED — OCR required: scan.pdf", err.getvalue())
            self.assertIn("deferred/manual:  1", out.getvalue())
            self.assertIn("failed:           0", out.getvalue())

    def test_importer_is_packaged_and_document_root_is_operator_owned(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
        tmpfiles = (ROOT / "packaging/bc250-llm-server.tmpfiles").read_text(
            encoding="utf-8"
        )
        self.assertIn("models/rag/rag_import.py\t{libexec}/rag_import.py", manifest)
        self.assertIn("models/rag/rag.py\t{libexec}/rag", manifest)
        self.assertIn('"rag|$LIBEXEC/rag"', dispatcher)
        self.assertIn("d /srv/bc250-documents 0750 root root -", tmpfiles)


if __name__ == "__main__":
    unittest.main()
