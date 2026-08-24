from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent.parent


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
            "gfx1013",
            "llm-server",
            "night-shutdown",
            "wol",
        }
        for path in ROOT.rglob("*.md"):
            relative = path.relative_to(ROOT)
            if any(part in {"build", "dist", "rpmbuild", "sources"} for part in relative.parts):
                continue
            text = path.read_text(encoding="utf-8")
            blocks = re.findall(r"```(?:bash|text)?\n(.*?)```", text, re.DOTALL)
            for block in blocks:
                for suffix in re.findall(r"\bbc250-([a-z0-9-]+)\b", block):
                    self.assertIn(suffix, allowed, f"{relative}: bc250-{suffix}")

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
        documented_experiments = set(re.findall(r"(?m)^exp-[a-z0-9.-]+$", experiment_doc))
        self.assertEqual(documented_experiments, {name for name in names if name.startswith("exp-")})

        recommended = (
            "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl",
            "prod-gemma4-e4b-unsloth-qat-ud-q4-k-xl",
            "prod-lfm25-8b-a1b-liquidai-q6-k",
            "prod-gpt-oss20b-ggml-org-mxfp4",
            "embed-jina-v5-small-retrieval-q4-k-m",
            "task-gemma3-1b-unsloth-ud-q4-k-xl",
            "agentic-ornith15-9b-ornith-q5-k-m",
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for name in recommended:
            self.assertIn(name, names)
            self.assertIn(name, readme)


if __name__ == "__main__":
    unittest.main()
