# You can use non-prefixed targets to run the project directly,
# or use the targets prefixed with `docker-` to build an image
# and run the corresponding target in a container.
#
# See the README for more information.

SHELL := /bin/bash
MAKEFLAGS += --warn-undefined-variables --no-builtin-rules
.PHONY: default \
		setup examples interactive test type-check \
		format show-deps \
		docker-build docker-examples docker-interactive docker-test docker-type-check \
		docker-clean

PYTHON ?= python3
DOCKER ?= docker
BLACK ?= black
MYPY ?= mypy
PYTEST ?= pytest

PYTEST_OPTS ?=
IMAGE ?= localhost/tracker

default: docker-test

# Dependencies.
DIRS := src tests
PYDEPS := pyproject.toml \
		  $(shell find $(DIRS) -not -name '.*' \
			  \( -type d -name '__pycache__' -prune \) \
			  -o -type f -name '*.py' -print )
show-deps:
	@printf "Dependencies:\n $(addsuffix \n,$(PYDEPS))"

##############################################################################
# Local targets (best run in a virtual environment).
##############################################################################

setup:
	pip install -e .[test,dev]

EXAMPLES := $(wildcard examples/*.txt)
.PHONY: $(EXAMPLES)
examples: $(EXAMPLES)
runner = $(PYTHON) src/driver.py
$(EXAMPLES):
	@printf "$(green)>>>> Running example '%q' <<<<$(clear)\n" "$(@F)"
	$(runner) < "$@"
	@printf "$(green)>>>> Done with example '%q' <<<<\n$(clear)" "$(@F)"

interactive:
	$(runner)

test:
	$(PYTEST) $(PYTEST_OPTS)

type-check:
	$(MYPY) src

format:
	$(PYTHON) -m isort --profile black --line-length=95 src/ tests/
	$(BLACK) src/ tests/

##############################################################################
# Docker targets.
##############################################################################

docker-build: .imagebuilt
.imagebuilt: $(PYDEPS) Dockerfile .dockerignore
	$(DOCKER) build -t $(IMAGE) .
	touch $@

DOCKER_RUN_ARGS = --rm -i
docker-%: runner = $(DOCKER) run $(DOCKER_RUN_ARGS) $(IMAGE)
docker-interactive docker-test docker-type-check: DOCKER_RUN_ARGS += -t
docker-interactive docker-examples: docker-%: docker-build %

docker-test: docker-build
	$(runner) $(PYTEST) $(PYTEST_OPTS)

docker-type-check: docker-build
	$(runner) $(MYPY) src

.IGNORE: docker-clean
docker-clean:
	docker image rm $(IMAGE)
	rm .imagebuilt

green = $(shell tput setaf 2)
clear = $(shell tput sgr0)

