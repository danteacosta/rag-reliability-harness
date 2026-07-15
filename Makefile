.PHONY: test ingest eval gate simulate all

PYTHON := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

test:
	$(PYTHON) -m pytest -q

ingest:
	$(PYTHON) -m ingest --corpus-root data/corpus --mutable-version v2 --index-dir .index

eval:
	$(PYTHON) -m eval

gate:
	$(PYTHON) -m gates

simulate:
	$(PYTHON) -m eval.simulate_regressions

all: test ingest eval gate
