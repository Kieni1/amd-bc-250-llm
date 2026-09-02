from __future__ import annotations

import re
import subprocess
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
        for path in ROOT.rglob("*.md"):
            relative = path.relative_to(ROOT)
            if any(part in EXCLUDED_DOC_TREES for part in relative.parts):
                continue
            text = path.read_text(encoding="utf-8")
            blocks = re.findall(r"```(?:bash|text)?\n(.*?)```", text, re.DOTALL)
            for block in blocks:
                for suffix in re.findall(r"\bbc250-([a-z0-9-]+)\b", block):
                    self.assertIn(suffix, allowed, f"{relative}: bc250-{suffix}")

    def test_open_webui_limits_and_current_catalog_prose_are_consistent(self) -> None:
        settings = (ROOT / "docs/openwebui-settings.md").read_text(encoding="utf-8")
        experiments = (ROOT / "models/experiments/README.md").read_text(encoding="utf-8")
        maintenance = (ROOT / "docs/MAINTENANCE.md").read_text(encoding="utf-8")
        self.assertIn("128 MiB per file", settings)
        self.assertIn("256 MiB reverse-proxy ceiling", settings)
        self.assertIn("0.9.7-0.11 catalog", experiments)
        self.assertNotIn("0.9.7-0.10 catalog", experiments)
        self.assertIn("bc250-openwebui-setup init", settings)
        self.assertIn("custom_params.think=false", maintenance)

    def test_model_admin_docs_use_canonical_categories_and_sudo_listing(self) -> None:
        commands = (ROOT / "docs/COMMANDS.md").read_text(encoding="utf-8")
        models = (ROOT / "models/README.md").read_text(encoding="utf-8")
        self.assertIn("`mtp` and `all`", commands)
        self.assertIn("Legacy category aliases are intentionally not accepted", commands)
        self.assertIn("sudo bc250-model cleanup all --keep-gguf", models)
        for text in (commands, models):
            for legacy in ("`tasker`", "`coding`", "`embedded`", "`embed`"):
                self.assertNotIn(legacy, text)

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

        experiment_doc = (ROOT / "models/experiments/README.md").read_text(
            encoding="utf-8"
        )
        documented_experiments = set(
            re.findall(r"(?m)^exp-[a-z0-9.-]+$", experiment_doc)
        )
        self.assertEqual(
            documented_experiments, {name for name in names if name.startswith("exp-")}
        )

        recommended = (
            "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl",
            "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl",
            "prod-lfm25-8b-a1b-liquidai-q6-k",
            "prod-gpt-oss20b-ggml-org-mxfp4",
            "embed-jina-v5-small-retrieval-q4-k-m",
            "task-gemma3-1b-unsloth-ud-q4-k-xl",
            "agentic-qwen25-coder7b-unsloth-q5-k-m",
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for name in recommended:
            self.assertIn(name, names)
            self.assertIn(name, readme)


if __name__ == "__main__":
    unittest.main()
