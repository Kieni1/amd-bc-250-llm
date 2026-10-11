from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

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
                "      */\n",
                "      info->ip[ip_type].num_queues = 1;\n",
                "   } else if (ip_info->available_rings) {\n",
                "      /* GFX1013 is known to have broken compute queue */\n",
                "      if (ip_type == AMD_IP_COMPUTE && device_info->family == FAMILY_NV &&\n",
                "          ASICREV_IS(device_info->external_rev, GFX1013))\n",
                "         return false;\n",
                "\n",
                "      info->ip[ip_type].num_queues = util_bitcount(ip_info->available_rings);\n",
                "   } else {\n",
                "      return false;\n",
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
            lines[479 : 479 + len(first)] = first
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
                "/* GFX1013 is known to have broken compute queue */\n"
                "info->family == CHIP_TONGA;\n",
                encoding="utf-8",
            )
            with self.assertRaises(mesa_check.ValidationError):
                mesa_check.validate_pre_patch_semantics(source)

    def test_fedora_prep_dependencies_are_declared(self) -> None:
        gfx = (ROOT / "cmd/system/gfx1013.sh").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/build-rpm.yml").read_text(encoding="utf-8")
        ci_local = (ROOT / "scripts/ci-local.sh").read_text(encoding="utf-8")
        self.assertIn("cargo-rpm-macros", gfx)
        self.assertIn("cargo-rpm-macros", workflow)
        self.assertIn("cargo-rpm-macros", ci_local)
        self.assertIn("rpmbuild -bp --nodeps", gfx)


if __name__ == "__main__":
    unittest.main()
