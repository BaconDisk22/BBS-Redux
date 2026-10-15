"""Node history: every Node the BBS has heard, remembered past the live roster.

Meshtastic's roster only holds nodes the radio currently knows. This store
keeps the last-known details of every node seen (hardware, battery, position,
when it was first and last heard) in ``nodes.db``, so Node Info can still
answer for a node that has dropped off the mesh.

Same shape as `Database`: one object owns the path, connection and schema, is
handed to whoever needs it, and a test builds ``NodeHistory(":memory:")``.
`node_stats.py` reads the same table from the command line.
"""

import logging
import sqlite3
import threading
import time

#: Where the history lives unless a caller says otherwise.
DEFAULT_PATH = 'nodes.db'


def _flatten(node_id, node, now):
    """One roster entry as a row of the nodes table (first_seen left to the caller)."""
    user = node.get('user', {}) or {}
    metrics = node.get('deviceMetrics', {}) or {}
    position = node.get('position', {}) or {}
    return {
        "node_id": node_id,
        "num": node.get('num'),
        "short_name": user.get('shortName'),
        "long_name": user.get('longName'),
        "hw_model": user.get('hwModel'),
        "role": user.get('role'),
        "battery_level": metrics.get('batteryLevel'),
        "voltage": metrics.get('voltage'),
        "channel_utilization": metrics.get('channelUtilization'),
        "air_util_tx": metrics.get('airUtilTx'),
        "temperature": metrics.get('temperature'),
        "latitude": position.get('latitude'),
        "longitude": position.get('longitude'),
        "altitude": position.get('altitude'),
        "snr": node.get('snr'),
        "last_heard": node.get('lastHeard'),
        "last_updated": now,
    }


class NodeHistory:
    def __init__(self, path=DEFAULT_PATH):
        self._path = path
        self._connection = None
        self._lock = threading.Lock()

    def _connect(self):
        if self._connection is None:
            self._connection = sqlite3.connect(self._path, check_same_thread=False)
        return self._connection

    def initialize_schema(self):
        with self._lock:
            connection = self._connect()
            connection.execute('''CREATE TABLE IF NOT EXISTS nodes (
                            node_id TEXT PRIMARY KEY,
                            num INTEGER,
                            short_name TEXT,
                            long_name TEXT,
                            hw_model TEXT,
                            role TEXT,
                            battery_level INTEGER,
                            voltage REAL,
                            channel_utilization REAL,
                            air_util_tx REAL,
                            temperature REAL,
                            latitude REAL,
                            longitude REAL,
                            altitude INTEGER,
                            snr REAL,
                            last_heard INTEGER,
                            first_seen INTEGER,
                            last_updated INTEGER
                        )''')
            connection.commit()

    # --- writes -----------------------------------------------------------

    def record(self, node_id, node, now=None):
        """Insert or refresh one node from its roster entry.

        first_seen is set once — from the node's own lastHeard if it has one,
        else now — and never moved by later updates.
        """
        now = int(now if now is not None else time.time())
        row = _flatten(node_id, node, now)
        with self._lock:
            connection = self._connect()
            existing = connection.execute(
                "SELECT first_seen FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
            if existing:
                fields = [c for c in row if c != "node_id"]
                connection.execute(
                    f"UPDATE nodes SET {', '.join(f'{c} = ?' for c in fields)} WHERE node_id = ?",
                    [row[c] for c in fields] + [node_id])
            else:
                row["first_seen"] = row["last_heard"] or now
                columns = list(row)
                connection.execute(
                    f"INSERT INTO nodes ({', '.join(columns)}) "
                    f"VALUES ({', '.join('?' for _ in columns)})",
                    [row[c] for c in columns])
            connection.commit()

    def record_all(self, roster, now=None):
        """Refresh every node in the roster. Returns how many were recorded;
        one bad entry is logged and skipped rather than stopping the rest."""
        count = 0
        for node_id, node in list(roster.items()):
            try:
                self.record(node_id, node, now)
                count += 1
            except Exception as error:
                logging.error(f"Could not record node {node_id}: {error}")
        return count

    # --- reads ------------------------------------------------------------

    def _rows(self, sql, params=()):
        with self._lock:
            cursor = self._connect().execute(sql, params)
            names = [d[0] for d in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]

    def by_id(self, node_id):
        rows = self._rows("SELECT * FROM nodes WHERE node_id = ?", (node_id,))
        return rows[0] if rows else None

    def all(self):
        """Every remembered node, most recently heard first."""
        return self._rows("SELECT * FROM nodes ORDER BY last_heard DESC")

    def by_short_name(self, short_name):
        """Every remembered node answering to a short name, most recent first."""
        return self._rows("SELECT * FROM nodes WHERE LOWER(short_name) = LOWER(?) "
                          "ORDER BY last_heard DESC", (short_name,))
