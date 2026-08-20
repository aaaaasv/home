# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0]

### Added

- Telegram bot (aiogram 3) with a Ukrainian interface, restricted to an allowlist of Telegram user ids
- Guided `/add` flow: name, photo, species, location, watering interval, last watering
- Care schedules per plant — watering, fertilizing, misting, repotting, rotating — each on its own interval,
  rescheduled from the moment care actually happened
- Daily care digest at a configurable time, listing due and overdue tasks with one-tap buttons
- Care attribution — every recorded event keeps who performed it, and a guard warns before the same care is
  recorded twice within `RECENT_CARE_GUARD_HOURS`
- Photo journal per plant, stored as Telegram file ids with an optional local copy on disk
- `/plants`, `/today`, `/history` commands and plant cards with inline actions
- SQLite persistence with Alembic migrations, Unit of Work and repositories
