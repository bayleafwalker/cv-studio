# CV Studio — a stupidly simple little CV generator

CV Studio is a stupidly simple little CV generator for clean, professional CVs.
It runs only on your computer and does not upload your CV anywhere.

## Download and start on Windows

You do **not** need to know Git or use a command line.

1. Open [the latest release](../../releases/latest).
2. Under **Assets**, download `cv-studio-windows.zip`.
3. Open your Downloads folder, right-click the ZIP file and choose **Extract All**.
4. Open the extracted `cv-studio` folder and read `START-HERE.md`.
5. Follow the one-time Python setup, then double-click `start-windows.bat`.

If the release ZIP is unavailable, use the green **Code** button on this page and
choose **Download ZIP** instead.

Your CV stays in the folder on your computer. Back up the local profile file as
explained in the guide.

## Screenshots

### Editor

![CV Studio editor, with profile selection, template selection, and live preview](assets/screenshots/editor.png)

### Classic two-column template

![Classic two-column sample CV](assets/screenshots/classic-two-column.png)

### Modern single-column template

![Modern single-column sample CV](assets/screenshots/modern-single-column.png)

The editor presents ordinary fields, repeatable cards and show/hide switches. It
stores a portable local `content/cv.local.json` document, then feeds that document to a
selected template. The data is not tied to a template, so another template can
be added without making the editor user learn markup or CSS.

## Start

For developers, from this directory:

```bash
uv sync
make serve
```

Open <http://127.0.0.1:8765>. Nothing is sent over the network; the server binds
only to the loopback address. Click **Save changes** to update your local profile.
The preview updates while editing. Use **Download PDF** when the PDF helper is
installed, otherwise use **Download HTML** and print it from the browser.

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
