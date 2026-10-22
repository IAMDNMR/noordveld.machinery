"""Fail-closed approval contract for future Design Studio graph mutations.

No production approval source or graph writer is wired here. A proposed change is
never equivalent to permission to execute it.
"""

from dataclasses import dataclass
import logging
from typing import Callable, TypeVar

T = TypeVar("T")
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphWriteRequest:
    operation: str
    targets: tuple[str, ...]
    changes: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class GraphWriteApproval:
    request: GraphWriteRequest
    actor_id: str
    approved: bool


class GraphWriteDenied(PermissionError):
    pass


def execute_approved(
    request: GraphWriteRequest,
    approval: GraphWriteApproval | None,
    actor_id: str,
    operation: Callable[[], T],
) -> T:
    """Only an exact, explicit approval by the actor can release a supplied writer.

    No route accepts client-supplied approval objects; a trusted approval source is
    required before this can ever be connected to production Neo4j operations.
    """
    if (
        not approval
        or not approval.approved
        or approval.actor_id != actor_id
        or approval.request != request
    ):
        log.info(
            "design graph write denied actor=%s operation=%s target_count=%d",
            actor_id,
            request.operation,
            len(request.targets),
        )
        raise GraphWriteDenied("Specific approval is required for this graph change")
    log.info(
        "design graph write approved actor=%s operation=%s target_count=%d",
        actor_id,
        request.operation,
        len(request.targets),
    )
    try:
        result = operation()
    except Exception:
        log.exception(
            "design graph write failed actor=%s operation=%s", actor_id, request.operation
        )
        raise
    log.info("design graph write completed actor=%s operation=%s", actor_id, request.operation)
    return result
