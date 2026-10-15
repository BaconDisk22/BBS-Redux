"""Announcement: broadcast a message on one of this BBS's radio channels.

Stepped from [A]nnouncement on the Utilities menu — pick a channel, type the
text (END to finish), confirm — or in one shot with the QA quick command,
which sends the configured message (or ``QA,,{text}``) to the configured
channel.

Who may announce: the [announcement] admin_nodes list, or the Urgent Allow
List when that is empty; both empty means any Node may, the same rule the
Allow List already follows.

Pure: the broadcast rides back as a notification addressed to a MeshChannel,
which the Transport turns into a one-packet channel broadcast.
"""

from flows.base import MeshChannel, stay, end, keep, goto, GOTO_UTILITIES

#: One packet, never split — a broadcast arrives whole or not at all. Bytes,
#: not characters: emoji cost four.
MAX_BYTES = 200
PREFIX = "📢 ANNOUNCEMENT 📢 "

NOT_ALLOWED = "⛔ Only BBS admins can send announcements."
NO_CHANNELS = "❌ No channels available on device."
SENT = "✅ Announcement sent successfully!"
CANCELLED = "Announcement cancelled."


def may_announce(deps):
    admins = (deps.announcement.admins if deps.announcement else []) or deps.allowed_nodes
    return not admins or deps.node_id in admins


def compose(text):
    return PREFIX + text


def too_long(text):
    """The over-limit reply for a would-be announcement, or None if it fits."""
    size = len(compose(text).encode("utf-8"))
    if size <= MAX_BYTES:
        return None
    room = MAX_BYTES - len(PREFIX.encode("utf-8"))
    return f"Announcement too long ({size - len(PREFIX.encode('utf-8'))} bytes). Max is {room}."


def _channel_menu(channels):
    lines = [f"[{c.index}] {c.label}" for c in channels]
    return ("📣 ANNOUNCEMENT 📣\nSelect a channel to broadcast to:\n" + "\n".join(lines)
            + "\nReply with channel number or X to cancel")


class AnnouncementFlow:
    TOPIC = "ANNOUNCEMENT"
    QUICK_COMMANDS = {"qa,,": "quick"}

    def entry(self, deps):
        if not may_announce(deps):
            return goto(GOTO_UTILITIES, replies=[NOT_ALLOWED])
        if not deps.channels:
            return goto(GOTO_UTILITIES, replies=[NO_CHANNELS])
        channels = [[c.index, c.label] for c in deps.channels]
        return stay({"command": self.TOPIC, "step": 1, "channels": channels},
                    replies=[_channel_menu(deps.channels)])

    def advance(self, message, state, deps):
        step = state.get("step", 1)
        if step == 1:
            return self._choose_channel(message, state)
        if step == 2:
            return self._compose(message, state)
        return self._confirm(message, state)

    # --- steps ------------------------------------------------------------

    def _choose_channel(self, message, state):
        try:
            index = int(message.strip())
        except ValueError:
            return stay(state, replies=["Invalid input. Please enter a channel number or X to cancel."])
        match = next((c for c in state.get("channels", []) if c[0] == index), None)
        if match is None:
            return stay(state, replies=["Invalid channel number. Please try again or send X to cancel."])
        return stay({"command": self.TOPIC, "step": 2, "channel_idx": match[0],
                     "channel_name": match[1], "message": ""},
                    replies=[f"Selected: {match[1]}\nEnter your announcement message.\n"
                             f"Type END on a new line when finished."])

    def _compose(self, message, state):
        if message.strip().lower() != "end":
            # Content is kept verbatim, one line per message, like a mail body.
            text = state.get("message", "")
            text = f"{text}\n{message}" if text else message
            return stay(dict(state, message=text))

        text = state.get("message", "").strip()
        if not text:
            return goto(GOTO_UTILITIES, replies=["No message entered. " + CANCELLED])
        problem = too_long(text)
        if problem:
            return stay(dict(state, message=""),
                        replies=[problem + " Enter a shorter message, then END."])
        preview = (f"📣 PREVIEW 📣\nChannel: {state.get('channel_name', 'Unknown')}\n---\n"
                   f"{text}\n---\nSend this? [Y]es or [N]o")
        return stay(dict(state, step=3, message=text), replies=[preview])

    def _confirm(self, message, state):
        answer = message.strip().lower()
        if answer == "y":
            channel = MeshChannel(index=state["channel_idx"], name=state.get("channel_name", ""))
            return end(replies=[SENT], notifications=[(channel, compose(state["message"]))])
        if answer == "n":
            return goto(GOTO_UTILITIES, replies=[CANCELLED])
        return stay(state, replies=["Please reply with Y to send or N to cancel."])

    # --- quick command ----------------------------------------------------

    def quick(self, message, deps):
        """QA sends the configured message; QA,,{text} sends that text instead,
        either way to the configured announcement channel."""
        if not may_announce(deps):
            return keep(replies=[NOT_ALLOWED])
        config = deps.announcement
        parts = message.split(",,", 1)
        text = parts[1].strip() if len(parts) == 2 and parts[1].strip() else config.message

        channel = next((c for c in deps.channels if c.index == config.channel), None)
        if channel is None:
            available = ", ".join(f"{c.index} ({c.label})" for c in deps.channels) or "none"
            return keep(replies=[f"❌ Channel {config.channel} not found.\n"
                                 f"Available channels: {available}"])
        problem = too_long(text)
        if problem:
            return keep(replies=["❌ " + problem])
        return keep(replies=[SENT], notifications=[(channel, compose(text))])
