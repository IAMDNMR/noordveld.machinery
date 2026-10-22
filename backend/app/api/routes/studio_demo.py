"""The live demo of a project, opened from a signed link in its own tab. Read-only, no sign-in, nothing saved."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.api.routes.design_studio import Knowledge, Projects
from app.api.routes.studio_frontend import preview_html
from app.core.config import get_settings
from app.design_studio.demo_links import read_token

log = logging.getLogger(__name__)
router = APIRouter()

HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow"}
GONE = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    "<title>Demo unavailable</title><style>body{font:16px system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;"
    "margin:0;background:#f6f5f1;color:#14181a}main{max-width:26rem;padding:2rem;text-align:center}</style></head><body><main>"
    "<h1>This demo link is no longer available</h1><p>It has expired, or the project was changed or removed. "
    "Ask the owner for a new link.</p></main></body></html>"
)


@router.get("/demo/{token}", include_in_schema=False)
def live_demo(token: str, projects: Projects, knowledge: Knowledge):
    found = read_token(token, get_settings().session_secret)
    if found is None:
        return HTMLResponse(GONE, status_code=404, headers=HEADERS)
    owner_id, project_id = found
    try:
        current = projects.current(owner_id, project_id)
    except Exception:  # missing, trashed or storage trouble: the visitor only needs to know it is unavailable
        log.warning("live demo could not load project %s", project_id, exc_info=True)
        return HTMLResponse(GONE, status_code=404, headers=HEADERS)
    return HTMLResponse(preview_html(current, knowledge), headers=HEADERS)
