from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "quality-checks/translation/owui-provider-config.py"
spec = importlib.util.spec_from_file_location("bc250_owui_provider", HELPER)
provider = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(provider)


def config(*, model_ids=None, prefix_id=None, enabled=True, extra_provider=False):
    main = {
        "enable": enabled,
        "model_ids": model_ids,
        "prefix_id": prefix_id,
        "key": "provider-secret",
        "headers": {"Authorization": "Bearer other-secret", "X-Custom": "opaque"},
        "keep": {"nested": [1, 2, 3]},
    }
    urls = ["http://host.containers.internal:11434", "http://host.containers.internal:11437"]
    configs = {"0": main, "1": {"enable": True, "model_ids": ["embed-model"]}}
    if extra_provider:
        urls.append("http://127.0.0.1:11434")
        configs["2"] = {"enable": True, "model_ids": ["other"]}
    return {
        "ENABLE_OLLAMA_API": True,
        "OLLAMA_BASE_URLS": urls,
        "OLLAMA_API_CONFIGS": configs,
        "unrelated_top_level": "preserve-me",
    }


class TranslationProviderConfigTests(unittest.TestCase):
    def test_restricted_provider_appends_candidate_once_and_preserves_other_fields(self):
        original = config(model_ids=["prod-a", "prod-b"])
        candidate, meta = provider.prepare_candidate(original, "exp-test:latest")
        self.assertTrue(meta["allowlist_changed"])
        self.assertEqual(candidate["OLLAMA_API_CONFIGS"]["0"]["model_ids"], ["prod-a", "prod-b", "exp-test:latest"])
        self.assertEqual(original["OLLAMA_API_CONFIGS"]["0"]["model_ids"], ["prod-a", "prod-b"])
        expected = json.loads(json.dumps(original))
        expected["OLLAMA_API_CONFIGS"]["0"]["model_ids"].append("exp-test:latest")
        self.assertEqual(candidate, expected)

        again, second = provider.prepare_candidate(candidate, "exp-test:latest")
        self.assertFalse(second["allowlist_changed"])
        self.assertEqual(again["OLLAMA_API_CONFIGS"]["0"]["model_ids"].count("exp-test:latest"), 1)

    def test_unrestricted_provider_remains_unrestricted(self):
        for model_ids in (None, []):
            with self.subTest(model_ids=model_ids):
                original = config(model_ids=model_ids)
                if model_ids is None:
                    original["OLLAMA_API_CONFIGS"]["0"].pop("model_ids")
                candidate, meta = provider.prepare_candidate(original, "exp-test:latest")
                self.assertFalse(meta["allowlist_changed"])
                self.assertEqual(candidate, original)

    def test_prefix_uses_raw_allowlist_id_and_prefixed_effective_id(self):
        candidate, meta = provider.prepare_candidate(
            config(model_ids=["prod-a"], prefix_id="local"), "exp-test:latest"
        )
        self.assertIn("exp-test:latest", candidate["OLLAMA_API_CONFIGS"]["0"]["model_ids"])
        self.assertEqual(meta["effective_candidate_id"], "local.exp-test:latest")

    def test_disabled_or_ambiguous_main_provider_fails_closed(self):
        with self.assertRaises(ValueError):
            provider.prepare_candidate(config(model_ids=["prod-a"], enabled=False), "exp-test:latest")
        with self.assertRaises(ValueError):
            provider.prepare_candidate(config(model_ids=["prod-a"], extra_provider=True), "exp-test:latest")
        missing = config(model_ids=["prod-a"])
        missing["OLLAMA_BASE_URLS"] = ["http://host.containers.internal:11437"]
        missing["OLLAMA_API_CONFIGS"] = {"0": {"enable": True}}
        with self.assertRaises(ValueError):
            provider.prepare_candidate(missing, "exp-test:latest")
        disabled_global = config(model_ids=["prod-a"])
        disabled_global["ENABLE_OLLAMA_API"] = False
        with self.assertRaises(ValueError):
            provider.prepare_candidate(disabled_global, "exp-test:latest")

    def test_config_compare_detects_restoration_mismatch(self):
        original = config(model_ids=["prod-a"])
        changed, _ = provider.prepare_candidate(original, "exp-test:latest")
        self.assertTrue(provider.configs_match(original, json.loads(json.dumps(original))))
        self.assertFalse(provider.configs_match(original, changed))

    def test_owui_wrapper_fails_closed_around_provider_mutation(self):
        script = (ROOT / "quality-checks/translation/20-owui-candidate-screen.sh").read_text(encoding="utf-8")
        self.assertIn("flock -n", script)
        self.assertIn("save_original_ollama_config", script)
        self.assertIn("restore_original_ollama_config", script)
        self.assertIn("candidate effective visibility was not restored", script)
        self.assertIn("Tarball: WITHHELD", script)
        self.assertNotIn("HTTP_TMP", script)

    def test_redaction_and_secret_scan_cover_provider_credentials(self):
        original = config(model_ids=["prod-a"])
        original["OLLAMA_BASE_URLS"][0] = "https://alice:url-secret@example.test:11434/api"
        redacted = provider.redact(original)
        main = redacted["OLLAMA_API_CONFIGS"]["0"]
        self.assertEqual(main["key"], "<redacted>")
        self.assertEqual(main["headers"], "<redacted>")
        self.assertNotIn("alice", redacted["OLLAMA_BASE_URLS"][0])
        secrets = provider.collect_secrets(original)
        self.assertTrue({"provider-secret", "Bearer other-secret", "opaque", "alice", "url-secret"} <= secrets)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "evidence.txt").write_text("Bearer other-secret", encoding="utf-8")
            self.assertEqual(provider.scan_tree_for_secrets(root, secrets), [str(root / "evidence.txt")])


if __name__ == "__main__":
    unittest.main()
