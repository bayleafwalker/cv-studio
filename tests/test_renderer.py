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
        with tempfile.TemporaryDirectory() as directory:
            token = server.CONTENT.set(Path(directory))
            try:
                server.save_cv(sample)
                self.assertEqual(server.load_cv()["person"]["name"], "Your Name")
            finally:
                server.CONTENT.reset(token)

    def test_named_profiles_are_isolated(self):
        sample = load_cv("sample")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = server.CONTENT.set(root)
            try:
                server.save_cv(sample, "product-manager")
                self.assertEqual(server.load_cv("product-manager")["person"]["name"], "Your Name")
                self.assertIn("product-manager", {p["id"] for p in server.list_profiles()})
            finally:
                server.CONTENT.reset(token)

    def test_a_stale_put_is_refused_so_an_agents_write_survives(self):
        import http.client, json, threading
        from http.server import ThreadingHTTPServer
        sample = load_cv("sample")
        with tempfile.TemporaryDirectory() as directory:
            old_dir = server.CONTENT_DIR
            server.CONTENT_DIR = Path(directory)
            token = server.CONTENT.set(Path(directory))
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                server.save_cv(sample, "my-cv")
                stamp = {p["id"]: p["mtime"] for p in server.list_profiles()}["my-cv"]
                self.assertTrue(stamp)
                agent = dict(sample, person=dict(sample["person"], name="Written by the GPT"))
                server.save_cv(agent, "my-cv")  # someone else writes while the editor holds the old stamp

                def put(body, stamp=None):
                    headers = {"Content-Type": "application/json"}
                    if stamp:
                        headers["If-Unmodified-Since"] = stamp
                    c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
                    c.request("PUT", "/api/cv?profile=my-cv", body=json.dumps(body), headers=headers)
                    r = c.getresponse(); data = json.loads(r.read()); c.close()
                    return r.status, data

                status, data = put(sample, stamp)
                self.assertEqual(status, 409)
                self.assertEqual(data["cv"]["person"]["name"], "Written by the GPT")
                self.assertEqual(server.load_cv("my-cv")["person"]["name"], "Written by the GPT")
                status, data = put(sample, data["mtime"])  # with the stamp it just read, the save goes through
                self.assertEqual(status, 200)
                self.assertEqual(server.load_cv("my-cv")["person"]["name"], "Your Name")
                self.assertEqual(data["mtime"], {p["id"]: p["mtime"] for p in server.list_profiles()}["my-cv"])
            finally:
                httpd.shutdown(); httpd.server_close()
                server.CONTENT.reset(token); server.CONTENT_DIR = old_dir

    def test_dropped_in_files_are_found_and_problems_explained(self):
        sample = load_cv("sample")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = server.CONTENT.set(root)
            server.profiles_dir().mkdir()
            try:
                (server.profiles_dir() / "cv_airlife_product_engineer.local.json").write_text(
                    server.json.dumps(sample), encoding="utf-8")
                (server.profiles_dir() / "Broken file.json").write_text("{not json", encoding="utf-8")
                (server.profiles_dir() / "no-name.json").write_text('{"template": "classic-two-column"}', encoding="utf-8")
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
                server.CONTENT.reset(token)

    def test_rename_moves_the_file_and_links_are_clickable(self):
        sample = load_cv("sample")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = server.CONTENT.set(root)
            try:
                server.save_cv(sample, "my-cv")
                self.assertEqual(server.rename_cv("my-cv", "Product engineer"), "Product engineer")
                self.assertFalse(server.local_source().exists())
                self.assertEqual(load_cv("Product engineer")["person"]["name"], "Your Name")
                with self.assertRaises(ValueError):
                    server.rename_cv("sample", "x")
            finally:
                server.CONTENT.reset(token)
        rendered = render_html(sample)
        self.assertIn('href="mailto:your.name@example.com"', rendered)
        self.assertIn('href="https://linkedin.com/in/yourname"', rendered)

    def test_persons_have_separate_folders_and_tokens(self):
        old_dir = server.CONTENT_DIR
        with tempfile.TemporaryDirectory() as directory:
            server.CONTENT_DIR = Path(directory)
            try:
                self.assertEqual(server.list_persons(), [])
                server.person_folder("Anna").joinpath("profiles").mkdir(parents=True)
                server.person_folder("Juha").joinpath("profiles").mkdir(parents=True)
                self.assertEqual(server.list_persons(), ["Anna", "Juha"])
                with self.assertRaises(ValueError):
                    server.person_folder("../etc")
                (server.CONTENT_DIR / "tokens.json").write_text('{"secret-1": "Anna", "stale": "Nobody"}', encoding="utf-8")
                self.assertEqual(server.token_person("secret-1"), "Anna")
                self.assertIsNone(server.token_person("stale"))
                self.assertIsNone(server.token_person(""))
                token = server.CONTENT.set(server.person_folder("Anna"))
                try:
                    server.save_cv(load_cv("sample"), "Anna's CV")
                    self.assertTrue((server.person_folder("Anna") / "profiles" / "Anna's CV.local.json").exists())
                finally:
                    server.CONTENT.reset(token)
                server.OIDC_USERINFO = "https://auth.example/application/o/userinfo/"
                calls = []
                lookup = lambda token: calls.append(token) or ({"preferred_username": "Juha", "email": "j@example"} if token == "good" else None)
                self.assertEqual(server.oidc_person("good", lookup), "Juha")
                self.assertEqual(server.oidc_person("good", lookup), "Juha")  # cached
                self.assertEqual(calls, ["good"])
                self.assertTrue((server.person_folder("Juha") / "profiles").is_dir())
                self.assertIsNone(server.oidc_person("bad", lookup))
                server.OIDC_INTROSPECT = "https://auth.example/application/o/introspect/"
                server._userinfo_cache.clear()
                self.assertIsNone(server.oidc_person("good", lookup, check=lambda t: False))  # wrong audience refused
                server._userinfo_cache.clear()
                self.assertEqual(server.oidc_person("good", lookup, check=lambda t: True), "Juha")
                server.OIDC_INTROSPECT = ""
                server.OIDC_USERINFO = ""
                spec = server.openapi("https://cv.example")
                self.assertEqual(spec["servers"][0]["url"], "https://cv.example")
                self.assertIn("/api/cv", spec["paths"])
            finally:
                server.CONTENT_DIR = old_dir

    def test_public_requests_only_get_the_agent_api_with_a_bearer(self):
        import http.client, threading
        from http.server import ThreadingHTTPServer
        old_dir, old_mode = server.CONTENT_DIR, server.PERSONS_MODE
        with tempfile.TemporaryDirectory() as directory:
            server.CONTENT_DIR, server.PERSONS_MODE = Path(directory), True
            server.person_folder("Anna").joinpath("profiles").mkdir(parents=True)
            (server.CONTENT_DIR / "tokens.json").write_text('{"tok": "Anna"}', encoding="utf-8")
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                def call(method, path, headers=None, body=None):
                    c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
                    c.request(method, path, body=body, headers=headers or {}); r = c.getresponse(); data = r.read(); c.close()
                    return r.status, data
                pub = {"X-CV-Studio-Public": "1"}
                import io, contextlib
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    self.assertEqual(call("GET", "/api/schema", {**pub, "Cf-Connecting-Ip": "203.0.113.9"})[0], 200)
                self.assertIn("public 203.0.113.9 person=- GET /api/schema -> 200", buffer.getvalue())
                self.assertEqual(call("GET", "/", pub)[0], 404)                       # editor is never public
                self.assertEqual(call("GET", "/static/app.js", pub)[0], 404)
                self.assertEqual(call("POST", "/api/persons", pub, '{"name":"X"}')[0], 404)
                self.assertIn(call("GET", "/api/persons", {})[0], (401, 404))           # anonymous listing removed
                self.assertEqual(call("GET", "/api/schema", pub)[0], 200)
                self.assertEqual(call("GET", "/api/profiles", pub)[0], 401)            # bearer required
                self.assertEqual(call("GET", "/api/profiles", {**pub, "Cookie": "cv_person=Anna"})[0], 401)  # cookie ignored
                status, data = call("GET", "/api/profiles", {**pub, "Authorization": "Bearer tok"})
                self.assertEqual(status, 200); self.assertIn(b"Example CV", data)
                self.assertEqual(call("DELETE", "/api/cv?profile=my-cv", {**pub, "Authorization": "Bearer tok"})[0], 404)  # no public delete
                self.assertEqual(call("POST", "/api/cv", pub)[0], 404)  # preview endpoint not public
                old_cap, server.Handler.MAX_BODY = server.Handler.MAX_BODY, 10_000
                try:
                    big = '{"pad": "' + 'x' * 20_000 + '"}'
                    self.assertEqual(call("PUT", "/api/cv?profile=my-cv", {**pub, "Authorization": "Bearer tok"}, big)[0], 400)
                finally:
                    server.Handler.MAX_BODY = old_cap
                self.assertEqual(call("GET", "/api/profiles", {"Cookie": "cv_person=Anna"})[0], 200)  # internal cookie still works
                self.assertEqual(call("GET", "/", {})[0], 200)                        # chooser page internally
            finally:
                httpd.shutdown(); httpd.server_close()
                server.CONTENT_DIR, server.PERSONS_MODE = old_dir, old_mode

    def test_preview_has_anchors_for_following_the_editor(self):
        rendered = render_html(load_cv("sample"))
        self.assertIn('data-cv="sections.1.entries.0"', rendered)
        self.assertIn('data-cv="person"', rendered)


if __name__ == "__main__":
    unittest.main()
