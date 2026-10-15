"""Node Info: NodeHistory persistence and NodeInfoFlow over roster + history."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fakes import make_node
from flows.base import Deps, Goto, Keep, Stay, GOTO_UTILITIES
from flows.node_info import PROMPT, QUICK_USAGE, NodeInfoFlow, describe, find
from node_history import NodeHistory
from session import Session

NOW = 1_800_000_000


def history(*entries):
    store = NodeHistory(":memory:")
    store.initialize_schema()
    for node_id, node, when in entries:
        store.record(node_id, node, now=when)
    return store


def rich_node(num, short, long_name, **extra):
    node = make_node(num, short, long_name, last_heard=NOW - 120, battery=55)
    node["deviceMetrics"].update(voltage=3.912, channelUtilization=12.34,
                                 airUtilTx=1.5, temperature=21.0)
    node["position"] = {"latitude": 38.99, "longitude": -74.81, "altitude": 5}
    node["snr"] = 6.25
    node.update(extra)
    return node


# --- NodeHistory -------------------------------------------------------------

def test_record_then_read_back_by_id_and_short_name():
    store = history(("!a1", rich_node(1, "ABC", "Alpha"), NOW))
    row = store.by_id("!a1")
    assert row["short_name"] == "ABC" and row["battery_level"] == 55
    assert row["latitude"] == 38.99
    assert [r["node_id"] for r in store.by_short_name("abc")] == ["!a1"]


def test_first_seen_is_kept_across_updates():
    store = history(("!a1", make_node(1, "ABC", "Alpha", last_heard=NOW - 500), NOW))
    store.record("!a1", make_node(1, "ABC", "Alpha v2", last_heard=NOW), now=NOW + 60)
    row = store.by_id("!a1")
    assert row["first_seen"] == NOW - 500
    assert row["long_name"] == "Alpha v2"
    assert row["last_updated"] == NOW + 60


def test_first_seen_falls_back_to_now_without_last_heard():
    store = history(("!a1", make_node(1, "ABC", "Alpha"), NOW))
    assert store.by_id("!a1")["first_seen"] == NOW


def test_record_all_skips_a_bad_entry_and_counts_the_rest():
    store = history()
    count = store.record_all({"!ok": make_node(1, "OK", "Fine"), "!bad": None}, now=NOW)
    assert count == 1
    assert store.by_id("!ok") is not None


def test_missing_lookups_are_empty():
    store = history()
    assert store.by_id("!none") is None
    assert store.by_short_name("zzz") == []


# --- find / describe -----------------------------------------------------------

def test_find_prefers_the_live_roster():
    roster = {"!live": make_node(1, "ABC", "Live One")}
    store = history(("!old", make_node(2, "ABC", "Old One"), NOW))
    assert find("abc", Deps(roster=roster, node_history=store)) == [("!live", "ABC", "Live One")]


def test_find_falls_back_to_history():
    store = history(("!old", make_node(2, "ABC", "Old One"), NOW))
    assert find("ABC", Deps(roster={}, node_history=store)) == [("!old", "ABC", "Old One")]


def test_find_tolerates_roster_entries_without_a_user():
    roster = {"!x": {"num": 9}, "!a": make_node(1, "ABC", "Alpha")}
    assert find("abc", Deps(roster=roster)) == [("!a", "ABC", "Alpha")]


def test_describe_from_the_live_roster():
    roster = {"!a1": rich_node(1, "ABC", "Alpha")}
    card = describe(("!a1", "ABC", "Alpha"), Deps(roster=roster), now=NOW)
    for line in ["📡 Node Info: ABC 📡", "Node ID: !a1", "Hardware: TBEAM", "Role: CLIENT",
                 "Battery: 55%", "Voltage: 3.91V", "Ch. Util: 12.3%", "Air Util TX: 1.5%",
                 "Temp: 21.0°C", "Last Heard: 2 min ago", "SNR: 6.2 dB",
                 "Location: 38.9900, -74.8100"]:
        assert line in card, line


def test_describe_fills_gaps_from_history():
    store = history(("!a1", rich_node(1, "ABC", "Alpha"), NOW))
    card = describe(("!a1", "ABC", "Alpha"), Deps(roster={}, node_history=store), now=NOW)
    assert "Battery: 55%" in card
    assert "First Seen:" in card


def test_last_heard_buckets():
    def heard(ago):
        roster = {"!a": make_node(1, "A", "A", last_heard=NOW - ago)}
        card = describe(("!a", "A", "A"), Deps(roster=roster), now=NOW)
        return next(l for l in card.splitlines() if l.startswith("Last Heard"))
    assert heard(5) == "Last Heard: 5 sec ago"
    assert heard(7200) == "Last Heard: 2 hr ago"
    assert heard(3 * 86400) == "Last Heard: 3 days ago"


# --- the flow ----------------------------------------------------------------

def test_entry_prompts():
    result = NodeInfoFlow().entry(Deps())
    assert result.replies == [PROMPT]
    assert result.outcome == Stay({"command": "NODE_INFO", "step": 1})


def test_single_match_answers_and_returns_to_utilities():
    roster = {"!a": make_node(1, "ABC", "Alpha")}
    result = NodeInfoFlow().advance("abc", {"command": "NODE_INFO", "step": 1}, Deps(roster=roster))
    assert result.replies[0].startswith("📡 Node Info: ABC")
    assert result.outcome == Goto(GOTO_UTILITIES)


def test_not_found_returns_to_utilities():
    result = NodeInfoFlow().advance("zzz", {"command": "NODE_INFO", "step": 1}, Deps())
    assert "not found" in result.replies[0]
    assert result.outcome == Goto(GOTO_UTILITIES)


def test_several_matches_ask_which():
    roster = {"!a": make_node(1, "ABC", "Alpha"), "!b": make_node(2, "ABC", "Bravo")}
    flow = NodeInfoFlow()
    d = Deps(roster=roster)
    asked = flow.advance("ABC", {"command": "NODE_INFO", "step": 1}, d)
    assert "[0] Alpha (!a)" in asked.replies[0] and "[1] Bravo (!b)" in asked.replies[0]
    state = asked.outcome.state
    assert flow.advance("9", state, d).outcome == Stay(state)
    assert flow.advance("one", state, d).outcome == Stay(state)
    chosen = flow.advance("1", state, d)
    assert "Long Name: Bravo" in chosen.replies[0]
    assert chosen.outcome == Goto(GOTO_UTILITIES)


def test_quick_command_lists_every_match():
    roster = {"!a": make_node(1, "ABC", "Alpha"), "!b": make_node(2, "ABC", "Bravo")}
    result = NodeInfoFlow().quick("N,,abc", Deps(roster=roster))
    assert isinstance(result.outcome, Keep)
    assert result.replies[0].startswith("Multiple nodes")
    assert len(result.replies) == 3


def test_quick_command_usage():
    assert NodeInfoFlow().quick("N,,", Deps()).replies == [QUICK_USAGE]


def test_lone_n_stays_a_menu_choice():
    """N,, must not swallow a bare "n" — that is News, Nodes, or No."""
    session = Session()
    assert session._quick_command("n", Deps()) is None
    assert session._quick_command("N, maybe", Deps()) is None
    assert session._quick_command("n,,ABC", Deps(roster={})) is not None


def test_bare_words_still_route_for_longer_commands():
    session = Session()
    assert session._quick_command("PB", Deps()) is not None


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
