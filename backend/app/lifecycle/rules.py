"""The lifecycle rules: installation validation, replacement chronology and the deterministic warranty evaluator.

Where facts live
  * WHICH conditions apply to a part is DATA: `WarrantyPolicy.coverage_conditions` holds condition codes.
  * HOW each code is checked, and what a failure means, is this one catalogue (CONDITIONS). Nothing is scattered through application code.
  * Authorisation is the dealer's own `authorized_status`; there is no second field for it. The value that means "authorised dealer" is AUTHORISED.

Outcomes (precedence, strongest first)
  NOT_ELIGIBLE       a condition that must hold definitely fails (unauthorised dealer, expired period, part not approved, fitment not approved, wrong part)
  INSUFFICIENT_DATA  a needed fact is missing (no technician, work order or evidence; no policy; a start date that is not recorded). Nothing is invented.
  REQUIRES_REVIEW    the facts are complete but a review condition fires (an earlier claim, an earlier replacement of this part) or the policy is ambiguous
  ELIGIBLE           every applicable condition holds on complete, evidenced facts
FITS (a part is approved for a machine MODEL) is never the same as an installation (this part was fitted to THIS physical machine): the evaluator needs both.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
ELIGIBLE, NOT_ELIGIBLE, REQUIRES_REVIEW, INSUFFICIENT_DATA = "ELIGIBLE", "NOT_ELIGIBLE", "REQUIRES_REVIEW", "INSUFFICIENT_DATA"
OUTCOMES = (ELIGIBLE, NOT_ELIGIBLE, REQUIRES_REVIEW, INSUFFICIENT_DATA)
AUTHORISED = "AUTHORISED"  # Dealer.authorized_status that means an authorised dealer
APPROVED = "APPROVED"
VERIFIED = "VERIFIED"  # PartCatalogProfile.part_status of a catalogue-verified part


@dataclass
class Factor:
    code: str
    label: str
    status: str  # PASS | FAIL | UNKNOWN
    detail: str
    on_fail: str = NOT_ELIGIBLE  # what a FAIL means: NOT_ELIGIBLE or REQUIRES_REVIEW
    records: list[str] = field(default_factory=list)  # the graph records the factor was read from
    evidence: list[str] = field(default_factory=list)  # evidence ids that support it


@dataclass
class Facts:
    """Everything the evaluator may use, already read from the graph or files. None / [] means NOT RECORDED."""

    instance: dict[str, Any] | None = None
    installation: dict[str, Any] | None = None
    part: dict[str, Any] | None = None
    dealer: dict[str, Any] | None = None
    technician: dict[str, Any] | None = None
    work_order: dict[str, Any] | None = None
    fitment: dict[str, Any] | None = None
    approved_sources: list[dict[str, Any]] = field(default_factory=list)
    policies: list[dict[str, Any]] = field(default_factory=list)
    claim: dict[str, Any] | None = None
    other_claims: list[dict[str, Any]] = field(default_factory=list)  # claims on this machine for this part, not the one being judged
    replacements: list[dict[str, Any]] = field(default_factory=list)  # replacements on this machine
    evidence: list[dict[str, Any]] = field(default_factory=list)
    reference_date: date | None = None  # the day coverage is judged on: the failure date of a claim, else today


@dataclass
class Decision:
    outcome: str
    factors: list[Factor]
    policy_id: str | None
    coverage_start: str | None
    coverage_end: str | None
    reference_date: str | None
    reasons: list[str]

    def factor(self, code: str) -> Factor | None:
        return next((f for f in self.factors if f.code == code), None)


def _d(v: str | None) -> date | None:
    try:
        return date.fromisoformat(v[:10]) if v else None
    except ValueError:
        return None


def _ev(facts: Facts, entity_type: str, entity_id: str | None, *types: str) -> list[str]:
    return [e["evidence_id"] for e in facts.evidence if e["entity_type"] == entity_type and e["entity_id"] == entity_id and (not types or e["evidence_type"] in types)]


# ── policy selection and coverage window ─────────────────────────────────────────────────────────
def select_policy(policies: list[dict[str, Any]], region: str | None) -> tuple[dict[str, Any] | None, str]:
    """(policy, state): state is 'one', 'none' or 'ambiguous'. Active policies whose region is empty (every region) or the dealer's region; a regional policy wins over a global one."""
    active = [p for p in policies if p.get("status") == "ACTIVE" and (not p.get("region") or p["region"] == region)]
    regional = [p for p in active if p.get("region")]
    pool = regional or active
    if not pool:
        return None, "none"
    return (pool[0], "one") if len(pool) == 1 else (None, "ambiguous")


def coverage_window(policy: dict[str, Any] | None, installation: dict[str, Any] | None) -> tuple[date, date] | None:
    """(start, end) from the policy's start rule. Only INSTALLATION_DATE is recorded today; a rule needing a date that is not on record gives None, never a guess."""
    if not policy or not installation:
        return None
    start = _d(installation.get("installation_date")) if policy["start_rule"] == "INSTALLATION_DATE" else None
    return (start, start + timedelta(days=policy["coverage_period_days"])) if start else None


# ── the base facts every judgement needs ─────────────────────────────────────────────────────────
def check_part_installed(f: Facts) -> Factor:
    inst, claim = f.installation, f.claim
    if not inst:
        return Factor("PART_INSTALLED", "The part was installed on this machine", UNKNOWN, "No installation record is on file for this part on this machine.")
    ev = _ev(f, "INSTALLATION", inst["installation_id"], "INSTALLATION_RECORD")
    if f.instance and inst["machine_instance_id"] != f.instance["machine_instance_id"]:
        return Factor("PART_INSTALLED", "The part was installed on this machine", FAIL, "The installation belongs to a different machine.", records=[inst["installation_id"]])
    if claim and (claim["part_id"] != inst["part_id"] or claim["machine_instance_id"] != inst["machine_instance_id"]):
        return Factor("PART_INSTALLED", "The part was installed on this machine", FAIL, "The claimed part is not the part this installation fitted.", records=[inst["installation_id"], claim["claim_id"]])
    return Factor("PART_INSTALLED", "The part was installed on this machine", PASS,
                  f"Installation {inst['installation_id']} fitted {inst['part_id']} on {inst['machine_instance_id']} on {inst['installation_date']}.", records=[inst["installation_id"]], evidence=ev)


def check_policy(f: Facts) -> tuple[Factor, dict[str, Any] | None]:
    policy, state = select_policy(f.policies, (f.dealer or {}).get("region"))
    if state == "none":
        return Factor("POLICY_FOUND", "A warranty policy applies to the part", UNKNOWN, "No active warranty policy is recorded for this part and region."), None
    if state == "ambiguous":
        return Factor("POLICY_FOUND", "A single warranty policy applies to the part", FAIL, "More than one active policy applies and none is more specific.", on_fail=REQUIRES_REVIEW,
                      records=[p["warranty_policy_id"] for p in f.policies]), None
    return Factor("POLICY_FOUND", "A warranty policy applies to the part", PASS, f"Policy {policy['warranty_policy_id']}: {policy['coverage_period_days']} days from {policy['start_rule'].lower().replace('_', ' ')}.",
                  records=[policy["warranty_policy_id"]]), policy


# ── the condition catalogue ──────────────────────────────────────────────────────────────────────
def c_machine_fitment(f: Facts) -> Factor:
    label = "The part is approved for this machine model"
    if not f.fitment:  # a part with no fitment record is not approved for the model: absence of approval is a definite answer, not missing data
        return Factor("APPROVED_MACHINE_FITMENT", label, FAIL, "No fitment record approves this part for this machine model.")
    ok = f.fitment.get("approval_status") == APPROVED
    return Factor("APPROVED_MACHINE_FITMENT", label, PASS if ok else FAIL, f"Fitment is {f.fitment.get('approval_status')} ({f.fitment.get('fitment_rule') or 'rule not stated'}).", records=[f.fitment["fitment_id"]])


def c_approved_part(f: Facts) -> Factor:
    label = "The part is a verified catalogue part from an approved source"
    if not f.part:
        return Factor("APPROVED_PART", label, UNKNOWN, "The installed part is not in the catalogue.")
    if f.part.get("status") != VERIFIED:
        return Factor("APPROVED_PART", label, FAIL, f"The part's catalogue status is {f.part.get('status')}, not {VERIFIED}.", records=[f.part["part_id"]])
    sources = [s["approved_source_id"] for s in f.approved_sources if s.get("approval_status") == APPROVED]
    if not sources:
        return Factor("APPROVED_PART", label, FAIL, "No approved source is recorded for the part.", records=[f.part["part_id"]])
    return Factor("APPROVED_PART", label, PASS, f"Verified part with {len(sources)} approved source(s).", records=[f.part["part_id"], *sources[:3]], evidence=_ev(f, "PART", f.part["part_id"]))


def c_authorised_dealer(f: Facts) -> Factor:
    label = "The installation was performed by an authorised dealer"
    if not f.installation or not f.installation.get("dealer_id") or not f.dealer:
        return Factor("AUTHORISED_DEALER_INSTALL", label, UNKNOWN, "The installing dealer is not recorded.")
    status = f.dealer.get("authorized_status")
    return Factor("AUTHORISED_DEALER_INSTALL", label, PASS if status == AUTHORISED else FAIL, f"Dealer {f.dealer['dealer_id']} is {status or 'of unstated status'}.",
                  records=[f.dealer["dealer_id"]], evidence=_ev(f, "DEALER", f.dealer["dealer_id"]))


def c_coverage_active(f: Facts) -> Factor:
    label = "The warranty period is active"
    policy, _ = select_policy(f.policies, (f.dealer or {}).get("region"))
    window = coverage_window(policy, f.installation)
    if window is None or f.reference_date is None:
        why = "no policy" if policy is None else f"the start rule {policy['start_rule']} needs a date that is not recorded" if not f.installation or not _d(f.installation.get("installation_date")) else "no reference date"
        return Factor("COVERAGE_PERIOD_ACTIVE", label, UNKNOWN, f"Coverage cannot be dated: {why}.")
    start, end = window
    if f.reference_date < start:
        return Factor("COVERAGE_PERIOD_ACTIVE", label, FAIL, f"The failure ({f.reference_date}) is before coverage starts ({start}).", records=[policy["warranty_policy_id"]])
    if f.reference_date > end:
        return Factor("COVERAGE_PERIOD_ACTIVE", label, FAIL, f"Coverage ended on {end}; the failure was on {f.reference_date}.", records=[policy["warranty_policy_id"]])
    return Factor("COVERAGE_PERIOD_ACTIVE", label, PASS, f"Covered from {start} to {end}; judged on {f.reference_date}.", records=[policy["warranty_policy_id"]])


def c_installation_evidenced(f: Facts) -> Factor:
    label = "The installation is evidenced (technician, work order and records)"
    inst = f.installation
    if not inst:
        return Factor("INSTALLATION_EVIDENCED", label, UNKNOWN, "There is no installation to evidence.")
    missing = []
    if not inst.get("technician_id") or not f.technician:
        missing.append("technician")
    if not inst.get("work_order_id") or not f.work_order:
        missing.append("work order")
    install_ev = _ev(f, "INSTALLATION", inst["installation_id"], "INSTALLATION_RECORD")
    wo_ev = _ev(f, "WORK_ORDER", inst.get("work_order_id"), "WORK_ORDER") if inst.get("work_order_id") else []
    if not install_ev:
        missing.append("installation record")
    if inst.get("work_order_id") and not wo_ev:
        missing.append("work order record")
    if missing:
        return Factor("INSTALLATION_EVIDENCED", label, UNKNOWN, "Missing: " + ", ".join(missing) + ". Nothing is assumed in their place.", records=[inst["installation_id"]], evidence=install_ev + wo_ev)
    return Factor("INSTALLATION_EVIDENCED", label, PASS, f"Technician {f.technician['technician_id']} under work order {f.work_order['work_order_id']}.",
                  records=[inst["installation_id"], f.technician["technician_id"], f.work_order["work_order_id"]], evidence=install_ev + wo_ev + _ev(f, "TECHNICIAN", f.technician["technician_id"]))


def c_no_prior_claim(f: Facts) -> Factor:
    label = "There is no earlier claim for this part on this machine"
    mine = f.claim["claim_date"] if f.claim else None
    prior = [c for c in f.other_claims if mine is None or c["claim_date"] < mine]
    if prior:
        return Factor("NO_PRIOR_CLAIM", label, FAIL, "Earlier claim(s): " + ", ".join(c["claim_id"] for c in prior) + ".", on_fail=REQUIRES_REVIEW, records=[c["claim_id"] for c in prior])
    return Factor("NO_PRIOR_CLAIM", label, PASS, "No earlier claim for this part on this machine.")


def c_no_prior_replacement(f: Facts) -> Factor:
    label = "This installation is not the result of repeated replacement of the part"
    inst = f.installation
    if not inst:
        return Factor("NO_PRIOR_REPLACEMENT", label, UNKNOWN, "There is no installation to date a replacement against.")
    # replacements that put this part on the machine before this installation; the replacement that created this installation is the first of its kind and does not count
    prior = [r for r in f.replacements if r.get("installed_part_id") == inst["part_id"] and r["new_installation_id"] != inst["installation_id"]
             and r["replacement_date"] <= inst["installation_date"]]
    if prior:
        return Factor("NO_PRIOR_REPLACEMENT", label, FAIL, f"{len(prior)} earlier replacement(s) of this part on this machine: " + ", ".join(r["replacement_id"] for r in prior) + ".",
                      on_fail=REQUIRES_REVIEW, records=[r["replacement_id"] for r in prior])
    return Factor("NO_PRIOR_REPLACEMENT", label, PASS, "No earlier replacement of this part on this machine.")


@dataclass(frozen=True)
class Condition:
    code: str
    description: str
    on_fail: str
    check: Callable[[Facts], Factor]


CONDITIONS: dict[str, Condition] = {c.code: c for c in (
    Condition("APPROVED_MACHINE_FITMENT", "The part must be approved for the machine model (FitmentContext APPROVED)", NOT_ELIGIBLE, c_machine_fitment),
    Condition("APPROVED_PART", "The part must be a VERIFIED catalogue part with an APPROVED source", NOT_ELIGIBLE, c_approved_part),
    Condition("AUTHORISED_DEALER_INSTALL", "The installing dealer must have authorized_status AUTHORISED", NOT_ELIGIBLE, c_authorised_dealer),
    Condition("COVERAGE_PERIOD_ACTIVE", "The failure must fall inside the coverage window the start rule gives", NOT_ELIGIBLE, c_coverage_active),
    Condition("INSTALLATION_EVIDENCED", "The installation must have a technician, a work order and their records", INSUFFICIENT_DATA, c_installation_evidenced),
    Condition("NO_PRIOR_CLAIM", "An earlier claim for this part on this machine sends the claim to review", REQUIRES_REVIEW, c_no_prior_claim),
    Condition("NO_PRIOR_REPLACEMENT", "An earlier replacement of this part on this machine sends the claim to review", REQUIRES_REVIEW, c_no_prior_replacement),
)}


# ── the evaluator ────────────────────────────────────────────────────────────────────────────────
def evaluate(f: Facts) -> Decision:
    """Deterministic: the same facts always give the same outcome. The policy chooses the conditions; the base facts (installed, policy) always apply."""
    factors = [check_part_installed(f)]
    policy_factor, policy = check_policy(f)
    factors.append(policy_factor)
    for code in (policy["coverage_conditions"] if policy else []):
        cond = CONDITIONS.get(code)
        if cond is None:
            factors.append(Factor(code, f"Unknown condition {code}", UNKNOWN, "The policy names a condition this system cannot check."))
        else:
            fac = cond.check(f)
            fac.on_fail = cond.on_fail
            factors.append(fac)
    hard = [x for x in factors if x.status == FAIL and x.on_fail == NOT_ELIGIBLE]
    unknown = [x for x in factors if x.status == UNKNOWN]
    review = [x for x in factors if x.status == FAIL and x.on_fail == REQUIRES_REVIEW]
    outcome = NOT_ELIGIBLE if hard else INSUFFICIENT_DATA if unknown else REQUIRES_REVIEW if review else ELIGIBLE
    window = coverage_window(policy, f.installation)
    reasons = [f"{x.label}: {x.detail}" for x in (hard or unknown or review)] if outcome != ELIGIBLE else ["Every applicable condition holds on complete, evidenced facts."]
    return Decision(outcome, factors, policy["warranty_policy_id"] if policy else None, window[0].isoformat() if window else None, window[1].isoformat() if window else None,
                    f.reference_date.isoformat() if f.reference_date else None, reasons)


def claim_status_for(outcome: str) -> tuple[str, str | None]:
    """The recorded status of a DECIDED claim, derived from the evaluator's outcome (never chosen by hand). Undecided outcomes stay with a reviewer."""
    return {ELIGIBLE: ("APPROVED", APPROVED), NOT_ELIGIBLE: ("REJECTED", "REJECTED")}.get(outcome, ("UNDER_REVIEW", None))


# ── installation validation ──────────────────────────────────────────────────────────────────────
def validate_installation(inst: dict[str, Any], instance: dict[str, Any] | None, part: dict[str, Any] | None, dealer: dict[str, Any] | None, technician: dict[str, Any] | None,
                          work_order: dict[str, Any] | None, today: date | None = None) -> tuple[str, list[str]]:
    """('VALID' | 'INCOMPLETE', issues). VALID only when the machine, part, dealer, technician and work order all exist and the dates are sound. A reference that is
    intentionally unavailable makes the record INCOMPLETE; no value is filled in."""
    issues: list[str] = []
    if instance is None:
        issues.append("machine_instance_missing")
    if part is None:
        issues.append("part_missing")
    if dealer is None:
        issues.append("dealer_missing")
    if technician is None:
        issues.append("technician_missing")
    if work_order is None:
        issues.append("work_order_missing")
    start, end = _d(inst.get("installation_date")), _d(inst.get("removal_date"))
    if start is None:
        issues.append("installation_date_invalid")
    else:
        if instance and instance.get("model_year") and start.year < int(instance["model_year"]):
            issues.append("installed_before_machine_existed")
        if today and start > today:
            issues.append("installation_date_in_future")
    if end is not None and start is not None and end < start:
        issues.append("removal_before_installation")
    if technician and dealer and technician.get("dealer_id") != dealer.get("dealer_id"):
        issues.append("technician_works_for_another_dealer")
    if work_order and instance and work_order.get("machine_instance_id") != instance.get("machine_instance_id"):
        issues.append("work_order_for_another_machine")
    return ("VALID" if not issues else "INCOMPLETE"), issues


def replacement_chronology_errors(rep: dict[str, Any], removed: dict[str, Any] | None, new: dict[str, Any] | None) -> list[str]:
    """removed installation date < replacement date <= new installation date; the removal happened on or before the replacement."""
    errors: list[str] = []
    if removed is None or new is None:
        return ["installation_missing"]
    r_date, rem_in, new_in, rem_out = _d(rep["replacement_date"]), _d(removed["installation_date"]), _d(new["installation_date"]), _d(removed.get("removal_date"))
    if not (rem_in and r_date and new_in):
        return ["date_invalid"]
    if not rem_in < r_date:
        errors.append("replacement_not_after_removed_installation")
    if not r_date <= new_in:
        errors.append("new_installation_before_replacement")
    if rem_out is None:
        errors.append("removed_installation_has_no_removal_date")
    elif rem_out > r_date:
        errors.append("removal_after_replacement")
    if removed["machine_instance_id"] != new["machine_instance_id"]:
        errors.append("installations_on_different_machines")
    return errors


def current_installations(installations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The current components of a machine: installations with no removal date that are active. Derived from graph state; nothing is stored as 'current_part'."""
    return sorted((i for i in installations if not i.get("removal_date") and i.get("status") == "CURRENT"), key=lambda i: (i["installation_date"], i["installation_id"]))
