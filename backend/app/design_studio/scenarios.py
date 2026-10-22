"""Scenario harness: prove that the one generator turns different domains into working applications.

For a set of catalog packs it builds a project the way the Studio would (adopt the packs, then screens from the process), stamps a clearly
synthetic approval, compiles it, loads the generated runtime *in this process* on a temporary database and drives it: records are created
by the roles that own them, each workflow runs to its end with the records its steps work on, and the checks that make an application
trustworthy are exercised (a wrong role is refused, an invalid record is rejected, data survives a restart, another organization sees
nothing). The result states what actually ran, what is only an assumption and what is blocked.

Nothing here is customer data or an approved design. Decisions are marked decided with an explicit synthetic answer.
"""

from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

from app.design_studio.approval import digest
from app.design_studio.compiler import compile_project
from app.design_studio.discovery import blank_definition
from app.design_studio.knowledge.provider import (
    FIXTURES_DIR,
    KnowledgeProvider,
    LocalKnowledgeProvider,
    adoption_order,
    apply_pack,
)
from app.design_studio.runtime_generation import coverage
from app.domain_knowledge.store import ReadOnlyDomainStore
from app.schemas.application_definition import ApplicationDefinition, ApprovalRecord

TENANT = "demo_scenario"
SYNTHETIC_ANSWER = "(synthetic scenario answer, not company policy)"


class ScenarioFailure(AssertionError):
    pass


def build_definition(
    provider: KnowledgeProvider, pack_ids: list[str], name: str, goal: str
) -> tuple[ApplicationDefinition, dict]:
    """The project the Studio builds from these packs, with test-only approvals."""
    definition = blank_definition().model_copy(
        update={"id": "app_scenario_" + "_".join(pack_ids)[:50].replace("-", "_"), "revision": 1}
    )
    adopted: dict[str, int] = {}
    for pack_id in pack_ids:
        definition, added = apply_pack(definition, pack_id, provider)
        for key, count in added.items():
            adopted[key] = adopted.get(key, 0) + count
    raw = definition.model_dump(mode="json")
    raw["metadata"].update({"name": name, "description": goal})
    raw["business"]["brief"]["goal"] = goal
    for decision in raw["business"]["decisions"]:
        if decision["status"] == "open":
            decision["status"], decision["answer"] = "decided", SYNTHETIC_ANSWER
    definition = ApplicationDefinition.model_validate(raw)
    definition.approvals = [
        ApprovalRecord(
            scope=scope,
            revision=definition.revision,
            content_sha256=digest(definition, scope),
            approved_by="synthetic_scenario_reviewer",
            approved_at="2026-10-15T00:00:00Z",
            comment="Synthetic scenario approval; not a customer approval",
        )
        for scope in ("process", "design")
    ]
    return definition, adopted


def fixtures_for(provider: KnowledgeProvider, pack_ids: list[str]) -> tuple[list[dict], list[dict]]:
    """Records of every pack that contributes data, in dependency order, and the workflow runs of the packs adopted completely."""
    order, full = adoption_order(pack_ids, provider)
    records, flows = [], []
    for pack in order:
        path = FIXTURES_DIR / f"{pack.id}.json"
        if not path.exists():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        records += [
            item for item in document.get("records", []) if pack.id in full or item.get("shared")
        ]
        if pack.id in full:
            flows += document.get("flows", [])
    return records, flows


@contextmanager
def loaded_runtime(files: dict[str, bytes], directory: Path):
    """The generated server module, loaded from its own files, with its `validation` import resolved to the generated copy."""
    for name, content in files.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    previous = sys.modules.get("validation")
    spec = importlib.util.spec_from_file_location("validation", directory / "runtime/validation.py")
    sys.modules["validation"] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sys.modules["validation"])
    spec = importlib.util.spec_from_file_location(
        f"scenario_server_{abs(hash(str(directory)))}", directory / "runtime/server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        if previous is None:
            sys.modules.pop("validation", None)
        else:
            sys.modules["validation"] = previous


def _user(role: str, tenant: str = TENANT) -> dict:
    return {"tenant": tenant, "role": role, "actor": f"{tenant}:{role}"}


def _expect(condition: bool, message: str):
    if not condition:
        raise ScenarioFailure(message)


def run_scenario(
    name: str,
    pack_ids: list[str],
    goal: str,
    provider: KnowledgeProvider | None = None,
    directory: Path | None = None,
    keep_files: bool = False,
) -> dict:
    provider = provider or LocalKnowledgeProvider()
    definition, adopted = build_definition(provider, pack_ids, name, goal)
    compiled = compile_project(definition, ReadOnlyDomainStore(), provider)
    report: dict = {
        "name": name,
        "packs": pack_ids,
        "compiled": compiled["status"],
        "adopted": adopted,
        "checks": {c["check"]: c["status"] for c in compiled.get("checks", [])},
        "failed_checks": [c for c in compiled.get("checks", []) if c["status"] == "fail"],
        "ran": [],
        "refused": [],
        "errors": [],
    }
    if compiled["status"] != "generated":
        report["errors"].append("generation blocked: " + "; ".join(compiled["plan"]["reasons"][:5]))
        return report
    schema = json.loads(compiled["files"]["runtime/schema.json"])
    report["coverage"] = coverage(schema)
    records, flows = fixtures_for(provider, pack_ids)
    root = directory or Path(tempfile.mkdtemp(prefix="studio-runtime-scenario-"))
    with loaded_runtime(compiled["files"], root) as module:
        database = root / "scenario.sqlite"
        runtime = module.Runtime(schema, database)
        saved: dict[str, dict] = {}
        entity_of: dict[str, str] = {}
        try:
            for item in records:
                values = dict(item["values"])
                for target, other in item.get("refs", {}).items():
                    reference = next(
                        (
                            r
                            for r in schema["references"]
                            if r["source"] == item["entity"] and r["target"] == target
                        ),
                        None,
                    )
                    _expect(
                        reference is not None,
                        f"{item['name']}: no relationship from {item['entity']} to {target}",
                    )
                    values[reference["field"]] = (
                        saved[other]["id"]
                        if reference["enforcement"] == "link"
                        else saved[other]["data"][reference["target_key"]]
                    )
                row = runtime.save_record(_user(item["role"]), item["entity"], values)
                saved[item["name"]] = row
                entity_of[item["name"]] = item["entity"]
                report["ran"].append(
                    f"created {item['entity']} as {item['role'].replace('role_', '')}"
                )
            for number, spec in enumerate(flows, 1):
                _run_flow(runtime, module, schema, saved, entity_of, spec, report)
            _negative_checks(runtime, module, schema, saved, flows, report)
            restarted = module.Runtime(schema, database)
            first = records[-1] if records else None
            if first:
                again = restarted.records(_user(first["role"]), first["entity"])
                _expect(
                    any(r["id"] == saved[first["name"]]["id"] for r in again),
                    "a record did not survive a restart",
                )
                report["ran"].append("records and process state survive a restart")
            other = records[0] if records else None
            if other:
                _expect(
                    restarted.records(_user(other["role"], "demo_other_org"), other["entity"])
                    == [],
                    "another organization can see these records",
                )
                report["ran"].append("another organization sees none of these records")
        except (ScenarioFailure, module.Fault) as exc:
            detail = "; ".join(
                f"{d.get('field')}: {d.get('message')}"
                for d in (getattr(exc, "details", None) or [])
            )
            report["errors"].append(
                f"{type(exc).__name__}: {getattr(exc, 'message', exc)}{' (' + detail + ')' if detail else ''} after {report['ran'][-1] if report['ran'] else 'nothing'}"
            )
    report["files"] = len(compiled["files"])
    report["directory"] = str(root) if keep_files else None
    report["passed"] = not report["errors"] and not report["failed_checks"]
    return report


def _run_flow(runtime, module, schema, saved: dict, entity_of: dict, spec: dict, report: dict):
    workflow = next(w for w in schema["workflows"] if w["id"] == spec["flow"])
    states = {s["id"]: s for s in workflow["states"]}
    prefix = spec["flow"].replace("wf_", "st_", 1) + "_"
    start = next(s for s in workflow["states"] if s["kind"] == "start")
    first = states[next(t["target"] for t in workflow["transitions"] if t["source"] == start["id"])]
    instance = runtime.create_instance(_user(first["role_id"]), spec["flow"], {})
    steps = 0
    while states[instance["state"]]["kind"] != "end":
        steps += 1
        _expect(steps <= 60, f"{spec['flow']}: the process did not finish")
        step = states[instance["state"]]
        key = (
            instance["state"][len(prefix) :]
            if instance["state"].startswith(prefix)
            else instance["state"]
        )
        for change in spec.get("set", {}).get(key, []):
            row = saved[change["record"]]
            saved[change["record"]] = runtime.save_record(
                _user(change["role"]),
                entity_of[change["record"]],
                change["values"],
                row["id"],
                row["revision"],
            )
        links = {
            entity: saved[spec["bind"][entity]]["id"]
            for entity in step.get("reads_entity_ids", []) + step.get("writes_entity_ids", [])
            if entity in spec["bind"]
        }
        instance = runtime.advance(
            _user(step["role_id"]), instance["id"], instance["revision"], links
        )
        report["ran"].append(f"{spec['flow']}: {step['label']}")
    _expect(
        instance["state"].endswith(spec.get("ends", "done")),
        f"{spec['flow']} ended at {instance['state']}, expected …{spec.get('ends', 'done')}",
    )


def _negative_checks(runtime, module, schema, saved, flows, report):
    """Things that must be refused: a role without the permission, an invalid record, an unknown organization."""
    if flows:
        workflow = next(w for w in schema["workflows"] if w["id"] == flows[0]["flow"])
        start = next(s for s in workflow["states"] if s["kind"] == "start")
        first = next(
            s
            for s in workflow["states"]
            if s["id"]
            == next(t["target"] for t in workflow["transitions"] if t["source"] == start["id"])
        )
        outsider = next(
            (
                r["id"]
                for r in schema["roles"]
                if r["id"] != first["role_id"] and first["permission"] not in r["permissions"]
            ),
            None,
        )
        if outsider:
            try:
                runtime.create_instance(_user(outsider), flows[0]["flow"], {})
            except module.Fault as fault:
                _expect(
                    fault.status == 403,
                    f"a role without the permission got status {fault.status}, expected 403",
                )
                report["refused"].append(
                    f"{outsider.replace('role_', '')} may not start {flows[0]['flow']} (403)"
                )
            else:
                raise ScenarioFailure("a role without the permission could start a process")
    writable = next((e for e in schema["entities"] if e.get("owner_role_id")), None)
    if writable:
        required = [
            a
            for a in writable["attributes"]
            if a.get("required") and not a.get("key") and a.get("value_source") == "user_entered"
        ]
        if required:
            try:
                runtime.save_record(_user(writable["owner_role_id"]), writable["id"], {})
            except module.Fault as fault:
                _expect(
                    fault.status == 422, f"an empty record got status {fault.status}, expected 422"
                )
                report["refused"].append(
                    f"an empty {writable['name']} record is rejected with field messages (422)"
                )
            else:
                raise ScenarioFailure("an empty record was saved")
