from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


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
        self.assertIn("fetch-embeddings", result.stdout.splitlines())
        self.assertIn("ocr", result.stdout.splitlines())
        self.assertIn("models/ocr/bc250-ocr.sh\t{libexec}/ocr.sh", manifest)

    def test_embedding_uses_modelfile_discovery_and_recommended_open_webui_name(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        dispatcher = (ROOT / "packaging/bc250").read_text(encoding="utf-8")
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("pull-embedding-model.sh", manifest)
        self.assertIn('modelctl|install|embedding', dispatcher)
        self.assertIn(
            "Environment=RAG_EMBEDDING_MODEL=embed-jina-v5-small-retrieval-q4-k-m",
            quadlet,
        )
        self.assertIn("Environment=RAG_TEXT_SPLITTER=token", quadlet)
        self.assertIn("Environment=CHUNK_SIZE=1500", quadlet)
        self.assertIn("Environment=CHUNK_OVERLAP=200", quadlet)
        self.assertIn("Environment=RAG_TOP_K=8", quadlet)
        self.assertIn("Environment=ENABLE_RETRIEVAL_QUERY_GENERATION=false", quadlet)

    def test_package_standard_ollama_is_03215(self) -> None:
        helper = (ROOT / "cmd/system/install-ollama.sh").read_text(encoding="utf-8")
        installer = (ROOT / "install").read_text(encoding="utf-8")
        verify = (ROOT / "cmd/monitoring/verify-server.sh").read_text(encoding="utf-8")
        self.assertIn('VERSION="${OLLAMA_VERSION:-0.32.15}"', helper)
        self.assertIn('requested="${OLLAMA_VERSION:-0.32.15}"', installer)
        self.assertIn("package standard 0.32.15", verify)

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

    def test_open_webui_v0110_is_digest_pinned(self) -> None:
        quadlet = (ROOT / "config/containers/open-webui.container").read_text(
            encoding="utf-8"
        )
        self.assertIn("# v0.11.0, pinned OCI index digest.", quadlet)
        self.assertIn(
            "Image=ghcr.io/open-webui/open-webui@sha256:"
            "72c0ba641ba75e7aa52655cb242570906ececd09b1140fb736483038a22b3228",
            quadlet,
        )
        self.assertNotRegex(quadlet, r"(?m)^Image=.*:(?:latest|v0\.11\.0)$")

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
        self.assertIn('/var/cache/bc250-llm-server/40cu', helper)
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


if __name__ == "__main__":
    unittest.main()
