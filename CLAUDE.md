# CLAUDE.md

Guidance for Claude Code working in this repository. `README.md` carries the same architecture as prose for
a human reader; this file is the authority on what you must do.

# Task tracking

Bugs, features and improvements live in **Linear** (workspace `rii`, team `homeserver`, prefix `HOM-`) —
never in markdown files. Do not create `TODO.md`, `BUGS.md`, `IMPROVEMENTS.md` or similar. Use the
`linear-home` MCP server; `linear` is a different account and a different workspace.

Verify against the current code before filing something as open, and before closing something as done. A
checkbox in a document is not evidence.

`docs/` is for design and reference, not for work items. Every document carries a status line as its first
line after the title:

```
> **Статус:** збудовано · 2026-08-18
```

One of `збудовано` (describes what runs), `довідник` (living reference: topology, hardware to buy),
`вирішено` (research that reached a decision, kept for the reasoning), `дослідження` (open question, nothing
built), `архів` (superseded). A document without a status line is a bug.

# Repository hygiene

Nothing that identifies this household or unlocks anything may enter git history. The first commit is
permanent, so this is checked before adding, not after.

Never committed, in `.gitignore`, and physically kept in `../home-bot-vault/` (a sibling directory, because
a `.gitignore` entry can be overridden with `git add -f` and a different directory cannot):

- `.env`, `data/`, `backups/`, `photos/`, `*.db` — runtime state
- `*.password`, `*.key` — credentials
- `home-knowledge.md` — names the address and the daily routine; commit `home-knowledge.example.md` instead

The code is written to open-source standards even though the repository is private: no address, credential,
device MAC, chat id or coordinate is hardcoded anywhere, and test fixtures use the documentation-reserved
ranges (`192.0.2.0/24` from RFC 5737, `00:00:5E:00:53:xx` from IANA). Anything a deployment needs to know
about *this* home is an environment variable with an inline comment in `.env.example`.

The repository stays private because `docs/` describes a specific home — floor plan, devices, network,
when nobody is in. That is a physical-security document, not a portfolio piece.

# Branching and releases

`main` is what runs. `develop` is where work integrates. Feature branches come off `develop` and merge
back; `develop` merges to `main` only as a release.

```bash
git checkout -b <short-descriptive-branch> develop
# ... work, with tests ...
git checkout develop && git merge --no-ff <branch>
```

**Commit messages are one line.** Imperative, capitalized, no trailing period, no body, no trailers —
the reference project's style: `Fix export staying in progress when a requested column no longer exists`,
`Bump version to 0.0.17`. Never mention Claude or AI assistance and never add a `Co-Authored-By` trailer;
the history reads as the author's own.

A release bumps `VERSION`, folds `## [Unreleased]` into a dated `## [X.Y.Z]` section in `CHANGELOG.md`,
merges `develop` into `main` with `--no-ff`, and tags `vX.Y.Z` with the changelog section as the tag body.
Semantic versioning; the changelog is written for the family, not for git.

Every change lands with its `CHANGELOG.md` line under `## [Unreleased]` in the same commit. A version is
never reused — the tag would point at a different tree than the one already running.

**Deploy runs from a clean worktree.** `make deploy` rsyncs the working tree, so uncommitted and untracked
files reach the Pi. `git status` must be clean before deploying, and the deployed commit must be tagged or
at least recorded.

# Architecture

## Four layers

This repository is the **interface layer** of a larger home system. It is not the centre of it. Every piece
of work — a bot module, a Zigbee dongle, a UPS HAT — belongs to exactly one layer, and each layer has a
different law. Something that fits none is not a feature, it is a separate project.

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

## Alarm path or convenience path

The second question, and the one that decides how much redundancy something earns.

| Path | Value is realized… | What it earns |
|---|---|---|
| **Alarm** | during a failure — power loss, smoke, a leak, "everyone left and the AC is on", DNS down | Its own battery, redundancy, hardware budget. Must survive the failure of everything above it |
| **Convenience** | on an ordinary day — media, archive, assistant, transit, shopping, prices, lighting scenes | Zero redundancy, and that is correct. A blackout that stops Jellyfin is not an incident |

Before building anything, answer: which layer · which path · does it satisfy that layer's law · is it push
or pull · what happens when the internet, the service, the sensor, or **the electricity** disappears.

`docs/vision.md` is the canonical version of this, with worked examples, the never-build list, and the
phased path. Read it before proposing anything structural.

## The five rules

**1. A push must usually be empty.** A module earns a scheduled message only if that message is normally
silent. An always-non-empty list that speaks every morning gets the group muted, and a muted group takes the
plant digest down with it. Everything else is pull: a command, a board, a button.

**2. The topic is the namespace.** The group is a forum. `/add` means "add a plant" only because the plants
router listens inside the plants topic, so module commands stay short and unprefixed. `InModuleTopic`
(`src/bot/filters.py`) is applied to a module's top-level router in `application.py`; aiogram checks a
router's own filters before descending into sub-routers, so one filter gates the whole module. A module
whose topic is unresolved answers **nothing**.

Three consequences, each load-bearing:

- **Private chats have no topics, so no module answers there.** `wrong_topic.router`, included after every
  module, catches the orphaned command and points back to the group.
- **The command menu cannot be scoped to a topic.** `BotCommandScope` reaches a chat or a member, never a
  thread. A shared command's description must hold in every topic ("додати запис у цьому топіку", not
  "додати рослину").
- **The FSM is scoped `FSMStrategy.USER_IN_TOPIC`**, so a flow started in one topic cannot swallow text
  typed in another.

**3. Buttons are never filtered by topic.** A `CallbackData` payload names its own module in its prefix, so
it is already unambiguous; filtering by topic would break every button posted outside its own topic.
Callbacks pass only `HasAccessibleMessage`, because Telegram replaces the message of a callback it can no
longer reach with an `InaccessibleMessage` that has no `message_thread_id` and cannot be edited.

**4. Nothing may depend on one long-lived message.** A bot may edit its own message for 48 hours, then
`MESSAGE_EDIT_TIME_EXPIRED`. A self-editing card is safe only if it is reposted more often than that — the
weather digest may carry a refresh button because it is reposted daily; air-conditioner controls may not,
so `/ac` lives on its own card.

**5. Ukrainian lives only in the delivery layer** (`src/bot/`). Domain errors carry English detail for logs;
`src/bot/errors.py` maps the exception to what a person reads.

## Layers

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
src/vendor/                  vendored third-party code; read as a dependency, never edited as source
```

- **Use cases** are callable classes; logic lives in `__call__`, one per file.
- **A module earns use cases only when it remembers something.** `presence`, `system_health` and `weather`
  own no table and never open a Unit of Work: they read a sensor or an API, decide, and hand the answer
  straight back. A use case there would be a one-line pass-through to a service, which reads worse than the
  call it wraps. Their logic lives in a monitor or a service with its own unit tests. The moment such a
  module has to remember anything between readings it gains a table, a repository and use cases like the
  rest — `power` is exactly that story, and its state machine belongs in
  `src/modules/power/use_cases/`, not in the job that calls it.
- **Unit of Work** (`uow`) wraps database access as an async context manager and exposes repositories as
  attributes.
- **Handlers parse the update, call one use case, render the reply.** They hold no business logic.
  Dependencies reach them through aiogram's workflow data, the way `Depends` works in FastAPI.
- **A module is named for what it is about, not for who asked for it first.** Room climate was born inside
  `plant_care` because plants needed it, and then the air conditioner and the weather digest had to import
  from the plants to read the air. It is `room_climate` now. Same rule for adapters: anything that talks to a
  vendor — an HTTP client and the code that reads that vendor's payload shape — belongs in
  `src/infrastructure/adapters/`, so a changed response stops there instead of reaching the domain.
- **A module owns its own delivery code.** Rendering, keyboards, message text and scheduled jobs for a
  module belong in `src/bot/handlers/<name>/`, not in a shared file. `src/bot/formatting.py` and
  `messages.py` hold only genuinely cross-module primitives; `reminders.py` holds only the scheduler
  assembly. Adding a module must not mean editing four shared files. There is no shared `keyboards.py`:
  every button belongs to exactly one module.
- **A module schedules its own work.** `src/bot/handlers/<name>/jobs.py` exposes one
  `register_jobs(scheduler, context)`; `reminders.py` only collects those registrations, and
  `SchedulerContext` (`src/bot/scheduling.py`) carries whatever the composition root built. A module reads
  its own settings flag there and registers nothing when it is switched off, so a cadence, a trigger and an
  enabling flag never live in a shared file. `src/tests/unit/test_architecture.py` fails if a `jobs.py`
  goes uncollected, if anything outside a `jobs.py` calls `add_job`, or if a shared delivery file starts
  importing from one module.
- **Time**: everything is stored UTC through the `UtcDateTime` column type — SQLite keeps no offset, so it
  is re-attached on read. A due date is a calendar day in the household timezone, and only `HouseholdCalendar`
  may convert between the two.
- **Integer primary keys, not UUIDs.** Telegram caps `callback_data` at 64 bytes; a UUID plus an action plus
  a task type does not fit. Every button payload is asserted under the cap.
- **`BaseActorUseCase` carries an `Actor`, not a user id.** Care is attributed to a Telegram user, and the
  display name is denormalized onto `care_events` so history keeps the name as it was at the time.

## Adding a module

1. `src/modules/<name>/` — commands, domain, use cases. No Telegram types.
2. Tables in `src/infrastructure/db/models.py`, a migration, repositories on the Unit of Work.
3. `src/bot/handlers/<name>/` — a package whose `__init__.py` composes one Router from its handler files,
   and which owns its own formatting, keyboards, messages and jobs.
4. Include the router in `src/bot/application.py`, filtered by `InModuleTopic` on its own
   `ForumTopicRegistry`, and add the module's section to `messages.WELCOME`.
5. Register any new command in `wrong_topic.MODULE_COMMANDS` and `main.GROUP_COMMANDS`.
6. If it has scheduled work, add its `register_jobs` to `reminders.JOB_REGISTRARS`.

`start.router` must stay included first: `/cancel` has to win over any module's FSM state that swallows
plain text.

## Operational facts that have cost time before

- **Enabling topics upgrades a group to a supergroup, which changes its chat id.** This once cost days of
  silent digests. `verify_reminder_chat` (`src/bot/preflight.py`) refuses to start and prints the new id. It
  probes with `get_chat_member_count`, not `get_chat` — on a migrated id `get_chat` quietly returns the
  stale basic-group record with `is_forum` false and reports no error at all.
- After changing `.env`, the container needs `docker compose up -d --force-recreate`. `restart` does not
  reload `env_file`.
- `ForumTopicRegistry` resolves before polling starts, because the filter reads the resolved id on every
  update. The Bot API can create a topic but cannot list them, so the bot only recognises the one it made.
- `message.answer()` and `callback.message.answer()` carry `message_thread_id` automatically. Only messages
  the bot originates — digests, job cards — must pass it explicitly, or they land in General.
- The Pi is not a git checkout. `make deploy` rsyncs; `entrypoint.sh` runs `alembic upgrade head` on start.

# Commands

```bash
python -m unittest discover -s src/tests/ -t .          # all tests
python -m unittest discover -s src/tests/integration/ -t .
python -m unittest src.tests.integration.test_record_care_event.RecordCareEventTestCase
pre-commit run --all-files                              # lint and format check
alembic upgrade head
alembic revision --autogenerate -m "description"
python -m src.main
```

Use `./venv/bin/python`, not the system interpreter — the system one lacks `aiogram`, `smbus2` and
`greeclimate`, and the suite reports 40 spurious errors.

# Code style

## Formatting

- **Formatter**: Black, line length 120
- **Import sorting**: isort with Black profile, line length 120
- **Linter**: flake8, max line length 120
- **Imports**: all imports at the top of the file — never inside functions, methods, or classes
- Run `pre-commit run --all-files` before committing

## Naming

- Use full words — no abbreviations or contractions in any identifier
- Allowed exception: `uow` (unit of work — established convention throughout the codebase)
- Allowed exception: `data` for a use case or handler input parameter whose type annotation already names
  the contents
- Names must describe the contents, not just the type — a reader must understand what's inside without
  looking elsewhere
- Bad: `results`, `data`, `items`, `rows` (when the type alone is clear from context)
- Functions and methods are verbs — name them with a verb phrase, never a bare noun
- Good: `build_digest_keyboard`, `record_care_event`, `list_due_with_plants`
- Bad: `digest_keyboard`, `care_event`, `due_schedules` (reads like data, not an action)
- Variables and attributes stay nouns — the verb rule is for callables only

## Design

- Follow SOLID, and prefer the simple readable shape over the clever one. A use case does one thing; a
  service has one reason to change; a handler does not know how the database works.
- Do not split a function into helpers that are each called once and read worse than the original. Split
  when a piece has its own name, its own reason to exist, or its own test.
- Domain code depends on abstractions (`PhotoStorage`, `KnowledgeSource` are protocols), never on aiogram,
  SQLAlchemy or `httpx`.
- If a module needs another module's data, it goes through a use case, not through its repository.

## Testing

- Integration tests are the top priority — always write integration tests first; add unit tests only when
  integration tests are insufficient to cover the logic
- Test method naming: `test_{action}_{condition}_{expected_outcome}` — all three parts, lowercase with
  underscores
- Good: `test_record_care_event_within_the_guard_window_raises_recent_care_exists`,
  `test_create_plant_with_unknown_last_watering_is_due_today`
- Bad: `test_records_event`, `test_guard_window` (missing the action/subject)
- Test body structure: `{prepare}` — empty line — `{call}` — empty line — `{check}`. One blank line between
  each block; no blank lines inside a block. The call block is a single statement (or a single `with` for
  expected exceptions)
- Asserting on errors: an exception type alone is not enough — always assert the full message text
  (`str(context.exception) == "..."`), not a substring
- Be explicit, not defensive, in assertions. Assert exact values and exact lists; a test that tolerates
  partial matches hides regressions
- Tests use `unittest.IsolatedAsyncioTestCase` and class-based organization. No `conftest.py`, no pytest
  fixtures — infrastructure lives in base classes and `asyncSetUp`/`asyncTearDown`. Integration tests run
  against in-memory SQLite built from the models, seeded through the real Unit of Work with a frozen clock
  (`FrozenHouseholdCalendar`), so every due-date assertion is exact rather than relative to the wall clock
- Fixtures never carry real identifiers — use the documentation-reserved ranges

## Error handling

- Do not add defensive fallbacks everywhere — understand the actual data flow and handle the one real
  scenario
- Fallbacks are acceptable when justified (a Telegram photo download failing, an external API being down),
  but not as a default habit
- Trust internal code contracts; if a function is only called with valid data, don't guard against invalid
  data inside it

## Comments

- **A note about the callable is a docstring; a note about the surrounding code is a comment.** If it says
  what a function is for or when it is reached, it belongs inside as a docstring. If it says something about
  the code *around* it — the order two decorators are registered in, what a filter excludes, a workaround at
  this line — it stays a comment above. A handler carrying both gets both:

```python
# commands are excluded, or a mistyped /list here would land on the list as a chore called "/list"
@router.message(F.text, ~F.text.startswith("/"))
async def add_chore(...) -> None:
    """Plain text is the whole point: saving a chore must be cheaper than remembering it."""
```

- Docstrings start with a capital and end with a period; comments do neither
- Default to no comment — write code, not prose about code
- Prefer self-explanatory code over comments — if the code needs a comment to be understood, consider
  renaming or restructuring first
- Before writing a comment, check the intent isn't already obvious from a name, type, or test — if it is,
  don't write it
- When a comment genuinely adds value (non-obvious intent, algorithmic reasoning, workarounds), write it —
  one short line, not a paragraph
- Style: lowercase, no leading capital letter, no trailing period, imperative form
- Avoid semicolons joining two clauses into one comment — keep one idea per comment, or split across two
  short lines
- Good: `# sqlite keeps no offset, so re-attach utc on read`
- Bad: `# Re-attaches UTC on read.`
- Bad: `# re-attach utc on read; sqlite keeps no offset`
