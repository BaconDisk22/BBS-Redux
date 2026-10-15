"""Node Info: everything the BBS knows about a node, by short name.

Stepped from [N]ode Info on the Utilities menu — enter a short name, pick one
if several Nodes share it — or in one shot with ``N,,{short_name}``, which
lists every match.

Answers from the live roster first and fills the gaps from NodeHistory, so a
Node that has dropped off the mesh can still be looked up. Pure: both arrive
through Deps; nothing here touches the radio or opens a file.
"""

import time
from datetime import datetime

from flows.base import stay, keep, goto, GOTO_UTILITIES

PROMPT = "🔍NODE INFO🔍\nEnter the short name of the node to look up:"
QUICK_USAGE = "Node Info Quick Command format:\nN,,{short_name}"

# (label, roster path, history column, format) — the order lines are shown in.
_FIELDS = [
    ("Hardware", ("user", "hwModel"), "hw_model", "{}"),
    ("Role", ("user", "role"), "role", "{}"),
    ("Battery", ("deviceMetrics", "batteryLevel"), "battery_level", "{}%"),
    ("Voltage", ("deviceMetrics", "voltage"), "voltage", "{:.2f}V"),
    ("Ch. Util", ("deviceMetrics", "channelUtilization"), "channel_utilization", "{:.1f}%"),
    ("Air Util TX", ("deviceMetrics", "airUtilTx"), "air_util_tx", "{:.1f}%"),
    ("Temp", ("deviceMetrics", "temperature"), "temperature", "{:.1f}°C"),
]


def _dig(node, path):
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def find(short_name, deps):
    """Every node answering to `short_name`, as (id, short, long) — live roster
    first; the history only when the roster has none."""
    wanted = short_name.strip().lower()
    live = [(node_id, _dig(n, ("user", "shortName")), _dig(n, ("user", "longName")))
            for node_id, n in (deps.roster or {}).items()
            if (_dig(n, ("user", "shortName")) or "").lower() == wanted]
    if live or deps.node_history is None:
        return live
    return [(row["node_id"], row["short_name"], row["long_name"])
            for row in deps.node_history.by_short_name(wanted)]


def _ago(seconds):
    if seconds < 60:
        return f"{seconds} sec ago"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} hr ago"
    return f"{seconds // 86400} days ago"


def describe(match, deps, now=None):
    """The info card for one (id, short, long) match."""
    node_id, short, long_name = match
    now = int(now if now is not None else time.time())
    live = (deps.roster or {}).get(node_id) or {}
    past = (deps.node_history.by_id(node_id) if deps.node_history else None) or {}

    def value(path, column):
        found = _dig(live, path)
        return found if found is not None else past.get(column)

    lines = [f"📡 Node Info: {short} 📡",
             f"Long Name: {long_name}",
             f"Short Name: {short}",
             f"Node ID: {node_id}"]
    for label, path, column, shape in _FIELDS:
        found = value(path, column)
        if found is not None and found != "Unknown":
            lines.append(f"{label}: {shape.format(found)}")

    last_heard = value(("lastHeard",), "last_heard")
    if last_heard:
        lines.append(f"Last Heard: {_ago(max(0, now - int(last_heard)))}")
    snr = value(("snr",), "snr")
    if snr is not None:
        lines.append(f"SNR: {snr:.1f} dB")
    lat = value(("position", "latitude"), "latitude")
    lon = value(("position", "longitude"), "longitude")
    if lat is not None and lon is not None:
        lines.append(f"Location: {lat:.4f}, {lon:.4f}")
    if past.get("first_seen"):
        lines.append(f"First Seen: {datetime.fromtimestamp(past['first_seen']).strftime('%m/%d %H:%M')}")
    return "\n".join(lines)


def _not_found(short_name):
    return f"Node with short name '{short_name}' not found."


class NodeInfoFlow:
    TOPIC = "NODE_INFO"
    QUICK_COMMANDS = {"n,,": "quick"}

    def entry(self, deps):
        return stay({"command": self.TOPIC, "step": 1}, replies=[PROMPT])

    def advance(self, message, state, deps):
        if state.get("step", 1) == 1:
            return self._lookup(message.strip(), deps)
        return self._choose(message.strip(), state, deps)

    def _lookup(self, short_name, deps):
        matches = find(short_name, deps)
        if not matches:
            return goto(GOTO_UTILITIES, replies=[_not_found(short_name)])
        if len(matches) == 1:
            return goto(GOTO_UTILITIES, replies=[describe(matches[0], deps)])
        listing = "\n".join(f"[{i}] {long_name} ({node_id})"
                            for i, (node_id, _, long_name) in enumerate(matches))
        return stay({"command": self.TOPIC, "step": 2, "nodes": [list(m) for m in matches]},
                    replies=[f"Multiple nodes found with short name '{short_name}':\n{listing}\n"
                             f"Reply with the number to view details or X to cancel."])

    def _choose(self, message, state, deps):
        nodes = state.get("nodes", [])
        try:
            choice = int(message)
        except ValueError:
            return stay(state, replies=["Invalid input. Please enter a number or X to cancel."])
        if not 0 <= choice < len(nodes):
            return stay(state, replies=["Invalid selection. Please try again or send X to cancel."])
        return goto(GOTO_UTILITIES, replies=[describe(tuple(nodes[choice]), deps)])

    def quick(self, message, deps):
        parts = message.split(",,", 1)
        if len(parts) != 2 or not parts[1].strip():
            return keep(replies=[QUICK_USAGE])
        short_name = parts[1].strip()
        matches = find(short_name, deps)
        if not matches:
            return keep(replies=[_not_found(short_name)])
        cards = [describe(m, deps) for m in matches]
        if len(matches) > 1:
            cards.insert(0, f"Multiple nodes found with short name '{short_name}':")
        return keep(replies=cards)
