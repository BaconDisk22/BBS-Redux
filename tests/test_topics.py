"""Top MQTT Topics: the TopicCounts reader and the replies built from it."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import tempfile

from flows.base import Deps, Keep, Stay
from flows.navigation import NavigationFlow
from flows.topics import FOOTER, HEADER, UNAVAILABLE, TopicsFlow, replies, short_topic
from mqtt_topics import TopicCounts
from session import Session
from settings import Menus


class FakeCounts:
    def __init__(self, rows):
        self.rows = rows

    def top(self, limit=15):
        return self.rows[:limit] if self.rows is not None else None


def _counts_db(rows):
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    connection = sqlite3.connect(handle.name)
    connection.execute("CREATE TABLE topic_counts (base_topic TEXT, subtopic TEXT, message_count INTEGER)")
    connection.executemany("INSERT INTO topic_counts VALUES (?, ?, ?)", rows)
    connection.commit()
    connection.close()
    return handle.name


# --- reader ------------------------------------------------------------------

def test_reader_returns_busiest_first_and_limits():
    path = _counts_db([("msh/US/NJ", "2/e", 5), ("msh/US/NJ", "2/json", 50), ("msh/US/NJ", "", 9)])
    try:
        rows = TopicCounts(path).top(2)
        assert rows == [("msh/US/NJ", "2/json", 50), ("msh/US/NJ", "", 9)]
    finally:
        os.unlink(path)


def test_reader_without_a_file_is_unavailable():
    assert TopicCounts("/nonexistent/mqtt_counts.db").top() is None


def test_reader_with_the_wrong_schema_is_unavailable():
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    try:
        assert TopicCounts(handle.name).top() is None
    finally:
        os.unlink(handle.name)


# --- formatting --------------------------------------------------------------

def test_short_topic_trims_the_configured_base():
    assert short_topic("msh/US/NJ", "2/e/LongFast", "msh/US/NJ") == "2/e/LongFast"
    assert short_topic("msh/US/NJ", "", "msh/US/NJ") == "(base)"
    assert short_topic("msh/US/NJX", "a", "msh/US/NJ") == "msh/US/NJX/a"
    assert short_topic("msh/US/MI", "a", "") == "msh/US/MI/a"


def test_replies_batch_three_lines_per_message():
    rows = [("msh/US/NJ", f"t{i}", 1000 - i) for i in range(7)]
    out = replies(Deps(topics=FakeCounts(rows), mqtt_base_topic="msh/US/NJ"))
    assert out[0] == HEADER and out[-1] == FOOTER
    assert len(out) == 2 + 3                       # 7 lines -> 3 + 3 + 1
    assert out[1].splitlines() == ["01. t0 — 1,000", "02. t1 — 999", "03. t2 — 998"]
    assert out[3] == "07. t6 — 994"


def test_replies_unavailable_when_no_counts():
    assert replies(Deps(topics=FakeCounts(None))) == [UNAVAILABLE]
    assert replies(Deps(topics=FakeCounts([]))) == [UNAVAILABLE]
    assert replies(Deps(topics=None)) == [UNAVAILABLE]


# --- entry points ------------------------------------------------------------

def test_quick_command_answers_without_moving():
    result = TopicsFlow().quick("TT", Deps(topics=FakeCounts([("b", "s", 3)])))
    assert isinstance(result.outcome, Keep)
    assert result.replies[0] == HEADER


def test_utilities_t_answers_and_stays_in_the_menu():
    menus = Menus(main=["Q", "B", "U", "X"], bbs=["M", "X"], utilities=["T", "X"])
    state = {"command": "MENU", "menu": "utilities", "step": 1}
    result = NavigationFlow().advance("t", state, Deps(menus=menus, topics=FakeCounts(None)))
    assert result.replies == [UNAVAILABLE]
    assert result.outcome == Stay(state)


def test_tt_only_matches_as_a_whole_word():
    """A mail line starting "tt" must not trigger the quick command."""
    session = Session()
    deps = Deps(topics=FakeCounts([("b", "s", 3)]))
    assert session.advance(1, "tt", deps)[0][1] == HEADER
    assert session._quick_command("ttyl see you", deps) is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"ok  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
