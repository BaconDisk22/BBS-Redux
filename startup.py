"""The startup announcement: one broadcast on a channel when the BBS comes online.

Kept out of server.py so it can be driven with a FakeTransport.
"""

import logging

from flows.base import MeshChannel
from transport import MAX_PAYLOAD


def announce_startup(transport, startup):
    """Send `startup.message` on `startup.channel_index` if enabled.

    Returns whether it was sent. A message over one payload is refused rather
    than split — a broadcast arrives as one packet or not at all.
    """
    if not startup.enabled:
        return False
    size = len(startup.message.encode("utf-8"))
    if size > MAX_PAYLOAD:
        logging.error(f"Startup announcement is {size} bytes; the limit is "
                      f"{MAX_PAYLOAD}. Not sent.")
        return False
    logging.info(f"Sending startup announcement to channel {startup.channel_index}")
    transport.send(startup.message, MeshChannel(index=startup.channel_index))
    return True
