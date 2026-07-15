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
	@echo "TODO: simulate failure modes"

all: test
	@echo "TODO: full pipeline (ingest -> eval -> gate)"
