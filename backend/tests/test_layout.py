"""Scaffold checks: the app imports, configuration hides secrets, and the data and graph packages are where the scripts expect them."""
import unittest

from app.core.config import BACKEND_DIR, DATA_DIR, GRAPH_DIR, Settings


class LayoutTest(unittest.TestCase):
    def test_app_imports_and_has_health_route(self):
        from app.main import app

        self.assertIn("/health", {route.path for route in app.routes})

    def test_settings_do_not_leak_the_password(self):
        self.assertNotIn("hunter2", repr(Settings(neo4j_password="hunter2")))

    def test_data_and_graph_are_in_place(self):
        self.assertTrue((DATA_DIR / "catalogue" / "noordveld-parts-catalog.xlsx").exists())
        self.assertTrue((DATA_DIR / "processed" / "noordveld-complete-dataset-synthetic-demo.xlsx").exists())
        for part in ("cypher", "schema", "validation", "audits"):
            self.assertTrue((GRAPH_DIR / part).is_dir(), part)
        self.assertEqual(len(list((GRAPH_DIR / "cypher").glob("[0-2]*.cypher"))), 24)

    def test_env_file_is_not_tracked_by_the_example(self):
        self.assertTrue((BACKEND_DIR / ".env.example").exists())


if __name__ == "__main__":
    unittest.main()
