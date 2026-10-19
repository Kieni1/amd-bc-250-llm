from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/check-gfx1013-mesa.py"
SPEC = importlib.util.spec_from_file_location("bc250_check_gfx1013_mesa", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
mesa_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mesa_check)


class Gfx1013MesaSourceGateTests(unittest.TestCase):
    def test_metadata_pins_exact_fedora_44_mesa_source(self) -> None:
        metadata = mesa_check.read_metadata()
        self.assertEqual(metadata["version"], "26.2.4")
        self.assertEqual(metadata["fedora_release"], "1.fc44")
        self.assertEqual(metadata["srpm_nevra"], "mesa-26.2.4-1.fc44.src")
        self.assertEqual(metadata["source0"], "mesa-26.2.4.tar.xz")
        self.assertEqual(
            metadata["source0_sha256"],
            "bce5f7fbebb934373b86c999a064d52fb5065878dc57f287f95346648ec832e9",
        )


    def test_missing_cargo_prep_macro_fails_early_with_provisioning_hint(self) -> None:
        result = subprocess.CompletedProcess(["rpm"], 0, b"%{cargo_prep}\n", b"")
        with patch.object(mesa_check, "require_command", return_value="rpm"), patch.object(
            mesa_check, "run", return_value=result
        ), self.assertRaisesRegex(mesa_check.ValidationError, "provision-gfx1013-mesa-builddeps"):
            mesa_check.require_rpm_macro("cargo_prep")

    def test_available_cargo_prep_macro_is_accepted(self) -> None:
        result = subprocess.CompletedProcess(["rpm"], 0, b"/usr/bin/true\n", b"")
        with patch.object(mesa_check, "require_command", return_value="rpm"), patch.object(
            mesa_check, "run", return_value=result
        ):
            mesa_check.require_rpm_macro("cargo_prep")

    def test_source_rpm_identity_uses_sourcepackage_not_arch(self) -> None:
        metadata = mesa_check.read_metadata()
        query = subprocess.CompletedProcess(
            ["rpm"], 0, b"mesa-26.2.4-1.fc44\n1\n", b""
        )
        verify = subprocess.CompletedProcess(["rpm"], 0, b"digests signatures OK\n", b"")
        with patch.object(mesa_check, "require_command", return_value="rpm"), patch.object(
            mesa_check, "run", side_effect=[query, verify]
        ):
            mesa_check.validate_srpm_identity(Path("mesa-26.2.4-1.fc44.src.rpm"), metadata)

    def test_binary_rpm_is_rejected_even_when_nevr_matches(self) -> None:
        metadata = mesa_check.read_metadata()
        query = subprocess.CompletedProcess(
            ["rpm"], 0, b"mesa-26.2.4-1.fc44\n0\n", b""
        )
        with (
            patch.object(mesa_check, "require_command", return_value="rpm"),
            patch.object(mesa_check, "run", return_value=query),
            self.assertRaises(mesa_check.ValidationError),
        ):
            mesa_check.validate_srpm_identity(Path("mesa.rpm"), metadata)

    def test_patch_identity_matches_closed_manifest(self) -> None:
        mesa_check.validate_patch_identity()

    def test_patch_identity_rejects_mixed_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            patch_path = root / "patch.patch"
            manifest_path = root / "PATCH-SHA256SUMS"
            patch_path.write_text("different patch\n", encoding="utf-8")
            manifest_path.write_text(
                "0" * 64 + "  " + mesa_check.PATCH_MANIFEST_PATH + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                mesa_check.ValidationError, "patch identity mismatch"
            ):
                mesa_check.validate_patch_identity(patch_path, manifest_path)

    def test_private_patch_is_minimal_for_current_mesa_baseline(self) -> None:
        patch = mesa_check.PATCH.read_text(encoding="utf-8")
        self.assertIn("GFX1013 is known to have broken compute queue", patch)
        self.assertIn("info->family == CHIP_GFX1013", patch)
        self.assertNotIn("ver_minor = info->ip[AMD_IP_COMPUTE].ver_minor = 1", patch)
        self.assertIn("already contains the GFX1013 GFX10.1 IP-version", patch)

    def test_patch_is_syntactically_valid_with_zero_fuzz(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "src/amd/common/ac_gpu_info.c"
            target.parent.mkdir(parents=True)
            lines = [f"/* filler {index} */\n" for index in range(1, 1100)]
            first = [
                "      /* Userqueue path: report support for the requested IP type.\n",
                "       * supported or not. Setting this variable to 1 for userqueues.\n",
                "       */\n",
                "      info->ip[ip_type].num_queues = 1;\n",
                "   } else if (ip_info->available_rings) {\n",
                "      /* GFX1013 is known to have broken compute queue */\n",
                "      if (ip_type == AMD_IP_COMPUTE && device_info->family == FAMILY_NV &&\n",
                "          ASICREV_IS(device_info->external_rev, GFX1013))\n",
                "         return false;\n",
                "\n",
                "      info->ip[ip_type].num_queues = util_bitcount(ip_info->available_rings);\n",
                "   }\n",
                "\n",
                "   /* Gfx6-8 don't set ip_discovery_version. */\n",
            ]
            second = [
                "    * dimension mode.\n",
                "    */\n",
                "   info->has_async_compute_threadgroup_bug = info->family == CHIP_ICELAND ||\n",
                "                                             info->family == CHIP_TONGA;\n",
                "\n",
                "   /* GFX7 CP requires 32 bytes alignment for the indirect buffer arguments on\n",
                "    * the compute queue.\n",
            ]
            lines[476 : 476 + len(first)] = first
            lines[1014 : 1014 + len(second)] = second
            target.write_text("".join(lines), encoding="utf-8")
            result = subprocess.run(
                ["patch", "--batch", "--forward", "--fuzz=0", "--dry-run", "-p1", "-i", str(mesa_check.PATCH)],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_semantic_guard_rejects_missing_upstreamed_ip_fix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "ac_gpu_info.c"
            source.write_text(
                "/* Fix incorrect IP versions reported by the kernel. */\n"
                "/* no GFX1013 correction here */\n"
                "   /* GFX1013 is known to have broken compute queue */\n"
                "   if (device_info.family == FAMILY_NV && ASICREV_IS(device_info.external_rev, GFX1013)) {\n"
                "      info->ip[AMD_IP_COMPUTE].num_queues = 0;\n"
                "   }\n"
                "info->family == CHIP_TONGA;\n",
                encoding="utf-8",
            )
            with self.assertRaises(mesa_check.ValidationError):
                mesa_check.validate_pre_patch_semantics(source)


    def test_semantic_guard_accepts_fedora_prepared_helper_local_queue_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "ac_gpu_info.c"
            source.write_text(
                "/* Fix incorrect IP versions reported by the kernel. */\n"
                "if (device_info->family == FAMILY_NV &&\n"
                "    ASICREV_IS(device_info->external_rev, GFX1013)) {\n"
                "   info->ip[AMD_IP_GFX].ver_minor = info->ip[AMD_IP_COMPUTE].ver_minor = 1;\n"
                "}\n"
                "   } else if (ip_info->available_rings) {\n"
                "      /* GFX1013 is known to have broken compute queue */\n"
                "      if (ip_type == AMD_IP_COMPUTE && device_info->family == FAMILY_NV &&\n"
                "          ASICREV_IS(device_info->external_rev, GFX1013))\n"
                "         return false;\n"
                "\n"
                "      info->ip[ip_type].num_queues = util_bitcount(ip_info->available_rings);\n"
                "   }\n"
                "info->family == CHIP_TONGA;\n",
                encoding="utf-8",
            )
            mesa_check.validate_pre_patch_semantics(source)

    def test_semantic_guard_rejects_post_enumeration_queue_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "ac_gpu_info.c"
            source.write_text(
                "/* Fix incorrect IP versions reported by the kernel. */\n"
                "if (device_info->family == FAMILY_NV &&\n"
                "    ASICREV_IS(device_info->external_rev, GFX1013)) {\n"
                "   info->ip[AMD_IP_GFX].ver_minor = info->ip[AMD_IP_COMPUTE].ver_minor = 1;\n"
                "}\n"
                "/* GFX1013 is known to have broken compute queue */\n"
                "if (device_info.family == FAMILY_NV && ASICREV_IS(device_info.external_rev, GFX1013)) {\n"
                "   info->ip[AMD_IP_COMPUTE].num_queues = 0;\n"
                "}\n"
                "info->family == CHIP_TONGA;\n",
                encoding="utf-8",
            )
            with self.assertRaises(mesa_check.ValidationError):
                mesa_check.validate_pre_patch_semantics(source)


    def test_headless_meson_schema_requires_exact_profile_options(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            options = root / "meson.options"
            options.write_text(
                "\n".join(f"option('{name}', type : 'string')" for name in mesa_check.HEADLESS_MESON_OPTIONS) + "\n",
                encoding="utf-8",
            )
            mesa_check.validate_headless_meson_schema(root)
            options.write_text("option('platforms', type : 'array')\n", encoding="utf-8")
            with self.assertRaisesRegex(mesa_check.ValidationError, "headless RADV Meson options"):
                mesa_check.validate_headless_meson_schema(root)


    def test_fedora_prep_dependencies_are_declared(self) -> None:
        gfx = (ROOT / "cmd/system/gfx1013.sh").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(encoding="utf-8")
        local_build = (ROOT / "build-local.sh").read_text(encoding="utf-8")
        kernel_provision = (ROOT / "scripts/provision-gfx1013-kernel-builddeps.sh").read_text(encoding="utf-8")
        mesa_provision = (ROOT / "scripts/provision-gfx1013-mesa-builddeps.sh").read_text(encoding="utf-8")
        self.assertIn("cargo-rpm-macros", gfx)
        self.assertIn("git-core", gfx)
        self.assertIn("redhat-rpm-config", gfx)
        self.assertIn("kernel-srpm-macros", gfx)
        self.assertNotIn("cargo-rpm-macros", workflow)
        self.assertIn("provision-gfx1013-kernel-builddeps.sh", local_build)
        self.assertIn("provision-gfx1013-mesa-builddeps.sh", local_build)
        self.assertIn('dnf --disable-repo=fedora-cisco-openh264 -y builddep --srpm "$srpm"', kernel_provision)
        self.assertIn('dnf --disable-repo=fedora-cisco-openh264 -y builddep --srpm "$srpm"', mesa_provision)
        packages = gfx[gfx.index("GFX_BUILD_PACKAGES=("): gfx.index("build_requirement_provider() {")]
        for requirement in ("cargo-rpm-macros", "bzip2", "meson", "ninja-build", "gcc-c++", "vulkan-headers", "systemd-devel", "spirv-tools-devel", "pkgconf-pkg-config"):
            self.assertIn(requirement, packages)
        packages = gfx[gfx.index("GFX_BUILD_PACKAGES=("): gfx.index("build_requirement_provider() {")]
        for gui_requirement in ("libX11-devel", "libxcb-devel", "wayland-devel", "libdisplay-info-devel"):
            self.assertNotIn(gui_requirement, packages)
        self.assertIn("rpmbuild -bp --nodeps", gfx)


if __name__ == "__main__":
    unittest.main()
