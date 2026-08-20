# eflib — vendored

An EcoFlow BLE protocol library, copied into this tree rather than installed as a dependency. This project
uses two symbols from it — `NewDevice` and `DeviceBase` — via `src/bot/services/ecoflow_ble_station.py`.

## Provenance

| | |
|---|---|
| Upstream | **https://github.com/rabits/ha-ef-ble** — *Unofficial EcoFlow BLE Home Assistant integration* |
| Path there | `custom_components/ef_ble/eflib/` |
| Licence | **Apache-2.0.** The `LICENSE` beside this file is upstream's own, byte-identical |
| Version | `main`, between **v1.0.3** and **v1.0.4** |
| Contains | `c63665394` (2026-07-24) *"Add energy monitoring mode select for STREAM devices (#411)"* |
| Does not contain | `fdc51b7e9` (2026-08-16) *"Route every device packet through a connection-aware send helper"* |
| Local modifications | **None** |

Established 2026-08-20 by diffing the whole tree against each upstream release: identical to v1.0.3 in all
100 files except `devices/stream_ac.py`, whose extra code is upstream's `EnergyMonitoringMode` for STREAM
devices — hardware this household does not own, so it cannot be a local edit. Upstream ships no `NOTICE`
file, so there is none to reproduce.

### One oddity, so nobody trips over it

Upstream's `LICENSE` contains `Copyright 2013-2017 Docker, Inc.` at line 178. That is inside the Apache
appendix, and it is there because the file was copied from Docker's repository with its example copyright
line intact. It is upstream's boilerplate artefact, **not** a claim that Docker owns this code. The
copyright holders are rabits and the ha-ef-ble contributors.

## Apache-2.0 compliance

§4 requires retaining the licence and copyright notices and **stating whether the files were changed**.
They were not. Redistribution is therefore clean: keep `LICENSE` beside the code, keep this file, and say
plainly that the tree is unmodified.

## What it costs

It forces the runtime for the whole project. From `pyproject.toml`:

> `# eflib uses PEP 695 generics + typing.TypeIs → needs 3.13`

A driver for one battery is why the bot requires Python 3.13, when Raspberry Pi OS ships 3.11. It also
brings `bleak-retry-connector`, `protobuf`, `pycryptodome` and `ecdsa`, and `eflib/__init__.py:7` does
`from . import devices`, loading all 41 device modules and their generated protobuf stacks at import time
on a 4 GB Pi.

`docs`-side note: `home-docs/lighting-plan.md` records «Прошивку Delta 2 не оновлювати — зламає eflib»,
a behavioural contract now pinned to a version that can finally be diffed.

## Why it stays vendored

Pinning it as a dependency was the obvious answer and it does not work. Upstream's `pyproject.toml`:

- has **no `[build-system]` table**, so nothing can build it into an installable distribution;
- declares `packages = ["custom_components.ef_ble"]`, so even if built it would install under that name,
  not as `eflib`;
- and sets **`requires-python = ">=3.13"` itself**, so pinning would not lower this project's floor either.
  The 3.13 requirement is upstream's own, not a consequence of vendoring.

Installing it would therefore mean maintaining a fork purely to add packaging metadata — more work than
copying the tree, and a standing obligation to rebase.

So: keep the copy, keep it unmodified, keep this file accurate. That is a legitimate resting place, not a
compromise.

Upgrading past `fdc51b7e9` is not free either — it renames the send path (`_conn.sendPacket` →
`send_packet`), which `ecoflow_ble_station.py` would have to follow.

Linting already excludes this tree (`.pre-commit-config.yaml`: `exclude: '^src/vendor/'`), which is right:
it is a dependency, not source.
