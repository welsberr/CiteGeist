PYTHONPATH_SRC=PYTHONPATH=src
VENV_PYTHON=.venv/bin/python

.PHONY: test test-live live-smoke

test:
	$(PYTHONPATH_SRC) $(VENV_PYTHON) -m pytest -q

test-live:
	CITEGEIST_LIVE_TESTS=1 CITEGEIST_SOURCE_CACHE=.cache/citegeist $(PYTHONPATH_SRC) $(VENV_PYTHON) -m pytest -m live -q

live-smoke:
	CITEGEIST_SOURCE_CACHE=.cache/citegeist $(PYTHONPATH_SRC) $(VENV_PYTHON) scripts/live_smoke.py
