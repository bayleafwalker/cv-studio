# CV Studio

New here or not technical? Read [START-HERE.md](START-HERE.md) and use
`start-windows.bat` on Windows.

CV Studio is a deliberately small, local-only editor for clean, professional CVs.
It can be published as a standalone project; it does not rely on this directory's
parent project or include any personal CV content.

The editor presents ordinary fields, repeatable cards and show/hide switches. It
stores a portable local `content/cv.local.json` document, then feeds that document to a
selected template. The data is not tied to a template, so another template can
be added without making the editor user learn markup or CSS.

## Start

For a nontechnical Windows walkthrough, read [START-HERE.md](START-HERE.md).

For developers, from this directory:

```bash
uv sync
make serve
```

Open <http://127.0.0.1:8765>. Nothing is sent over the network; the server binds
only to the loopback address. Click **Save changes** to update `content/cv.json`.
The preview updates while editing. Use **Download PDF** when WeasyPrint is
installed (the parent project already has it in its `uv` environment), otherwise
use **Download HTML** and print it from the browser.

```bash
python server.py --render  # render without opening the editor
make test                  # renderer and manifest checks
```

## Structure

- `content/cv.sample.json` — safe starter content committed to Git.
- `content/cv.local.json` — automatically created on the first save and ignored
  by Git. This is the personal file the app loads thereafter; copy it elsewhere
  to back it up or move it to another computer.
- `templates/` — presentation-only templates. `classic-two-column` reproduces
  the compact 2018 reference family.
- `server.py` — local editor, validation, HTML rendering and optional PDF export.
- `REQUIREMENTS.md` — product boundary and acceptance criteria.

To make a second visual template, add a renderer to `TEMPLATES` in `server.py`.
It receives the same normalised data, so content and UI stay unchanged.
