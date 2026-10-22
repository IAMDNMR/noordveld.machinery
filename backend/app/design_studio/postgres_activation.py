"""Explicit PostgreSQL dependency selection; never creates or migrates a schema."""

from functools import lru_cache
import atexit
import logging
import os
from pathlib import Path
import tempfile
import certifi
from fastapi import HTTPException

from app.design_studio.activation import storage_candidate
from app.design_studio.postgres_store import PostgresProjectStore, PostgresStudioStore


def unavailable(message):
    return HTTPException(503, detail={"code": "studio_storage_unavailable", "message": message})


@lru_cache(maxsize=1)
def certificate_file(pem):
    """Allow hosted backends to supply the public CA through an environment variable."""
    import ssl

    # Validate before writing; never disable certificate or hostname checks.
    ssl.create_default_context(cadata=pem)
    with tempfile.NamedTemporaryFile(mode="w", suffix="-studio-ca.crt", delete=False) as output:
        output.write(pem)
        return str(Path(output.name))


@lru_cache(maxsize=1)
def connection_pool(dsn, ca_file, size):
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        conninfo=dsn,
        name="studio-sql",
        min_size=1,
        max_size=size,
        timeout=10,
        max_idle=120,
        kwargs={
            "row_factory": dict_row,
            "connect_timeout": 10,
            "options": "-c statement_timeout=15000",
            "sslmode": "verify-full",
            "sslrootcert": ca_file,
        },
        open=True,
    )
    atexit.register(pool.close)
    return pool


def connection_factory():
    if os.environ.get("DESIGN_STUDIO_POSTGRES_ENABLED") != "1":
        return None
    candidate = storage_candidate(os.environ)
    if candidate.mode == "disabled":
        return None
    if not candidate.syntactically_valid:
        raise unavailable(candidate.reason)
    # No DSN reaches an exception/log, and no network call occurs until this
    # opt-in dependency is requested. Schema identity is checked by both stores.
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise unavailable("Install the PostgreSQL driver before enabling this store.") from None
    dsn = os.environ["DESIGN_STUDIO_DATABASE_URL"]
    pem = os.environ.get("DESIGN_STUDIO_PG_CA_PEM")
    try:
        ca_file = (
            certificate_file(pem)
            if pem
            else os.environ.get("DESIGN_STUDIO_PG_CA_FILE", certifi.where())
        )
        if not pem and not os.path.isfile(ca_file):
            # A configured certificate file that is not on this machine must not silently send the Studio back to its rollback
            # storage. Verification stays on (verify-full); only the trust store changes, to the public bundle.
            logging.getLogger(__name__).warning("DESIGN_STUDIO_PG_CA_FILE is missing; verifying with the public CA bundle instead")
            ca_file = certifi.where()
    except Exception:
        raise unavailable("The configured SQL CA certificate is invalid.") from None
    try:
        pool_size = int(os.environ.get("DESIGN_STUDIO_SQL_POOL_SIZE", "5"))
        if not 0 <= pool_size <= 10:
            raise ValueError()
    except ValueError:
        raise unavailable("SQL connection pool size must be between 0 and 10.") from None

    def connect():
        if pool_size:
            return connection_pool(dsn, ca_file, pool_size).connection()
        return psycopg.connect(
            dsn,
            row_factory=dict_row,
            connect_timeout=10,
            options="-c statement_timeout=15000",
            sslmode="verify-full",
            sslrootcert=ca_file,
        )

    return connect


@lru_cache(maxsize=1)
def configured_stores():
    connect = connection_factory()
    if connect is None:
        return None
    try:
        return PostgresStudioStore(connect), PostgresProjectStore(connect)
    except Exception:
        raise HTTPException(
            503,
            detail={
                "code": "studio_storage_unavailable",
                "message": "SQL storage could not be verified. Check connectivity and apply the isolated Studio schema before activation.",
            },
        ) from None


@lru_cache(maxsize=1)
def configured_release_store():
    connect = connection_factory()
    if connect is None:
        return None
    from app.design_studio.postgres_releases import PostgresReleaseStore

    try:
        return PostgresReleaseStore(connect)
    except Exception:
        raise unavailable(
            "PostgreSQL release storage could not be verified. Apply the isolated release schema before activation."
        ) from None
