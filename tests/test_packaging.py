from __future__ import annotations

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
            "examples/benchmark/usecase-office.json\t{share}/benchmark/usecase-office.json",
            "examples/benchmark/translation-office.json\t{share}/benchmark/translation-office.json",
            "examples/benchmark/rag-cycle.json\t{share}/benchmark/rag-cycle.json",
            "examples/benchmark/rag-quality-office.json\t{share}/benchmark/rag-quality-office.json",
            "examples/benchmark/ocr/manifest.json\t{share}/benchmark/ocr/manifest.json",
            "MODELS.md\t{docdir}/MODELS.md",
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
        self.assertIn("Environment=ENABLE_TITLE_GENERATION=true", quadlet)
        self.assertIn("Environment=ENABLE_TAGS_GENERATION=true", quadlet)
        self.assertIn("Environment=ENABLE_FOLLOW_UP_GENERATION=false", quadlet)
        self.assertIn("Environment=ENABLE_AUTOCOMPLETE_GENERATION=false", quadlet)
        self.assertIn("Environment=ENABLE_SEARCH_QUERY_GENERATION=false", quadlet)

    def test_rpm_post_is_small_and_defers_provisioning(self) -> None:
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        post = spec[spec.index("%post\n"):spec.index("%preun")]
        self.assertIn("%tmpfiles_create", post)
        self.assertIn("WEBUI_SECRET_KEY", post)
        self.assertIn("sudo bc250-install", post)
        for forbidden in ("firewall-cmd", "setsebool", "dnf ", "bc250-model", "systemctl enable --now"):
            self.assertNotIn(forbidden, post)

    def test_package_standard_ollama_is_0332(self) -> None:
        helper = (ROOT / "cmd/system/install-ollama.sh").read_text(encoding="utf-8")
        installer = (ROOT / "cmd/system/install.sh").read_text(encoding="utf-8")
        verify = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        self.assertIn('VERSION="${OLLAMA_VERSION:-$BC250_OLLAMA_VERSION}"', helper)
        self.assertIn('requested="${OLLAMA_VERSION:-$BC250_OLLAMA_VERSION}"', installer)
        self.assertIn("BC250_OLLAMA_VERSION=0.33.2", (ROOT / "config/runtime.env").read_text())
        self.assertIn("package standard $BC250_OLLAMA_VERSION", verify)

    def test_ollama_topology_is_statically_packaged_and_local_only(self) -> None:
        units = {
            name: (ROOT / f"config/systemd/{name}").read_text(encoding="utf-8")
            for name in ("ollama.service", "ollama-task.service", "ollama-embedding.service", "ollama-agent.service")
        }
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        preset = (ROOT / "packaging/90-bc250-llm-server.preset").read_text(encoding="utf-8")
        for name, unit in units.items():
            self.assertIn('Environment="OLLAMA_NO_CLOUD=1"', unit)
            self.assertIn("/usr/local/bin/ollama serve", unit)
            self.assertIn(name, manifest)
        for name in ("ollama.service", "ollama-task.service", "ollama-embedding.service"):
            self.assertIn("Conflicts=ollama-agent.service", units[name])
        self.assertIn("Conflicts=ollama.service ollama-task.service ollama-embedding.service", units["ollama-agent.service"])
        self.assertNotIn("[Install]", units["ollama-agent.service"])
        self.assertIn("disable ollama.service", preset)
        self.assertFalse((ROOT / "cmd/system/ollama.service.d-override.conf").exists())
        self.assertFalse((ROOT / "models/setup-ollama-instance.sh").exists())

    def test_open_webui_boot_enablement_is_deferred_to_installer(self) -> None:
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(encoding="utf-8")
        enable = (ROOT / "config/openwebui/open-webui-enable.conf").read_text(encoding="utf-8")
        installer = (ROOT / "cmd/system/install.sh").read_text(encoding="utf-8")
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertNotIn("[Install]", quadlet)
        self.assertIn("[Install]", enable)
        self.assertIn("WantedBy=multi-user.target", enable)
        self.assertIn("enable_open_webui_boot", installer)
        self.assertIn("open-webui-enable.conf", manifest)

    def test_open_webui_signing_secret_persists_across_container_recreation(self) -> None:
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(encoding="utf-8")
        tmpfiles = (ROOT / "packaging/bc250-llm-server.tmpfiles").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        path = "/var/lib/bc250-llm-server/secrets/open-webui.env"
        self.assertIn(f"EnvironmentFile={path}", quadlet)
        self.assertIn("d /var/lib/bc250-llm-server/secrets 0700 root root -", tmpfiles)
        self.assertIn('if [ ! -s "$secret_env" ]; then', spec)
        self.assertIn("secrets.token_hex(32)", spec)
        self.assertIn('chmod 0600 "$secret_env"', spec)

    def test_open_webui_connection_config_is_valid_and_matches_packaged_roles(self) -> None:
        helper = (ROOT / "cmd/openwebui/openwebui-setup.py").read_text(encoding="utf-8")
        models = (ROOT / "config/openwebui/models.json").read_text(encoding="utf-8")
        self.assertIn('MAIN_URL = "http://host.containers.internal:11434"', helper)
        self.assertIn('TASK_URL = "http://host.containers.internal:11435"', helper)
        self.assertIn('EMBED_URL = "http://host.containers.internal:11437"', helper)
        self.assertIn('"OLLAMA_BASE_URLS": [MAIN_URL, TASK_URL]', helper)
        self.assertIn('"tags": ["production"]', helper)
        self.assertIn('"tags": ["task"]', helper)
        self.assertNotIn('http://host.containers.internal:11436', helper)
        self.assertIn('"bc250-office-standard"', models)
        self.assertIn('"bc250-office-deep-reasoning"', models)

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

    def test_open_webui_v0113_is_digest_pinned(self) -> None:
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(
            encoding="utf-8"
        )
        self.assertIn("# v0.11.3, pinned OCI index digest.", quadlet)
        self.assertIn(
            "Image=ghcr.io/open-webui/open-webui@sha256:"
            "751b617714b91e4cfd0186a509c72480c858e012976103b09a30dad053c36175",
            quadlet,
        )
        self.assertNotRegex(quadlet, r"(?m)^Image=.*:(?:latest|v0\.11\.3)$")

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

    def test_open_webui_v0113_new_controls_stay_conservative(self) -> None:
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
        self.assertIn("Environment=OLLAMA_BASE_URL=http://host.containers.internal:11434", quadlet)
        helper = (ROOT / "cmd/openwebui/openwebui-setup.py").read_text(encoding="utf-8")
        self.assertIn('/ollama/config/update', helper)
        self.assertIn("Environment=ENABLE_KNOWLEDGE_FILE_RETENTION=false", quadlet)
        self.assertIn("Environment=RAG_SYSTEM_CONTEXT=false", quadlet)
        self.assertIn("Environment=CHUNK_MIN_SIZE_TARGET=0", quadlet)
        self.assertIn("Environment=RAG_EMBEDDING_BATCH_SIZE=1", quadlet)
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

    def test_config_noreplace_and_explicit_install_behavior_remain(self) -> None:
        installer = (ROOT / "scripts/install-manifest.py").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertIn('return f"%config(noreplace) {destination}"', installer)
        self.assertNotIn("systemctl try-restart tika.service open-webui.service", spec)
        self.assertIn("sudo bc250-install", spec)
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
        self.assertEqual(
            values["BC250_OLLAMA_INSTALLER_COMMIT"],
            "f96e7aa0513b9973a0ccc71be414c2ecb9d65b1a",
        )
        self.assertEqual(
            values["BC250_OLLAMA_INSTALLER_SHA256"],
            "25f64b810b947145095956533e1bdf56eacea2673c55a7e586be4515fc882c9f",
        )
        self.assertEqual(values["BC250_OPEN_WEBUI_VERSION"], "0.11.3")
        self.assertEqual(values["BC250_OPEN_WEBUI_TASK_CONTRACT"], "0.11.3")
        self.assertIn(f'# v{values["BC250_OPEN_WEBUI_VERSION"]}, pinned OCI index digest.', quadlet)
        self.assertIn(values["BC250_OPEN_WEBUI_IMAGE_DIGEST"], quadlet)
        self.assertIn(values["BC250_TIKA_VERSION"], tika)
        self.assertIn(values["BC250_TIKA_IMAGE_DIGEST"], tika)
        self.assertIn("config/runtime.env\t{share}/runtime.env", (ROOT / "packaging/install-manifest.tsv").read_text())

    def test_fresh_machine_memory_profile_is_ttm_only_and_cleans_legacy_overrides(self) -> None:
        profile = (ROOT / "cmd/system/memory-profile.sh").read_text(encoding="utf-8")
        installer = (ROOT / "cmd/system/install.sh").read_text(encoding="utf-8")
        canonical = "ttm.pages_limit=4194304 ttm.page_pool_size=4194304"
        self.assertIn(f'FULL_MEMORY_ARGS="{canonical}"', profile)
        for token in ("ttm.pages_limit=4194304", "ttm.page_pool_size=4194304"):
            self.assertIn(token, installer)
        self.assertNotIn("amdgpu.gttsize=14750", installer)
        self.assertNotIn("amdgpu.ppfeaturemask=0xffffffff", installer)
        self.assertIn("amdgpu.gttsize", profile)
        self.assertIn("amdgpu.ppfeaturemask", profile)
        self.assertIn("legacy", profile.lower())
        self.assertIn("mapfile -t kernel_args", installer)
        self.assertNotIn("apply-safe", profile)


if __name__ == "__main__":
    unittest.main()
