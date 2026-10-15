"""Configuration as a value.

`load()` reads the config file once and returns a frozen `Config`. There is no
module-level state, no `configure()`, no `reset()` — a caller that wants
different settings builds a different `Config` and passes it down (see
docs/adr/0004). Reading the filesystem happens only inside `load()`.
"""

import configparser
from dataclasses import dataclass, field
from typing import List, Optional

DEFAULT_CONFIG_FILE = 'config.ini'
FORTUNES_FILE = 'fortunes.txt'


@dataclass(frozen=True)
class Menus:
    """Which letters each menu offers, in order."""

    main: List[str]
    bbs: List[str]
    utilities: List[str]


@dataclass(frozen=True)
class Js8Config:
    """How to reach JS8Call and which of its traffic to keep."""

    host: Optional[str] = None
    port: Optional[int] = None
    db_path: Optional[str] = None
    groups: List[str] = field(default_factory=list)
    urgent: List[str] = field(default_factory=list)
    store_messages: bool = True


@dataclass(frozen=True)
class WeatherConfig:
    """OpenWeatherMap access for the Weather utility. No key means no weather."""

    api_key: Optional[str] = None
    default_location: str = '48336'
    units: str = 'imperial'


@dataclass(frozen=True)
class AnnouncementConfig:
    """Channel broadcasts: who may send them, and what QA sends where.

    `admins` empty falls back to the Urgent Allow List; both empty means any
    Node may announce — the same "empty means anyone" rule the Allow List uses.
    """

    channel: int = 0
    message: str = 'BBS Announcement'
    admins: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class StartupConfig:
    """An optional one-shot channel broadcast when the BBS comes online."""

    enabled: bool = False
    channel_index: int = 0
    message: str = 'TC²-BBS is online and ready!'


@dataclass(frozen=True)
class MqttTopicsConfig:
    """Where monitor_mqtt_topics.py writes its counts, and the base topic it
    watches — the prefix trimmed off each topic when the BBS lists them."""

    db_path: str = 'mqtt_counts.db'
    base_topic: str = ''


@dataclass(frozen=True)
class Config:
    """Everything a running BBS reads from disk, resolved once."""

    menus: Menus
    fortunes: List[str] = field(default_factory=list)
    bbs_nodes: List[str] = field(default_factory=list)
    allowed_nodes: List[str] = field(default_factory=list)
    js8: Js8Config = field(default_factory=Js8Config)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    announcement: AnnouncementConfig = field(default_factory=AnnouncementConfig)
    startup: StartupConfig = field(default_factory=StartupConfig)
    mqtt_topics: MqttTopicsConfig = field(default_factory=MqttTopicsConfig)
    message_delay: float = 4.0


def _items(parser, section, option):
    """Comma-separated values, trimmed, empties dropped."""
    raw = parser.get(section, option, fallback='')
    return [entry.strip() for entry in raw.split(',') if entry.strip()]


def _read_fortunes(path):
    try:
        with open(path, 'r') as handle:
            return [line.strip() for line in handle if line.strip()]
    except OSError:
        return []


def load(config_file=DEFAULT_CONFIG_FILE, fortunes_file=FORTUNES_FILE):
    """Read the config file (and fortunes) into a Config.

    A single `config_file` supplies every section — menus, sync, allow-list and
    JS8Call all come from the same file, so `--config other.ini` means what it
    says.
    """
    parser = configparser.ConfigParser()
    parser.read(config_file)

    return Config(
        menus=Menus(
            main=_items(parser, 'menu', 'main_menu_items'),
            bbs=_items(parser, 'menu', 'bbs_menu_items'),
            utilities=_items(parser, 'menu', 'utilities_menu_items'),
        ),
        fortunes=_read_fortunes(fortunes_file),
        bbs_nodes=_items(parser, 'sync', 'bbs_nodes'),
        allowed_nodes=_items(parser, 'allow_list', 'allowed_nodes'),
        js8=Js8Config(
            host=parser.get('js8call', 'host', fallback=None),
            port=parser.getint('js8call', 'port', fallback=None),
            db_path=parser.get('js8call', 'db_file', fallback=None),
            groups=_items(parser, 'js8call', 'js8groups'),
            urgent=_items(parser, 'js8call', 'js8urgent'),
            store_messages=parser.getboolean('js8call', 'store_messages', fallback=True),
        ),
        weather=WeatherConfig(
            api_key=_api_key(parser.get('weather', 'api_key', fallback=None)),
            default_location=parser.get('weather', 'default_location', fallback='48336').strip(),
            units=parser.get('weather', 'units', fallback='imperial').strip(),
        ),
        announcement=AnnouncementConfig(
            channel=parser.getint('announcement', 'default_announcement_channel', fallback=0),
            message=parser.get('announcement', 'default_message', fallback='BBS Announcement'),
            admins=_items(parser, 'announcement', 'admin_nodes'),
        ),
        startup=StartupConfig(
            enabled=parser.getboolean('startup', 'enabled', fallback=False),
            channel_index=parser.getint('startup', 'channel_index', fallback=0),
            message=parser.get('startup', 'message', fallback='TC²-BBS is online and ready!'),
        ),
        mqtt_topics=MqttTopicsConfig(
            db_path=parser.get('mqtt_monitor', 'db_path', fallback='mqtt_counts.db'),
            base_topic=parser.get('mqtt_monitor', 'base_topic', fallback='').strip().rstrip('/'),
        ),
        message_delay=parser.getfloat('misc', 'message_delay', fallback=4.0),
    )


def _api_key(raw):
    """A key left at the example's placeholder is no key at all."""
    if raw is None:
        return None
    raw = raw.strip()
    if not raw or raw.lower() in ('your_api_key_here', 'your_api_key'):
        return None
    return raw
