PYTHON ?= uv run --frozen python

.PHONY: serve check render test e2e dist

serve:
	$(PYTHON) server.py

check:
	$(PYTHON) -m py_compile server.py
	$(PYTHON) -c "from server import load_cv, validate; assert not validate(load_cv('sample'))"

render: check
	$(PYTHON) server.py --render

test:
	$(PYTHON) -m unittest discover -s tests -v

# Browser walkthrough of the real editor (needs Node; installs Playwright's Chromium on first run).
e2e:
	cd tests/e2e && npm install --no-audit --no-fund && npx playwright install chromium && PYTHON="$(PYTHON)" node walkthrough.mjs

# The same layout the release workflow and update-windows.ps1 expect: a cv-studio/ folder at the top.
dist:
	mkdir -p dist
	git archive --format=zip --prefix=cv-studio/ -o dist/cv-studio-windows.zip HEAD
