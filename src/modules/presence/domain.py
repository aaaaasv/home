"""Who is on the wi-fi, when a phone's address will not stay still.

iOS gives every network a **private wi-fi address** and rotates it. The flat learned this the hard way: both
phones sat at home for hours while the bot saw two strangers and none of its own, because the two addresses
written in the configuration had been retired. Nothing logged an error — a list of addresses cannot tell the
difference between "that phone left" and "that phone renamed itself".

So a phone is ours by **what the router calls it**, not by the address it happens to wear today. The router
keeps the name it learned over DHCP even for a client that is currently away, which is what makes the same
lookup work for the moment somebody leaves and the moment they come back.
"""
from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class NetworkClient:
    """One client the router knows about, whether or not it is on the network right now."""

    mac: str
    name: str | None
    is_online: bool


@dataclass(frozen=True)
class PhoneRoster:
    """
    Every phone the router recognises as the family's, and which of them are on the wi-fi at this moment.

    `known` is wider than `ours` on purpose: it is every client the router has heard of, and it is what lets a
    caller tell "a device we have decided is not a phone" from "a device nobody has ever seen" — the second is
    the shape a rotated address arrives in, and the only one worth asking the router again about.
    """

    ours: frozenset[str]
    online: frozenset[str]
    known: frozenset[str]

    def includes(self, mac: str) -> bool:
        return mac in self.ours

    def others_online(self, mac: str) -> set[str]:
        """Our other phones the router has on the wi-fi — each still to be judged resident or companion."""
        return set((self.ours & self.online) - {mac})


@dataclass(frozen=True)
class HouseholdAbsence:
    """
    How long the flat has stood empty, as the log can tell — which is not the same as how long one address
    has been gone.

    a phone carries a **different private address on each SSID**, and this flat runs two, so walking from the
    5 GHz radio to the 2.4 GHz one retires one address and raises another. measured per address that reads as
    a long absence ending right now; measured per household it reads as what it is, somebody who never left.
    """

    empty_for: timedelta | None
    somebody_stayed: bool


# what the welcome light decided about one arrival, kept with the join so the reason survives the evening
RAISED = "raised"
REFUSED_HOP = "hop"
REFUSED_DAYLIGHT = "daylight"
REFUSED_SOMEBODY_HOME = "somebody_home"
REFUSED_LIGHT_ON = "light_on"
REFUSED_NO_DEPARTURE = "no_departure"
REFUSED_ROUTER_SILENT = "router_silent"
REFUSED_NEVER_EMPTY = "never_empty"
# a join that never followed a real absence says nothing about whether its owner is at home
OUTCOMES_THAT_ARE_NOT_AN_ARRIVAL = (REFUSED_HOP, REFUSED_NO_DEPARTURE)
