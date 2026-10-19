from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def make_recipe(target: str) -> str:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(rf"(?ms)^{re.escape(target)}:(.*?)(?=^\S[^\n]*:|\Z)", text)
    if not match:
        raise AssertionError(f"missing Make target: {target}")
    return match.group(0)


class ReleasePipelineTests(unittest.TestCase):
    def test_contract_is_core_only_and_github_primary(self) -> None:
        contract = json.loads((ROOT / "release-contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["schema"], "bc250.release-contract.v2")
        self.assertEqual(contract["authority"]["primary"]["kind"], "github-actions")
        self.assertEqual(contract["authority"]["secondary"]["kind"], "local-reproduction")
        self.assertEqual(contract["authority"]["primary"]["selection_event"], "workflow_dispatch")
        self.assertEqual(contract["authority"]["primary"]["selection_record"], "release-selection.json")
        self.assertEqual(contract["build_root"]["make_override"], "BUILD_DIR")
        self.assertNotIn("gfx", json.dumps(contract).lower())
        self.assertEqual(
            [stage["id"] for stage in contract["validation"]["stages"]],
            ["preflight-freeze", "frozen-package", "artifact-evidence"],
        )

    def test_contract_matches_current_package_and_runtime_identity(self) -> None:
        contract = json.loads((ROOT / "release-contract.json").read_text(encoding="utf-8"))
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        runtime = (ROOT / "config/runtime.env").read_text(encoding="utf-8")
        self.assertEqual(contract["package"]["version"], version)
        self.assertRegex(spec, rf"(?m)^Version:\s+{re.escape(version)}$")
        self.assertRegex(spec, rf"(?m)^Release:\s+{re.escape(contract['package']['rpm_release'])}%")
        self.assertIn(f"BC250_OLLAMA_VERSION={contract['runtime']['ollama']}", runtime)

    def test_workflow_runs_primary_gate_as_unprivileged_builder(self) -> None:
        workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(encoding="utf-8")
        self.assertIn("container:\n      image: fedora:44", workflow)
        self.assertIn("runuser -u bc250-builder", workflow)
        self.assertIn("make release-gate", workflow)
        self.assertIn('BC250_REQUIRE_GIT_SOURCE: "1"', workflow)
        self.assertIn('release_authority:', workflow)
        self.assertIn("BC250_RELEASE_AUTHORITY", workflow)
        self.assertIn("Upload selected release authority record", workflow)
        self.assertIn("--disable-repo=fedora-cisco-openh264", workflow)
        self.assertNotIn("build-local.sh", workflow)

    def test_local_ci_is_backup_and_builds_unprivileged(self) -> None:
        local = (ROOT / "scripts/ci-local.sh").read_text(encoding="utf-8")
        self.assertIn("must be invoked by a non-root workspace owner", local)
        self.assertIn("runuser -u bc250-builder", local)
        self.assertIn("make release-gate", local)
        self.assertIn("BC250_REQUIRE_GIT_SOURCE=0", local)
        self.assertIn("BC250_RELEASE_AUTHORITY=false", local)
        self.assertIn("BC250_BUILD_IMAGE_REF", local)
        self.assertIn("--disable-repo=fedora-cisco-openh264", local)
        self.assertNotIn("gfx" + "1013", local.lower())

    def test_release_gate_freezes_inputs_before_package_build(self) -> None:
        preflight = make_recipe("release-gate-preflight")
        package = make_recipe("release-gate-package")
        gate = make_recipe("release-gate")
        self.assertLess(preflight.index("$(MAKE) preflight"), preflight.index("$(MAKE) freeze-rpm-inputs"))
        self.assertLess(preflight.index("$(MAKE) freeze-rpm-inputs"), preflight.index("$(MAKE) check-frozen-source"))
        self.assertIn("RPM_TREE_TARGET=rpm-tree-frozen rpm", package)
        self.assertIn("$(FROZEN_SOURCE_DIR)/packaging/rpmlint.toml", package)
        self.assertIn("-C '$(FROZEN_SOURCE_DIR)'", package)
        self.assertLess(gate.index("release-gate-preflight"), gate.index("release-gate-package"))

    def test_frozen_input_contract_hashes_source0_and_spec(self) -> None:
        freeze = make_recipe("freeze-rpm-inputs")
        frozen = make_recipe("rpm-tree-frozen")
        check = make_recipe("check-frozen-source")
        self.assertIn("check-release-source.sh", freeze)
        self.assertIn("RPM-INPUTS.sha256", freeze)
        self.assertIn("sha256sum -c", frozen)
        self.assertIn("$(FROZEN_SPEC)", frozen)
        self.assertIn("cmp -s", check)
        self.assertIn("validate.sh --preflight", check)

    def test_package_check_excludes_only_host_release_contract_tests(self) -> None:
        validator = (ROOT / "scripts/validate.sh").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertIn("all|--preflight|--package", validator)
        self.assertIn("release_pipeline_test", validator)
        self.assertIn('if [[ "$mode" == "--package" && "$test_file" == "$release_pipeline_test" ]]', validator)
        self.assertIn("bash scripts/validate.sh --package </dev/null", spec)

    def test_source_tar_supports_custom_build_root_and_prunes_empty_dirs(self) -> None:
        source = (ROOT / "scripts/make-source-tarball.sh").read_text(encoding="utf-8")
        self.assertIn('OUT_DIR="${BC250_BUILD_DIR:-$ROOT/build}"', source)
        self.assertIn("--exclude='./.build'", source)
        self.assertIn('exclude_args+=(--exclude="./$output_relative")', source)
        self.assertIn('find "$stage" -depth -type d -empty -delete', source)

    def test_git_source_tar_uses_tracked_files_only_and_excludes_ignored_junk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            (root / "scripts").mkdir(parents=True)
            (root / "packaging").mkdir()
            source_script = root / "scripts/make-source-tarball.sh"
            source_script.write_text(
                (ROOT / "scripts/make-source-tarball.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            source_script.chmod(0o755)
            (root / "VERSION").write_text("0.13.1\n", encoding="utf-8")
            (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
            (root / ".gitignore").write_text(".DS_Store\n/build/\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "tests@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "BC250 tests"], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
            (root / ".DS_Store").write_text("ignored workspace junk\n", encoding="utf-8")
            status = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(status.stdout, "")
            build = root / "build"
            completed = subprocess.run(
                ["bash", str(source_script)],
                cwd=root,
                env={
                    **os.environ,
                    "BC250_BUILD_DIR": str(build),
                    "SOURCE_DATE_EPOCH": "1700000000",
                },
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            archive = build / "bc250-llm-server-0.13.1.tar.gz"
            with tarfile.open(archive, "r:gz") as tf:
                names = set(tf.getnames())
            prefix = "bc250-llm-server-0.13.1/"
            self.assertIn(prefix + "tracked.txt", names)
            self.assertIn(prefix + ".gitignore", names)
            self.assertNotIn(prefix + ".DS_Store", names)

    def test_github_source_identity_requires_checked_out_head_to_match_run_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            (root / "scripts").mkdir(parents=True)
            source_script = root / "scripts/check-release-source.sh"
            source_script.write_text(
                (ROOT / "scripts/check-release-source.sh").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            source_script.chmod(0o755)
            (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "tests@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "BC250 tests"], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
            head = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            output = root / "identity.json"
            mismatch = subprocess.run(
                ["bash", str(source_script), str(output)],
                cwd=root,
                env={**os.environ, "GITHUB_ACTIONS": "true", "GITHUB_SHA": "0" * 40},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(mismatch.returncode, 0)
            self.assertIn("HEAD does not match", mismatch.stderr)
            matched = subprocess.run(
                ["bash", str(source_script), str(output)],
                cwd=root,
                env={**os.environ, "GITHUB_ACTIONS": "true", "GITHUB_SHA": head},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(matched.returncode, 0, matched.stdout + matched.stderr)
            identity = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(identity["commit"], head)
            self.assertTrue(identity["clean"])

    def test_source_preparation_supports_isolated_cache_and_work_roots(self) -> None:
        source = (ROOT / "scripts/prepare-sources.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("BC250_SOURCE_DIR"', source)
        self.assertIn('os.environ.get("BC250_BUILD_DIR"', source)
        self.assertIn("shutil.rmtree(work, ignore_errors=True)", source)

    def test_validator_ignores_configured_generated_roots(self) -> None:
        validator = (ROOT / "scripts/validate.py").read_text(encoding="utf-8")
        self.assertIn("dynamic_excluded_roots", validator)
        with tempfile.TemporaryDirectory(prefix=".bc250-generated-", dir=ROOT) as tmp:
            generated = Path(tmp)
            (generated / "stale.py").write_text("this is not python", encoding="utf-8")
            result = subprocess.run(
                ["python3", str(ROOT / "scripts/validate.py")],
                cwd=ROOT,
                env={**os.environ, "BC250_BUILD_DIR": str(generated)},
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_binary_and_source_manifests_are_separate_and_closed(self) -> None:
        recipe = make_recipe("artifact-manifests")
        self.assertIn("SHA256SUMS.binary", recipe)
        self.assertIn("SHA256SUMS.source", recipe)
        self.assertIn("sha256sum -c SHA256SUMS.binary", recipe)
        self.assertIn("sha256sum -c SHA256SUMS.source", recipe)

    def test_payload_gate_checks_transformed_runtime_metadata(self) -> None:
        recipe = make_recipe("check-rpm-payload")
        self.assertIn("rpm2cpio", recipe)
        self.assertIn("cpio -idm", recipe)
        self.assertIn("cmp -s config/runtime.env", recipe)
        self.assertIn("cmp -s VERSION", recipe)
        self.assertIn("stat -c '%a'", recipe)
        self.assertNotIn("gfx" + "1013", recipe.lower())

    def test_release_evidence_distinguishes_producer_from_selected_authority_and_records_environment(self) -> None:
        source = (ROOT / "scripts/release-evidence.py").read_text(encoding="utf-8")
        for field in (
            '"commit_sha"', '"run_id"', '"workflow"', '"workflow_ref"',
            '"source0"', '"spec"', '"binary_rpms"', '"source_rpms"',
            '"producer"', '"release_authority"', '"environment"', '"container_image"',
            '"rpmbuild"', '"rpmlint"', '"python"', '"ruff"', '"shellcheck"',
            '"gcc"', '"cargo"', '"rustc"',
        ):
            self.assertIn(field, source)
        self.assertIn('"schema": "bc250.release-evidence.v2"', source)
        self.assertIn('release authority requires an explicit workflow_dispatch run', source)

    def test_release_selection_binds_exact_selected_github_artifacts(self) -> None:
        source = (ROOT / "scripts/release-selection.py").read_text(encoding="utf-8")
        for field in (
            'bc250.release-selection.v1', '"github_run_id"', '"github_run_attempt"',
            '"nevra"', '"rpm_sha256"', '"srpm_sha256"', '"source0_sha256"',
            '"spec_sha256"', '"release_contract_sha256"',
        ):
            self.assertIn(field, source)
        self.assertIn('workflow_dispatch', source)
        recipe = make_recipe("release-evidence")
        self.assertIn("BC250_RELEASE_AUTHORITY", recipe)
        self.assertIn("release-selection", recipe)

    def test_make_level_custom_build_root_uses_build_dir_only(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("BC250_BUILD_DIR is internal to helper scripts; use BUILD_DIR=/path", makefile)
        self.assertIn("override BC250_BUILD_DIR := $(BUILD_DIR)", makefile)
        clean_env = {key: value for key, value in os.environ.items() if key != "BC250_BUILD_DIR"}
        ok = subprocess.run(
            ["make", "-s", "BUILD_DIR=/tmp/bc250-test-build", "help"],
            cwd=ROOT, env=clean_env, text=True, capture_output=True, check=False,
        )
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        bad = subprocess.run(
            ["make", "-s", "help"], cwd=ROOT,
            env={**clean_env, "BC250_BUILD_DIR": "/tmp/bc250-unsupported-build"},
            text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("BC250_BUILD_DIR is internal", bad.stderr)

    def test_release_evidence_hash_helper_is_correct(self) -> None:
        spec = importlib.util.spec_from_file_location("release_evidence", ROOT / "scripts/release-evidence.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample"
            path.write_bytes(b"abc")
            self.assertEqual(module.sha256(path), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_workflow_uploads_artifact_specific_manifests_and_release_evidence(self) -> None:
        workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(encoding="utf-8")
        self.assertIn("dist/SHA256SUMS.binary", workflow)
        self.assertIn("dist/SHA256SUMS.source", workflow)
        self.assertIn("dist/SHA256SUMS.inputs", workflow)
        self.assertGreaterEqual(workflow.count("dist/release-evidence.json"), 2)

    def test_make_help_states_github_release_authority(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("GitHub artifact is release authority, local execution reproduces the gate", makefile)

    def test_release_pipeline_has_no_gfx_ownership(self) -> None:
        paths = (
            "release-contract.json",
            "scripts/check-release-source.sh",
            "scripts/release-contract.py",
            "scripts/release-evidence.py",
            "scripts/release-selection.py",
            "scripts/ci-local.sh",
            ".github/workflows/build-rpm.yml",
        )
        for relative in paths:
            text = (ROOT / relative).read_text(encoding="utf-8").lower()
            self.assertNotIn("gfx" + "1013", text, relative)


if __name__ == "__main__":
    unittest.main()
