#!/bin/sh
set -e

# a clean clone has no home-knowledge.md — run on the example so the assistant
# answers "I do not know" instead of crashing on a missing file
if [ ! -f home-knowledge.md ] && [ -f home-knowledge.example.md ]; then
    cp home-knowledge.example.md home-knowledge.md
fi

alembic upgrade head
exec python -m src.main
