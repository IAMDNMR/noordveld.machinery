"""Logging setup. One format, no secrets: connection details and query parameters are never logged at INFO."""
from __future__ import annotations

import logging


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", force=True)
    # the driver reports expected schema notices (e.g. a label that does not exist yet) at WARNING; they are noise here
    logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
    logging.getLogger("neo4j").setLevel(logging.WARNING)
