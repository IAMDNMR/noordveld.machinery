"""Run tests without .env loading or remote connections: python scripts/test_offline.py [pytest args]."""
import os
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.core.config as config

config._load_env_file = lambda *args: None
for key in list(os.environ):
    if any(part in key for part in ('API_KEY', 'NEO4J', 'RUN_GRAPH', 'RUN_LLM', 'VERCEL', 'DOMAIN_GRAPH')):
        os.environ.pop(key, None)
os.environ['APP_ENV'] = 'local'
config.get_settings.cache_clear()
original_connect = socket.socket.connect


def isolated_connect(self, address):
    # Windows asyncio implements its internal wakeup with a loopback socket pair.
    if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1', 'localhost'):
        raise RuntimeError('External network disabled for isolated verification')
    return original_connect(self, address)


socket.socket.connect = isolated_connect
import pytest

raise SystemExit(pytest.main(sys.argv[1:] or ['tests', '-q', '--tb=short']))
