let cv, templates = [], profiles = [], profile, meta;
const form = document.querySelector('#form'), preview = document.querySelector('#preview'), status = document.querySelector('#status'), problem = document.querySelector('#problem'), notice = document.querySelector('#notice'), sheet = document.querySelector('.sheet');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const json = body => ({method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});

function ok(message) { status.textContent = message; problem.classList.remove('show'); }
function fail(message) { problem.textContent = message; problem.classList.add('show'); status.textContent = ''; }
function tell(html) { notice.innerHTML = html; notice.classList.add('show'); }
function hush() { notice.classList.remove('show'); }

const fid = path => 'f-' + path.replace(/[^a-z0-9]+/gi, '-');
function field(label, value, path, area = false) {
  return `<label for="${fid(path)}">${label}</label>${area ? `<textarea id="${fid(path)}" data-path="${path}">${esc(value)}</textarea>` : `<input id="${fid(path)}" data-path="${path}" value="${esc(value)}">`}`;
}
function visible(item, path) {
  return `<label class="toggle"><input type="checkbox" data-path="${path}.visible" ${item.visible === false ? '' : 'checked'}> Show this</label>`;
}
function pageBreak(item, path) {
  return `<label class="toggle"><input type="checkbox" data-path="${path}.page_break_before" ${item.page_break_before ? 'checked' : ''}> Start on a new page</label>`;
}
function mover(path, i, n) {
  return `<span class="mini"><button class="secondary" data-move="${path},${i},-1" ${i === 0 ? 'disabled' : ''} title="Move up">▲</button><button class="secondary" data-move="${path},${i},1" ${i === n - 1 ? 'disabled' : ''} title="Move down">▼</button></span>`;
}
function entry(e, path, i, n) {
  return `<div class="card"><button class="remove" data-remove="${path}">Remove</button>${mover(path.replace(/\.\d+$/, ''), i, n)}${visible(e, path)}${pageBreak(e, path)}${field('Title', e.title, path + '.title')}${field('Organisation / school', e.organisation, path + '.organisation')}<div class="row"><div>${field('Dates', e.dates, path + '.dates')}</div><div>${field('Location', e.location, path + '.location')}</div></div>${field('Description', e.description, path + '.description', true)}<label for="${fid(path + '.bullets')}">Achievement bullets (one per line)</label><textarea id="${fid(path + '.bullets')}" data-bullets="${path}">${esc((e.bullets || []).join('\n'))}</textarea></div>`;
}
function profileOptions() {
  return profiles.map(p => `<option value="${esc(p.id)}" ${p.id === profile ? 'selected' : ''}>${p.error ? '⚠ ' : ''}${esc(p.label)}${p.error ? ' — cannot be opened' : ''}</option>`).join('');
}
function renderProfiles() {
  const select = form.querySelector('[data-profile]');
  if (select) select.innerHTML = profileOptions();
}
function render() {
  const options = templates.map(t => `<option value="${t.id}" ${t.id === cv.template ? 'selected' : ''}>${t.label}</option>`).join('');
  const isSample = profile === 'sample';
  form.innerHTML = `<h2>Which CV</h2><label for="f-profile">Open CV</label><select id="f-profile" data-profile>${profileOptions()}</select>
<p class="hint">${isSample ? 'This is the example. Your edits are saved as <b>My CV</b> automatically.' : `Saved in <code>${esc((profiles.find(p => p.id === profile) || {}).file || '')}</code>.`}</p>
<div class="actions"><button class="secondary" onclick="newProfile()">Make a copy of this CV</button><button class="secondary" onclick="renameProfile()" ${isSample ? 'disabled' : ''}>Rename</button><button class="danger" onclick="deleteProfile()" ${isSample ? 'disabled' : ''}>Delete this CV</button></div>
<div class="card"><b>Your CV files are here:</b><br><code>${esc(meta.folder)}</code><div class="actions" style="margin-bottom:0"><button class="secondary" onclick="openFolder()">Open this folder</button></div><p class="hint" style="margin:8px 0 0">Any <code>.json</code> file you put in this folder shows up in the <b>Open CV</b> list within a few seconds. The file name becomes the CV name.</p></div>
<p class="hint">Want ChatGPT to draft one? Click <b>Copy example for ChatGPT</b>, paste it into the chat, save the answer as a <code>.json</code> file, then click <b>Open a CV file…</b> (or drop the file onto this window, or put it in the CV folder).</p>
<h2>Document style</h2><label for="f-template">Template</label><select id="f-template" data-template>${options}</select><p class="hint">The style changes presentation only; your content stays the same.</p>
<h2>About you</h2>${field('Full name', cv.person.name, 'person.name')}${field('Headline', cv.person.headline, 'person.headline')}${field('Short introduction', cv.person.summary, 'person.summary', true)}
<h2>Contact details</h2>${cv.contact.map((x, i) => `<div class="card"><button class="remove" data-remove="contact.${i}">Remove</button>${mover('contact', i, cv.contact.length)}${visible(x, 'contact.' + i)}${field('Label', x.label, 'contact.' + i + '.label')}${field('Value', x.value, 'contact.' + i + '.value')}</div>`).join('')}<button class="secondary" data-add-contact>Add contact detail</button>
<h2>Sidebar</h2><p class="hint">Short lists such as skills and languages. In the modern style these appear as compact lines under the introduction.</p>${cv.sidebar_sections.map((x, i) => `<div class="card"><button class="remove" data-remove="sidebar_sections.${i}">Remove</button>${mover('sidebar_sections', i, cv.sidebar_sections.length)}${visible(x, 'sidebar_sections.' + i)}${pageBreak(x, 'sidebar_sections.' + i)}${field('Heading', x.title, 'sidebar_sections.' + i + '.title')}<label for="${fid('sidebar_sections.' + i + '.items')}">Items (one per line)</label><textarea id="${fid('sidebar_sections.' + i + '.items')}" data-items="sidebar_sections.${i}">${esc((x.items || []).join('\n'))}</textarea></div>`).join('')}<button class="secondary" data-add-sidebar>Add sidebar block</button>
<h2>Main CV sections</h2><p class="hint">Move whole sections to set their order. Any section, entry or sidebar block can start on a fresh A4 page; you can also hover an entry in the preview and click <b>Move to next page</b>.</p>
${cv.sections.map((s, i) => `<section class="card"><div class="actions"><button class="secondary" data-section-move="${i},-1" ${i === 0 ? 'disabled' : ''}>Move up</button><button class="secondary" data-section-move="${i},1" ${i === cv.sections.length - 1 ? 'disabled' : ''}>Move down</button></div>${visible(s, 'sections.' + i)}<label class="toggle"><input type="checkbox" data-path="sections.${i}.page_break_before" ${s.page_break_before ? 'checked' : ''}> Start this section on a new page</label>${field('Section heading', s.title, 'sections.' + i + '.title')}<p class="hint">${s.type}</p>${s.entries.map((e, j) => entry(e, `sections.${i}.entries.${j}`, j, s.entries.length)).join('')}<button class="secondary" data-add="${i}">Add ${s.type} entry</button></section>`).join('')}
<p class="hint">CV Studio ${esc(meta.version)}</p>`;
  bind();
}
function get(path) { return path.split('.').reduce((o, k) => o[k], cv); }
function set(path, value) { const p = path.split('.'), key = p.pop(), o = p.reduce((x, k) => x[k], cv); o[key] = value; }
function bind() {
  form.querySelectorAll('[data-path]').forEach(el => el.oninput = () => { set(el.dataset.path, el.type === 'checkbox' ? el.checked : el.value); changed(); });
  form.querySelector('[data-template]').onchange = e => { cv.template = e.target.value; changed(); };
  form.querySelector('[data-profile]').onchange = e => loadProfile(e.target.value);
  form.querySelectorAll('[data-bullets]').forEach(el => el.oninput = () => { get(el.dataset.bullets).bullets = el.value.split('\n').filter(Boolean); changed(); });
  form.querySelectorAll('[data-items]').forEach(el => el.oninput = () => { get(el.dataset.items).items = el.value.split('\n').filter(Boolean); changed(); });
  form.querySelectorAll('[data-remove]').forEach(b => b.onclick = () => { const p = b.dataset.remove.split('.'), idx = +p.pop(), list = get(p.join('.')), [item] = list.splice(idx, 1); undoStack.push({list: p.join('.'), idx, item}); render(); changed(); tell(`Removed “${esc(item.title || item.label || item.value || 'item')}”.<button onclick="undo()">Undo</button>`); });
  form.querySelectorAll('[data-move]').forEach(b => b.onclick = () => { const [path, i, d] = b.dataset.move.split(','), list = get(path), from = +i, to = from + +d; if (to < 0 || to >= list.length) return; [list[from], list[to]] = [list[to], list[from]]; render(); changed(); form.querySelector(`[data-move="${path},${to},${d}"]`)?.focus(); });
  const addC = form.querySelector('[data-add-contact]'); if (addC) addC.onclick = () => { cv.contact.push({label: 'Website', value: '', visible: true}); render(); changed(); form.querySelector(`[data-path="contact.${cv.contact.length - 1}.value"]`).focus(); };
  const addS = form.querySelector('[data-add-sidebar]'); if (addS) addS.onclick = () => { cv.sidebar_sections.push({title: 'New block', visible: true, items: []}); render(); changed(); form.querySelector(`[data-path="sidebar_sections.${cv.sidebar_sections.length - 1}.title"]`).select(); };
  form.querySelectorAll('[data-add]').forEach(b => b.onclick = () => { cv.sections[+b.dataset.add].entries.push({title: 'New entry', organisation: '', dates: '', location: '', description: '', bullets: [], visible: true}); render(); changed(); });
  form.querySelectorAll('[data-section-move]').forEach(b => b.onclick = () => { const [i, d] = b.dataset.sectionMove.split(',').map(Number), to = i + d; if (to < 0 || to >= cv.sections.length) return; [cv.sections[i], cv.sections[to]] = [cv.sections[to], cv.sections[i]]; render(); changed(); });
}

const undoStack = [];
function undo() { const u = undoStack.pop(); if (!u) return; get(u.list).splice(u.idx, 0, u.item); render(); changed(); hush(); ok('Put back.'); }
document.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && undoStack.length) { e.preventDefault(); undo(); } });
// Editing marks the CV dirty and schedules a save; re-rendering the form never does (that caused an endless save/redraw loop).
let previewTimer, saveTimer, dirty = false;
function changed() { dirty = true; status.textContent = 'Saving…'; clearTimeout(saveTimer); saveTimer = setTimeout(save, 700); updatePreview(); }
function updatePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    const r = await fetch('/api/preview', json(cv));
    if (!r.ok) { fail(await r.text()); return; }
    preview.srcdoc = await r.text();
  }, 120);
}
preview.onload = () => { paginate(); fitPreview(); addHandles(); addClickToEdit(); follow(lastPath, false); };
const MM = 96 / 25.4, PAGE = 297 * MM;
function margins() { return (templates.find(t => t.id === cv.template) || {}).margins || {top: 0, right: 0, bottom: 0, left: 0}; }
// Screen preview of print pagination: blocks that would cross the bottom margin are pushed to the next page's
// top margin (what break-inside: avoid does in print), and explicit page breaks jump to the next page.
function paginate() {
  const doc = preview.contentDocument;
  if (!doc) return;
  const m = margins(), mt = m.top * MM, mb = m.bottom * MM, usable = PAGE - mt - mb;
  doc.querySelectorAll('.pushed').forEach(el => { el.classList.remove('pushed'); el.style.removeProperty('--push'); });
  doc.querySelectorAll('.page-break').forEach(el => el.style.setProperty('--push', '0px'));
  const scrollTop = () => doc.documentElement.scrollTop;
  doc.querySelectorAll('.page-break, .masthead, .contact, .summary, .sidebar-section, .main-section > h2, .entry, .entry > :not(.cv-handle), li').forEach(el => {
    const box = el.getBoundingClientRect(), top = box.top + scrollTop(), bottom = top + box.height;
    if (!box.height) return;
    const k = Math.floor(top / PAGE), pageTop = k * PAGE + mt, limit = (k + 1) * PAGE - mb;
    let push = 0;
    if (el.classList.contains('page-break') && top - pageTop > 1) push = (k + 1) * PAGE + mt - top;
    else if ((bottom > limit + 0.5 || top >= limit) && box.height <= usable) push = (k + 1) * PAGE + mt - top;
    if (push <= 0) return;
    // Print keeps a heading with what follows it (break-after: avoid): push the heading instead, the block follows.
    const prev = el.previousElementSibling;
    if (prev && prev.tagName === 'H2' && !prev.classList.contains('pushed')) {
      const ptop = prev.getBoundingClientRect().top + scrollTop();
      prev.classList.add('pushed'); prev.style.setProperty('--push', ((k + 1) * PAGE + mt - ptop) + 'px');
    } else { el.classList.add('pushed'); el.style.setProperty('--push', push + 'px'); }
  });
}
function fitPreview() {
  const doc = preview.contentDocument, m = margins();
  if (doc && doc.documentElement) {
    const height = doc.documentElement.scrollHeight, pages = Math.max(1, Math.ceil((height - 2) / PAGE));
    preview.style.height = (pages * PAGE) + 'px';
    document.querySelector('#pagecount').textContent = pages === 1 ? '1 page' : `${pages} pages — the red lines show where pages end`;
    const band = 'rgba(214,98,106,.07)', mt = m.top * MM, mb = m.bottom * MM;
    document.querySelector('.guides').style.background = `repeating-linear-gradient(to bottom, ${band} 0, ${band} ${mt}px, transparent ${mt}px, transparent ${PAGE - mb}px, ${band} ${PAGE - mb}px, ${band} ${PAGE - 1}px, #d6626a ${PAGE - 1}px, #d6626a ${PAGE}px)`;
  }
  const available = preview.closest('.preview').clientWidth - 36, scale = Math.min(1, available / sheet.offsetWidth);
  sheet.style.transform = `scale(${scale})`;
  sheet.style.marginBottom = (sheet.offsetHeight * (scale - 1)) + 'px';
}
// Clicking a part of the CV opens the matching fields in the editor.
function editFrom(path) {
  const first = form.querySelector(`[data-path="${path}.title"], [data-path="${path}.name"], [data-path="${path}.value"], [data-path="${path}.label"], [data-path^="${path}."]:not([type=checkbox]), [data-items="${path}"]`);
  if (!first) return;
  document.body.classList.remove('show-preview'); const t = document.querySelector('.viewtoggle'); if (t) t.textContent = '👁 Show the CV';
  first.scrollIntoView({block: 'center', behavior: 'smooth'}); first.focus({preventScroll: true});
}
function addClickToEdit() {
  const doc = preview.contentDocument;
  if (!doc) return;
  doc.querySelectorAll('[data-cv]').forEach(el => { el.style.cursor = 'text'; el.title = el.title || 'Click to edit this in the form'; });
  doc.body.addEventListener('click', e => { if (e.target.closest('.cv-handle, a')) return; const el = e.target.closest('[data-cv]'); if (el) { e.preventDefault(); editFrom(el.dataset.cv); } });
}
// Page-break handles inside the preview: hover an entry (or sidebar block) and move it to the next page; split entries are flagged.
function addHandles() {
  const doc = preview.contentDocument;
  if (!doc) return;
  const pageHeight = PAGE;
  let splits = 0;
  doc.querySelectorAll('.entry[data-cv], .sidebar-section[data-cv]').forEach(el => {
    const path = el.dataset.cv, item = get(path), on = !!item.page_break_before;
    const push = parseFloat(el.style.getPropertyValue('--push')) || 0;
    const box = el.getBoundingClientRect(), top = box.top + doc.documentElement.scrollTop + push, bottom = top + box.height - push;
    const split = !on && Math.floor(top / pageHeight) !== Math.floor((bottom - 1) / pageHeight);
    if (split) { el.classList.add('cv-split'); splits++; }
    const b = doc.createElement('button');
    b.className = 'cv-handle' + (on ? ' on' : '');
    b.textContent = on ? '↥ Undo page break' : split ? '↧ Too long for one page — move to next page' : '↧ Move to next page';
    b.title = 'This only changes where the page ends; your text stays the same.';
    b.onclick = e => { e.preventDefault(); set(path + '.page_break_before', !on); lastPath = path; render(); changed(); };
    el.appendChild(b);
  });
  const count = document.querySelector('#pagecount');
  if (splits) count.textContent += ` · ${splits} ${splits === 1 ? 'entry is' : 'entries are'} too long for one page (dashed); shorten it or move it.`;
}
// The preview follows the field being edited: scroll to and outline the matching part of the CV.
let lastPath = '';
function follow(path, smooth = true) {
  if (!path) return;
  lastPath = path;
  const doc = preview.contentDocument;
  if (!doc) return;
  let el = null, parts = path.split('.');
  while (parts.length && !el) { el = doc.querySelector(`[data-cv="${parts.join('.')}"]`); parts.pop(); }
  doc.querySelectorAll('.cv-focus').forEach(x => x.classList.remove('cv-focus'));
  if (!el) return;
  el.classList.add('cv-focus');
  const pane = document.querySelector('.preview'), scale = sheet.getBoundingClientRect().width / sheet.offsetWidth;
  const top = sheet.offsetTop + (el.getBoundingClientRect().top + (parseFloat(el.style.getPropertyValue('--push')) || 0)) * scale - 60;
  if (top < pane.scrollTop || top + el.offsetHeight * scale > pane.scrollTop + pane.clientHeight - 60) pane.scrollTo({top: Math.max(0, top), behavior: smooth ? 'smooth' : 'auto'});
}
form.addEventListener('focusin', e => follow(e.target.dataset.path || e.target.dataset.bullets || e.target.dataset.items));
window.addEventListener('resize', fitPreview);

async function reloadProfiles() { profiles = await fetch('/api/profiles').then(r => r.json()); profiles.forEach(p => known.add(p.id)); renderProfiles(); }
async function loadProfile(id, quiet = false) {
  if (dirty) { await save(); if (dirty) { renderProfiles(); return; } }
  const r = await fetch('/api/cv?profile=' + encodeURIComponent(id));
  if (!r.ok) {
    const info = profiles.find(p => p.id === id) || {};
    fail(`${info.file || id} cannot be opened.\n${await r.text()}\n\nFix the file and save it; this page notices the change by itself. If ChatGPT wrote it, paste this message back to ChatGPT and ask for a corrected file.`);
    renderProfiles();
    return;
  }
  cv = await r.json(); profile = id; render(); updatePreview(); hush();
  if (!quiet) ok('Opened from this computer.');
}
async function save() {
  clearTimeout(saveTimer);
  const r = await fetch('/api/cv?profile=' + encodeURIComponent(profile), {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cv)});
  const d = await r.json();
  if (!r.ok) { fail('Not saved yet: ' + d.errors.join(' ')); return; }
  dirty = false;
  const switched = d.profile !== profile;
  profile = d.profile;
  await reloadProfiles();
  if (switched) render();
  ok('Saved on this computer at ' + new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) + '.');
}
async function createProfile(name, data) {
  const r = await fetch('/api/profiles', json({name, cv: data}));
  if (!r.ok) { fail(await r.text()); return false; }
  const created = (await r.json()).profile;
  await reloadProfiles();
  await loadProfile(created, true);
  return true;
}
async function newProfile() {
  const current = (profiles.find(p => p.id === profile) || {}).label || 'My CV';
  const name = prompt('Name for the copy', current === 'Example CV' ? 'My CV 2' : current + ' 2');
  if (!name) return;
  if (dirty) await save();
  if (await createProfile(name, cv)) ok('Copy saved. You are now editing the copy.');
}
async function renameProfile() {
  const info = profiles.find(p => p.id === profile) || {};
  const name = prompt('New name for this CV', info.label || '');
  if (!name || name === info.label) return;
  if (dirty) await save();
  const r = await fetch('/api/rename', json({profile, name}));
  if (!r.ok) { fail(await r.text()); return; }
  profile = (await r.json()).profile; await reloadProfiles(); render(); ok('Renamed.');
}
async function deleteProfile() {
  const info = profiles.find(p => p.id === profile) || {};
  if (!confirm(`Delete "${info.label}" (${info.file})? This cannot be undone.`)) return;
  const r = await fetch('/api/cv?profile=' + encodeURIComponent(profile), {method: 'DELETE'});
  if (!r.ok) { fail(await r.text()); return; }
  dirty = false; await reloadProfiles();
  await loadProfile(profiles.some(p => p.id === 'my-cv') ? 'my-cv' : 'sample', true);
  ok('Deleted.');
}
async function openFolder() {
  const r = await fetch('/api/open-folder', {method: 'POST'});
  if (r.ok) ok('Folder opened: ' + await r.text() + ' — any .json file you put there appears in the Open CV list.'); else fail(await r.text());
}
async function importFile(file) {
  if (!file) return;
  let imported;
  try { imported = JSON.parse(await file.text()); }
  catch (error) { fail(`${file.name} is not valid JSON: ${error.message}\n\nIf ChatGPT wrote it, paste this message back and ask for the complete corrected file.`); return; }
  const r = await fetch('/api/preview', json(imported));
  if (!r.ok) { fail(`${file.name} cannot be used: ${await r.text()}`); return; }
  if (dirty) await save();
  if (await createProfile(file.name, imported)) ok(`${file.name} opened and saved as its own CV.`);
}
document.querySelector('#backup-file').onchange = e => { importFile(e.target.files[0]); e.target.value = ''; };
document.addEventListener('dragover', e => { e.preventDefault(); document.body.classList.add('dragging'); });
document.addEventListener('dragleave', e => { if (!e.relatedTarget) document.body.classList.remove('dragging'); });
document.addEventListener('drop', e => { e.preventDefault(); document.body.classList.remove('dragging'); importFile(e.dataTransfer.files[0]); });

async function copyForChat() {
  const text = `I am making a CV. Below is (1) my background and (2) a CV in JSON form that shows the exact structure to use.
Please write my CV in that JSON structure: keep every field name and the "template" value exactly as they are, replace the example text with my real details, keep "visible": true, and write concise achievement bullets that start with an action and state a result. If something is unknown, write "Add ..." so I can fill it in. Answer with the complete JSON only, no other text, so I can save it as a .json file.

(1) MY BACKGROUND — paste your old CV, LinkedIn text or a job advert here:
...

(2) STRUCTURE:
` + JSON.stringify(cv, null, 2);
  try { await navigator.clipboard.writeText(text); ok('Copied. Paste it into ChatGPT, then save the answer as a .json file and click "Open a CV file…".'); }
  catch { downloadBlob(new Blob([text], {type: 'text/plain'}), 'cv-for-chatgpt.txt'); ok('Saved as cv-for-chatgpt.txt in your Downloads. Paste its contents into ChatGPT.'); }
}
const PLACEHOLDER = /^(add |your |write |describe |briefly |start each|use a second|skill (one|two|three|four)|language (one|two)|job title$|organisation$|degree or qualification|school or university|relevant project|city, country|new entry$|emphasise |showcase |quantify |add a )|example\.com|\+00 000|XX/i;
function placeholders() {
  const found = [];
  const walk = (v, where) => { if (typeof v === 'string') { if (PLACEHOLDER.test(v.trim())) found.push(`${where}: “${v.trim().slice(0, 40)}${v.trim().length > 40 ? '…' : ''}”`); } else if (Array.isArray(v)) v.forEach((x, i) => walk(x, where)); else if (v && typeof v === 'object') Object.entries(v).forEach(([k, x]) => walk(x, k === 'title' || k === 'name' ? where : (where ? where + ' › ' : '') + k.replace(/_/g, ' '))); };
  walk({person: cv.person, contact: cv.contact, sidebar: cv.sidebar_sections, sections: cv.sections}, '');
  return found;
}
async function savePDF() {
  const left = placeholders();
  if (left.length && !confirm(`${left.length} place${left.length === 1 ? '' : 's'} still contain${left.length === 1 ? 's' : ''} example text:\n\n${left.slice(0, 8).join('\n')}${left.length > 8 ? '\n…' : ''}\n\nMake the PDF anyway?`)) { fail('Example text left: ' + left.join(' · ')); return; }
  if (dirty) await save();
  const r = await fetch('/api/pdf', json(cv));
  if (r.ok) { downloadBlob(await r.blob(), fileName('pdf')); ok('PDF saved to your Downloads.'); return; }
  fail('The PDF could not be made directly: ' + await r.text());
  tell('In the print window: <b>Printer</b> = Save as PDF (or Microsoft Print to PDF) · <b>Paper</b> = A4 · <b>Margins</b> = Default · <b>Background graphics</b> on (under More settings) · then Save.<button onclick="hush()">Got it</button>');
  preview.contentWindow.focus(); preview.contentWindow.print();
}
function fileName(kind) { return (cv.person.name || 'CV').trim().replace(/[^a-z0-9]+/gi, '-') + '-CV.' + kind; }
function downloadBlob(blob, name) { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); URL.revokeObjectURL(a.href); }
async function downloadFile(kind) {
  const r = await fetch('/api/' + kind, json(cv));
  if (!r.ok) { fail(await r.text()); return; }
  downloadBlob(await r.blob(), fileName(kind));
}

// Notice CV files that appear or change in the folder while the page is open.
let known = new Set();
async function watchFolder() {
  try {
    const latest = await fetch('/api/profiles').then(r => r.json());
    const fresh = latest.filter(p => !known.has(p.id) && p.id !== 'sample');
    const removed = profiles.filter(p => !latest.some(q => q.id === p.id));
    const broke = latest.filter(p => p.error && !(profiles.find(q => q.id === p.id) || {}).error);
    const fixed = latest.filter(p => !p.error && (profiles.find(q => q.id === p.id) || {}).error);
    profiles = latest; latest.forEach(p => known.add(p.id)); renderProfiles();
    if (fresh.length) {
      const p = fresh[0];
      if (p.error) fail(`New file found: ${p.file}\n${p.error}\n\nFix the file and save it; it is checked again automatically.`);
      else tell(`New CV file found: <b>${esc(p.file)}</b><button onclick="loadProfile('${esc(p.id)}');hush()">Open it</button>`);
    } else if (fixed.length) {
      const p = fixed[0]; problem.classList.remove('show');
      tell(`${esc(p.file)} is fine now.<button onclick="loadProfile('${esc(p.id)}');hush()">Open it</button>`);
    } else if (broke.length) {
      fail(`${broke[0].file} changed and cannot be opened any more.\n${broke[0].error}`);
    } else if (removed.some(p => p.id === profile)) {
      fail(`The file for this CV (${removed.find(p => p.id === profile).file}) was removed while it was open. Save now to write it again, or open another CV.`);
    }
  } catch {}
}

const initial = JSON.parse(document.querySelector('#initial').textContent);
meta = initial.meta;
profiles = initial.profiles; templates = initial.templates; profile = meta.profile; cv = initial.cv;
profiles.forEach(p => known.add(p.id));
preview.srcdoc = initial.preview; render();
ok(profile === 'sample' ? 'Ready. This is the example CV; start typing and your version is saved automatically.' : 'Ready — saved changes stay on this computer.');
setInterval(watchFolder, 2500);
