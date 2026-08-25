PYTHON := ./venv/bin/python
# your own host and path belong in Makefile.local, which is gitignored:
#   PI := pi@192.0.2.10
-include Makefile.local
PI ?= pi@raspberrypi.local
REMOTE_DIR ?= /opt/bots/home-bot
BACKUP_FILE := backups/home-$(shell date +%F).db
BOT_IMAGE ?= ghcr.io/aaaaasv/home-bot
BOT_VERSION := $(shell cat VERSION)
GIT_SHA := $(shell git rev-parse --short HEAD)
# the pi and this machine are both arm64, so the build is native and the pi never compiles anything
PLATFORM ?= linux/arm64

.PHONY: install lock migrate run test lint build-prod tag-release deploy running logs restart backup

# the lock MUST be generated in the deployment image, not on your laptop: on macOS pip-compile
# resolves bleak's pyobjc dependencies, which cannot build on the pi and fail the deploy
lock:
	docker run --rm -v "$(PWD)":/w -w /w python:3.13-slim \
	  sh -c "pip install -q pip-tools && pip-compile --quiet --output-file=requirements.lock pyproject.toml"

install:
	python3 -m venv venv
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -e ".[dev]"
	# without this the hooks only run when invoked by hand, and `pre-commit run --all-files`
	# silently skips untracked files — so brand-new files reach a commit unformatted
	./venv/bin/pre-commit install

migrate:
	./venv/bin/alembic upgrade head

run:
	$(PYTHON) -m src.main

test:
	$(PYTHON) -m unittest discover -s src/tests/ -t .

lint:
	./venv/bin/pre-commit run --all-files

# the docker context is the working tree, so an uncommitted file would land inside the release image
build-prod:
	@git diff --quiet && git diff --cached --quiet || { echo "working tree is dirty; commit before building a release"; exit 1; }
	docker buildx build --platform $(PLATFORM) \
	  -t $(BOT_IMAGE):$(BOT_VERSION) \
	  -t $(BOT_IMAGE):$(BOT_VERSION)-$(GIT_SHA) \
	  --push .
	@echo "pushed $(BOT_IMAGE):$(BOT_VERSION) and :$(BOT_VERSION)-$(GIT_SHA)"

tag-release:
	@{ printf "Release v%s\n\n" "$(BOT_VERSION)"; awk -v v="$(BOT_VERSION)" '/^## \[/{p=($$0 ~ "\\["v"\\]")} p' CHANGELOG.md; } | git tag -a v$(BOT_VERSION) -F -
	git push origin v$(BOT_VERSION)

# no code travels: the pi is told which already-built image to run, and pulls it
deploy:
	ssh $(PI) 'cd $(REMOTE_DIR) \
	  && sed -i "s|^BOT_VERSION=.*|BOT_VERSION=$(BOT_VERSION)-$(GIT_SHA)|" .env \
	  && docker compose pull \
	  && docker compose up -d'
	@echo "running $(BOT_VERSION)-$(GIT_SHA)"

# what is actually running, read from the container rather than from a branch
running:
	@ssh $(PI) 'cd $(REMOTE_DIR) && docker compose images --format json' | python3 -c "import sys,json;[print(i[\"Repository\"]+\":\"+i[\"Tag\"]) for i in json.loads(sys.stdin.read() or '[]')]" 2>/dev/null \
	  || ssh $(PI) 'cd $(REMOTE_DIR) && docker compose images'

logs:
	ssh $(PI) 'cd $(REMOTE_DIR) && docker compose logs -f --tail 100'

restart:
	ssh $(PI) 'cd $(REMOTE_DIR) && docker compose restart'

# the pi has no sqlite3 cli, so the snapshot goes through python's backup api — it is safe on a live database
backup:
	@mkdir -p backups
	ssh $(PI) 'python3 -c "import sqlite3; source = sqlite3.connect(\"$(REMOTE_DIR)/data/home.db\"); destination = sqlite3.connect(\"/tmp/home-backup.db\"); destination.__enter__(); source.backup(destination); destination.close()"'
	scp $(PI):/tmp/home-backup.db $(BACKUP_FILE)
	@echo "saved $(BACKUP_FILE)"
