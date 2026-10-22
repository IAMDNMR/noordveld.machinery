"""Generate fresh React source, build it without executing it, and retain the exact result.

There is deliberately no application UI template here. The only shared source is the
transport SDK and React bootstrap. Backend workflow execution remains authoritative.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
import logging
import os
import html
import base64
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile

from app.design_studio.frontend_repair import (
    build_errors,
    close_stylesheet,
    fix_indexed_tags,
    patch_file,
    with_hint,
)
from app.design_studio.ui_direction import (
    DESIGN_RULES,
    art_direction,
    css_variables,
    domain_reference,
    with_base,
)
from app.llm.base import LLMInvalidResponse
from app.schemas.application_definition import ApplicationDefinition
from app.schemas.generated_frontend import FrontendProposal, GeneratedFrontend
from app.design_studio.process import needs_screen
from app.design_studio.application_blueprint import application_blueprint, plan_gaps, preview_role

PLANNING_VERSION = 2

MAX_BUILD_ATTEMPTS = 7  # a multi-file app often needs several rounds: each round fixes every file the builder reported
MAX_REVIEW_ROUNDS = (
    2  # model fix passes after the first render; each one costs one to two model calls
)
# Files other modules import from: written before the pages so the pages use what they really export.
SHARED_MODULE = re.compile(
    r"(^src/(ui|shared|types|demoData)\.tsx?$)|/(components|hooks|utils|lib|shared)/|(format|helpers|api)\.tsx?$"
)
FRONTEND = Path(__file__).resolve().parents[3] / "frontend"
SDK = FRONTEND / "scripts/studio-sdk.tsx"
ENTRY = FRONTEND / "scripts/studio-entry.tsx"

SYSTEM = (
    """You are a senior product designer and React engineer creating a bespoke business application.
Write fresh application code for THIS business. You choose the information architecture, navigation,
layout, visual identity, typography hierarchy, color, icons and page compositions from the tasks and
users. Do not produce a generic dashboard plus identical CRUD forms with different names. A decision
workspace, receiving checklist, supplier directory and purchase document must feel purpose-built.
Use restrained professional styling, generous readable spacing, meaningful lucide icons, accessible
labels, visible keyboard focus, responsive CSS, useful empty states and loading/error feedback.
Do not add decorative marketing copy, fake KPIs, fake integrations, fabricated policy or fake records on your own.
Sample data only when the requirements or design_request ask for it: write src/demoData.ts exporting the records (entity id,
data, optional links) using only declared attribute IDs and exact enum values, a few clearly fictional records per entity,
and offer an explicit "Load demo data" button that creates them through createRecord in dependency order. Never load them
automatically, and show a visible "Demo data" label while they exist.
Use the exact entity IDs and attribute IDs from the business contract. Use @studio/sdk for ALL data,
identity, record writes and workflow actions. It is a transport library, not a page template.
Render a role selector using users/signIn in runtime mode, including when user is null.
users[].id is an identity identifier, distinct from users[].role. Pass users[].id to signIn; never build identities from app.roles.
Catch rejected async actions and surface their message; no unhandled promises. Runtime identity/permissions and
workflow state are server-owned. Do not simulate approvals or change process states client-side.
Use app.entities writable/creatable, instance.can_act/blocked and step.input_fields when deciding
which inputs/actions to expose. System-generated/calculated fields are read-only.
Provide record detail, create/edit where supported, searching/filtering, navigation, process work
and role-aware task actions. If a process needs linked records, provide selectors for those records.
App owns the selected page. Shared navigation components receive activePage and an onNavigate(pageId: string)
callback; they must invoke that callback instead of keeping a separate selected-page state.
Show the server's unsupported/blocked reasons clearly. Empty data is a valid initial state.
Every selectable role needs a useful first screen. If a role has no tasks in this application,
show a clear role-specific empty state and the relevant next navigation or identity switch.
Do not turn an unresolved business decision into a hard-coded amount, policy or client validation.
Only apply numeric limits and required fields present in the exact business contract.
RecordRow.id is an opaque STRING, never convert it to a number. Link records through the third
createRecord argument using relationship IDs (or an unambiguous target entity ID) mapped to record.id;
the SDK translates these to backend reference fields. app.references defines the exact contract.
updateRecord needs the actual record.id as its second argument; IDs are NOT stored in record.data.id.
To complete an existing task, first save its editable fields with updateRecord(entityId, record.id,
changedData, record.revision, {instance_id: instance.id, expected_revision: instance.revision}).
Then advanceWorkflow(instance.id, instance.revision, {[entityId]: record.id}). The third argument
contains entity IDs mapped to record IDs ONLY: never put field values, decisions, comments or dotted
entity.field keys in workflow links. New records must be linked in the advanceWorkflow call.
startWorkflow returns the first actionable instance; start it after creating the initial record,
then complete that task through advanceWorkflow using the returned instance and record link.
Expose only the outcomes in the saved field enum and process contract: do not invent return/reject actions.
Never cast {} to Instance or invent an instance/revision. Use an existing matching instance from
instances, or startWorkflow to obtain one. Never claim an action succeeded after a rejected call.
Use declared attribute enum values exactly. Coerce Data values to String(value ?? '') for text/select
inputs, Boolean for checked, and convert numeric inputs only for actual numeric attributes.
Return a JSON object ONLY with design_summary, pages, files. pages is an array of {id,title,purpose,
step_ids,entity_ids,surface_ids}; step_ids are exact workflowId/stateId strings. surface_ids bind the
application_blueprint responsibilities: cover every surface with its exact entity and step bindings.
A surface can be a dialog or panel within a page; it does not require a separate route. Declare only
what the page actually implements. Do not put every missing task on an unrelated dashboard.
Cover every actionable process
step. This is declared traceability; the UI must actually expose those tasks.
files contains src/App.tsx (default export a React component), src/styles.css, and optional local
src/*.tsx or src/*.ts modules. Import useStudio and types from '@studio/sdk'. Use React and lucide-react
only as packages. No CSS imports (Studio loads styles.css), external assets/fonts, network APIs,
browser globals, direct DOM manipulation, dynamic imports, inline HTML injection or build scripts.
For accessibility only, document.activeElement and document.addEventListener/removeEventListener
are allowed inside the isolated app frame; use React refs for focus and local DOM inspection.
Never touch document.body or document.documentElement (for example to lock page scroll): toggle a CSS class on an element React renders.
window, localStorage, sessionStorage, navigator and location are not available: keep UI state in React state.
Use CSS, inline SVG or lucide for visuals. No libraries beyond React and lucide-react.
All types must pass TypeScript. The SDK contract below is exact; do not invent its fields.
"""
    + DESIGN_RULES
)


class FrontendGenerationError(ValueError):
    pass


def require_builder() -> str:
    node = shutil.which("node")
    if (
        not node
        or not SDK.is_file()
        or not ENTRY.is_file()
        or not (FRONTEND / "node_modules/esbuild").is_dir()
    ):
        raise FrontendGenerationError(
            "This deployment can preview saved generated applications. Creating new frontend code requires the Studio Node build tools; generate it in the local Studio build environment."
        )
    return node


def input_digest(definition: ApplicationDefinition) -> str:
    raw = definition.model_dump(mode="json")
    return sha256(
        json.dumps(
            {name: raw[name] for name in ("metadata", "business", "workflow_definitions", "theme")},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def is_current(definition: ApplicationDefinition) -> bool:
    artifact = definition.generated_frontend
    return bool(artifact and artifact.input_sha256 == input_digest(definition))


def validate_proposal(proposal: FrontendProposal, definition: ApplicationDefinition, *, complete: bool = False) -> None:
    if sum(len(value) for value in proposal.files.values()) > 500_000:
        raise FrontendGenerationError("Generated source exceeds the size limit.")
    entities = {item.id for item in definition.business.entities}
    steps = {f"{w.id}/{s.id}" for w in definition.workflow_definitions for s in w.states}
    actionable = {
        f"{w.id}/{s.id}"
        for w in definition.workflow_definitions
        for s in w.states
        if needs_screen(s)
    }
    covered, errors = set(), []
    for page in proposal.pages:
        unknown_entities = set(page.entity_ids) - entities
        unknown_steps = set(page.step_ids) - steps
        if unknown_entities or unknown_steps:
            errors.append(
                f"Unknown page bindings: entities={sorted(unknown_entities)}, steps={sorted(unknown_steps)}. "
                f"Use only these entity IDs: {sorted(entities)} and these workflowId/stateId step IDs: {sorted(steps)}"
            )
        covered.update(page.step_ids)
    if actionable - covered:
        errors.append(
            "Pages omit process steps: " + ", ".join(sorted(actionable - covered))
        )
    if len({page.id for page in proposal.pages}) != len(proposal.pages):
        errors.append("Page IDs must be unique.")
    if complete:
        errors.extend(plan_gaps(proposal, definition))
    if errors:
        raise FrontendGenerationError("; ".join(errors))


def run_tool(script: Path, payload: dict, timeout: int) -> subprocess.CompletedProcess:
    """Run a Node tool and always come back. On timeout the whole process tree is killed: a browser or compiler child
    that outlives its parent would otherwise hold the output pipe open and block this thread for good."""
    process = subprocess.Popen(
        [require_builder(), str(script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=FRONTEND,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        stdout, stderr = process.communicate(json.dumps(payload), timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, timeout=30
            )
        else:
            process.kill()
        process.stdout.close()
        process.stderr.close()
        process.wait(timeout=30)
        raise
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)


def focus(files: dict[str, str], name: str) -> str:
    """What a repair of one file needs: that file in full and only the names the other files export. Sending every source
    made each repair call ten times larger, slow, and prone to dropped connections."""
    others = module_contracts({other: text for other, text in files.items() if other != name})
    return (
        "\nACTUAL TYPES AND COMPONENT PROPS EXPORTED BY OTHER FILES:\n"
        + json.dumps(others)
        + "\nCURRENT "
        + name
        + ":\n"
        + files.get(name, "")
    )


def module_contracts(files: dict[str, str]) -> dict[str, str]:
    """Read declarations with the installed TypeScript parser, without running source."""
    try:
        result = run_tool(FRONTEND / 'scripts/studio-source-contracts.mjs', {"files": files}, 20)
        contracts = json.loads(result.stdout)
        if result.returncode or not isinstance(contracts, dict):
            raise ValueError('No source contracts returned')
        return contracts
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise FrontendGenerationError('The generated module contracts could not be read.') from exc


def symbol_usages(files: dict[str, str], names: set[str], exclude: str) -> dict[str, str]:
    """Show actual caller props/arguments when repairing a shared declaration."""
    if not names:
        return {}
    pattern = re.compile(r'\b(?:' + '|'.join(re.escape(name) for name in sorted(names)) + r')\b')
    snippets = {}
    for path, source in files.items():
        if path == exclude or not path.endswith(('.ts', '.tsx')):
            continue
        lines = source.splitlines()
        hits = [i for i, line in enumerate(lines) if pattern.search(line) and not line.lstrip().startswith('import ')][:3]
        if hits:
            snippets[path] = '\n...\n'.join('\n'.join(lines[max(0, i - 1):i + 10]) for i in hits)
    return snippets


def errors_for(report: str, name: str) -> str:
    lines = [with_hint(line) for line in report.splitlines() if name in line]
    return "\n".join(lines) or report[:30000]


def build_source(files: dict[str, str]) -> dict:
    try:
        result = run_tool(FRONTEND / "scripts/build-studio-frontend.mjs", {"files": files}, 90)
        output = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise FrontendGenerationError("Frontend builder could not complete its checks.") from exc
    if result.returncode or output.get("error"):
        raise FrontendGenerationError(output.get("error", "Frontend build failed."))
    return output


def guard_open_business_limits(definition: ApplicationDefinition, files: dict[str, str]) -> None:
    """An unresolved owner decision must not silently become a numeric UI policy."""
    open_limits = [
        decision.question
        for decision in definition.business.decisions
        if decision.status == "open"
        and re.search(
            r"spend|cost|price|budget|amount|limit|threshold|approval", decision.question, re.I
        )
    ]
    if not open_limits:
        return
    comparison = re.compile(r"(?:[<>]=?\s*\d{4,}|\b\d{4,}\s*[<>]=?)")
    policy_literal = re.compile(
        r"(?:policy\s+limit|approval\s+threshold|approval\s+limit)\s*[:=]\s*[$€£]?\s*\d", re.I
    )
    monetary = re.compile(r"spend|cost|price|budget|amount|total|limit|threshold", re.I)
    for name, source in files.items():
        if not name.endswith((".ts", ".tsx")):
            continue
        for number, line in enumerate(source.splitlines(), 1):
            if (comparison.search(line) and monetary.search(line)) or policy_literal.search(line):
                raise FrontendGenerationError(
                    f"{name}: Unresolved business limit used as a numeric UI rule "
                    f"[line {number}: {line.strip()[:100]}]. "
                    "Show the open decision without applying a threshold. "
                    f"Owner question: {open_limits[0]}"
                )


# Last in every repair prompt: with a long prompt the model otherwise answers in the plan's JSON shape instead of the file.
RAW_SOURCE_REMINDER = "\nReturn ONLY the complete corrected raw source of {name}: no JSON, no commentary, no code fences."


def clean_source(text: str, name: str) -> str:
    """Unwrap known source-response shapes, always bound to the requested file.

    Unknown prose or edit instructions remain invalid source for the build gate.
    """
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:tsx|ts|typescript|jsx|javascript|css|json)?\s*\n([\s\S]*?)\n```", stripped)
    if fence:
        text = stripped = fence.group(1)
    if stripped.startswith("{"):
        try:
            response = json.loads(stripped)
        except ValueError:
            return text
        if not isinstance(response, dict):
            return text
        files = response.get("files")
        if isinstance(files, dict) and isinstance(files.get(name), str):
            return files[name]
        if response.get("file", name) == name:
            for key in ("source", "content", "code"):
                if isinstance(response.get(key), str):
                    return response[key]
    return text


def used_classes(sources: dict[str, str]) -> list[str]:
    """Class names written in className attributes, so the stylesheet can cover every one of them."""
    names: set[str] = set()
    for path, text in sources.items():
        if not path.endswith(".tsx"):
            continue
        for expression in re.findall(
            r"className\s*=\s*(\"[^\"]*\"|\{(?:[^{}]|\$\{[^}]*\})*\})", text
        ):
            # Quoted strings, plus the fixed text of template literals (the part outside ${...}).
            literals = re.findall(r"([\"'])([^\"']*)\1", expression)
            parts = [text for _, text in literals] + [
                re.sub(r"\$\{[^}]*\}", " ", t) for t in re.findall(r"`([^`]*)`", expression)
            ]
            for literal in parts:
                names.update(
                    w
                    for w in literal.split()
                    if re.fullmatch(r"[a-zA-Z_][\w-]*", w) and not w.endswith("-")
                )
    return sorted(names)


def merge_module_repair(original: str, response: str, name: str, missing: set[str]) -> str | None:
    """A requested export suffix sometimes arrives as a complete replacement.

    Never concatenate two application modules or accept a response that does not
    define the requested exports. The ordinary build still checks the result.
    """
    from app.design_studio.frontend_imports import exports

    addition = clean_source(response, name).strip()
    declared = exports(addition)
    existing = exports(original)
    if not missing <= declared:
        return None
    definitions = re.search(r'\b(?:function|class|const|let|interface|type|enum)\s+\w+', addition)
    replacement = 'export default' in addition or (definitions and existing.intersection(declared))
    if replacement:
        if 'export default' in original and 'export default' not in addition:
            return None
        return addition if existing <= declared else None
    return original.rstrip() + '\n\n' + addition + '\n'


def incomplete_source(source: str) -> bool:
    """Detect a token-limit cutoff without executing the returned code."""
    node = require_builder()
    checked = subprocess.run(
        [node, str(FRONTEND / "scripts/check-studio-syntax.mjs")],
        input=json.dumps({"source": source}),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    result = json.loads(checked.stdout)
    return not result["valid"] and result.get("at_end", False)


def generate_frontend(
    definition: ApplicationDefinition,
    llm,
    brief: str = "",
    progress=None,
    initial_plan=None,
    initial_sources=None,
) -> GeneratedFrontend:
    require_builder()
    from app.design_studio.compiler import references

    raw = definition.model_dump(mode="json")
    sdk = SDK.read_text(encoding="utf-8")
    contract = sdk[sdk.index("export type Data") : sdk.index("type Bootstrap")]
    contract += sdk[sdk.index("export type Studio") : sdk.index("const Context")]

    def compact(value):
        if isinstance(value, dict):
            return {
                key: compact(item)
                for key, item in value.items()
                if key not in {"origin", "provenance", "knowledge", "intake", "reviewed_sha256"}
            }
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value

    context = {
        "project": {
            name: compact(raw[name]) for name in ("metadata", "business", "workflow_definitions")
        },
        "design_request": brief,
        "domain_reference": domain_reference(definition),
        "application_blueprint": application_blueprint(definition),
    }
    # A retry of the same project and contract continues from the last saved draft instead of starting over.
    checkpoint = (
        Path(tempfile.gettempdir())
        / f"studio-frontend-v{PLANNING_VERSION}-{definition.id}-{input_digest(definition)[:16]}-{sha256(brief.encode()).hexdigest()[:8]}.json"
    )
    saved = None
    if initial_plan is None and checkpoint.is_file():
        try:
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            initial_plan = FrontendProposal.model_validate(saved["plan"])
            initial_sources = saved["files"]
        except (OSError, ValueError, KeyError):
            saved = None
    try:
        direction = (
            saved["direction"] if saved and saved.get("direction") else art_direction(llm, context)
        )
    except (ValueError, LLMInvalidResponse) as exc:
        raise FrontendGenerationError("The model could not produce a valid art direction.") from exc
    if progress:
        progress({"phase": "art_direction", "navigation": direction["navigation"]["pattern"]})
    prompt = json.dumps(
        {
            **context,
            "art_direction": direction,
            "sdk_types": contract,
            "runtime_references": [
                reference.model_dump() for reference in references(definition)[0]
            ],
            "allowed_page_bindings": {
                "entity_ids": [item.id for item in definition.business.entities],
                "step_ids": [
                    f"{w.id}/{s.id}" for w in definition.workflow_definitions for s in w.states
                ],
            },
            "notes": "Preview is local in-memory form interaction; running mode uses the generated Python backend. No records exist initially. Render useful empty states and creation actions.",
        },
        ensure_ascii=False,
    )
    planning = (
        SYSTEM
        + """
For this request return a DESIGN PLAN ONLY in that JSON shape. The files mapping
must contain file paths mapped to precise implementation instructions, NOT source code.
Choose concise modules including src/App.tsx and src/styles.css: one TSX module per page or workspace.
Share only components actually used by these pages. Do not generate a generic component library or unused dialogs.
Keep each source module below 220 lines; split shared controls into focused modules when needed rather than building
one oversized ui.tsx. Include explicit props and callback contracts in the plan so parent and child files agree.
Each feature module exports a default React component with NO required props; it gets
business data from useStudio. App imports these components and owns the navigation.
Navigation callbacks may be explicit optional props; document their exact signatures in the plan.
Specify the shared CSS class vocabulary in the plan so every file uses the same styling.
Include an identity selector, usable create/edit dialogs, record details and linked-record
selectors in the file responsibilities. Do not give every page the same composition.
"""
    )
    proposal = initial_plan
    base_prompt = prompt
    for attempt in range(3):
        try:
            proposal = proposal or FrontendProposal.model_validate(
                llm.studio_frontend(planning, prompt)
            )
            validate_proposal(proposal, definition, complete=True)
            if not {"src/App.tsx", "src/styles.css"} <= set(proposal.files):
                raise FrontendGenerationError(
                    "Plan must include src/App.tsx and src/styles.css. Split modules according to the required application responsibilities. Received: "
                    + ", ".join(sorted(proposal.files))
                )
            if any(
                not re.fullmatch(r"src/[a-zA-Z0-9_/-]+\.(tsx|ts|css)", path)
                or ".." in path
                or path in {"src/main.tsx", "src/studio-sdk.tsx"}
                for path in proposal.files
            ):
                raise FrontendGenerationError("Source paths must stay inside src/.")
            if progress:
                progress({"phase": "planned", "files": sorted(proposal.files), "pages": len(proposal.pages)})
            break
        except (ValueError, LLMInvalidResponse) as exc:
            rejected = proposal.model_dump_json() if proposal else "No valid structured plan was returned."
            if proposal:
                checkpoint.write_text(json.dumps({"plan": proposal.model_dump(), "files": {}, "direction": direction}), encoding="utf-8")
            proposal = None
            logging.getLogger(__name__).warning(
                "application plan rejected (attempt %d): %s", attempt + 1, str(exc)[:600]
            )
            if attempt == 2:
                raise FrontendGenerationError(
                    "The model could not produce a complete application plan: " + str(exc)
                ) from exc
            if progress:
                progress({"phase": "planning_repair", "attempt": attempt + 1})
            prompt = base_prompt + "\nREJECTED PLAN (preserve working pages and repair every missing responsibility in both pages and file instructions):\n" + rejected
            prompt += "\nPLANNING ERRORS:\n" + str(exc)
    if proposal is None:
        raise FrontendGenerationError("No application plan was returned.")
    prompt = base_prompt  # Rejected plans belong to planning repair, never to source-file instructions.
    plan = proposal.model_dump_json()
    source_system = (
        SYSTEM
        + """
This request writes ONE FILE. Return ONLY its complete raw source, no JSON or commentary.
Follow the shared design plan and SDK types. Keep the file below 220 lines and 5000 tokens.
Use default exports for local feature modules; no required props. All source must be complete,
including closing brackets. Use concise code and share small helpers within the file.
"""
    )
    sources = dict(initial_sources or {})

    def save_checkpoint():
        checkpoint.write_text(
            json.dumps(
                {
                    "project_id": definition.id,
                    "input_sha256": input_digest(definition),
                    "plan": proposal.model_dump(),
                    "direction": direction,
                    "files": sources,
                }
            ),
            encoding="utf-8",
        )

    save_checkpoint()
    if progress:
        progress({"phase": "checkpoint", "path": str(checkpoint)})

    def write_source(name: str, known: dict[str, str]) -> str:
        request = prompt + "\nDESIGN PLAN:\n" + plan
        request += "\nACTUAL MODULE CONTRACTS ALREADY WRITTEN (use these exact props and exports):\n" + json.dumps(module_contracts(known))
        request += "\nWRITE THIS FILE ONLY: " + name
        if name.endswith(".css"):
            # The stylesheet is written last, so it can be given the exact class names the components use.
            request += "\nA base layer already defines the :root colour, spacing, radius and type variables and the resets; do NOT repeat them."
            request += (
                " Write only layout and component rules that use var(--...). Variables: "
                + json.dumps(css_variables())
            )
            request += (
                "\nCLASS NAMES USED BY THE COMPONENTS (write a rule for every one): "
                + json.dumps(used_classes(known))
            )
        else:
            request += "\nImport from the files already written ONLY the names they really export. Page modules are written at the same time: import them by their path in the plan, as their default export."
        text = clean_source(llm.studio_frontend_file(source_system, request), name)
        if name.endswith(('.ts', '.tsx')):
            for module_attempt in range(3):
                header = module_contracts({name: text})[name]
                if header.startswith('This module does not parse') or re.search(r'(?m)^export\b', header):
                    break
                if module_attempt == 2:
                    raise FrontendGenerationError(f'{name}: the writer returned planning notes instead of an exported implementation. Retry to continue this file.')
                text = clean_source(llm.studio_frontend_file(source_system, request + '\nThe previous answer did not export an implementation. Return the complete source module, not comments or planning instructions.\n' + RAW_SOURCE_REMINDER.format(name=name)), name)
        for _ in range(0 if name.endswith(".css") else 2):
            if not incomplete_source(text):
                break
            suffix = getattr(llm, "studio_frontend_suffix", llm.studio_frontend_file)(
                "Complete a truncated React/TypeScript source file. Return ONLY the missing suffix after its last character. Do not repeat any existing code or use code fences. Close the file completely.",
                request + "\nEXISTING PREFIX (append after this):\n" + text,
            )
            text += suffix  # the cut can fall inside a word or string: continue exactly where it stopped
        return with_base(text, direction) if name.endswith(".css") else text

    # Shared modules (ui, hooks, helpers, demo data) are written first, together, so every page can see their real exports;
    # the pages and the shell are then written at the same time; the stylesheet comes last because it needs their class names.
    def write_all(names: list[str]) -> None:
        if not names:
            return
        known = dict(sources)
        with ThreadPoolExecutor(max_workers=min(5, len(names))) as pool:
            futures = {}
            for name in names:
                if progress:
                    progress({"phase": "writing", "file": name})
                futures[pool.submit(write_source, name, known)] = name
            try:
                for future in as_completed(futures):
                    sources[futures[future]] = future.result()
                    save_checkpoint()
            except BaseException:
                pool.shutdown(
                    wait=False, cancel_futures=True
                )  # one file failed: do not start the rest
                raise

    # Old checkpoints may contain a writer's comment-only plan instead of code.
    # Regenerate only those stubs; preserve real modules and repair syntax errors.
    for name, header in module_contracts(sources).items():
        if not header.startswith('This module does not parse') and not re.search(r'(?m)^export\b', header):
            sources.pop(name, None)
    pending = [name for name in proposal.files if name != "src/styles.css" and name not in sources]
    shared = [name for name in pending if name != "src/App.tsx" and SHARED_MODULE.search(name)]
    write_all(shared)
    write_all([name for name in pending if name not in shared])
    if "src/styles.css" not in sources:
        if progress:
            progress({"phase": "writing", "file": "src/styles.css"})
        sources["src/styles.css"] = write_source("src/styles.css", dict(sources))
        save_checkpoint()

    def wire_missing(files: dict[str, str], report: str) -> bool:
        """Wire imports that have one answer; ask the model once per module for definitions other files expect from it."""
        from app.design_studio.frontend_imports import wire_imports

        wired, missing = wire_imports(files, report)
        changed = wired != files
        files.update(wired)
        for module, names in missing.items():
            usage = [
                f"{name}:{number}: {line.strip()}"
                for name, text in files.items()
                for number, line in enumerate(text.splitlines(), 1)
                if any(re.search(rf"<{item}\b|\b{item}\(", line) for item in names)
            ][:60]
            request = (
                prompt + "\nDESIGN PLAN:\n" + plan + "\nCURRENT " + module + ":\n" + files[module]
            )
            request += (
                "\nOther files import these names from "
                + module
                + ", but it does not define them: "
                + ", ".join(sorted(names))
            )
            request += "\nHOW THEY ARE USED:\n" + "\n".join(usage)
            request += (
                "\nReturn ONLY new TypeScript/TSX code to APPEND to "
                + module
                + ": an exported definition for each of these names"
            )
            request += " that fits how it is used, using what the file already defines. No imports unless the file lacks them, no code fences."
            addition = getattr(llm, "studio_frontend_suffix", llm.studio_frontend_file)(
                source_system, request
            )
            repaired = merge_module_repair(files[module], addition, module, set(names))
            if repaired is None:
                continue
            files[module] = repaired
            changed = True
        return changed

    built = None
    for attempt in range(MAX_BUILD_ATTEMPTS):
        try:
            if progress:
                progress({"phase": "building", "attempt": attempt + 1})
            for name in sources:
                sources[name] = clean_source(sources[name], name)
                if name.endswith(".tsx"):
                    sources[name] = fix_indexed_tags(sources[name])
                elif name.endswith(".css"):
                    sources[name] = close_stylesheet(sources[name])
            guard_open_business_limits(definition, sources)
            built = build_source(sources)
            break
        except FrontendGenerationError as exc:
            if progress:
                progress({"phase": "repairing", "error": str(exc)[:3000]})
            if attempt == MAX_BUILD_ATTEMPTS - 1:
                raise FrontendGenerationError(
                    f"Frontend build still fails after {MAX_BUILD_ATTEMPTS - 1} repairs: "
                    + str(exc)[:3000]
                ) from exc
            if "TypeScript check failed" in str(exc) and wire_missing(sources, str(exc)):
                save_checkpoint()
                continue  # imports were wired or missing definitions written: build again before any file repair
            problems = build_errors(str(exc))
            affected = {name for name in problems if name in sources}
            if not affected:
                affected = {"src/styles.css"} if "Styles" in str(exc) else {"src/App.tsx"}
            for name in sorted(affected):
                cut_off = any(
                    "Unexpected end of file" in item["message"] for item in problems.get(name, [])
                )
                if not name.endswith(".css") and (cut_off or incomplete_source(sources[name])):
                    # A token-limit cutoff: only the missing end of the file has to be written.
                    request = prompt + "\nDESIGN PLAN:\n" + plan + focus(sources, name)
                    sources[name] += getattr(
                        llm, "studio_frontend_suffix", llm.studio_frontend_file
                    )(
                        "Return ONLY the missing suffix that completes this truncated source file after its last character; never repeat the prefix. No code fences.",
                        request + "\nAPPEND AFTER THE LAST CHARACTER OF " + name + " ABOVE.",
                    )
                elif not patch_file(
                    llm, sources, name, problems.get(name, [])
                ):
                    # Keep using focused edits as diagnostics advance; rewrite only when no edit applies.
                    request = prompt + "\nDESIGN PLAN:\n" + plan
                    request += focus(sources, name)
                    request += (
                        "\nREPAIR ONLY " + name + "\nBUILD ERRORS:\n" + errors_for(str(exc), name)
                    )
                    request += RAW_SOURCE_REMINDER.format(name=name)
                    sources[name] = clean_source(
                        llm.studio_frontend_file(source_system, request), name
                    )
                    if name.endswith(".css"):
                        sources[name] = with_base(sources[name], direction)
                save_checkpoint()
    assert built is not None

    def assemble(files: dict[str, str], output: dict) -> GeneratedFrontend:
        return GeneratedFrontend(
            **{**proposal.model_dump(), "files": files},
            input_sha256=input_digest(definition),
            source_sha256=sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
            provider=str(getattr(llm, "name", "configured-model")),
            generated_at=datetime.now(timezone.utc).isoformat(),
            bundle_js=output["js"],
            bundle_css=output["css"],
            checks=output["checks"],
            sdk_source=output.get("sdk_source", sdk),
            entry_source=output.get("entry_source", ENTRY.read_text(encoding="utf-8")),
        )

    # The build only proves the code compiles. Render it in a real browser, give the model the measurable defects and let it
    # fix them (bounded rounds), so visual problems are caught before a person ever sees the result.
    from app.design_studio.ui_quality import check_ui, describe

    artifact = assemble(sources, built)
    errors: list[dict] = []
    review_note = ""
    for round_number in range(MAX_REVIEW_ROUNDS + 1):
        try:
            report = check_ui(definition.model_copy(update={"generated_frontend": artifact}))
        except FrontendGenerationError as exc:
            raise FrontendGenerationError(
                "The generated interface could not be checked in a browser. Install the local browser build dependency and retry."
            ) from exc
        errors = [item for item in report["findings"] if item["severity"] == "error"]
        if progress:
            progress({"phase": "reviewing", "round": round_number, "errors": len(errors)})
        if not errors or round_number == MAX_REVIEW_ROUNDS:
            break
        candidate = dict(sources)
        # Render feedback identifies the affected surface; keep repair requests focused.
        targets = (
            ["src/styles.css"]
            if any(
                item["id"]
                in {
                    "unstyled-classes",
                    "horizontal-overflow",
                    "no-responsive-rules",
                    "small-touch-targets",
                    "navigation-overflow",
                    "navigation-unstyled",
                }
                for item in errors
            )
            else []
        )
        if any(item["id"].startswith("accessibility") for item in errors):
            targets.append("src/App.tsx")
        if any(item["id"] in {"navigation-accessibility", "dialog-focus"} for item in errors):
            targets.append("src/ui.tsx" if "src/ui.tsx" in candidate else "src/App.tsx")
        if any(item["id"].startswith("demo-data-") for item in errors):
            targets.extend(
                name
                for name, source in candidate.items()
                if name.endswith((".tsx", ".ts"))
                and re.search(
                    r"loadDemoData|loadSampleData|Load demo data|Load sample data", source
                )
            )
        if any(item["id"] == "role-empty" for item in errors):
            dashboard = next(
                (
                    name
                    for name in candidate
                    if re.search(r"dashboard|home|overview", name, re.I) and name.endswith(".tsx")
                ),
                "src/App.tsx",
            )
            targets.append(dashboard)
        if any(item["id"] == "navigation-no-change" for item in errors):
            targets.extend(name for name in candidate if name.endswith('.tsx') and re.search(r'App\.tsx$|Nav|Drawer|Rail', name))
        if any(item["id"] == "identity-switch-failed" for item in errors):
            targets.extend(name for name in candidate if name.endswith('.tsx') and re.search(r'App\.tsx$|Role|Identity|TopAppBar|Drawer', name))
        if not targets:
            targets = ["src/App.tsx"]
        targets = list(dict.fromkeys(targets))
        for name in targets:
            request = prompt + "\nDESIGN PLAN:\n" + plan + focus(candidate, name)
            request += (
                "\nFINDINGS FROM RENDERING THE APPLICATION IN A REAL BROWSER AT 375, 768 AND 1280px"
                " (fix every one and change nothing else):\n" + describe(errors)
            )
            if name.endswith(".css"):
                request += "\nCLASS NAMES USED BY THE COMPONENTS: " + json.dumps(
                    used_classes(candidate)
                )
            request += "\nREPAIR ONLY " + name + RAW_SOURCE_REMINDER.format(name=name)
            candidate[name] = clean_source(llm.studio_frontend_file(source_system, request), name)
            if name.endswith(".css"):
                candidate[name] = with_base(candidate[name], direction)
        try:
            guard_open_business_limits(definition, candidate)
            rebuilt = build_source(candidate)
        except FrontendGenerationError:
            break  # keep the last version that built; what remains is reported in the checks below
        sources, artifact = candidate, assemble(candidate, rebuilt)
        save_checkpoint()
    if errors:
        raise FrontendGenerationError(
            f"The generated interface still has {len(errors)} browser finding(s) after repair: "
            + "; ".join(item["message"] for item in errors[:5])
        )
    if not review_note:
        review_note = (
            f"UI review at 375, 768 and 1280px: {len(errors)} issue(s) remain. "
            + "; ".join(item["message"] for item in errors[:5])
            if errors
            else "UI review at 375, 768 and 1280px: no layout, styling or accessibility errors found."
        )
    checkpoint.unlink(missing_ok=True)  # finished: a later request starts a fresh design
    return artifact.model_copy(update={"checks": [*artifact.checks, review_note]})


def app_document(definition: ApplicationDefinition) -> str:
    """The application page itself (bundle + bootstrap data); the preview and the UI quality gate both render this."""
    artifact = definition.generated_frontend
    if not artifact:
        raise FrontendGenerationError("Generate the project frontend first.")
    from app.design_studio.compiler import references
    from app.design_studio.runtime_generation import unsupported_items

    app = {
        "name": definition.metadata.name,
        "project_id": definition.id,
        "entities": [
            {
                **entity.model_dump(mode="json"),
                "writable": True,
                "creatable": True,
                "attributes": [
                    {**attribute.model_dump(mode="json"), "options": attribute.enum}
                    for attribute in entity.attributes
                ],
                "relationships": [
                    {
                        **relationship.model_dump(mode="json"),
                        "target_entity_id": relationship.target,
                    }
                    for relationship in entity.relationships
                ],
            }
            for entity in definition.business.entities
        ],
        "workflows": [
            workflow.model_dump(mode="json") for workflow in definition.workflow_definitions
        ],
        "roles": {role.id: role.name for role in definition.business.roles},
        "unsupported": [item["text"] for item in unsupported_items(definition)],
        "references": [reference.model_dump() for reference in references(definition)[0]],
    }
    bootstrap = json.dumps({"mode": "preview", "app": app, "preview_role": preview_role(definition)}).replace("<", "\\u003c")
    # Opaque sandbox + CSP are the isolation boundary. AST checks are additional linting.
    policy = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
    document = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(policy, quote=True)}">'
        f"<title>{html.escape(definition.metadata.name)}</title>"
        f"<style>{artifact.bundle_css.replace('<', '\\3c ')}</style></head><body>"
        '<div id="app"></div>'
        f'<script id="studio-bootstrap" type="application/json">{bootstrap}</script>'
        f"<script>{artifact.bundle_js.replace('</', '<\\/')}</script></body></html>"
    )
    return document


def preview_document(definition: ApplicationDefinition) -> str:
    encoded = base64.b64encode(app_document(definition).encode()).decode()
    # A second, non-scripted shell also restricts navigation of the application frame.
    # The app cannot navigate itself to an external URL: its parent only embeds data:.
    outer_policy = "default-src 'none'; frame-src data:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(outer_policy, quote=True)}">'
        "<style>html,body{margin:0;height:100%}iframe{display:block;border:0;width:100%;height:100%}</style>"
        '</head><body><iframe sandbox="allow-scripts" title="Application workspace" '
        f'src="data:text/html;base64,{encoded}"></iframe></body></html>'
    )


def generated_files(definition: ApplicationDefinition) -> dict[str, bytes]:
    artifact = definition.generated_frontend
    if not artifact:
        return {}
    if not is_current(definition):
        raise FrontendGenerationError(
            "The generated frontend is out of date. Regenerate it before building this application."
        )
    files = {name: text.encode() for name, text in artifact.files.items()}
    # Use a local relative SDK import in the independently editable export.
    for name in list(files):
        if name.endswith((".tsx", ".ts")):
            depth = len(Path(name).parts) - 2
            relative = (
                "../" * depth + "./studio-sdk" if depth == 0 else "../" * depth + "studio-sdk"
            )
            files[name] = files[name].replace(b"@studio/sdk", relative.encode())
    files.update(
        {
            "src/studio-sdk.tsx": artifact.sdk_source.encode(),
            "src/main.tsx": artifact.entry_source.encode().replace(b"@studio/sdk", b"./studio-sdk"),
            "src/styles.css": artifact.bundle_css.encode(),
            "runtime/app.js": artifact.bundle_js.encode(),
            "runtime/app.css": artifact.bundle_css.encode(),
            "runtime/index.html": b'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Application workspace</title><link rel="stylesheet" href="/app.css"></head><body><div id="app"></div><script src="/app.js"></script></body></html>',
            "index.html": b'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/src/styles.css"></head><body><div id="app"></div><script type="module" src="/src/main.tsx"></script></body></html>',
            "design/frontend.json": json.dumps(
                {
                    "input_sha256": artifact.input_sha256,
                    "source_sha256": artifact.source_sha256,
                    "provider": artifact.provider,
                    "generated_at": artifact.generated_at,
                    "design_summary": artifact.design_summary,
                    "pages": [p.model_dump() for p in artifact.pages],
                    "checks": artifact.checks,
                    "limitations": "Build and type checks are not a functional or accessibility certification. Preview edits are temporary. Runtime permissions and process rules are server enforced.",
                },
                indent=2,
            ).encode(),
            "design/application-blueprint.json": json.dumps(application_blueprint(definition), indent=2).encode(),
        }
    )
    return files
