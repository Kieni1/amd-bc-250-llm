from __future__ import annotations

import hashlib
import importlib.util
import io
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "cmd/documents/importer.py"
LIFECYCLE = ROOT / "cmd/documents/lifecycle.py"

spec = importlib.util.spec_from_file_location("bc250_document_importer", SCRIPT)
assert spec and spec.loader
rag = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rag
spec.loader.exec_module(rag)

lifecycle_spec = importlib.util.spec_from_file_location("bc250_document_lifecycle", LIFECYCLE)
assert lifecycle_spec and lifecycle_spec.loader
lifecycle = importlib.util.module_from_spec(lifecycle_spec)
sys.modules[lifecycle_spec.name] = lifecycle
_previous_importer = sys.modules.get("importer")
sys.modules["importer"] = rag
try:
    lifecycle_spec.loader.exec_module(lifecycle)
finally:
    if _previous_importer is None:
        sys.modules.pop("importer", None)
    else:
        sys.modules["importer"] = _previous_importer


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
        *,
        family: str = "family",
        translation_of: str = "",
    ) -> Path:
        base = root / scope / "COLLECTION"
        active = base / "active"
        sources = base / "sources"
        active.mkdir(parents=True, exist_ok=True)
        sources.mkdir(parents=True, exist_ok=True)
        source = sources / source_name
        source.write_bytes((name + " source").encode())
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        role = authority or ("authoritative" if language.lower().startswith("de") else "translation")
        document_id = f"{family}_{language}"
        revision_id = f"{document_id}_{digest[:16]}"
        translation_line = f'translation_of: "{translation_of}"\n' if translation_of else ""
        doc = active / name
        doc.write_text(
            "---\n"
            f'document_id: "{document_id}"\n'
            f'revision_id: "{revision_id}"\n'
            f'document_family: "{family}"\n'
            f'language: "{language}"\n'
            f'authority_role: "{role}"\n'
            f"{translation_line}"
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
            de = self.make_doc(root, "public", "de.md", "de-CH", "de-CH", "de.pdf")
            de_revision = rag.revision_identity(rag.front_matter(de))
            self.make_doc(
                root, "public", "fr.md", "fr-CH", "de-CH", "fr.pdf",
                translation_of=de_revision,
            )
            docs, warnings = rag.discover(root)
            self.assertEqual(warnings, [])
            self.assertEqual({doc.lane for doc in docs}, {"original", "translation"})
            self.assertEqual(
                {doc.kb_name for doc in docs},
                {"[PUBLIC] COLLECTION — Originals", "[PUBLIC] COLLECTION — Français"},
            )

    def test_non_german_authoritative_document_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_doc(
                root, "public", "en.md", "en", "en", "en.pdf", authority="authoritative"
            )
            with self.assertRaisesRegex(
                ValueError, "authoritative managed-corpus documents must be German"
            ):
                rag.discover(root)


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
            with self.assertRaisesRegex(ValueError, "confidential-scope knowledge state"):
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
            with self.assertRaisesRegex(ValueError, "confidential-scope knowledge state"):
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
        self.assertNotIn('prog="bc250 document ingest"', source)

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
            self.assertIn("Document collection ready", result.stdout)
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
            self.assertEqual(missing.returncode, 2, missing.stdout + missing.stderr)
            self.assertIn("Document collection not found: public/MISSING", missing.stderr)
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
            self.assertIn("Needs review:         1", status.stdout)

    def test_activation_preflight_failure_preserves_active_and_working_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            source = base / "sources" / "reglement.pdf"
            source.write_bytes(b"authoritative source")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            template = (
                "---\n"
                'document_id: "family_de-CH"\n'
                'revision_id: "{revision}"\n'
                'document_family: "family"\n'
                'title: "{title}"\n'
                'language: "de-CH"\n'
                'authority_role: "authoritative"\n'
                'effective_from: "{date}"\n'
                'status: "active"\n'
                'review_required: false\n'
                'source_file: "reglement.pdf"\n'
                'source_sha256: "{digest}"\n'
                "---\n\n# {title}\n"
            )
            old = base / "active" / "family_de-CH_2025-01-01.md"
            old.write_text(
                template.format(
                    revision="family_de-CH_old",
                    title="Old",
                    date="2025-01-01",
                    digest=digest,
                ),
                encoding="utf-8",
            )
            replacement = base / "working" / "family_de-CH_2026-01-01.md"
            replacement.write_text(
                template.format(
                    revision="family_de-CH_new",
                    title="New",
                    date="2026-01-01",
                    digest="0" * 64,
                ),
                encoding="utf-8",
            )
            old_bytes = old.read_bytes()
            replacement_bytes = replacement.read_bytes()
            args = type(
                "Args",
                (),
                {
                    "root": root,
                    "scope": "public",
                    "collection": "COLLECTION",
                    "files": [replacement.name],
                    "all_ready": False,
                    "yes": True,
                },
            )()
            with self.assertRaisesRegex(RuntimeError, "no files were changed"):
                lifecycle.cmd_activate(args)
            self.assertEqual(old.read_bytes(), old_bytes)
            self.assertEqual(replacement.read_bytes(), replacement_bytes)
            self.assertEqual(list((base / "superseded").iterdir()), [])

    def test_activate_all_ready_rejects_duplicate_logical_target_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            for index in (1, 2):
                source = base / "sources" / f"source-{index}.pdf"
                source.write_bytes(f"source {index}".encode())
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                draft = base / "working" / f"candidate-{index}.md"
                draft.write_text(
                    "---\n"
                    'document_id: "family_de-CH"\n'
                    f'revision_id: "family_de-CH_{index}"\n'
                    'document_family: "family"\n'
                    f'title: "Candidate {index}"\n'
                    'language: "de-CH"\n'
                    'authority_role: "authoritative"\n'
                    'effective_from: "2026-01-01"\n'
                    'review_required: false\n'
                    f'source_file: "source-{index}.pdf"\n'
                    f'source_sha256: "{digest}"\n'
                    "---\n\n# Candidate\n",
                    encoding="utf-8",
                )
            args = type(
                "Args",
                (),
                {
                    "root": root,
                    "scope": "public",
                    "collection": "COLLECTION",
                    "files": [],
                    "all_ready": True,
                    "yes": True,
                },
            )()
            with self.assertRaisesRegex(ValueError, "activation is ambiguous"):
                lifecycle.cmd_activate(args)
            self.assertEqual(len(list((base / "working").glob("*.md"))), 2)
            self.assertEqual(list((base / "active").glob("*.md")), [])
            self.assertEqual(list((base / "superseded").iterdir()), [])

    def test_activation_runtime_failure_rolls_back_prior_moves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            source = base / "sources" / "reglement.pdf"
            source.write_bytes(b"authoritative source")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            template = (
                "---\n"
                'document_id: "family_de-CH"\n'
                'revision_id: "{revision}"\n'
                'document_family: "family"\n'
                'title: "{title}"\n'
                'language: "de-CH"\n'
                'authority_role: "authoritative"\n'
                'effective_from: "{date}"\n'
                'review_required: false\n'
                'source_file: "reglement.pdf"\n'
                f'source_sha256: "{digest}"\n'
                "---\n\n# {title}\n"
            )
            old = base / "active" / "old.md"
            new = base / "working" / "new.md"
            old.write_text(
                template.format(revision="old-revision", title="Old", date="2025-01-01"),
                encoding="utf-8",
            )
            new.write_text(
                template.format(revision="new-revision", title="New", date="2026-01-01"),
                encoding="utf-8",
            )
            original_move = lifecycle.transaction_move

            def fail_on_second_move(source_path, destination_path, journal):
                if journal:
                    raise OSError("simulated activation move failure")
                return original_move(source_path, destination_path, journal)

            args = type(
                "Args",
                (),
                {
                    "root": root,
                    "scope": "public",
                    "collection": "COLLECTION",
                    "files": [new.name],
                    "all_ready": False,
                    "yes": True,
                },
            )()
            with patch.object(lifecycle, "transaction_move", side_effect=fail_on_second_move), \
                 self.assertRaisesRegex(RuntimeError, "all filesystem moves were rolled back"):
                lifecycle.cmd_activate(args)
            self.assertTrue(old.is_file())
            self.assertTrue(new.is_file())
            self.assertEqual(list((base / "superseded").iterdir()), [])

    def test_french_authority_policy_is_shared_by_validation_and_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            source = base / "sources" / "fr.pdf"
            source.write_bytes(b"french source")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            bad = base / "active" / "fr.md"
            bad.write_text(
                "---\n"
                'document_id: "family_fr-CH"\n'
                'revision_id: "family_fr-CH_revision"\n'
                'document_family: "family"\n'
                'title: "FR"\n'
                'language: "fr-CH"\n'
                'authority_role: "authoritative"\n'
                'review_required: false\n'
                'source_file: "fr.pdf"\n'
                f'source_sha256: "{digest}"\n'
                "---\n\n# FR\n",
                encoding="utf-8",
            )
            out = io.StringIO()
            with redirect_stdout(out):
                errors, _warnings = lifecycle.validate_collection(base)
            self.assertEqual(errors, 1)
            self.assertIn("authoritative managed-corpus documents must be German", out.getvalue())
            with self.assertRaisesRegex(
                ValueError, "authoritative managed-corpus documents must be German"
            ):
                rag.discover(root)

    def test_activation_rejects_legacy_translation_filename_that_would_retarget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            de_source = base / "sources" / "de.pdf"
            fr_source = base / "sources" / "fr.pdf"
            de_source.write_bytes(b"de source")
            fr_source.write_bytes(b"fr source")
            de_digest = hashlib.sha256(de_source.read_bytes()).hexdigest()
            fr_digest = hashlib.sha256(fr_source.read_bytes()).hexdigest()

            old_de = base / "active" / "family_de-CH.md"
            old_de.write_text(
                "---\n"
                'document_id: "family_de-CH"\n'
                'revision_id: "de-old"\n'
                'document_family: "family"\n'
                'title: "DE old"\n'
                'language: "de-CH"\n'
                'authority_role: "authoritative"\n'
                'review_required: false\n'
                'source_file: "de.pdf"\n'
                f'source_sha256: "{de_digest}"\n'
                "---\n\n# DE old\n",
                encoding="utf-8",
            )
            fr = base / "active" / "family_fr-CH.md"
            fr.write_text(
                "---\n"
                'document_id: "family_fr-CH"\n'
                'revision_id: "fr-current"\n'
                'document_family: "family"\n'
                'title: "FR"\n'
                'language: "fr-CH"\n'
                'authority_role: "translation"\n'
                'translation_of: "family_de-CH.md"\n'
                'review_required: false\n'
                'source_file: "fr.pdf"\n'
                f'source_sha256: "{fr_digest}"\n'
                "---\n\n# FR\n",
                encoding="utf-8",
            )
            replacement = base / "working" / "family_de-CH.md"
            replacement.write_text(
                "---\n"
                'document_id: "family_de-CH"\n'
                'revision_id: "de-new"\n'
                'document_family: "family"\n'
                'title: "DE new"\n'
                'language: "de-CH"\n'
                'authority_role: "authoritative"\n'
                'review_required: false\n'
                'source_file: "de.pdf"\n'
                f'source_sha256: "{de_digest}"\n'
                "---\n\n# DE new\n",
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "root": root,
                    "scope": "public",
                    "collection": "COLLECTION",
                    "files": [replacement.name],
                    "all_ready": False,
                    "yes": True,
                },
            )()
            with self.assertRaisesRegex(RuntimeError, "no files were changed"):
                lifecycle.cmd_activate(args)
            self.assertTrue(old_de.is_file())
            self.assertTrue(fr.is_file())
            self.assertTrue(replacement.is_file())

    def test_supersede_rejects_removing_german_revision_with_active_translation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            de_source = base / "sources" / "de.pdf"
            fr_source = base / "sources" / "fr.pdf"
            de_source.write_bytes(b"de source")
            fr_source.write_bytes(b"fr source")
            de_digest = hashlib.sha256(de_source.read_bytes()).hexdigest()
            fr_digest = hashlib.sha256(fr_source.read_bytes()).hexdigest()
            de_revision = "family_de-CH_sha256_" + de_digest
            de = base / "active" / "de.md"
            de.write_text(
                "---\n"
                'document_id: "family_de-CH"\n'
                f'revision_id: "{de_revision}"\n'
                'document_family: "family"\n'
                'title: "DE"\n'
                'language: "de-CH"\n'
                'authority_role: "authoritative"\n'
                'review_required: false\n'
                'source_file: "de.pdf"\n'
                f'source_sha256: "{de_digest}"\n'
                "---\n\n# DE\n",
                encoding="utf-8",
            )
            fr = base / "active" / "fr.md"
            fr.write_text(
                "---\n"
                'document_id: "family_fr-CH"\n'
                'revision_id: "family_fr-CH_revision"\n'
                'document_family: "family"\n'
                'title: "FR"\n'
                'language: "fr-CH"\n'
                'authority_role: "translation"\n'
                f'translation_of: "{de_revision}"\n'
                'review_required: false\n'
                'source_file: "fr.pdf"\n'
                f'source_sha256: "{fr_digest}"\n'
                "---\n\n# FR\n",
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "root": root,
                    "scope": "public",
                    "collection": "COLLECTION",
                    "file": de.name,
                },
            )()
            with self.assertRaisesRegex(RuntimeError, "no files were changed"):
                lifecycle.cmd_supersede(args)
            self.assertTrue(de.is_file())
            self.assertTrue(fr.is_file())
            self.assertEqual(list((base / "superseded").iterdir()), [])

    def test_prepare_batch_failure_and_restore_failure_are_nonzero_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            inbox = base / "inbox" / "german" / "scan.pdf"
            inbox.write_bytes(b"scan")
            argv = [
                "--root", str(root), "prepare-batch", "public", "COLLECTION"
            ]
            with patch.object(lifecycle, "enter_agent_if_needed", return_value=False), \
                 patch.object(lifecycle, "agent_models", return_value={lifecycle.DEFAULT_AGENT_MODEL}), \
                 patch.object(lifecycle, "prepare_one", side_effect=ValueError("broken input")), \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(lifecycle.main(argv), 2)

            with patch.object(lifecycle, "enter_agent_if_needed", return_value=True), \
                 patch.object(lifecycle, "agent_models", return_value={lifecycle.DEFAULT_AGENT_MODEL}), \
                 patch.object(lifecycle, "prepare_one", return_value=[]), \
                 patch.object(lifecycle, "restore_normal_if_needed", return_value="restore failed"), \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(lifecycle.main(argv), 2)

    def test_agent_entry_readiness_failure_restores_normal_topology(self) -> None:
        entered = subprocess.CompletedProcess(["bc250"], 0)
        with patch.object(lifecycle, "agent_ready", return_value=False), \
             patch.object(lifecycle.os, "geteuid", return_value=0), \
             patch.object(lifecycle.shutil, "which", return_value="/usr/bin/bc250"), \
             patch.object(lifecycle.subprocess, "run", return_value=entered), \
             patch.object(lifecycle, "restore_normal_if_needed", return_value=None) as restore, \
             self.assertRaisesRegex(ValueError, "did not become ready"):
            lifecycle.enter_agent_if_needed(lifecycle.DEFAULT_AGENT_URL)
        restore.assert_called_once_with(True)

    def test_prepare_batch_keyboard_interrupt_restores_normal_topology(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            (base / "inbox" / "german" / "scan.pdf").write_bytes(b"scan")
            args = type(
                "Args",
                (),
                {
                    "root": root,
                    "scope": "public",
                    "collection": "COLLECTION",
                    "agent_url": lifecycle.DEFAULT_AGENT_URL,
                    "model": lifecycle.DEFAULT_AGENT_MODEL,
                    "max_chars": lifecycle.DEFAULT_MAX_CHARS,
                    "dry_run": False,
                },
            )()
            with patch.object(lifecycle, "enter_agent_if_needed", return_value=True), \
                 patch.object(lifecycle, "agent_models", return_value={lifecycle.DEFAULT_AGENT_MODEL}), \
                 patch.object(lifecycle, "prepare_one", side_effect=KeyboardInterrupt), \
                 patch.object(lifecycle, "restore_normal_if_needed", return_value=None) as restore, \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                 self.assertRaises(KeyboardInterrupt):
                lifecycle.cmd_prepare(args)
            restore.assert_called_once_with(True)

    def test_existing_working_draft_is_never_overwritten_by_reprepare(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            source = base / "sources" / "reglement.pdf"
            source.write_bytes(b"source")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            draft, created = lifecycle.write_draft(
                base,
                source,
                digest,
                "# Original\n\nBody\n",
                "de-CH",
                "authoritative",
                bilingual=False,
            )
            self.assertTrue(created)
            reviewed = draft.read_text(encoding="utf-8") + "\nHUMAN EDIT\n"
            draft.write_text(reviewed, encoding="utf-8")
            same, created_again = lifecycle.write_draft(
                base,
                source,
                digest,
                "# Regenerated\n\nDifferent body\n",
                "de-CH",
                "authoritative",
                bilingual=False,
            )
            self.assertEqual(same, draft)
            self.assertFalse(created_again)
            self.assertEqual(draft.read_text(encoding="utf-8"), reviewed)
            meta = lifecycle.importer.front_matter(draft)
            self.assertEqual(meta["document_id"], "reglement_de-CH")
            self.assertEqual(
                meta["revision_id"], f"reglement_de-CH_sha256_{digest}"
            )

    def test_lifecycle_agent_output_integrity_and_deferral_taxonomy(self) -> None:
        lifecycle_source = LIFECYCLE.read_text(encoding="utf-8")
        self.assertIn('url + "/api/chat"', lifecycle_source)
        self.assertIn('"think": think', lifecycle_source)
        self.assertIn('retrying once without extended thinking', lifecycle_source)
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
        with self.assertRaises(lifecycle.AgentGenerationLimit):
            lifecycle.final_agent_content(
                {"done": True, "done_reason": "length", "message": {"content": "# T\nBody"}}
            )
        for response in (
            {"done": True, "done_reason": "stop", "message": {"content": "# T\n</think>\nBody"}},
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
                 redirect_stdout(out), redirect_stderr(err), \
                 self.assertRaisesRegex(RuntimeError, "batch preparation incomplete"):
                lifecycle.cmd_prepare(args)
            self.assertIn("DEFERRED — OCR required: scan.pdf", err.getvalue())
            self.assertIn("deferred/manual:  1", out.getvalue())
            self.assertIn("failed:           0", out.getvalue())

    def test_document_topology_helpers_traverse_canonical_advanced_dispatcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bindir = root / "bin"
            libexec = root / "libexec"
            bindir.mkdir()
            libexec.mkdir()
            bc250 = bindir / "bc250"
            bc250.write_text((ROOT / "packaging/bc250").read_text(encoding="utf-8"), encoding="utf-8")
            bc250.chmod(0o755)
            advanced = libexec / "advanced"
            advanced.write_text((ROOT / "packaging/advanced").read_text(encoding="utf-8"), encoding="utf-8")
            advanced.chmod(0o755)
            log = root / "agent-mode.log"
            mode = libexec / "agent-mode.sh"
            mode.write_text(
                '#!/usr/bin/env bash\nprintf "%s\n" "$*" >> "$BC250_AGENT_MODE_LOG"\n',
                encoding="utf-8",
            )
            mode.chmod(0o755)
            env = {
                "PATH": f"{bindir}:{__import__('os').environ.get('PATH', '')}",
                "BC250_LIBEXEC": str(libexec),
                "BC250_AGENT_MODE_LOG": str(log),
            }
            with patch.dict(__import__('os').environ, env, clear=False), \
                 patch.object(lifecycle.os, "geteuid", return_value=0), \
                 patch.object(lifecycle, "agent_ready", side_effect=[False, True]):
                self.assertTrue(lifecycle.enter_agent_if_needed("http://127.0.0.1:11436"))
                self.assertIsNone(lifecycle.restore_normal_if_needed(True))
            self.assertEqual(log.read_text(encoding="utf-8").splitlines(), ["enter", "normal"])

    def test_importer_is_packaged_and_document_root_is_operator_owned(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
        tmpfiles = (ROOT / "packaging/bc250-llm-server.tmpfiles").read_text(
            encoding="utf-8"
        )
        self.assertIn("cmd/documents/importer.py\t{libexec}/documents/importer.py", manifest)
        self.assertIn("cmd/documents/lifecycle.py\t{libexec}/documents/lifecycle.py", manifest)
        self.assertIn('"document|$LIBEXEC/documents/lifecycle.py"', dispatcher)
        self.assertIn("d /srv/bc250-documents 0750 root root -", tmpfiles)


    def test_batch2_front_matter_round_trip_preserves_escaped_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roundtrip.md"
            meta = {
                "document_id": "family_de-CH",
                "revision_id": "family_de-CH_revision",
                "document_family": "family",
                "title": ' A "quoted" title \\ path: #tag ',
                "organisation": "Biel/Bienne – Département",
                "language": "de-CH",
                "authority_role": "authoritative",
                "review_required": True,
                "source_file": "source.pdf",
                "source_sha256": "a" * 64,
                "bc250_fidelity_status": "not-scored",
                "bc250_fidelity_note": "line one\\line two: # literal",
            }
            path.write_text(
                lifecycle.render_markdown(meta, "# Body\n"), encoding="utf-8"
            )
            parsed = rag.front_matter(path)
            for key, value in meta.items():
                if key == "review_required":
                    self.assertEqual(parsed[key], "true")
                else:
                    self.assertEqual(parsed[key], value)

    def test_batch2_metadata_rejects_impossible_dates_and_bad_translation_relation(self) -> None:
        base = {
            "document_id": "family_de-CH",
            "revision_id": "family_de-CH_revision",
            "document_family": "family",
            "language": "de-CH",
            "authority_role": "authoritative",
        }
        for field in ("effective_from", "approved_on"):
            bad = dict(base)
            bad[field] = "2026-99-31"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                rag.validate_document_metadata(bad)

        translation = dict(base)
        translation.update(
            {
                "document_id": "family_fr-CH",
                "revision_id": "family_fr-CH_revision",
                "language": "fr-CH",
                "authority_role": "translation",
                "translation_of": "family_de-CH_revision",
                "relation": {"type": "translation-pair", "source_language": "en"},
            }
        )
        with self.assertRaisesRegex(ValueError, "source_language must be German"):
            rag.validate_document_metadata(translation, active=True)

    def test_batch2_openwebui_sync_schema_validation_is_fail_closed(self) -> None:
        invalid = (
            ({"added": {}}, "must be a list"),
            ({"added": [{}]}, "missing a valid filename"),
            ({"modified": [{"filename": "doc.md"}]}, "missing a valid stale_file_id"),
            ({"deleted": [{}]}, "missing a valid file_id"),
            ({"unmodified_count": -1}, "must not be negative"),
        )
        for result, message in invalid:
            with self.subTest(result=result), self.assertRaisesRegex(
                (RuntimeError, TypeError), message
            ):
                rag.validate_diff_result(result)

        api = rag.OpenWebUI("http://example.invalid", "token")
        with patch.object(api, "_request", return_value=[]), self.assertRaisesRegex(
            TypeError, "search response must be an object"
        ):
            api.find_knowledge("Wanted")
        with patch.object(
            api,
            "_request",
            return_value={
                "items": [{"name": "Wanted", "write_access": True}],
                "total": 1,
            },
        ), self.assertRaisesRegex(RuntimeError, "missing a valid id"):
            api.find_knowledge("Wanted")

    def test_batch2_inbox_and_working_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            outside_pdf = root / "outside.pdf"
            outside_pdf.write_bytes(b"outside")
            inbox_link = base / "inbox" / "german" / "linked.pdf"
            inbox_link.symlink_to(outside_pdf)
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = lifecycle.main(
                    [
                        "--root",
                        str(root),
                        "prepare-batch",
                        "public",
                        "COLLECTION",
                        "--dry-run",
                    ]
                )
            self.assertEqual(result, 2)
            self.assertIn("inbox entries must not be symlinks", stderr.getvalue())

            inbox_link.unlink()
            outside_md = root / "outside.md"
            outside_md.write_text("---\n---\n", encoding="utf-8")
            working_link = base / "working" / "linked.md"
            working_link.symlink_to(outside_md)
            with self.assertRaisesRegex(ValueError, "Markdown must not be a symlink"):
                lifecycle.docs_in(base / "working")

    def test_batch2_fidelity_metadata_persists_and_review_status_requires_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            source = base / "sources" / "reglement.pdf"
            source.write_bytes(b"source")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            draft, created = lifecycle.write_draft(
                base,
                source,
                digest,
                "# Reglement\n\nBody\n",
                "de-CH",
                "authoritative",
                bilingual=False,
                fidelity_status="review",
                fidelity_note_text=(
                    "critical-token coverage REVIEW (0/1); missing examples: Art. 17"
                ),
            )
            self.assertTrue(created)
            meta = rag.front_matter(draft)
            self.assertEqual(meta["bc250_fidelity_status"], "review")
            self.assertIn("Art. 17", str(meta["bc250_fidelity_note"]))
            meta["review_required"] = False
            with self.assertRaisesRegex(ValueError, "requires explicit"):
                rag.validate_document_metadata(meta, active=True)
            meta["bc250_fidelity_acknowledged"] = "true"
            rag.validate_document_metadata(meta, active=True)

    def test_batch2_review_persists_explicit_fidelity_acknowledgement(self) -> None:
        class Tty:
            @staticmethod
            def isatty() -> bool:
                return True

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            source = base / "sources" / "reglement.pdf"
            source.write_bytes(b"source")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            lifecycle.write_draft(
                base,
                source,
                digest,
                "# Reglement\n\nBody\n",
                "de-CH",
                "authoritative",
                bilingual=False,
                fidelity_status="review",
                fidelity_note_text="manual source comparison required",
            )
            args = type(
                "Args",
                (),
                {
                    "root": root,
                    "scope": "public",
                    "collection": "COLLECTION",
                    "all": False,
                },
            )()
            answers = iter(["", "", "2026-01-01", "", "", "y", "y"])
            stdout = io.StringIO()
            with patch.object(lifecycle.sys, "stdin", Tty()), patch(
                "builtins.input", side_effect=lambda _prompt="": next(answers)
            ), redirect_stdout(stdout):
                lifecycle.cmd_review(args)
            reviewed = base / "working" / "reglement_de-CH_2026-01-01.md"
            self.assertTrue(reviewed.is_file())
            meta = rag.front_matter(reviewed)
            self.assertEqual(meta["review_required"], "false")
            self.assertEqual(meta["bc250_fidelity_acknowledged"], "true")
            self.assertIn("RESULT=READY", stdout.getvalue())
            self.assertIn("READY_TO_ACTIVATE=YES", stdout.getvalue())

    def test_review_without_effective_or_edition_reports_not_ready_state(self) -> None:
        class Tty:
            @staticmethod
            def isatty() -> bool:
                return True

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            source = base / "sources" / "reglement.pdf"
            source.write_bytes(b"source")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            lifecycle.write_draft(
                base,
                source,
                digest,
                "# Reglement\n\nBody\n",
                "de-CH",
                "authoritative",
                bilingual=False,
                fidelity_status="not-scored",
                fidelity_note_text="no critical tokens",
            )
            args = type(
                "Args",
                (),
                {
                    "root": root,
                    "scope": "public",
                    "collection": "COLLECTION",
                    "all": False,
                },
            )()
            answers = iter(["", "", "", "", "", "y"])
            stdout = io.StringIO()
            with patch.object(lifecycle.sys, "stdin", Tty()), patch(
                "builtins.input", side_effect=lambda _prompt="": next(answers)
            ), redirect_stdout(stdout):
                lifecycle.cmd_review(args)
            output = stdout.getvalue()
            self.assertIn(
                "REVIEW REQUIRED: provide either an effective date or edition/version before activation.",
                output,
            )
            self.assertIn("RESULT=REVIEW_REQUIRED", output)
            self.assertIn("READY_TO_ACTIVATE=NO", output)
            reviewed = base / "working" / "reglement_de-CH_review.md"
            self.assertEqual(rag.front_matter(reviewed)["review_required"], "true")

    def test_batch2_prepare_one_records_automated_fidelity_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            source = base / "inbox" / "german" / "reglement.pdf"
            source.write_bytes(b"fake pdf")
            extracted = "Art. 17 applies. " + ("text " * 100)
            with patch.object(lifecycle, "source_text", return_value=(1, extracted)), patch.object(
                lifecycle,
                "call_agent",
                return_value="# Reglement\n\nThe article was omitted.\n",
            ):
                drafts = lifecycle.prepare_one(
                    base,
                    source,
                    "german",
                    "http://127.0.0.1:11436",
                    lifecycle.DEFAULT_AGENT_MODEL,
                    lifecycle.DEFAULT_MAX_CHARS,
                )
            self.assertEqual(len(drafts), 1)
            meta = rag.front_matter(drafts[0])
            self.assertEqual(meta["bc250_fidelity_status"], "review")
            self.assertIn("Art. 17", str(meta["bc250_fidelity_note"]))


    def test_batch3_status_reports_review_currentness_and_validation_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lifecycle.ensure_collection(root, "public", "COLLECTION")
            active = self.make_doc(
                root,
                "public",
                "reglement.md",
                "de-CH",
                "de-CH",
                "reglement.pdf",
            )
            active_text = active.read_text(encoding="utf-8").replace(
                'authority_role: "authoritative"\n',
                'authority_role: "authoritative"\nstatus: "currentness-not-verified"\n',
            )
            active.write_text(active_text, encoding="utf-8")
            base = active.parent.parent
            source = base / "sources" / "draft.pdf"
            source.write_bytes(b"draft source")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            draft, _created = lifecycle.write_draft(
                base,
                source,
                digest,
                "# Draft\n\nBody\n",
                "de-CH",
                "authoritative",
                bilingual=False,
                fidelity_status="review",
                fidelity_note_text="manual comparison required",
            )
            draft_meta, draft_body = lifecycle.split_markdown(draft)
            draft_meta["effective_from"] = "2026-01-01"
            draft_meta["review_required"] = False
            draft_meta["bc250_fidelity_acknowledged"] = "true"
            draft.write_text(
                lifecycle.render_markdown(draft_meta, draft_body), encoding="utf-8"
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = lifecycle.main(
                    ["--root", str(root), "status", "public", "COLLECTION"]
                )
            self.assertEqual(rc, 0)
            output = stdout.getvalue()
            self.assertIn("Needs review:         0", output)
            self.assertIn("Ready to activate:    1", output)
            self.assertIn("Currentness review:   1", output)
            self.assertIn("Lifecycle validation: WARN", output)
            self.assertIn("Knowledge sync: NOT INSPECTED", output)

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                missing_rc = lifecycle.main(
                    ["--root", str(root), "status", "public", "MISSING"]
                )
            self.assertEqual(missing_rc, 2)
            self.assertIn("Document collection not found: public/MISSING", stderr.getvalue())

    def test_batch3_review_surfaces_provenance_and_blocks_bad_source(self) -> None:
        class Tty:
            @staticmethod
            def isatty() -> bool:
                return True

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = lifecycle.ensure_collection(root, "public", "COLLECTION")
            source = base / "sources" / "reglement.pdf"
            source.write_bytes(b"source")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            draft, _created = lifecycle.write_draft(
                base,
                source,
                digest,
                "# Reglement\n\nBody\n",
                "de-CH",
                "authoritative",
                bilingual=False,
                fidelity_status="not-scored",
                fidelity_note_text="manual fixture",
            )
            meta, body = lifecycle.split_markdown(draft)
            meta["source_sha256"] = "0" * 64
            draft.write_text(lifecycle.render_markdown(meta, body), encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "root": root,
                    "scope": "public",
                    "collection": "COLLECTION",
                    "all": False,
                },
            )()
            answers = iter(["", "", "2026-01-01", "", "", "y"])
            stdout = io.StringIO()
            with (
                patch.object(lifecycle.sys, "stdin", Tty()),
                patch("builtins.input", side_effect=lambda _prompt="": next(answers)),
                redirect_stdout(stdout),
            ):
                lifecycle.cmd_review(args)
            output = stdout.getvalue()
            self.assertIn("source SHA:  FAIL", output)
            self.assertIn("currentness: currentness-not-verified", output)
            self.assertIn(
                "Source provenance must be repaired before this draft can be marked ready.",
                output,
            )
            self.assertIn("RESULT=REVIEW_REQUIRED", output)
            self.assertIn("READY_TO_ACTIVATE=NO", output)
            reviewed = base / "working" / "reglement_de-CH_2026-01-01.md"
            reviewed_meta = rag.front_matter(reviewed)
            self.assertEqual(reviewed_meta["review_required"], "true")



    def test_managed_docx_extraction_preserves_basic_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docx = Path(tmp) / "example.docx"
            xml = ('<?xml version="1.0" encoding="UTF-8"?>'
                   '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                   '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Policy</w:t></w:r></w:p>'
                   '<w:p><w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>Keep provenance</w:t></w:r></w:p>'
                   '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Amount</w:t></w:r></w:p></w:tc>'
                   '<w:tc><w:p><w:r><w:t>CHF 123</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
                   '</w:body></w:document>')
            with zipfile.ZipFile(docx, "w") as archive:
                archive.writestr("word/document.xml", xml)
            pages, text = lifecycle.docx_source_text(docx)
            self.assertEqual(pages, 0)
            self.assertIn("# Policy", text)
            self.assertIn("- Keep provenance", text)
            self.assertIn("Amount | CHF 123", text)

    def test_large_source_normalization_chunks_and_retries_budget_exhaustion_safely(self) -> None:
        source = ("Paragraph one " * 120 + "\n\n" + "Paragraph two " * 120).strip()
        calls = []
        def fake_call(_url, _model, prompt, *, think=True):
            calls.append((think, prompt))
            if think and len(calls) == 1:
                raise lifecycle.AgentGenerationLimit("budget")
            marker = re.search(r"<!-- BC250-CHUNK \d+/\d+ SHA256=[0-9a-f]+ -->", prompt)
            self.assertIsNotNone(marker)
            return f"{marker.group(0)}\n# Managed\n\nNormalized body {len(calls)}\n"
        with patch.object(lifecycle, "call_agent", side_effect=fake_call):
            result = lifecycle.normalize_source_text(
                "http://127.0.0.1:11436", "agent", source, "de-CH", False, 1000
            )
        self.assertGreater(len(calls), 2)
        self.assertEqual(calls[0][0], True)
        self.assertEqual(calls[1][0], False)
        self.assertTrue(result.startswith("# Managed"))
        self.assertEqual(result.count("# Managed"), 1)

    def test_large_source_rejects_missing_chunk_critical_tokens(self) -> None:
        sections = [
            f"Article {100 + index} BC250-LARGE-{index:02d} CHF {1000 + index} " + ("word " * 130)
            for index in range(1, 4)
        ]
        source = "\n\n".join(sections)
        chunks = lifecycle.split_source_chunks(source, 1000)
        by_identity = {
            lifecycle.chunk_identity(chunk, index, len(chunks)): chunk
            for index, chunk in enumerate(chunks, 1)
        }

        def fake_call(_url, _model, prompt, *, think=True):
            marker = re.search(r"<!-- BC250-CHUNK \d+/\d+ SHA256=[0-9a-f]+ -->", prompt)
            self.assertIsNotNone(marker)
            body = by_identity[marker.group(0)]
            if "BC250-LARGE-02" in body:
                body = body.replace("BC250-LARGE-02", "")
            return f"{marker.group(0)}\n# Managed\n\n{body}\n"

        with patch.object(lifecycle, "call_agent", side_effect=fake_call), \
             self.assertRaisesRegex(lifecycle.DeferredPreparation, "critical source token"):
            lifecycle.normalize_source_text(
                "http://127.0.0.1:11436", "agent", source, "de-CH", False, 1000
            )

    def test_large_source_rejects_duplicate_normalized_chunk(self) -> None:
        source = "\n\n".join(
            (f"Section {letter} " + (f"word{letter} " * 150)).strip()
            for letter in ("A", "B", "C")
        )

        def fake_call(_url, _model, prompt, *, think=True):
            marker = re.search(r"<!-- BC250-CHUNK \d+/\d+ SHA256=[0-9a-f]+ -->", prompt)
            self.assertIsNotNone(marker)
            return f"{marker.group(0)}\n# Managed\n\nRepeated normalized chunk\n"

        with patch.object(lifecycle, "call_agent", side_effect=fake_call), \
             self.assertRaisesRegex(lifecycle.DeferredPreparation, "duplicated an earlier"):
            lifecycle.normalize_source_text(
                "http://127.0.0.1:11436", "agent", source, "de-CH", False, 1000
            )

    def test_document_status_help_exposes_read_only_knowledge_inspection(self) -> None:
        result = subprocess.run(
            [sys.executable, str(LIFECYCLE), "status", "--help"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--knowledge", result.stdout)
        self.assertIn("read-only Open WebUI Knowledge diff", result.stdout)
        self.assertIn("--verbose", result.stdout)

if __name__ == "__main__":
    unittest.main()
