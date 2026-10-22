"""Run what the generator produced: its own tests, and the application itself, on this computer only.

The generated runtime (see runtime_generation) is a standard-library Python server with SQLite and server-side role checks. Here it is
written to a dedicated temporary directory and started as a separate process bound to 127.0.0.1 with its own isolated database. This is
a local preview of a REAL running application, not production hosting: demo identities are the runtime's own synthetic ones.

Only an approved revision is ever launched (the runtime itself also refuses an unapproved specification).
The backend is compiler-owned. A saved, build-checked model frontend can run in the
browser on that separate local runtime origin; model source never runs in Python.
"""

from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

PORTS = range(8100, 8200)
STARTUP_SECONDS = 12
TEST_SECONDS = 120


class LaunchError(RuntimeError):
    """The application could not be started or tested. The message is safe to show."""


def local_runtime_available() -> bool:
    """A serverless function cannot publish a long-lived loopback preview server."""
    return not (os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))


@dataclass
class Running:
    process: subprocess.Popen
    port: int
    revision: int
    code_dir: Path
    data_dir: Path
    log: Path
    started: float = field(default_factory=time.time)


def _slug(project_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", project_id.lower()).strip("-")[:40] or "project"


def _free_port() -> int:
    for port in PORTS:
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise LaunchError("No free local port is available for the generated application.")


def _write(files: dict[str, bytes], directory: Path) -> None:
    if directory.exists():
        shutil.rmtree(directory)
    for name, content in files.items():
        target = (directory / name).resolve()
        if directory.resolve() not in target.parents:
            raise LaunchError("The generated files contain an unsafe path.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


class RuntimeManager:
    def __init__(self) -> None:
        self._running: dict[str, Running] = {}
        self._lock = threading.RLock()
        self._test_slots = threading.BoundedSemaphore(2)
        atexit.register(self.stop_all)

    def _alive(self, project_id: str) -> Running | None:
        item = self._running.get(project_id)
        if item and item.process.poll() is not None:
            self._running.pop(project_id, None)
            return None
        return item

    def status(self, project_id: str, current_revision: int) -> dict:
        if not local_runtime_available():
            return {
                "running": False,
                "available": False,
                "reason": "Local application previews are unavailable on Vercel. Download the generated application for separate hosting.",
            }
        with self._lock:
            item = self._alive(project_id)
            if item is None:
                return {"running": False}
            return {
                "running": True,
                "url": f"http://127.0.0.1:{item.port}",
                "port": item.port,
                "revision": item.revision,
                "stale": item.revision != current_revision,
                "started_seconds_ago": int(time.time() - item.started),
            }

    def stop(self, project_id: str) -> bool:
        with self._lock:
            return self._stop(project_id)

    def _stop(self, project_id: str) -> bool:
        with self._lock:
            item = self._running.pop(project_id, None)
        if item is None:
            return False
        item.process.terminate()
        try:
            item.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            item.process.kill()
        shutil.rmtree(
            item.code_dir, ignore_errors=True
        )  # the generated files are rebuilt on every launch; the application's own data stays for the next one
        return True

    def stop_all(self) -> None:
        for project_id in list(self._running):
            self.stop(project_id)

    def launch(self, project_id: str, revision: int, files: dict[str, bytes]) -> dict:
        if not local_runtime_available():
            raise LaunchError("Local application previews are unavailable on Vercel.")
        with self._lock:
            return self._launch(project_id, revision, files)

    def _launch(self, project_id: str, revision: int, files: dict[str, bytes]) -> dict:
        self.stop(project_id)
        root = Path(tempfile.gettempdir())
        name = _slug(project_id)
        code_dir = root / f"noordveld-generated-{name}-r{revision}"
        data_dir = root / f"studio-runtime-{name}-r{revision}"
        _write(files, code_dir)
        log = code_dir / "server.log"
        port = _free_port()
        with log.open("wb") as sink:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "runtime/server.py",
                    "--demo",
                    "--data-dir",
                    str(data_dir),
                    "--port",
                    str(port),
                ],
                cwd=code_dir,
                stdout=sink,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
        deadline = time.time() + STARTUP_SECONDS
        while time.time() < deadline:
            if process.poll() is not None:
                raise LaunchError(
                    "The generated application stopped while starting: "
                    + (log.read_text(errors="replace").strip().splitlines() or ["no output"])[-1][
                        :300
                    ]
                )
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/demo-users", timeout=1
                ) as response:
                    if response.status == 200:
                        json.loads(response.read())
                        break
            except Exception:  # not listening yet
                time.sleep(0.25)
        else:
            process.kill()
            raise LaunchError("The generated application did not start in time.")
        with self._lock:
            self._running[project_id] = Running(process, port, revision, code_dir, data_dir, log)
        return self.status(project_id, revision)

    def test(self, project_id: str, revision: int, files: dict[str, bytes]) -> dict:
        if not self._test_slots.acquire(blocking=False):
            raise LaunchError("Both local test workers are busy. Retry after a current run finishes.")
        try:
            return self._test(project_id, revision, files)
        finally:
            self._test_slots.release()

    def _test(self, project_id: str, revision: int, files: dict[str, bytes]) -> dict:
        if not local_runtime_available():
            raise LaunchError(
                "Generated application tests must run in a build worker or local development environment."
            )
        root = Path(tempfile.gettempdir())
        code_dir = Path(
            tempfile.mkdtemp(
                prefix=f"noordveld-generated-{_slug(project_id)}-r{revision}-tests-", dir=root
            )
        )
        _write(files, code_dir)
        started = time.time()
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "runtime",
                    "-p",
                    "test_runtime.py",
                    "-v",
                ],
                cwd=code_dir,
                capture_output=True,
                text=True,
                timeout=TEST_SECONDS,
            )
        except subprocess.TimeoutExpired:
            raise LaunchError("The generated tests did not finish in time.") from None
        finally:
            shutil.rmtree(code_dir, ignore_errors=True)
        output = (result.stdout + result.stderr).strip()
        ran = re.search(r"Ran (\d+) tests?", output)
        lines = output.splitlines()
        cases = [line for line in lines if re.search(r"\.\.\. (ok|FAIL|ERROR|skipped)", line)]
        passed_count = sum(bool(re.search(r"\.\.\. ok$", line)) for line in cases)
        skipped_count = sum("... skipped" in line for line in cases)
        failed_count = sum(bool(re.search(r"\.\.\. (FAIL|ERROR)$", line)) for line in cases)
        return {
            "passed": result.returncode == 0,
            "ran": int(ran[1]) if ran else 0,
            "seconds": round(time.time() - started, 1),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "cases": cases,
            "output_tail": "\n".join(lines[-25:]),
            "output": output[-100_000:],
            "output_truncated": len(output) > 100_000,
        }


manager = RuntimeManager()
