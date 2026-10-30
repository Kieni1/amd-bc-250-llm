from __future__ import annotations

import glob
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED_DOC_TREES = {
    ".git",
    "build",
    "dist",
    "rpmbuild",
    "sources",
    "governor-src",
    "live-manager-src",
    "__pycache__",
}
NON_PACKAGE_DOC_TREES = {"development"}


def package_markdown_paths():
    for path in ROOT.rglob("*.md"):
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_DOC_TREES for part in relative.parts):
            continue
        if any(part in NON_PACKAGE_DOC_TREES for part in relative.parts):
            continue
        yield path, relative



def current_identity() -> tuple[str, str, str]:
    contract = json.loads((ROOT / "release-contract.json").read_text(encoding="utf-8"))
    version = contract["package"]["version"]
    release = contract["package"]["rpm_release"]
    return version, release, f"{contract['package']['name']}-{version}-{release}"


def dispatcher_routes() -> set[str]:
    source = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
    return set(re.findall(r'^  "([a-z0-9-]+)\|', source, re.MULTILINE))


class DocumentationTests(unittest.TestCase):
    def test_clean_core_current_guidance_and_absence_gates_pass(self) -> None:
        scripts = (
            ROOT / "scripts/check-clean-core-absence.sh",
            ROOT / "scripts/check-current-guidance.sh",
            ROOT / "development/handovers/scripts/validate-handovers.sh",
        )
        for script in scripts:
            result = subprocess.run(
                [str(script), str(ROOT)] if script.parent.name == "scripts" and script.parent.parent == ROOT else [str(script)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_current_guidance_gate_rejects_release_continuity_regressions(self) -> None:
        _version, _release, nvr = current_identity()
        cases = {
            "release identity drifts": (
                "development/VALIDATION-MATRIX.md",
                nvr,
                nvr + "-drift",
            ),
            "test retention rule disappears": (
                "development/TESTING-STRATEGY.md",
                "Do not delete tests merely to make fast-moving development quieter.",
                "Delete tests merely to make fast-moving development quieter.",
            ),
            "development memory becomes release authority": (
                "development/README.md",
                "do not need to be rewritten for every RPM release",
                "must be rewritten for every RPM release",
            ),
            "ownership boundary disappears": (
                "development/OWNERSHIP.md",
                "Public product concepts are intentionally fewer",
                "Every implementation owner is a public product concept",
            ),
            "workbench NVR drifts": (
                "WORKBENCH-STATE.json",
                f'"nvr": "{nvr}"',
                f'"nvr": "{nvr}-drift"',
            ),
        }
        for label, (relative, old, new_value) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                fixture = Path(tmp)
                shutil.copytree(ROOT / "development", fixture / "development")
                shutil.copytree(ROOT / "packaging", fixture / "packaging")
                shutil.copytree(ROOT / "scripts", fixture / "scripts")
                shutil.copy2(ROOT / "Makefile", fixture / "Makefile")
                shutil.copy2(ROOT / "TLDR.md", fixture / "TLDR.md")
                for source in ("VERSION", "release-contract.json", "WORKBENCH-STATE.json"):
                    shutil.copy2(ROOT / source, fixture / source)
                target = fixture / relative
                current = target.read_text(encoding="utf-8")
                self.assertIn(old, current)
                target.write_text(current.replace(old, new_value), encoding="utf-8")
                result = subprocess.run(
                    [str(ROOT / "scripts/check-current-guidance.sh"), str(fixture)],
                    text=True, capture_output=True, check=False,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_current_document_guidance_uses_package_owned_preset_and_current_terms(self) -> None:
        rag = (ROOT / "docs/RAG.md").read_text(encoding="utf-8")
        models = (ROOT / "MODELS.md").read_text(encoding="utf-8")
        openwebui = (ROOT / "docs/OPENWEBUI.md").read_text(encoding="utf-8")
        scope = (ROOT / "development/DEVELOPMENT-SCOPE.json").read_text(encoding="utf-8")

        self.assertIn("Office - Documents / RAG", rag)
        self.assertIn("managed document workflow", rag)
        self.assertNotIn("Office Documents – Pilot", rag)
        self.assertNotIn("v0.12.3 candidate", rag)
        self.assertNotIn("Builtin Tools disabled for this first baseline", rag)
        self.assertNotIn("Graveyard Modelfiles", models)
        self.assertNotIn("remains only in the retired as historical", openwebui)
        self.assertNotIn("0.14.1-1.7 release line", scope)

    def test_current_operator_reference_is_gfx_free(self) -> None:
        operations = (ROOT / "docs/OPERATIONS.md").read_text(encoding="utf-8")
        self.assertNotIn("GFX", operations)
        self.assertIn("Exact installed package/runtime identity", operations)

    def test_command_reference_covers_every_public_dispatcher_route(self) -> None:
        reference = (ROOT / "docs/OPERATIONS.md").read_text(encoding="utf-8")
        for route in sorted(dispatcher_routes()):
            self.assertIn(f"`bc250 {route}`", reference, route)
        for command in ("`bc250`", "`bc250-cu-live-manager`", "`bc250-40cu`", "`bc250 advanced benchmark parity`"):
            self.assertIn(command, reference)

    def test_shell_examples_do_not_invent_bc250_commands(self) -> None:
        # The only deliberately standalone bc250-* commands are the CU tools.
        allowed = {"cu-live-manager", "40cu", "llm-server", "documents", "night-shutdown", "wol", "coding-agent"}
        for path, relative in package_markdown_paths():
            text = path.read_text(encoding="utf-8")
            blocks = re.findall(r"```(?:bash|text)?\n(.*?)```", text, re.DOTALL)
            for block in blocks:
                for suffix in re.findall(r"\bbc250-([a-z0-9-]+)\b", block):
                    self.assertIn(suffix, allowed, f"{relative}: bc250-{suffix}")

    def test_privileged_command_examples_use_sudo(self) -> None:
        privileged = (
            r"bc250\s+(?:install|maintenance|storage|document|reset)(?:\s|$)",
            r"bc250\s+ocr\s+install(?:\s|$)",
            r"bc250\s+advanced\s+openwebui\s+(?:init|apply|save-key)(?:\s|$)",
            r"bc250\s+advanced\s+agent\s+(?:enter|leave|normal|prepare)(?:\s|$)",
            r"bc250\s+model\s+(?:status|install|apply|refresh|unregister|remove|purge-retired)(?:\s|$)",
            r"bc250\s+advanced\s+ollama-profile\s+(?:balanced|max-context|reset)(?:\s|$)",
            r"bc250\s+advanced\s+benchmark\s+owui-system-context(?:\s|$)",
            r"bc250-40cu(?:\s|$)",
            r"bc250-cu-live-manager(?:\s|$)",
        )
        for path, relative in package_markdown_paths():
            text = path.read_text(encoding="utf-8")
            for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
                for line in block.splitlines():
                    command = line.strip()
                    if not command or command.startswith("#"):
                        continue
                    for pattern in privileged:
                        if re.search(pattern, command):
                            # Provider-aware removal explanation is deliberately read-only and rootless.
                            if re.search(r"\bbc250\s+model\s+remove\b", command) and "--explain" in command:
                                continue
                            self.assertRegex(command, r"(?:^|\s)sudo(?:\s|$)", f"{relative}: {command}")

    def test_current_docs_use_supported_model_rag_and_storage_subcommands(self) -> None:
        allowed = {
            "model": {"list", "status", "inspect", "path", "install", "apply", "refresh", "unregister", "remove", "purge-retired"},
            "document": {"init", "prepare-batch", "review", "validate", "activate", "supersede", "status", "ingest"},
            "storage": {"status", "dedupe", "prune-sources"},
        }
        patterns = {
            family: re.compile(rf"\bbc250\s+{family}\s+([a-z0-9-]+)\b")
            for family in allowed
        }
        for path, relative in package_markdown_paths():
            text = path.read_text(encoding="utf-8")
            for family, pattern in patterns.items():
                for command in pattern.findall(text):
                    self.assertIn(command, allowed[family], f"{relative}: bc250 {family} {command}")

    def test_ocr_guidance_preserves_managed_document_lifecycle(self) -> None:
        rag = (ROOT / "docs/RAG.md").read_text(encoding="utf-8")
        self.assertIn("Managed text-native PDF", rag)
        self.assertIn("bc250 document prepare-batch", rag)
        self.assertIn("proper managed working draft with source provenance", rag)
        self.assertIn("Never write raw", rag)
        self.assertIn("directly to `active/`", rag)
        self.assertNotIn("Use Tika for text-native PDFs and office files", rag)
        self.assertNotIn("save the\ncleaned canonical Markdown under `active/`", rag)
        self.assertNotIn("For the pilot", rag)

    def test_activate_help_does_not_overclaim_crash_atomicity(self) -> None:
        lifecycle = (ROOT / "cmd/documents/lifecycle.py").read_text(encoding="utf-8")
        self.assertIn("transactionally promote a validated batch", lifecycle)
        self.assertNotIn("atomically promote reviewed working Markdown", lifecycle)

    def test_revalidate_reference_covers_public_lifecycle(self) -> None:
        reference = (ROOT / "docs/OPERATIONS.md").read_text(encoding="utf-8")
        for form in (
            "sudo bc250 advanced revalidate start",
            "sudo bc250 advanced revalidate start --skip-owui",
            "sudo bc250 advanced revalidate status",
            "sudo bc250 advanced revalidate status --raw",
            "sudo bc250 advanced revalidate abort",
            "sudo bc250 advanced revalidate cleanup",
        ):
            self.assertIn(form, reference)

    def test_read_only_profile_examples_do_not_require_sudo(self) -> None:
        forbidden = (
            "sudo bc250 advanced ollama-profile status",
        )
        for path, relative in package_markdown_paths():
            text = path.read_text(encoding="utf-8")
            for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
                for command in forbidden:
                    self.assertNotIn(command, block, f"{relative}: {command}")


    def test_model_manager_current_docs_use_canonical_lifecycle_contract(self) -> None:
        current_docs = (
            "README.md",
            "MODELS.md",
            "TLDR.md",
            "docs/OPERATIONS.md",
            "docs/RAG.md",
            "models/README.md",
            "models/coding-agent/README.md",
            "models/embedding/README.md",
            "models/experiments/README.md",
            "models/mtp/README.md",
            "models/task-model/README.md",
        )
        required = ("bc250 model list", "bc250 model status", "bc250 model apply")
        corpus = "\n".join((ROOT / relative).read_text(encoding="utf-8") for relative in current_docs)
        for command in required:
            self.assertIn(command, corpus)

    def test_model_manager_read_only_examples_do_not_require_sudo(self) -> None:
        current_docs = (
            "README.md",
            "MODELS.md",
            "TLDR.md",
            "docs/OPERATIONS.md",
            "docs/OPERATIONS.md",
            "docs/RAG.md",
            "models/README.md",
            "models/coding-agent/README.md",
            "models/embedding/README.md",
            "models/experiments/README.md",
            "models/mtp/README.md",
            "models/task-model/README.md",
        )
        forbidden = (
            "sudo bc250 model list",
            "sudo bc250 model path",
        )
        for relative in current_docs:
            text = (ROOT / relative).read_text(encoding="utf-8")
            for command in forbidden:
                self.assertNotIn(command, text, f"{relative}: {command}")


    def test_secondary_model_docs_expose_explicit_mtp_opt_in(self) -> None:
        for relative in ("README.md", "TLDR.md", "MODELS.md", "models/README.md", "models/mtp/README.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("bc250 advanced mtp list", text, relative)
            self.assertIn("bc250 advanced mtp prepare", text, relative)

    def test_mtp_command_reference_matches_same_target_contract(self) -> None:
        reference = (ROOT / "docs/OPERATIONS.md").read_text(encoding="utf-8")
        self.assertIn("controlled same-target qualification helper", reference)
        self.assertIn("draft accepted/proposed counts", reference)
        self.assertNotIn("The quick MTP comparison accepts `BASELINE_MODEL`", reference)
        self.assertNotIn("speed-oriented Ollama-vs-llama.cpp helper", reference)

    def test_current_docs_keep_mtp_explicit_while_unifying_installer_overview(self) -> None:
        commands = (ROOT / "docs/OPERATIONS.md").read_text(encoding="utf-8")
        models = (ROOT / "models/README.md").read_text(encoding="utf-8")
        for text in (commands, models):
            self.assertIn("apply all", text)
            self.assertIn("MTP", text)
            self.assertIn("explicit", text)
        self.assertIn("same global indexed", commands)
        self.assertIn("broad `all`, `recommended` and `production` groups exclude MTP", models)
        self.assertIn("combined `apply all` / `refresh all`", models)
        self.assertNotIn("MTP is deliberately absent from that picker", models)

    def test_current_docs_preserve_optional_setup_and_diagnostic_contracts(self) -> None:
        maintenance = (ROOT / "docs/OPERATIONS.md").read_text(encoding="utf-8")
        commands = (ROOT / "docs/OPERATIONS.md").read_text(encoding="utf-8")
        quality = (ROOT / "docs/QUALITY-CHECKS.md").read_text(encoding="utf-8")

        self.assertIn("separate optional decisions", maintenance)
        self.assertIn("Pi/companion integration", maintenance)
        self.assertIn("default-No", maintenance)
        self.assertIn("configured independently", maintenance)
        self.assertIn("Selected setup is verified", maintenance)

        self.assertIn("Both top-level choices remain optional/default-No", commands)
        self.assertIn("512 MiB", commands)
        self.assertIn("128 MiB hard", commands)
        self.assertIn("generation output budget", commands)
        self.assertIn("/usr/share/doc/bc250-llm-server/", commands)

        self.assertIn("512 MiB", commands)
        self.assertIn("128 MiB", commands)
        self.assertIn("output budget", commands)
        self.assertIn("Model-quality findings", quality)

    def test_current_model_docs_distinguish_retired_qwen_distill(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        ollama = (ROOT / "docs/OLLAMA.md").read_text(encoding="utf-8")
        experiments = (ROOT / "models/experiments/README.md").read_text(encoding="utf-8")
        for text in (readme, ollama, experiments):
            self.assertIn("exp-qwen38-4b-distill-empero-q6-k", text)
            self.assertIn("exp-qwen38-4b-empero-q6-k", text)
        self.assertNotIn("Qwen3.8 therefore remains an opt-in experiment", ollama)
        self.assertNotIn("intentional in 0.10", experiments)

    def test_current_vs_historical_guidance_boundary(self) -> None:
        handovers = (ROOT / "development/handovers/00_README_START_HERE.md").read_text(encoding="utf-8")
        self.assertIn("retained engineering memory", handovers)
        self.assertIn("not current release authority", handovers)
        self.assertIn("WORKBENCH-STATE.json", handovers)

        active = []
        for path in sorted((ROOT / "development/handovers").glob("*.md")):
            active.append(path.read_text(encoding="utf-8"))
        joined = "\n".join(active)
        self.assertNotRegex(joined, r"\bC[0-9]+(?:[A-Z-]|\b)")
        self.assertNotIn("0.13.1-1.9", joined)

        validation = (ROOT / "development/VALIDATION-MATRIX.md").read_text(encoding="utf-8")
        _version, _release, nvr = current_identity()
        self.assertIn(f"Current release identity: `{nvr}`", validation)
        self.assertIn("Exact-RPM core functionality", validation)

        strategy = (ROOT / "development/TESTING-STRATEGY.md").read_text(encoding="utf-8")
        self.assertIn("Keep every existing `tests/test_*.py` module", strategy)
        self.assertIn("full suite is advisory", strategy)

    def test_workbench_records_current_release_without_reconstruction_checkpoints(self) -> None:
        workbench = json.loads((ROOT / "WORKBENCH-STATE.json").read_text(encoding="utf-8"))
        self.assertEqual(workbench["schema"], 2)
        self.assertEqual(workbench["kind"], "release-workbench")
        _version, _release, nvr = current_identity()
        self.assertEqual(workbench["release"]["nvr"], nvr)
        self.assertEqual(workbench["release"]["state"], "1.11-source-release-candidate-unbuilt")
        self.assertNotIn("checkpoint", workbench)
        self.assertIn("Batch ", workbench["next_work"]["current_batch"])
        self.assertIn("complete", workbench["next_work"]["current_batch"].casefold())
        self.assertTrue(workbench["next_work"]["next_batch"].strip())
        self.assertIn("current SOURCE release candidate", workbench["long_term"]["direction"])
        self.assertIn("Exact 0.14.1-1.10 RPM", workbench["validation"]["device_acceptance"])
        rpm_check = workbench["validation"]["rpm_package_check"]
        self.assertIn("0.14.1-1.11", rpm_check)
        self.assertIn("No", rpm_check)
        self.assertIn("built yet", rpm_check)
        self.assertEqual(workbench["build_authority"]["selection_event"], "workflow_dispatch")

    def test_ollama_docs_match_effective_vulkan_environment_contract(self) -> None:
        ollama = (ROOT / "docs/OLLAMA.md").read_text(encoding="utf-8")
        _version, release, _nvr = current_identity()
        self.assertIn("Package standard: **Ollama v0.40.8**", ollama)
        self.assertIn(f"release {release}", ollama)
        self.assertIn("runtime pin unchanged", ollama)
        self.assertIn("0.40.8 keeps the established four-lane settings", ollama)
        self.assertIn("does not transfer DEVICE acceptance", ollama)
        self.assertNotIn("0.34.4 remains the last exact-device-qualified runtime", ollama)
        self.assertNotIn("0.13.1-1.2", ollama)
        for assignment in ("OLLAMA_VULKAN=1", "OLLAMA_IGPU_ENABLE=1", "GGML_VK_VISIBLE_DEVICES=0"):
            self.assertIn(assignment, ollama)

    def test_release_guidance_matches_blocking_gate_and_product_roadmap(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("Run blocking Ruff and ShellCheck release preflight", makefile)
        self.assertNotIn("developer quality; not release-blocking", makefile)

        scope = json.loads((ROOT / "development/DEVELOPMENT-SCOPE.json").read_text(encoding="utf-8"))
        note = scope["policy"]["full_release_gate"]["note"]
        for required in ("Ruff", "ShellCheck", "configured rpmlint", "blocking"):
            self.assertIn(required, note)
        for name, component in scope["components"].items():
            if component["status"] in {"active", "boundary_active"}:
                self.assertTrue(
                    component.get("focused_tests") or component.get("focused_tests_reason"),
                    f"{name} has no focused-test mapping or explicit reason",
                )

        matrix = (ROOT / "development/VALIDATION-MATRIX.md").read_text(encoding="utf-8")
        for required in (
            "Ruff or ShellCheck failure",
            "configured rpmlint failure",
            "current operator/release guidance contract drift",
            "development-scope consistency failure",
        ):
            self.assertIn(required, matrix)
        self.assertNotIn("Do not stop artifact production solely for:\n\n- documentation wording drift", matrix)

        roadmap = (ROOT / "development/handovers/16_PRODUCT_GOAL_AND_ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("bounded cleanup only where it removes real ownership/risk", roadmap)
        self.assertIn("RAG/document workflow quality", roadmap)
        self.assertIn("German ↔ French", roadmap)
        working = (ROOT / "development/handovers/10_WORKING_METHOD_AND_EVIDENCE.md").read_text(encoding="utf-8")
        self.assertNotIn("simplification has priority over feature accumulation", working)
        self.assertFalse((ROOT / "development/handovers/SHA256SUMS.txt").exists())

    def test_active_handover_names_are_release_oriented(self) -> None:
        handovers = ROOT / "development/handovers"
        names = {path.name for path in handovers.glob("*.md")}
        self.assertIn("00_README_START_HERE.md", names)
        self.assertIn("01_CURRENT_STATE_AND_NEXT_WORK.md", names)
        self.assertIn("11_LONG_TERM_ENGINEERING_GUIDELINES.md", names)
        for name in names:
            self.assertNotRegex(name, r"0\.1[23]\.")
            self.assertNotIn("CLEAN_CORE_RECONSTRUCTION", name)
            self.assertNotIn("DONOR_DELTA", name)

    def test_installed_document_layout_preserves_source_paths_and_links(self) -> None:
        manifest = ROOT / "packaging/install-manifest.tsv"
        entries = []
        for raw in manifest.read_text(encoding="utf-8").splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            kind, _mode, source, destination = raw.split("\t")
            if kind != "file" or not destination.startswith("{docdir}"):
                continue
            matches = [Path(item) for item in sorted(glob.glob(str(ROOT / source)))]
            self.assertTrue(matches, source)
            for source_path in matches:
                installed_rel = destination.removeprefix("{docdir}").lstrip("/")
                if destination.endswith("/"):
                    installed_rel = f"{installed_rel.rstrip('/')}/{source_path.name}"
                entries.append((source_path, Path(installed_rel)))
                if source_path.suffix == ".md":
                    self.assertEqual(
                        installed_rel,
                        source_path.relative_to(ROOT).as_posix(),
                        f"documentation path rewrite: {source_path.relative_to(ROOT)}",
                    )

        with tempfile.TemporaryDirectory() as temporary:
            staged = Path(temporary)
            for source_path, installed_rel in entries:
                target = staged / installed_rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target)
            for path in staged.rglob("*.md"):
                text = path.read_text(encoding="utf-8")
                for target in re.findall(r"\[[^]]*\]\(([^)]+)\)", text):
                    if target.startswith(("http://", "https://", "mailto:", "#")):
                        continue
                    local = target.split("#", 1)[0]
                    if local:
                        self.assertTrue(
                            (path.parent / local).exists(),
                            f"installed {path.relative_to(staged)}: {target}",
                        )

    def test_documented_model_sets_match_current_modelfiles(self) -> None:
        names = set()
        for path in (ROOT / "models/modelfiles").glob("*.Modelfile"):
            match = re.search(
                r"(?m)^# Ollama model:\s*(\S+)\s*$",
                path.read_text(encoding="utf-8"),
            )
            self.assertIsNotNone(match, path.name)
            names.add(match.group(1))

        models_doc = (ROOT / "MODELS.md").read_text(encoding="utf-8")
        catalog = re.search(
            r"<!-- ACTIVE_EXPERIMENTS:BEGIN -->\n```text\n(.*?)\n```\n<!-- ACTIVE_EXPERIMENTS:END -->",
            models_doc,
            re.DOTALL,
        )
        self.assertIsNotNone(catalog)
        documented_experiments = {
            line.strip() for line in catalog.group(1).splitlines() if line.strip()
        }
        actual_experiments = {name for name in names if name.startswith("exp-")}
        self.assertEqual(documented_experiments, actual_experiments)

        recommended = (
            "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl",
            "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl",
            "prod-translate-gemma4-sub-e4b-17s-q4-k-xl",
            "prod-gpt-oss20b-ggml-org-mxfp4",
            "embed-jina-v5-small-retrieval-q4-k-m",
            "task-lfm25-1.2b-instruct-liquidai-q6-k",
            "agentic-ornith15-9b-ornith-q5-k-m",
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for name in recommended:
            self.assertIn(name, names)
            self.assertIn(name, readme)

    def test_openwebui_api_compatibility_boundary_is_explicit(self) -> None:
        settings = (ROOT / "docs/OPENWEBUI.md").read_text(encoding="utf-8")
        commands = (ROOT / "docs/OPERATIONS.md").read_text(encoding="utf-8")
        benchmark = (ROOT / "docs/BENCHMARKING.md").read_text(encoding="utf-8")
        for text in (settings, commands):
            self.assertIn("/api/chat/completions", text)
            self.assertIn("options.num_predict", text)
        self.assertIn("root `max_tokens`", benchmark)
        self.assertIn("options.num_predict", benchmark)
        self.assertIn("reasoning_tokens", settings)
        self.assertIn("finish_reason=stop", settings)
        self.assertIn("advertised external BC-250 API", settings)


    def test_agent_validation_scope_is_explicit_in_current_guidance(self) -> None:
        benchmarking = (ROOT / "docs/BENCHMARKING.md").read_text(encoding="utf-8")
        models = (ROOT / "MODELS.md").read_text(encoding="utf-8")
        self.assertIn("agent_validation=static-output-contract", benchmarking)
        self.assertIn("does not exercise/qualify native Ollama `tool_calls`", benchmarking)
        self.assertIn("agent_validation=static-output-contract", models)

    def test_development_scope_ignores_python_bytecode_in_frozen_trees(self) -> None:
        cache_dir = ROOT / "cmd/documents/__pycache__"
        cache_dir.mkdir(exist_ok=True)
        probe = cache_dir / "scope-test-probe.pyc"
        probe.write_bytes(b"generated-bytecode-probe")
        try:
            completed = subprocess.run(
                [sys.executable, str(ROOT / "development/scope.py"), "check", "--quiet"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        finally:
            probe.unlink(missing_ok=True)
            try:
                cache_dir.rmdir()
            except OSError:
                pass

if __name__ == "__main__":
    unittest.main()
