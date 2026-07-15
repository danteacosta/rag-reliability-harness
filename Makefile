.PHONY: test ingest eval gate simulate all

test:
	python -m pytest -v

ingest:
	python -m ingest --corpus-root data/corpus --mutable-version v2 --index-dir .index

eval:
	python -m eval

gate:
	python -m gates

simulate:
	python -m eval.simulate_regressions

all: test
	@echo "TODO: full pipeline (ingest -> eval -> gate)"
