PYTHON := ./venv/bin/python
# your own host and path belong in Makefile.local, which is gitignored:
#   PI := pi@192.0.2.10
-include Makefile.local
PI ?= pi@raspberrypi.local
REMOTE_DIR ?= /opt/bots/home-bot
BACKUP_FILE := backups/home-$(shell date +%F).db

.PHONY: install lock migrate run test lint deploy logs restart backup

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

# ship the working tree to the pi and restart — .env and data/ are never touched
deploy:
	rsync -az --delete \
	  --exclude 'venv/' --exclude '.git/' --exclude '__pycache__/' --exclude '*.pyc' \
	  --exclude 'data/' --exclude 'photos/' --exclude '*.db' --exclude '.env' --exclude 'backups/' \
	  --exclude '*.key' --exclude '*.password' \
	  ./ $(PI):$(REMOTE_DIR)/
	ssh $(PI) 'cd $(REMOTE_DIR) && docker compose up -d --build'

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
