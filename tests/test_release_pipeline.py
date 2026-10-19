from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def release_contract() -> dict:
    return json.loads((ROOT / "release-contract.json").read_text(encoding="utf-8"))


def plan_stage_ids(plan: str) -> list[str]:
    stages: list[str] = []
    for line in plan.splitlines():
        match = re.match(r"^\d+\. ([^(]+?)(?: \(|$)", line)
        if match:
            stages.append(match.group(1).strip())
    return stages


def make_recipe(target: str) -> str:
    lines = (ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    header = re.compile(rf"^{re.escape(target)}(?:\s+[^:]*)?:")
    next_target = re.compile(r"^[A-Za-z0-9_.%+/-]+(?:\s+[^:]*)?:")
    for index, line in enumerate(lines):
        if not header.match(line):
            continue
        body = [line]
        for candidate in lines[index + 1 :]:
            if candidate and not candidate[0].isspace() and next_target.match(candidate):
                break
            body.append(candidate)
        return "\n".join(body)
    raise AssertionError(f"missing Makefile target: {target}")


def local_plan(*args: str) -> str:
    result = subprocess.run(
        ["bash", str(ROOT / "build-local.sh"), *args, "--plan"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


class ReleasePipelineTests(unittest.TestCase):
    def test_ci_is_static_only_and_runs_repository_validation(self) -> None:
        workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(encoding="utf-8")
        self.assertRegex(workflow, r"(?m)^  push:$")
        self.assertRegex(workflow, r"(?m)^  pull_request:$")
        self.assertNotIn("rpmbuild", workflow)
        self.assertNotIn("make release-gate", workflow)
        self.assertNotIn("upload-artifact", workflow)
        self.assertIn("make lint", workflow)
        self.assertIn("make validate", workflow)

    def test_release_contract_helper_exposes_current_release_identity(self) -> None:
        contract = release_contract()
        for field, expected in (
            ("package.version", contract["package"]["version"]),
            ("package.rpm_release", contract["package"]["rpm_release"]),
            ("package.fedora", contract["package"]["fedora"]),
            ("runtime.ollama", contract["runtime"]["ollama"]),
            ("gfx1013.patch_reference_kernel", contract["gfx1013"]["patch_reference_kernel"]),
            ("gfx1013.qualification_kernel", contract["gfx1013"]["qualification_kernel"]),
        ):
            result = subprocess.run(
                ["python3", str(ROOT / "scripts/release-contract.py"), "field", field],
                cwd=ROOT, text=True, capture_output=True, check=True,
            )
            self.assertEqual(result.stdout.strip(), str(expected))

    def test_full_plan_is_driven_by_release_contract_and_fail_fast(self) -> None:
        contract = release_contract()
        expected = [stage["id"] for stage in contract["validation"]["full_plan"]]
        plan = local_plan("--full", "--allow-dirty")
        self.assertEqual(plan_stage_ids(plan), expected)
        self.assertEqual(expected[0], "sudo authentication")
        self.assertLess(expected.index("sudo authentication"), expected.index("release-gate-preflight"))
        self.assertLess(expected.index("release-gate-preflight"), expected.index("release-gate-postprovision"))
        self.assertIn("engineering-only dirty source allowed", plan)

    def test_dirty_override_is_explicit_not_hardcoded(self) -> None:
        driver = (ROOT / "build-local.sh").read_text(encoding="utf-8")
        help_text = subprocess.run(
            ["bash", str(ROOT / "build-local.sh"), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        self.assertIn("--allow-dirty", help_text)
        self.assertNotRegex(driver, r"(?m)^BC250_ALLOW_DIRTY_FULL=")
        self.assertIn('${BC250_ALLOW_DIRTY_FULL:-0}', driver)
        self.assertIn("release_qualified", driver)
        self.assertIn("GIT_SNAPSHOT_VERIFIED", driver)
        self.assertIn("verify_frozen_source_identity", driver)
        self.assertIn("FULL ENGINEERING GATE PASSED", driver)

    def test_configured_in_repo_build_root_is_not_scanned_as_source(self) -> None:
        driver = (ROOT / "build-local.sh").read_text(encoding="utf-8")
        self.assertIn('export BC250_LOCAL_BUILD_ROOT="$BUILD_HOME"', driver)
        with tempfile.TemporaryDirectory(prefix=".bc250-generated-", dir=ROOT) as tmp:
            generated = Path(tmp)
            (generated / "stale.sh").write_text("bc250-benchmark\n", encoding="utf-8")
            result = subprocess.run(
                ["python3", str(ROOT / "scripts/validate.py")],
                cwd=ROOT,
                env={**os.environ, "BC250_LOCAL_BUILD_ROOT": str(generated)},
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_workspace_cache_and_sccache_contract(self) -> None:
        driver = (ROOT / "build-local.sh").read_text(encoding="utf-8")
        for token in (
            'BUILD_HOME="${BC250_LOCAL_BUILD_ROOT:-$REPO/.build}"',
            'RUN_ROOT="$BUILD_HOME/runs/$STAMP"',
            'WORK_DIR="$RUN_ROOT/work"',
            'RPM_DIR="$RUN_ROOT/rpmbuild"',
            'ARTIFACT_DIR="$RUN_ROOT/artifacts"',
            'LOG_DIR="$RUN_ROOT/logs"',
            'CACHE_ROOT="$BUILD_HOME/cache"',
            'export SCCACHE_DIR="$CACHE_ROOT/sccache"',
            'export RUSTC_WRAPPER=sccache',
            'sccache statistics (before)',
            'sccache statistics (after)',
        ):
            self.assertIn(token, driver)
        self.assertNotIn("sccache --zero-stats", driver)

    def test_sudo_is_one_interactive_auth_then_noninteractive_use(self) -> None:
        driver = (ROOT / "build-local.sh").read_text(encoding="utf-8")
        self.assertEqual(driver.count("sudo -v"), 1)
        self.assertIn("sudo -n -v", driver)
        self.assertIn("sudo -n env BC250_GFX1013_KERNEL=", driver)
        self.assertIn("sudo -n chown -R", driver)
        plan = local_plan("--full")
        self.assertLess(plan.index("sudo authentication"), plan.index("release-gate-preflight"))

    def test_build_driver_timestamps_major_checkpoints(self) -> None:
        driver = (ROOT / "build-local.sh").read_text(encoding="utf-8")
        self.assertIn("checkpoint()", driver)
        self.assertIn("finish_stage()", driver)
        self.assertIn("date --iso-8601=seconds", driver)
        self.assertIn("stage elapsed", driver)
        self.assertIn('checkpoint "build start"', driver)
        self.assertIn('checkpoint "frozen source identity verified"', driver)
        self.assertIn('checkpoint "build command phase complete"', driver)

    def test_successful_build_prints_main_rpm_path_as_final_output_line(self) -> None:
        driver = (ROOT / "build-local.sh").read_text(encoding="utf-8")
        self.assertIn("FINAL_MAIN_RPM=''", driver)
        self.assertIn('FINAL_MAIN_RPM="$(main_rpm)"', driver)
        self.assertRegex(
            driver,
            r'echo "Result:\s+\$RESULT"\nif \(\(rc == 0\)\); then\n  echo "\$FINAL_MAIN_RPM"\nfi\nexit "\$rc"\s*$',
        )

    def test_makefile_preflight_is_cheap_and_postprovision_owns_heavy_gates(self) -> None:
        preflight = make_recipe("release-gate-preflight")
        post = make_recipe("release-gate-postprovision")
        self.assertIn("$(MAKE) clean", preflight)
        self.assertIn("$(MAKE) sources", preflight)
        self.assertIn("$(MAKE) lint", preflight)
        self.assertIn("$(MAKE) preflight", preflight)
        self.assertNotIn("gfx1013-kernel-build-check", preflight)
        self.assertNotIn("gfx1013-mesa-build-check", preflight)
        self.assertLess(post.index("$(MAKE) gfx1013-kernel-build-check"), post.index("$(MAKE) gfx1013-mesa-build-check"))
        self.assertIn("$(MAKE) freeze-rpm-inputs", preflight)
        self.assertIn("$(MAKE) check-frozen-source", preflight)
        self.assertLess(preflight.index("$(MAKE) freeze-rpm-inputs"), preflight.index("$(MAKE) check-frozen-source"))
        self.assertLess(post.index("RPM_TREE_TARGET=rpm-tree-frozen rpm"), post.index("rpmlint -c packaging/rpmlint.toml"))
        self.assertLess(post.index("rpmlint -c packaging/rpmlint.toml"), post.index("$(MAKE) check-srpm-rebuild"))

    def test_gfx_production_checks_use_real_builders(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        kernel_gate = (ROOT / "scripts/check-gfx1013-kernel-build.sh").read_text(encoding="utf-8")
        gfx = (ROOT / "cmd/system/gfx1013.sh").read_text(encoding="utf-8")
        self.assertIn("./scripts/check-gfx1013-kernel-build.sh", makefile)
        self.assertIn('source "$$1/cmd/system/gfx1013.sh"; build_mesa', makefile)
        for token in ("build_kernel_module", "validate_built_module_identity", "kernel-source-provenance.txt"):
            self.assertIn(token, kernel_gate)
        self.assertIn('release-contract.py" field gfx1013.qualification_kernel', kernel_gate)
        self.assertIn("srcversion", kernel_gate)
        self.assertIn("-Dplatforms=[]", gfx)
        self.assertNotIn("-Dplatforms=x11,wayland", gfx)

    def test_clean_full_build_reports_release_gate_qualification(self) -> None:
        driver = (ROOT / "build-local.sh").read_text(encoding="utf-8")
        self.assertIn("Qualification: full release gate PASS", driver)
        self.assertIn("Qualification: engineering only ($GIT_STATE source)", driver)

    def test_artifact_manifests_are_closed(self) -> None:
        recipe = make_recipe("artifact-manifests")
        self.assertIn('sha256sum "$${binary_rpms[@]}" > SHA256SUMS.binary', recipe)
        self.assertIn('sha256sum "$${source_rpms[@]}" > SHA256SUMS.source', recipe)
        self.assertIn("sha256sum -c SHA256SUMS.binary", recipe)
        self.assertIn("sha256sum -c SHA256SUMS.source", recipe)

    def test_build_locale_is_portable(self) -> None:
        workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(encoding="utf-8")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertRegex(workflow, r"(?m)^  LANG: C$")
        self.assertRegex(workflow, r"(?m)^  LC_ALL: C$")
        self.assertIn("export LANG := C", makefile)
        self.assertIn("export LC_ALL := C", makefile)

    def test_output_directory_is_single_authority(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        driver = (ROOT / "build-local.sh").read_text(encoding="utf-8")
        self.assertIn("DISTDIR ?= $(CURDIR)/dist", makefile)
        self.assertIn('"DISTDIR=$ARTIFACT_DIR"', driver)
        self.assertNotIn("$ROOT/dist/*.x86_64.rpm", (ROOT / "scripts/release-diagnostics.sh").read_text(encoding="utf-8"))

    def test_release_diagnostics_do_not_weaken_release_gate(self) -> None:
        diagnostics = (ROOT / "scripts/release-diagnostics.sh").read_text(encoding="utf-8")
        release_gate = make_recipe("release-gate")
        self.assertIn("failures=$((failures + 1))", diagnostics)
        self.assertIn("release-gate-preflight", release_gate)
        self.assertIn("release-gate-postprovision", release_gate)

    def test_validation_layers_release_and_package_contracts(self) -> None:
        validator = (ROOT / "scripts/validate.sh").read_text(encoding="utf-8")
        spec = (ROOT / "packaging/bc250-llm-server.spec").read_text(encoding="utf-8")
        self.assertIn("--preflight", validator)
        self.assertIn("--package", validator)
        self.assertIn("release-contract.py field validation.release_pipeline_test", validator)
        self.assertIn("bash scripts/validate.sh --package </dev/null", spec)

    def test_full_release_uses_frozen_validated_rpm_inputs(self) -> None:
        freeze = make_recipe("freeze-rpm-inputs")
        frozen_tree = make_recipe("rpm-tree-frozen")
        self.assertIn("source-tar", freeze.splitlines()[0])
        self.assertIn("cp -f packaging/$(NAME).spec $(FROZEN_SPEC)", freeze)
        self.assertIn("RPM-INPUTS.sha256", freeze)
        self.assertIn("sha256sum -c", frozen_tree)
        self.assertIn("$(FROZEN_SPEC)", frozen_tree)

    def test_frozen_source_gate_validates_exact_archive_before_heavy_work(self) -> None:
        freeze = make_recipe("freeze-rpm-inputs")
        gate = make_recipe("check-frozen-source")
        preflight = make_recipe("release-gate-preflight")
        self.assertIn("tar -xzf", freeze)
        self.assertIn("$(FROZEN_SOURCE_PARENT)", freeze)
        self.assertIn("sha256sum -c", gate)
        self.assertIn("$(FROZEN_SOURCE_DIR)", gate)
        self.assertIn("cmp -s", gate)
        self.assertIn("bash scripts/validate.sh --package </dev/null", gate)
        self.assertIn("env -u BC250_BUILD_DIR -u BC250_SOURCE_DIR -u BC250_GFX1013_CACHE_ROOT", gate)
        self.assertLess(preflight.index("$(MAKE) check-frozen-source"), len(preflight))
        post = make_recipe("release-gate-postprovision")
        self.assertNotIn("check-frozen-source", post)

    def test_full_driver_runs_privileged_and_heavy_steps_from_frozen_source(self) -> None:
        driver = (ROOT / "build-local.sh").read_text(encoding="utf-8")
        self.assertIn('FROZEN_SOURCE_ROOT="$WORK_DIR/frozen-source/$PACKAGE_NAME-$PACKAGE_VERSION"', driver)
        self.assertIn('BUILD_SOURCE_ROOT="$FROZEN_SOURCE_ROOT"', driver)
        self.assertIn('"$BUILD_SOURCE_ROOT/scripts/provision-gfx1013-kernel-builddeps.sh"', driver)
        self.assertIn('make -C "$BUILD_SOURCE_ROOT" "${MAKE_VARS[@]}" release-gate-postprovision', driver)
        self.assertIn('"release_contract_sha256": contract_sha256', driver)
        self.assertIn('"frozen_rpm_inputs": frozen_inputs', driver)
        self.assertIn('"git_snapshot_verified": snapshot_verified_bool', driver)


if __name__ == "__main__":
    unittest.main()
