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
PERSONS_MODE = os.environ.get("CV_STUDIO_PERSONS", "") not in ("", "0", "false")  # hosted: one folder per person under persons/
PERSON_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,39}$")
# Requests that arrive through a public route carry this header (set by the gateway, never by clients):
# they may only use the agent API, with a bearer token; cookies and the editor are refused.
PUBLIC_HEADER = os.environ.get("CV_STUDIO_PUBLIC_HEADER", "X-CV-Studio-Public")
# Method-aware: a public agent may read everything, create/replace CVs, but never delete (C2 in the
# 2026-08-30 pre-cutover review) — deletion stays a decision for a person in the editor.
PUBLIC_ALLOW = {("GET", "/api/openapi.json"), ("GET", "/api/schema"),
                ("GET", "/api/profiles"), ("POST", "/api/profiles"),
                ("GET", "/api/cv"), ("PUT", "/api/cv")}
import contextvars
CONTENT: contextvars.ContextVar[Path] = contextvars.ContextVar("content", default=CONTENT_DIR)


def local_source() -> Path:
    return CONTENT.get() / "cv.local.json"


def profiles_dir() -> Path:
    return CONTENT.get() / "profiles"
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
    if local_source().exists():
        candidates.append(local_source())
    for folder in (local_source().parent, profiles_dir()):
        if folder.is_dir():
            candidates += sorted(p for p in folder.glob("*.json") if p not in (SAMPLE_SOURCE, local_source()) and not p.name.startswith("."))
    seen = {"sample"}
    for path in candidates:
        if path == local_source():
            item = {"id": "my-cv", "label": "My CV", "path": path}
        else:
            profile_id = path.name.removesuffix(".json").removesuffix(".local")
            item = {"id": profile_id, "label": profile_label(profile_id), "path": path}
            if not PROFILE_ID.fullmatch(profile_id) or ".." in profile_id:
                item["error"] = "Rename this file: names may not start with a dot or contain \\ / : * ? \" < > |."
            elif profile_id in seen:
                item["error"] = "Another CV file already has this name. Rename one of them."
        base = ROOT if path.is_relative_to(ROOT) else CONTENT.get()
        item["file"] = str(path.relative_to(base)) if path.is_relative_to(base) else path.name
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
        return local_source()
    if not PROFILE_ID.fullmatch(profile) or ".." in profile:
        raise ValueError("A CV name may not start with a dot or contain \\ / : * ? \" < > |.")
    for item in scan_profiles():
        if item["id"] == profile:
            return item["path"]
    return profiles_dir() / f"{profile}.local.json"


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
    target = profiles_dir() / f"{target_id}.local.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)
    return target_id


def new_profile_id(name: str) -> str:
    requested = re.sub(r"\.(local\.)?json$", "", str(name).strip(), flags=re.I)
    profile = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", requested).strip(" .-")[:100]
    if not profile or not PROFILE_ID.fullmatch(profile):
        raise ValueError("Give the CV a short name, for example: Product engineer.")
    return profile


def find_browser() -> str | None:
    """A Chromium-based browser that can print to PDF without page headers (Edge ships with Windows)."""
    import shutil, sys
    if os.environ.get("CV_STUDIO_BROWSER"):
        return os.environ["CV_STUDIO_BROWSER"]
    candidates = []
    if sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LocalAppData")):
            if base:
                candidates += [Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe", Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"]
    elif sys.platform == "darwin":
        candidates += [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"), Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")]
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "microsoft-edge", "msedge", "chrome"):
        if shutil.which(name):
            return shutil.which(name)
    return next((str(p) for p in candidates if p.is_file()), None)


def pdf_bytes(document: str) -> bytes:
    """WeasyPrint when installed, otherwise a headless Chromium/Edge print with no header or footer."""
    try:
        from weasyprint import HTML
        return HTML(string=document, base_url=str(ROOT)).write_pdf()
    except ImportError:
        pass
    browser = find_browser()
    if not browser:
        raise RuntimeError("No PDF helper and no Chrome or Edge found. Use the print window instead.")
    import shutil, subprocess
    directory = Path(tempfile.mkdtemp(prefix="cv-pdf-"))
    try:
        source, target = directory / "cv.html", directory / "cv.pdf"
        source.write_text(document, encoding="utf-8")
        flags = ["--disable-gpu", "--no-sandbox", "--no-first-run", "--disable-background-networking", "--disable-component-update",
                 "--disable-sync", "--no-pdf-header-footer", "--timeout=20000", f"--print-to-pdf={target}", source.as_uri()]
        problems = []
        for mode in ("--headless=new", "--headless=old"):  # new is what current Edge/Chrome ship; old for builds where new hangs
            try:
                result = subprocess.run([browser, mode, f"--user-data-dir={directory / 'profile'}", *flags], capture_output=True, timeout=30)
                problems.append(result.stderr.decode(errors="replace")[-200:].strip())
            except subprocess.TimeoutExpired:
                problems.append(f"{mode} did not finish in time")
            if target.is_file() and target.stat().st_size:
                return target.read_bytes()
        raise RuntimeError(f"{Path(browser).name} could not make the PDF. Use the print window instead. ({' / '.join(p for p in problems if p)})")
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def persons_dir() -> Path:
    return CONTENT_DIR / "persons"


def list_persons() -> list[str]:
    if not persons_dir().is_dir():
        return []
    return sorted(p.name for p in persons_dir().iterdir() if p.is_dir() and PERSON_ID.fullmatch(p.name))


def person_folder(person: str) -> Path:
    if not PERSON_ID.fullmatch(person) or ".." in person:
        raise ValueError("A person's name may only use letters, numbers, spaces, dots, dashes or underscores.")
    return persons_dir() / person


def token_person(token: str) -> str | None:
    """Agents (ChatGPT, Claude) identify with a bearer token listed in <data>/tokens.json as {"token": "person"}."""
    path = CONTENT_DIR / "tokens.json"
    if not token or not path.is_file():
        return None
    try:
        person = json.loads(path.read_text(encoding="utf-8")).get(token)
    except (OSError, ValueError):
        return None
    return person if isinstance(person, str) and person in list_persons() else None


OIDC_USERINFO = os.environ.get("CV_STUDIO_OIDC_USERINFO", "")  # e.g. https://auth.example/application/o/userinfo/
# When set, a token must also pass token introspection for THIS client (audience check): any other
# application's Authentik token is refused (C1 in the 2026-08-30 pre-cutover review).
OIDC_INTROSPECT = os.environ.get("CV_STUDIO_OIDC_INTROSPECT", "")
OIDC_CLIENT_ID = os.environ.get("CV_STUDIO_OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("CV_STUDIO_OIDC_CLIENT_SECRET", "")


def introspect_ok(token: str) -> bool:
    """True when the identity provider says this token is active and was issued to our client."""
    import base64, urllib.parse, urllib.request, urllib.error
    body = urllib.parse.urlencode({"token": token}).encode()
    basic = base64.b64encode(f"{OIDC_CLIENT_ID}:{OIDC_CLIENT_SECRET}".encode()).decode()
    request = urllib.request.Request(OIDC_INTROSPECT, data=body, headers={
        "Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError):
        return False
    return bool(data.get("active")) and data.get("client_id") in (OIDC_CLIENT_ID, None) and (
        data.get("client_id") is not None or OIDC_CLIENT_ID == "")
_userinfo_cache: dict[str, tuple[float, str | None]] = {}


def fetch_userinfo(token: str) -> dict | None:
    """Ask the identity provider who a bearer token belongs to (None when it is not valid)."""
    import urllib.request, urllib.error
    request = urllib.request.Request(OIDC_USERINFO, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError):
        return None


def oidc_person(token: str, lookup=None, check=None) -> str | None:
    """Map an OAuth access token to a person folder via the provider's userinfo; creates the folder on first use."""
    import time
    if not OIDC_USERINFO or not token:
        return None
    cached = _userinfo_cache.get(token)
    if cached and cached[0] > time.time():
        return cached[1]
    person = None
    if OIDC_INTROSPECT and not (check or introspect_ok)(token):
        info = None
    else:
        info = (lookup or fetch_userinfo)(token)
    if isinstance(info, dict):
        name = str(info.get("preferred_username") or info.get("nickname") or str(info.get("email", "")).split("@")[0] or "").strip()
        if name and PERSON_ID.fullmatch(name) and ".." not in name:
            person_folder(name).joinpath("profiles").mkdir(parents=True, exist_ok=True)
            person = name
    _userinfo_cache[token] = (time.time() + (300 if person else 30), person)
    if len(_userinfo_cache) > 500:
        _userinfo_cache.clear()
    return person


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


def openapi(base_url: str) -> dict:
    cv_schema = {"type": "object", "description": "A CV document. Use GET /api/schema for a complete example; keep every field name.",
                 "required": ["template", "person", "contact", "sidebar_sections", "sections"]}
    profile_param = {"name": "profile", "in": "query", "required": True, "schema": {"type": "string"},
                     "description": "CV id from GET /api/profiles (for example 'my-cv' or 'Product engineer')."}
    return {
        "openapi": "3.1.0",
        "info": {"title": "CV Studio", "version": VERSION,
                 "description": "Read and update a person's CVs. Every CV is a JSON document rendered by CV Studio into a PDF; the person reviews it in the editor."},
        "servers": [{"url": base_url}],
        "components": {"securitySchemes": {"bearer": {"type": "http", "scheme": "bearer",
                       "description": "An OAuth access token from the household identity provider, or a token from tokens.json."}},
                       "schemas": {"CV": cv_schema}},
        "security": [{"bearer": []}],
        "paths": {
            "/api/schema": {"get": {"operationId": "getExampleCV", "summary": "Complete example CV showing the JSON structure and available templates",
                                     "responses": {"200": {"description": "Example", "content": {"application/json": {"schema": cv_schema}}}}}},
            "/api/profiles": {"get": {"operationId": "listCVs", "summary": "List the person's CVs", "responses": {"200": {"description": "Ids, labels and any file problems"}}},
                              "post": {"operationId": "createCV", "summary": "Create a new CV under a name",
                                       "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["name", "cv"],
                                                       "properties": {"name": {"type": "string"}, "cv": cv_schema}}}}},
                                       "responses": {"200": {"description": "The id of the new CV"}, "400": {"description": "What is wrong with the CV"}}}},
            "/api/cv": {"get": {"operationId": "getCV", "summary": "Read one CV", "parameters": [profile_param], "responses": {"200": {"description": "The CV"}, "404": {"description": "No such CV"}}},
                        "put": {"operationId": "updateCV", "summary": "Replace one CV (send the complete document)", "parameters": [profile_param],
                                "requestBody": {"required": True, "content": {"application/json": {"schema": cv_schema}}},
                                "responses": {"200": {"description": "Saved"}, "400": {"description": "Validation errors, as a list"}}}},
        },
    }


def app_html() -> str:
    return (STATIC_DIR / "app.html").read_text(encoding="utf-8")



class Handler(BaseHTTPRequestHandler):
    person: str | None = None
    extra_headers: list[tuple[str, str]]

    def send(self, body: bytes, content_type: str, status: int = 200, filename: str | None = None):
        self.send_response(status); self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename: self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer"); self.send_header("Cache-Control", "no-store")
        for name, value in getattr(self, "extra_headers", []): self.send_header(name, value)
        self.end_headers(); self.wfile.write(body)
        self.audit(status)

    server_version = "CVStudio"  # no Python/BaseHTTP version leak
    sys_version = ""

    def is_public(self) -> bool:
        return self.headers.get(PUBLIC_HEADER, "").strip() == "1"

    def public_guard(self, route: str) -> bool:
        """On a public request only the allow-listed method+path pairs are served; anything else is not found."""
        if self.is_public() and (self.command, route) not in PUBLIC_ALLOW:
            self.extra_headers = []; self.plain("Not found", HTTPStatus.NOT_FOUND); return True
        return False

    def log_message(self, *_):  # quiet for local use; public requests are logged in send()
        pass

    def audit(self, status: int):
        if self.is_public():
            source = self.headers.get("Cf-Connecting-Ip") or self.client_address[0]
            print(f"public {source} person={self.person or '-'} {self.command} {self.path} -> {status}", flush=True)

    def cookie(self, name: str) -> str | None:
        from http.cookies import SimpleCookie
        jar = SimpleCookie(self.headers.get("Cookie", ""))
        return jar[name].value if name in jar else None

    def set_person_cookie(self, person: str | None):
        value = f"cv_person={person}; Path=/; Max-Age=31536000; SameSite=Lax" if person else "cv_person=; Path=/; Max-Age=0"
        self.extra_headers = getattr(self, "extra_headers", []) + [("Set-Cookie", value)]

    def resolve_person(self) -> bool:
        """In persons mode, pick the folder for this request from a bearer token or the cookie. False = nobody chosen yet."""
        self.extra_headers = []
        self.person = None
        CONTENT.set(CONTENT_DIR)
        if not PERSONS_MODE:
            return not self.is_public()  # a public route only makes sense with per-person folders
        auth = self.headers.get("Authorization", "")
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        person = (token_person(bearer) or oidc_person(bearer)) if bearer else None
        if not person and not self.is_public():
            candidate = self.cookie("cv_person")
            person = candidate if candidate and candidate in list_persons() else None
        if not person:
            return False
        self.person = person
        CONTENT.set(person_folder(person))
        return True

    def chooser_page(self) -> bytes:
        options = "".join(f'<button onclick="pick({json.dumps(p)})">{html.escape(p)}</button>' for p in list_persons())
        return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>CV Studio — who is editing?</title><link rel="stylesheet" href="/static/app.css"><style>.who{{max-width:520px;margin:8vh auto;padding:0 20px}}.who button{{display:block;width:100%;margin:8px 0;padding:14px;font-size:16px}}.who input{{padding:12px;font-size:16px}}</style></head><body><div class="who"><h1>Whose CV?</h1><p class="hint">Each person has their own folder of CVs on this server. Pick yourself; this browser remembers the choice.</p>{options}<h2>Someone new</h2><input id="name" placeholder="First name"><button class="secondary" onclick="pick(document.querySelector('#name').value, true)">Start</button><div id="problem" class="problem"></div></div><script>
async function pick(name, create) {{ const r = await fetch(create ? '/api/persons' : '/api/person', {{method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{name}})}}); if (r.ok) location.href = '/'; else {{ const p = document.querySelector('#problem'); p.textContent = await r.text(); p.classList.add('show'); }} }}
</script></body></html>""".encode()

    def plain(self, message: str, status: int = 200):
        return self.send(message.encode(), "text/plain; charset=utf-8", status)

    MAX_BODY = 2 * 1024 * 1024  # a CV is tens of kilobytes; anything near this is not a CV

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > self.MAX_BODY:
            raise ValueError("The request is too large to be a CV.")
        return json.loads(self.rfile.read(length) or b"null")

    def template_choices(self):
        return [{"id": key, "label": value.get("label", key), "margins": value.get("margins_mm", {"top": 0, "right": 0, "bottom": 0, "left": 0})} for key, value in TEMPLATES.items()]

    def do_GET(self):
        parsed = urlparse(self.path); route = parsed.path
        if self.public_guard(route): return
        if route in ("/health", "/ready"): self.extra_headers = []; return self.plain("ok")
        if route.startswith("/static/"): return self.static(route)
        if route == "/api/openapi.json":
            self.extra_headers = []
            host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host", "127.0.0.1")
            scheme = self.headers.get("X-Forwarded-Proto", "http")
            return self.send(json.dumps(openapi(f"{scheme}://{host}"), indent=2).encode(), "application/json")
        if route == "/api/schema": self.extra_headers = []; return self.send(SAMPLE_SOURCE.read_bytes(), "application/json")
        if not self.resolve_person():
            if route == "/": return self.send(self.chooser_page(), "text/html; charset=utf-8")
            return self.plain("Sign in first: send an OAuth bearer token, or open the site in a browser and choose a person.", HTTPStatus.UNAUTHORIZED)
        if route == "/":
            profile = default_profile()
            initial_cv = load_cv(profile)
            initial = {"cv": initial_cv, "profiles": list_profiles(), "templates": self.template_choices(),
                       "preview": render_html(initial_cv) + preview_css(initial_cv),
                       "meta": {"profile": profile, "version": VERSION, "folder": str(profiles_dir()), "person": self.person, "hosted": PERSONS_MODE}}
            page = app_html().replace("__INITIAL__", json.dumps(initial).replace("</", "<\\/"))
            return self.send(page.encode(), "text/html; charset=utf-8")
        self.api_get(parsed, route)

    def static(self, route: str):
            self.extra_headers = []
            name = route.removeprefix("/static/")
            target = STATIC_DIR / name
            if "/" in name or not target.is_file(): return self.plain("Not found", HTTPStatus.NOT_FOUND)
            kind = {"css": "text/css", "js": "text/javascript"}.get(target.suffix[1:], "application/octet-stream")
            self.send_response(200); self.send_header("Content-Type", kind + "; charset=utf-8"); self.send_header("Cache-Control", "no-cache")
            body = target.read_bytes(); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return

    def api_get(self, parsed, route):
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
        if self.public_guard(route): return
        if route in ("/api/person", "/api/persons"):
            self.extra_headers = []
            try:
                name = str(self.read_json().get("name", "")).strip()
                if route == "/api/persons":
                    person_folder(name).joinpath("profiles").mkdir(parents=True, exist_ok=True)
                elif name not in list_persons():
                    raise ValueError("No such person.")
                self.set_person_cookie(name)
                return self.send(json.dumps({"person": name}).encode(), "application/json")
            except (AttributeError, ValueError, OSError, json.JSONDecodeError) as exc:
                return self.plain(str(exc) or "Give a name.", HTTPStatus.BAD_REQUEST)
        if route == "/api/leave":
            self.extra_headers = []; self.set_person_cookie(None); return self.plain("ok")
        if not self.resolve_person(): return self.plain("Sign in first: send an OAuth bearer token, or open the site in a browser and choose a person.", HTTPStatus.UNAUTHORIZED)
        if route == "/api/open-folder":
            if PERSONS_MODE: return self.plain(f"On the server the files are in {profiles_dir()}; download a backup instead.", HTTPStatus.BAD_REQUEST)
            try:
                open_folder(profiles_dir()); return self.plain(str(profiles_dir()))
            except OSError as exc:
                return self.plain(f"The folder is {profiles_dir()} but it could not be opened automatically: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)
        try: cv = self.read_json()
        except json.JSONDecodeError as exc: return self.plain(f"This is not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}.", HTTPStatus.BAD_REQUEST)
        except ValueError as exc: return self.plain(str(exc), HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
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
                return self.send(pdf_bytes(document), "application/pdf", filename="CV.pdf")
            except Exception as exc:  # noqa: BLE001 - any failure falls back to the browser's print window
                return self.plain(str(exc), HTTPStatus.SERVICE_UNAVAILABLE)
        self.plain("Not found", HTTPStatus.NOT_FOUND)

    def do_PUT(self):
        parsed = urlparse(self.path)
        if self.public_guard(parsed.path): return
        if not self.resolve_person(): return self.plain("Sign in first: send an OAuth bearer token, or open the site in a browser and choose a person.", HTTPStatus.UNAUTHORIZED)
        if parsed.path != "/api/cv": return self.plain("Not found", HTTPStatus.NOT_FOUND)
        try: cv = self.read_json(); errors = validate(cv)
        except (json.JSONDecodeError, ValueError): errors = ["The submitted CV is not valid data."]
        if errors: return self.send(json.dumps({"errors": errors}).encode(), "application/json", HTTPStatus.BAD_REQUEST)
        try:
            profile = parse_qs(parsed.query).get("profile", ["my-cv"])[0]
            saved = save_cv(cv, profile)
        except ValueError as exc:
            return self.send(json.dumps({"errors": [str(exc)]}).encode(), "application/json", HTTPStatus.BAD_REQUEST)
        self.send(json.dumps({"ok": True, "profile": saved}).encode(), "application/json")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if self.public_guard(parsed.path): return
        if not self.resolve_person(): return self.plain("Sign in first: send an OAuth bearer token, or open the site in a browser and choose a person.", HTTPStatus.UNAUTHORIZED)
        if parsed.path != "/api/cv": return self.plain("Not found", HTTPStatus.NOT_FOUND)
        try:
            delete_cv(parse_qs(parsed.query).get("profile", [""])[0]); return self.plain("Deleted")
        except (ValueError, OSError) as exc:
            return self.plain(str(exc), HTTPStatus.BAD_REQUEST)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--render", action="store_true", help="write content/cv.html and exit")
    parser.add_argument("--port", type=int, default=8765, help="local web port (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on (default: loopback only; 0.0.0.0 inside a container)")
    args = parser.parse_args()
    if args.render:
        (ROOT / "content" / "cv.html").write_text(render_html(load_cv()), encoding="utf-8"); print(ROOT / "content" / "cv.html"); return
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    where = "local only" if args.host == "127.0.0.1" else f"listening on {args.host}"
    print(f"CV Studio {VERSION}: http://127.0.0.1:{args.port} ({where}). CV files live in {CONTENT_DIR}" + (" per person" if PERSONS_MODE else ""))
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")

if __name__ == "__main__": main()
