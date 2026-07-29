import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from server import TEMPLATES, load_cv, render_html, validate


class RendererTests(unittest.TestCase):
    def test_sample_is_valid_and_renders(self):
        cv = load_cv()
        self.assertEqual(validate(cv), [])
        rendered = render_html(cv)
        self.assertIn("Your Name", rendered)
        self.assertIn("@page { size: A4", rendered)

    def test_invalid_template_is_explained(self):
        cv = load_cv()
        cv["template"] = "missing"
        self.assertIn("Choose one", " ".join(validate(cv)))

    def test_manifests_have_matching_stylesheets(self):
        self.assertIn("classic-two-column", TEMPLATES)
        for template in TEMPLATES.values():
            self.assertTrue(template["css_path"].is_file())

    def test_save_is_a_readable_round_trip(self):
        sample = load_cv()
        original = server.LOCAL_SOURCE
        with tempfile.TemporaryDirectory() as directory:
            server.LOCAL_SOURCE = Path(directory) / "cv.local.json"
            try:
                server.save_cv(sample)
                self.assertEqual(server.load_cv()["person"]["name"], "Your Name")
            finally:
                server.LOCAL_SOURCE = original


if __name__ == "__main__":
    unittest.main()
