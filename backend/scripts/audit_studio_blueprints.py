"""Compile every shared blueprint and run its exported tests in isolated processes.

Uses synthetic scenario approvals only. Never connects to customer storage or
creates a real Studio project. Skips and unsupported capabilities remain visible.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.design_studio.compiler import compile_project
from app.design_studio.knowledge.provider import LocalKnowledgeProvider
from app.design_studio.runtime_launcher import RuntimeManager
from app.design_studio.scenarios import build_definition
from app.domain_knowledge.store import ReadOnlyDomainStore


def audit(pack_ids=None):
    provider = LocalKnowledgeProvider()
    manager = RuntimeManager()
    rows = []
    for pack in sorted(provider.packs(), key=lambda item: item.id):
        if pack.usage != "blueprint" or pack.company or (pack_ids and pack.id not in pack_ids):
            continue
        row = {"pack": pack.id, "version": pack.version, "workflow_count": len(pack.workflows)}
        try:
            if not pack.workflows:
                row.update(
                    status="data_reference",
                    reason="No standalone process in this shared foundation.",
                )
            else:
                definition, _ = build_definition(
                    provider, [pack.id], pack.title, "Isolated synthetic audit of " + pack.title
                )
                compiled = compile_project(definition, ReadOnlyDomainStore(), provider)
                row["compile_status"] = compiled["status"]
                row["checks"] = compiled["checks"]
                if compiled["status"] != "generated":
                    row.update(status="blocked", reasons=compiled["plan"]["reasons"])
                else:
                    tests = manager.test("audit-" + pack.id, definition.revision, compiled["files"])
                    row.update(status="passed" if tests["passed"] else "failed", tests=tests)
        except Exception as exc:
            row.update(status="error", error=f"{type(exc).__name__}: {exc}")
        rows.append(row)
        print(
            json.dumps(
                {
                    "pack": row["pack"],
                    "status": row["status"],
                    **{
                        key: row.get("tests", {}).get(key)
                        for key in ("passed_count", "failed_count", "skipped_count")
                    },
                }
            ),
            flush=True,
        )
    return {
        "scope": "Synthetic independent tests, not customer acceptance or production hosting",
        "results": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pack", action="append")
    args = parser.parse_args()
    result = audit(args.pack)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    sys.exit(any(row["status"] in ("blocked", "failed", "error") for row in result["results"]))
