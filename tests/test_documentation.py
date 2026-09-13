from __future__ import annotations

import glob
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED_DOC_TREES = {
    ".git",
    "build",
    "dist",
    "rpmbuild",
    "sources",
    "governor-src",
    "unlock-src",
    "live-manager-src",
    "__pycache__",
}
NON_PACKAGE_DOC_TREES = {"development"}


def package_markdown_paths():
    for path in ROOT.rglob("*.md"):
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_DOC_TREES for part in relative.parts):
            continue
        if any(part in NON_PACKAGE_DOC_TREES for part in relative.parts):
            continue
        yield path, relative


def dispatcher_aliases() -> set[str]:
    result = subprocess.run(
        [str(ROOT / "packaging/bc250"), "--list-aliases"],
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    )
    return set(result.stdout.splitlines())


class DocumentationTests(unittest.TestCase):
    def test_command_reference_covers_every_public_alias(self) -> None:
        reference = (ROOT / "docs/COMMANDS.md").read_text(encoding="utf-8")
        for alias in sorted(dispatcher_aliases()):
            self.assertIn(f"`bc250-{alias}`", reference, alias)
        for command in ("`bc250`", "`bc250-cu-live-manager`", "`llm-run-diagnose`"):
            self.assertIn(command, reference)

    def test_shell_examples_do_not_invent_bc250_commands(self) -> None:
        allowed = dispatcher_aliases() | {
            "coding-agent",
            "cu-live-manager",
            "documents",
            "gfx1013",
            "llm-server",
            "night-shutdown",
            "wol",
        }
        for path, relative in package_markdown_paths():
            text = path.read_text(encoding="utf-8")
            blocks = re.findall(r"```(?:bash|text)?\n(.*?)```", text, re.DOTALL)
            for block in blocks:
                for suffix in re.findall(r"\bbc250-([a-z0-9-]+)\b", block):
                    self.assertIn(suffix, allowed, f"{relative}: bc250-{suffix}")

    def test_privileged_command_examples_use_sudo(self) -> None:
        privileged = (
            r"bc250-install(?:-ollama)?(?:\s|$)",
            r"bc250-maintenance(?:\s|$)",
            r"bc250-model\s+(?:list|install|cleanup|cleanup-retired)(?:\s|$)",
            r"bc250-storage(?:\s|$)",
            r"bc250-revalidate(?:\s|$)",
            r"bc250-rag-import(?:\s|$)",
            r"bc250-ocr\s+install(?:\s|$)",
            r"bc250-fetch-mtp(?:\s|$)",
            r"bc250-agent-mode\s+(?:enter|leave)(?:\s|$)",
            r"bc250-40cu(?:\s|$)",
            r"bc250-cu-live-manager(?:\s|$)",
            r"bc250-memory-profile\s+(?:ensure|apply-full|remove)(?:\s|$)",
            r"bc250-swap-profile\s+(?:ensure|apply|remove)(?:\s|$)",
            r"bc250-ollama-profile\s+(?:balanced|max-context|reset)(?:\s|$)",
            r"bc250-openwebui-setup\s+(?:init|apply)(?:\s|$)",
            r"bc250-benchmark\s+owui-system-context(?:\s|$)",
            r"bc250-reset(?:\s|$)",
            r"bc250-uninstall(?:\s|$)",
        )
        for path, relative in package_markdown_paths():
            text = path.read_text(encoding="utf-8")
            for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
                for line in block.splitlines():
                    command = line.strip()
                    if not command or command.startswith("#"):
                        continue
                    for pattern in privileged:
                        if re.search(pattern, command):
                            self.assertRegex(command, r"(?:^|\s)sudo(?:\s|$)", f"{relative}: {command}")

    def test_revalidate_reference_covers_public_lifecycle(self) -> None:
        reference = (ROOT / "docs/COMMANDS.md").read_text(encoding="utf-8")
        for form in (
            "sudo bc250-revalidate start --owui-token-file /root/owui-test.key",
            "sudo bc250-revalidate start --skip-owui",
            "sudo bc250-revalidate status",
            "sudo bc250-revalidate status --raw",
            "sudo bc250-revalidate abort",
            "sudo bc250-revalidate cleanup",
        ):
            self.assertIn(form, reference)

    def test_read_only_profile_examples_do_not_require_sudo(self) -> None:
        forbidden = (
            "sudo bc250-memory-profile status",
            "sudo bc250-memory-profile recommend",
            "sudo bc250-swap-profile status",
            "sudo bc250-ollama-profile status",
        )
        for path, relative in package_markdown_paths():
            text = path.read_text(encoding="utf-8")
            for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
                for command in forbidden:
                    self.assertNotIn(command, block, f"{relative}: {command}")

    def test_current_model_docs_distinguish_retired_qwen_distill(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        ollama = (ROOT / "docs/OLLAMA.md").read_text(encoding="utf-8")
        experiments = (ROOT / "models/experiments/README.md").read_text(encoding="utf-8")
        for text in (readme, ollama, experiments):
            self.assertIn("exp-qwen38-4b-distill-empero-q6-k", text)
            self.assertIn("exp-qwen38-4b-empero-q6-k", text)
        self.assertNotIn("Qwen3.8 therefore remains an opt-in experiment", ollama)
        self.assertNotIn("intentional in 0.10", experiments)

    def test_installed_document_layout_preserves_source_paths_and_links(self) -> None:
        manifest = ROOT / "packaging/install-manifest.tsv"
        entries = []
        for raw in manifest.read_text(encoding="utf-8").splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            kind, _mode, source, destination = raw.split("\t")
            if kind != "file" or not destination.startswith("{docdir}"):
                continue
            matches = [Path(item) for item in sorted(glob.glob(str(ROOT / source)))]
            self.assertTrue(matches, source)
            for source_path in matches:
                installed_rel = destination.removeprefix("{docdir}").lstrip("/")
                if destination.endswith("/"):
                    installed_rel = f"{installed_rel.rstrip('/')}/{source_path.name}"
                entries.append((source_path, Path(installed_rel)))
                if source_path.suffix == ".md":
                    self.assertEqual(
                        installed_rel,
                        source_path.relative_to(ROOT).as_posix(),
                        f"documentation path rewrite: {source_path.relative_to(ROOT)}",
                    )

        with tempfile.TemporaryDirectory() as temporary:
            staged = Path(temporary)
            for source_path, installed_rel in entries:
                target = staged / installed_rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target)
            for path in staged.rglob("*.md"):
                text = path.read_text(encoding="utf-8")
                for target in re.findall(r"\[[^]]*\]\(([^)]+)\)", text):
                    if target.startswith(("http://", "https://", "mailto:", "#")):
                        continue
                    local = target.split("#", 1)[0]
                    if local:
                        self.assertTrue(
                            (path.parent / local).exists(),
                            f"installed {path.relative_to(staged)}: {target}",
                        )

    def test_internal_markdown_links_resolve(self) -> None:
        for path in ROOT.rglob("*.md"):
            relative = path.relative_to(ROOT)
            if any(part in EXCLUDED_DOC_TREES for part in relative.parts):
                continue
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^]]*\]\(([^)]+)\)", text):
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                local = target.split("#", 1)[0]
                if local:
                    self.assertTrue(
                        (path.parent / local).exists(), f"{relative}: {target}"
                    )

    def test_documented_model_sets_match_current_modelfiles(self) -> None:
        names = set()
        for path in (ROOT / "models/modelfiles").glob("*.Modelfile"):
            match = re.search(
                r"(?m)^# Ollama model:\s*(\S+)\s*$",
                path.read_text(encoding="utf-8"),
            )
            self.assertIsNotNone(match, path.name)
            names.add(match.group(1))

        models_doc = (ROOT / "MODELS.md").read_text(encoding="utf-8")
        catalog = re.search(
            r"<!-- ACTIVE_EXPERIMENTS:BEGIN -->\n```text\n(.*?)\n```\n<!-- ACTIVE_EXPERIMENTS:END -->",
            models_doc,
            re.DOTALL,
        )
        self.assertIsNotNone(catalog)
        documented_experiments = {
            line.strip() for line in catalog.group(1).splitlines() if line.strip()
        }
        actual_experiments = {name for name in names if name.startswith("exp-")}
        self.assertEqual(documented_experiments, actual_experiments)

        recommended = (
            "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl",
            "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl",
            "prod-lfm25-8b-a1b-liquidai-q6-k",
            "prod-gpt-oss20b-ggml-org-mxfp4",
            "embed-jina-v5-small-retrieval-q4-k-m",
            "task-lfm25-1.2b-instruct-liquidai-q6-k",
            "agentic-ornith15-9b-ornith-q5-k-m",
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for name in recommended:
            self.assertIn(name, names)
            self.assertIn(name, readme)


if __name__ == "__main__":
    unittest.main()
