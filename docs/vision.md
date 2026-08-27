# The home system — what it is and where things go

> **Статус:** довідник · 2026-08-24

The canonical document. `README.md` describes the bot; this describes the system the bot is one part of.

---

## What it is

> **A household that notices things and tells you only when it matters, and that keeps noticing when the
> grid, the ISP, or a vendor's cloud goes away.**

Two doctrines carry that sentence, and both are already applied consistently:

**Silence by default.** A scheduled message earns its place only if it is normally empty. An always-full
list that speaks every morning is the notification that gets the group muted, and a muted group takes the
alarms down with it.

**Nothing depends on a vendor.** Gree over local UDP, EcoFlow over BLE, Open-Meteo without a key,
Zigbee2MQTT rather than Home Assistant. Every one of those was chosen deliberately, and each has already
outlived some cloud that would have been the alternative.

The Telegram bot is one **interface** to this system, the way Caddy and the web UIs are the interface to the
archive. Naming it that way answers most placement questions on its own.

---

## Where anything goes: two questions

### 1. Which path is it on?

| Path | Value is realized… | What it earns |
|---|---|---|
| **Alarm** | during a failure — power loss, smoke, a leak, "everyone left and the AC is on", DNS down | Its own battery. Redundancy. Hardware budget. It must survive the failure of everything above it |
| **Convenience** | on an ordinary day — media, archive, assistant, transit, shopping, prices, lighting scenes | Zero redundancy, and that is correct. A blackout that stops Jellyfin is not an incident |

The path decides which machine it runs on, whether it gets a battery, and whether it may depend on the
laptop, the internet, or a subscription.

### 2. Which layer is it in?

Arrows point downward only. Nothing may depend on something above it.

| | Layer | Today | Rule |
|---|---|---|---|
| **L0** | Power | Grid, Delta 2, the router's UPS, X728 (not yet fitted), the laptop's own battery | Alarm-path devices each get their own battery — never a shared one someone can unplug |
| **L1** | Network | ASUS router, provider line, pi-hole DNS, WireGuard + DDNS | Must not depend on any single compute node. **Today it does** — see HOM-36 |
| **L2** | Compute | Pi (always on, low-watt), laptop (heavy, stateful). No cloud tier | Pi = alarm path. Laptop = convenience path. **Today both are wrong** — see HOM-35 |
| **L3** | Buses | I²C (SHT31), BLE (Delta 2), UDP (Gree), HTTP (router, Yasno, Open-Meteo), Zigbee/MQTT arriving | Every bus terminates in an adapter with a null fallback. Already the pattern — keep it |
| **L4** | Data | Bot SQLite, two archive Postgres, restic local + offsite | A store without a scheduled, **restore-tested** backup does not exist |
| **L5** | Logic | 13 bot modules, later Z2M automations | Edge-triggered, silent by default |
| **L6** | Interface | Telegram topics, the web UIs, maybe Siri later | Interchangeable. An interface must never own domain logic |

**Worked examples.** A soil-moisture sensor: convenience, L3→L5, on the Pi, no battery beyond its own cell.
A CO detector: **alarm** — which is exactly why the standalone screaming box must exist before the Zigbee
one, since the Zigbee version inherits every dependency in the stack.

---

## The imbalance, stated plainly

Thirteen software modules at L5. No battery at L0.

The single most valuable message this system could send — «світло зникло» — is the one it cannot send,
while the thirteenth module shipped and then sat behind a feature flag. The Pi is the nervous system (bot,
DNS for the entire flat, Uptime Kuma, and the far end of an SSH tunnel a **day job** depends on), and it
runs from an SD card with no UPS and, until today, no commits.

The problem is not that there are too many modules. Modules are cheap under this doctrine and most of them
earn their keep. The problem is that **survivability and recoverability lag behaviour by about six months.**

The Pi's contested role is worth naming, and it is heavier than an earlier draft of this section claimed.
The Pi hosts **no proxy software at all**, which was the useful half of that draft. What it does host is a
systemd unit holding an *outbound* SSH connection open, with `Restart=always`, so that a day job's traffic
can leave from a residential address.

The tunnel is therefore the Pi's own responsibility, not the far end's, and the practical consequence is a
cost that does not look like one: after a reboot the remote side keeps the forwarded port bound by the dead
session, and ssh refuses to idle without its forward — so it exits and systemd retries until the far side
reaps the stale listener. Measured once at close to an hour. **A planned restart costs up to an hour of
tunnel downtime rather than the seconds the reboot takes**, and nothing alerts on it.

That is an argument for batching Pi work into one window. The fix belongs on the far side and is recorded
with the rest of the operational detail, which does not live in this repository.

The sharper version of the same problem is the other machine: layer 3's law says loss is unacceptable, and
it is currently served by a laptop that gets switched off — so backups do not run and the archive is
unreachable for most of the day.

---

## Never build

Written down so it does not get re-litigated every six months.

- **Home Assistant.** Its EcoFlow path is cloud; ours is BLE. It would duplicate the bot's judgment layer
  and hand the family a second interface to learn. Revisit only if a second person needs to author
  automations.
- **A second Telegram bot.** In a group, both bots receive every `/` command.
- **Recurring chores.** Plant care's schedule engine already is one.
- **Cameras or an NVR on the Pi.**
- **A stationary battery system in the rented Kyiv flat.** Central heating removes the need.
- **Anything whose only trigger is a vendor cloud** (Tapo-class hardware).

---

## The path

Each phase has an exit **test**, not a task list. A phase is done when the test passes.

**Phase 0 — Survive.** Fit the X728 and batteries. Ship power-loss detection on GPIO. Buy the standalone
CO/smoke detector. Bring Immich, Paperless, Memos and Karakeep — with `pg_dump` for the two Postgres — into
restic, and migrate off the Google Drive target before it goes read-only.
→ **Test:** flip the breaker for ten minutes. The family gets «світло зникло» and «світло з'явилось», and a
restore drill recovers one Paperless document and one Immich photo from the offsite copy.

**Phase 1 — Reproduce.** Lock dependencies. Deploy from a clean tree by tag, not by rsync. WAL and
`busy_timeout` on SQLite. A second DNS answer, so a Pi reboot is not a household internet outage. A
dead-man's switch that can report the Pi's own death, since Kuma on the Pi cannot.
→ **Test:** a blank SD card reaches a fully running Pi using only git, the vault and restic, in under an
hour, without anyone remembering how it was set up.

**Phase 2 — Sense.** Zigbee2MQTT and Mosquitto, the dongle on a USB 2 extension, the channel chosen before
pairing anything. First devices in doctrine order: leak sensor (alarm), Zigbee smoke/CO (alarm, an addition
to the standalone rather than a replacement), soil moisture (feeds the strongest existing module).
→ **Test:** pulling a sensor's battery produces exactly one message, and re-pairing after a Pi reboot takes
zero manual steps.

**Phase 3 — Winter power.** The electrician gate from `lighting-plan.md`. Delta 2 as an inline UPS,
`/conserve`, the 80 % limit. The lighting layer rides the same wiring.
→ **Test:** a real Yasno outage passes with lights, fridge, Pi and router all up, and the bot narrating
start and end, with nobody touching anything.

**Phase 4 — Consolidate the bot.** The entry fee for the next module, paid before `/light` is written.
Otherwise the Zigbee event stream lands as the tenth job class in `reminders.py` and a seventh copy of the
board pattern.

---

## The rule that keeps this from happening again

**Feature freeze on new bot modules until Phase 0 passes its test.** Every hour spent on the media language
ladder or the places module was a fine hour. The *next* such hour is not.
