"""The utilities wired end to end: config, Transport broadcasts, startup, router.

Drives the real message_processing router with a FakeTransport, the same way
the characterization suite does, plus a fake meshtastic interface where the
Transport itself is under test.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
import types

import message_processing
import settings
from database import Database
from fakes import FakeTransport, make_node
from flows.announcement import PREFIX
from flows.base import MeshChannel
from js8_db import Js8Database
from node_history import NodeHistory
from runtime import Runtime
from session import Session
from settings import AnnouncementConfig, Config, Menus, StartupConfig
from startup import announce_startup
from transport import MAX_PAYLOAD, MeshtasticTransport


# --- config ------------------------------------------------------------------

CONFIG_TEXT = """
[interface]
type = serial
[menu]
main_menu_items = Q, B, U, X
bbs_menu_items = M, B, C, J, X
utilities_menu_items = S, F, W, T, R, A, N, X
[weather]
api_key = abc123
default_location = 08260
units = metric
[announcement]
default_announcement_channel = 2
default_message = Hi all
admin_nodes = !aa, !bb
[startup]
enabled = True
channel_index = 1
message = BBS up
[mqtt_monitor]
db_path = counts.db
base_topic = msh/US/NJ/
[misc]
message_delay = 2.5
"""


def _load(text):
    handle = tempfile.NamedTemporaryFile("w", suffix=".ini", delete=False)
    handle.write(text)
    handle.close()
    try:
        return settings.load(handle.name, fortunes_file="/nonexistent")
    finally:
        os.unlink(handle.name)


def test_load_reads_every_utility_section():
    config = _load(CONFIG_TEXT)
    assert config.menus.utilities == ["S", "F", "W", "T", "R", "A", "N", "X"]
    assert config.weather.api_key == "abc123"
    assert config.weather.default_location == "08260"     # leading zero kept
    assert config.weather.units == "metric"
    assert config.announcement == AnnouncementConfig(channel=2, message="Hi all", admins=["!aa", "!bb"])
    assert config.startup == StartupConfig(enabled=True, channel_index=1, message="BBS up")
    assert config.mqtt_topics.db_path == "counts.db"
    assert config.mqtt_topics.base_topic == "msh/US/NJ"   # trailing slash dropped
    assert config.message_delay == 2.5


def test_load_defaults_when_sections_are_missing():
    config = _load("[menu]\nmain_menu_items = Q, X\n")
    assert config.weather.api_key is None
    assert config.announcement.admins == []
    assert config.startup.enabled is False
    assert config.message_delay == 4.0


# --- Transport: channel broadcasts --------------------------------------------

class RadioInterface:
    def __init__(self, slots=None):
        self.nodes = {}
        self.sent = []
        self.localNode = types.SimpleNamespace(channels=slots or [])

    def sendText(self, text, destinationId, wantAck=True, wantResponse=False, channelIndex=0):
        self.sent.append(dict(text=text, dest=destinationId, ack=wantAck, channel=channelIndex))
        return types.SimpleNamespace(id=1)


def slot(name):
    return types.SimpleNamespace(settings=types.SimpleNamespace(name=name))


def test_transport_lists_primary_and_named_slots_only():
    radio = RadioInterface([slot(""), slot("LongFast"), slot(""), slot("Local")])
    channels = MeshtasticTransport(radio, pacing_seconds=0).channels
    assert channels == [MeshChannel(0, ""), MeshChannel(1, "LongFast"), MeshChannel(3, "Local")]


def test_transport_without_channel_info_lists_none():
    radio = RadioInterface()
    del radio.localNode
    assert MeshtasticTransport(radio, pacing_seconds=0).channels == []


def test_meshchannel_destination_broadcasts_on_that_slot():
    from meshtastic import BROADCAST_NUM
    radio = RadioInterface()
    MeshtasticTransport(radio, pacing_seconds=0).send("hello", MeshChannel(3, "Local"))
    assert radio.sent == [dict(text="hello", dest=BROADCAST_NUM, ack=False, channel=3)]


def test_over_long_broadcast_is_refused_not_split():
    radio = RadioInterface()
    MeshtasticTransport(radio, pacing_seconds=0).send("é" * (MAX_PAYLOAD // 2 + 1), MeshChannel(0))
    assert radio.sent == []


# --- startup -----------------------------------------------------------------

def test_startup_disabled_sends_nothing():
    transport = FakeTransport()
    assert announce_startup(transport, StartupConfig(enabled=False)) is False
    assert transport.outbox == []


def test_startup_sends_on_the_configured_channel():
    transport = FakeTransport()
    assert announce_startup(transport, StartupConfig(True, 2, "BBS up")) is True
    assert transport.outbox == [(MeshChannel(2), "BBS up")]


def test_startup_refuses_an_over_long_message():
    transport = FakeTransport()
    assert announce_startup(transport, StartupConfig(True, 0, "x" * (MAX_PAYLOAD + 1))) is False
    assert transport.outbox == []


# --- through the router --------------------------------------------------------

ME, ME_ID = 1001, "!me"


def runtime_for(**config_overrides):
    database = Database(":memory:")
    database.initialize_schema()
    history = NodeHistory(":memory:")
    history.initialize_schema()
    config = Config(menus=Menus(main=["Q", "B", "U", "X"], bbs=["M", "X"],
                                utilities=["S", "T", "R", "A", "N", "X"]),
                    **config_overrides)
    return Runtime(config=config, database=database, js8_database=Js8Database(None),
                   session=Session(), node_history=history)


def transport_for():
    transport = FakeTransport(nodes={ME_ID: make_node(ME, "ME", "Me Node")})
    transport.channels = [MeshChannel(0, ""), MeshChannel(1, "Club")]
    return transport


def say(runtime, transport, message):
    transport.clear()
    message_processing.process_message(ME, message, transport, runtime)
    return transport.outbox


def test_utilities_menu_lists_the_new_items():
    runtime, transport = runtime_for(), transport_for()
    say(runtime, transport, "hi")
    menu = say(runtime, transport, "u")[0][1]
    for label in ["[T]op MQTT Topics", "Weathe[R]", "[A]nnouncement", "[N]ode Info"]:
        assert label in menu, label


def test_announcement_reaches_the_radio_channel_through_the_router():
    runtime, transport = runtime_for(announcement=AnnouncementConfig(admins=[ME_ID])), transport_for()
    say(runtime, transport, "u")
    assert "[1] Club" in say(runtime, transport, "a")[0][1]
    say(runtime, transport, "1")
    say(runtime, transport, "Meet at 7")
    say(runtime, transport, "END")
    out = say(runtime, transport, "y")
    assert (MeshChannel(1, "Club"), PREFIX + "Meet at 7") in out


def test_non_admin_cannot_announce_through_the_router():
    runtime, transport = runtime_for(announcement=AnnouncementConfig(admins=["!someone"])), transport_for()
    out = say(runtime, transport, "QA")
    assert [dest for dest, _ in out] == [ME]
    assert "Only BBS admins" in out[0][1]


def test_node_info_quick_command_through_the_router():
    runtime, transport = runtime_for(), transport_for()
    out = say(runtime, transport, "N,,me")
    assert "Long Name: Me Node" in out[0][1]


def test_on_receive_records_the_sender_in_node_history():
    runtime = runtime_for()
    radio = types.SimpleNamespace(nodes={ME_ID: make_node(ME, "ME", "Me Node", battery=42)},
                                  myInfo=types.SimpleNamespace(my_node_num=9999))
    packet = {"fromId": ME_ID, "from": ME, "decoded": {"portnum": "TELEMETRY_APP"}}
    message_processing.on_receive(packet, radio, runtime)
    assert runtime.node_history.by_id(ME_ID)["battery_level"] == 42


def test_on_receive_ignores_unknown_senders():
    runtime = runtime_for()
    radio = types.SimpleNamespace(nodes={}, myInfo=types.SimpleNamespace(my_node_num=9999))
    message_processing.on_receive({"fromId": "!ghost", "decoded": {"portnum": "X"}}, radio, runtime)
    assert runtime.node_history.by_id("!ghost") is None


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
