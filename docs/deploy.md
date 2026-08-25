# Deploy — how a version reaches the Pi

> **Статус:** збудовано · 2026-08-25

The Pi is production. There is no other environment, so there is no dev/prod split to maintain — one
stream, versioned the way a production service is versioned.

## The rule this replaces

Deploy used to `rsync` the working tree and build on the Pi. Two things were wrong with that. Uncommitted
and untracked files reached the Pi, so **what ran there had no name** — no tag, no commit, nothing to point
at when something broke. And the Pi spent five to ten CPU-heavy minutes compiling, on the machine that is
least able to spare them and most disruptive to restart.

Now the image is built here, pushed to a private registry, and pulled there.

## Two tags, and why the second one matters

```
ghcr.io/aaaaasv/home-bot:0.1.0
ghcr.io/aaaaasv/home-bot:0.1.0-a1b2c3d
```

The version tag is convenient; the sha-pinned tag is **immutable**. If a version tag is ever pushed twice —
and it will be, sooner or later — the version tag no longer identifies a build and the sha-pinned one still
does. `make deploy` writes the sha-pinned tag into the Pi's `.env`, so the answer to "what is running" comes
from the container, never from a branch.

## Ordinary deploy

```bash
make test
make lint
git status                  # must be clean: the docker context is the working tree
make build-prod             # native arm64 — this machine and the Pi are both arm64
make deploy                 # pins the tag in the Pi's .env, pulls, restarts
make running                # what the Pi actually has
```

`make deploy` moves no code. It tells the Pi which already-built image to run.

## Release

Bump `VERSION`, fold `## [Unreleased]` into a dated section in `CHANGELOG.md`, merge `develop` into `main`
with `--no-ff`, then:

```bash
make tag-release            # tags vX.Y.Z with the changelog section as the tag body
```

## Building locally

The deployed compose file has no `build:` on purpose, so nothing on the Pi can quietly compile. To build on
this machine instead:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

## Registry access

This machine pushes with a token that already exists. **The Pi must not use it** — that token carries
`repo` scope, which is full access to every private repository, and the Pi is the machine most exposed and
least worth trusting with a credential that broad. The Pi gets its own classic token with **`read:packages`
and nothing else**:

```bash
ssh <pi> 'echo <token> | docker login ghcr.io -u <user> --password-stdin'
```

## Migrations

`entrypoint.sh` runs `alembic upgrade head` on start, so a deploy migrates itself. That is the same choice
`trends-api` makes and the opposite of `stats-api`, which migrates by hand — worth knowing when reading
either as a reference.
