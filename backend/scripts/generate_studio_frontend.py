"""Generate and save a frontend for one existing SQL-backed Studio project.

Local operator tool. It preserves history, checks the revision and does not approve
the design or launch generated code. Provider credentials come from configuration.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.assistant.providers import get_studio_llm
from app.design_studio.postgres_activation import configured_stores
from app.design_studio.frontend_generation import generate_frontend


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_id")
    parser.add_argument("--expected-revision", type=int, required=True)
    parser.add_argument("--brief", default="")
    parser.add_argument("--resume-source", type=Path)
    args = parser.parse_args()
    get_settings()
    stores = configured_stores()
    if stores is None:
        raise SystemExit("SQL project storage is not configured.")
    with stores[0]._connection() as db:
        row = db.execute(
            "SELECT owner FROM studio_projects WHERE id=%s", (args.project_id,)
        ).fetchone()
    if not row:
        raise SystemExit("Project not found.")
    owner = row["owner"]
    project = stores[1].current(owner, args.project_id)
    if project.revision != args.expected_revision:
        raise SystemExit("Project revision changed; inspect it before retrying.")
    llm = get_studio_llm()
    if llm is None:
        raise SystemExit("Studio language model is unavailable.")
    print(
        json.dumps({"status": "generating", "project": project.id, "revision": project.revision}),
        flush=True,
    )
    recovered = (
        json.loads(args.resume_source.read_text(encoding="utf-8")) if args.resume_source else None
    )
    from app.design_studio.frontend_generation import input_digest
    from app.schemas.generated_frontend import FrontendProposal

    if recovered and (
        recovered["project_id"] != project.id or recovered["input_sha256"] != input_digest(project)
    ):
        raise SystemExit("The checkpoint belongs to another project or business contract.")
    artifact = generate_frontend(
        project,
        llm,
        args.brief,
        progress=lambda event: print(json.dumps(event), flush=True),
        initial_plan=FrontendProposal.model_validate(recovered["plan"]) if recovered else None,
        initial_sources=recovered["files"] if recovered else None,
    )
    candidate = project.model_copy(
        update={"generated_frontend": artifact, "frontend_required": True}
    )
    saved = stores[1].update(
        owner, project.id, args.expected_revision, candidate, "generate:frontend", owner
    )
    print(
        json.dumps(
            {
                "status": "saved",
                "project": saved.id,
                "revision": saved.revision,
                "pages": len(artifact.pages),
                "files": sorted(artifact.files),
                "source_sha256": artifact.source_sha256,
                "checks": artifact.checks,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
