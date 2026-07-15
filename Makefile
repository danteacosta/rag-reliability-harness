.PHONY: test ingest eval gate simulate all

test:
	python -m pytest -v

ingest:
	@echo "TODO: ingest corpus into index"

eval:
	@echo "TODO: run retrieval/answer evaluation"

gate:
	@echo "TODO: enforce reliability gate thresholds"

simulate:
	@echo "TODO: simulate failure modes"

all: test
	@echo "TODO: full pipeline (ingest -> eval -> gate)"
