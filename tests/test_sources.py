from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_prepare_sources():
    path = ROOT / "scripts/prepare-sources.py"
    spec = importlib.util.spec_from_file_location("bc250_prepare_sources_tests", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourceManifestTests(unittest.TestCase):
    def test_manifest_describes_four_rpm_inputs_with_local_cache_integrity(
        self,
    ) -> None:
        prepare = load_prepare_sources()
        sources = prepare.load_sources()
        self.assertEqual(len(prepare.source_files(sources)), 4)
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        for source in sources:
            self.assertIn("repository", source)
            self.assertIn(source["commit"], spec)
            self.assertNotIn("required", source)

    def test_existing_verified_archive_is_reused(self) -> None:
        prepare = load_prepare_sources()
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "cached.tar.gz"
            archive.write_bytes(b"cached")
            prepare.write_checksum(archive)
            prepare.download(
                {"url": "https://invalid.example/{commit}", "commit": "a" * 40},
                archive,
                force=False,
            )
            self.assertEqual(archive.read_bytes(), b"cached")

    def test_changed_cached_archive_is_rejected(self) -> None:
        prepare = load_prepare_sources()
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "cached.tar.gz"
            archive.write_bytes(b"cached")
            prepare.write_checksum(archive)
            archive.write_bytes(b"tampered")
            with self.assertRaises(prepare.SourceError):
                prepare.download(
                    {"url": "https://invalid.example/{commit}", "commit": "a" * 40},
                    archive,
                    force=False,
                )


if __name__ == "__main__":
    unittest.main()
