#!/usr/bin/env bash
# refuse to stage anything that identifies this household or unlocks something.
# .gitignore is the first line of defence; this is the one that survives `git add -f`
set -euo pipefail

blocked=()
for path in "$@"; do
  case "$path" in
    *.password|*.key|.env|home-knowledge.md|*.db|*.db-shm|*.db-wal) blocked+=("$path") ;;
    data/*|backups/*|photos/*|saved-export/*) blocked+=("$path") ;;
  esac
done

if [ ${#blocked[@]} -gt 0 ]; then
  echo "refusing to commit private files:" >&2
  printf '  %s\n' "${blocked[@]}" >&2
  echo >&2
  echo "credentials and runtime state belong in ../home-bot-vault/, not in git history." >&2
  echo "if this is a template, name it *.example.* instead." >&2
  exit 1
fi
