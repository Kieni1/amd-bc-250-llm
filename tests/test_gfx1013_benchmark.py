from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = ROOT / "cmd/benchmark"
sys.path.insert(0, str(BENCH_DIR))
SPEC = importlib.util.spec_from_file_location("gfx1013_ab", BENCH_DIR / "gfx1013-ab.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Gfx1013BenchmarkTests(unittest.TestCase):
    def test_role_screen_is_standard_advanced_with_optional_deep(self) -> None:
        roles = MODULE.model_roles(False)
        self.assertEqual(list(roles), ["standard", "advanced"])
        self.assertEqual(
            roles["standard"]["model"],
            "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl:latest",
        )
        self.assertEqual(
            roles["advanced"]["model"],
            "prod-qwen35-9b-unsloth-q6-k:latest",
        )
        deep = MODULE.model_roles(True)
        self.assertEqual(list(deep), ["standard", "advanced", "deep"])
        self.assertEqual(
            deep["deep"]["model"],
            "prod-gpt-oss20b-ggml-org-mxfp4:latest",
        )

    def test_comparison_uses_directionally_correct_gain_math(self) -> None:
        self.assertAlmostEqual(MODULE.delta_pct(100, 120), 20.0)
        self.assertAlmostEqual(MODULE.delta_pct(10, 8, lower_is_better=True), 20.0)
        self.assertAlmostEqual(MODULE.delta_pct(100, 95), -5.0)

    def test_recommendation_requires_a2_and_clean_safety_evidence(self) -> None:
        aggregate_a1 = {
            "prompt_tps_cv_pct": 2.0,
            "generation_tps_cv_pct": 2.0,
            "mem_available_min_mib": 1000.0,
            "swap_peak_delta_mib": 0.0,
            "temp_max_c": 70.0,
        }
        aggregate_b = {
            "prompt_tps_cv_pct": 2.5,
            "generation_tps_cv_pct": 2.5,
            "mem_available_min_mib": 980.0,
            "swap_peak_delta_mib": 0.0,
            "temp_max_c": 71.0,
        }
        aggregate_a2 = dict(aggregate_a1)
        role = {
            "delta": {"prompt_tps_gain_pct": 10.0, "generation_tps_gain_pct": 7.0},
            "a1_stock": aggregate_a1,
            "b_gfx": aggregate_b,
            "a2_restored": aggregate_a2,
            "a2_control_drift": {
                "prompt_tps_vs_a1_pct": 1.0,
                "generation_tps_vs_a1_pct": -1.0,
            },
        }
        clean_meta = {
            "gpu_fault_count": 0,
            "gpu_journal_error": None,
            "ollama_restart_delta": 0,
            "residency_restoration": "PASS",
        }
        report = {
            "roles": {"standard": role, "advanced": role},
            "a1_stock_meta": clean_meta,
            "b_gfx_meta": clean_meta,
            "a2_restored_meta": clean_meta,
            "a2_restored_present": True,
        }
        self.assertEqual(MODULE.recommendation(report)["state"], "PROMOTION_CANDIDATE")
        report["a2_restored_present"] = False
        self.assertEqual(MODULE.recommendation(report)["state"], "KEEP_OPTIONAL")
        report["a2_restored_present"] = True
        report["b_gfx_meta"] = {**clean_meta, "gpu_fault_count": 1}
        self.assertEqual(MODULE.recommendation(report)["state"], "KEEP_OPTIONAL")


    def test_report_can_be_generated_without_mutating_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            campaign = root / "campaign-test"
            for phase in ("stock", "gfx", "restored"):
                (campaign / phase).mkdir(parents=True, exist_ok=True)
            model = "prod-gemma4-e2b-unsloth-qat-ud-q4-k-xl:latest"
            base = {
                "schema": MODULE.SCHEMA,
                "identity": {
                    "package_nevra": "bc250-llm-server-0.13.1-1.7.fc44.x86_64",
                    "kernel": "test",
                },
                "models": {"standard": {"model": model, "digest": "abc"}},
                "phases": {"stock": "CAPTURED", "gfx": "CAPTURED", "restored": "CAPTURED"},
            }
            (campaign / "campaign.json").write_text(json.dumps(base), encoding="utf-8")

            def role(prompt: float, generation: float, temp: float) -> dict[str, object]:
                return {
                    "model": model,
                    "digest": "abc",
                    "aggregate": {
                        "prompt_tps_median": prompt,
                        "generation_tps_median": generation,
                        "prompt_tps_cv_pct": 2.0,
                        "generation_tps_cv_pct": 2.0,
                        "ttfc_s_median": 2.0,
                        "ttfa_s_median": 2.5,
                        "cold_load_s": 4.0,
                        "mem_available_min_mib": 1000.0,
                        "swap_peak_delta_mib": 0.0,
                        "temp_max_c": temp,
                    },
                }

            common = {
                "gpu_fault_count": 0,
                "gpu_journal_error": None,
                "ollama_restart_delta": 0,
                "memory_psi_delta_total_us": {"some_total_us": 0, "full_total_us": 0},
                "residency_restoration": "PASS",
            }
            phases = {
                "stock": role(100.0, 50.0, 70.0),
                "gfx": role(112.0, 55.0, 71.0),
                "restored": role(101.0, 49.5, 70.0),
            }
            for phase, role_payload in phases.items():
                (campaign / phase / "phase.json").write_text(
                    json.dumps({**common, "roles": {"standard": role_payload}}),
                    encoding="utf-8",
                )
                MODULE.closed_manifest(campaign / phase)
            MODULE.closed_manifest(campaign)
            args = Namespace(root=root, campaign_dir=campaign)
            self.assertEqual(MODULE.report_campaign(args), 0)
            report = json.loads((campaign / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["schema"], MODULE.REPORT_SCHEMA)
            self.assertAlmostEqual(
                report["roles"]["standard"]["delta"]["prompt_tps_gain_pct"], 12.0
            )
            self.assertEqual(report["recommendation"]["state"], "PROMOTION_CANDIDATE")
            self.assertIn("A2 restored-stock control: CAPTURED", (campaign / "report.txt").read_text())


    def test_closed_manifest_rejects_unlisted_or_modified_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            evidence = directory / "phase.json"
            evidence.write_text("{}\n", encoding="utf-8")
            MODULE.closed_manifest(directory)
            MODULE.verify_closed_manifest(directory)
            evidence.write_text('{"changed": true}\n', encoding="utf-8")
            with self.assertRaises(MODULE.BenchmarkError):
                MODULE.verify_closed_manifest(directory)

    def test_closed_manifest_rejects_symlinked_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            target = directory / "target.json"
            target.write_text("{}\n", encoding="utf-8")
            link = directory / "phase.json"
            link.symlink_to(target.name)
            with self.assertRaises(MODULE.BenchmarkError):
                MODULE.closed_manifest(directory)

    def test_gfx_lifecycle_exposes_benchmark_without_automating_transitions(self) -> None:
        source = (ROOT / "cmd/system/gfx1013.sh").read_text(encoding="utf-8")
        self.assertIn("benchmark {stock|gfx|restored|status|report}", source)
        self.assertIn("Benchmarking", source)
        function = source[source.index("benchmark() {"): source.index("say() {")]
        self.assertNotIn("prepare", function)
        self.assertNotIn("enable", function)
        self.assertNotIn("disable", function)
        self.assertIn('exec python3 "$helper"', function)


if __name__ == "__main__":
    unittest.main()
