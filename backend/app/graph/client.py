"""Neo4j access: one driver per process, read-only queries, errors translated into GraphUnavailableError."""
from __future__ import annotations

import logging
import time
from typing import Any

import certifi
from neo4j import READ_ACCESS, GraphDatabase, TrustCustomCAs, unit_of_work
from neo4j.exceptions import AuthError, ClientError, DriverError, Neo4jError, ServiceUnavailable

from app.core.config import Settings
from app.core.exceptions import GraphUnavailableError

log = logging.getLogger(__name__)


class GraphClient:
    """Thin wrapper around the Neo4j driver. The API only reads the graph, so every session is READ_ACCESS."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._driver = None

    def _connect(self):
        s = self._settings
        if not s.graph_configured:
            raise GraphUnavailableError("Neo4j is not configured (NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD)")
        uri = s.neo4j_uri
        options: dict[str, Any] = {}
        if uri.startswith(("neo4j+s://", "bolt+s://")):
            # Full certificate verification, trusting the Mozilla root bundle (some machines lack the SSL.com root Aura uses)
            uri = uri.replace("+s://", "://", 1)
            options = {"encrypted": True, "trusted_certificates": TrustCustomCAs(certifi.where())}
        return GraphDatabase.driver(uri, auth=(s.neo4j_username, s.neo4j_password), **options)

    @property
    def driver(self):
        if self._driver is None:
            self._driver = self._connect()
        return self._driver

    def read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        """Run a read query and return its rows as dictionaries."""
        started = time.perf_counter()
        timeout = self._settings.neo4j_query_timeout
        try:
            with self.driver.session(database=self._settings.neo4j_database, default_access_mode=READ_ACCESS) as session:
                rows = session.execute_read(unit_of_work(timeout=timeout)(lambda tx: tx.run(query, params).data()))
        except GraphUnavailableError:
            raise
        except (ServiceUnavailable, AuthError, ClientError, DriverError, Neo4jError, OSError) as exc:
            # the class name is enough to diagnose; messages can echo connection details
            log.error("graph query failed: %s", type(exc).__name__)
            raise GraphUnavailableError(type(exc).__name__) from exc
        log.debug("graph query returned %d rows in %.0f ms", len(rows), (time.perf_counter() - started) * 1000)
        return rows

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
