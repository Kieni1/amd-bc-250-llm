from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "scripts/install-manifest.py"


class InstallManifestTests(unittest.TestCase):
    def test_overhaul_has_an_upgradeable_package_version(self) -> None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertEqual(version, "0.6.3")
        self.assertIn("Version:        0.6.3", spec)
        self.assertIn("- 0.6.3-0.1.testing", spec)

    def test_installs_files_and_emits_rpm_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "plain.txt").write_text("plain\n", encoding="utf-8")
            (source / "config.toml").write_text("value = 1\n", encoding="utf-8")
            manifest = root / "manifest.tsv"
            manifest.write_text(
                "dir\t0755\t-\t/usr/share/example\n"
                "file\t0644\tplain.txt\t/usr/share/example/plain.txt\n"
                "config\t0640\tconfig.toml\t/etc/example.toml\n"
                "ghost\t0600\t-\t/etc/example.secret\n",
                encoding="utf-8",
            )
            buildroot = root / "buildroot"
            filelist = root / "files.list"
            result = subprocess.run(
                [
                    str(INSTALLER),
                    "--manifest",
                    str(manifest),
                    "--source-root",
                    str(source),
                    "--buildroot",
                    str(buildroot),
                    "--filelist",
                    str(filelist),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((buildroot / "usr/share/example/plain.txt").read_text(), "plain\n")
            listing = filelist.read_text(encoding="utf-8")
            self.assertIn("%config(noreplace) /etc/example.toml", listing)
            self.assertIn("%ghost %config(noreplace) %attr(0600,root,root) /etc/example.secret", listing)

    def test_feature_moves_are_reflected_in_the_package_manifest(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn(
            "config\t0644\tmodels/mtp/models.toml\t{config}/mtp-models.toml",
            manifest,
        )
        for path in (
            "models/embedding/pull-embedding-model.sh",
            "models/experiments/compare-experiments.sh",
            "models/mtp/run-mtp-llamacpp.sh",
        ):
            self.assertIn(path, manifest)
        self.assertNotIn("\nfile\t0755\texperiments/", manifest)

    def test_rpm_upgrade_restarts_web_services_without_legacy_migration(self) -> None:
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        post = spec.split("%post\n", 1)[1].split("%preun", 1)[0]
        upgrade = post.split('if [ "$1" -gt 1 ]; then', 1)[1].split("else", 1)[0]
        self.assertIn("systemctl try-restart tika.service open-webui.service", upgrade)
        self.assertNotIn("migrate-legacy", post)


if __name__ == "__main__":
    unittest.main()
