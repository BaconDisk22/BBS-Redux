"""Top MQTT Topics: the busiest topics seen by monitor_mqtt_topics.py.

A leaf — [T]op MQTT Topics on the Utilities menu and the TT quick command give
the same answer. Pure: counts come from the injected ``deps.topics`` reader
(mqtt_topics.TopicCounts); pacing between the replies is the Transport's job.
"""

from flows.base import keep

TOP_LIMIT = 15
LINES_PER_MESSAGE = 3

UNAVAILABLE = "MQTT topic statistics are unavailable."
HEADER = f"🏆 Top {TOP_LIMIT} Topics 🏆"
FOOTER = "🏁 End of Topics 🏁"


def short_topic(base_topic, subtopic, prefix):
    """The topic with the monitored base prefix trimmed off to save airtime."""
    topic = base_topic if not subtopic else f"{base_topic}/{subtopic}"
    if prefix:
        if topic == prefix:
            return "(base)"
        if topic.startswith(prefix + "/"):
            return topic[len(prefix) + 1:]
    return topic


def replies(deps):
    """Header, the ranked topics a few per message, footer."""
    rows = deps.topics.top(TOP_LIMIT) if deps.topics is not None else None
    if not rows:
        return [UNAVAILABLE]
    lines = [f"{rank:02d}. {short_topic(base, sub, deps.mqtt_base_topic)} — {count:,}"
             for rank, (base, sub, count) in enumerate(rows, start=1)]
    batches = ["\n".join(lines[i:i + LINES_PER_MESSAGE])
               for i in range(0, len(lines), LINES_PER_MESSAGE)]
    return [HEADER] + batches + [FOOTER]


class TopicsFlow:
    """Owns only the TT quick command; the menu entry is a Navigation leaf.

    Keyed "tt,," so the bare word TT matches exactly — a plain "tt" prefix
    would also catch any mail or bulletin line that happens to start "tt".
    """

    TOPICS = []
    QUICK_COMMANDS = {"tt,,": "quick"}

    def quick(self, message, deps):
        return keep(replies=replies(deps))
