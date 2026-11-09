"""Offline SOURCE contracts for post-0.20.0-5 upstream runtime candidates.

These are packaging/integration assertions, not BUILD or installed DEVICE evidence.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(relpath: str) -> str:
    return (ROOT / relpath).read_text(encoding="utf-8")


def runtime_pins() -> dict[str, str]:
    return dict(
        item.split("=", 1)
        for line in read("config/runtime.env").splitlines()
        if (item := line.strip()) and not item.startswith("#")
    )


class RuntimeRefreshContracts(unittest.TestCase):
    def test_version_and_immutable_payload_identity(self) -> None:
        pins = runtime_pins()
        self.assertEqual(pins["BC250_OPEN_WEBUI_VERSION"], "0.13.3")
        self.assertEqual(pins["BC250_OLLAMA_VERSION"], "0.40.15")
        self.assertEqual(pins["BC250_GOVERNOR_VERSION"], "0.4.15")
        self.assertRegex(pins["BC250_OLLAMA_PAYLOAD_SHA256"], r"^[0-9a-f]{64}$")
        self.assertIn("/releases/download/v0.40.15/", pins["BC250_OLLAMA_PAYLOAD_URL"])
        self.assertRegex(pins["BC250_OPEN_WEBUI_IMAGE_DIGEST"], r"^sha256:[0-9a-f]{64}$")
        self.assertIn(
            "ghcr.io/open-webui/open-webui@" + pins["BC250_OPEN_WEBUI_IMAGE_DIGEST"],
            read("config/containers/open-webui.container"),
        )
        self.assertIn("SUPPORTED_OPENWEBUI_VERSION = \"0.13.3\"", read("config/openwebui/runtime/sitecustomize.py"))

    def test_new_scheduled_ai_surfaces_are_disabled_and_converged(self) -> None:
        container = read("config/containers/open-webui.container")
        desired = json.loads(read("config/openwebui/desired-state.json"))
        for flag, key in (
            ("ENABLE_AUTOMATIONS", "automations.enable"),
            ("ENABLE_CALENDAR", "calendar.enable"),
        ):
            self.assertIn(f"Environment={flag}=false", container)
            self.assertIs(desired["application"][key], False)
        owui_setup = read("cmd/openwebui/openwebui-setup.py")
        self.assertIn('client.post("/api/v1/configs/import", {"config": desired_application()})', owui_setup)
        self.assertIn('client.get("/api/v1/configs/export")', owui_setup)

    def test_tika_guard_kept_for_pinned_openwebui_release(self) -> None:
        helper = read("config/openwebui/runtime/sitecustomize.py")
        self.assertIn('TIKA4_MARKDOWN_SUFFIX = "/tika/json/md"', helper)
        self.assertIn('NO_TEXT_PLACEHOLDER = "<No text content found>"', helper)
        self.assertIn("install_tika_empty_content_guard()", helper)
        self.assertIn("PYTHONPATH=/opt/bc250-openwebui-shim:/app/backend", read("config/containers/open-webui.container"))

    def test_governor_udev_rule_unit_package_and_activation(self) -> None:
        pins = runtime_pins()
        self.assertEqual(pins["BC250_GOVERNOR_COMMIT"], "34cea69cdf617d1ad05edc71c4c61df501a13c8e")
        rule = read("config/governor/70-cyan-skillfish-governor.rules")
        self.assertIn('ATTRS{device}=="0x13fe"', rule)
        self.assertIn('ENV{SYSTEMD_ALIAS}+="/dev/cyan_skillfish_gpu"', rule)
        unit = read("config/governor/cyan-skillfish-governor-smu.service")
        self.assertIn("BindsTo=dev-cyan_skillfish_gpu.device", unit)
        self.assertIn("After=dev-cyan_skillfish_gpu.device", unit)
        manifest = read("packaging/install-manifest.tsv")
        self.assertIn("/usr/lib/udev/rules.d/70-cyan-skillfish-governor.rules", manifest)
        spec = read("packaging/bc250-llm-server.spec")
        self.assertIn("%global governor_version 0.4.15", spec)
        self.assertIn("%global governor_commit " + pins["BC250_GOVERNOR_COMMIT"], spec)
        self.assertIn("udevadm control --reload-rules", spec)
        self.assertIn("udevadm trigger --action=change", spec)
        self.assertLess(spec.index("udevadm control --reload-rules"), spec.index("%systemd_post %{bc250_units}"))

    def test_no_kernel_pin_and_no_unqualified_release_reuse(self) -> None:
        spec = read("packaging/bc250-llm-server.spec")
        self.assertNotRegex(spec, r"(?:^|\n)Requires:\s+kernel\s*[=<>]")
        self.assertNotIn("7.2.15-200.fc44", spec)
        self.assertNotIn("7.3.3-200.fc44", spec)
        state = json.loads(read("WORKBENCH-STATE.json"))
        self.assertIn("open-wip", state["release"]["state"])
        self.assertEqual(state["release"]["candidate_nvr"], "not-selected")
        # The frozen 0.20.0-5 RPM spec stays at its last RELEASE identity
        # until a NEW candidate is explicitly selected; never ship modified
        # runtime bytes under this old release label.
        self.assertRegex(spec, r"(?m)^Version:\s+0\.20\.0$")
        self.assertRegex(spec, r"(?m)^Release:\s+5%\{\?dist\}$")

    def test_privacy_related_lanes_are_single_request(self) -> None:
        for name in ("ollama.service", "ollama-task.service", "ollama-embedding.service", "ollama-agent.service"):
            data = read(f"config/systemd/{name}")
            self.assertIn("OLLAMA_NUM_PARALLEL=1", data, name)


if __name__ == "__main__":
    unittest.main()
