# home

A self-hosted home system. Its interface today is one Telegram bot in the family group chat, thirteen
domain modules — plants, shopping, chores, climate, power, transit — in a single asyncio process on a
Raspberry Pi, against one SQLite file. No cloud, no vendor apps, no account for anyone to create.

**The bot is one of four layers, not the point of the exercise** — which is why this repository is not
called `home-bot`. The power chain, the Zigbee network and the service stack are peers, and the layers below
the interface matter more than it does. `docs/vision.md` is the system as a whole and where each piece belongs.

The family talks to it in Telegram and nowhere else. That constraint is the whole design.

## Read this before cloning it

**This is one household's bot. Fork it, don't install it.** It expects a Ukrainian-speaking family, a
Telegram forum supergroup, a Gree air conditioner at a fixed address, an EcoFlow Delta 2 on Bluetooth, an
SHT31 on the Pi's i²c bus, an ASUS router, Kyiv's transit feed and Yasno's outage schedule. Nobody else has
that exact house. Every one of those is optional and off by default — but with them off, what remains is a
plant tracker and a shopping list.

**The interface is Ukrainian**, and deliberately stays that way. Roughly 450 lines of 14 500 are Cyrillic,
all of it in `src/bot/`, so translating is cheap — but a translated bot still has no Yasno, no hotline.ua,
no Kyiv transit and none of the hardware. It would be an English-language bot for a Ukrainian household's
appliances, which serves nobody. Code, comments, commits and domain errors are all English; only what the
family reads is not.

**What is worth taking is below, not above.** The five rules are the transferable part, and they apply to a
codebase sharing no line with this one.

---

## Design rules

Five rules the codebase is built around. They are not style preferences — breaking one has broken
something real before, and each cost more to learn than to read.

**1. A push must usually be empty.** A module earns a scheduled message only if that message is normally
silent. An always-non-empty list that speaks every morning is the notification that gets the whole group
muted, and a muted group takes the plant digest down with it. Everything else is pull: a command, a board,
a button. Push is scarce; pull is free.

**2. The topic is the namespace.** The group is a forum, and `/add` means "add a plant" only because the
plants router listens inside the plants topic. Module commands stay short and unprefixed. A module whose
topic is unresolved answers *nothing* — waving commands through would hand `/add` to whichever router was
included first.

**3. Buttons are never filtered by topic.** A `CallbackData` payload names its own module in its prefix, so
it is already unambiguous. Filtering it by topic would break every button posted outside its own topic.

**4. Nothing may depend on one long-lived message.** A bot may edit its own message for 48 hours, then
`MESSAGE_EDIT_TIME_EXPIRED`. A self-editing card is only safe if it is reposted more often than that —
which is why the weather digest may carry a refresh button and the air-conditioner controls may not.

**5. Ukrainian lives only in the delivery layer.** Domain errors carry English detail for logs;
`src/bot/errors.py` maps the exception to what a person reads.

---

## What it does

Each module lives in its own forum topic. **The topic names are yours to choose** — they are configuration,
not code, so nothing here assumes what you call them.


| Module | |
|---|---|
| `plant_care` | Per-plant schedules (watering, fertilizing, misting, repotting). A daily digest names what is due; one tap records who did it and reschedules from the moment care actually happened. Photo journal with AI review of what changed |
| `shopping` | One list, split into this-trip and someday. Adding an item takes no command — plain text is the interface. Deliberately has no digest. `/track` watches a hotline.ua price and pings on a new low |
| `chores` | A silent to-do pile. An item with no date never speaks; a date («до 31.07», parsed inline) turns it into one card that pings when the deadline enters its lead window, rewrites itself as the day turns, and is deleted the instant the chore is done |
| `weather`, `air_conditioner` | A morning digest about the hours still ahead — every line except the two temperatures is omitted when it has nothing to say. Refreshes itself in place every 15 minutes. `/ac` controls the air conditioner over the local Gree protocol |
| `power` | EcoFlow Delta 2 over local BLE, the Yasno outage schedule, and conservation advice during a blackout |
| `transit` | On-demand arrival times for a configured stop, from a positions-only GTFS-realtime feed |
| `system_health`, `presence` | Pi vitals, posted only when wrong. Presence reads who is on Wi-Fi from the router, to catch "everyone left and the AC is still on" |
| `assistant` | Grounded Q&A over a curated `home-knowledge.md`, with web search and vision |

---

## Architecture

Four layers. Which one a feature belongs to decides how it is built.

| Layer | What | Law |
|---|---|---|
| **1 · Power & network** | Grid, EcoFlow Delta 2, the ZUBR relay, the Pi's UPS, router, WireGuard, DNS | Everything above it is fiction when this is down. Must outlive a grid outage — that is the hour the family most needs it |
| **2 · Sense & act** | SHT31, Zigbee sensors, CO₂, presence, the air conditioner, lights, relays | Must work with no internet and no single service. A sensor disappearing makes the system quiet, not broken |
| **3 · Memory** | SQLite, photos, the self-hosted stack (Immich, Paperless, Memos, Karakeep, Vaultwarden) | Loss is unacceptable. Nothing is switched on until it is in a backup that has been restored at least once |
| **4 · Interface** | This bot, plus one admin board | The family never opens a browser. Anything needing a web UI is the operator's problem, not theirs |

The order is a dependency order, and **investment must follow it upward**. This project has gone the other
way: thirteen modules at layer 4, and at layer 1 the Pi still has no battery. During a blackout — precisely
when "коли буде світло" is the most valuable message in the house — the whole thing is off. Correcting that
imbalance outranks any new module.

### Layers

```
src/modules/<name>/          domain — no Telegram type may appear here
  commands.py                  pydantic inputs to use cases
  domain.py                    their outputs
  use_cases/                   one callable class per file; logic lives in __call__
  services/                    the module's collaborators

src/infrastructure/          SQLAlchemy models, repositories, the Unit of Work
  adapters/                  i2c, BLE, UDP and HTTP clients — the outside world, with no Telegram in it
src/bot/                     delivery — the role src/api/ plays in an HTTP service
src/common/                  config, time, shared base classes
src/vendor/                  vendored third-party code, read as a dependency not as source
```

`src/bot/` parses the update, calls one use case, renders the reply. It holds no business logic.
Dependencies reach handlers through aiogram's workflow data, the way `Depends` works in FastAPI.

**Time.** Everything is stored UTC through the `UtcDateTime` column type — SQLite keeps no offset, so it is
re-attached on read. A due date is a calendar day in the household timezone, and only `CareCalendar` may
convert between the two.

**Integer primary keys, not UUIDs.** Telegram caps `callback_data` at 64 bytes; a UUID plus an action plus a
task type does not fit. Every button payload is asserted under the cap.

### Adding a module

1. `src/modules/<name>/` — commands, domain, use cases
2. Tables in `src/infrastructure/db/models.py`, a migration, repositories on the Unit of Work
3. `src/bot/handlers/<name>/` — a package whose `__init__.py` composes one Router
4. Include the router in `src/bot/application.py`, filtered by `InModuleTopic` on its own
   `ForumTopicRegistry`, and add the module's section to `messages.WELCOME`
5. Register the command in `wrong_topic.MODULE_COMMANDS` and `main.GROUP_COMMANDS`

`start.router` must stay included first: `/cancel` has to win over any module's FSM state that swallows
plain text.

---

## Running it

```bash
make install        # venv + editable install with dev extras
make migrate        # alembic upgrade head
make run            # python -m src.main, against a local sqlite file
make test           # unittest, integration-first
make lint           # black, isort, flake8 via pre-commit
```

Integration tests run against an in-memory SQLite database built from the models, seeded through the real
Unit of Work with a frozen clock, so every due-date assertion is exact rather than relative to the wall
clock. There is no `conftest.py` — infrastructure lives in base classes and `asyncSetUp`.

## Configuration

Copy `.env.example` to `.env` and fill it in; it documents every variable inline. Copy
`home-knowledge.example.md` to `home-knowledge.md` for the assistant. Neither real file is ever committed.

Two things worth knowing before first run:

- **Disable privacy mode** in BotFather (`/setprivacy` → Disable), or the bot cannot see commands in a group.
- **Leave `TELEGRAM_ALLOWED_USER_IDS` empty at first.** The bot logs the id of everyone it ignores, so
  `make logs` hands you the ids to paste in.

Enabling topics upgrades a group to a supergroup, **which changes its chat id**. `verify_reminder_chat`
refuses to start on a dead id and prints the new one. It probes with `get_chat_member_count`, not
`get_chat` — on a migrated id `get_chat` quietly returns the stale basic-group record and reports no error
at all. After changing `.env`, the container needs `docker compose up -d --force-recreate`; `restart` does
not reload `env_file`.

## Deployment

```bash
make deploy     # rsync the working tree to the Pi, rebuild, restart
make logs
make backup     # snapshot the sqlite file through python's backup api (safe on a live db)
```

Runs as a Docker Compose service in `/opt/bots/home-bot`. `.env` and `data/` are never touched by a deploy.
The container runs as uid 1000 so the database stays writable and backup-able from the host.

> Deployment currently ships the **working tree**, not a tagged commit — untracked files land on the Pi and
> there is no way to say which version is running. Replacing this with a versioned image build is tracked in
> Linear.

## Repository hygiene

Runtime state (`data/`, `*.db`, `photos/`), credentials (`*.password`, `*.key`) and the household's own
facts (`home-knowledge.md`) are gitignored. They live in `../home-bot-vault/`, deliberately a sibling
directory — a `.gitignore` entry can be overridden with `git add -f`, a different directory cannot.

Two further repositories are nested in this folder and ignored by this one, the way `stats-api` nests
`trends-api` and `stats-infrastructure` — plain git repos, not submodules, so one editor window covers all
three and no history can leak between them:

| | |
|---|---|
| `home-docs/` | Floor plan, network layout, hardware research, the household reference. **Private, permanently** |
| `home-infrastructure/` | Compose stacks, Caddy, backup scripts and systemd units for both machines. **Private** — it is checked out on the servers |

This repository hardcodes no address, credential, coordinate, device MAC or chat id; every setting that
describes *a place* is required configuration with no default, and test fixtures use the
documentation-reserved ranges (RFC 5737, IANA). `docs/vision.md` stays here because it is architecture
rather than address.

Licensed MIT. `src/vendor/eflib/` is third-party Apache-2.0 code — see `src/vendor/eflib/VENDORED.md`,
which records that its provenance is **not yet established** and must be before this goes public.
