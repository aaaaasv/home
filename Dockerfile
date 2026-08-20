FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# install dependencies against a stub package, so editing source does not rebuild this layer. entrypoint runs
# `python -m src.main` from /app, so only the dependencies matter here — the stub is thrown away right after.
# greeclimate pulls netifaces, which ships no arm wheel and must be compiled: bring the toolchain in and drop it
# again inside the same layer, so the compiler never reaches the final image
# requirements.lock pins every transitive version, so two builds a month apart install the same tree.
# without it a fresh `pip install .` resolves whatever PyPI is serving that minute, on the machine that is
# hardest to debug. regenerate with: pip-compile --output-file=requirements.lock pyproject.toml
COPY pyproject.toml requirements.lock ./
RUN mkdir -p src \
    && touch src/__init__.py \
    && apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev \
    && pip install --no-cache-dir -r requirements.lock \
    && pip install --no-cache-dir --no-deps . \
    && apt-get purge -y gcc python3-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* src

COPY src ./src
COPY migrations ./migrations
# glob, not a literal: home-knowledge.md is gitignored, so a clean clone only has
# the example. entrypoint falls back to it when the real file is absent
COPY alembic.ini entrypoint.sh ./
COPY home-knowledge*.md ./
RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
