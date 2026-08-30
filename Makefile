PYTHON ?= uv run python

.PHONY: serve check render test dist

serve:
	$(PYTHON) server.py

check:
	$(PYTHON) -m py_compile server.py
	$(PYTHON) -c "from server import load_cv, validate; assert not validate(load_cv('sample'))"

render: check
	$(PYTHON) server.py --render

test:
	$(PYTHON) -m unittest discover -s tests -v

# The same layout the release workflow and update-windows.ps1 expect: a cv-studio/ folder at the top.
dist:
	mkdir -p dist
	git archive --format=zip --prefix=cv-studio/ -o dist/cv-studio-windows.zip HEAD
