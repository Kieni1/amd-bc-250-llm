"""Focused OPEN WIP regressions from the 2026-11-05 code-review handovers."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cmd/benchmark"))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


category = load("review_category", ROOT / "cmd/benchmark/category-benchmark.py")
translator = load("review_translation", ROOT / "config/openwebui/functions/bc250_translation_direction.py")
importer = load("review_importer", ROOT / "cmd/documents/importer.py")
modelctl = load("review_modelctl", ROOT / "models/modelctl.py")
storage = load("review_storage", ROOT / "cmd/system/storage.py")


class ReviewRegressions(unittest.TestCase):
    def test_h1_numeric_date_and_reference_contract(self):
        good = (
            ("Die Frist beträgt 30 Tage.", "Le délai est de 30 jours."),
            ("Sitzung am 03.11.2026.", "Séance le 3 novembre 2026."),
            ("Der Betrag beträgt 1'250 Franken.", "Le montant est de 1 250 francs."),
        )
        bad = (
            ("Die Frist beträgt 30 Tage.", "Le délai est de 60 jours."),
            ("Art. 12 gilt.", "L'art. 21 s'applique."),
            ("Der Betrag beträgt 1250 Franken.", "Le montant est de 2150 francs."),
            ("Sitzung am 03.11.2026.", "Séance le 4 novembre 2026."),
        )
        for source, target in good:
            with self.subTest(source=source, good=True):
                self.assertIsNone(translator.literal_integrity_mismatch(source, target))
        for source, target in bad:
            with self.subTest(source=source, good=False):
                self.assertIsNotNone(translator.literal_integrity_mismatch(source, target))

    def test_c3_translation_role_rejects_attached_context(self):
        roles = json.loads((ROOT / "config/openwebui/models.json").read_text())["models"]
        for role in roles:
            if role["id"] in translator.WRAPPERS:
                self.assertFalse(role["meta"]["capabilities"]["file_context"])
        body = {"model": translator.DE_FR_MODEL, "files": [{"id": "doc"}],
                "messages": [{"role": "user", "content": "Bitte Datei übersetzen"}]}
        with self.assertRaisesRegex(ValueError, "attachment|file context"):
            asyncio.run(translator.Filter().inlet(body))

    def test_h2_ghost_secrets_survive_erase(self):
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text()
        for name in ("open-webui.env", "openwebui-admin.key"):
            self.assertRegex(spec, rf"%ghost %config\(noreplace\) %attr\(0600,root,root\) /var/lib/bc250-llm-server/secrets/{name}")

    def test_m2_bounded_match_rejects_extended_fields(self):
        for text, required in (("CHF 840'000", "CHF 840"), ("CHF 840.50", "CHF 840"),
                               ("INV-2026-0042-B", "INV-2026-0042")):
            with self.subTest(text=text):
                self.assertFalse(category._bounded_acceptance_match(text, required))
        self.assertTrue(category._bounded_acceptance_match("CHF 840. Andere Daten", "CHF 840"))

    def test_m3_forbidden_semantic_formats(self):
        for response, forbidden in (("CHF 1'500", "CHF 1500"),
                                    ("30.09.2026", "30. September 2026")):
            self.assertFalse(category._acceptance_ok(response, {"forbidden": [forbidden]})[0])

    def test_m4_dates_and_currency(self):
        for response, required in (("1er mars 2026", "01.03.2026"),
                                    ("2026-03-01", "1. März 2026"),
                                    ("CHF 1,250.00", "CHF 1'250.00"),
                                    ("EUR 1,250.00", "EUR 1.250,00")):
            with self.subTest(response=response):
                self.assertTrue(category._acceptance_ok(response, {"required": [required]})[0])
        self.assertFalse(category._semantic_dates("31.02.2026"))
        self.assertFalse(category._acceptance_ok("CHF 1250", {"required": ["CHF 1,250"]})[0])

    def test_m5_visible_budget_truncation_is_quality_failure(self):
        case = {"id": "cut", "prompt": "short", "model": "demo", "num_predict": 32}
        record = category._usecase_result_record(case=case, model="demo", row={"timestamp": "2026-11-05T00:00:00Z"},
            ok=True, problems=[], content="Visible unfinished", thinking="", telemetry={}, wall=1.0, done_reason="length")
        self.assertEqual(record["outcome"], "quality-fail")
        self.assertIn("output-budget", record["diagnostics"])
        self.assertNotIn("thinking-budget", record["diagnostics"])
        self.assertTrue(record["failure_kinds"])

    def test_l6_strict_json_parser_consistency(self):
        self.assertFalse(category.strict_json_object('{"a":1,"a":2}'))
        self.assertFalse(category.strict_json_object('{"a":NaN}'))
        self.assertTrue(category.strict_json_object('{"a":1}'))

    def test_c1_known_superseded_remote_revision_is_pruned_only_after_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "public" / "COLLECTION"
            (base / "active").mkdir(parents=True)
            (base / "superseded").mkdir()
            (base / "superseded" / "old.md").write_text("---\nlanguage: de-CH\n---\nold\n")
            current = base / "active" / "new.md"
            current.write_text("new")
            document = importer.Document(current, "public", "COLLECTION", "original", "de-CH", "new.pdf", "a"*64)
            class FakeApi:
                def __init__(self):
                    self.cleaned = []
                    self.uploaded = []
                def knowledge(self, name, description):
                    return {"id": "kb"}
                def find_knowledge(self, name):
                    return None
                def diff(self, knowledge_id, docs):
                    return {"added": [{"filename": "new.md"}], "modified": [],
                            "deleted": [{"filename": "old.md", "file_id": "old-id"},
                                        {"filename": "unrelated.md", "file_id": "other-id"}]}
                def upload(self, knowledge_id, doc):
                    self.uploaded.append(doc.path.name)
                def cleanup(self, knowledge_id, file_ids):
                    self.cleaned.extend(file_ids)
            fake = FakeApi()
            args = SimpleNamespace(url="http://127.0.0.1:3000", token_file=None, timeout=5, prune=False,
                                   allow_remote=False, allow_confidential_remote=False)
            with patch.object(importer, "OpenWebUI", return_value=fake), patch.object(importer, "token_from", return_value="key"), redirect_stdout(io.StringIO()):
                importer.sync(root, [document], [], args)
            self.assertEqual(fake.uploaded, ["new.md"])
            self.assertEqual(fake.cleaned, ["old-id"])

    def test_c6_ingest_package_admin_key_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            credential = Path(directory) / "admin.key"
            credential.write_text("test-key")
            credential.chmod(0o600)
            args = SimpleNamespace(token_file=None)
            with patch.object(importer, "PACKAGE_API_KEY", credential), patch.dict("os.environ", {"OPEN_WEBUI_API_KEY": ""}):
                self.assertEqual(importer.token_from(args), "test-key")

    def test_m1_pruned_source_stays_registered_without_redownload(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.gguf"
            source.write_bytes(b"tested GGUF")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            state_file = source.with_name(source.name + ".bc250.json")
            state_file.write_text(json.dumps({"schema": 4, "sha256": digest,
                "repository": "local/repo", "gguf": "model.gguf", "remote_path": "model.gguf",
                "revision": "latest", "configured_ref": "latest"}))
            storage.mark_pruned_source(state_file)
            source.unlink()
            state = modelctl.load_state(state_file)
            model = {"id": "model", "name": "model", "provider": "huggingface", "sha256": "",
                     "repository": "local/repo", "gguf": "model.gguf", "remote_path": "model.gguf",
                     "revision": "latest"}
            status, _detail, checksum = modelctl.inspect_local_source(state, model, source)
            self.assertEqual(status, "pruned")
            self.assertEqual(checksum, digest)
            self.assertTrue(modelctl.pruned_registration_reusable(status, "current", "current", False))
            self.assertFalse(modelctl.pruned_registration_reusable(status, "missing", "current", False))
            self.assertFalse(modelctl.pruned_registration_reusable(status, "current", "drift", False))
            self.assertFalse(modelctl.pruned_registration_reusable(status, "current", "current", True))

    def test_c1_last_active_superseded_lane_still_syncs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archived = root / "public" / "COLLECTION" / "superseded"
            archived.mkdir(parents=True)
            (archived / "old.md").write_text("---\nlanguage: de-CH\n---\nold\n")
            class FakeApi:
                def __init__(self):
                    self.removed = []
                    self.visited = []
                def find_knowledge(self, name):
                    self.visited.append(name)
                    return {"id": "kb"}
                def diff(self, knowledge_id, docs):
                    return {"deleted": [{"filename": "old.md", "file_id": "old-id"}]}
                def cleanup(self, knowledge_id, file_ids):
                    self.removed.extend(file_ids)
            fake = FakeApi()
            args = SimpleNamespace(url="http://127.0.0.1:3000", token_file=None, timeout=5, prune=False,
                                   allow_remote=False, allow_confidential_remote=False)
            with patch.object(importer, "OpenWebUI", return_value=fake), patch.object(importer, "token_from", return_value="key"), redirect_stdout(io.StringIO()):
                importer.sync(root, [], [], args)
            self.assertEqual(fake.visited, ["[PUBLIC] COLLECTION — Originals"])
            self.assertEqual(fake.removed, ["old-id"])

    def test_l7_multipart_rejects_untrusted_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'header"injection.md'
            path.write_text("content")
            document = importer.Document(path, "public", "COLLECTION", "original", "de-CH", "src.pdf", "a"*64)
            api = importer.OpenWebUI("http://127.0.0.1:3000", "test-key", 5)
            with self.assertRaisesRegex(ValueError, "unsafe multipart"):
                api.upload("kb", document)

    def test_m6_openwebui_translation_finish_reason_extracted(self):
        owui = load("review_owui_benchmark", ROOT / "cmd/benchmark/openwebui-benchmark.py")
        self.assertEqual(owui.response_finish_reason({"choices": [{"finish_reason": "length"}]}), "length")
        self.assertEqual(owui.response_finish_reason({"choices": [{"finish_reason": "stop"}]}), "stop")

    def test_l2_override_rejected_when_symlinked_or_world_writable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            desired = root / "desired.json"
            desired.write_text((ROOT / "config/openwebui/desired-state.json").read_text())
            desired.chmod(0o666)
            with (
                patch.dict("os.environ", {"BC250_OWUI_DESIRED_STATE": str(desired)}),
                self.assertRaisesRegex(category.BenchmarkError, "permissions"),
            ):
                category.task_prompt_state_path()
            desired.chmod(0o600)
            target = root / "alias.json"
            target.symlink_to(desired)
            with (
                patch.dict("os.environ", {"BC250_OWUI_DESIRED_STATE": str(target)}),
                self.assertRaisesRegex(category.BenchmarkError, "non-symlink"),
            ):
                category.task_prompt_state_path()
            with patch.dict("os.environ", {"BC250_OWUI_DESIRED_STATE": str(desired)}):
                self.assertEqual(category.task_prompt_state_path(), desired)

    def test_c5_revalidation_covers_generalist_role(self):
        script = (ROOT / "cmd/benchmark/revalidate.sh").read_text()
        self.assertIn('readonly GENERALIST_MODEL=prod-nemotron35-bolt-e4b-atomicchat-uncensored-q6-k', script)
        self.assertIn('"$E2B_MODEL" "$E4B_MODEL" "$GENERALIST_MODEL"', script)

    def test_l3_posttrans_classification_uses_pre_marker(self):
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text()
        pre = spec[spec.index("%pre\n"):spec.index("%post\n")]
        posttrans = spec[spec.index("%posttrans\n"):spec.index("%preun\n")]
        self.assertIn('bc250_tx_dir/upgrade', pre)
        self.assertIn('bc250_tx_dir/upgrade', posttrans)
        self.assertNotIn('if [ "$1" -gt 1 ]', posttrans)

    def test_c8_verify_uses_desired_state_task_model_not_literal(self):
        script = (ROOT / "cmd/monitoring/verify-server.sh").read_text()
        self.assertIn(".task.TASK_MODEL", script)
        self.assertNotIn('--arg model "task-lfm25-1.2b-instruct-liquidai-q6-k"', script)
        self.assertIn('"$desired_task_model"', script)

    def test_c7_missing_pair_error_mentions_safe_update_path(self):
        source = (ROOT / "cmd/documents/lifecycle.py").read_text()
        self.assertIn("activate the matching reviewed FR re-translation", source)
        self.assertIn("supersede the old FR translation first", source)

    def test_l1_current_rag_docs_match_k6_desired_state(self):
        text = (ROOT / "docs/RAG.md").read_text()
        self.assertIn("| Top K | `6`", text)
        self.assertNotIn("Top-K-4 profile is the package standard", text)
        fixture = json.loads((ROOT / "examples/benchmark/rag-quality-office.json").read_text())
        self.assertEqual(fixture["top_k"], 6)



class ReviewFollowUpRegressions(unittest.TestCase):
    """Follow-up fixes from the 2026-11-06 review of the OPEN WIP overlay."""

    CORRECT = (
        ("Die Sitzung beginnt am 1. Juli um 14.30 Uhr.", "La séance commence le 1er juillet à 14h30."),
        ("Treffpunkt um 9 Uhr im 2. Stock.", "Rendez-vous à 9h au 2e étage."),
        ("Die Arbeitszeit beträgt 8 Stunden pro Tag.", "Le temps de travail est de 8 h par jour."),
        ("Le guichet ouvre à 14:00.", "Der Schalter öffnet um 14 Uhr."),
        ("Les employés peuvent utiliser la salle jusqu'à 18:00.", "Die Mitarbeitenden dürfen den Raum bis 18 Uhr nutzen."),
        ("Die Frist endet am 15. Jan. 2027.", "Le délai expire le 15 janvier 2027."),
        ("Le délai expire le 15 janv. 2027.", "Die Frist endet am 15. Januar 2027."),
        ("Im Jahr 2025 wurden 1'200 Gesuche bearbeitet.", "En 2025, 1200 demandes ont été traitées."),
        ("Der 2. Absatz bleibt unverändert.", "Le 2e alinéa reste inchangé."),
        ("Ouvert de 8 h à 12 h.", "Geöffnet von 8 bis 12 Uhr."),
        ("Bitte rufen Sie uns unter 044 123 45 67 an.", "Veuillez nous appeler au 044 123 45 67."),
    )
    WRONG = (
        ("Die Sitzung beginnt um 14.30 Uhr.", "La séance commence à 15h30."),
        ("Le guichet ouvre à 14h30.", "Der Schalter öffnet um 14 Uhr."),
        ("Die Frist endet am 15. Jan. 2027.", "Le délai expire le 16 janvier 2027."),
        ("Die Arbeitszeit beträgt 8 Stunden.", "Le temps de travail est de 6 h."),
        ("Die Ziffern 1, 2 und 3 gelten.", "Les chiffres 1, 2 et 4 s'appliquent."),
        ("Im Jahr 2025 wurden 1'200 Gesuche bearbeitet.", "En 2025, 1300 demandes ont été traitées."),
    )

    def test_h1_guard_accepts_equivalent_swiss_renderings(self):
        for source, target in self.CORRECT:
            with self.subTest(source=source):
                self.assertIsNone(translator.literal_integrity_mismatch(source, target))

    def test_h1_guard_still_withholds_changed_values(self):
        for source, target in self.WRONG:
            with self.subTest(source=source):
                self.assertIsNotNone(translator.literal_integrity_mismatch(source, target))

    def test_c1_superseded_lane_uses_ingestion_route_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archived = root / "public" / "COLLECTION" / "superseded"
            archived.mkdir(parents=True)
            (archived / "ancien.md").write_text(
                "---\nlanguage: fr\nrelation:\n  type: translation-pair\n  source_language: de\n---\nx\n"
            )
            (archived / "broken.md").write_text("no front matter\n")
            lanes = importer.known_superseded_knowledge(root)
            self.assertEqual(set(lanes), {"[PUBLIC] COLLECTION — Français"})
            self.assertEqual(lanes["[PUBLIC] COLLECTION — Français"], archived)

    def test_c1_superseded_match_rejects_path_like_remote_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "public" / "COLLECTION"
            (base / "superseded").mkdir(parents=True)
            (base / "active").mkdir()
            (base / "superseded" / "old.md").write_text("---\nlanguage: de-CH\n---\nold\n")
            (base / "active" / "keep.md").write_text("x")

            class FakeApi:
                def __init__(self):
                    self.removed: list[str] = []

                def find_knowledge(self, name):
                    return {"id": "kb"}

                def diff(self, knowledge_id, docs):
                    return {"deleted": [{"filename": "../active/keep.md", "file_id": "escape-id"},
                                        {"filename": "old.md", "file_id": "old-id"}]}

                def cleanup(self, knowledge_id, file_ids):
                    self.removed.extend(file_ids)

            fake = FakeApi()
            args = SimpleNamespace(url="http://127.0.0.1:3000", token_file=None, timeout=5, prune=False,
                                   allow_remote=False, allow_confidential_remote=False)
            with (
                patch.object(importer, "OpenWebUI", return_value=fake),
                patch.object(importer, "token_from", return_value="key"),
                redirect_stdout(io.StringIO()),
            ):
                importer.sync(root, [], [], args)
            self.assertEqual(fake.removed, ["old-id"])

    def test_c6_missing_package_key_names_the_remedy(self):
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(token_file=None)
            missing = Path(directory) / "absent.key"
            with (
                patch.object(importer, "PACKAGE_API_KEY", missing),
                patch.dict("os.environ", {"OPEN_WEBUI_API_KEY": ""}),
                self.assertRaisesRegex(ValueError, "--token-file or OPEN_WEBUI_API_KEY"),
            ):
                importer.token_from(args)

    def test_m5_truncated_agent_output_is_not_accepted(self):
        source = (ROOT / "cmd/benchmark/category-benchmark.py").read_text(encoding="utf-8")
        self.assertIn('accepted = bool(result["accepted"]) and done_reason != "length"', source)

    def test_l2_verify_resolves_desired_state_once_before_checks(self):
        verify = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        resolved = verify.index('DESIRED_STATE_FILE="${BC250_OWUI_DESIRED_STATE:-')
        self.assertLess(resolved, verify.index('section "Platform"'))
        self.assertEqual(verify.count("${BC250_OWUI_DESIRED_STATE:-/usr/share"), 1)
        self.assertIn('desired_state="$DESIRED_STATE_FILE"', verify)

    def test_l3_erase_removes_transaction_marker_directory(self):
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        postun = spec[spec.index("%postun"):spec.index("%files")]
        self.assertIn("rm -rf /var/lib/rpm-state/bc250-llm-server", postun)


if __name__ == "__main__":
    unittest.main()
