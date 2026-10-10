from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class PackagingTests(unittest.TestCase):
    def test_release_identity_is_consistent(self) -> None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        state = json.loads((ROOT / "WORKBENCH-STATE.json").read_text(encoding="utf-8"))
        spec_version = re.search(r"^Version:\s*(\S+)", spec, re.MULTILINE)
        spec_release = re.search(r"^Release:\s*([^%\s]+)", spec, re.MULTILINE)
        self.assertIsNotNone(spec_version)
        self.assertIsNotNone(spec_release)
        self.assertEqual(spec_version.group(1), version)
        expected = f"bc250-llm-server-{version}-{spec_release.group(1)}"
        self.assertEqual(state["release_identity"], expected)
        self.assertIn(expected, (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn(expected, (ROOT / "TLDR.md").read_text(encoding="utf-8"))

    def test_package_version_authority_is_installed_for_revalidation(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn("file\t0644\tVERSION\t{share}/VERSION", manifest)

    def test_runtime_state_helper_is_packaged_as_private_read_only_library(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn(
            "file\t0644\tcmd/monitoring/runtime-state.sh\t{libexec}/runtime-state.sh",
            manifest,
        )
        helper = (ROOT / "cmd/monitoring/runtime-state.sh").read_text(encoding="utf-8")
        self.assertFalse(helper.startswith("#!"))

    def test_install_manifest_rejects_non_executable_shebang_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_root = base / "source"
            source_root.mkdir()
            helper = source_root / "helper.sh"
            helper.write_text("#!/usr/bin/env bash\necho test\n", encoding="utf-8")
            manifest = base / "manifest.tsv"
            manifest.write_text(
                "file\t0644\thelper.sh\t/usr/libexec/test/helper.sh\n",
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
        self.assertIn("non-executable source has a shebang", result.stderr)

    def test_candidate_quality_checks_are_source_only(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        revalidate = (ROOT / "cmd/benchmark/revalidate.sh").read_text(encoding="utf-8")
        self.assertNotIn("quality-checks/", manifest)
        self.assertNotIn("quality-checks", revalidate)
        self.assertIn("models/retired-models.json\t{share}/model-management/retired-models.json", manifest)
        self.assertTrue((ROOT / "quality-checks/README.md").is_file())

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

    def test_live_manager_cpu_unlock_uses_bc250_compatible_reboot_patch(self) -> None:
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        patch = (ROOT / "patches/cu-live-manager-rpm-paths.patch").read_text(encoding="utf-8")
        self.assertIn("patch -d live-manager-src -p1 < patches/cu-live-manager-rpm-paths.patch", spec)
        self.assertIn("-\t\t\t\tsystemctl reboot", patch)
        self.assertIn("+\t\t\t\t/usr/sbin/reboot", patch)

        # GNU patch applies hunks sequentially. Keep source hunks ordered by the
        # original-file line number so a later RPM %prep does not fail merely
        # because a newly added hunk targets an earlier section of the file.
        old_starts = [
            int(match.group(1))
            for match in re.finditer(r"(?m)^@@ -(\d+)(?:,\d+)? \+", patch)
        ]
        self.assertGreaterEqual(len(old_starts), 4)
        self.assertEqual(old_starts, sorted(old_starts))

    def test_source_tarball_is_reproducible_and_excludes_local_state(self) -> None:
        source = (ROOT / "scripts/make-source-tarball.sh").read_text(encoding="utf-8")
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for expected in (
            "--exclude='./sources'",
            "--exclude='*/.ruff_cache'",
            "--exclude='*/.pytest_cache'",
            "--exclude='*/__pycache__'",
            "--exclude='*.pyc'",
            "--exclude='*.pyo'",
            "TZ=UTC date",
            "--mode='u+rwX,go+rX,go-w,a-s,a-t'",
        ):
            self.assertIn(expected, source)
        for expected in (
            "/sources/*.sha256",
            ".ruff_cache/",
            ".pytest_cache/",
            "__pycache__/",
            "*.pyc",
            "*.pyo",
        ):
            self.assertIn(expected, gitignore)

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            (project / "scripts").mkdir(parents=True)
            (project / "packaging").mkdir()
            (project / "sources").mkdir()
            (project / "nested/.pytest_cache").mkdir(parents=True)
            (project / "nested/.ruff_cache").mkdir(parents=True)
            (project / "nested/__pycache__").mkdir(parents=True)
            script = project / "scripts/make-source-tarball.sh"
            script.write_text(source, encoding="utf-8")
            script.chmod(0o755)
            (project / "VERSION").write_text("0.13.1\n", encoding="utf-8")
            (project / "packaging/bc250-llm-server.spec").write_text(
                "%changelog\n* Thu Oct 08 2026 Test <test@example.invalid> - 0.13.1-1.1\n",
                encoding="utf-8",
            )
            (project / "sources/cache.sha256").write_text("local cache\n", encoding="utf-8")
            (project / "nested/.pytest_cache/state").write_text("cache", encoding="utf-8")
            (project / "nested/.ruff_cache/state").write_text("cache", encoding="utf-8")
            (project / "nested/__pycache__/module.pyc").write_bytes(b"cache")
            (project / "nested/module.pyc").write_bytes(b"cache")
            (project / "nested/module.pyo").write_bytes(b"cache")
            keep = project / "nested/keep.txt"
            keep.write_text("keep\n", encoding="utf-8")
            tool = project / "nested/tool.sh"
            tool.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            tool.chmod(0o755)

            hashes = []
            for timezone in ("UTC", "Europe/Zurich"):
                if timezone != "UTC":
                    project.chmod(0o2775)
                    keep.chmod(0o664)
                    (project / "sources/cache.sha256").write_text("changed local cache\n", encoding="utf-8")
                result = subprocess.run(
                    ["bash", str(script)],
                    cwd=project,
                    env={**os.environ, "TZ": timezone},
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                archive = project / "build/bc250-llm-server-0.13.1.tar.gz"
                hashes.append(hashlib.sha256(archive.read_bytes()).hexdigest())

            self.assertEqual(hashes[0], hashes[1])
            with tarfile.open(archive, "r:gz") as tar:
                members = {member.name: member for member in tar.getmembers()}

        self.assertTrue(any(name.endswith("nested/keep.txt") for name in members))
        self.assertFalse(any("/sources/" in name for name in members))
        forbidden = ("/.pytest_cache/", "/.ruff_cache/", "/__pycache__/", ".pyc", ".pyo")
        for name in members:
            self.assertFalse(any(token in name for token in forbidden), name)
        keep_member = next(member for name, member in members.items() if name.endswith("nested/keep.txt"))
        tool_member = next(member for name, member in members.items() if name.endswith("nested/tool.sh"))
        self.assertEqual(keep_member.mode & 0o777, 0o644)
        self.assertEqual(tool_member.mode & 0o777, 0o755)

    def test_model_package_and_public_dispatcher_are_installed(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn("models/modelctl.py\t{libexec}/modelctl", manifest)
        self.assertIn("{config}/models.d", manifest)
        self.assertIn("models/modelfiles/*.Modelfile", manifest)
        self.assertNotIn("models/sources", manifest)
        self.assertIn("uninstall.sh\t{libexec}/uninstall.sh", manifest)
        self.assertIn("cmd/monitoring/status.sh\t{libexec}/status.sh", manifest)
        self.assertIn("cmd/monitoring/status-json.py\t{libexec}/status-json.py", manifest)
        self.assertIn("cmd/monitoring/doctor.py\t{libexec}/doctor.py", manifest)
        self.assertIn("cmd/monitoring/support-bundle.sh\t{libexec}/support-bundle.sh", manifest)
        self.assertNotIn("bc250_model", manifest)
        dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
        for route in ("model", "status", "doctor", "version", "support-bundle", "fetch-mtp", "gfx1013", "ocr", "rag", "package-gate", "qualification", "resilience"):
            self.assertRegex(dispatcher, rf'(?m)^  "{route}\|', route)
        self.assertNotIn('--list-aliases', dispatcher)
        self.assertNotIn('"uninstall|', dispatcher)
        self.assertNotIn('"fetch-embeddings|', dispatcher)
        self.assertNotIn("aliases\t", manifest)
        self.assertIn("packaging/bc250\t{bindir}/bc250", manifest)
        self.assertIn("cmd/system/40cu.sh\t{bindir}/bc250-40cu", manifest)
        self.assertIn("live-manager-src/bc250-cu-live-manager.sh\t{bindir}/bc250-cu-live-manager", manifest)
        self.assertIn("models/ocr/bc250-ocr.sh\t{libexec}/ocr.sh", manifest)
        for entry in (
            "cmd/benchmark/benchmark.sh\t{libexec}/benchmark.sh",
            "cmd/benchmark/generation-benchmark.py\t{libexec}/generation-benchmark.py",
            "cmd/benchmark/category-benchmark.py\t{libexec}/category-benchmark.py",
            "cmd/benchmark/runtime-benchmark.py\t{libexec}/runtime-benchmark.py",
            "cmd/benchmark/openwebui-benchmark.py\t{libexec}/openwebui-benchmark.py",
            "cmd/benchmark/benchmark_common.py\t{libexec}/benchmark_common.py",
            "cmd/benchmark/gfx1013-ab.py\t{libexec}/gfx1013-ab.py",
            "cmd/qualification/qualification_inventory.py\t{libexec}/qualification/qualification_inventory.py",
            "cmd/monitoring/version.py\t{libexec}/version.py",
            "packaging/completions/bc250.bash\t{bashcompletiondir}/bc250",
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

    def test_17_operator_qol_interfaces_are_packaged(self) -> None:
        dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        completion = (ROOT / "packaging/completions/bc250.bash").read_text(encoding="utf-8")
        self.assertIn('"qualification|$LIBEXEC/qualification/qualification_inventory.py"', dispatcher)
        self.assertIn('"version|$LIBEXEC/version.py"', dispatcher)
        self.assertIn('--version) exec "$LIBEXEC/version.py" --short', dispatcher)
        self.assertIn("gfx1013-ab.py\t{libexec}/gfx1013-ab.py", manifest)
        self.assertIn("qualification_inventory.py\t{libexec}/qualification/qualification_inventory.py", manifest)
        self.assertIn("packaging/completions/bc250.bash\t{bashcompletiondir}/bc250", manifest)
        self.assertIn("qualification", completion)
        self.assertIn("stock gfx restored status report", completion)
        self.assertIn("--older-than-days --keep-latest --apply", completion)

    def test_dispatcher_suppresses_python_bytecode_in_package_helpers(self) -> None:
        dispatcher = ROOT / "packaging/bc250"
        with tempfile.TemporaryDirectory() as temporary:
            libexec = Path(temporary)
            (libexec / "helper_module.py").write_text("VALUE = 1\n", encoding="utf-8")
            rag = libexec / "rag"
            rag.write_text("#!/usr/bin/env python3\nimport helper_module\nprint(helper_module.VALUE)\n", encoding="utf-8")
            rag.chmod(0o755)
            result = subprocess.run([str(dispatcher), "rag"], env={**os.environ, "BC250_LIBEXEC": str(libexec)}, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "1")
            self.assertFalse((libexec / "__pycache__").exists())

    def test_fetch_mtp_dispatches_to_explicit_disabled_entry_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            libexec = Path(temporary)
            modelctl = libexec / "modelctl"
            modelctl.write_text(
                "#!/usr/bin/env bash\nprintf '%s\n' \"$@\"\n", encoding="utf-8"
            )
            modelctl.chmod(0o755)
            result = subprocess.run(
                [
                    str(ROOT / "packaging/bc250"),
                    "fetch-mtp",
                    "qwen3.6-27b-mtp",
                ],
                env={**os.environ, "BC250_LIBEXEC": str(libexec)},
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["apply", "mtp", "--include-disabled", "qwen3.6-27b-mtp"],
        )

    def test_embedding_uses_modelfile_discovery_and_recommended_open_webui_name(
        self,
    ) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(
            encoding="utf-8"
        )
        desired = json.loads(
            (ROOT / "config/openwebui/desired-state.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("pull-embedding-model", dispatcher)
        self.assertNotIn("install-cu-manager", dispatcher)
        self.assertNotIn("log_sensors.sh", manifest)
        self.assertNotIn("fetch-embeddings|", dispatcher)
        self.assertIn("models/modelctl.py\t{libexec}/modelctl", manifest)
        self.assertEqual(
            desired["embedding"]["RAG_EMBEDDING_MODEL"],
            "embed-jina-v5-small-retrieval-q4-k-m",
        )
        self.assertEqual(desired["embedding"]["ollama_config"]["url"], "http://host.containers.internal:11437")
        self.assertEqual(desired["rag"]["TEXT_SPLITTER"], "token")
        self.assertEqual(desired["rag"]["CHUNK_SIZE"], 1500)
        self.assertEqual(desired["rag"]["CHUNK_OVERLAP"], 200)
        self.assertEqual(desired["rag"]["TOP_K"], 4)
        self.assertFalse(desired["task"]["ENABLE_RETRIEVAL_QUERY_GENERATION"])
        self.assertTrue(desired["task"]["ENABLE_TITLE_GENERATION"])
        self.assertTrue(desired["task"]["ENABLE_TAGS_GENERATION"])
        self.assertFalse(desired["task"]["ENABLE_FOLLOW_UP_GENERATION"])
        self.assertFalse(desired["task"]["ENABLE_AUTOCOMPLETE_GENERATION"])
        self.assertFalse(desired["task"]["ENABLE_SEARCH_QUERY_GENERATION"])
        self.assertNotIn("RAG_EMBEDDING_MODEL=", quadlet)
        self.assertNotIn("CHUNK_SIZE=", quadlet)

    def test_rpm_post_is_small_and_defers_provisioning(self) -> None:
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        post = spec[spec.index("%post\n"):spec.index("%preun")]
        self.assertIn("%tmpfiles_create", post)
        self.assertIn("WEBUI_SECRET_KEY", post)
        self.assertIn("sudo bc250 install", post)
        self.assertIn("\\033[1;33m", post)
        self.assertIn("printf '%b' \"$bc250_amber\"", post)
        for forbidden in ("firewall-cmd", "setsebool", "dnf ", "systemctl enable --now"):
            self.assertNotIn(forbidden, post)

    def test_package_standard_ollama_uses_runtime_authority(self) -> None:
        helper = (ROOT / "cmd/system/install-ollama.sh").read_text(encoding="utf-8")
        installer = (ROOT / "cmd/system/install.sh").read_text(encoding="utf-8")
        verify = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        self.assertIn('VERSION="${OLLAMA_VERSION:-$BC250_OLLAMA_VERSION}"', helper)
        self.assertIn('source "$runtime_env"', installer)
        self.assertNotIn('BC250_OLLAMA_VERSION="0.34.0"', installer)
        self.assertIn('requested="$BC250_OLLAMA_VERSION"', installer)
        self.assertIn("BC250_OLLAMA_VERSION=0.34.4", (ROOT / "config/runtime.env").read_text())
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
        desired = json.loads(
            (ROOT / "config/openwebui/desired-state.json").read_text(encoding="utf-8")
        )
        models = (ROOT / "config/openwebui/models.json").read_text(encoding="utf-8")
        self.assertEqual(
            desired["ollama"]["OLLAMA_BASE_URLS"],
            ["http://host.containers.internal:11434", "http://host.containers.internal:11435"],
        )
        self.assertEqual(desired["embedding"]["ollama_config"]["url"], "http://host.containers.internal:11437")
        self.assertEqual(desired["ollama"]["OLLAMA_API_CONFIGS"]["0"]["tags"], ["main", "testing"])
        self.assertEqual(desired["ollama"]["OLLAMA_API_CONFIGS"]["1"]["tags"], ["task", "testing"])
        self.assertNotIn("http://host.containers.internal:11436", json.dumps(desired))
        self.assertIn("desired-state.json", helper)
        self.assertIn('"bc250-office-standard"', models)
        self.assertIn('"bc250-office-deep-reasoning"', models)
        model_data = json.loads(models)["models"]
        hidden_ids = {
            item["id"]
            for item in model_data
            if item.get("is_active") is True
            and isinstance(item.get("meta"), dict)
            and item["meta"].get("hidden") is True
        }
        self.assertEqual(hidden_ids, set())
        self.assertEqual(desired["ollama"]["OLLAMA_API_CONFIGS"]["0"]["model_ids"], [])
        self.assertEqual(desired["ollama"]["OLLAMA_API_CONFIGS"]["1"]["model_ids"], [])

    def test_fresh_install_governor_maximum_is_1850_mhz(self) -> None:
        config = (ROOT / "config/governor/config.toml").read_text(encoding="utf-8")
        self.assertRegex(
            config,
            r"(?ms)^\[frequency-range\]\s*$.*?^min = 350\s*$.*?^max = 1850\s*$",
        )

    def test_governor_v0413_pin_keeps_conservative_usage_defaults(self) -> None:
        commit = "aaed42535622aee1a93df8b22860c409539f67f8"
        upstreams = (ROOT / "packaging/upstreams.toml").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        config = (ROOT / "config/governor/config.toml").read_text(encoding="utf-8")
        self.assertIn('version = "0.4.13"', upstreams)
        self.assertIn(f'commit = "{commit}"', upstreams)
        self.assertIn("%global governor_version 0.4.13", spec)
        self.assertIn(f"%global governor_commit {commit}", spec)
        self.assertRegex(
            config,
            r"(?ms)^\[gpu-usage\]\s*$.*?^fix-metrics = true\s*$.*?^fix-freq = false\s*$.*?^method = \"busy-flag\"",
        )
        self.assertIn('temp-read = "sysfs"', config)

    def test_open_webui_v0114_is_digest_pinned(self) -> None:
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(
            encoding="utf-8"
        )
        self.assertIn("# v0.11.4, pinned OCI index digest.", quadlet)
        self.assertIn(
            "Image=ghcr.io/open-webui/open-webui@sha256:"
            "9591b13f13843c7721c2b8eaf7382846c81b3ffe126526d1888d1fed50c6a33f",
            quadlet,
        )
        self.assertNotRegex(quadlet, r"(?m)^Image=.*:(?:latest|v0\.11\.4)$")

    def test_open_webui_fresh_install_privacy_features_are_disabled(self) -> None:
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(
            encoding="utf-8"
        )
        desired = json.loads(
            (ROOT / "config/openwebui/desired-state.json").read_text(encoding="utf-8")
        )
        for setting in (
            "ENABLE_COMMUNITY_SHARING=false",
            "ENABLE_CODE_EXECUTION=false",
            "ENABLE_CODE_INTERPRETER=false",
            "ENABLE_MEMORIES=false",
        ):
            self.assertIn(f"Environment={setting}", quadlet)
        self.assertEqual(
            desired["application"],
            {
                "evaluation.arena.enable": False,
                "openai.enable": False,
                "direct.enable": False,
                "code_execution.enable": False,
                "code_interpreter.enable": False,
                "memories.enable": False,
                "ui.enable_community_sharing": False,
            },
        )
        self.assertEqual(desired["rag"]["FILE_MAX_SIZE"], 128)
        self.assertEqual(desired["rag"]["FILE_MAX_COUNT"], 20)
        self.assertIn("pdf", desired["rag"]["ALLOWED_FILE_EXTENSIONS"])

    def test_open_webui_pinned_controls_stay_conservative(self) -> None:
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(
            encoding="utf-8"
        )
        desired = json.loads(
            (ROOT / "config/openwebui/desired-state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(desired["task"]["TASK_MODEL_PARAMS"], {})
        self.assertEqual(
            desired["task"]["TASK_MODEL"],
            "task-lfm25-1.2b-instruct-liquidai-q6-k:latest",
        )
        for key in (
            "TITLE_GENERATION_PROMPT_TEMPLATE",
            "TAGS_GENERATION_PROMPT_TEMPLATE",
            "QUERY_GENERATION_PROMPT_TEMPLATE",
        ):
            self.assertIsInstance(desired["task"][key], str)
            self.assertTrue(desired["task"][key].strip())
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
        self.assertEqual(desired["rag"]["CHUNK_MIN_SIZE_TARGET"], 0)
        self.assertEqual(desired["embedding"]["RAG_EMBEDDING_BATCH_SIZE"], 1)
        self.assertEqual(desired["rag"]["TIKA_SERVER_VERSION"], "4")
        self.assertNotIn("CHUNK_MIN_SIZE_TARGET=", quadlet)
        self.assertNotIn("RAG_EMBEDDING_BATCH_SIZE=", quadlet)
        self.assertNotIn("Environment=ENABLE_ORJSON=true", quadlet)

    def test_task_default_is_consistent_across_package_entry_points(self) -> None:
        desired = json.loads(
            (ROOT / "config/openwebui/desired-state.json").read_text(encoding="utf-8")
        )
        task = desired["task"]["TASK_MODEL"].removesuffix(":latest")
        self.assertEqual(task, "task-lfm25-1.2b-instruct-liquidai-q6-k")
        installer = (ROOT / "cmd/system/install.sh").read_text(encoding="utf-8")
        self.assertIn(".task.TASK_MODEL", installer)
        self.assertIn(".embedding.RAG_EMBEDDING_MODEL", installer)
        self.assertIn("select(.is_active == true)", installer)
        self.assertIn(
            f"readonly TASK_MODEL={task}",
            (ROOT / "cmd/benchmark/revalidate.sh").read_text(encoding="utf-8"),
        )
        self.assertIn(
            f'--arg model "{task}"',
            (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8"),
        )
        self.assertIn(
            f'"{task}"',
            (ROOT / "models/modelctl.py").read_text(encoding="utf-8"),
        )

    def test_compare_mtp_does_not_force_global_think_false(self) -> None:
        source = (ROOT / "models/experiments/compare-mtp.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("think:false", source)

    def test_compare_mtp_proves_process_group_ownership_before_group_signal(self) -> None:
        source = (ROOT / "models/experiments/compare-mtp.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("process_group_owned()", source)
        self.assertIn('ps -o sid= -p "$pid"', source)
        self.assertIn('ps -o pgid= -p "$pid"', source)
        self.assertIn('"$sid" == "$pid" && "$pgid" == "$pid"', source)
        self.assertIn('signal_server TERM "$pgid"', source)
        self.assertIn('signal_server KILL "$pgid"', source)
        self.assertIn("signaling only the direct child", source)
        self.assertNotIn('kill -TERM -- "-$ACTIVE_PGID"', source)
        self.assertNotIn('kill -KILL -- "-$ACTIVE_PGID"', source)

    def test_mtp_evidence_records_acceptance_and_opt_in_ubatch(self) -> None:
        runner = (ROOT / "models/mtp/run-mtp-llamacpp.sh").read_text(encoding="utf-8")
        self.assertIn('UBATCH="${UBATCH:-}"', runner)
        self.assertIn('--ubatch-size "$UBATCH"', runner)
        self.assertIn("llama-server version/build", runner)
        self.assertIn("llama-server flags", runner)
        self.assertIn('MIN_MEM_AVAILABLE_MIB="${MIN_MEM_AVAILABLE_MIB:-2048}"', runner)
        self.assertIn('status mtp "$choice" --include-disabled', runner)
        self.assertIn("TCP port $PORT is already listening", runner)
        self.assertIn("another llama-server process is already running", runner)
        self.assertIn('sudo -n -u ollama -- "$LLAMACPP"', runner)
        self.assertIn('--no-mtp', runner)
        self.assertNotIn('UBATCH="384"', runner)

    def test_task_recovery_gate_reloads_main_and_ignores_preexisting_faults(self) -> None:
        recovery = (ROOT / "quality-checks/task/30-appliance-recovery-check.sh").read_text(encoding="utf-8")
        self.assertIn('WARM_MAIN="${WARM_MAIN:-1}"', recovery)
        self.assertIn('--until "$CHECK_START"', recovery)
        self.assertIn('--since "$CHECK_START"', recovery)
        self.assertIn('new serious kernel events during recovery probe', recovery)

    def test_task_safety_gates_cover_normal_embedding_service(self) -> None:
        scripts = (
            ROOT / "quality-checks/task/20-survival-gate.sh",
            ROOT / "quality-checks/task/30-appliance-recovery-check.sh",
        )
        for script in scripts:
            with self.subTest(script=script.name):
                source = script.read_text(encoding="utf-8")
                self.assertIn("ollama-embedding.service", source)

    def test_translation_final_status_is_written_after_privacy_and_updated_on_tar_failure(self) -> None:
        source = (ROOT / "quality-checks/translation/10-direct-candidate-screen.sh").read_text(encoding="utf-8")
        privacy_pos = source.index("privacy_rc=$?")
        status_pos = source.index("printf '%s\\n' \"$rc\" > \"$OUT/post/script-exit-rc.txt\"", privacy_pos)
        tar_pos = source.index('tar --owner=0 --group=0 --numeric-owner', status_pos)
        failure_rewrite_pos = source.index("printf '%s\\n' \"$rc\" > \"$OUT/post/script-exit-rc.txt\"", tar_pos)
        self.assertLess(privacy_pos, status_pos)
        self.assertLess(status_pos, tar_pos)
        self.assertGreater(failure_rewrite_pos, tar_pos)
        self.assertIn('write_run_manifest "$rc"', source[failure_rewrite_pos:])

    def test_owui_translation_final_status_updates_after_archive_failure(self) -> None:
        source = (ROOT / "quality-checks/translation/20-owui-candidate-screen.sh").read_text(encoding="utf-8")
        credential_pos = source.index("credential_scan")
        status_pos = source.index("test-script-rc.txt", credential_pos)
        manifest_pos = source.index('write_run_manifest "$rc"', status_pos)
        tar_pos = source.index('tar --owner=0 --group=0 --numeric-owner', manifest_pos)
        rc_change_pos = source.index('rc=27', tar_pos)
        status_rewrite_pos = source.index("test-script-rc.txt", rc_change_pos)
        manifest_rewrite_pos = source.index('write_run_manifest "$rc"', status_rewrite_pos)
        self.assertLess(status_pos, manifest_pos)
        self.assertLess(manifest_pos, tar_pos)
        self.assertLess(tar_pos, rc_change_pos)
        self.assertLess(rc_change_pos, status_rewrite_pos)
        self.assertLess(status_rewrite_pos, manifest_rewrite_pos)

    def test_historical_quality_scripts_are_source_only(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertNotIn("quality-checks/history", manifest)
        self.assertTrue((ROOT / "quality-checks/history/01-task-matrix.sh").is_file())
        self.assertTrue((ROOT / "quality-checks/history/README.md").is_file())

    def test_current_quality_archives_print_sha_without_sidecar_files(self) -> None:
        scripts = (
            ROOT / "quality-checks/task/10-candidate-screen.sh",
            ROOT / "quality-checks/task/20-survival-gate.sh",
            ROOT / "quality-checks/translation/10-direct-candidate-screen.sh",
            ROOT / "quality-checks/translation/20-owui-candidate-screen.sh",
        )
        for script in scripts:
            with self.subTest(script=script.name):
                text = script.read_text(encoding="utf-8")
                self.assertIn("sha256sum", text)
                self.assertNotIn('> "$tarball.sha256"', text)
                self.assertNotIn('> "$TARBALL.sha256"', text)

    def test_compare_mtp_uses_same_model_baseline_and_captures_qualification_evidence(self) -> None:
        source = (ROOT / "models/experiments/compare-mtp.sh").read_text(encoding="utf-8")
        self.assertIn('run_phase baseline --no-mtp', source)
        self.assertIn('run_phase mtp ""', source)
        self.assertNotIn('OLLAMA_URL', source)
        self.assertNotIn('BASELINE_MODEL', source)
        for expected in (
            'draft_n_accepted',
            'draft_n // empty',
            'resources.tsv',
            'journal-gpu-faults.log',
            'llamacpp-version.txt',
            'model-status.txt',
            'Speedup:',
        ):
            self.assertIn(expected, source)
        self.assertIn('qualification evidence is incomplete', source)

    def test_ci_runs_on_push_and_pull_request_with_static_linters(self) -> None:
        workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(
            encoding="utf-8"
        )
        self.assertRegex(workflow, r"(?m)^  push:$")
        self.assertRegex(workflow, r"(?m)^  pull_request:$")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("make release-gate", workflow)
        self.assertIn("ruff check .", makefile)
        self.assertIn("shellcheck", makefile)
        self.assertIn("ruff rust ShellCheck", workflow)

    def test_build_environment_uses_portable_c_locale(self) -> None:
        workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(
            encoding="utf-8"
        )
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertRegex(workflow, r"(?m)^  LANG: C$")
        self.assertRegex(workflow, r"(?m)^  LC_ALL: C$")
        self.assertIn("export LANG := C", makefile)
        self.assertIn("export LC_ALL := C", makefile)
        self.assertNotIn("en_US.UTF-8", workflow + makefile)

    def test_main_rpm_description_respects_rpmlint_line_limit(self) -> None:
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        match = re.search(r"(?ms)^%description\s*$\n(.*?)(?=^%[A-Za-z])", spec)
        self.assertIsNotNone(match)
        assert match is not None
        too_long = [line for line in match.group(1).splitlines() if len(line) > 79]
        self.assertEqual(too_long, [])

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

    def test_git_cli_uses_minimal_git_core_runtime_dependency(self) -> None:
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertIn("Requires:       git-core", spec)
        self.assertNotRegex(spec, r"(?m)^Requires:\s+git\s*$")

    def test_package_provides_its_own_ollama_account(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        sysusers = (ROOT / "packaging/bc250-llm-server.sysusers").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("g      ollama -", sysusers)
        self.assertIn('u      ollama -  "Runs Ollama"', sysusers)
        self.assertIn("g      bc250-backup-export -", sysusers)
        self.assertIn(
            "packaging/bc250-llm-server.sysusers\t{sysusersdir}/bc250-llm-server.conf",
            manifest,
        )
        self.assertIn('--define "sysusersdir=%{_sysusersdir}"', spec)
        self.assertNotIn("Requires(pre):    shadow-utils", spec)
        self.assertNotRegex(spec, r"(?s)%pre\s+.*?useradd.*?%build")

    def test_backup_export_directory_permissions_survive_tmpfiles_reconciliation(self) -> None:
        tmpfiles = (ROOT / "packaging/bc250-llm-server.tmpfiles").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertIn("d /var/backups/bc250-llm-server 0710 root bc250-backup-export -", tmpfiles)
        self.assertIn("d /var/backups/bc250-llm-server/config 0750 root bc250-backup-export -", tmpfiles)
        self.assertIn("d /var/backups/bc250-llm-server/users 0750 root bc250-backup-export -", tmpfiles)
        self.assertIn("%attr(0710,root,bc250-backup-export) /var/backups/bc250-llm-server", spec)
        self.assertIn("%attr(0750,root,bc250-backup-export) /var/backups/bc250-llm-server/config", spec)
        self.assertIn("%attr(0750,root,bc250-backup-export) /var/backups/bc250-llm-server/users", spec)

    def test_config_noreplace_and_explicit_install_behavior_remain(self) -> None:
        installer = (ROOT / "scripts/install-manifest.py").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertIn('return f"%config(noreplace) {destination}"', installer)
        self.assertNotIn("systemctl try-restart tika.service open-webui.service", spec)
        self.assertIn("sudo bc250 install", spec)
        self.assertNotIn("legacy migration", spec.lower())

    def test_live_cu_manager_is_the_only_packaged_cu_backend(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        upstreams = (ROOT / "packaging/upstreams.toml").read_text(encoding="utf-8")
        wrapper = (ROOT / "cmd/system/40cu.sh").read_text(encoding="utf-8")
        self.assertIn("live-manager-src/bc250-cu-live-manager.sh", manifest)
        self.assertIn("cmd/system/cu-status.sh\t{libexec}/cu-status.sh", manifest)
        self.assertIn("cmd/system/cu-status.sh\t{libexec}/cu-status.sh", manifest)
        self.assertNotIn("unlock-src", manifest + spec)
        self.assertNotIn("bc250-40cu-unlock", upstreams + spec)
        self.assertFalse((ROOT / "cmd/system/40cu-module.sh").exists())
        self.assertFalse((ROOT / "licenses/40CU-LICENSE-NOTICE").exists())
        self.assertIn('case "${1:-}" in', wrapper)
        self.assertNotIn("prepare)", wrapper)
        self.assertNotIn("enable)", wrapper)

    def test_runtime_pins_match_container_and_ollama_helpers(self) -> None:
        values = {}
        for line in (ROOT / "config/runtime.env").read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                values[key] = value
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(encoding="utf-8")
        tika = (ROOT / "config/containers/tika.container").read_text(encoding="utf-8")
        self.assertEqual(values["BC250_OLLAMA_VERSION"], "0.34.4")
        self.assertEqual(
            values["BC250_OLLAMA_PAYLOAD_URL"],
            "https://github.com/ollama/ollama/releases/download/v0.34.4/ollama-linux-amd64.tar.zst",
        )
        self.assertEqual(
            values["BC250_OLLAMA_PAYLOAD_SHA256"],
            "c238986e61d40c0cc5f4a9b9e40b9eea104350b77efa34741fc134e105cb9533",
        )
        self.assertEqual(values["BC250_OPEN_WEBUI_VERSION"], "0.11.4")
        self.assertEqual(values["BC250_OPEN_WEBUI_TASK_CONTRACT"], "0.11.4")
        self.assertEqual(values["BC250_TIKA_VERSION"], "4.1.0-full")
        self.assertEqual(values["BC250_GOVERNOR_VERSION"], "0.4.13")
        self.assertEqual(values["BC250_GOVERNOR_COMMIT"], "aaed42535622aee1a93df8b22860c409539f67f8")
        self.assertEqual(
            values["BC250_TIKA_IMAGE_DIGEST"],
            "sha256:d7607239d4e9c2dc1fd396f41a370576a334aef28f767e5bc5511247a1e1adf7",
        )
        self.assertIn(f'# v{values["BC250_OPEN_WEBUI_VERSION"]}, pinned OCI index digest.', quadlet)
        self.assertIn(values["BC250_OPEN_WEBUI_IMAGE_DIGEST"], quadlet)
        self.assertIn("Environment=TIKA_SERVER_VERSION=4", quadlet)
        self.assertIn(values["BC250_TIKA_VERSION"], tika)
        self.assertIn(values["BC250_TIKA_IMAGE_DIGEST"], tika)
        self.assertIn("SuccessExitStatus=143", tika)
        self.assertNotIn("SuccessExitStatus=0 143", tika)
        upstreams = (ROOT / "packaging/upstreams.toml").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        live_manager_commit = "a929085d791f126ce76a60eb609610820fb08066"
        self.assertIn(f'commit = "{live_manager_commit}"', upstreams)
        self.assertIn(f"%global live_manager_commit {live_manager_commit}", spec)
        self.assertIn("config/runtime.env\t{share}/runtime.env", (ROOT / "packaging/install-manifest.tsv").read_text())

    def test_fresh_machine_memory_profile_is_ttm_only_and_cleans_legacy_overrides(self) -> None:
        profile = (ROOT / "cmd/system/memory-profile.sh").read_text(encoding="utf-8")
        installer = (ROOT / "cmd/system/install.sh").read_text(encoding="utf-8")
        canonical = "ttm.pages_limit=4194304 ttm.page_pool_size=4194304"
        self.assertIn(f'FULL_MEMORY_ARGS="{canonical}"', profile)
        self.assertIn('MEMORY_PROFILE="$LIBEXEC_DIR/memory-profile.sh"', installer)
        self.assertIn('"$MEMORY_PROFILE" ensure', installer)
        self.assertIn('MEMORY_PROFILE="$LIBEXEC_DIR/memory-profile.sh"', installer)
        self.assertNotIn("ttm.pages_limit=4194304", installer)
        self.assertNotIn("ttm.page_pool_size=4194304", installer)
        self.assertNotIn("amdgpu.gttsize=14750", installer)
        self.assertNotIn("amdgpu.ppfeaturemask=0xffffffff", installer)
        self.assertIn("amdgpu.gttsize", profile)
        self.assertIn("amdgpu.ppfeaturemask", profile)
        self.assertIn("legacy", profile.lower())
        self.assertNotIn("apply-safe", profile)


    def test_license_payload_uses_distinct_basenames(self) -> None:
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertIn("cp -p governor-src/LICENSE governor-src/LICENSE.cyan-skillfish-governor", spec)
        self.assertIn("%license licenses/LICENSE governor-src/LICENSE.cyan-skillfish-governor", spec)
        self.assertNotIn("%license licenses/LICENSE governor-src/LICENSE\n", spec)

    def test_sysusers_relies_on_user_entry_for_ollama_primary_group(self) -> None:
        sysusers = (ROOT / "packaging/bc250-llm-server.sysusers").read_text(encoding="utf-8")
        self.assertIn('u      ollama -  "Runs Ollama"', sysusers)
        self.assertEqual(sum(1 for line in sysusers.splitlines() if line.split()[1:2] == ["ollama"]), 1)

    def test_makefile_checks_actual_greenfield_rpm_payload(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("check-rpm-payload", makefile)
        self.assertIn("/usr/bin/bc250-40cu", makefile)
        self.assertIn("/usr/bin/bc250-cu-live-manager", makefile)
        self.assertIn("/usr/libexec/bc250-llm-server/status-json.py", makefile)
        self.assertIn("/usr/libexec/bc250-llm-server/doctor.py", makefile)
        self.assertIn("/usr/libexec/bc250-llm-server/qualification/package_gate_capture.py", makefile)
        self.assertIn("/usr/libexec/bc250-llm-server/qualification/resilience_manager.py", makefile)
        self.assertIn("grep '^/usr/bin/bc250-'", makefile)
        self.assertIn("/quality-checks/", makefile)
        self.assertIn("/usr/share/licenses/bc250-llm-server/LICENSE.cyan-skillfish-governor", makefile)
        self.assertIn("ollama_group_provides", makefile)
        self.assertIn("expected exactly one generated group(ollama) provide", makefile)

    def test_ci_runs_configured_rpmlint_after_rpm_build(self) -> None:
        workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(encoding="utf-8")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("rpmlint", workflow)
        self.assertIn("make release-gate", workflow)
        release_gate = makefile[makefile.index("release-gate:"):makefile.index("\n\nclean:")]
        self.assertLess(release_gate.index("$(MAKE) rpm"), release_gate.index("rpmlint -c"))
        self.assertIn("rpmlint -c packaging/rpmlint.toml $(DISTDIR)/*.rpm", release_gate)
        self.assertIn("$(MAKE) check-srpm-rebuild", release_gate)

    def test_rpmlint_policy_filters_only_intentional_appliance_findings(self) -> None:
        import tomllib

        config = tomllib.loads(
            (ROOT / "packaging/rpmlint.toml").read_text(encoding="utf-8")
        )
        filters = "\n".join(config["Filters"])
        for expected in (
            "non-standard-dir-perm",
            "/srv/bc250-documents 750",
            "non-standard-uid",
            "non-standard-gid",
            "non-standard-dir-in-var backups",
            "invalid-url Source[0-3]",
            "spelling-error",
            "incorrect-fsf-address",
            "no-manual-page-for-binary",
            "dangerous-command-in-%preun",
            "dangerous-command-in-%pre",
            "dangerous-command-in-%post",
        ):
            self.assertIn(expected, filters)
        for genuine in (
            "tmpfile-not-in-filelist",
            "strange-permission",
            "non-executable-script",
            "macro-in-comment",
            "description-line-too-long",
        ):
            self.assertNotIn(genuine, filters)

    def test_tmpfiles_document_root_is_represented_as_ghost_directory(self) -> None:
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertIn(
            "%ghost %dir %attr(0750,root,root) /srv/bc250-documents",
            spec,
        )

    def test_repository_validation_runs_test_modules_in_isolation(self) -> None:
        validate = (ROOT / "scripts/validate.sh").read_text(encoding="utf-8")
        self.assertIn('for test_file in "$ROOT"/tests/test_*.py', validate)
        self.assertIn('python3 -m unittest "$test_file"', validate)
        self.assertNotIn("python3 -m unittest discover -s tests -v", validate)
        self.assertIn('BC250_TEST_MODULE_TIMEOUT:-120', validate)
        self.assertIn('timeout --kill-after=5s "${test_module_timeout}s"', validate)

    def test_internal_rag_importer_is_not_packaged_as_an_executable_script(self) -> None:
        source_path = ROOT / "models/rag/rag_import.py"
        source = source_path.read_text(encoding="utf-8")
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertFalse(source.startswith("#!"))
        self.assertEqual(source_path.stat().st_mode & 0o111, 0)
        self.assertIn(
            "file\t0644\tmodels/rag/rag_import.py\t{libexec}/rag_import.py",
            manifest,
        )




if __name__ == "__main__":
    unittest.main()
