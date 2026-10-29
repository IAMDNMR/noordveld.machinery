"""Optional start-up warm-up: ask the Spark catalogue questions once, slowly, so the model's replies are already remembered.

Switched on with SPARK_WARMUP=1. It runs in a background thread, one question every few seconds, so it never competes with real
use for the model's per-minute quota, and it asks anonymously, so it reads and writes nothing of any user's.
"""

from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger("app.warmup")
PAUSE = 6.0  # seconds between questions: well inside the per-minute limit


def _run(app) -> None:
    from fastapi.testclient import TestClient

    from app.question_catalog import SPARK_CATALOG

    time.sleep(5)
    done = failed = 0
    with TestClient(app) as client:
        for group in SPARK_CATALOG:
            for question in group["questions"]:
                try:
                    reply = client.post(
                        "/api/v1/spark/conversation", json={"message": question}, timeout=120
                    )
                    done += reply.status_code == 200
                    failed += reply.status_code != 200
                except Exception:  # a warm-up must never take the app down
                    failed += 1
                time.sleep(PAUSE)
    log.info("spark warm-up finished: %d asked, %d failed", done, failed)


def start(app) -> None:
    threading.Thread(target=_run, args=(app,), name="spark-warmup", daemon=True).start()
