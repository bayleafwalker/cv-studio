import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from server import TEMPLATES, load_cv, render_html, validate


class RendererTests(unittest.TestCase):
    def test_sample_is_valid_and_renders(self):
        cv = load_cv("sample")
        self.assertEqual(validate(cv), [])
        rendered = render_html(cv)
        self.assertIn("Your Name", rendered)
        self.assertIn("@page { size: A4", rendered)

    def test_invalid_template_is_explained(self):
        cv = load_cv("sample")
        cv["template"] = "missing"
        self.assertIn("Choose one", " ".join(validate(cv)))

    def test_manifests_have_matching_stylesheets(self):
        self.assertIn("classic-two-column", TEMPLATES)
        for template in TEMPLATES.values():
            self.assertTrue(template["css_path"].is_file())

    def test_save_is_a_readable_round_trip(self):
        sample = load_cv("sample")
        original = server.LOCAL_SOURCE
        with tempfile.TemporaryDirectory() as directory:
            server.LOCAL_SOURCE = Path(directory) / "cv.local.json"
            try:
                server.save_cv(sample)
                self.assertEqual(server.load_cv()["person"]["name"], "Your Name")
            finally:
                server.LOCAL_SOURCE = original

    def test_named_profiles_are_isolated(self):
        sample = load_cv("sample")
        old_local, old_profiles = server.LOCAL_SOURCE, server.PROFILES_DIR
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server.LOCAL_SOURCE, server.PROFILES_DIR = root / "cv.local.json", root / "profiles"
            try:
                server.save_cv(sample, "product-manager")
                self.assertEqual(server.load_cv("product-manager")["person"]["name"], "Your Name")
                self.assertIn("product-manager", {p["id"] for p in server.list_profiles()})
            finally:
                server.LOCAL_SOURCE, server.PROFILES_DIR = old_local, old_profiles

    def test_dropped_in_files_are_found_and_problems_explained(self):
        sample = load_cv("sample")
        old_local, old_profiles = server.LOCAL_SOURCE, server.PROFILES_DIR
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server.LOCAL_SOURCE, server.PROFILES_DIR = root / "cv.local.json", root / "profiles"
            server.PROFILES_DIR.mkdir()
            try:
                (server.PROFILES_DIR / "cv_airlife_product_engineer.local.json").write_text(
                    server.json.dumps(sample), encoding="utf-8")
                (server.PROFILES_DIR / "Broken file.json").write_text("{not json", encoding="utf-8")
                (server.PROFILES_DIR / "no-name.json").write_text('{"template": "classic-two-column"}', encoding="utf-8")
                found = {p["id"]: p for p in server.list_profiles()}
                self.assertIsNone(found["cv_airlife_product_engineer"].get("error"))
                self.assertEqual(found["cv_airlife_product_engineer"]["label"], "Airlife product engineer")
                self.assertIn("not valid JSON", found["Broken file"]["error"])
                self.assertIn("name", found["no-name"]["error"])
                self.assertEqual(server.default_profile(), "cv_airlife_product_engineer")
                self.assertEqual(load_cv("cv_airlife_product_engineer")["person"]["name"], "Your Name")
                with self.assertRaises(ValueError):
                    load_cv("Broken file")
                self.assertEqual(server.new_profile_id("cv_airlife_product_engineer.local.json"), "cv_airlife_product_engineer")
                server.delete_cv("Broken file")
                self.assertNotIn("Broken file", {p["id"] for p in server.list_profiles()})
            finally:
                server.LOCAL_SOURCE, server.PROFILES_DIR = old_local, old_profiles

    def test_rename_moves_the_file_and_links_are_clickable(self):
        sample = load_cv("sample")
        old_local, old_profiles = server.LOCAL_SOURCE, server.PROFILES_DIR
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server.LOCAL_SOURCE, server.PROFILES_DIR = root / "cv.local.json", root / "profiles"
            try:
                server.save_cv(sample, "my-cv")
                self.assertEqual(server.rename_cv("my-cv", "Product engineer"), "Product engineer")
                self.assertFalse(server.LOCAL_SOURCE.exists())
                self.assertEqual(load_cv("Product engineer")["person"]["name"], "Your Name")
                with self.assertRaises(ValueError):
                    server.rename_cv("sample", "x")
            finally:
                server.LOCAL_SOURCE, server.PROFILES_DIR = old_local, old_profiles
        rendered = render_html(sample)
        self.assertIn('href="mailto:your.name@example.com"', rendered)
        self.assertIn('href="https://linkedin.com/in/yourname"', rendered)

    def test_preview_has_anchors_for_following_the_editor(self):
        rendered = render_html(load_cv("sample"))
        self.assertIn('data-cv="sections.1.entries.0"', rendered)
        self.assertIn('data-cv="person"', rendered)


if __name__ == "__main__":
    unittest.main()
