from __future__ import annotations

import hashlib
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
        self.assertIn("PACKAGE_PROFILE=v0.2.1-alpha", source)
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
        self.assertIn("v0.2.1-alpha / experimental / default OFF", result.stdout)
        self.assertIn("Package patch/full-source manifests: PASS", result.stdout)
        self.assertIn("Ollama private-RADV override: disabled", result.stdout)

    def test_lifecycle_is_exact_kernel_stock_first_and_ollama_scoped(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for token in (
            'build="/lib/modules/$kernel/build"',
            "rpm -qp --qf '%{VERSION}-%{RELEASE}",
            "patch --dry-run",
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
            'patched_boot_running || die',
            "VK_DRIVER_FILES=$BC250_GFX1013_ICD",
            'grub2-set-default "$BC250_GFX1013_PATCHED_ENTRY_ID"',
            "enable_cleanup_on_exit",
        ):
            self.assertIn(token, source)
        self.assertNotIn("/etc/environment", source)
        self.assertNotIn("install -m 0755", source[source.find("UPSTREAM_GENERATOR"):])

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
