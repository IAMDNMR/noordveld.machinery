"""Find processes a model drafted that a verified, adopted pack process already covers, and fold the draft into the verified one.

Evidence is deliberately strict, because merging the wrong two processes would change how a business runs. A drafted process
duplicates a verified one only when both are named for the same thing (the same head noun: "Run cycle *count*" and "Stock
*count*", "Process *return*" and "Sales *return*") AND they work on the same records or share requirement wording beyond that
noun. Processes that merely share a word ("Pack picked items" and "Pick and deliver an order") are not matched. A pair with no
shared noun is matched only when a pack's process-synonym catalogue lists the draft's name as another name for the verified
process ("replenishment" for "Automatic reorder"), see knowledge/process_synonyms.py; otherwise it is left for a person.
"""

from __future__ import annotations

import re

from app.design_studio.knowledge.process_synonyms import synonyms_of

STOP = frozenset("the a an of and to from into for with by on in at is are be as or not that this it its when then if each per all any".split())
# Words that describe how a process is run, not what it is about: "Automatic reorder", "Run cycle count", "Process return".
GENERIC = frozenset(
    "process processes management manage handling handle automatic automatically auto manual run create record general standard workflow new".split()
)
SHARED_WORDS = 1  # words in common beyond the head noun, when no record is shared
SHARED_RECORDS = 1


def stem(word: str) -> str:
    """A light plural/tense stem, consistent between "difference" and "differences", "quantity" and "quantities"."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if len(word) > 4 and (word.endswith(("ches", "shes")) or word[-3:-2] in ("s", "x", "z") and word.endswith("es")):
        return word[:-2]
    for suffix in ("ations", "ation", "ings", "ing", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def words(text: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP and len(w) > 2]


def head(name: str) -> str | None:
    """The noun a process is named for: its last meaningful word."""
    meaningful = [w for w in words(name) if w not in GENERIC]
    return meaningful[-1] if meaningful else None


def adopted_workflow_ids(definition, provider) -> set[str]:
    """Processes that came from an adopted (verified) pack rather than from a model."""
    found: set[str] = set()
    for link in definition.business.knowledge:
        try:
            found.update(workflow.id for workflow in provider.pack(link.pack_id).workflows)
        except Exception:  # a pack the provider cannot read proves nothing about its processes
            continue
    return found


def _profile(workflow, requirements: dict[str, str]) -> dict:
    steps = [s for s in workflow.states if s.kind not in ("start", "end")]
    text = [workflow.name, *(s.label for s in steps), *(requirements.get(r, "") for s in steps for r in s.requirement_ids)]
    return {
        "head": head(workflow.name),
        "name": {w for w in words(workflow.name) if w not in GENERIC},
        "vocabulary": {w for t in text for w in words(t)} - GENERIC,
        "records": {e for s in steps for e in [*s.reads_entity_ids, *s.writes_entity_ids]},
    }


def _alias(name_words: set[str], workflow_id: str, reviewed_only: bool = False):
    """The catalogue name of a verified process whose every word the draft's name contains, or None."""
    for name, entry in synonyms_of(workflow_id, reviewed_only):
        wanted = {w for w in words(name) if w not in GENERIC}
        if wanted and wanted <= name_words:
            return name, entry
    return None


def find_overlaps(definition, provider) -> list[dict]:
    """Drafted processes that duplicate a verified one: {duplicate, keep, because}. Each draft is matched to at most one process."""
    if provider is None or not definition.workflow_definitions:
        return []
    verified = adopted_workflow_ids(definition, provider)
    if not verified:
        return []
    requirements = {r.id: r.statement for r in definition.business.requirements}
    profiles = {w.id: (w, _profile(w, requirements)) for w in definition.workflow_definitions}
    found = []
    for draft_id, (draft, mine) in profiles.items():
        if draft_id in verified or mine["head"] is None:
            continue
        best = None
        for keep_id in verified:
            if keep_id not in profiles:
                continue
            keep, theirs = profiles[keep_id]
            records = mine["records"] & theirs["records"]
            shared = (mine["vocabulary"] & theirs["vocabulary"]) - {mine["head"]}
            alias = _alias(mine["name"], keep_id)
            same_noun = theirs["head"] == mine["head"] and (
                len(records) >= SHARED_RECORDS or len(shared) >= SHARED_WORDS + 1
            )
            if not same_noun and not (alias and len(records) >= SHARED_RECORDS):
                continue
            strength = len(records) + len(shared) + (3 if alias else 0)
            if best is None or strength > best[0]:
                best = (strength, keep, sorted(records), sorted(shared), alias)
        if best:
            _, keep, records, shared, alias = best
            if alias:
                name, entry = alias
                state = "approved" if entry.review_state == "reviewed" else "proposed, awaiting review"
                because = f"“{name}” is listed as another name for “{keep.name}” ({state}): {entry.basis}"
            else:
                because = (
                    f"Both are about “{mine['head']}”"
                    + (f" and work on the same records ({len(records)})" if records else "")
                    + (f"; shared wording: {', '.join(shared[:5])}" if shared else "")
                )
            found.append(
                {
                    "duplicate": draft_id,
                    "keep": keep.id,
                    "because": because,
                    "approved": alias is None or alias[1].review_state == "reviewed",
                }
            )
    return found


def merge_processes(raw: dict, keep_id: str, duplicate_id: str) -> list[str]:
    """Fold a drafted process into a verified one without losing a requirement, rule or exception it carried. Edits `raw`.

    Requirements, rules and exceptions move onto the verified step that talks about the same thing. Records, roles and rules stay in
    the application; steps the verified process does not have are reported, not silently dropped. Returns one line per consequence.
    """
    workflows = raw["workflow_definitions"]
    keep = next((w for w in workflows if w["id"] == keep_id), None)
    duplicate = next((w for w in workflows if w["id"] == duplicate_id), None)
    if keep is None or duplicate is None or keep is duplicate:
        raise ValueError("Choose two different existing processes")
    targets = [s for s in keep["states"] if s["kind"] not in ("start", "end")]
    if not targets:
        raise ValueError("The verified process has no steps to take the draft's requirements")
    texts = {r["id"]: r["statement"] for r in raw["business"]["requirements"]}
    texts |= {e["id"]: f"{e['name']} {e.get('trigger', '')} {e.get('recovery', '')}" for e in raw["business"]["exceptions"]}
    texts |= {r["id"]: r["description"] for r in raw["business"]["rules"]}
    old = [s for s in duplicate["states"] if s["kind"] not in ("start", "end")]

    def closest(reference: str, hint: str = "") -> dict:
        wanted = set(words(f"{texts.get(reference, '')} {hint}"))
        return max(targets, key=lambda s: len(wanted & set(words(s["label"]))))

    for step in old:
        for key in ("requirement_ids", "rule_ids", "exception_ids"):
            for reference in step.get(key, []):
                target = closest(reference, step["label"])
                if reference not in target[key]:
                    target[key].append(reference)
    moved = {s["id"]: closest("", s["label"])["id"] for s in old}
    for exception in raw["business"]["exceptions"]:
        if exception.get("resolution_state_id") in moved:
            exception["resolution_state_id"] = moved[exception["resolution_state_id"]]
    for screen in raw["screens"]:
        trace = screen.get("trace") or {}
        if trace.get("workflow_id") == duplicate_id:
            screen["trace"] = None
    raw["workflow_definitions"] = [w for w in workflows if w["id"] != duplicate_id]
    raw["workflows"] = [w for w in raw["workflows"] if w != duplicate_id]
    label = {s["label"].strip().lower() for s in keep["states"]}
    lost = [s["label"] for s in old if s["label"].strip().lower() not in label]
    notes = [f"Merged “{duplicate['name']}” into “{keep['name']}”; its requirements, rules and exceptions now belong to the verified process."]
    if lost:
        notes.append("Steps named differently in the verified process (check they are covered there): " + "; ".join(lost[:6]))
    return notes


def covered_by(raw: dict, name: str, step_names: list[str], provider) -> str | None:
    """The verified process that already covers a process about to be drafted, or None. Same rule as find_overlaps, on the draft's words."""
    from app.schemas.application_definition import ApplicationDefinition

    noun = head(name)
    if noun is None or provider is None:
        return None
    definition = ApplicationDefinition.model_validate(raw)
    vocabulary = {w for text in [name, *step_names] for w in words(text)} - GENERIC
    drafted = {w for w in words(name) if w not in GENERIC}
    requirements = {r.id: r.statement for r in definition.business.requirements}
    by_id = {w.id: w for w in definition.workflow_definitions}
    for keep_id in adopted_workflow_ids(definition, provider):
        keep = by_id.get(keep_id)
        if keep is None:
            continue
        theirs = _profile(keep, requirements)
        # Only an approved name may stop a draft; a proposed one is for a person to judge afterwards.
        if _alias(drafted, keep_id, reviewed_only=True):
            return keep.name
        if theirs["head"] == noun and len((vocabulary & theirs["vocabulary"]) - {noun}) >= SHARED_WORDS + 1:
            return keep.name
    return None
