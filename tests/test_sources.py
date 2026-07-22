from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


def load_prepare_sources():
    path = ROOT / "scripts/prepare-sources.py"
    spec = importlib.util.spec_from_file_location("bc250_prepare_sources_tests", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourceManifestTests(unittest.TestCase):
    def test_manifest_describes_four_rpm_inputs_without_digest_bookkeeping(self) -> None:
        prepare = load_prepare_sources()
        sources = prepare.load_sources()
        self.assertEqual(len(prepare.source_files(sources)), 4)
        for source in sources:
            self.assertNotIn("sha256", source)
            self.assertNotIn("required", source)
            self.assertNotIn("vendor_sha256", source)

    def test_existing_nonempty_archive_is_reused(self) -> None:
        prepare = load_prepare_sources()
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "cached.tar.gz"
            archive.write_bytes(b"cached")
            prepare.download(
                {"url": "https://invalid.example/{commit}", "commit": "a" * 40},
                archive,
                force=False,
            )
            self.assertEqual(archive.read_bytes(), b"cached")


if __name__ == "__main__":
    unittest.main()
