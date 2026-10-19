from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "cmd/system/gfx1013.sh"
SOURCE = ROOT / "gfx1013/upstream"
SPEC = ROOT / "packaging/bc250-llm-server.spec"


def dependency_shell_source() -> str:
    source = SCRIPT.read_text(encoding="utf-8")
    start = source.index("GFX_BUILD_PACKAGES=(")
    end = source.index("\nread_one_line() {", start)
    return source[start:end]


def run_stage_boot_case(
    next_entry: str,
    *,
    fail_commit_once: bool = False,
    precreate_patched: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    """Exercise stage-boot against a sandboxed GRUB/state model."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        active = root / "active.env"
        active.write_text("prepared\n", encoding="utf-8")
        (root / "prepared").mkdir()
        (root / "saved").write_text("stock\n", encoding="utf-8")
        (root / "next").write_text(next_entry + "\n", encoding="utf-8")
        if precreate_patched:
            (root / "patched.conf").write_text("patched\n", encoding="utf-8")
            (root / "patched.img").write_text("patched\n", encoding="utf-8")
        shell = r"""
set -Eeuo pipefail
export BC250_GFX1013_LIBRARY_ONLY=1
source "$SCRIPT_PATH"
mkdir -p "$BC250_GFX1013_STATE_ROOT"
ACTIVE_STATE="$ACTIVE_PATH"
need_root() { :; }
acquire_lifecycle_lock() { :; }
gfx_lifecycle_state() { GFX_LIFECYCLE_STATE=PREPARED; GFX_STATE_REASON=prepared; }
load_active_state() {
  BC250_GFX1013_STOCK_ENTRY_ID=stock
  BC250_GFX1013_PATCHED_ENTRY_ID=patched
  BC250_GFX1013_KERNEL=test-kernel
  BC250_GFX1013_PATCHED_BLS="$ROOT_PATH/patched.conf"
  BC250_GFX1013_PATCHED_INITRAMFS="$ROOT_PATH/patched.img"
  BC250_GFX1013_MODULE="$ROOT_PATH/amdgpu.ko"
  BC250_GFX1013_STOCK_MODULE="$ROOT_PATH/stock.ko"
  BC250_GFX1013_STOCK_BLS="$ROOT_PATH/stock.conf"
  BC250_GFX1013_STOCK_INITRAMFS="$ROOT_PATH/stock.img"
  BC250_GFX1013_STOCK_MODULE_SHA256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  BC250_GFX1013_STOCK_INITRAMFS_SHA256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
  BC250_GFX1013_BUILD_EVIDENCE="$ROOT_PATH/prepared/build-evidence"
  return 0
}
verify_active_identity() { :; }
patched_boot_running() { return 1; }
grub_value() {
  case "$1" in
    saved_entry) tr -d '\n' < "$ROOT_PATH/saved" ;;
    next_entry) tr -d '\n' < "$ROOT_PATH/next" ;;
    *) return 2 ;;
  esac
}
grub2-editenv() {
  [[ "$1" == - ]] || return 64
  case "$2" in
    set)
      value=${3#next_entry=}
      printf '%s\n' "$value" > "$ROOT_PATH/next"
      printf 'set:%s\n' "$value" >> "$ROOT_PATH/grub.log"
      ;;
    unset)
      [[ "$3" == next_entry ]] || return 64
      : > "$ROOT_PATH/next"
      printf 'unset\n' >> "$ROOT_PATH/grub.log"
      ;;
    *) return 64 ;;
  esac
}
set_active_transaction_state() {
  phase=$1
  printf '%s\n' "$phase" >> "$ROOT_PATH/transactions.log"
  if [[ ${FAIL_COMMIT_ONCE:-0} == 1 && "$phase" == PREPARED && ! -e "$ROOT_PATH/commit-failed" ]]; then
    : > "$ROOT_PATH/commit-failed"
    return 1
  fi
  return 0
}
prepared_stamp_for() { printf '%s\n' "$ROOT_PATH/prepared/prepared.env"; }
prepared_dir_for() { printf '%s\n' "$ROOT_PATH/prepared"; }
set_staged_boot_identity() { :; }
stage_patched_boot() {
  info_file=$7
  : > "$BC250_GFX1013_PATCHED_BLS"
  : > "$BC250_GFX1013_PATCHED_INITRAMFS"
  printf '%s\n' \
    "$BC250_GFX1013_PATCHED_BLS" \
    "$BC250_GFX1013_PATCHED_ENTRY_ID" \
    "$BC250_GFX1013_PATCHED_INITRAMFS" \
    "$BC250_GFX1013_STOCK_INITRAMFS" \
    "$(grub_value saved_entry)" \
    "$(grub_value next_entry)" \
    "$BC250_GFX1013_STOCK_MODULE_SHA256" \
    "$BC250_GFX1013_STOCK_INITRAMFS_SHA256" \
    cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc \
    dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd \
    > "$info_file"
}
stage_boot
"""
        env = {
            **os.environ,
            "SCRIPT_PATH": str(SCRIPT),
            "ROOT_PATH": str(root),
            "ACTIVE_PATH": str(active),
            "BC250_GFX1013_STATE_ROOT": str(root / "state"),
            "FAIL_COMMIT_ONCE": "1" if fail_commit_once else "0",
        }
        result = subprocess.run(
            ["bash", "-c", shell],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        state: dict[str, object] = {
            "saved": (root / "saved").read_text(encoding="utf-8").strip(),
            "next": (root / "next").read_text(encoding="utf-8").strip(),
            "grub_log": (root / "grub.log").read_text(encoding="utf-8").splitlines()
            if (root / "grub.log").exists()
            else [],
            "transactions": (root / "transactions.log").read_text(encoding="utf-8").splitlines()
            if (root / "transactions.log").exists()
            else [],
            "patched_bls": (root / "patched.conf").exists(),
            "patched_initramfs": (root / "patched.img").exists(),
        }
        return result, state


def run_tty_bash(body: str, *, extra_env: dict[str, str] | None = None) -> tuple[int, str]:
    env = os.environ.copy()
    env.update(extra_env or {})
    master, slave = os.openpty()
    proc = subprocess.Popen(
        ["bash", "-c", body],
        stdin=subprocess.DEVNULL,
        stdout=slave,
        stderr=slave,
        env=env,
        close_fds=True,
    )
    os.close(slave)
    chunks: list[bytes] = []
    try:
        while True:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(master)
    return proc.wait(timeout=10), b"".join(chunks).decode("utf-8", errors="replace")


class Gfx1013Tests(unittest.TestCase):
    def test_package_profile_identity_and_selected_patch_set(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("PACKAGE_PROFILE=v0.2.5-alpha", source)
        self.assertIn("UPSTREAM_VERSION=0.2.0-alpha", source)
        self.assertIn("PINNED_COMMIT=d3e6dc062c34d2523db0abe5741d1f5b0dea00d9", source)
        self.assertIn("PATCH_REFERENCE_KERNEL=7.2.9-200.fc44.x86_64", source)
        self.assertIn("PACKAGE_QUALIFICATION_KERNEL=7.2.10-200.fc44.x86_64", source)
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

    def test_nounset_safe_local_assignments_for_build_helpers(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("local build=$1 module=$2 work=$3 kernel=$4\n  local symvers=\"$build/Module.symvers\"", source)
        self.assertIn("local index=$1 label=$2\n  local marker=\"[$index/7] $label\"", source)
        self.assertNotIn("local build=$1 module=$2 work=$3 kernel=$4 symvers=", source)
        self.assertNotIn("local index=$1 label=$2 marker=", source)

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
            verbose = subprocess.run(
                [str(SCRIPT), "status", "--verbose"],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            brief = subprocess.run(
                [str(SCRIPT), "status", "--brief"],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("GFX1013 state: disabled", result.stdout)
        self.assertIn("Integrity:", result.stdout)
        self.assertIn("Private RADV: absent / disabled", result.stdout)
        self.assertNotIn("Pinned upstream:", result.stdout)
        self.assertNotIn("Mesa baseline:", result.stdout)
        self.assertEqual(verbose.returncode, 0, verbose.stdout)
        self.assertIn("v0.2.5-alpha / experimental / default OFF", verbose.stdout)
        self.assertIn("Carried source integrity: PASS", verbose.stdout)
        self.assertIn("Experimental private-RADV override: disabled", verbose.stdout)
        self.assertIn("Pinned upstream:", verbose.stdout)
        self.assertEqual(brief.returncode, 0, brief.stdout)
        self.assertEqual(brief.stdout.count("Boot:"), 1, brief.stdout)
        self.assertNotIn("Pinned upstream:", brief.stdout)
        self.assertNotIn("Mesa baseline:", brief.stdout)


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
        self.assertEqual(payload["schema"], "bc250.gfx1013-status.v2")
        self.assertEqual(payload["state"], "DISABLED")
        self.assertEqual(payload["profile"], "v0.2.5-alpha")
        self.assertTrue(payload["default_off"])

    def test_nonroot_status_only_reports_not_inspected_for_inaccessible_state(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("requires an unprivileged test runner")
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            state = tmp / "state"
            state.mkdir()
            env = os.environ.copy()
            env.update(
                {
                    "BC250_GFX1013_SOURCE": str(SOURCE),
                    "BC250_GFX1013_STATE_ROOT": str(state),
                    "BC250_GFX1013_PREFIX_ROOT": str(tmp / "prefix"),
                    "BC250_GFX1013_DROPIN": str(tmp / "dropin.conf"),
                    "BC250_GFX1013_UPSTREAM_GENERATOR": str(tmp / "upstream-generator"),
                    "BC250_GFX1013_UPSTREAM_STATE": str(tmp / "upstream-state"),
                }
            )
            state.chmod(0o000)
            try:
                result = subprocess.run(
                    [str(SCRIPT), "status", "--json"],
                    env=env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
            finally:
                state.chmod(0o700)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "NOT_INSPECTED")
        self.assertIn("root inspection", payload["reason"])

    def test_16_hardens_secure_boot_stale_kernel_and_private_radv_guard(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for state in (
            "DISABLED",
            "PREPARED",
            "PATCHED_BOOT_UNVERIFIED",
            "ENABLED",
            "STOCK_REBOOT_REQUIRED",
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
        self.assertIn("prepare [--check|--download-only] [--verbose]", source)
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
resolve_safe_stock_target() {{ printf '/boot/loader/entries/stock.conf|stock\n'; }}
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
            ({"active": True, "saved": "stock", "next_entry": "patched", "patched": False}, "ROLLBACK_REQUIRED"),
            ({"active": True, "saved": "stock", "next_entry": "", "patched": True}, "ROLLBACK_REQUIRED"),
        )
        for kwargs, expected in cases:
            with self.subTest(kwargs=kwargs):
                result = self._run_classifier_case(**kwargs)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.startswith(expected + "|"), result.stdout)

    def test_22_upgrade_from_enabled_is_classified_as_stock_reboot_pending(self) -> None:
        result = self._run_classifier_case(
            active=False,
            saved="stock",
            next_entry="stock",
            patched=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("STOCK_REBOOT_REQUIRED|"), result.stdout)
        self.assertIn("reboot required", result.stdout)

    def test_22_reboot_pending_state_drives_json_reset_check_reset_and_prepare_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stock_bls = root / "stock.conf"
            stock_bls.write_text("stock\n", encoding="utf-8")
            env = {
                **os.environ,
                "BC250_GFX1013_LIBRARY_ONLY": "1",
                "BC250_GFX1013_STATE_ROOT": str(root / "state"),
                "BC250_GFX1013_PREFIX_ROOT": str(root / "prefix"),
                "BC250_GFX1013_DROPIN": str(root / "dropin"),
                "ROOT_PATH": str(root),
            }
            script = rf'''
source "{SCRIPT}"
need_root() {{ :; }}
acquire_lifecycle_lock() {{ :; }}
kernel_release() {{ printf '7.2.10-200.fc44.x86_64\n'; }}
package_nevra() {{ printf 'bc250-llm-server-0.13.1-2.2.x86_64\n'; }}
grub_value() {{ printf 'stock\n'; }}
patched_boot_running() {{ return 0; }}
risky_artifacts_without_state() {{ return 1; }}
stock_entry_file_safe() {{ return 0; }}
resolve_safe_stock_target() {{ printf '%s|stock\n' "$ROOT_PATH/stock.conf"; }}
source_identity_ok() {{ return 0; }}
installed_payload_integrity_detail() {{ return 0; }}
bc250_device_present() {{ return 0; }}
secure_boot_state() {{ printf 'disabled\n'; }}
private_icd() {{ printf '%s/private/icd.json\n' "$ROOT_PATH"; }}
private_radv_lib() {{ printf '%s/private/radv.so\n' "$ROOT_PATH"; }}
load_active_state() {{ return 1; }}

gfx_lifecycle_state
printf 'CLASS=%s|%s\n' "$GFX_LIFECYCLE_STATE" "$GFX_STATE_REASON"
status_json
if rollback_check reset; then
  printf 'RESET_CHECK_RC=0\n'
else
  printf 'RESET_CHECK_RC=%s\n' "$?"
fi
if reset; then
  printf 'RESET_RC=0\n'
else
  printf 'RESET_RC=%s\n' "$?"
fi
if prepare_runtime_ready; then
  printf 'PREPARE_GUARD_RC=0|UNEXPECTED-PASS\n'
else
  rc=$?
  printf 'PREPARE_GUARD_RC=%s|BLOCKED|%s|%s\n' "$rc" "$PREPARE_RUNTIME_BLOCK_REASON" "$PREPARE_RUNTIME_NEXT_ACTION"
fi
if prepare; then
  printf 'PREPARE_RC=0|UNEXPECTED-PASS\n'
else
  printf 'PREPARE_RC=%s|BLOCKED\n' "$?"
fi
'''
            result = subprocess.run(
                ["bash", "-c", script],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertTrue(lines[0].startswith("CLASS=STOCK_REBOOT_REQUIRED|"), result.stdout)
        json_start = result.stdout.index("{\n")
        decoder = json.JSONDecoder()
        payload, json_end = decoder.raw_decode(result.stdout[json_start:])
        trailing = result.stdout[json_start + json_end :]
        self.assertEqual(payload["state"], "STOCK_REBOOT_REQUIRED")
        self.assertEqual(payload["boot"]["stock_entry"], "stock")
        self.assertEqual(payload["boot"]["saved_entry"], "stock")
        self.assertEqual(payload["boot"]["next_entry"], "stock")
        self.assertIn("GFX1013 rollback check: PASS", trailing)
        self.assertIn("Next action: sudo reboot", trailing)
        self.assertIn("Reset: PASS (stock rollback prepared; reboot pending)", trailing)
        self.assertIn("Current runtime: patched GFX1013", trailing)
        self.assertIn("Verified next boot: stock (stock)", trailing)
        self.assertIn("A reboot is required to complete the return to stock.", trailing)
        self.assertIn("RESET_CHECK_RC=0", trailing)
        self.assertIn("RESET_RC=0", trailing)
        self.assertIn("PREPARE_GUARD_RC=1|BLOCKED|", trailing)
        self.assertIn("|sudo reboot", trailing)
        self.assertIn("PREPARE_RC=2|BLOCKED", trailing)

    def test_22_prepare_check_and_prepare_share_runtime_readiness_guard(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        preflight = source[source.index("prepare_preflight() {"): source.index("prefetch_sources() {")]
        prepare = source[source.index("prepare() {"): source.index("verify_active_identity() {")]
        self.assertIn("prepare_runtime_ready", preflight)
        self.assertIn("prepare_runtime_ready", prepare)
        self.assertIn('preflight_primary_action="$PREPARE_RUNTIME_NEXT_ACTION"', preflight)
        self.assertIn('print_next_action "$preflight_primary_action"', preflight)
        self.assertIn('print_next_action "$PREPARE_RUNTIME_NEXT_ACTION"', prepare)


    def test_22_prepare_check_preserves_blocked_preflight_return_code(self) -> None:
        body = f'''
export BC250_GFX1013_LIBRARY_ONLY=1
source "{SCRIPT}"
need_root() {{ :; }}
prepare_preflight() {{ return 2; }}
if prepare --check; then
  printf 'RC=0\n'
else
  printf 'RC=%s\n' "$?"
fi
'''
        result = subprocess.run(
            ["bash", "-c", body],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "RC=2")

    def test_enable_guard_lock_and_recovery_are_fail_closed(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        enable = source[source.index("enable() {"): source.index("risky_artifacts_without_state() {")]
        guard = source[source.index("ollama_guard() {"): source.index("write_ollama_dropin() {")]
        cleanup = source[source.index("enable_cleanup_on_exit() {"): source.index("enable() {")]
        self.assertIn("acquire_lifecycle_lock", enable)
        self.assertIn("enable requires PATCHED_BOOT_UNVERIFIED", enable)
        self.assertIn("loaded_amdgpu_identity_ok", guard)
        self.assertIn("GFX_MODULE_ATTESTATION_REASON", guard)
        self.assertIn("ENABLING:0|ENABLED:1", guard)
        self.assertIn("ollama_enable_smoke", enable)
        self.assertLess(enable.index("systemctl restart ollama.service"), enable.index('grub2-set-default "$BC250_GFX1013_PATCHED_ENTRY_ID"'))
        self.assertLess(enable.index("ollama_enable_smoke"), enable.index('grub2-set-default "$BC250_GFX1013_PATCHED_ENTRY_ID"'))
        self.assertLess(enable.index('grub2-set-default "$BC250_GFX1013_PATCHED_ENTRY_ID"'), enable.index('mv -f "$state_tmp" "$ACTIVE_STATE"'))
        self.assertIn("restore_prepared_state_after_enable_failure", cleanup)
        self.assertIn('restore_previous_next "$ENABLE_PREVIOUS_NEXT"', cleanup)

    def test_mutating_commands_take_one_nonblocking_lifecycle_lock(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        lock = source[source.index("acquire_lifecycle_lock() {"): source.index("kernel_release() {")]
        self.assertIn("flock -n", lock)
        self.assertIn("LIFECYCLE_LOCK_HELD", lock)
        for function, end_marker in (("prepare() {", "verify_active_identity() {"), ("disable() {", "reset() {"), ("reset() {", 'if [[ ${BC250_GFX1013_LIBRARY_ONLY:-0}')):
            body = source[source.index(function): source.index(end_marker, source.index(function))]
            self.assertIn("acquire_lifecycle_lock", body)

    def test_build_requirement_exact_package_uses_success_status(self) -> None:
        command = dependency_shell_source() + r'''
rpm() {
  if [[ "$*" == *"--whatprovides"* ]]; then
    printf 'unexpected capability lookup\n' >&2
    return 9
  fi
  printf 'vulkan-headers-1.4.341.0-1.fc44.noarch\n'
  return 0
}
build_requirement_provider vulkan-headers
'''
        result = subprocess.run(["bash", "-c", command], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "vulkan-headers-1.4.341.0-1.fc44.noarch")
        self.assertNotIn("unexpected capability lookup", result.stderr)

    def test_build_requirement_falls_back_to_capability_provider(self) -> None:
        command = dependency_shell_source() + r'''
rpm() {
  if [[ "$*" == *"--whatprovides"* ]]; then
    printf 'provider-devel-9.1-2.fc44.x86_64\n'
    return 0
  fi
  printf 'package virtual-devel is not installed\n'
  return 1
}
build_requirement_provider virtual-devel
'''
        result = subprocess.run(["bash", "-c", command], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "provider-devel-9.1-2.fc44.x86_64")
        self.assertNotIn("not installed", result.stdout)

    def test_missing_requirement_stdout_never_becomes_provider_and_blocks_dependency_preflight(self) -> None:
        command = dependency_shell_source() + r'''
rpm() {
  local requirement=${!#}
  printf 'package %s is not installed\n' "$requirement"
  return 1
}
GFX_BUILD_PACKAGES=(vulkan-loader-devel)
GFX_BUILD_CAPABILITIES=()
if check_build_requirements; then
  printf 'UNEXPECTED-PASS\n'
  exit 0
fi
printf 'BLOCKED:%s\n' "${GFX_MISSING_BUILD_REQUIREMENTS[*]}"
exit 23
'''
        result = subprocess.run(["bash", "-c", command], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertIn("provider: <none>", result.stdout)
        self.assertIn("NOT INSTALLED", result.stdout)
        self.assertIn("BLOCKED:vulkan-loader-devel", result.stdout)
        self.assertNotIn("package vulkan-loader-devel is not installed", result.stdout)
        self.assertNotIn("status: SATISFIED", result.stdout)

    def test_zlib_devel_compatibility_provider_is_satisfied(self) -> None:
        command = dependency_shell_source() + r'''
rpm() {
  if [[ "$*" == *"--whatprovides"*"zlib-devel"* ]]; then
    printf 'zlib-ng-compat-devel-2.3.3-3.fc44.x86_64\n'
    return 0
  fi
  printf 'package zlib-devel is not installed\n'
  return 1
}
GFX_BUILD_PACKAGES=(zlib-devel)
GFX_BUILD_CAPABILITIES=()
check_build_requirements 1
'''
        result = subprocess.run(["bash", "-c", command], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("zlib-ng-compat-devel-2.3.3-3.fc44.x86_64", result.stdout)
        self.assertIn("status: SATISFIED", result.stdout)
        self.assertNotIn("package zlib-devel is not installed", result.stdout)

    def test_rpm_macro_requirement_resolves_to_python3_rpm_macros_provider(self) -> None:
        command = dependency_shell_source() + r'''
rpm() {
  local requirement=${!#}
  if [[ "$*" == *"--whatprovides"* && "$requirement" == 'rpm_macro(py3_shebang_fix)' ]]; then
    printf 'python3-rpm-macros-3.14-4.fc44.noarch\n'
    return 0
  fi
  printf 'package %s is not installed\n' "$requirement"
  return 1
}
build_requirement_provider 'rpm_macro(py3_shebang_fix)'
'''
        result = subprocess.run(["bash", "-c", command], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "python3-rpm-macros-3.14-4.fc44.noarch")

    def test_default_dependency_output_is_exception_focused_and_verbose_retains_providers(self) -> None:
        command = dependency_shell_source() + r'''
rpm() {
  local requirement=${!#}
  if [[ "$requirement" == present-devel ]]; then
    printf 'present-devel-1-1.fc44.x86_64\n'
    return 0
  fi
  return 1
}
GFX_BUILD_PACKAGES=(present-devel missing-devel)
GFX_BUILD_CAPABILITIES=()
printf '%s\n' DEFAULT
check_build_requirements 0 || true
printf '%s\n' VERBOSE
check_build_requirements 1 || true
'''
        result = subprocess.run(["bash", "-c", command], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        default, verbose = result.stdout.split("VERBOSE\n", 1)
        self.assertIn("Build dependencies: BLOCKED — 1 missing", default)
        self.assertIn("missing-devel — NOT INSTALLED", default)
        self.assertNotIn("status: SATISFIED", default)
        self.assertNotIn("present-devel-1-1", default)
        self.assertIn("present-devel-1-1.fc44.x86_64", verbose)
        self.assertIn("status: SATISFIED", verbose)
        self.assertIn("status: NOT INSTALLED", verbose)

    def test_prepare_blocks_missing_rpm_macro_before_source_acquisition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            os_release = tmp / "os-release"
            os_release.write_text("ID=fedora\n", encoding="utf-8")
            fakebin = tmp / "bin"
            fakebin.mkdir()
            for name in (
                "cargo",
                "rpm2cpio",
                "rpmbuild",
                "meson",
                "vulkaninfo",
                "dracut",
                "lsinitrd",
                "grub2-editenv",
                "grub2-set-default",
            ):
                path = fakebin / name
                path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
                path.chmod(0o755)
            marker = tmp / "source-acquired"
            command = r'''
set -Eeuo pipefail
export BC250_GFX1013_LIBRARY_ONLY=1
export BC250_GFX1013_OS_RELEASE_FILE="$2"
source "$1"
need_root() { :; }
acquire_lifecycle_lock() { :; }
patched_boot_running() { return 1; }
secure_boot_prepare_ok() { :; }
rpm() {
  local requirement=${!#}
  if [[ "$requirement" == 'rpm_macro(py3_shebang_fix)' ]]; then
    return 1
  fi
  printf 'provider-1-1.fc44.x86_64\n'
  return 0
}
fetch_verified_srpm() { : > "$3"; }
prepare
'''
            env = os.environ | {"PATH": f"{fakebin}:{os.environ.get('PATH', '')}"}
            result = subprocess.run(
                ["bash", "-c", command, "bash", str(SCRIPT), str(os_release), str(marker)],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        combined = result.stdout + result.stderr
        self.assertIn("rpm_macro(py3_shebang_fix)", combined)
        self.assertIn("NOT INSTALLED", combined)
        self.assertFalse(marker.exists(), combined)

    def test_kernel_prep_failure_classifier_recognizes_missing_py3_shebang_macro(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "kernel-prep.log"
            log.write_text(
                "kernel.spec:2216: Fixing Python shebangs...\n"
                "+ %py3_shebang_fix tools/kvm/kvm_stat/kvm_stat\n"
                "/var/tmp/rpm-tmp.X: line 171: fg: no job control\n"
                "error: Bad exit status from /var/tmp/rpm-tmp.X (%prep)\n",
                encoding="utf-8",
            )
            command = r'''
export BC250_GFX1013_LIBRARY_ONLY=1
source "$1"
classify_prepare_log_failure '[2/7] Run Fedora kernel %prep' "$2"
prepare_stage_display '[2/7] Run Fedora kernel %prep'
'''
            result = subprocess.run(
                ["bash", "-c", command, "bash", str(SCRIPT), str(log)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["required RPM macro unavailable: py3_shebang_fix", "Fedora kernel %prep"],
        )

    def test_prepare_failure_evidence_is_real_gzip_tar_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            prepare_dir = tmp / "transaction"
            work = prepare_dir / "work"
            work.mkdir(parents=True)
            (work / "kernel-prep.log").write_text("error: synthetic prep failure\n", encoding="utf-8")
            state_root = tmp / "state"
            command = r'''
set -Eeuo pipefail
export BC250_GFX1013_LIBRARY_ONLY=1
export BC250_GFX1013_STATE_ROOT="$2"
source "$1"
PREPARE_DIR="$3"
PREPARE_STAGE='[2/7] Run Fedora kernel %prep'
PREPARE_FAILURE_REASON='required RPM macro unavailable: py3_shebang_fix'
package_nevra() { printf 'bc250-llm-server-0.13.1-1.17.fc44.x86_64\n'; }
kernel_release() { printf '7.2.10-200.fc44.x86_64\n'; }
preserve_prepare_evidence 2 failure
printf '%s\n' "$PREPARE_EVIDENCE_PATH"
'''
            result = subprocess.run(
                ["bash", "-c", command, "bash", str(SCRIPT), str(state_root), str(prepare_dir)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = Path(result.stdout.strip().splitlines()[-1])
            self.assertTrue(archive.name.endswith(".tar.gz"))
            self.assertEqual(archive.read_bytes()[:2], b"\x1f\x8b")
            with tarfile.open(archive, "r:gz") as tf:
                names = tf.getnames()
                self.assertTrue(any(name.endswith("/result.env") for name in names), names)
                self.assertTrue(any(name.endswith("/kernel-prep.log") for name in names), names)

    def test_prepare_preflight_consumes_dependency_status_and_aggregates(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        preflight = source[source.index("prepare_preflight() {"): source.index("prefetch_sources() {", source.index("prepare_preflight() {"))]
        self.assertIn('if ! check_build_requirements "$verbose"; then', preflight)
        self.assertIn('missing_requirements=("${GFX_MISSING_BUILD_REQUIREMENTS[@]}")', preflight)
        self.assertIn("dependency_blocked=1", preflight)
        self.assertIn("NOT CHECKED — required command modinfo unavailable", preflight)
        self.assertIn("NOT CHECKED — required command rpm unavailable", preflight)
        self.assertIn("failures != ${#remediation[@]}", preflight)
        self.assertIn("prepare check: BLOCKED — %d remediation required", preflight)
        self.assertIn("No files, boot state or services were changed.", preflight)



    def test_module_attestation_contract_is_shared_and_srcversion_is_supplemental(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        release_gate = (ROOT / "scripts/check-gfx1013-kernel-build.sh").read_text(encoding="utf-8")
        helper = source[source.index("validate_built_module_identity() {"): source.index("build_kernel_module() {", source.index("validate_built_module_identity() {"))]
        prepare = source[source.index("prepare() {"): source.index("verify_active_identity() {", source.index("prepare() {"))]
        self.assertIn("srcversion_policy=supplemental", helper)
        self.assertIn('module_sha="$(sha256sum "$module" | awk \'{print $1}\')"', helper)
        self.assertIn('[[ "$vermagic" == "$kernel "* ]]', helper)
        self.assertIn("verify_module_abi", helper)
        self.assertIn("validate_built_module_identity", prepare)
        self.assertIn("validate_built_module_identity", release_gate)
        self.assertNotIn("lacks the srcversion identity required for runtime attestation", source)

    def test_kernel_identity_fields_distinguish_qualification_and_patch_reference(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        contract = json.loads((ROOT / "release-contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["gfx1013"]["qualification_kernel"], "7.2.10-200.fc44.x86_64")
        self.assertEqual(contract["gfx1013"]["patch_reference_kernel"], "7.2.9-200.fc44.x86_64")
        self.assertIn("Package qualification: $PACKAGE_QUALIFICATION_KERNEL", source)
        self.assertIn("Patch/profile reference: $PATCH_REFERENCE_KERNEL", source)
        self.assertIn("Preparing device-local GFX1013 artifacts", source)
        self.assertNotIn("Exact-kernel rebuild: REQUIRED", source)

    def test_prepare_failure_evidence_captures_module_identity(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        evidence = source[source.index("preserve_prepare_evidence() {"): source.index("prepare_cleanup_on_exit() {", source.index("preserve_prepare_evidence() {"))]
        self.assertIn("module-identity-built.txt", evidence)
        self.assertIn("module-identity-stock.txt", evidence)
        self.assertIn("kernel-srcversion-config.txt", evidence)
        self.assertIn("capture_module_identity_evidence", evidence)

    def test_stock_module_lookup_targets_exact_kernel_first(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        function = source[source.index("find_stock_module() {"): source.index("find_stock_bls() {", source.index("find_stock_module() {"))]
        self.assertIn('modinfo -k "$kernel" -n amdgpu', function)

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
                    'source "$1"; adapt_external_amd_trace_paths "$2" "$3"',
                    "bash",
                    str(SCRIPT),
                    str(root),
                    str(Path(temporary) / "trace-include"),
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("#define TRACE_INCLUDE_PATH _bc250_trace_0001", amdgpu.read_text(encoding="utf-8"))
            self.assertIn("#define TRACE_INCLUDE_PATH _bc250_trace_0002", amdkfd.read_text(encoding="utf-8"))
            include_root = Path(temporary) / "trace-include"
            self.assertEqual((include_root / "_bc250_trace_0001").resolve(), amdgpu.parent.resolve())
            self.assertEqual((include_root / "_bc250_trace_0002").resolve(), amdkfd.parent.resolve())

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
                    'source "$1"; adapt_external_amd_trace_paths "$2" "$3"',
                    "bash",
                    str(SCRIPT),
                    str(root),
                    str(Path(temporary) / "trace-include"),
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("unresolved or unexpected in-tree AMD TRACE_INCLUDE_PATH", bad.stderr)

    def test_kernel_external_build_uses_trace_include_namespace(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        build = source[source.index("build_kernel_module() {"): source.index("prepare_fedora_mesa_source() {")]
        self.assertIn('trace_include_root="$work/trace-include"', build)
        self.assertIn('adapt_external_amd_trace_paths "$linux_root/drivers/gpu/drm/amd" "$trace_include_root"', build)
        self.assertIn('"KCFLAGS=-I$trace_include_root"', build)

    def test_kernel_build_progress_is_heartbeat_driven_and_parallelism_is_configurable(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        helper = source[source.index("gfx_build_progress() {"): source.index("prepare_fedora_kernel_source() {")]
        build = source[source.index("build_kernel_module() {"): source.index("prepare_fedora_mesa_source() {")]
        self.assertIn("BC250_GFX1013_BUILD_PROGRESS", helper)
        self.assertIn("BC250_GFX1013_HEARTBEAT_SECONDS", helper)
        self.assertIn('still running, $elapsed elapsed', helper)
        self.assertIn("BC250_GFX1013_BUILD_JOBS", helper)
        self.assertNotIn("detected > 4", helper)
        self.assertIn('detected="$(nproc)"', helper)
        self.assertIn("requested <= 64", helper)
        self.assertIn('jobs="$(kernel_build_jobs)"', build)
        self.assertIn('"-j$jobs"', build)
        self.assertNotIn('"-j$(nproc)"', build)
        self.assertIn('run_kernel_logged_phase "amdgpu external-module build"', build)

    def test_kernel_checker_enables_progress_without_forcing_device_output(self) -> None:
        checker = (ROOT / "scripts/check-gfx1013-kernel-build.sh").read_text(encoding="utf-8")
        self.assertIn('BC250_GFX1013_BUILD_PROGRESS="${BC250_GFX1013_BUILD_PROGRESS:-1}"', checker)
        self.assertIn('BC250_GFX1013_HEARTBEAT_SECONDS="${BC250_GFX1013_HEARTBEAT_SECONDS:-60}"', checker)

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
        prepare = source[source.index("prepare() {"): source.index("stage_boot() {")]
        self.assertIn("deployed private RADV ICD does not retain", prepare)

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
            "preserve_prepare_evidence",
            "rotate_prepare_evidence",
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
    [[ "$kmod" == "{root}/state/.prepare-test/work/kmod/lib/modules/$kernel" ]] || return 78
    printf '%s\n' "$kmod" > "{root}/dracut-kmoddir"
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
stage_patched_boot "$kernel" "$prepared" "$module_payload" "$stock_module" "$stock_bls" "$transaction/work" "$info"
'''
        return subprocess.run(
            ["bash", "-c", script],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_20_stage_boot_uses_dracut_lib_modules_hierarchy(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        staging = source[source.index("stage_patched_boot() {"): source.index("restore_previous_next() {")]
        self.assertIn('kmod_stage="$kmod_stage_root/lib/modules/$kernel"', staging)
        self.assertNotIn('kmod_stage="$work/kmod/$kernel"', staging)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self._run_stage_fault(root, "none")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (root / "dracut-kmoddir").read_text(encoding="utf-8").strip(),
                f"{root}/state/.prepare-test/work/kmod/lib/modules/7.2.9-200.fc44.x86_64",
            )

    def test_20_stage_boot_dracut_failure_leaves_stock_module_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self._run_stage_fault(root, "dracut")
            self.assertNotEqual(result.returncode, 0)
            stock = root / "modules/7.2.9-200.fc44.x86_64/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko"
            self.assertEqual(stock.read_text(encoding="utf-8"), "stockmodule")
            self.assertIn("patched initramfs generation from isolated module tree failed", result.stderr)

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

    def test_114_prepare_is_build_only_and_stage_boot_owns_boot_activation(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        prepare = source[source.index("prepare() {"): source.index("STAGE_BOOT_COMMITTED=1")]
        stage = source[source.index("stage_boot() {"): source.index("verify_active_identity() {")]
        self.assertNotIn("stage_patched_boot", prepare)
        self.assertNotIn('grub2-editenv - set "next_entry=', prepare)
        self.assertIn("Private RADV: built and staged", prepare)
        self.assertIn("Boot state changed: no", prepare)
        self.assertIn("stage_patched_boot", stage)
        self.assertIn("select_patched_next_boot", stage)
        self.assertIn("set_active_transaction_state BOOT_ENTRY_STAGING", stage)
        self.assertIn("set_active_transaction_state PREPARED", stage)
        self.assertIn("Prepared build retained: yes", source)
        self.assertIn('next" != "$BC250_GFX1013_STOCK_ENTRY_ID"', stage)
        self.assertIn("GFX1013 stage-boot: BLOCKED", stage)
        self.assertIn("Existing one-shot boot: verified stock entry", stage)
        self.assertIn('print_next_action "sudo bc250 gfx1013 status --verbose"', stage)
        bls = source[source.index("stage_patched_boot() {"): source.index("restore_previous_next() {")]
        self.assertNotIn("amdgpu.sched_policy=2", bls)
        self.assertIn("bc250.gfx1013_v33=1", bls)
        self.assertNotIn("$mesa_stage", bls)
        self.assertNotIn('$(dirname "$private")', bls)

    def test_21_stage_boot_state_machine_covers_all_next_entry_branches(self) -> None:
        empty, empty_state = run_stage_boot_case("")
        self.assertEqual(empty.returncode, 0, empty.stderr)
        self.assertIn("Boot activation: PASS", empty.stdout)
        self.assertEqual(empty_state["saved"], "stock")
        self.assertEqual(empty_state["next"], "patched")
        self.assertEqual(empty_state["grub_log"], ["set:patched"])

        stock, stock_state = run_stage_boot_case("stock")
        self.assertEqual(stock.returncode, 0, stock.stderr)
        self.assertIn("Existing one-shot boot: verified stock entry", stock.stdout)
        self.assertEqual(stock_state["saved"], "stock")
        self.assertEqual(stock_state["next"], "patched")
        self.assertEqual(stock_state["grub_log"], ["set:patched"])

        unknown, unknown_state = run_stage_boot_case("admin-custom")
        self.assertEqual(unknown.returncode, 2, unknown.stderr)
        self.assertIn("GFX1013 stage-boot: BLOCKED", unknown.stderr)
        self.assertIn("admin-custom", unknown.stderr)
        self.assertIn("status --verbose", unknown.stderr)
        self.assertEqual(unknown_state["saved"], "stock")
        self.assertEqual(unknown_state["next"], "admin-custom")
        self.assertEqual(unknown_state["grub_log"], [])
        self.assertFalse(unknown_state["patched_bls"])
        self.assertFalse(unknown_state["patched_initramfs"])

        conflicting, conflicting_state = run_stage_boot_case("patched")
        self.assertEqual(conflicting.returncode, 2, conflicting.stderr)
        self.assertIn("patched next_entry is selected but its boot artifacts are missing", conflicting.stderr)
        self.assertEqual(conflicting_state["next"], "patched")
        self.assertEqual(conflicting_state["grub_log"], [])

        staged, staged_state = run_stage_boot_case("patched", precreate_patched=True)
        self.assertEqual(staged.returncode, 0, staged.stderr)
        self.assertIn("Boot activation: already staged", staged.stdout)
        self.assertEqual(staged_state["saved"], "stock")
        self.assertEqual(staged_state["next"], "patched")
        self.assertEqual(staged_state["grub_log"], [])

    def test_21_stage_boot_restores_verified_stock_next_entry_after_post_selection_failure(self) -> None:
        result, state = run_stage_boot_case("stock", fail_commit_once=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("GFX1013 stage-boot: FAILED", result.stderr)
        self.assertIn("Prepared build retained: yes", result.stderr)
        self.assertIn("Partial boot artifacts removed: yes", result.stderr)
        self.assertIn("Boot selection restored: yes", result.stderr)
        self.assertEqual(state["saved"], "stock")
        self.assertEqual(state["next"], "stock")
        self.assertEqual(state["grub_log"], ["set:patched", "set:stock"])
        self.assertFalse(state["patched_bls"])
        self.assertFalse(state["patched_initramfs"])
        self.assertGreaterEqual(state["transactions"].count("PREPARED"), 2)

    def test_21_help_and_normal_completion_are_workflow_oriented(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        usage = source[source.index("usage() {"):source.index("benchmark_helper() {")]
        help_result = subprocess.run(
            [str(SCRIPT), "--help"], text=True, capture_output=True, check=False
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        for heading in ("Typical activation", "Return to stock", "Inspection", "Preparation", "Activation", "Deactivation", "Recovery only", "Qualification / performance testing"):
            self.assertIn(heading, usage)
            self.assertIn(heading, help_result.stdout)
        self.assertNotIn("build the pinned V33", usage)
        self.assertIn("build the patched amdgpu module", usage)
        self.assertIn("make the verified patched boot persistent", usage)
        self.assertIn("a reboot is required", usage)
        enable = source[source.index("enable() {"):source.index("risky_artifacts_without_state() {")]
        self.assertIn('print_next_action "none — GFX1013 is ready"', enable)
        self.assertIn('echo "Qualification only: sudo bc250 gfx1013 status"', enable)
        disable = source[source.index("disable() {"):source.index("reset() {")]
        self.assertIn('print_next_action "sudo reboot"', disable)
        self.assertNotIn('sudo reboot  # unload', disable)

    def test_114_source_downloads_resume_and_operator_interrupt_is_distinct(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        fetch = source[source.index("fetch_verified_srpm() {"): source.index("find_stock_module() {")]
        cleanup = source[source.index("prepare_cleanup_on_exit() {"): source.index("prepare_preflight() {")]
        self.assertIn("--continue-at -", fetch)
        self.assertIn("resumable partial retained", fetch)
        self.assertIn("validate_source_rpm", fetch)
        self.assertLess(fetch.index('validate_source_rpm "$part"'), fetch.index('mv -f -- "$part" "$dest"'))
        self.assertIn("GFX1013 prepare interrupted by operator.", cleanup)
        self.assertIn("Exit status: 130", cleanup)
        self.assertIn("Rerun 'sudo bc250 gfx1013 prepare' to resume.", cleanup)

    def test_114_long_build_interrupts_kill_process_group_and_queue_attestation_is_compute_only(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        phase = source[source.index("stop_active_phase() {"): source.index("kernel_build_jobs() {")]
        self.assertIn('kill -TERM -- "-$pid"', phase)
        self.assertIn('kill -KILL -- "-$pid"', phase)
        self.assertIn('setsid --wait', phase)
        queue = source[source.index("verify_private_radv_compute_queue() {"): source.index("verify_loaded_amdgpu_identity() {")]
        self.assertIn('QUEUE_COMPUTE_BIT', queue)
        self.assertIn('QUEUE_GRAPHICS_BIT', queue)
        self.assertIn('"QUEUE_GRAPHICS_BIT" not in flags', queue)

    def test_110_records_fedora_kernel_source_lineage_and_transaction_phases(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('check-kernel-provenance.py', source)
        self.assertIn('fedora-prepared-source', source)
        self.assertIn('BC250_GFX1013_KERNEL_SRPM_NEVR=', source)
        self.assertIn('BC250_GFX1013_KERNEL_SOURCE_PROVENANCE_SHA256=', source)
        self.assertIn('BC250_GFX1013_KERNEL_TARGET_MANIFEST_SHA256=', source)
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


    def test_21_gfx_next_action_color_is_tty_only_and_no_color_safe(self) -> None:
        body = (
            f'export BC250_GFX1013_LIBRARY_ONLY=1; source "{SCRIPT}"; '
            'print_next_action "sudo reboot"'
        )
        plain = subprocess.run(
            ["bash", "-c", body],
            text=True,
            capture_output=True,
            env={**os.environ, "TERM": "xterm"},
            check=False,
        )
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertEqual(plain.stdout, "Next action: sudo reboot\n")
        self.assertNotIn("\x1b", plain.stdout)

        rc, tty = run_tty_bash(body, extra_env={"TERM": "xterm"})
        self.assertEqual(rc, 0, tty)
        self.assertIn("\x1b[1;33mNext action: sudo reboot\x1b[0m", tty)

        rc, no_color = run_tty_bash(
            body, extra_env={"TERM": "xterm", "NO_COLOR": "1"}
        )
        self.assertEqual(rc, 0, no_color)
        self.assertIn("Next action: sudo reboot", no_color)
        self.assertNotIn("\x1b", no_color)

    def test_nonroot_status_does_not_infer_missing_lifecycle_state(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("authoritative lifecycle state requires root inspection", source)
        self.assertIn("GFX_LIFECYCLE_STATE=NOT_INSPECTED", source)
        self.assertIn("NOT_INSPECTED) printf 'sudo bc250 gfx1013 status --brief", source)
        self.assertIn("NO_COLOR", source)


if __name__ == "__main__":
    unittest.main()
