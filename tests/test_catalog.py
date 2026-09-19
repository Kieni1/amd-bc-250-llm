from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
MODELFILES = ROOT / "models/modelfiles"
sys.path.insert(0, str(ROOT / "models"))

import modelctl


def load(category: str) -> tuple[dict, list[dict]]:
    return modelctl.load_models(category, directories=[MODELFILES])


class ModelfileDiscoveryTests(unittest.TestCase):

    def test_modelfile_graveyard_contains_only_modelfiles(self) -> None:
        graveyard = ROOT / "models/modelfiles-graveyard"
        self.assertTrue(graveyard.is_dir())
        entries = list(graveyard.iterdir())
        self.assertTrue(entries)
        self.assertTrue(all(path.is_file() and path.suffix == ".Modelfile" for path in entries))

    def test_modelfile_graveyard_is_not_packaged_or_discovered(self) -> None:
        graveyard = ROOT / "models/modelfiles-graveyard"
        retired = {path.stem for path in graveyard.glob("*.Modelfile")}
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertNotIn("modelfiles-graveyard", manifest)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MODELFILE_SOURCE_DIR", None)
            roots = modelctl.model_directories()
        self.assertNotIn(graveyard, roots)
        self.assertTrue(all("graveyard" not in str(path) for path in roots))
        active = {model["name"] for model in modelctl.discover_models([MODELFILES])}
        self.assertTrue(retired.isdisjoint(active))

    def test_retired_catalog_exactly_matches_source_graveyard(self) -> None:
        graveyard = ROOT / "models/modelfiles-graveyard"
        expected = {path.stem for path in graveyard.glob("*.Modelfile")}
        catalog = json.loads((ROOT / "models/retired-models.json").read_text(encoding="utf-8"))
        actual = {item["name"] for item in catalog["models"]}
        self.assertEqual(actual, expected)

    def test_every_packaged_modelfile_is_discovered_and_strictly_valid(self) -> None:
        models = modelctl.discover_models([MODELFILES])
        packaged = {path.stem for path in MODELFILES.glob("*.Modelfile")}
        self.assertEqual({model["name"] for model in models}, packaged)

    def test_current_model_set_and_dedicated_instances_are_preserved(self) -> None:
        expected_hosts = {
            "production": "127.0.0.1:11434",
            "experiments": "127.0.0.1:11434",
            "task": "127.0.0.1:11435",
            "agentic": "127.0.0.1:11436",
            "embedding": "127.0.0.1:11437",
        }
        for category, host in expected_hosts.items():
            with self.subTest(category=category):
                defaults, models = load(category)
                self.assertTrue(models, f"{category} catalog must not be empty")
                self.assertEqual(defaults["ollama_host"], host)
        required = {
            "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl",
            "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl",
            "prod-gpt-oss20b-ggml-org-mxfp4",
            "prod-translate-gemma4-sub-e4b-17s-q4-k-xl",
            "prod-qwen35-9b-unsloth-q6-k",
        }
        self.assertTrue(required <= {model["name"] for model in load("production")[1]})

    def test_runtime_modelfiles_do_not_embed_campaign_measurement_notes(self) -> None:
        for path in MODELFILES.glob("*.Modelfile"):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("measurement note, 2026-09-17", text)

    def test_all_modelfiles_keep_required_bc250_gpu_and_context_settings(self) -> None:
        for path in MODELFILES.glob("*.Modelfile"):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(
                    len(re.findall(r"^PARAMETER num_gpu 99$", text, re.MULTILINE)), 1
                )
                if not path.name.startswith("embed-"):
                    self.assertEqual(
                        len(
                            re.findall(r"^PARAMETER num_keep 256$", text, re.MULTILINE)
                        ),
                        1,
                    )

    def test_experimental_ocr_models_use_ollama_managed_hf_sources(self) -> None:
        expected = {
            "exp-glm-ocr-ggml-q8-0",
            "exp-ovisocr2-abiray-q8-0",
        }
        models = {
            model["name"]: model for model in modelctl.discover_models([MODELFILES])
        }
        self.assertTrue(expected <= models.keys())
        self.assertTrue(
            all(models[name]["provider"] == "ollama-hf" for name in expected)
        )
        glm = (MODELFILES / "exp-glm-ocr-ggml-q8-0.Modelfile").read_text()
        self.assertIn("PARAMETER num_ctx 16384", glm)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "exp-remote-mismatch.Modelfile"
            path.write_text(
                glm.replace("exp-glm-ocr-ggml-q8-0", "exp-remote-mismatch").replace(
                    "hf.co/ggml-org/GLM-OCR-GGUF", "hf.co/other/repository"
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                modelctl.ModelError, "must match Source metadata"
            ):
                modelctl.load_modelfile(path)

    def test_ornith_checksum_is_pinned_to_replacement_commit(self) -> None:
        text = (MODELFILES / "agentic-ornith15-9b-ornith-q5-k-m.Modelfile").read_text()
        self.assertIn("@ 87fcf5d7dbecb02941c0917a0e93619af2075b61", text)
        self.assertIn(
            "# SHA256: e4d9634a3b6546a5c00a8680568fe1125f6c98c704ee51ae52ba07650fb4247d",
            text,
        )

    def test_embedding_modelfiles_are_bounded_to_dedicated_4k_lane(self) -> None:
        for name in (
            "embed-jina-v5-small-retrieval-q4-k-m.Modelfile",
            "embed-qwen3-0.6b-q8-0.Modelfile",
        ):
            text = (MODELFILES / name).read_text(encoding="utf-8")
            self.assertIn("PARAMETER num_ctx 4096", text)
            self.assertNotIn("PARAMETER num_ctx 32768", text)

    def test_jina_embedding_uses_pooling_metadata_revision(self) -> None:
        text = (
            MODELFILES / "embed-jina-v5-small-retrieval-q4-k-m.Modelfile"
        ).read_text()
        self.assertIn("@ e9137ac0a9d41c851de69bea36babc029b7f5fc9", text)
        self.assertIn(
            "# SHA256: 9440cf89f3e8a7a31a42e11b87e106dd5b344af4e0e3b6b21a96136cc8686e21",
            text,
        )
        self.assertIn("pooling metadata", text)

    def test_promoted_task_model_has_reviewed_sampling_and_no_fixed_system(self) -> None:
        task = (MODELFILES / "task-lfm25-1.2b-instruct-liquidai-q6-k.Modelfile").read_text()
        self.assertIn("PARAMETER temperature 0.1", task)
        self.assertIn("PARAMETER top_k 50", task)
        self.assertIn("PARAMETER repeat_penalty 1.05", task)
        self.assertNotRegex(task, r"(?m)^SYSTEM\s")
        coder = (MODELFILES / "agentic-ornith15-9b-ornith-q5-k-m.Modelfile").read_text()
        self.assertIn("PARAMETER num_ctx 32768", coder)
        self.assertIn("PARAMETER num_predict 3072", coder)
        self.assertIn("PARAMETER temperature 0", coder)
        self.assertIn("PARAMETER top_p 0.95", coder)

    def test_new_agentic_challenger_profiles_are_discoverable_and_bounded(self) -> None:
        expected = {
            "agentic-qwen35-4b-khazarai-q6-k",
            "agentic-gemma4-e4b-sol-fable-q4-k-m",
        }
        discovered = {
            model["name"]: model for model in modelctl.discover_models([MODELFILES])
        }
        self.assertTrue(expected <= discovered.keys())
        self.assertTrue(all(discovered[name]["category"] == "agentic" for name in expected))

        qwen = (MODELFILES / "agentic-qwen35-4b-khazarai-q6-k.Modelfile").read_text()
        self.assertIn("PARAMETER num_ctx 32768", qwen)
        self.assertIn("PARAMETER num_predict 3072", qwen)
        self.assertIn("PARAMETER temperature 0.6", qwen)
        self.assertIn("PARAMETER top_p 0.95", qwen)
        self.assertIn("PARAMETER top_k 20", qwen)
        self.assertIn("PARAMETER min_p 0.0", qwen)
        self.assertIn("PARAMETER repeat_penalty 1.0", qwen)

        gemma = (MODELFILES / "agentic-gemma4-e4b-sol-fable-q4-k-m.Modelfile").read_text()
        self.assertIn("PARAMETER num_ctx 16384", gemma)
        self.assertIn("PARAMETER num_predict 3072", gemma)
        self.assertIn("PARAMETER temperature 0", gemma)
        self.assertIn("PARAMETER top_p 0.95", gemma)
        self.assertIn("PARAMETER top_k 64", gemma)
        self.assertIn("PARAMETER repeat_penalty 1.1", gemma)

    def test_coding_helper_defaults_to_measured_ornith(self) -> None:
        helper = (ROOT / "models/coding-agent/coding-agent.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "CODING_AGENT_MODEL:-agentic-ornith15-9b-ornith-q5-k-m", helper
        )
        self.assertIn("CODING_AGENT_NUM_PREDICT:-3072", helper)
        self.assertIn('"${OLLAMA_URL}/api/chat"', helper)
        self.assertIn("think:true", helper)
        self.assertIn(".message.content", helper)
        self.assertIn('[[ "$done" != true ]]', helper)
        self.assertIn('[[ "$done_reason" == "length" ]]', helper)
        self.assertIn("reasoning markers", helper)
        self.assertIn('mktemp --tmpdir="$out_dir" .bc250-code.XXXXXX', helper)
        self.assertIn('mv -f -- "$tmp_out" "$output"', helper)
        self.assertNotIn('"${OLLAMA_URL}/api/generate"', helper)

    def test_recommended_tooling_models_are_discoverable(self) -> None:
        expected = {
            "embedding": "embed-jina-v5-small-retrieval-q4-k-m",
            "task": "task-lfm25-1.2b-instruct-liquidai-q6-k",
            "agentic": "agentic-ornith15-9b-ornith-q5-k-m",
        }
        for category, name in expected.items():
            with self.subTest(category=category):
                _defaults, models = load(category)
                self.assertIn(name, {model["name"] for model in models})
        self.assertNotIn(
            "task-gemma3-1b-unsloth-ud-q4-k-xl",
            {model["name"] for model in load("task")[1]},
        )

    def test_example_is_ignored_and_operator_template_overrides_package(self) -> None:
        name = "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl.Modelfile"
        with tempfile.TemporaryDirectory() as temporary:
            operator = Path(temporary)
            shutil.copy2(MODELFILES / name, operator / name)
            models = modelctl.discover_models([MODELFILES, operator])
            selected = next(model for model in models if model["modelfile"] == name)
            self.assertEqual(selected["template"], operator / name)
            self.assertNotIn("MODEL-TEMPLATE", {model["name"] for model in models})

    def test_incomplete_modelfile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "prod-invalid.Modelfile"
            path.write_text("PARAMETER num_gpu 99\nPARAMETER num_keep 256\n")
            with self.assertRaisesRegex(
                modelctl.ModelError, "missing category metadata"
            ):
                modelctl.load_modelfile(path)

    def test_duplicate_source_metadata_is_rejected(self) -> None:
        source = MODELFILES / "task-lfm25-1.2b-instruct-liquidai-q6-k.Modelfile"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / source.name
            text = source.read_text(encoding="utf-8")
            path.write_text(
                text.replace("# GGUF:", "# Source: owner/other @ main\n# GGUF:")
            )
            with self.assertRaisesRegex(modelctl.ModelError, "exactly one.*Source"):
                modelctl.load_modelfile(path)

    def test_production_qwen35_prompt_and_fablevibes_sampling_match_policy(
        self,
    ) -> None:
        qwen = (MODELFILES / "prod-qwen35-9b-unsloth-q6-k.Modelfile").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("experimental general assistant", qwen)
        self.assertIn("German-, French-, and English-speaking users", qwen)
        self.assertIn("PARAMETER temperature 0.7", qwen)
        self.assertIn("PARAMETER top_p 0.8", qwen)
        translator = (MODELFILES / "prod-translate-gemma4-sub-e4b-17s-q4-k-xl.Modelfile").read_text(encoding="utf-8")
        self.assertIn("production German/French translation base", translator)
        self.assertIn("PARAMETER num_predict 2048", translator)
        self.assertNotRegex(translator, r"(?m)^SYSTEM\s")
        lfm = (MODELFILES / "exp-lfm25-8b-a1b-liquidai-q6-k.Modelfile").read_text(encoding="utf-8")
        self.assertIn("experimental rollback/control", lfm)

    def test_qwen38_ista_profiles_match_intended_bc250_roles(self) -> None:
        quality = (MODELFILES / "exp-qwen38-27b-ista-gsq-rco-iq3-s.Modelfile").read_text(encoding="utf-8")
        self.assertIn("PARAMETER num_ctx 8192", quality)
        self.assertIn("PARAMETER num_predict 3072", quality)
        self.assertIn("PARAMETER temperature 1.0", quality)
        self.assertIn("PARAMETER top_p 0.95", quality)
        self.assertIn("PARAMETER top_k 20", quality)
        self.assertIn("PARAMETER min_p 0.0", quality)
        self.assertIn("PARAMETER repeat_last_n 64", quality)
        self.assertIn("think=true", quality)

        deploy = (MODELFILES / "exp-qwen38-27b-ista-gsq-rco-iq3-xxs.Modelfile").read_text(encoding="utf-8")
        self.assertIn("PARAMETER num_ctx 16384", deploy)
        self.assertIn("PARAMETER num_predict 1024", deploy)
        self.assertIn("PARAMETER temperature 0.7", deploy)
        self.assertIn("PARAMETER top_p 0.8", deploy)
        self.assertIn("PARAMETER top_k 20", deploy)
        self.assertIn("PARAMETER min_p 0.0", deploy)
        self.assertIn("PARAMETER repeat_last_n 64", deploy)
        self.assertIn("think=false", deploy)
        self.assertNotRegex(deploy, r"(?m)^SYSTEM\s")

    def test_task_model_accepts_open_webui_integrated_task_prompts(self) -> None:
        source = MODELFILES / "task-lfm25-1.2b-instruct-liquidai-q6-k.Modelfile"
        text = source.read_text(encoding="utf-8")
        self.assertIn("PARAMETER num_predict 128", text)
        self.assertNotRegex(
            text, r"(?m)^SYSTEM\s", msg="task prompts must come from Open WebUI"
        )

    def test_ollama_toml_catalogs_are_not_part_of_the_source_tree(self) -> None:
        source_dir = ROOT / "models/sources"
        self.assertFalse(source_dir.exists() and any(source_dir.glob("*.toml")))

    def test_mtp_keeps_its_download_only_runtime_catalog(self) -> None:
        defaults, models = modelctl.load_mtp_catalog(ROOT / "models/mtp/models.toml")
        self.assertEqual(defaults["category"], "mtp")
        self.assertEqual(
            [model["id"] for model in models],
            [
                "qwen3.5-9b-mtp",
                "qwen3.6-27b-mtp",
                "qwen3.8-27b-hauhaucs-mtp",
                "qwen3.8-27b-ymq-xs-ti-mtp",
            ],
        )
        self.assertTrue(all(model["provider"] == "download-only" for model in models))
        self.assertTrue(all(model["enabled"] is False for model in models))
        qwen38 = {model["id"]: model for model in models if model["id"].startswith("qwen3.8-27b-")}
        self.assertEqual(qwen38["qwen3.8-27b-hauhaucs-mtp"]["context"], 8192)
        self.assertEqual(qwen38["qwen3.8-27b-hauhaucs-mtp"]["draft"], 2)
        self.assertEqual(qwen38["qwen3.8-27b-ymq-xs-ti-mtp"]["context"], 8192)
        self.assertEqual(qwen38["qwen3.8-27b-ymq-xs-ti-mtp"]["draft"], 2)


    def test_failed_mtp_35b_candidate_is_source_graveyard_only(self) -> None:
        active = (ROOT / "models/mtp/models.toml").read_text(encoding="utf-8")
        graveyard = (ROOT / "models/mtp/graveyard.toml").read_text(encoding="utf-8")
        self.assertNotIn('id = "qwen3.6-35b-a3b-mtp"', active)
        self.assertIn('id = "qwen3.6-35b-a3b-mtp"', graveyard)
        self.assertIn("128 MiB MemAvailable hard floor", graveyard)

    def test_mtp_filtered_view_preserves_global_catalog_indexes(self) -> None:
        _defaults, mtp_only = modelctl.load_models(
            "mtp", directories=[MODELFILES], source=ROOT / "models/mtp/models.toml"
        )
        catalogs = modelctl.load_all_catalogs(
            directories=[MODELFILES], source=ROOT / "models/mtp/models.toml"
        )
        combined = next(models for defaults, models in catalogs if defaults["category"] == "mtp")
        self.assertEqual(
            [(model["id"], model["index"]) for model in mtp_only],
            [(model["id"], model["index"]) for model in combined],
        )

    def test_granite42_context_is_explicitly_bounded_for_bc250(self) -> None:
        source = (ROOT / "models/modelfiles" / "exp-granite42-3b-ibm-q6-k.Modelfile").read_text(encoding="utf-8")
        self.assertIn("PARAMETER num_ctx 32768", source)
        self.assertIn("128K context", source)


class CategoryInterfaceTests(unittest.TestCase):
    def test_public_categories_are_canonical_and_include_all(self) -> None:
        self.assertEqual(
            modelctl.CATEGORIES,
            (
                "production",
                "experiments",
                "task",
                "agentic",
                "embedding",
                "mtp",
                "all",
            ),
        )
        for legacy in ("experimental", "tasker", "coding", "embedded", "embed"):
            self.assertNotIn(legacy, modelctl.CATEGORIES)

    def test_no_argument_help_explains_common_workflows(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(modelctl.main([]), 0)
        text = output.getvalue()
        self.assertIn("bc250-model status agentic", text)
        self.assertIn("bc250-model apply agentic MODEL", text)
        self.assertIn("bc250-model unregister agentic MODEL", text)
        self.assertIn("bc250-model remove agentic MODEL", text)

    def test_list_is_catalog_only_and_does_not_require_sudo(self) -> None:
        output = StringIO()
        with (
            patch.object(modelctl.os, "geteuid", return_value=1000),
            patch.object(modelctl, "registered_models") as registered,
            redirect_stdout(output),
        ):
            self.assertEqual(
                modelctl.main(
                    ["list", "production", "--modelfile-dir", str(MODELFILES)]
                ),
                0,
            )
        registered.assert_not_called()
        self.assertIn("Production models:", output.getvalue())

    def test_status_requires_sudo_for_protected_runtime_state(self) -> None:
        with (
            patch.object(modelctl.os, "geteuid", return_value=1000),
            self.assertRaisesRegex(modelctl.ModelError, "sudo bc250-model status"),
        ):
            modelctl.main(["status", "agentic"])

    def test_incomplete_and_legacy_commands_get_actionable_guidance(self) -> None:
        cases = (
            (["apply"], "apply: model category is required"),
            (["--install"], "bc250-model apply <category>"),
            (["--refresh"], "bc250-model refresh <category>"),
            (["install", "agentic"], "'install' was replaced by 'apply'"),
            (
                ["cleanup", "agentic", "x", "--keep-gguf"],
                "'cleanup' was replaced by 'unregister'",
            ),
            (["cleanup-retired"], "'cleanup-retired' was replaced by 'purge-retired'"),
            (["resolve", "mtp", "x"], "'resolve' was replaced by 'path'"),
            (["all", "--install"], "bc250-model apply all"),
        )
        for argv, expected in cases:
            with self.subTest(argv=argv), self.assertRaisesRegex(
                modelctl.ModelError, expected
            ):
                modelctl.main(argv)


    def test_active_package_callers_use_new_model_manager_lifecycle(self) -> None:
        callers = (
            "cmd/system/install.sh",
            "models/coding-agent/setup-ollama.sh",
            "models/embedding/setup-ollama.sh",
            "models/task-model/setup-ollama.sh",
            "models/ocr/bc250-ocr.sh",
            "models/mtp/run-mtp-llamacpp.sh",
            "quality-checks/main/10-main-model-candidate-matrix.sh",
            "quality-checks/task/10-candidate-screen.sh",
            "quality-checks/translation/10-direct-candidate-screen.sh",
            "quality-checks/translation/20-owui-candidate-screen.sh",
            "quality-checks/package/installed-assets.sh",
            "scripts/validate.py",
        )
        forbidden = (
            "bc250-model install",
            "bc250-model cleanup",
            "bc250-model cleanup-retired",
            "bc250-model resolve",
            '"$MANAGER" install',
            '"$MANAGER" resolve',
            "--keep-gguf",
            "sudo bc250-model list",
            "sudo bc250-model path",
        )
        for relative in callers:
            text = (ROOT / relative).read_text(encoding="utf-8")
            for old in forbidden:
                self.assertNotIn(old, text, f"{relative}: stale model-manager call {old}")

    def test_global_source_override_requires_exactly_one_selected_model(self) -> None:
        catalogs = [
            ({"category": "production"}, [{"category": "production", "id": "p", "name": "prod-p"}]),
            ({"category": "task"}, [{"category": "task", "id": "t", "name": "task-t"}]),
        ]
        selected = [catalogs[0][1][0], catalogs[1][1][0]]
        for field, value in (("revision", "main"), ("sha256", "a" * 64)):
            args = modelctl.argparse.Namespace(
                command="refresh", quiet=False, revision=None, sha256=None
            )
            setattr(args, field, value)
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(modelctl.ModelError, "require one selected model"),
                patch.object(modelctl, "operate_models") as operate,
            ):
                modelctl.run_all_catalog_operation(catalogs, selected, args)
            operate.assert_not_called()

    def test_explicit_mtp_apply_can_select_packaged_disabled_candidate(self) -> None:
        defaults = {"category": "mtp", "destination": "/tmp/mtp", "download_namespace": "mtp"}
        model = {
            "category": "mtp", "id": "qwen3.6-27b-mtp", "provider": "download-only",
            "enabled": False, "index": 32,
        }
        with (
            patch.object(modelctl.os, "geteuid", return_value=0),
            patch.object(modelctl, "load_models", return_value=(defaults, [model])),
            patch.object(modelctl, "print_catalog_models"),
            patch.object(modelctl, "run_category_operation", return_value=0) as run,
        ):
            self.assertEqual(
                modelctl.main([
                    "apply", "mtp", "qwen3.6-27b-mtp", "--include-disabled"
                ]),
                0,
            )
        self.assertEqual(run.call_args.args[1], [model])

    def test_apply_all_switches_modes_around_agent_models(self) -> None:
        catalogs = [
            ({"category": "production"}, [{"category": "production", "id": "p", "name": "prod-p"}]),
            ({"category": "task"}, [{"category": "task", "id": "t", "name": "task-t"}]),
            ({"category": "embedding"}, [{"category": "embedding", "id": "e", "name": "embed-e"}]),
            ({"category": "agentic"}, [{"category": "agentic", "id": "a", "name": "agentic-a"}]),
            ({"category": "mtp"}, [{"category": "mtp", "id": "m", "name": "mtp-m"}]),
        ]
        selected = [model for _defaults, models in catalogs for model in models]
        args = modelctl.argparse.Namespace(command="apply", quiet=False)
        operations = []
        modes = []

        def operate(defaults, models, _args):
            operations.append(defaults["category"])
            return 0

        with (
            patch.object(modelctl, "set_appliance_mode", side_effect=modes.append),
            patch.object(modelctl, "operate_models", side_effect=operate),
        ):
            self.assertEqual(
                modelctl.run_all_catalog_operation(catalogs, selected, args), 0
            )

        self.assertEqual(modes, ["normal", "agent", "normal"])
        self.assertEqual(
            operations, ["production", "task", "embedding", "agentic", "mtp"]
        )

    def test_unregister_confirmation_happens_before_mode_switch(self) -> None:
        defaults = {
            "category": "agentic",
            "ollama_host": "127.0.0.1:11436",
            "destination": "/tmp",
        }
        model = {
            "category": "agentic",
            "id": "a",
            "name": "agent-a",
            "provider": "ollama",
            "from": "/tmp/a.gguf",
            "gguf": "a.gguf",
        }
        args = modelctl.argparse.Namespace(
            command="unregister", yes=False, host=None, destination=None
        )
        with (
            patch.object(modelctl, "prompt_line", return_value="n"),
            patch.object(modelctl, "set_appliance_mode") as mode,
        ):
            self.assertEqual(
                modelctl.run_category_operation(defaults, [model], args), 0
            )
        mode.assert_not_called()

    def test_remove_all_without_selection_does_not_implicitly_select_everything(self) -> None:
        catalogs = [
            (
                {"category": "production"},
                [{"category": "production", "id": "p", "name": "prod-p", "provider": "ollama"}],
            ),
            (
                {"category": "mtp"},
                [{"category": "mtp", "id": "m", "name": "mtp-m", "provider": "download-only", "enabled": False}],
            ),
        ]
        with (
            patch.object(modelctl.os, "geteuid", return_value=0),
            patch.object(modelctl, "load_all_catalogs", return_value=catalogs),
            patch.object(modelctl, "print_catalogs_basic"),
            patch.object(modelctl, "prompt_line", return_value=""),
            patch.object(modelctl, "run_all_catalog_operation") as run,
        ):
            self.assertEqual(modelctl.main(["remove", "all", "--yes"]), 0)
        run.assert_not_called()

    def test_all_remove_dispatches_each_selected_category(self) -> None:
        catalogs = [
            (
                {"category": "production"},
                [{"category": "production", "id": "p", "name": "prod-p"}],
            ),
            (
                {"category": "mtp"},
                [{"category": "mtp", "id": "m", "name": "mtp-m"}],
            ),
        ]
        selected = [catalogs[0][1][0], catalogs[1][1][0]]
        args = modelctl.argparse.Namespace(command="remove", yes=True, quiet=False)
        with (
            patch.object(modelctl, "set_appliance_mode"),
            patch.object(modelctl, "remove_models", return_value=0) as remove,
        ):
            self.assertEqual(
                modelctl.run_all_catalog_operation(catalogs, selected, args), 0
            )
        self.assertEqual(remove.call_count, 2)
        self.assertTrue(all(call.args[2].yes for call in remove.call_args_list))


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _defaults, cls.models = load("production")

    def test_selection_accepts_stable_ids_indices_and_ranges(self) -> None:
        first = self.models[0]
        self.assertEqual(modelctl.select_models(self.models, first["id"]), [first])
        self.assertEqual(
            modelctl.select_models(self.models, "0,2-3"),
            [self.models[0], *self.models[2:4]],
        )

    def test_all_selects_every_entry(self) -> None:
        self.assertEqual(modelctl.select_models(self.models, "all"), self.models)

    def test_named_selection_groups_are_global_and_explicit(self) -> None:
        catalogs = modelctl.load_all_catalogs(directories=[MODELFILES])
        models = [model for _defaults, group in catalogs for model in group if model.get("enabled", True)]
        production = modelctl.select_models(models, "production")
        recommended = modelctl.select_models(models, "recommended")
        self.assertTrue(production)
        self.assertTrue(all(model.get("category") == "production" for model in production))
        self.assertEqual({m["id"] for m in recommended}, modelctl.RECOMMENDED_MODELS)

    def test_catalog_indexes_are_global_and_selectable(self) -> None:
        all_models = modelctl.discover_models([MODELFILES])
        self.assertEqual(
            [model["index"] for model in all_models], list(range(len(all_models)))
        )
        _defaults, experiments = load("experiments")
        first_index = experiments[0]["index"]
        self.assertEqual(
            modelctl.select_models(experiments, str(first_index)), [experiments[0]]
        )

    def test_empty_and_invalid_selections_fail(self) -> None:
        for selection in ("", "999", "original-name"):
            with (
                self.subTest(selection=selection),
                self.assertRaises(modelctl.ModelError),
            ):
                modelctl.select_models(self.models, selection)


class StatusTests(unittest.TestCase):
    def test_compact_status_exposes_state_rich_picker_labels(self) -> None:
        model = {
            "id": "prod-test",
            "name": "prod-test",
            "category": "production",
            "provider": "ollama",
            "origin": "packaged",
            "index": 3,
        }
        inspection = modelctl.ModelInspection(
            model=model,
            source_path=Path("/tmp/model.gguf"),
            state_path=Path("/tmp/model.gguf.bc250.json"),
            source_status="current",
            source_detail="verified",
            source_checksum="a" * 64,
            runtime_modelfile=Path("/tmp/prod-test.Modelfile"),
            modelfile_status="current",
            registration_status="current",
            overall_status="CURRENT",
        )
        output = StringIO()
        with redirect_stdout(output):
            modelctl.print_model_inspection_compact(inspection)
        text = output.getvalue()
        self.assertIn("  3) prod-test", text)
        self.assertIn("[CURRENT]", text)
        self.assertNotIn("source verified", text)
        self.assertNotIn("Modelfile current", text)

    def test_compact_agent_status_marks_inactive_lane_as_deferred(self) -> None:
        model = {
            "id": "agent-test",
            "name": "agent-test",
            "category": "agentic",
            "provider": "ollama",
            "origin": "packaged",
            "index": 26,
        }
        inspection = modelctl.ModelInspection(
            model=model,
            source_path=Path("/tmp/agent.gguf"),
            state_path=Path("/tmp/agent.gguf.bc250.json"),
            source_status="current",
            source_detail="verified",
            source_checksum="c" * 64,
            runtime_modelfile=Path("/tmp/agent-test.Modelfile"),
            modelfile_status="current",
            registration_status="unavailable",
            overall_status="UNKNOWN",
        )
        details = modelctl.compact_inspection_details(inspection)
        self.assertEqual(details, ["agent lane inactive", "deferred"])

    def test_registration_probe_skips_known_inactive_agent_lane(self) -> None:
        with (
            patch.object(modelctl.shutil, "which", return_value="/usr/bin/ollama"),
            patch.object(modelctl, "systemd_unit_active", return_value=False),
            patch.object(modelctl.subprocess, "run") as run,
        ):
            self.assertIsNone(
                modelctl.registered_models(
                    modelctl.CATEGORY_DEFAULTS["agentic"]["ollama_host"]
                )
            )
        run.assert_not_called()

    def test_registration_probe_is_bounded_when_ollama_is_unresponsive(self) -> None:
        with (
            patch.object(modelctl.shutil, "which", return_value="/usr/bin/ollama"),
            patch.object(
                modelctl.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(["ollama", "list"], 5),
            ) as run,
        ):
            self.assertIsNone(modelctl.registered_models("127.0.0.1:11434"))
        self.assertEqual(run.call_args.kwargs["timeout"], modelctl.REGISTRATION_PROBE_TIMEOUT)

    def test_catalog_views_do_not_print_an_empty_mtp_heading(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            rc = modelctl.main(["list"])
        self.assertEqual(rc, 0)
        self.assertNotIn("MTP models:", output.getvalue())

        output = StringIO()
        with redirect_stdout(output):
            rc = modelctl.main(["list", "mtp"])
        self.assertEqual(rc, 0)
        self.assertIn("no enabled models; use --all", output.getvalue())

    def test_suppressed_catalog_environment_is_honored_for_mutations(self) -> None:
        defaults, models = load("production")
        selected = [models[0]]
        output = StringIO()
        with (
            patch.dict(os.environ, {"BC250_MODELCTL_SUPPRESS_CATALOG": "1"}),
            patch.object(modelctl.os, "geteuid", return_value=0),
            patch.object(modelctl, "load_models", return_value=(defaults, models)),
            patch.object(modelctl, "run_category_operation", return_value=0),
            redirect_stdout(output),
        ):
            rc = modelctl.main(["apply", "production", selected[0]["id"]])
        self.assertEqual(rc, 0)
        self.assertNotIn("Available production models", output.getvalue())

    def test_generic_all_apply_excludes_disabled_mtp_candidates(self) -> None:
        catalogs = modelctl.load_all_catalogs(directories=[MODELFILES])
        for include_disabled in (False, True):
            available = modelctl.all_available_models(
                catalogs, command="apply", include_disabled=include_disabled
            )
            self.assertFalse(any(model["category"] == "mtp" for model in available))
        self.assertTrue(
            any(model["id"] == "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl" for model in available)
        )

    def test_apply_summary_collapses_unchanged_models_without_hiding_changes(self) -> None:
        model = {
            "id": "exp-remote-test",
            "name": "exp-remote-test",
            "category": "experiments",
            "provider": "ollama-hf",
            "origin": "packaged",
            "from": "hf.co/example/test:Q4_K_M",
            "template": Path("/tmp/exp-remote-test.Modelfile"),
            "modelfile": "exp-remote-test.Modelfile",
            "revision": "latest",
            "repository": "example/test",
            "gguf": "test.gguf",
        }
        defaults = dict(modelctl.CATEGORY_DEFAULTS["experiments"], category="experiments")
        inspection = modelctl.ModelInspection(
            model=model,
            source_path=None,
            state_path=None,
            source_status="ollama-managed",
            source_detail="managed",
            source_checksum="",
            runtime_modelfile=Path("/tmp/exp-remote-test.Modelfile"),
            modelfile_status="current",
            registration_status="current",
            overall_status="CURRENT",
        )
        args = argparse.Namespace(
            command="apply", revision=None, sha256=None, host=None, destination=None,
            min_free_bytes=None, token_file=None, hf_session={"resolved": False, "token": ""},
        )
        output = StringIO()
        with (
            patch.dict(os.environ, {"BC250_MODELCTL_CURRENT_SUMMARY": "1"}),
            patch.object(modelctl.os, "geteuid", return_value=0),
            patch.object(modelctl, "ollama_identity", return_value=(0, 0)),
            patch.object(modelctl, "command_path", return_value="/bin/true"),
            patch.object(modelctl, "registered_models", return_value={model["name"]}),
            patch.object(modelctl, "ensure_directory"),
            patch.object(modelctl, "inspect_model_state", return_value=inspection),
            patch.object(modelctl, "write_runtime_modelfile", return_value=False),
            patch.object(modelctl.os, "chown"),
            patch.object(modelctl.os, "chmod"),
            redirect_stdout(output),
        ):
            rc = modelctl.apply_models(defaults, [model], args)
        self.assertEqual(rc, 0)
        text = output.getvalue()
        self.assertIn("Experiments: 1/1 current", text)
        self.assertNotIn(">>> exp-remote-test", text)
        self.assertNotIn("already current; skipping", text)
        self.assertNotIn("Done: 1 model(s) processed.", text)

    def test_verbose_status_explains_online_check_and_source_identity(self) -> None:
        model = {
            "id": "prod-test",
            "name": "prod-test",
            "category": "production",
            "provider": "ollama",
            "origin": "packaged",
            "repository": "example/repo",
            "revision": "latest",
        }
        inspection = modelctl.ModelInspection(
            model=model,
            source_path=Path("/tmp/model.gguf"),
            state_path=Path("/tmp/model.gguf.bc250.json"),
            source_status="current",
            source_detail="verified",
            source_checksum="b" * 64,
            runtime_modelfile=Path("/tmp/prod-test.Modelfile"),
            modelfile_status="current",
            registration_status="current",
            overall_status="CURRENT",
        )
        output = StringIO()
        with redirect_stdout(output):
            modelctl.print_model_inspection(inspection, verbose=True)
        text = output.getvalue()
        self.assertIn("Upstream:       not checked (use --online)", text)
        self.assertIn("Source repo:    example/repo", text)
        self.assertIn("Source revision: latest", text)
        self.assertIn(f"Source SHA-256: {'b' * 64}", text)

    def test_disabled_mtp_status_recommends_an_action_that_can_select_it(self) -> None:
        model = {
            "id": "qwen3.6-27b-mtp",
            "category": "mtp",
            "provider": "download-only",
            "enabled": False,
        }
        missing = modelctl.ModelInspection(
            model=model, source_path=None, state_path=None, source_status="missing",
            source_detail="not downloaded", source_checksum="", runtime_modelfile=None,
            modelfile_status="not applicable", registration_status="not applicable",
            overall_status="MISSING", remote_status="not checked", remote_detail="",
        )
        self.assertEqual(
            modelctl.recommended_status_action(missing),
            "sudo bc250-fetch-mtp qwen3.6-27b-mtp",
        )
        update = modelctl.ModelInspection(
            model=model, source_path=None, state_path=None, source_status="current",
            source_detail="verified", source_checksum="a" * 64, runtime_modelfile=None,
            modelfile_status="not applicable", registration_status="not applicable",
            overall_status="CURRENT", remote_status="update available", remote_detail="remote differs",
        )
        self.assertEqual(
            modelctl.recommended_status_action(update),
            "sudo bc250-model refresh mtp qwen3.6-27b-mtp --include-disabled",
        )

    def test_combined_status_handles_protected_sources_and_unmanaged_models(
        self,
    ) -> None:
        class ProtectedPath:
            def stat(self):
                raise PermissionError

        registrations = {
            "127.0.0.1:11434": {
                "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl",
                "unmanaged-test-model",
            },
            "127.0.0.1:11435": {"task-lfm25-1.2b-instruct-liquidai-q6-k"},
            "127.0.0.1:11436": {"prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl"},
            "127.0.0.1:11437": set(),
        }
        output = StringIO()
        with (
            patch.object(
                modelctl,
                "registered_models",
                side_effect=lambda host: registrations[host],
            ),
            patch.object(modelctl, "model_path", return_value=ProtectedPath()),
            redirect_stdout(output),
        ):
            modelctl.print_all_models([MODELFILES])

        text = output.getvalue()
        gemma = next(
            model
            for model in modelctl.discover_models([MODELFILES])
            if model["name"] == "exp-gemma4-12b-google-qat-q4-0"
        )
        self.assertIn(f"  {gemma['index']:2d}) exp-gemma4-12b-google-qat-q4-0", text)
        self.assertIn("downloaded, set up", text)
        self.assertIn("source Ollama-managed (main+projector), not set up", text)
        self.assertIn("unmanaged-test-model", text)
        self.assertIn("Modelfile missing", text)
        self.assertIn("Misplaced Ollama models", text)
        self.assertIn("prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl", text)
        self.assertIn("expected 127.0.0.1:11434", text)

    def test_ollama_hf_status_is_explicitly_managed(self) -> None:
        model = {
            "id": "m",
            "name": "exp-vision",
            "provider": "ollama-hf",
            "enabled": True,
        }
        output = StringIO()
        with redirect_stdout(output):
            modelctl.print_models({}, [model], registered=set())
        text = output.getvalue()
        self.assertIn("source Ollama-managed (main+projector), not set up", text)
        self.assertNotIn("download unknown", text)

    def test_unavailable_registration_status_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_path = Path(temporary) / "model.gguf"
            output_path.write_bytes(b"weights")
            model = {
                "id": "m",
                "name": "agentic-test",
                "provider": "ollama",
                "from": str(output_path),
                "gguf": output_path.name,
                "enabled": True,
            }
            output = StringIO()
            with (
                patch.object(modelctl, "model_path", return_value=output_path),
                redirect_stdout(output),
            ):
                modelctl.print_models(
                    {"destination": temporary}, [model], registered=None
                )
            text = output.getvalue()
            self.assertIn("downloaded, registration unavailable", text)
            self.assertNotIn("setup unknown", text)

    def test_retained_gguf_reports_downloaded_after_registration_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_path = Path(temporary) / "model.gguf"
            output_path.write_bytes(b"weights")
            modelctl.state_path(output_path).write_text("{}", encoding="utf-8")
            model = {
                "id": "m",
                "name": "prod-test",
                "provider": "ollama",
                "from": str(output_path),
                "gguf": output_path.name,
                "enabled": True,
            }
            output = StringIO()
            with (
                patch.object(modelctl, "model_path", return_value=output_path),
                redirect_stdout(output),
            ):
                modelctl.print_models(
                    {"destination": temporary}, [model], registered=set()
                )
            text = output.getvalue()
            self.assertIn("downloaded, not set up", text)
            self.assertNotIn("download unknown", text)


if __name__ == "__main__":
    unittest.main()
