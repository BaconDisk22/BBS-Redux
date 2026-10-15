"""AnnouncementFlow: permission, channel choice, compose, confirm, and QA."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flows.announcement import (
    CANCELLED, MAX_BYTES, NO_CHANNELS, NOT_ALLOWED, PREFIX, SENT, AnnouncementFlow, may_announce,
)
from flows.base import Deps, End, Goto, Keep, MeshChannel, Stay, GOTO_UTILITIES
from settings import AnnouncementConfig

CHANNELS = [MeshChannel(0, ""), MeshChannel(1, "LongFast"), MeshChannel(3, "Local")]


def deps(node_id="!admin", admins=("!admin",), allowed=(), channels=CHANNELS,
         channel=3, message="Hello from the BBS"):
    return Deps(node_id=node_id, allowed_nodes=list(allowed), channels=list(channels),
                announcement=AnnouncementConfig(channel=channel, message=message,
                                                admins=list(admins)))


def walk(*messages, d=None):
    """Enter the flow and feed it messages; return the last result."""
    d = d or deps()
    flow = AnnouncementFlow()
    result = flow.entry(d)
    for message in messages:
        result = flow.advance(message, result.outcome.state, d)
    return result


# --- permission --------------------------------------------------------------

def test_admins_list_decides():
    assert may_announce(deps(node_id="!admin"))
    assert not may_announce(deps(node_id="!stranger"))


def test_empty_admins_fall_back_to_the_allow_list():
    assert may_announce(deps(node_id="!ok", admins=(), allowed=("!ok",)))
    assert not may_announce(deps(node_id="!no", admins=(), allowed=("!ok",)))


def test_both_lists_empty_means_anyone():
    assert may_announce(deps(node_id="!anyone", admins=(), allowed=()))


def test_unknown_node_is_refused_when_admins_are_set():
    assert not may_announce(deps(node_id=None))


def test_entry_refuses_a_non_admin():
    result = AnnouncementFlow().entry(deps(node_id="!stranger"))
    assert result.replies == [NOT_ALLOWED]
    assert result.outcome == Goto(GOTO_UTILITIES)


# --- stepped -----------------------------------------------------------------

def test_entry_lists_channels_with_default_for_unnamed_primary():
    result = AnnouncementFlow().entry(deps())
    text = result.replies[0]
    assert "[0] Default" in text and "[1] LongFast" in text and "[3] Local" in text
    assert result.outcome.state["step"] == 1


def test_entry_without_channels():
    result = AnnouncementFlow().entry(deps(channels=[]))
    assert result.replies == [NO_CHANNELS]
    assert result.outcome == Goto(GOTO_UTILITIES)


def test_bad_channel_choice_stays():
    for bad in ("2", "abc"):
        result = walk(bad)
        assert isinstance(result.outcome, Stay)
        assert result.outcome.state["step"] == 1


def test_full_walk_sends_to_the_chosen_channel():
    result = walk("1", "Net tonight", "at 8pm", "END", "y")
    assert result.replies == [SENT]
    assert isinstance(result.outcome, End)
    assert result.notifications == [(MeshChannel(1, "LongFast"), PREFIX + "Net tonight\nat 8pm")]


def test_preview_before_sending():
    result = walk("3", "Hi", "END")
    assert "PREVIEW" in result.replies[0] and "Channel: Local" in result.replies[0]
    assert result.outcome.state["step"] == 3
    assert result.notifications == []


def test_no_cancels_back_to_utilities():
    result = walk("3", "Hi", "END", "n")
    assert result.replies == [CANCELLED]
    assert result.outcome == Goto(GOTO_UTILITIES)
    assert result.notifications == []


def test_empty_message_cancels():
    result = walk("3", "END")
    assert result.outcome == Goto(GOTO_UTILITIES)
    assert result.notifications == []


def test_over_long_message_asks_again():
    result = walk("3", "x" * MAX_BYTES, "END")
    assert "too long" in result.replies[0]
    assert result.outcome.state["step"] == 2
    assert result.outcome.state["message"] == ""


def test_emoji_count_as_bytes():
    room = MAX_BYTES - len(PREFIX.encode("utf-8"))
    just_fits = "a" * room
    assert walk("3", just_fits, "END").outcome.state["step"] == 3
    over = "😀" + "a" * (room - 3)          # one emoji is 4 bytes
    assert walk("3", over, "END").outcome.state["step"] == 2


def test_unclear_confirmation_reprompts():
    result = walk("3", "Hi", "END", "maybe")
    assert result.outcome.state["step"] == 3
    assert "Y to send" in result.replies[0]


# --- QA ----------------------------------------------------------------------

def test_quick_sends_the_configured_message():
    result = AnnouncementFlow().quick("QA", deps())
    assert result.replies == [SENT]
    assert isinstance(result.outcome, Keep)
    assert result.notifications == [(MeshChannel(3, "Local"), PREFIX + "Hello from the BBS")]


def test_quick_with_text_sends_that_text():
    result = AnnouncementFlow().quick("QA,,Repeater down for maintenance", deps())
    assert result.notifications[0][1] == PREFIX + "Repeater down for maintenance"


def test_quick_refuses_a_missing_channel():
    result = AnnouncementFlow().quick("QA", deps(channel=5))
    assert "Channel 5 not found" in result.replies[0]
    assert "3 (Local)" in result.replies[0]
    assert result.notifications == []


def test_quick_refuses_a_non_admin():
    result = AnnouncementFlow().quick("QA", deps(node_id="!stranger"))
    assert result.replies == [NOT_ALLOWED]
    assert result.notifications == []


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
