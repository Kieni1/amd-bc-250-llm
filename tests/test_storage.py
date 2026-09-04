from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bc250_storage", ROOT / "cmd/system/storage.py")
storage = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(storage)


class StorageTests(unittest.TestCase):
    def test_state_pairs_keep_multiple_ollama_lanes_for_one_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); gguf = base / "gguf"; ollama = base / "ollama"
            source = gguf / "embedding" / "model.gguf"; source.parent.mkdir(parents=True)
            source.write_bytes(b"same")
            checksum = storage.digest(source)
            source.with_name(source.name + ".bc250.json").write_text(json.dumps({"sha256": checksum}))
            for lane in ("main", "embedding"):
                blob = ollama / lane / "blobs" / f"sha256-{checksum}"
                blob.parent.mkdir(parents=True); blob.write_bytes(b"same")
            with patch.object(storage, "GGUF", gguf), patch.object(storage, "OLLAMA", ollama):
                pairs = storage.state_pairs()
            self.assertEqual(len(pairs), 2)
            self.assertEqual({pair[1].parents[1].name for pair in pairs}, {"main", "embedding"})

    def test_stale_40cu_cache_means_removed_kernel_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "cache"; modules = Path(temporary) / "modules"
            (cache / "current").mkdir(parents=True); (cache / "old").mkdir()
            (modules / "current").mkdir(parents=True)
            original = storage.Path
            def mapped(*parts):
                path = original(*parts)
                if str(path).startswith("/usr/lib/modules"):
                    suffix = path.relative_to("/usr/lib/modules")
                    return modules / suffix
                return path
            with patch.object(storage, "CU_CACHE", cache), patch.object(storage, "Path", side_effect=mapped):
                stale = storage.stale_cu_caches()
            self.assertEqual([path.name for path in stale], ["old"])

    def test_dedupe_requires_explicit_confirmation_by_default(self) -> None:
        source = (ROOT / "cmd/system/storage.py").read_text()
        self.assertIn("Type DEDUPLICATE", source)
        self.assertIn("digest(source) != checksum", source)
        self.assertIn("reflink=1", source)
        self.assertIn("16 * 1024**2", source)

    def test_blob_reference_requires_live_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lane = Path(temporary) / "main"
            checksum = "a" * 64
            blob = lane / "blobs" / f"sha256-{checksum}"
            blob.parent.mkdir(parents=True); blob.write_bytes(b"same")
            self.assertFalse(storage.blob_referenced(blob))
            manifest = lane / "manifests" / "registry.ollama.ai" / "library" / "model" / "latest"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"layers": [{"digest": f"sha256:{checksum}"}]}))
            self.assertTrue(storage.blob_referenced(blob))

    def test_source_prune_is_hash_verified_registered_and_excludes_mtp(self) -> None:
        source = (ROOT / "cmd/system/storage.py").read_text()
        self.assertIn("digest(source) != checksum or digest(blob) != checksum", source)
        self.assertIn("not blob_referenced(blob)", source)
        self.assertIn('Path("mtp") in source.relative_to(GGUF).parents', source)
        self.assertIn("PRUNE-SOURCES", source)

    def test_dedupe_quiesce_and_restore_failures_are_not_ignored(self) -> None:
        source = (ROOT / "cmd/system/storage.py").read_text()
        self.assertIn("def quiesce_services()", source)
        self.assertIn('["systemctl", "stop", unit], check=True', source)
        self.assertIn("services still active after stop", source)
        self.assertIn("failed to restore previously active services", source)
        self.assertIn("finally:", source)
        self.assertNotIn("error: Exception | None", source)


if __name__ == "__main__":
    unittest.main()
