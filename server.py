#!/usr/bin/env python3
"""Local-only editor and renderer for the compact classic CV template family."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
SAMPLE_SOURCE = ROOT / "content" / "cv.sample.json"
CONTENT_DIR = Path(os.environ.get("CV_STUDIO_CONTENT") or ROOT / "content")  # personal files; tests point this elsewhere
LOCAL_SOURCE = CONTENT_DIR / "cv.local.json"
PROFILES_DIR = CONTENT_DIR / "profiles"
PROFILE_ID = re.compile(r'^[^.\\/:*?"<>|\x00-\x1f][^\\/:*?"<>|\x00-\x1f]{0,99}$')
TEMPLATE_DIR = ROOT / "templates"


def discover_templates() -> dict[str, dict]:
    """Load presentation manifests; content is deliberately not stored in them."""
    found = {}
    for manifest_path in TEMPLATE_DIR.glob("*.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        template_id = manifest.get("id")
        if not isinstance(template_id, str) or not template_id:
            raise ValueError(f"{manifest_path.name}: template needs a non-empty id")
        css_path = TEMPLATE_DIR / f"{template_id}.css"
        if not css_path.is_file():
            raise ValueError(f"{manifest_path.name}: missing {css_path.name}")
        found[template_id] = {**manifest, "css_path": css_path}
    if not found:
        raise ValueError("No CV templates were found.")
    return found


TEMPLATES = discover_templates()


def read_version() -> str:
    try:
        import tomllib
        return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    except Exception:  # pragma: no cover - version is cosmetic
        return "unknown"


VERSION = read_version()


def profile_label(profile_id: str) -> str:
    words = re.sub(r"[-_.]+", " ", profile_id).strip()
    words = re.sub(r"^(cv|resume)\s+", "", words, flags=re.I) or words
    return words[:1].upper() + words[1:]


def scan_profiles() -> list[dict]:
    """Every CV file the app can see, including ones it cannot read, with a plain-language problem."""
    found: list[dict] = [{"id": "sample", "label": "Example CV", "path": SAMPLE_SOURCE, "file": SAMPLE_SOURCE.name}]
    candidates: list[Path] = []
    if LOCAL_SOURCE.exists():
        candidates.append(LOCAL_SOURCE)
    for folder in (LOCAL_SOURCE.parent, PROFILES_DIR):
        if folder.is_dir():
            candidates += sorted(p for p in folder.glob("*.json") if p not in (SAMPLE_SOURCE, LOCAL_SOURCE) and not p.name.startswith("."))
    seen = {"sample"}
    for path in candidates:
        if path == LOCAL_SOURCE:
            item = {"id": "my-cv", "label": "My CV", "path": path}
        else:
            profile_id = path.name.removesuffix(".json").removesuffix(".local")
            item = {"id": profile_id, "label": profile_label(profile_id), "path": path}
            if not PROFILE_ID.fullmatch(profile_id) or ".." in profile_id:
                item["error"] = "Rename this file: names may not start with a dot or contain \\ / : * ? \" < > |."
            elif profile_id in seen:
                item["error"] = "Another CV file already has this name. Rename one of them."
        item["file"] = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        item.setdefault("error", file_problem(path))
        seen.add(item["id"])
        found.append(item)
    return found


def file_problem(path: Path) -> str | None:
    """Explain why a CV file cannot be used, or None when it is fine."""
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return f"The file could not be read: {exc.strerror or exc}."
    try:
        cv = json.loads(raw)
    except json.JSONDecodeError as exc:
        return f"This is not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}."
    errors = validate(cv)
    return " ".join(errors) if errors else None


def list_profiles() -> list[dict[str, str]]:
    return [{key: value for key, value in item.items() if key != "path"} for item in scan_profiles()]


def profile_path(profile: str) -> Path:
    if profile == "sample":
        return SAMPLE_SOURCE
    if profile == "my-cv":
        return LOCAL_SOURCE
    if not PROFILE_ID.fullmatch(profile) or ".." in profile:
        raise ValueError("A CV name may not start with a dot or contain \\ / : * ? \" < > |.")
    for item in scan_profiles():
        if item["id"] == profile:
            return item["path"]
    return PROFILES_DIR / f"{profile}.local.json"


def default_profile() -> str:
    """The CV file changed most recently, so a freshly dropped-in file opens by itself."""
    usable = [item for item in scan_profiles() if item["id"] != "sample" and not item.get("error")]
    if not usable:
        return "sample"
    return max(usable, key=lambda item: item["path"].stat().st_mtime)["id"]


def load_cv(profile: str | None = None) -> dict:
    profile = profile or default_profile()
    source = profile_path(profile)
    if not source.exists():
        raise ValueError("That saved CV does not exist any more. It may have been moved or deleted.")
    problem = file_problem(source)
    if problem:
        raise ValueError(f"{source.name}: {problem}")
    return json.loads(source.read_text(encoding="utf-8-sig"))


def save_cv(cv: dict, profile: str = "my-cv") -> str:
    """Atomically write the ignored local profile; the public sample stays untouched."""
    encoded = (json.dumps(cv, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if profile == "sample":
        profile = "my-cv"  # never overwrite the safe public example
    destination = profile_path(profile)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".cv-", delete=False) as temp:
        temp.write(encoded)
        temp_path = Path(temp.name)
    try:
        os.replace(temp_path, destination)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return profile


def delete_cv(profile: str) -> None:
    if profile == "sample":
        raise ValueError("The example CV cannot be deleted.")
    path = profile_path(profile)
    if not path.exists():
        raise ValueError("That CV file is already gone.")
    path.unlink()


def rename_cv(profile: str, name: str) -> str:
    if profile == "sample":
        raise ValueError("The example CV cannot be renamed. Make a copy of it first.")
    source = profile_path(profile)
    if not source.exists():
        raise ValueError("That CV file is already gone.")
    target_id = new_profile_id(name)
    if target_id in {"sample", "my-cv"} or target_id in {item["id"] for item in scan_profiles()} and target_id != profile:
        raise ValueError("Another CV already has that name.")
    if target_id == profile:
        return profile
    target = PROFILES_DIR / f"{target_id}.local.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)
    return target_id


def new_profile_id(name: str) -> str:
    requested = re.sub(r"\.(local\.)?json$", "", str(name).strip(), flags=re.I)
    profile = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", requested).strip(" .-")[:100]
    if not profile or not PROFILE_ID.fullmatch(profile):
        raise ValueError("Give the CV a short name, for example: Product engineer.")
    return profile


def open_folder(path: Path) -> None:
    import subprocess, sys
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def validate(cv: object) -> list[str]:
    if not isinstance(cv, dict):
        return ["The CV must be a collection of fields."]
    errors = []
    template = TEMPLATES.get(cv.get("template"))
    if not template:
        errors.append("Choose one of the available templates.")
    person = cv.get("person")
    if not isinstance(person, dict) or not str(person.get("name", "")).strip():
        errors.append("Add the person's name.")
    for key in ("contact", "sidebar_sections", "sections"):
        if not isinstance(cv.get(key), list):
            errors.append(f"{key.replace('_', ' ').capitalize()} must be a list.")
    for section in cv.get("sections", []):
        if not isinstance(section, dict) or not str(section.get("title", "")).strip():
            errors.append("Every main section needs a title.")
        elif not isinstance(section.get("entries", []), list):
            errors.append(f"{section['title']} needs a list of entries.")
    if template:
        supported = set(template.get("supported_section_types", []))
        unsupported = [s.get("type") for s in cv.get("sections", [])
                       if isinstance(s, dict) and s.get("type") not in supported]
        if unsupported:
            errors.append("This template does not support: " + ", ".join(map(str, unsupported)))
    return errors


def text(value: object) -> str:
    return html.escape(str(value or ""))


def shown(item: dict) -> bool:
    return item.get("visible", True) is not False


def render_entry(entry: dict, anchor: str = "", hoisted: bool = False) -> str:
    if not shown(entry):
        return ""
    title = text(entry.get("title"))
    organisation = text(entry.get("organisation"))
    dates, location = text(entry.get("dates")), text(entry.get("location"))
    meta = ""
    if dates or location:
        meta = f'<div class="entry-meta"><span>{dates}</span><span>{location}</span></div>'
    description = text(entry.get("description"))
    description = f'<p class="entry-description">{description}</p>' if description else ""
    bullets = "".join(f"<li>{text(item)}</li>" for item in entry.get("bullets", []) if str(item).strip())
    bullet_html = f"<ul>{bullets}</ul>" if bullets else ""
    organisation_html = f'<p class="organisation">{organisation}</p>' if organisation else ""
    breaker = " page-break" if entry.get("page_break_before") and not hoisted else ""
    return f'<article class="entry{breaker}" data-cv="{anchor}"><h3 class="entry-title">{title}</h3>{organisation_html}{meta}{description}{bullet_html}</article>'


def render_section(section: dict, i: int) -> str:
    entries = [(j, e) for j, e in enumerate(section.get("entries", [])) if isinstance(e, dict) and shown(e)]
    # A break on the first entry means "this section starts a page": hoist it so the heading is not orphaned.
    hoisted = bool(entries) and bool(entries[0][1].get("page_break_before"))
    breaker = " page-break" if section.get("page_break_before") or hoisted else ""
    body = "".join(render_entry(e, f"sections.{i}.entries.{j}", hoisted=(j == entries[0][0] and hoisted)) for j, e in entries)
    return f'<section class="main-section{breaker}" data-cv="sections.{i}"><h2>{text(section.get("title"))}</h2>{body}</section>'


def contact_value(item: dict) -> str:
    """Make e-mail addresses and web addresses clickable in the HTML and PDF."""
    value = str(item.get("value") or "").strip()
    label = str(item.get("label") or "").lower()
    if "@" in value and " " not in value:
        return f'<a href="mailto:{text(value)}">{text(value)}</a>'
    if re.match(r"^(https?://|www\.)", value, re.I) or re.match(r"^[\w.-]+\.[a-z]{2,}(/\S*)?$", value, re.I) and label not in {"phone", "location", "address"}:
        href = value if value.lower().startswith("http") else "https://" + value
        return f'<a href="{text(href)}">{text(value)}</a>'
    return text(value)


def render_parts(cv: dict) -> dict[str, str]:
    """Create content fragments shared by every presentation template."""
    person = cv["person"]
    contact = "".join(
        f'<div class="contact-item" data-cv="contact.{i}"><span class="contact-label">{text(item.get("label"))}</span><span class="contact-value{" contact-link" if str(item.get("label", "")).lower() in {"linkedin", "website", "portfolio"} else ""}">{contact_value(item)}</span></div>'
        for i, item in enumerate(cv["contact"]) if isinstance(item, dict) and shown(item) and item.get("value")
    )
    side = "".join(
        f'<section class="sidebar-section{" page-break" if section.get("page_break_before") else ""}" data-cv="sidebar_sections.{i}"><h2>{text(section.get("title"))}</h2><div class="tags">' +
        "".join(f'<span class="tag">{text(item)}</span>' for item in section.get("items", []) if str(item).strip()) +
        "</div></section>"
        for i, section in enumerate(cv["sidebar_sections"]) if isinstance(section, dict) and shown(section)
    )
    sections = "".join(render_section(section, i) for i, section in enumerate(cv["sections"]) if isinstance(section, dict) and shown(section))
    return {"name": text(person["name"]), "headline": text(person.get("headline")),
            "summary": text(person.get("summary")), "contact": contact, "sidebar": side,
            "sections": sections}


def render_classic(parts: dict[str, str]) -> str:
    return f'<article class="cv"><aside class="sidebar"><div class="contact">{parts["contact"]}</div>{parts["sidebar"]}</aside><main class="main"><h1 data-cv="person">{parts["name"]}</h1><p class="headline">{parts["headline"]}</p><p class="summary">{parts["summary"]}</p>{parts["sections"]}</main></article>'


def render_modern(parts: dict[str, str]) -> str:
    return f'<article class="cv modern"><header class="masthead" data-cv="person"><h1>{parts["name"]}</h1><div class="headline">{parts["headline"]}</div><div class="contact-line">{parts["contact"]}</div></header><main><p class="summary">{parts["summary"]}</p><div class="skills">{parts["sidebar"]}</div>{parts["sections"]}</main></article>'


RENDERERS = {"classic": render_classic, "modern": render_modern}


def preview_css(cv: dict) -> str:
    """Screen-only styling so the preview matches the printed page: margins become body padding."""
    m = TEMPLATES.get(cv.get("template"), {}).get("margins_mm", {})
    pad = f'{m.get("top", 0)}mm {m.get("right", 0)}mm {m.get("bottom", 0)}mm {m.get("left", 0)}mm'
    return PREVIEW_CSS + f"<style>body{{padding:{pad}!important}}@media print{{body{{padding:0!important}}}}</style>"


def render_html(cv: dict) -> str:
    errors = validate(cv)
    if errors:
        raise ValueError(" ".join(errors))
    template = TEMPLATES[cv["template"]]
    renderer = RENDERERS.get(template.get("renderer"))
    if not renderer:
        raise ValueError(f"Template {cv['template']!r} has no renderer.")
    css = template["css_path"].read_text(encoding="utf-8")
    parts = render_parts(cv)
    return f'<!doctype html><html><head><meta charset="utf-8"><title>{parts["name"]} — CV</title><meta name="author" content="{parts["name"]}"><style>{css}</style></head><body>{renderer(parts)}</body></html>'


PREVIEW_CSS = "<style>html{background:#fff!important}body{margin:0!important;box-shadow:none!important;width:auto!important;min-height:0!important}.page-break,.pushed{padding-top:var(--push,0)!important}[data-cv]{position:relative}.cv-focus::before,.cv-split::before{content:"";position:absolute;inset:calc(var(--push,0px) - 3px) -3px -3px -3px;border:2px solid #147084;border-radius:2px;pointer-events:none}.cv-split::before{border-style:dashed;border-color:#d6626a}.cv-handle{position:absolute;top:calc(var(--push,0px) - 2pt);right:0;display:none;border:0;border-radius:4px;padding:3px 7px;background:#147084;color:#fff;font:600 10px system-ui,sans-serif;cursor:pointer;z-index:2}.cv-handle.on{background:#9a3940}[data-cv]:hover>.cv-handle,.cv-split>.cv-handle{display:block}@media print{.page-break,.pushed{padding-top:0!important}.cv-focus::before,.cv-split::before{display:none}.cv-handle{display:none!important}}</style>"


STATIC_DIR = ROOT / "static"


def app_html() -> str:
    return (STATIC_DIR / "app.html").read_text(encoding="utf-8")



class Handler(BaseHTTPRequestHandler):
    def send(self, body: bytes, content_type: str, status: int = 200, filename: str | None = None):
        self.send_response(status); self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename: self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers(); self.wfile.write(body)

    def plain(self, message: str, status: int = 200):
        return self.send(message.encode(), "text/plain; charset=utf-8", status)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0")); return json.loads(self.rfile.read(length) or b"null")

    def template_choices(self):
        return [{"id": key, "label": value.get("label", key), "margins": value.get("margins_mm", {"top": 0, "right": 0, "bottom": 0, "left": 0})} for key, value in TEMPLATES.items()]

    def do_GET(self):
        parsed = urlparse(self.path); route = parsed.path
        if route == "/":
            profile = default_profile()
            initial_cv = load_cv(profile)
            initial = {"cv": initial_cv, "profiles": list_profiles(), "templates": self.template_choices(),
                       "preview": render_html(initial_cv) + preview_css(initial_cv),
                       "meta": {"profile": profile, "version": VERSION, "folder": str(PROFILES_DIR)}}
            page = app_html().replace("__INITIAL__", json.dumps(initial).replace("</", "<\\/"))
            return self.send(page.encode(), "text/html; charset=utf-8")
        if route.startswith("/static/"):
            name = route.removeprefix("/static/")
            target = STATIC_DIR / name
            if "/" in name or not target.is_file(): return self.plain("Not found", HTTPStatus.NOT_FOUND)
            kind = {"css": "text/css", "js": "text/javascript"}.get(target.suffix[1:], "application/octet-stream")
            self.send_response(200); self.send_header("Content-Type", kind + "; charset=utf-8"); self.send_header("Cache-Control", "no-cache")
            body = target.read_bytes(); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if route == "/api/cv":
            try:
                profile = parse_qs(parsed.query).get("profile", [None])[0]
                return self.send(json.dumps(load_cv(profile)).encode(), "application/json")
            except ValueError as exc:
                return self.plain(str(exc), HTTPStatus.NOT_FOUND)
        if route == "/api/profiles": return self.send(json.dumps(list_profiles()).encode(), "application/json")
        if route == "/api/templates": return self.send(json.dumps(self.template_choices()).encode(), "application/json")
        self.plain("Not found", HTTPStatus.NOT_FOUND)

    def do_POST(self):
        route = urlparse(self.path).path
        if route == "/api/open-folder":
            try:
                open_folder(PROFILES_DIR); return self.plain(str(PROFILES_DIR))
            except OSError as exc:
                return self.plain(f"The folder is {PROFILES_DIR} but it could not be opened automatically: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
        try: cv = self.read_json()
        except json.JSONDecodeError as exc: return self.plain(f"This is not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}.", HTTPStatus.BAD_REQUEST)
        if route == "/api/rename":
            try:
                renamed = rename_cv(str(cv.get("profile", "")), str(cv.get("name", "")))
                return self.send(json.dumps({"profile": renamed}).encode(), "application/json")
            except (AttributeError, ValueError, OSError) as exc:
                return self.plain(str(exc), HTTPStatus.BAD_REQUEST)
        if route == "/api/profiles":
            try:
                profile = new_profile_id(cv.get("name", ""))
                errors = validate(cv.get("cv"))
                if errors: raise ValueError(" ".join(errors))
                if profile in {item["id"] for item in scan_profiles()}:
                    base, n = profile, 2
                    while profile in {item["id"] for item in scan_profiles()}: profile = f"{base} {n}"; n += 1
                saved = save_cv(cv["cv"], profile)
                return self.send(json.dumps({"profile": saved}).encode(), "application/json")
            except (KeyError, TypeError, AttributeError, ValueError) as exc:
                return self.plain(str(exc), HTTPStatus.BAD_REQUEST)
        try: document = render_html(cv)
        except ValueError as exc: return self.plain(str(exc), HTTPStatus.BAD_REQUEST)
        if route == "/api/preview": return self.send((document + preview_css(cv)).encode(), "text/html; charset=utf-8")
        if route == "/api/html": return self.send(document.encode(), "text/html; charset=utf-8", filename="CV.html")
        if route == "/api/pdf":
            try:
                from weasyprint import HTML
            except ImportError:
                return self.plain("Direct PDF download is optional and the PDF helper is not installed. Use Print / Save as PDF instead: it opens the normal print window, where you choose Save as PDF.", HTTPStatus.SERVICE_UNAVAILABLE)
            return self.send(HTML(string=document, base_url=str(ROOT)).write_pdf(), "application/pdf", filename="CV.pdf")
        self.plain("Not found", HTTPStatus.NOT_FOUND)

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/cv": return self.plain("Not found", HTTPStatus.NOT_FOUND)
        try: cv = self.read_json(); errors = validate(cv)
        except json.JSONDecodeError: errors = ["The submitted CV is not valid data."]
        if errors: return self.send(json.dumps({"errors": errors}).encode(), "application/json", HTTPStatus.BAD_REQUEST)
        try:
            profile = parse_qs(parsed.query).get("profile", ["my-cv"])[0]
            saved = save_cv(cv, profile)
        except ValueError as exc:
            return self.send(json.dumps({"errors": [str(exc)]}).encode(), "application/json", HTTPStatus.BAD_REQUEST)
        self.send(json.dumps({"ok": True, "profile": saved}).encode(), "application/json")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/cv": return self.plain("Not found", HTTPStatus.NOT_FOUND)
        try:
            delete_cv(parse_qs(parsed.query).get("profile", [""])[0]); return self.plain("Deleted")
        except (ValueError, OSError) as exc:
            return self.plain(str(exc), HTTPStatus.BAD_REQUEST)

    def log_message(self, *_): pass


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--render", action="store_true", help="write content/cv.html and exit")
    parser.add_argument("--port", type=int, default=8765, help="local web port (default: 8765)")
    args = parser.parse_args()
    if args.render:
        (ROOT / "content" / "cv.html").write_text(render_html(load_cv()), encoding="utf-8"); print(ROOT / "content" / "cv.html"); return
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"CV Studio {VERSION}: http://127.0.0.1:{args.port} (local only). CV files live in {PROFILES_DIR}")
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")

if __name__ == "__main__": main()
