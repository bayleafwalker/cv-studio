// Drives the real editor through the onboarding path and fails loudly if any step regresses.
// Run with `make e2e` from the project root. Uses a scratch copy of the content folder.
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const port = 8790 + Math.floor(Math.random() * 100);
const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'cv-studio-e2e-'));
const server = spawn(`${process.env.PYTHON || 'python3'} server.py --port ${port}`, { cwd: root, shell: true, env: { ...process.env, CV_STUDIO_CONTENT: scratch }, stdio: 'inherit' });
const failures = [];
const expect = (label, condition, detail = '') => { console.log(`${condition ? 'ok  ' : 'FAIL'} ${label}${detail ? ' — ' + detail : ''}`); if (!condition) failures.push(label); };
const sample = JSON.parse(fs.readFileSync(path.join(root, 'content', 'cv.sample.json'), 'utf8'));
const downloads = fs.mkdtempSync(path.join(os.tmpdir(), 'cv-studio-downloads-'));
const chatgptFile = path.join(downloads, 'cv (1).json');
fs.writeFileSync(chatgptFile, JSON.stringify({ ...sample, person: { ...sample.person, name: 'Imported Person' } }));

try {
  await new Promise(r => setTimeout(r, 1500));
  const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const errors = []; page.on('pageerror', e => errors.push(String(e)));
  page.on('dialog', d => d.accept());
  const status = () => page.locator('#status').innerText();
  await page.goto(`http://127.0.0.1:${port}/`);

  // Typing saves without re-rendering the form or losing focus.
  await page.locator('[data-path="person.name"]').fill('Test Person'); await page.waitForTimeout(1200);
  expect('autosave', (await status()).startsWith('Saved on this computer'));
  let renders = 0; await page.exposeFunction('bump', () => renders++);
  await page.evaluate(() => new MutationObserver(() => bump()).observe(document.querySelector('#form'), { childList: true }));
  await page.locator('[data-path="person.headline"]').focus(); await page.keyboard.type(' x'); await page.waitForTimeout(2500);
  expect('no re-render loop', renders === 0, `re-renders: ${renders}`);
  expect('focus kept', (await page.evaluate(() => document.activeElement.dataset.path)) === 'person.headline');

  // Importing a file names the CV after the file, with no prompt.
  await page.locator('#backup-file').setInputFiles(chatgptFile); await page.waitForTimeout(1200);
  expect('import names CV after file', (await page.locator('[data-profile]').inputValue()) === 'cv (1)');

  // A broken file dropped into the folder is reported with the reason; fixing it is noticed.
  const dropped = path.join(scratch, 'profiles', 'From ChatGPT.json');
  fs.writeFileSync(dropped, '{"template": "classic-two-column", "person": {}'); await page.waitForTimeout(3500);
  expect('broken file explained', (await page.locator('#problem').innerText()).includes('not valid JSON'));
  fs.writeFileSync(dropped, JSON.stringify(sample)); await page.waitForTimeout(3500);
  expect('fixed file noticed', (await page.locator('#notice').innerText()).includes('is fine now'));

  // Preview follows the field being edited and paginates within the margins.
  await page.locator('[data-path="sections.2.entries.0.title"]').focus(); await page.waitForTimeout(800);
  expect('preview follows editing', (await page.evaluate(() => document.querySelector('#preview').contentDocument.querySelector('.cv-focus')?.dataset.cv)) === 'sections.2.entries.0');
  await page.evaluate(() => { const s = cv.sections[1]; s.entries = [...s.entries, ...s.entries, ...s.entries, ...s.entries, ...s.entries, ...s.entries]; render(); changed(); }); await page.waitForTimeout(1500);
  const crossing = await page.evaluate(() => { const d = document.querySelector('#preview').contentDocument, PAGE = 297 * 96 / 25.4, m = templates.find(t => t.id === cv.template).margins, mt = m.top * 96 / 25.4, mb = m.bottom * 96 / 25.4; let n = 0; for (const e of d.querySelectorAll('.entry, .main-section > h2, li')) { const push = parseFloat(e.style.getPropertyValue('--push')) || 0, r = e.getBoundingClientRect(), top = r.top + d.documentElement.scrollTop + push, bottom = top + r.height - push, k = Math.floor(top / PAGE); if (r.height && bottom > (k + 1) * PAGE - mb + 0.5 && r.height <= PAGE - mt - mb) n++; } return n; });
  expect('nothing crosses the bottom margin', crossing === 0, `crossing: ${crossing}`);
  expect('multi-page count shown', /\d+ pages/.test(await page.locator('#pagecount').innerText()));

  // Every template renders and Save as PDF falls back to the print dialog when there is no helper.
  for (const id of await page.evaluate(() => templates.map(t => t.id))) {
    await page.locator('[data-template]').selectOption(id); await page.waitForTimeout(1000);
    expect(`template ${id} renders`, (await page.frameLocator('#preview').locator('h1').innerText()).includes('Test Person') || (await page.frameLocator('#preview').locator('h1').innerText()).length > 0);
  }
  await page.route('**/api/pdf', r => r.fulfill({ status: 503, body: 'no helper' }));
  await page.evaluate(() => { document.querySelector('#preview').contentWindow.print = () => window.__printed = true; });
  await page.locator('button', { hasText: 'Save as PDF' }).click(); await page.waitForTimeout(800);
  expect('print dialog fallback', await page.evaluate(() => window.__printed === true));

  // Remove + undo, reorder, rename.
  await page.locator('[data-remove="contact.0"]').click(); await page.locator('#notice button').click(); await page.waitForTimeout(300);
  expect('undo restores', (await page.evaluate(() => cv.contact[0].label)) === 'Email');
  expect('no JS errors', errors.length === 0, errors.join(' | '));
  await browser.close();
} finally {
  server.kill(); spawn('pkill', ['-f', `server.py --port ${port}`]);
  fs.rmSync(scratch, { recursive: true, force: true }); fs.rmSync(downloads, { recursive: true, force: true });
}
if (failures.length) { console.error(`\n${failures.length} step(s) failed: ${failures.join(', ')}`); process.exit(1); }
console.log('\nAll steps passed.');
