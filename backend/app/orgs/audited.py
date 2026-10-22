"""Audit of the OUTCOME of protected operations.

The Design Studio gate decides whether a request is allowed and, for sensitive operations, marks it (`request.state.audit_pending`).
This route class runs the handler and then records one audit event with the actor, the action, the target, and how it ended: a refusal
by the handler or a failure is recorded as such, never as a success. The organization directory owns the audit table.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute


def _finish(request: Request, status: int) -> None:
    pending = getattr(request.state, "audit_pending", None)
    if not pending:
        return
    request.state.audit_pending = None
    outcome = "success" if status < 400 else "denied" if status in (401, 403, 404) else "failed"
    try:
        pending["directory"].record(
            pending["actor"],
            pending["action"],
            pending["org"],
            f"{pending['detail']} → HTTP {status}",
            target=pending["target"],
            outcome=outcome,
        )
    except Exception:  # noqa: BLE001  an audit write problem must never change the response the person gets
        pass


class AuditedRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                response = await original(request)
            except HTTPException as exc:
                _finish(request, exc.status_code)
                raise
            except Exception:
                _finish(request, 500)
                raise
            _finish(request, response.status_code)
            return response

        return handler
