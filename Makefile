# You can use non-prefixed targets to run the project directly,
# or use the targets prefixed with `docker-` to build an image
# and run the corresponding target in a container.
#
# See the README for more information.

.PHONY: setup examples interactive show-deps \
		format test type-check \
		docker-build docker-examples docker-interactive docker-clean

PYTHON ?= python3
DOCKER ?= docker
BLACK ?= black
MYPY ?= mypy
PYTEST ?= pytest

PYTEST_OPTS ?=
IMAGE ?= localhost/tracker

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
	$(PYTHON) pip install -e .[test,dev]

examples:
	$(PYTHON) src/driver.py < examples/example-commands.txt
	$(PYTHON) src/driver.py < examples/invalid-commands.txt

interactive:
	$(PYTHON) src/driver.py

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
.imagebuilt: $(PYDEPS) Dockerfile
	$(DOCKER) build -t $(IMAGE) .
	touch $@

docker-examples: .imagebuilt
	$(DOCKER) run --rm -i $(IMAGE) < examples/example-commands.txt
	$(DOCKER) run --rm -i $(IMAGE) < examples/invalid-commands.txt

docker-interactive: .imagebuilt
	$(DOCKER) run --rm -it $(IMAGE)

docker-test: .imagebuilt
	$(DOCKER) run --rm -it $(IMAGE) pytest $(PYTEST_OPTS)

# Remove the sentinel file.
docker-clean:
	-rm .imagebuilt

