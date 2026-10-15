"""The resolved application: configuration and the stores built from it.

Assembled once at startup in `server.main()` and handed to the router. It is
frozen and passed, never reached for — no module holds it. The Session it
carries owns the live conversation state, so nothing on the conversation path
is a module global. A flow still receives only what it needs, through `Deps`.

The utility services default to None so a Runtime built for a test needs only
the four core fields; a flow handed None answers "unavailable".
"""

from dataclasses import dataclass
from typing import Any, Optional

from database import Database
from js8_db import Js8Database
from node_history import NodeHistory
from session import Session
from settings import Config


@dataclass(frozen=True)
class Runtime:
    config: Config
    database: Database
    js8_database: Js8Database
    session: Session
    node_history: Optional[NodeHistory] = None
    weather: Any = None          # weather.OpenWeather
    topics: Any = None           # mqtt_topics.TopicCounts
