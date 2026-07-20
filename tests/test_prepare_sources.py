from __future__ import annotations

import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts/prepare-sources.py"
SPEC = importlib.util.spec_from_file_location("bc250_prepare_sources_tests", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
prepare_sources = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_sources)


class SourceArchiveTests(unittest.TestCase):
    def _archive(self, root: Path, members: list[str]) -> Path:
        archive = root / "source.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            for name in members:
                data = b"fixture\n"
                info = tarfile.TarInfo(name)
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
        return archive

    @staticmethod
    def _source(archive: Path, required: list[str]) -> dict:
        return {
            "id": "fixture",
            "commit": "a" * 40,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "required": required,
        }

    def test_required_archive_members_are_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = self._archive(Path(temporary), [f"project-{'a' * 40}/tool.sh"])
            source = self._source(archive, ["project-{commit}/tool.sh"])
            prepare_sources.verify_archive(source, archive)
            source["required"].append("project-{commit}/missing.md")
            with self.assertRaisesRegex(prepare_sources.SourceError, "missing required members"):
                prepare_sources.verify_archive(source, archive)

    def test_unlock_lock_matches_the_pinned_archive_contract(self) -> None:
        unlock = next(source for source in prepare_sources.load_sources() if source["id"] == "unlock")
        required = {prepare_sources.expand(item, unlock) for item in unlock["required"]}
        self.assertIn(f"bc250-40cu-unlock-{unlock['commit']}/README.md", required)
        self.assertIn(
            f"bc250-40cu-unlock-{unlock['commit']}/scripts/bc250-enable-40cu-fedora.sh",
            required,
        )


if __name__ == "__main__":
    unittest.main()
