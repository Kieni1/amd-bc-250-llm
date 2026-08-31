from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class PackagingTests(unittest.TestCase):
    def test_version_release_and_top_changelog_match(self) -> None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertRegex(spec, rf"(?m)^Version:\s+{re.escape(version)}$")
        release = re.search(r"(?m)^Release:\s+([^%\s]+)", spec)
        self.assertIsNotNone(release)
        self.assertRegex(
            spec,
            rf"(?m)^%changelog\n\* .* - {re.escape(version)}-{re.escape(release.group(1))}$",
        )

    def test_install_manifest_rejects_sources_outside_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            source_root.mkdir()
            outside = base / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            manifest = base / "manifest.tsv"
            manifest.write_text(
                "file\t0644\t../outside.txt\t/usr/share/test/outside.txt\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/install-manifest.py"),
                    "--manifest",
                    str(manifest),
                    "--source-root",
                    str(source_root),
                    "--check",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("source escapes source root", result.stderr)

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            source_root.mkdir()
            outside = base / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            link = source_root / "linked.txt"
            link.symlink_to(outside)
            manifest = base / "manifest.tsv"
            manifest.write_text(
                "file\t0644\tlinked.txt\t/usr/share/test/linked.txt\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/install-manifest.py"),
                    "--manifest",
                    str(manifest),
                    "--source-root",
                    str(source_root),
                    "--check",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("source must not be a symlink", result.stderr)

    def test_source_tarball_excludes_python_and_ruff_caches(self) -> None:
        source = (ROOT / "scripts/make-source-tarball.sh").read_text(encoding="utf-8")
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("--exclude='./.ruff_cache'", source)
        self.assertIn("--exclude='*/__pycache__'", source)
        self.assertIn("--exclude='*.pyc'", source)
        self.assertIn(".ruff_cache/", gitignore)

    def test_model_package_and_public_dispatcher_are_installed(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn("models/modelctl.py\t{libexec}/modelctl", manifest)
        self.assertIn("{config}/models.d", manifest)
        self.assertIn("models/modelfiles/*.Modelfile", manifest)
        self.assertNotIn("models/sources", manifest)
        self.assertIn("uninstall.sh\t{libexec}/uninstall.sh", manifest)
        self.assertIn("cmd/monitoring/status.sh\t{libexec}/status.sh", manifest)
        self.assertNotIn("bc250_model", manifest)
        result = subprocess.run(
            [str(ROOT / "packaging/bc250"), "--list-aliases"],
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        )
        self.assertIn("model", result.stdout.splitlines())
        self.assertIn("uninstall", result.stdout.splitlines())
        self.assertIn("status", result.stdout.splitlines())
        self.assertNotIn("fetch-embeddings", result.stdout.splitlines())
        self.assertIn("fetch-mtp", result.stdout.splitlines())
        self.assertIn("ocr", result.stdout.splitlines())
        self.assertIn("models/ocr/bc250-ocr.sh\t{libexec}/ocr.sh", manifest)
        for entry in (
            "cmd/benchmark/generation-benchmark.py\t{libexec}/generation-benchmark.py",
            "cmd/benchmark/category-benchmark.py\t{libexec}/category-benchmark.py",
            "cmd/benchmark/benchmark_common.py\t{libexec}/benchmark_common.py",
            "examples/benchmark/embedding-office.json\t{share}/benchmark/embedding-office.json",
            "examples/benchmark/agent-cases.json\t{share}/benchmark/agent-cases.json",
            "examples/benchmark/ocr/manifest.json\t{share}/benchmark/ocr/manifest.json",
            "MODEL.md\t{docdir}/MODEL.md",
        ):
            self.assertIn(entry, manifest)

    def test_embedding_uses_modelfile_discovery_and_recommended_open_webui_name(
        self,
    ) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("pull-embedding-model", dispatcher)
        self.assertNotIn("install-cu-manager", dispatcher)
        self.assertNotIn("log_sensors.sh", manifest)
        self.assertNotIn("fetch-embeddings|", dispatcher)
        self.assertIn("models/modelctl.py\t{libexec}/modelctl", manifest)
        self.assertIn(
            "Environment=RAG_EMBEDDING_MODEL=embed-jina-v5-small-retrieval-q4-k-m",
            quadlet,
        )
        self.assertIn("Environment=RAG_TEXT_SPLITTER=token", quadlet)
        self.assertIn("Environment=CHUNK_SIZE=1500", quadlet)
        self.assertIn("Environment=CHUNK_OVERLAP=200", quadlet)
        self.assertIn("Environment=RAG_TOP_K=8", quadlet)
        self.assertIn("Environment=ENABLE_RETRIEVAL_QUERY_GENERATION=false", quadlet)

    def test_package_standard_ollama_is_0332(self) -> None:
        helper = (ROOT / "cmd/system/install-ollama.sh").read_text(encoding="utf-8")
        installer = (ROOT / "install").read_text(encoding="utf-8")
        verify = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        self.assertIn('VERSION="${OLLAMA_VERSION:-$BC250_OLLAMA_VERSION}"', helper)
        self.assertIn('requested="${OLLAMA_VERSION:-$BC250_OLLAMA_VERSION}"', installer)
        self.assertIn("BC250_OLLAMA_VERSION=0.33.2", (ROOT / "config/runtime.env").read_text())
        self.assertIn("package standard $BC250_OLLAMA_VERSION", verify)

    def test_ollama_instances_are_local_only(self) -> None:
        main = (ROOT / "cmd/system/ollama.service.d-override.conf").read_text(encoding="utf-8")
        instances = (ROOT / "models/setup-ollama-instance.sh").read_text(encoding="utf-8")
        verify = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        self.assertIn('Environment="OLLAMA_NO_CLOUD=1"', main)
        self.assertIn('Environment="OLLAMA_NO_CLOUD=1"', instances)
        self.assertIn('OLLAMA_NO_CLOUD=1', verify)

    def test_open_webui_connection_config_is_valid_and_matches_packaged_roles(self) -> None:
        sys.path.insert(0, str(ROOT / "models"))
        import modelctl

        quadlet = (ROOT / "config/containers/open-webui.container").read_text(encoding="utf-8")
        line = next(
            line for line in quadlet.splitlines() if line.startswith('Environment="OLLAMA_API_CONFIGS=')
        )
        encoded = line.removeprefix('Environment="OLLAMA_API_CONFIGS=').removesuffix('"')
        api_configs = json.loads(encoded.replace('\\"', '"'))
        self.assertEqual(set(api_configs), {"0", "1", "2"})

        production = {f'{m["name"]}:latest' for m in modelctl.load_models("production", directories=[ROOT / "models/modelfiles"])[1]}
        task = {f'{m["name"]}:latest' for m in modelctl.load_models("task", directories=[ROOT / "models/modelfiles"])[1]}
        agentic = {f'{m["name"]}:latest' for m in modelctl.load_models("agentic", directories=[ROOT / "models/modelfiles"])[1]}
        self.assertTrue(api_configs["0"]["enable"])
        self.assertEqual(set(api_configs["0"]["model_ids"]), production)
        self.assertFalse(api_configs["1"]["enable"])
        self.assertEqual(set(api_configs["1"]["model_ids"]), task)
        self.assertFalse(api_configs["2"]["enable"])
        self.assertEqual(set(api_configs["2"]["model_ids"]), agentic)
        self.assertTrue(all("prefix_id" not in value for value in api_configs.values()))

    def test_fresh_install_governor_maximum_is_1850_mhz(self) -> None:
        config = (ROOT / "config/governor/config.toml").read_text(encoding="utf-8")
        self.assertRegex(
            config,
            r"(?ms)^\[frequency-range\]\s*$.*?^min = 350\s*$.*?^max = 1850\s*$",
        )

    def test_governor_v0412_pin_keeps_conservative_usage_defaults(self) -> None:
        commit = "be9537fc36f24b17570088cafa8c79365f80fee8"
        upstreams = (ROOT / "packaging/upstreams.toml").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        config = (ROOT / "config/governor/config.toml").read_text(encoding="utf-8")
        self.assertIn('version = "0.4.12"', upstreams)
        self.assertIn(f'commit = "{commit}"', upstreams)
        self.assertIn("%global governor_version 0.4.12", spec)
        self.assertIn(f"%global governor_commit {commit}", spec)
        self.assertRegex(
            config,
            r"(?ms)^\[gpu-usage\]\s*$.*?^fix-metrics = true\s*$.*?^fix-freq = false\s*$.*?^method = \"busy-flag\"",
        )

    def test_open_webui_v0112_is_digest_pinned(self) -> None:
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(
            encoding="utf-8"
        )
        self.assertIn("# v0.11.2, pinned OCI index digest.", quadlet)
        self.assertIn(
            "Image=ghcr.io/open-webui/open-webui@sha256:"
            "77ff490214a4b2699b309aa8d39bf4b42eca05f62d2742ef669ff846fcd10355",
            quadlet,
        )
        self.assertNotRegex(quadlet, r"(?m)^Image=.*:(?:latest|v0\.11\.2)$")

    def test_open_webui_fresh_install_privacy_features_are_disabled(self) -> None:
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(
            encoding="utf-8"
        )
        for setting in (
            "ENABLE_COMMUNITY_SHARING=false",
            "ENABLE_CODE_EXECUTION=false",
            "ENABLE_CODE_INTERPRETER=false",
            "ENABLE_MEMORIES=false",
        ):
            self.assertIn(f"Environment={setting}", quadlet)

    def test_open_webui_v0112_new_controls_stay_conservative(self) -> None:
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(
            encoding="utf-8"
        )
        self.assertIn('Environment="TASK_MODEL_PARAMS={}"', quadlet)
        self.assertIn("Environment=ENABLE_DIRECT_CONNECTIONS=false", quadlet)
        self.assertIn("Environment=ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS=false", quadlet)
        self.assertIn("Environment=RAG_FILE_MAX_SIZE=128", quadlet)
        self.assertIn("Environment=RAG_FILE_MAX_COUNT=20", quadlet)
        self.assertIn(
            "Environment=\"RAG_ALLOWED_FILE_EXTENSIONS=pdf,txt,md,csv,tsv,doc,docx,xls,xlsx,ppt,pptx,odt,ods,odp,rtf,html,htm,xml,json,epub\"",
            quadlet,
        )
        self.assertNotIn("RAG_ALLOWED_FILE_EXTENSIONS=.", quadlet)
        self.assertIn("OLLAMA_API_CONFIGS=", quadlet)
        self.assertIn("Environment=ENABLE_KNOWLEDGE_FILE_RETENTION=false", quadlet)
        self.assertIn("Environment=TIKA_SERVER_VERSION=3", quadlet)
        self.assertNotIn("Environment=ENABLE_ORJSON=true", quadlet)

    def test_compare_mtp_does_not_force_global_think_false(self) -> None:
        source = (ROOT / "models/experiments/compare-mtp.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("think:false", source)

    def test_ci_runs_on_push_and_pull_request_with_static_linters(self) -> None:
        workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(
            encoding="utf-8"
        )
        self.assertRegex(workflow, r"(?m)^  push:$")
        self.assertRegex(workflow, r"(?m)^  pull_request:$")
        self.assertIn("ruff check .", workflow)
        self.assertIn("shellcheck", workflow)
        self.assertIn("ruff rust ShellCheck", workflow)

    def test_build_outputs_share_one_dist_directory(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("dist/RPMS", makefile + workflow)
        self.assertNotIn("dist/SRPMS", makefile + workflow)
        self.assertIn("dist/*.x86_64.rpm", workflow)
        self.assertIn("dist/*.src.rpm", workflow)

    def test_progress_terminal_dependency_is_explicit(self) -> None:
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertIn("Requires:       util-linux-script", spec)

    def test_package_provides_its_own_ollama_account(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        sysusers = (ROOT / "packaging/bc250-llm-server.sysusers").read_text(
            encoding="utf-8"
        )
        self.assertIn("g      ollama -", sysusers)
        self.assertIn('u      ollama -  "Runs Ollama"', sysusers)
        self.assertIn(
            "packaging/bc250-llm-server.sysusers\t{sysusersdir}/bc250-llm-server.conf",
            manifest,
        )
        self.assertIn('--define "sysusersdir=%{_sysusersdir}"', spec)
        self.assertNotIn("Requires(pre):    shadow-utils", spec)
        self.assertNotRegex(spec, r"(?s)%pre\s+.*?useradd.*?%build")

    def test_config_noreplace_and_upgrade_restart_behavior_remain(self) -> None:
        installer = (ROOT / "scripts/install-manifest.py").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertIn('return f"%config(noreplace) {destination}"', installer)
        self.assertIn("systemctl try-restart tika.service open-webui.service", spec)
        self.assertNotIn("legacy migration", spec.lower())

    def test_40cu_helper_is_locally_integrated_and_initramfs_verified(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        helper = (ROOT / "cmd/system/40cu-module.sh").read_text(encoding="utf-8")
        self.assertIn(
            "cmd/system/40cu-module.sh\t{libexec}/40cu/bc250-enable-40cu-fedora.sh",
            manifest,
        )
        self.assertNotIn("patches/40cu-fedora-helper.patch", spec)
        self.assertIn("/var/cache/bc250-llm-server/40cu", helper)
        self.assertIn('lsinitrd -k "$KVER" -f "$relative"', helper)
        self.assertIn("Running driver:", helper)
        self.assertIn("signature_enforcement_active", helper)
        self.assertIn('metadata="$(modinfo "$1" 2>/dev/null)"', helper)
        self.assertIn("prepared_module_ready()", helper)
        self.assertIn('if ! prepared_module_ready "$target"; then', helper)
        self.assertNotIn("do_enable() {\n  do_prepare", helper)

    def test_gfx1013_compute_patch_stack_is_not_bundled(self) -> None:
        upstreams = (ROOT / "packaging/upstreams.toml").read_text(encoding="utf-8")
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertNotIn("bc250-gfx1013", upstreams + manifest)
        self.assertNotRegex(spec, r"(?m)^Source[0-9]+:.*gfx1013")

    def test_runtime_pins_match_container_and_ollama_helpers(self) -> None:
        values = {}
        for line in (ROOT / "config/runtime.env").read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                values[key] = value
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(encoding="utf-8")
        tika = (ROOT / "config/containers/tika.container").read_text(encoding="utf-8")
        self.assertEqual(values["BC250_OLLAMA_VERSION"], "0.33.2")
        self.assertEqual(values["BC250_OPEN_WEBUI_VERSION"], "0.11.2")
        self.assertEqual(values["BC250_OPEN_WEBUI_TASK_CONTRACT"], "0.11.2")
        self.assertIn(f'# v{values["BC250_OPEN_WEBUI_VERSION"]}, pinned OCI index digest.', quadlet)
        self.assertIn(values["BC250_OPEN_WEBUI_IMAGE_DIGEST"], quadlet)
        self.assertIn(values["BC250_TIKA_VERSION"], tika)
        self.assertIn(values["BC250_TIKA_IMAGE_DIGEST"], tika)
        self.assertIn("config/runtime.env\t{share}/runtime.env", (ROOT / "packaging/install-manifest.tsv").read_text())

    def test_fresh_machine_memory_profile_keeps_required_bc250_arguments(self) -> None:
        profile = (ROOT / "cmd/system/memory-profile.sh").read_text(encoding="utf-8")
        installer = (ROOT / "install").read_text(encoding="utf-8")
        for token in (
            "amdgpu.gttsize=14750", "ttm.pages_limit=4194304",
            "ttm.page_pool_size=4194304", "amdgpu.ppfeaturemask=0xffffffff",
        ):
            self.assertIn(token, profile)
            self.assertIn(token, installer)
        self.assertIn("mapfile -t kernel_args", installer)
        self.assertNotIn("apply-safe", profile)


if __name__ == "__main__":
    unittest.main()
