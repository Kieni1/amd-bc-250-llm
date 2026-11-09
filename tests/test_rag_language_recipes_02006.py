"""Private DE/FR RAG testing recipes must not alter production defaults."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PrivateRagRecipes(unittest.TestCase):
    def test_two_private_distinct_language_recipes_with_single_existing_base(self) -> None:
        doc = json.loads((ROOT / "examples/openwebui/de-fr-rag-testing-recipes.json").read_text())
        self.assertTrue(doc["not_an_openwebui_api_import"])
        self.assertEqual(doc["product_role_unchanged"], "bc250-office-documents")
        recipes = doc["recipes"]
        self.assertEqual({r["language"] for r in recipes}, {"de", "fr"})
        self.assertEqual({r["id"] for r in recipes}, {"bc250-test-documents-de", "bc250-test-documents-fr"})
        production = {m["id"]:m for m in json.loads((ROOT / "config/openwebui/models.json").read_text())["models"]}
        self.assertNotIn(recipes[0]["id"], production)
        self.assertNotIn(recipes[1]["id"], production)
        for recipe in recipes:
            with self.subTest(recipe=recipe["id"]):
                self.assertEqual(recipe["base_model_id"], production["bc250-office-documents"]["base_model_id"])
                self.assertEqual(recipe["visibility"], "administrator-private")
                self.assertFalse(recipe["automatic_application"])
                self.assertIsNone(recipe["knowledge_collection_id"])
                self.assertTrue(recipe["test_controls"]["no_chat_or_folder_inherited_knowledge"])
                self.assertTrue(recipe["test_controls"]["verify_effective_tool_scope_in_fresh_chat"])

    def test_package_examples_but_not_product_authority(self) -> None:
        manifest = (ROOT / "packaging/install-manifest.tsv").read_text()
        self.assertIn("examples/openwebui/de-fr-rag-testing-recipes.json", manifest)
        self.assertIn("examples/openwebui/README.md", manifest)
        self.assertNotIn("de-fr-rag-testing-recipes.json", (ROOT / "config/openwebui/models.json").read_text())
        readme = (ROOT / "examples/openwebui/README.md").read_text()
        self.assertIn("not Open WebUI import payloads", readme)
        self.assertIn("actual Knowledge tool calls", readme)

    def test_knowledge_settings_remain_unchanged(self) -> None:
        desired = json.loads((ROOT / "config/openwebui/desired-state.json").read_text())
        self.assertEqual(desired["rag"]["TOP_K"], 6)
        self.assertEqual(desired["rag"]["CHUNK_SIZE"], 1500)
        self.assertEqual(desired["rag"]["CHUNK_OVERLAP"], 200)
        self.assertFalse(desired["rag"]["ENABLE_RAG_HYBRID_SEARCH"])
        self.assertEqual(desired["rag"]["RELEVANCE_THRESHOLD"], 0)


if __name__ == "__main__":
    unittest.main()
