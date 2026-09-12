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

    def test_source_checksum_fast_path_uses_sidecar_stat_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "model.gguf"
            source.write_bytes(b"same")
            checksum = storage.digest(source)
            stat = source.stat()
            state = {
                "schema": 2,
                "sha256": checksum,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "ctime_ns": stat.st_ctime_ns,
            }
            with patch.object(storage, "digest", side_effect=AssertionError("rehash should not run")):
                self.assertTrue(storage.source_checksum_valid(source, checksum, state))

    def test_canonical_source_label_prefers_model_identity(self) -> None:
        source = Path("/var/lib/bc250-llm-server/gguf/experiments/Qwen3.8-4B-Q6_K.gguf")
        self.assertEqual(
            storage.source_label(source, {"model_name": "exp-qwen38-4b-distill-empero-q6-k"}, {}),
            "exp-qwen38-4b-distill-empero-q6-k",
        )

    def test_recorded_dedupe_pair_is_not_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source.gguf"; blob = base / "main" / "blobs" / ("sha256-" + "a" * 64)
            source.write_bytes(b"same"); blob.parent.mkdir(parents=True); blob.write_bytes(b"same")
            state = {"dedupe": {storage.dedupe_key(blob): {"source": storage.stat_signature(source), "blob": storage.stat_signature(blob)}}}
            self.assertTrue(storage.dedupe_record_matches(source, blob, state))


    def test_tree_bytes_reports_unavailable_when_root_is_not_traversable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "protected"
            root.mkdir()
            with patch.object(storage.os, "access", return_value=False):
                self.assertIsNone(storage.tree_bytes(root))

    def test_schema1_sidecar_does_not_use_stat_only_checksum_fast_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "model.gguf"
            source.write_bytes(b"same")
            checksum = storage.digest(source)
            stat = source.stat()
            state = {
                "schema": 1,
                "sha256": checksum,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "ctime_ns": stat.st_ctime_ns,
            }
            with patch.object(storage, "digest", return_value=checksum) as rehash:
                self.assertTrue(storage.source_checksum_valid(source, checksum, state))
                rehash.assert_called_once_with(source)

    def test_dedupe_record_writes_merge_latest_sidecar_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source.gguf"
            source.write_bytes(b"same")
            state_path = base / "source.gguf.bc250.json"
            state_path.write_text(json.dumps({"schema": 3, "sha256": "a" * 64}), encoding="utf-8")
            blobs = []
            for lane in ("main", "task"):
                blob = base / lane / "blobs" / ("sha256-" + "a" * 64)
                blob.parent.mkdir(parents=True)
                blob.write_bytes(b"same")
                blobs.append(blob)
            stale = json.loads(state_path.read_text())
            with patch.object(storage.os, "chown"):
                storage.write_dedupe_record(state_path, source, blobs[0], stale)
                storage.write_dedupe_record(state_path, source, blobs[1], stale)
            result = json.loads(state_path.read_text())
            self.assertEqual(set(result["dedupe"]), {storage.dedupe_key(blob) for blob in blobs})


    def test_dedupe_pair_batches_all_16m_ranges_into_one_xfs_io_process(self) -> None:
        alias = Path("/tmp/source")
        blob = Path("/tmp/blob")
        size = storage.DEDUPE_CHUNK_BYTES * 2 + 7
        with patch.object(storage.subprocess, "run") as run:
            ranges = storage.dedupe_pair(alias, blob, size)
        self.assertEqual(ranges, 3)
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[0], "xfs_io")
        self.assertEqual(command[-1], str(blob))
        self.assertEqual(command.count("-c"), 3)
        self.assertIn(
            f"dedupe -q {alias} 0 0 {storage.DEDUPE_CHUNK_BYTES}",
            command,
        )

    def test_dedupe_targets_only_manifest_referenced_pairs(self) -> None:
        source = (ROOT / "cmd/system/storage.py").read_text()
        self.assertIn("live_pairs = [pair for pair in all_pairs if blob_referenced(pair[1])]", source)
        self.assertIn("unreferenced source-hash blobs", source)

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
        self.assertIn("source_checksum_valid(source, checksum, state)", source)
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
        self.assertIn("not source_checksum_valid(source, checksum, state) or digest(blob) != checksum", source)
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
