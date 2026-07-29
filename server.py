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
LOCAL_SOURCE = ROOT / "content" / "cv.local.json"
PROFILES_DIR = ROOT / "content" / "profiles"
PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}$")
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


def profile_path(profile: str) -> Path:
    if profile == "sample":
        return SAMPLE_SOURCE
    if profile == "my-cv":
        return LOCAL_SOURCE
    if not PROFILE_ID.fullmatch(profile):
        raise ValueError("That CV profile name is not valid.")
    return PROFILES_DIR / f"{profile}.local.json"


def list_profiles() -> list[dict[str, str]]:
    profiles = [{"id": "sample", "label": "Example CV"}]
    if LOCAL_SOURCE.exists():
        profiles.append({"id": "my-cv", "label": "My CV"})
    if PROFILES_DIR.exists():
        for path in sorted(PROFILES_DIR.glob("*.local.json")):
            profile_id = path.name.removesuffix(".local.json")
            profiles.append({"id": profile_id, "label": profile_id.replace("-", " ").title()})
    return profiles


def load_cv(profile: str | None = None) -> dict:
    profile = profile or ("my-cv" if LOCAL_SOURCE.exists() else "sample")
    source = profile_path(profile)
    if not source.exists():
        raise ValueError("That saved CV profile does not exist yet.")
    return json.loads(source.read_text(encoding="utf-8"))


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


def render_entry(entry: dict) -> str:
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
    return f'<article class="entry"><h3 class="entry-title">{title}</h3>{organisation_html}{meta}{description}{bullet_html}</article>'


def render_parts(cv: dict) -> dict[str, str]:
    """Create content fragments shared by every presentation template."""
    person = cv["person"]
    contact = "".join(
        f'<div class="contact-item"><span class="contact-label">{text(item.get("label"))}</span><span class="contact-value{" contact-link" if str(item.get("label", "")).lower() in {"linkedin", "website", "portfolio"} else ""}">{text(item.get("value"))}</span></div>'
        for item in cv["contact"] if isinstance(item, dict) and shown(item) and item.get("value")
    )
    side = "".join(
        f'<section class="sidebar-section"><h2>{text(section.get("title"))}</h2><div class="tags">' +
        "".join(f'<span class="tag">{text(item)}</span>' for item in section.get("items", []) if str(item).strip()) +
        "</div></section>"
        for section in cv["sidebar_sections"] if isinstance(section, dict) and shown(section)
    )
    sections = "".join(
        f'<section class="main-section{" page-break" if section.get("page_break_before") else ""}"><h2>{text(section.get("title"))}</h2>' +
        "".join(render_entry(entry) for entry in section.get("entries", []) if isinstance(entry, dict)) +
        "</section>"
        for section in cv["sections"] if isinstance(section, dict) and shown(section)
    )
    return {"name": text(person["name"]), "headline": text(person.get("headline")),
            "summary": text(person.get("summary")), "contact": contact, "sidebar": side,
            "sections": sections}


def render_classic(parts: dict[str, str]) -> str:
    return f'<article class="cv"><aside class="sidebar"><div class="contact">{parts["contact"]}</div>{parts["sidebar"]}</aside><main class="main"><h1>{parts["name"]}</h1><p class="headline">{parts["headline"]}</p><p class="summary">{parts["summary"]}</p>{parts["sections"]}</main></article>'


def render_modern(parts: dict[str, str]) -> str:
    return f'<article class="cv modern"><header class="masthead"><h1>{parts["name"]}</h1><div class="headline">{parts["headline"]}</div><div class="contact-line">{parts["contact"]}</div></header><main><p class="summary">{parts["summary"]}</p>{parts["sections"]}</main></article>'


RENDERERS = {"classic": render_classic, "modern": render_modern}


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
    return f'<!doctype html><html><head><meta charset="utf-8"><title>{parts["name"]} — CV</title><style>{css}</style></head><body>{renderer(parts)}</body></html>'


APP_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>CV editor</title><style>
*{box-sizing:border-box} body{margin:0;font:14px system-ui,sans-serif;color:#263944;background:#f2f5f6}.app{display:grid;grid-template-columns:minmax(330px,43%) 1fr;min-height:100vh}.editor{padding:22px;overflow:auto}.preview{padding:18px;background:#dce3e6;overflow:auto}h1{margin:0 0 6px;font-size:24px}h2{margin:24px 0 8px;font-size:17px}.hint{color:#62737d;margin:0 0 18px}label{display:block;margin:10px 0 4px;font-weight:650}input,textarea,select{width:100%;border:1px solid #b9cbd2;border-radius:5px;padding:8px;font:inherit;background:white}textarea{min-height:70px;resize:vertical}.card{margin:10px 0;padding:12px;border:1px solid #cbd7dc;border-radius:7px;background:#fff}.row{display:grid;grid-template-columns:1fr 1fr;gap:9px}.actions{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}button{border:0;border-radius:5px;padding:9px 12px;background:#147084;color:white;font:inherit;font-weight:650;cursor:pointer}button.secondary{background:#60747e}button.remove{background:#9a3940;padding:5px 8px;float:right}.toggle{display:flex;align-items:center;gap:6px;font-weight:500}.toggle input{width:auto}.status{min-height:20px;color:#176238}iframe{width:210mm;height:297mm;border:0;background:white;box-shadow:0 2px 12px #89969b}@media(max-width:1000px){.app{grid-template-columns:1fr}.preview{padding:10px}.editor{max-height:none}iframe{transform-origin:top left;transform:scale(.72);margin-bottom:-83mm}}@media print{.editor{display:none}.app{display:block}.preview{padding:0;background:white}iframe{width:100%;height:100vh;box-shadow:none}}</style></head><body><div class="app"><main class="editor"><h1>CV editor</h1><p class="hint">Edit plain fields and cards. Your preview updates as you type; save keeps the changes on this computer.</p><div id="form"></div><div class="actions"><button onclick="save()">Save changes</button><button class="secondary" onclick="newProfile()">New profile</button><button class="secondary" onclick="downloadFile('html')">Download HTML</button><button class="secondary" onclick="downloadFile('pdf')">Download PDF</button></div><div id="status" class="status"></div></main><aside class="preview"><iframe id="preview" title="CV preview"></iframe></aside></div><script>
let cv, templates=[], profiles=[], profile; const form=document.querySelector('#form'), preview=document.querySelector('#preview'), status=document.querySelector('#status');
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function field(label,value,path,area=false){return `<label>${label}</label>${area?`<textarea data-path="${path}">${esc(value)}</textarea>`:`<input data-path="${path}" value="${esc(value)}">`}`}
function visible(item,path){return `<label class="toggle"><input type="checkbox" data-path="${path}.visible" ${item.visible===false?'':'checked'}> Show this</label>`}
function entry(e,path){return `<div class="card"><button class="remove" data-remove="${path}">Remove</button>${visible(e,path)}${field('Title',e.title,path+'.title')}${field('Organisation / school',e.organisation,path+'.organisation')}<div class="row"><div>${field('Dates',e.dates,path+'.dates')}</div><div>${field('Location',e.location,path+'.location')}</div></div>${field('Description',e.description,path+'.description',true)}<label>Achievement bullets (one per line)</label><textarea data-bullets="${path}">${esc((e.bullets||[]).join('\n'))}</textarea></div>`}
function render(){let options=templates.map(t=>`<option value="${t.id}" ${t.id===cv.template?'selected':''}>${t.label}</option>`).join(''),profileOptions=profiles.map(p=>`<option value="${p.id}" ${p.id===profile?'selected':''}>${p.label}</option>`).join('');form.innerHTML=`<h2>CV profile</h2><label>Loaded CV</label><select data-profile>${profileOptions}</select><p class="hint">Choose a saved CV, or use New profile to make a separate copy.</p><h2>Document style</h2><label>Template</label><select data-template>${options}</select><p class="hint">The style changes presentation only; your content stays the same.</p><h2>About you</h2>${field('Full name',cv.person.name,'person.name')}${field('Headline',cv.person.headline,'person.headline')}${field('Short introduction',cv.person.summary,'person.summary',true)}<h2>Contact details</h2>${cv.contact.map((x,i)=>`<div class="card">${visible(x,'contact.'+i)}${field('Label',x.label,'contact.'+i+'.label')}${field('Value',x.value,'contact.'+i+'.value')}</div>`).join('')}<h2>Sidebar</h2>${cv.sidebar_sections.map((x,i)=>`<div class="card">${visible(x,'sidebar_sections.'+i)}${field('Heading',x.title,'sidebar_sections.'+i+'.title')}<label>Items (one per line)</label><textarea data-items="sidebar_sections.${i}">${esc((x.items||[]).join('\n'))}</textarea></div>`).join('')}<h2>Main CV sections</h2><p class="hint">Move whole sections to set their order. A page break starts that section on a fresh A4 page.</p>${cv.sections.map((s,i)=>`<section class="card"><div class="actions"><button class="secondary" data-section-move="${i},-1" ${i===0?'disabled':''}>Move up</button><button class="secondary" data-section-move="${i},1" ${i===cv.sections.length-1?'disabled':''}>Move down</button></div>${visible(s,'sections.'+i)}<label class="toggle"><input type="checkbox" data-path="sections.${i}.page_break_before" ${s.page_break_before?'checked':''}> Start this section on a new page</label>${field('Section heading',s.title,'sections.'+i+'.title')}<p class="hint">${s.type}</p>${s.entries.map((e,j)=>entry(e,`sections.${i}.entries.${j}`)).join('')}<button class="secondary" data-add="${i}">Add ${s.type} entry</button></section>`).join('')}`; bind(); updatePreview()}
function get(path){return path.split('.').reduce((o,k)=>o[k],cv)} function set(path,value){let p=path.split('.'),key=p.pop(),o=p.reduce((x,k)=>x[k],cv);o[key]=value}
function bind(){form.querySelectorAll('[data-path]').forEach(el=>el.oninput=()=>{set(el.dataset.path,el.type==='checkbox'?el.checked:el.value);updatePreview()});form.querySelector('[data-template]').onchange=e=>{cv.template=e.target.value;updatePreview()};form.querySelector('[data-profile]').onchange=e=>loadProfile(e.target.value);form.querySelectorAll('[data-bullets]').forEach(el=>el.oninput=()=>{get(el.dataset.bullets).bullets=el.value.split('\n').filter(Boolean);updatePreview()});form.querySelectorAll('[data-items]').forEach(el=>el.oninput=()=>{get(el.dataset.items).items=el.value.split('\n').filter(Boolean);updatePreview()});form.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{let p=b.dataset.remove.split('.'),idx=+p.pop(),a=get(p.join('.'));a.splice(idx,1);render()});form.querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>{let s=cv.sections[+b.dataset.add];s.entries.push({title:'New entry',organisation:'',dates:'',location:'',description:'',bullets:[],visible:true});render()});form.querySelectorAll('[data-section-move]').forEach(b=>b.onclick=()=>{let [i,d]=b.dataset.sectionMove.split(',').map(Number),to=i+d;if(to<0||to>=cv.sections.length)return;[cv.sections[i],cv.sections[to]]=[cv.sections[to],cv.sections[i]];render()})}
let timer; function updatePreview(){clearTimeout(timer);timer=setTimeout(async()=>{let r=await fetch('/api/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cv)});preview.srcdoc=await r.text()},120)}
async function reloadProfiles(){profiles=await fetch('/api/profiles').then(r=>r.json())} async function loadProfile(id){let r=await fetch('/api/cv?profile='+encodeURIComponent(id));if(!r.ok){status.textContent=await r.text();return}cv=await r.json();profile=id;render()}
async function save(){let r=await fetch('/api/cv?profile='+encodeURIComponent(profile),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(cv)}),d=await r.json();if(r.ok){profile=d.profile;await reloadProfiles();render();status.textContent='Saved locally.'}else status.textContent=d.errors.join(' ')}
async function newProfile(){let name=prompt('Name this separate CV profile (for example: Product manager)');if(!name)return;let r=await fetch('/api/profiles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,cv})});if(!r.ok){status.textContent=await r.text();return}profile=(await r.json()).profile;await reloadProfiles();render();status.textContent='New profile saved locally.'}
async function downloadFile(kind){let r=await fetch('/api/'+kind,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cv)});if(!r.ok){status.textContent=await r.text();return}let a=document.createElement('a');a.href=URL.createObjectURL(await r.blob());a.download='CV.'+kind;a.click();URL.revokeObjectURL(a.href)}
const initialCV=__INITIAL_CV__,initialProfiles=__INITIAL_PROFILES__,initialTemplates=__INITIAL_TEMPLATES__,initialPreview=__INITIAL_PREVIEW__;
profiles=initialProfiles;templates=initialTemplates;profile=profiles.some(x=>x.id==='my-cv')?'my-cv':'sample';cv=initialCV;preview.srcdoc=initialPreview;render();</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def send(self, body: bytes, content_type: str, status: int = 200, filename: str | None = None):
        self.send_response(status); self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename: self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers(); self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0")); return json.loads(self.rfile.read(length))

    def do_GET(self):
        parsed = urlparse(self.path); route = parsed.path
        if route == "/":
            safe_json = lambda value: json.dumps(value).replace("</", "<\\/")
            initial_cv = load_cv()
            page = APP_HTML.replace("__INITIAL_CV__", safe_json(initial_cv))
            page = page.replace("__INITIAL_PROFILES__", safe_json(list_profiles()))
            choices = [{"id": key, "label": value.get("label", key)} for key, value in TEMPLATES.items()]
            page = page.replace("__INITIAL_TEMPLATES__", safe_json(choices))
            return self.send(page.replace("__INITIAL_PREVIEW__", safe_json(render_html(initial_cv))).encode(), "text/html; charset=utf-8")
        if route == "/api/cv":
            try:
                profile = parse_qs(parsed.query).get("profile", [None])[0]
                return self.send(json.dumps(load_cv(profile)).encode(), "application/json")
            except ValueError as exc:
                return self.send(str(exc).encode(), "text/plain", HTTPStatus.NOT_FOUND)
        if route == "/api/profiles": return self.send(json.dumps(list_profiles()).encode(), "application/json")
        if route == "/api/templates":
            choices = [{"id": key, "label": value.get("label", key)} for key, value in TEMPLATES.items()]
            return self.send(json.dumps(choices).encode(), "application/json")
        self.send(b"Not found", "text/plain", HTTPStatus.NOT_FOUND)

    def do_POST(self):
        route = urlparse(self.path).path
        try: cv = self.read_json()
        except json.JSONDecodeError as exc: return self.send(str(exc).encode(), "text/plain", HTTPStatus.BAD_REQUEST)
        if route == "/api/profiles":
            try:
                requested = str(cv.get("name", "")).strip().lower()
                profile = re.sub(r"[^a-z0-9]+", "-", requested).strip("-")
                if not profile or not PROFILE_ID.fullmatch(profile):
                    raise ValueError("Use a short profile name made of letters and numbers.")
                saved = save_cv(cv["cv"], profile)
                return self.send(json.dumps({"profile": saved}).encode(), "application/json")
            except (KeyError, TypeError, ValueError) as exc:
                return self.send(str(exc).encode(), "text/plain", HTTPStatus.BAD_REQUEST)
        try: document = render_html(cv)
        except ValueError as exc: return self.send(str(exc).encode(), "text/plain", HTTPStatus.BAD_REQUEST)
        if route == "/api/preview": return self.send(document.encode(), "text/html; charset=utf-8")
        if route == "/api/html": return self.send(document.encode(), "text/html; charset=utf-8", filename="CV.html")
        if route == "/api/pdf":
            try:
                from weasyprint import HTML
            except ImportError:
                return self.send(b"PDF export needs WeasyPrint. Start via: uv run --project .. python server.py", "text/plain", HTTPStatus.SERVICE_UNAVAILABLE)
            return self.send(HTML(string=document, base_url=str(ROOT)).write_pdf(), "application/pdf", filename="CV.pdf")
        self.send(b"Not found", "text/plain", HTTPStatus.NOT_FOUND)

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/cv": return self.send(b"Not found", "text/plain", HTTPStatus.NOT_FOUND)
        try: cv = self.read_json(); errors = validate(cv)
        except json.JSONDecodeError: errors = ["The submitted CV is not valid data."]
        if errors: return self.send(json.dumps({"errors": errors}).encode(), "application/json", HTTPStatus.BAD_REQUEST)
        try:
            profile = parse_qs(parsed.query).get("profile", ["my-cv"])[0]
            saved = save_cv(cv, profile)
        except ValueError as exc:
            return self.send(json.dumps({"errors": [str(exc)]}).encode(), "application/json", HTTPStatus.BAD_REQUEST)
        self.send(json.dumps({"ok": True, "profile": saved}).encode(), "application/json")

    def log_message(self, *_): pass


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--render", action="store_true", help="write content/cv.html and exit")
    parser.add_argument("--port", type=int, default=8765, help="local web port (default: 8765)")
    args = parser.parse_args()
    if args.render:
        (ROOT / "content" / "cv.html").write_text(render_html(load_cv()), encoding="utf-8"); print(ROOT / "content" / "cv.html"); return
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"CV editor: http://127.0.0.1:{args.port} (local only)")
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")

if __name__ == "__main__": main()
