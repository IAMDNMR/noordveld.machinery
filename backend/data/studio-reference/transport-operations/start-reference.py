"""Run the saved synthetic reference without overwriting an existing database."""

from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from zipfile import ZipFile


def main():
    snapshot = Path(__file__).resolve().parent
    temporary = Path(tempfile.gettempdir()).resolve()
    code = temporary / "noordveld-transport-reference-snapshot-r12"
    data = temporary / "studio-runtime-app-transport-operations-20261019-r12"
    code.mkdir(exist_ok=True)
    data.mkdir(exist_ok=True)
    with ZipFile(snapshot / "application.zip") as archive:
        for name in archive.namelist():
            destination = (code / name).resolve()
            if not destination.is_relative_to(code):
                raise ValueError("Archive contains an invalid file path")
        archive.extractall(code)
    database = data / "application.sqlite"
    if not database.exists():
        shutil.copy2(snapshot / "demo.sqlite", database)
    for port in range(8100, 8200):
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port))
            break
        except OSError:
            continue
    else:
        raise RuntimeError("No free local preview port between 8100 and 8199")
    print(f"Transport Operations: http://127.0.0.1:{port}/", flush=True)
    return subprocess.call(
        [
            sys.executable,
            str(code / "runtime/server.py"),
            "--demo",
            "--data-dir",
            str(data),
            "--port",
            str(port),
        ],
        cwd=code,
    )


if __name__ == "__main__":
    raise SystemExit(main())
