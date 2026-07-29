# Functional requirements — local minimal-style CV editor

## Goal

Provide a focused, locally runnable editor for producing a polished, one-page-
when-possible CV in the visual family of a compact classic reference résumé:
an airy A4 document, personal details and skills in a narrow left column, and
education, experience and projects in the main column. It supplements—not
replaces—the parent YAML generator, whose evidence/provenance workflow remains
appropriate for its existing CV.

## Users and boundaries

- A nontechnical user edits their own content without seeing JSON, YAML, HTML,
  CSS, template variables, or build commands after start-up.
- The app is local-only and has no authentication, cloud storage, analytics or
  external calls. It binds to `127.0.0.1` only.
- The new editor lives in `editor-workspace/` and does not modify the parent
  generator's content, templates or deliverables.
- The initial scope is English and the compact classic style family, with a data
  model ready for optional additional templates. It is not a general document
  editor or a multi-user service.

## Functional behaviour

1. The editor shall expose friendly fields for name, headline, summary, contact
   details, skills, languages, education, experience and projects.
2. Repeatable sections shall use add/remove cards; individual cards and sections
   can be hidden without deletion. Experiences support simple achievement bullets.
3. A user shall be able to choose a visual template. The selected template is
   presentation metadata; the editable CV data remains template-neutral.
4. Changes shall update an A4 preview immediately in the browser. Save writes an
   atomic, readable local JSON profile (`cv.local.json`, ignored by Git) and
   reports validation errors in plain language.
5. The user shall be able to download self-contained HTML and, when WeasyPrint is
   available, PDF. Browser printing is the fallback PDF path.
6. The editor shall include fictional sample content only as a starting point;
   users can replace it entirely.

## Acceptance criteria

- `python server.py` starts an editor at `http://127.0.0.1:8765` with no network
  listener beyond localhost.
- A user can change the headline, add an experience bullet, hide a project and
  save; reload retains all three changes and preview reflects them.
- The sample downloads as an A4 two-column document with sidebar contact/skills/
  languages and main education/work/project sections.
- Invalid or incomplete JSON submitted through the API is rejected with a
  understandable message and does not overwrite the saved document.
- The source document can be rendered by the CLI without opening a browser.

## Non-goals for this iteration

- Rich text, drag-and-drop reordering, accounts, collaboration, spellchecking,
  automatic CV writing, job-specific variants, DOCX export and full localisation.
  These can be added on top of the stable content model if they become needed.
