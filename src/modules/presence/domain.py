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

    def somebody_else_home(self, mac: str) -> bool:
        """Whether any of our phones other than this one is on the wi-fi."""
        return bool((self.ours & self.online) - {mac})
