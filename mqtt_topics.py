"""Read side of the MQTT topic counter.

`monitor_mqtt_topics.py` runs as its own service and writes per-topic message
counts to a SQLite file. The BBS only reads them: `TopicCounts.top(limit)`
returns the busiest topics, or None when the counter has never run or its file
cannot be read — the Top Topics utility shows "unavailable" either way.
"""

import logging
import os
import sqlite3


class TopicCounts:
    def __init__(self, db_path):
        self._db_path = db_path

    def top(self, limit=15):
        """[(base_topic, subtopic, message_count), ...], busiest first, or None."""
        if not self._db_path or not os.path.exists(self._db_path):
            return None
        try:
            connection = sqlite3.connect(self._db_path)
            try:
                return connection.execute(
                    "SELECT base_topic, subtopic, message_count FROM topic_counts "
                    "ORDER BY message_count DESC LIMIT ?", (limit,)).fetchall()
            finally:
                connection.close()
        except sqlite3.Error as error:
            logging.error(f"Error reading MQTT topic stats: {error}")
            return None
