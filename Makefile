PYTHON ?= uv run python

.PHONY: serve check render test

serve:
	$(PYTHON) server.py

check:
	$(PYTHON) -m py_compile server.py
	$(PYTHON) -c "from server import load_cv, validate; assert not validate(load_cv())"

render: check
	$(PYTHON) server.py --render

test:
	$(PYTHON) -m unittest discover -s tests -v
