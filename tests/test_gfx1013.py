from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "cmd/system/gfx1013.sh"
SOURCE = ROOT / "gfx1013/upstream"
SPEC = ROOT / "packaging/bc250-llm-server.spec"


class Gfx1013Tests(unittest.TestCase):
    def test_package_profile_identity_and_selected_patch_set(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("PACKAGE_PROFILE=v0.2.4-alpha", source)
        self.assertIn("UPSTREAM_VERSION=0.2.0-alpha", source)
        self.assertIn("PINNED_COMMIT=d3e6dc062c34d2523db0abe5741d1f5b0dea00d9", source)
        self.assertIn("TESTED_KERNEL=7.2.9-200.fc44.x86_64", source)
        series = (SOURCE / "patches/mesa/series").read_text(encoding="utf-8")
        active = [line.strip() for line in series.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(active, ["0001-gfx1013-compute-queue-fix.patch"])
        self.assertFalse((SOURCE / "patches/mesa/0002-gfx1013-mesh-task-shaders.patch").exists())
        self.assertFalse((SOURCE / "patches/mesa/0003-gfx1013-taskmesh-queries.patch").exists())
        self.assertFalse((SOURCE / "patches/kernel/40cu-bc250-unlock.patch").exists())

    def test_patch_and_full_source_manifests_are_closed_and_valid(self) -> None:
        patch_manifest = SOURCE / "PATCH-SHA256SUMS"
        source_manifest = SOURCE / "SOURCE-SHA256SUMS"
        for manifest in (patch_manifest, source_manifest):
            self.assertTrue(manifest.is_file())
            for line in manifest.read_text(encoding="utf-8").splitlines():
                digest, relative = line.split(None, 1)
                relative = relative.strip()
                target = SOURCE / relative.removeprefix("./")
                self.assertTrue(target.is_file(), relative)
                self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), digest)
        patch_entries = [line.split(None, 1)[1].strip() for line in patch_manifest.read_text().splitlines()]
        self.assertEqual(
            patch_entries,
            [
                "patches/kernel/v33/0001-gfx1013-mmio-pasid-route.patch",
                "patches/kernel/v33/0002-gfx1013-compute-gfxoff-guard.patch",
                "patches/kernel/v33/0003-gfx1013-scoped-pasid-type0.patch",
                "patches/mesa/0001-gfx1013-compute-queue-fix.patch",
            ],
        )
        covered = {line.split(None, 1)[1].strip().removeprefix("./") for line in source_manifest.read_text().splitlines()}
        actual = {
            str(path.relative_to(SOURCE))
            for path in SOURCE.rglob("*")
            if path.is_file() and path.name != "SOURCE-SHA256SUMS"
        }
        self.assertEqual(covered, actual)

    def test_status_verifies_local_package_source_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            env = os.environ.copy()
            env.update(
                {
                    "BC250_GFX1013_SOURCE": str(SOURCE),
                    "BC250_GFX1013_STATE_ROOT": str(tmp / "state"),
                    "BC250_GFX1013_PREFIX_ROOT": str(tmp / "prefix"),
                    "BC250_GFX1013_DROPIN": str(tmp / "dropin.conf"),
                    "BC250_GFX1013_UPSTREAM_GENERATOR": str(tmp / "upstream-generator"),
                    "BC250_GFX1013_UPSTREAM_STATE": str(tmp / "upstream-state"),
                }
            )
            result = subprocess.run(
                [str(SCRIPT), "status"],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("v0.2.4-alpha / experimental / default OFF", result.stdout)
        self.assertIn("Package patch/full-source manifests: PASS", result.stdout)
        self.assertIn("Ollama private-RADV override: disabled", result.stdout)


    def test_status_json_exposes_explicit_lifecycle_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            env = os.environ.copy()
            env.update(
                {
                    "BC250_GFX1013_SOURCE": str(SOURCE),
                    "BC250_GFX1013_STATE_ROOT": str(tmp / "state"),
                    "BC250_GFX1013_PREFIX_ROOT": str(tmp / "prefix"),
                    "BC250_GFX1013_DROPIN": str(tmp / "dropin.conf"),
                    "BC250_GFX1013_UPSTREAM_GENERATOR": str(tmp / "upstream-generator"),
                    "BC250_GFX1013_UPSTREAM_STATE": str(tmp / "upstream-state"),
                }
            )
            result = subprocess.run(
                [str(SCRIPT), "status", "--json"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "bc250.gfx1013-status.v1")
        self.assertEqual(payload["state"], "DISABLED")
        self.assertEqual(payload["profile"], "v0.2.4-alpha")
        self.assertTrue(payload["default_off"])

    def test_16_hardens_secure_boot_stale_kernel_and_private_radv_guard(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for state in (
            "DISABLED",
            "PREPARED",
            "PATCHED_BOOT_UNVERIFIED",
            "ENABLED",
            "ROLLBACK_REQUIRED",
        ):
            self.assertIn(state, source)
        for token in (
            "mokutil --sb-state",
            "unsigned local amdgpu",
            "BC250_GFX1013_PACKAGE_NEVRA",
            "ConditionKernelCommandLine=$PATCH_MARKER",
            "ExecCondition=+$INSTALLED_SELF ollama-guard",
            "loaded amdgpu srcversion differs from prepared module",
            "verify_private_radv_device",
            'vendor.group(1).lower() == "0x1002"',
            'device.group(1).lower() == "0x13fe"',
            'name.lower() != "radv"',
        ):
            self.assertIn(token, source)
        self.assertNotIn("mokutil --import", source)
        self.assertNotIn("sign-file", source)

    def test_secure_boot_unsupported_is_treated_as_explicitly_disabled(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        start = source.index("secure_boot_state() {")
        end = source.index("\nsecure_boot_prepare_ok() {", start)
        function = source[start:end]
        with tempfile.TemporaryDirectory() as temporary:
            mock_mokutil = Path(temporary) / "mokutil"
            mock_mokutil.write_text(
                "#!/usr/bin/env bash\necho \"This system doesn't support Secure Boot\" >&2\nexit 255\n",
                encoding="utf-8",
            )
            mock_mokutil.chmod(0o755)
            env = os.environ | {"PATH": f"{temporary}:{os.environ.get('PATH', '')}"}
            result = subprocess.run(
                ["bash", "-c", function + "\nsecure_boot_state"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "disabled-unsupported")
        self.assertIn("disabled|disabled-non-efi|disabled-unsupported", source)
        self.assertIn('Secure Boot: PASS ($secure)', source)

    def test_optional_build_dependencies_cover_headless_radv_needs_without_gui_devel(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        packages = source[source.index("GFX_BUILD_PACKAGES=("): source.index("build_requirement_provider() {")]
        for requirement in (
            "python3-packaging",
            "python3-pycparser",
            "vulkan-headers",
            "vulkan-loader-devel",
            "systemd-devel",
            "libdrm-devel",
            "pkgconf-pkg-config",
            "glslang-devel",
            "cargo-rpm-macros",
            "git-core",
            "redhat-rpm-config",
            "kernel-srpm-macros",
        ):
            self.assertIn(requirement, packages)
        for gui_requirement in (
            "libdisplay-info-devel",
            "libxcb-devel",
            "libX11-devel",
            "libxshmfence-devel",
            "libXrandr-devel",
            "wayland-devel",
            "wayland-protocols-devel",
        ):
            self.assertNotIn(gui_requirement, packages)
        self.assertIn("readelf", source)
        self.assertIn("missing_build_packages", source)

    def test_private_mesa_build_is_headless_minimal_and_offline(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        build = source[source.index("build_mesa() {"): source.index("pin_private_icd_library() {")]
        for option in (
            "--wrap-mode=nodownload",
            "-Dvulkan-drivers=amd",
            "-Dgallium-drivers=[]",
            "-Dplatforms=[]",
            "-Dglx=disabled",
            "-Degl=disabled",
            "-Dgbm=disabled",
            "-Dgles1=disabled",
            "-Dgles2=disabled",
            "-Dopengl=false",
            "-Dllvm=disabled",
            "-Dvideo-codecs=[]",
            "-Ddisplay-info=disabled",
            "-Dvulkan-layers=[]",
            "-Dtools=[]",
        ):
            self.assertIn(option, build)
        self.assertNotIn("-Dplatforms=x11,wayland", build)
        self.assertIn("verify_headless_radv_stage", build)
        self.assertIn("lib64/libvulkan_radeon.so", build)
        self.assertIn("share/vulkan/icd.d/radeon_icd.x86_64.json", build)

    def test_headless_radv_stage_audit_accepts_system_only_deps_and_rejects_gui_deps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix_root = root / "prefix"
            stage = root / "stage"
            private = stage / prefix_root.relative_to("/") / "0.2.0-alpha"
            (private / "lib64").mkdir(parents=True)
            (private / "share/vulkan/icd.d").mkdir(parents=True)
            (private / "lib64/libvulkan_radeon.so").write_bytes(b"fake")
            (private / "share/vulkan/icd.d/radeon_icd.x86_64.json").write_text(
                json.dumps({"ICD": {"library_path": str(prefix_root / "0.2.0-alpha/lib64/libvulkan_radeon.so")}}) + "\n",
                encoding="utf-8",
            )
            fake_bin = root / "bin"
            fake_bin.mkdir()
            readelf = fake_bin / "readelf"
            readelf.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\n' ' 0x0000000000000001 (NEEDED)             Shared library: [libdrm_amdgpu.so.1]' "
                "' 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]'\n",
                encoding="utf-8",
            )
            readelf.chmod(0o755)
            env = os.environ | {
                "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
                "BC250_GFX1013_LIBRARY_ONLY": "1",
                "BC250_GFX1013_PREFIX_ROOT": str(prefix_root),
            }
            command = (
                f'source {SCRIPT!s}; '
                'verify_headless_radv_stage "$1" "$2"'
            )
            result = subprocess.run(
                ["bash", "-c", command, "bash", str(stage), str(root / "needed.txt")],
                env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            readelf.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\n' ' 0x0000000000000001 (NEEDED)             Shared library: [libxcb.so.1]'\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", "-c", command, "bash", str(stage), str(root / "needed.txt")],
                env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("GUI/WSI", result.stderr)

    def test_private_radv_device_smoke_unsets_graphical_session_variables(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        verifier = source[source.index("verify_private_radv_device() {"): source.index("PREPARE_DIR='", source.index("verify_private_radv_device() {"))]
        self.assertIn("unset DISPLAY WAYLAND_DISPLAY XDG_SESSION_TYPE", verifier)
        self.assertIn("private headless RADV failed Vulkan loader smoke check", verifier)

    def test_check_and_recovery_interfaces_are_non_destructive_before_commit(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("prepare [--check]", source)
        self.assertIn("disable [--check]", source)
        self.assertIn("reset [--check]", source)
        self.assertIn("GFX1013 prepare check: PASS", source)
        self.assertIn("GFX1013 rollback check: PASS", source)
        self.assertIn("No boot state, files or services were changed.", source)
        reset = source[source.index("reset() {"): source.index('case "${1:-status}"')]
        self.assertLess(reset.index("restore_stock_boot"), reset.index("remove_orphaned_package_artifacts"))

    def test_upgrade_rolls_back_old_gfx_profile_before_payload_replacement(self) -> None:
        spec = SPEC.read_text(encoding="utf-8")
        pre = spec[spec.index("%pre"): spec.index("%post")]
        self.assertIn("gfx1013.sh disable --package-upgrade", pre)
        self.assertIn("refusing package upgrade", pre)
        self.assertLess(
            pre.index("gfx1013.sh disable --package-upgrade"),
            pre.index("systemctl stop open-webui.service"),
        )

    def test_lifecycle_is_exact_kernel_stock_first_and_ollama_scoped(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for token in (
            'build="/lib/modules/$kernel/build"',
            "rpm -qp --qf '%{VERSION}-%{RELEASE}",
            "--fuzz=0 --dry-run",
            "modinfo -F vermagic",
            "modprobe --show-modversions",
            "kernel_build_owner",
            "BC250_GFX1013_KERNEL_DEVEL_NEVRA",
            "BC250_GFX1013_PRIVATE_RADV_SHA256",
            "BC250_GFX1013_ICD_SHA256",
            "stock amdgpu changed since prepare",
            "stock initramfs changed since prepare",
            "prepare_cleanup_on_exit",
            '[[ "$current_saved" == "$stock_entry_id" ]]',
            'grub2-editenv - set "next_entry=$patched_id"',
            'enable requires PATCHED_BOOT_UNVERIFIED',
            "VK_DRIVER_FILES=$BC250_GFX1013_ICD",
            'grub2-set-default "$BC250_GFX1013_PATCHED_ENTRY_ID"',
            "enable_cleanup_on_exit",
        ):
            self.assertIn(token, source)
        self.assertNotIn("/etc/environment", source)
        self.assertNotIn("install -m 0755", source[source.find("UPSTREAM_GENERATOR"):])

    def _run_classifier_case(self, *, active: bool, phase: str = "PREPARED", enabled: str = "0", recovery: str = "0", saved: str = "stock", next_entry: str = "patched", patched: bool = False) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            state.mkdir()
            if active:
                (state / "active.env").write_text("placeholder\n", encoding="utf-8")
            env = os.environ.copy()
            env.update(
                {
                    "BC250_GFX1013_LIBRARY_ONLY": "1",
                    "BC250_GFX1013_STATE_ROOT": str(state),
                    "BC250_GFX1013_PREFIX_ROOT": str(root / "prefix"),
                    "BC250_GFX1013_DROPIN": str(root / "dropin"),
                    "CASE_PHASE": phase,
                    "CASE_ENABLED": enabled,
                    "CASE_RECOVERY": recovery,
                    "CASE_SAVED": saved,
                    "CASE_NEXT": next_entry,
                    "CASE_PATCHED": "1" if patched else "0",
                }
            )
            script = rf'''
source "{SCRIPT}"
kernel_release() {{ printf '7.2.9-200.fc44.x86_64\n'; }}
package_nevra() {{ printf 'bc250-llm-server-0.13.1-1.12.x86_64\n'; }}
grub_value() {{ [[ $1 == saved_entry ]] && printf '%s\n' "$CASE_SAVED" || printf '%s\n' "$CASE_NEXT"; }}
patched_boot_running() {{ [[ "$CASE_PATCHED" == 1 ]]; }}
risky_artifacts_without_state() {{ return 1; }}
stock_entry_file_safe() {{ return 0; }}
load_active_state() {{
  [[ -e "$ACTIVE_STATE" ]] || return 1
  BC250_GFX1013_PACKAGE_NEVRA=bc250-llm-server-0.13.1-1.12.x86_64
  BC250_GFX1013_KERNEL=7.2.9-200.fc44.x86_64
  BC250_GFX1013_STOCK_BLS=/boot/loader/entries/stock.conf
  BC250_GFX1013_STOCK_ENTRY_ID=stock
  BC250_GFX1013_PATCHED_ENTRY_ID=patched
  BC250_GFX1013_ICD=/tmp/icd
  BC250_GFX1013_PRIVATE_RADV_LIB=/tmp/radv
  BC250_GFX1013_TRANSACTION_PHASE="$CASE_PHASE"
  BC250_GFX1013_RECOVERY_REQUIRED="$CASE_RECOVERY"
  BC250_GFX1013_ENABLED="$CASE_ENABLED"
}}
gfx_lifecycle_state
printf '%s|%s\n' "$GFX_LIFECYCLE_STATE" "$GFX_STATE_REASON"
'''
            return subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True, check=False)

    def test_greenfield_lifecycle_classifier_fails_closed_on_authority_mismatch(self) -> None:
        cases = (
            ({"active": False, "patched": True}, "ROLLBACK_REQUIRED"),
            ({"active": True, "saved": "other", "next_entry": "unrelated"}, "ROLLBACK_REQUIRED"),
            ({"active": True, "phase": "SAFETY_FAILURE", "recovery": "1", "patched": True, "next_entry": ""}, "ROLLBACK_REQUIRED"),
            ({"active": True, "saved": "stock", "next_entry": "patched", "patched": False}, "PREPARED"),
            ({"active": True, "saved": "stock", "next_entry": "", "patched": True}, "PATCHED_BOOT_UNVERIFIED"),
        )
        for kwargs, expected in cases:
            with self.subTest(kwargs=kwargs):
                result = self._run_classifier_case(**kwargs)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.startswith(expected + "|"), result.stdout)

    def test_enable_guard_lock_and_recovery_are_fail_closed(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        enable = source[source.index("enable() {"): source.index("risky_artifacts_without_state() {")]
        guard = source[source.index("ollama_guard() {"): source.index("write_ollama_dropin() {")]
        cleanup = source[source.index("enable_cleanup_on_exit() {"): source.index("enable() {")]
        reset = source[source.index("reset() {"): source.index('if [[ ${BC250_GFX1013_LIBRARY_ONLY:-0}')]
        orphan = source[source.index("remove_orphaned_package_artifacts() {"): source.index("disable() {")]
        self.assertIn("acquire_lifecycle_lock", enable)
        self.assertIn("enable requires PATCHED_BOOT_UNVERIFIED", enable)
        self.assertIn("BC250_GFX1013_TRANSACTION_PHASE:-", enable)
        self.assertIn("gfx_lifecycle_state", guard)
        self.assertIn('[[ "$GFX_LIFECYCLE_STATE" == ENABLED ]]', guard)
        self.assertLess(enable.index('mv -f "$state_tmp" "$ACTIVE_STATE"'), enable.index("systemctl restart ollama.service"))
        self.assertIn("ollama_enable_smoke", enable)
        self.assertIn("set +e", cleanup)
        self.assertIn('restore_previous_next "$ENABLE_PREVIOUS_NEXT"', cleanup)
        self.assertIn("restore_prepared_state_after_enable_failure", cleanup)
        self.assertNotIn('rm -f -- "$DROPIN" "$UPSTREAM_GENERATOR"', orphan)
        self.assertIn("separate upstream GFX1013 installation is present", orphan)
        self.assertLess(reset.index("separate upstream GFX1013 installation is present"), reset.index("restore_stock_boot"))

    def test_mutating_commands_take_one_nonblocking_lifecycle_lock(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        lock = source[source.index("acquire_lifecycle_lock() {"): source.index("kernel_release() {")]
        self.assertIn("flock -n", lock)
        self.assertIn("LIFECYCLE_LOCK_HELD", lock)
        for function, end_marker in (("prepare() {", "verify_active_identity() {"), ("disable() {", "reset() {"), ("reset() {", 'if [[ ${BC250_GFX1013_LIBRARY_ONLY:-0}')):
            body = source[source.index(function): source.index(end_marker, source.index(function))]
            self.assertIn("acquire_lifecycle_lock", body)

    def test_build_requirement_accepts_an_installed_provider(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        start = source.index("build_requirement_provider() {")
        end = source.index("\nmissing_build_packages() {", start)
        function = source[start:end]
        command = function + r'''
rpm() {
  [[ "$*" == *"--whatprovides"*"zlib-devel"* ]] || return 7
  printf 'zlib-ng-compat-devel-2.3.3-3.fc44.x86_64\n'
}
build_requirement_provider zlib-devel
'''
        result = subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            "zlib-ng-compat-devel-2.3.3-3.fc44.x86_64",
        )

    def test_prepare_preflight_is_provider_aware_and_aggregated(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("rpm -q --whatprovides", source)
        self.assertIn("build_requirement_provider", source)
        self.assertIn("prepare_preflight", source)
        self.assertIn("requirement:", source)
        self.assertIn("provider:", source)
        self.assertIn("status: satisfied", source)
        self.assertIn("prepare check: BLOCKED", source)
        self.assertIn("No files, boot state or services were changed.", source)



    def test_trace_path_adaptation_scans_allowed_amd_trace_headers_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "amd"
            amdgpu = root / "amdgpu" / "amdgpu_trace.h"
            amdkfd = root / "amdkfd" / "kfd_trace.h"
            amdgpu.parent.mkdir(parents=True)
            amdkfd.parent.mkdir(parents=True)
            amdgpu.write_text(
                "#define TRACE_INCLUDE_PATH ../../drivers/gpu/drm/amd/amdgpu\n",
                encoding="utf-8",
            )
            amdkfd.write_text(
                "#define TRACE_INCLUDE_PATH ../../../drivers/gpu/drm/amd/amdkfd\n",
                encoding="utf-8",
            )
            env = os.environ | {
                "BC250_GFX1013_LIBRARY_ONLY": "1",
                "BC250_GFX1013_SOURCE": str(SOURCE),
            }
            result = subprocess.run(
                [
                    "bash",
                    "-Eeuo",
                    "pipefail",
                    "-c",
                    'source "$1"; adapt_external_amd_trace_paths "$2"',
                    "bash",
                    str(SCRIPT),
                    str(root),
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(amdgpu.parent.resolve()), amdgpu.read_text(encoding="utf-8"))
            self.assertIn(str(amdkfd.parent.resolve()), amdkfd.read_text(encoding="utf-8"))

            amdgpu.write_text(
                "#define TRACE_INCLUDE_PATH ../../drivers/gpu/drm/amd/display\n",
                encoding="utf-8",
            )
            bad = subprocess.run(
                [
                    "bash",
                    "-Eeuo",
                    "pipefail",
                    "-c",
                    'source "$1"; adapt_external_amd_trace_paths "$2"',
                    "bash",
                    str(SCRIPT),
                    str(root),
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("unresolved or unexpected in-tree AMD TRACE_INCLUDE_PATH", bad.stderr)

    def test_mesa_spec_selection_is_fail_closed(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        prep = source[source.index("prepare_fedora_mesa_source() {"): source.index("build_mesa() {")]
        self.assertIn('[[ -f "$rpm_top/SOURCES/mesa.spec" ]]', prep)
        self.assertIn("-name 'mesa*.spec' -print | sort", prep)
        self.assertIn('((${#specs[@]} == 1))', prep)
        self.assertNotIn("-print -quit", prep)

    def test_headless_stage_icd_is_pinned_before_audit_and_deploy(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        build = source[source.index("build_mesa() {"): source.index("verify_headless_radv_stage() {")]
        self.assertLess(
            build.index('pin_private_icd_library "$stage$(private_icd)" "$(private_radv_lib)"'),
            build.index('verify_headless_radv_stage "$stage"'),
        )
        verify = source[source.index("verify_headless_radv_stage() {"): source.index("pin_private_icd_library() {")]
        self.assertIn('private_icd_library_ok "$stage$(private_icd)" "$(private_radv_lib)"', verify)
        staging = source[source.index("stage_patched_boot() {"): source.index("restore_previous_next() {")]
        self.assertNotIn("pin_private_icd_library", staging)
        self.assertIn("deployed private RADV ICD does not retain", staging)

    def test_110_rebases_private_radv_and_hardens_prepare_build_pipeline(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        mesa = (SOURCE / "MESA-SOURCE").read_text(encoding="utf-8")
        patch = (SOURCE / "patches/mesa/0001-gfx1013-compute-queue-fix.patch").read_text(encoding="utf-8")
        self.assertIn("MESA_VERSION=26.2.4", source)
        self.assertIn("MESA_FEDORA_RELEASE=1.fc44", source)
        self.assertIn("mesa-26.2.4-1.fc44.src", mesa)
        self.assertIn("bce5f7fbebb934373b86c999a064d52fb5065878dc57f287f95346648ec832e9", mesa)
        self.assertNotIn("26.2.0-rc3", mesa)
        self.assertIn("Fedora 44 Mesa 26.2.4 already contains", patch)
        self.assertNotIn("ver_minor = info->ip[AMD_IP_COMPUTE].ver_minor = 1", patch)
        for token in (
            "prepare_fedora_kernel_source",
            'rpmbuild -bp --nodeps --define "_topdir $rpm_top"',
            "kernel-prep.log",
            "adapt_external_amd_trace_paths",
            "unresolved or unexpected in-tree AMD TRACE_INCLUDE_PATH",
            "kernel_modversions_enabled",
            "mode=symbol-resolution",
            "Module.symvers",
            "materialize_module_ko",
            "PREPARE_COMMITTED=0",
            "preserve_prepare_failure",
            "rotate_prepare_failures",
            "kernel-srpm-members.txt",
        ):
            self.assertIn(token, source)

    def _run_stage_fault(self, root: Path, fault: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "BC250_GFX1013_LIBRARY_ONLY": "1",
                "BC250_GFX1013_SOURCE": str(SOURCE),
                "BC250_GFX1013_STATE_ROOT": str(root / "state"),
                "BC250_GFX1013_PREFIX_ROOT": str(root / "prefix"),
                "BC250_GFX1013_BOOT_ROOT": str(root / "boot"),
                "BC250_GFX1013_MODULES_ROOT": str(root / "modules"),
                "BC250_GFX1013_MACHINE_ID_FILE": str(root / "machine-id"),
                "FAULT": fault,
            }
        )
        script = rf'''\
source "{SCRIPT}"
kernel=7.2.9-200.fc44.x86_64
prepared="$BC250_GFX1013_STATE_ROOT/prepared/$kernel"
transaction="$BC250_GFX1013_STATE_ROOT/.prepare-test"
mesa_stage="$transaction/mesa-stage"
stock_module="$BC250_GFX1013_MODULES_ROOT/$kernel/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko"
stock_bls="$BC250_GFX1013_BOOT_ROOT/loader/entries/machine-$kernel.conf"
module_payload="$transaction/amdgpu.ko"
info="$prepared/stage-info"
mkdir -p "$(dirname "$stock_module")" "$(dirname "$stock_bls")" "$prepared" "$transaction/work"
printf machine > "$BC250_GFX1013_MACHINE_ID_FILE"
printf stockmodule > "$stock_module"
printf stockinit > "$BC250_GFX1013_BOOT_ROOT/initramfs-$kernel.img"
printf 'title stock\nversion %s\ninitrd /initramfs-%s.img\noptions quiet\n' "$kernel" "$kernel" > "$stock_bls"
printf patchedmodule > "$module_payload"
private=$(private_prefix)
mkdir -p "$mesa_stage$private/lib64" "$mesa_stage$private/share/vulkan/icd.d"
printf radv > "$mesa_stage$private/lib64/libvulkan_radeon.so"
printf '%s\n' '{{"ICD":{{"library_path":"libvulkan_radeon.so","api_version":"1.3.0"}}}}' > "$mesa_stage$private/share/vulkan/icd.d/radeon_icd.x86_64.json"

grub2-editenv() {{
  if [[ ${{1:-}} == list ]]; then
    printf 'saved_entry=stock\nnext_entry=previous\n'
  else
    return 0
  fi
}}
grub_value() {{ [[ $1 == saved_entry ]] && printf stock || printf previous; }}
if [[ "$FAULT" == dracut ]]; then
  dracut() {{ return 77; }}
else
  dracut() {{
    local out='' kmod=''
    while (($#)); do
      case "$1" in
        --kmoddir) kmod=$2; shift 2 ;;
        -f) out=$2; shift 2 ;;
        *) shift ;;
      esac
    done
    printf initramfs > "$out"
    cp "$(find "$kmod" -type f -name 'amdgpu.ko*' -print -quit)" "{root}/fake-embedded.ko"
  }}
  lsinitrd() {{
    mkdir -p "lib/modules/$kernel/kernel/drivers/gpu/drm/amd/amdgpu"
    cp "{root}/fake-embedded.ko" "lib/modules/$kernel/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko"
  }}
fi
if [[ "$FAULT" == bls ]]; then
  install() {{
    local last="${{@: -1}}"
    if [[ "$last" == "$PREPARE_PATCHED_BLS" ]]; then return 91; fi
    command install "$@"
  }}
fi

PREPARE_DIR="$transaction"
PREPARE_FINAL_DIR="$prepared"
PREPARE_PATCHED_BLS="$BC250_GFX1013_BOOT_ROOT/loader/entries/machine-$kernel-$PROFILE_VARIANT.conf"
PREPARE_PATCHED_INITRAMFS="$BC250_GFX1013_BOOT_ROOT/initramfs-$kernel-$PROFILE_VARIANT.img"
PREPARE_PRIVATE_PREFIX="$private"
PREPARE_PREVIOUS_NEXT=previous
PREPARE_BOOT_STATE_CHANGED=0
PREPARE_COMMITTED=0
PREPARE_STAGE="fault-$FAULT"
PREPARE_FAILURE_REASON=''
trap 'prepare_cleanup_on_exit $?' EXIT
stage_patched_boot "$kernel" "$prepared" "$module_payload" "$mesa_stage" "$stock_module" "$stock_bls" "$info"
'''
        return subprocess.run(
            ["bash", "-c", script],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def _run_boot_transaction_fault(self, root: Path, fault: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "BC250_GFX1013_LIBRARY_ONLY": "1",
                "BC250_GFX1013_SOURCE": str(SOURCE),
                "BC250_GFX1013_STATE_ROOT": str(root / "state"),
                "BC250_GFX1013_PREFIX_ROOT": str(root / "prefix"),
                "FAULT": fault,
            }
        )
        script = rf'''\
source "{SCRIPT}"
mkdir -p "$BC250_GFX1013_STATE_ROOT" "$BC250_GFX1013_PREFIX_ROOT/keep" "{root}/transaction" "{root}/prepared"
printf old > "{root}/next"
printf stock > "{root}/saved"
printf bls > "{root}/patched.conf"
printf initramfs > "{root}/patched.img"
cat > "$ACTIVE_STATE" <<'EOF'
BC250_GFX1013_TRANSACTION_PHASE=BOOT_ENTRY_STAGING
BC250_GFX1013_RECOVERY_REQUIRED=0
BC250_GFX1013_ENABLED=0
EOF

grub2-editenv() {{
  if [[ ${{1:-}} == list ]]; then
    printf 'saved_entry=%s\nnext_entry=%s\n' "$(cat "{root}/saved")" "$(cat "{root}/next")"
    return 0
  fi
  if [[ ${{2:-}} == set ]]; then
    value=${{3#next_entry=}}
    if [[ "$FAULT" == set-fail && "$value" == patched ]]; then return 41; fi
    if [[ "$FAULT" == restore-fail && "$value" == old ]]; then return 42; fi
    printf '%s' "$value" > "{root}/next"
    return 0
  fi
  if [[ ${{2:-}} == unset ]]; then
    : > "{root}/next"
    return 0
  fi
  return 1
}}
grub_value() {{
  [[ $1 == saved_entry ]] && cat "{root}/saved" || cat "{root}/next"
}}

PREPARE_DIR="{root}/transaction"
PREPARE_FINAL_DIR="{root}/prepared"
PREPARE_PATCHED_BLS="{root}/patched.conf"
PREPARE_PATCHED_INITRAMFS="{root}/patched.img"
PREPARE_PRIVATE_PREFIX="$BC250_GFX1013_PREFIX_ROOT/keep"
PREPARE_PREVIOUS_NEXT=old
PREPARE_BOOT_STATE_CHANGED=0
PREPARE_COMMITTED=0
PREPARE_STAGE="boot-$FAULT"
PREPARE_FAILURE_REASON=''
trap 'prepare_cleanup_on_exit $?' EXIT
trap 'exit 130' INT TERM
select_patched_next_boot patched stock
case "$FAULT" in
  restore-fail) die "forced post-selection failure" ;;
  sigterm) kill -TERM $$ ;;
  sigint) kill -INT $$ ;;
  set-fail) : ;;
  *) exit 99 ;;
esac
'''
        return subprocess.run(
            ["bash", "-c", script],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_110_behavioral_stage_faults_leave_stock_untouched_and_clean_partial_artifacts(self) -> None:
        kernel = "7.2.9-200.fc44.x86_64"
        for fault in ("dracut", "bls"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                result = self._run_stage_fault(root, fault)
                self.assertEqual(result.returncode, 2, result.stderr)
                stock_module = root / "modules" / kernel / "kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko"
                stock_initramfs = root / "boot" / f"initramfs-{kernel}.img"
                self.assertEqual(stock_module.read_text(encoding="utf-8"), "stockmodule")
                self.assertEqual(stock_initramfs.read_text(encoding="utf-8"), "stockinit")
                self.assertFalse((root / "boot/loader/entries" / f"machine-{kernel}-bc250-gfx1013-v33.conf").exists())
                self.assertFalse((root / "boot" / f"initramfs-{kernel}-bc250-gfx1013-v33.img").exists())
                self.assertFalse((root / "prefix/0.2.0-alpha").exists())
                self.assertFalse((root / "state/.prepare-test").exists())
                self.assertFalse((root / "state/active.env").exists())
                failures = list((root / "state/failures").glob("failure-*/failure.env"))
                self.assertEqual(len(failures), 1)
                evidence = failures[0].read_text(encoding="utf-8")
                self.assertIn(f"stage=fault-{fault}", evidence)
                if fault == "dracut":
                    self.assertIn("patched\\ initramfs\\ generation", evidence)
                else:
                    self.assertIn("failed\\ to\\ install\\ patched\\ BLS\\ entry", evidence)

    def test_110_behavioral_grub_set_failure_restores_and_cleans(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self._run_boot_transaction_fault(root, "set-fail")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual((root / "next").read_text(encoding="utf-8"), "old")
            self.assertEqual((root / "saved").read_text(encoding="utf-8"), "stock")
            self.assertFalse((root / "patched.conf").exists())
            self.assertFalse((root / "patched.img").exists())
            self.assertFalse((root / "prefix/keep").exists())
            self.assertFalse((root / "state/active.env").exists())
            self.assertEqual(len(list((root / "state/failures").glob("failure-*/failure.env"))), 1)

    def test_110_behavioral_grub_restore_failure_preserves_recovery_state_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self._run_boot_transaction_fault(root, "restore-fail")
            self.assertEqual(result.returncode, 5, result.stderr)
            self.assertEqual((root / "next").read_text(encoding="utf-8"), "patched")
            self.assertEqual((root / "saved").read_text(encoding="utf-8"), "stock")
            self.assertTrue((root / "patched.conf").is_file())
            self.assertTrue((root / "patched.img").is_file())
            self.assertTrue((root / "prefix/keep").is_dir())
            self.assertTrue((root / "transaction").is_dir())
            state = (root / "state/active.env").read_text(encoding="utf-8")
            self.assertIn("BC250_GFX1013_TRANSACTION_PHASE=SAFETY_FAILURE", state)
            self.assertIn("BC250_GFX1013_RECOVERY_REQUIRED=1", state)
            self.assertIn("failed\\ to\\ restore\\ previous\\ GRUB\\ next_entry", state)
            failures = list((root / "state/failures").glob("failure-*/failure.env"))
            self.assertEqual(len(failures), 1)

    def test_110_behavioral_prepare_signals_restore_boot_state_and_clean(self) -> None:
        for fault in ("sigint", "sigterm"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                result = self._run_boot_transaction_fault(root, fault)
                self.assertEqual(result.returncode, 130, result.stderr)
                self.assertEqual((root / "next").read_text(encoding="utf-8"), "old")
                self.assertEqual((root / "saved").read_text(encoding="utf-8"), "stock")
                self.assertFalse((root / "patched.conf").exists())
                self.assertFalse((root / "patched.img").exists())
                self.assertFalse((root / "prefix/keep").exists())
                self.assertFalse((root / "state/active.env").exists())
                self.assertEqual(len(list((root / "state/failures").glob("failure-*/failure.env"))), 1)

    def test_110_prepare_never_overwrites_stock_amdgpu_and_rolls_boot_back_first(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        stage = source[source.index("stage_patched_boot() {"): source.index("restore_previous_next() {")]
        cleanup = source[source.index("prepare_cleanup_on_exit() {"): source.index("prepare_preflight() {")]
        self.assertIn('dracut --kmoddir "$kmod_stage"', stage)
        self.assertIn('cp -a --reflink=auto "$stock_modules_root/." "$kmod_stage/"', stage)
        self.assertIn('stock amdgpu changed during isolated dracut generation', stage)
        self.assertIn('patched initramfs must contain exactly one amdgpu module', stage)
        self.assertNotIn('install -m 0644 "$module_payload" "$stock_module"', stage)
        self.assertNotIn("restore_stock_module", source)
        self.assertLess(cleanup.index('restore_previous_next "$PREPARE_PREVIOUS_NEXT"'), cleanup.index('rm -f -- "$PREPARE_PATCHED_BLS"'))
        self.assertIn("mark_prepare_safety_failure", cleanup)
        self.assertIn("SAFETY_FAILURE", source)
        self.assertIn("recovery artifacts were preserved", cleanup)
        selector = source[source.index("select_patched_next_boot() {"): source.index("rotate_prepare_failures() {")]
        self.assertLess(
            selector.index("PREPARE_BOOT_STATE_CHANGED=1"),
            selector.index('grub2-editenv - set "next_entry=$patched_id"'),
        )
        prepare = source[source.index("prepare() {"): source.index("verify_active_identity() {")]
        self.assertIn('select_patched_next_boot "$patched_id" "$saved_before"', prepare)

    def test_110_records_fedora_kernel_source_lineage_and_transaction_phases(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('check-kernel-provenance.py', source)
        self.assertIn('fedora-prepared-source', source)
        self.assertIn('BC250_GFX1013_KERNEL_SRPM_NEVR=', source)
        self.assertIn('BC250_GFX1013_KERNEL_SOURCE_PROVENANCE_SHA256=', source)
        self.assertIn('BC250_GFX1013_KERNEL_TARGET_MANIFEST_SHA256=', source)
        self.assertIn('BC250_GFX1013_TRANSACTION_PHASE=BOOT_ENTRY_STAGING', source)
        self.assertIn('BC250_GFX1013_TRANSACTION_PHASE=PREPARED', source)
        self.assertIn('set_active_transaction_state ENABLING', source)
        self.assertIn('set_active_transaction_state DISABLING', source)
        self.assertIn('BC250_GFX1013_ABI_MODE=', source)


    def test_110_fedora_mesa_prep_declares_cargo_toolchain_on_device(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        packages = source[source.index("GFX_BUILD_PACKAGES=("): source.index("build_requirement_provider() {")]
        self.assertIn("cargo rust cargo-rpm-macros", packages)
        self.assertIn("redhat-rpm-config", packages)
        self.assertIn("kernel-srpm-macros", packages)
        self.assertIn("git-core", packages)

    def test_110_source_rpm_detection_does_not_require_arch_src(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        validator = (ROOT / "scripts/check-gfx1013-mesa.py").read_text(encoding="utf-8")
        self.assertIn("%{SOURCEPACKAGE}", source)
        self.assertIn("%{SOURCEPACKAGE}", validator)
        self.assertNotIn("%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\\n' \"$srpm\"", source)

    def test_mesa_source_validation_is_part_of_sources_gate(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        validator = (ROOT / "scripts/check-gfx1013-mesa.py").read_text(encoding="utf-8")
        self.assertIn("./scripts/check-gfx1013-mesa.py --fetch", makefile)
        self.assertIn("./scripts/check-gfx1013-mesa.py", makefile)
        self.assertIn('"mesa-26.2.4-1.fc44.src"', validator)
        self.assertIn("--fuzz=0", validator)
        self.assertIn("Fedora Mesa %prep", validator)

    def test_disable_and_package_erase_are_fail_closed(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        disable = source[source.index("disable() {"): source.index('case "${1:-status}"')]
        self.assertLess(disable.index("restore_stock_boot"), disable.index('rm -f "$DROPIN"'))
        self.assertIn("stock saved/default boot verification failed", source)
        self.assertIn("stock next-boot verification failed", source)
        spec = SPEC.read_text(encoding="utf-8")
        preun = spec[spec.index("%preun"): spec.index("%postun")]
        self.assertIn("gfx1013.sh disable --package-erase", preun)
        self.assertIn("refusing package erase", preun)
        self.assertLess(preun.index("gfx1013.sh disable --package-erase"), preun.index("systemctl stop open-webui.service"))


if __name__ == "__main__":
    unittest.main()
