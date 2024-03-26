# The targets in this Makefile should be run within a virtual environment.
# To create one, use `python3.11 -m venv /path/to/venv && source /path/to/venv/bin/activate`.

.PHONY: dev format test type-check

# Setup a dev environment. 
dev:
	pip install -e .[dev]

PYTEST_OPTS ?=
test:
	cd src && python -m pytest $(PYTEST_OPTS) ../tests

type-check:
	mypy --show-absolute-path src

format:
	python -m isort --profile black --line-length=95 src/ tests/
	black src/ tests/

