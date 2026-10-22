"""Retry a complete, database-only operation after a serialization rollback.

Only SQLSTATE 40001 guarantees a rollback. Connection failures and ambiguous
commits must never be replayed. Wrapped operations must have no external effects.
"""

from functools import wraps
import random
import time


def serialization_failure(error):
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if getattr(error, "sqlstate", None) == "40001":
            return True
        error = error.__cause__
    return False


def retry_serialization(operation):
    @wraps(operation)
    def run(*args, **kwargs):
        for attempt in range(5):
            try:
                return operation(*args, **kwargs)
            except Exception as error:
                if attempt == 4 or not serialization_failure(error):
                    raise
                time.sleep(random.uniform(0.01, 0.04) * 2**attempt)

    return run
