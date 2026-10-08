# Machine lifecycle, warranty and traceability (Phase 3, schema 1.0)

Answers, from data and rules only: **"Is this covered under warranty, and was this part properly fitted?"** No language model, no UI, no claim submission, no external API. A later layer may explain a verified result; it never decides one. Phases 1 and 2 are described in [CANONICAL_DATA_MODEL.md](CANONICAL_DATA_MODEL.md) and [LOGISTICS_NETWORK.md](LOGISTICS_NETWORK.md).

## 1. Graph model
```
(MachineInstance)-[:HAS_INSTALLATION]->(InstallationEvent)-[:INSTALLED_PART]->(Part)
                                       (InstallationEvent)-[:PERFORMED_BY]->(Technician)-[:EMPLOYED_BY]->(Dealer)
                                       (InstallationEvent)-[:PERFORMED_AT]->(Dealer)
                                       (InstallationEvent)-[:RECORDED_IN]->(WorkOrder)<-[:HAS_WORK_ORDER]-(MachineInstance)
(MachineInstance)-[:HAS_REPLACEMENT]->(ReplacementEvent)-[:REMOVED_INSTALLATION|NEW_INSTALLATION]->(InstallationEvent); (ReplacementEvent)-[:RECORDED_IN]->(WorkOrder)
(MachineInstance)-[:HAS_CLAIM]->(WarrantyClaim)-[:CLAIM_ON_INSTALLATION]->(InstallationEvent); (WarrantyClaim)-[:CLAIM_FOR_PART]->(Part); (WarrantyClaim)-[:FILED_BY_DEALER]->(Dealer)
(WarrantyPolicy)-[:WARRANTY_FOR_PART]->(Part)            (Evidence)-[:SUPPORTS]->(any record above, a Dealer, a Technician or a Part)
```
* **`FITS` / `FitmentContext` is approval; `HAS_INSTALLATION` is fact.** A part can be installed on a machine it was never approved for (scenario G008), and an approved part may never have been fitted. The evaluator needs both.
* `MachineInstance` is the anchor: its history is every installation, replacement, work order and claim reachable from it.
* The Phase 1 names `OF_PART`, `INSTALLED_BY_DEALER`, `INSTALLED_BY_TECHNICIAN`, `UNDER_WORK_ORDER` were replaced by `INSTALLED_PART`, `PERFORMED_AT`, `PERFORMED_BY`, `RECORDED_IN` (`python backend/scripts/canonical.py migrate-lifecycle --yes`). A relationship is removed only if it carries this ingestion's own source id and its replacement already exists between the same two nodes.

## 2. Records and validation
* `InstallationEvent.validation_status` is `VALID` or `INCOMPLETE`, with `validation_issues` naming what is missing (`technician_missing`, `work_order_missing`, `dealer_missing`, `part_missing`, `machine_instance_missing`, `removal_before_installation`, `installed_before_machine_existed`, `technician_works_for_another_dealer`, `work_order_for_another_machine`, …). A reference that is not available is left empty, never filled in. It is computed by `rules.validate_installation` when the files are generated and re-checked by the quality checks.
* **Authorisation** is the dealer's existing `authorized_status`; the value `AUTHORISED` means authorised. There is no second field.
* **Technicians**: certification and specialisation (Hydraulics, Powertrain, Electrical, Transmission), employed by one dealer.
* **Work orders**: service type `INSTALLATION | REPLACEMENT | INSPECTION | MAINTENANCE | REPAIR`. One work order may record several component events (WO-G001 records two installations; WO-G005-2 an installation and the replacement it completes).
* **Replacements** keep history: the removed installation stays as `REMOVED` with its removal date. Chronology: removed installation date < replacement date <= new installation date; removal date <= replacement date. **Current component** = installation with no `removal_date` and status `CURRENT` (derived, never stored as a "current part" field).
* **Evidence** types: `INSTALLATION_RECORD, SERVICE_REPORT, INSPECTION_RECORD, WORK_ORDER, DEALER_RECORD, TECHNICIAN_RECORD, PART_RECORD` (plus the Phase 2 shipment/order types). Synthetic evidence says so in `reference`; no fabricated URLs or document ids. Dealer, technician and part records exist once per entity.
* Every lifecycle record carries `data_status = SYNTHETIC_DEMO`, `source_type`, `source_record_id`, `ingestion_timestamp`, `canonical_dataset`, `canonical_schema_version`; the existing catalogue records keep their own provenance.

## 3. Warranty policy and the deterministic evaluator
`WarrantyPolicy` is data: `coverage_period_days`, `start_rule` (`INSTALLATION_DATE | DELIVERY_DATE | PURCHASE_DATE`), `region` (empty = every region) and `coverage_conditions`, a list of condition codes. How each code is checked is one catalogue in `app/lifecycle/rules.py` (`CONDITIONS`); a policy naming an unknown code is rejected by the model.

| Condition | Holds when | If it fails |
|---|---|---|
| `APPROVED_MACHINE_FITMENT` | the part has an `APPROVED` fitment for the machine model | NOT_ELIGIBLE |
| `APPROVED_PART` | catalogue status `VERIFIED` and an `APPROVED` source | NOT_ELIGIBLE |
| `AUTHORISED_DEALER_INSTALL` | installing dealer `authorized_status = AUTHORISED` | NOT_ELIGIBLE |
| `COVERAGE_PERIOD_ACTIVE` | failure date (else evaluation date) in [start, start + days] | NOT_ELIGIBLE |
| `INSTALLATION_EVIDENCED` | technician, work order, installation record and work-order record exist | INSUFFICIENT_DATA |
| `NO_PRIOR_CLAIM` | no earlier claim for this part on this machine | REQUIRES_REVIEW |
| `NO_PRIOR_REPLACEMENT` | this installation is not the result of repeated replacement | REQUIRES_REVIEW |

Always evaluated first: `PART_INSTALLED` (this installation is of the claimed part on the claimed machine) and `POLICY_FOUND` (exactly one most-specific active policy; none → INSUFFICIENT_DATA, two equal → REQUIRES_REVIEW).

**Outcome precedence**: a definite hard failure (`NOT_ELIGIBLE`) > any unknown fact (`INSUFFICIENT_DATA`) > a review trigger (`REQUIRES_REVIEW`) > `ELIGIBLE`. A start rule that needs a delivery or purchase date that is not on record gives INSUFFICIENT_DATA; nothing is guessed. The same facts always give the same outcome.

**Claims.** Statuses `SUBMITTED, UNDER_REVIEW, APPROVED, REJECTED, CLOSED`. The status and decision of a *decided* claim are derived from the evaluator when the files are generated (`APPROVED` ⇔ ELIGIBLE, `REJECTED` ⇔ NOT_ELIGIBLE, else `UNDER_REVIEW`); the quality checks fail if a stored decision disagrees with the rules. Golden claims stay `SUBMITTED`: the evaluator returns the verdict, no approval is invented.

## 4. Context, traceability, part lifecycle (`app/lifecycle/context.py`)
`WarrantyContextBuilder(reader).for_claim(id)` / `.for_part(machine_instance_id, part_id)` returns a `WarrantyContext`: machine, current_part, installation, dealer, technician, work_order, fitment, approved_source, warranty_policy, coverage_start, coverage_end, replacement_history, prior_claims, evidence, decision_factors (code, status, detail, records, evidence), provenance, plus `outcome`, `reasons`, `missing`. `.traceability(machine_instance_id, part_id?)` gives installed now / installed before / who / where / when replaced / linked claims. `.part_lifecycle(installation_id)` gives Installed → Serviced → Inspected → Removed → Replaced → Current/Historical, each stage dated from a record; a stage with no record is absent. Readers: `FileReader` (canonical files) and `GraphReader` (Neo4j, read-only) return identical dictionaries; a live test asserts they agree.

## 5. Golden scenarios (`reference/lifecycle_scenarios.json`, KFT-600/800 and BTS-750)
| ID | Case | Expected |
|---|---|---|
| G001 | Piston pump (PRT-007) fitted by an authorised dealer, one work order for two components, failure inside the period | ELIGIBLE |
| G002 | Same part fitted by a SERVICE_PARTNER dealer | NOT_ELIGIBLE (authorisation) |
| G003 | Failure after the 365-day period (installed 2025-02-10, failed 2026-05-01) | NOT_ELIGIBLE (expired) |
| G004 | Second claim for the same part on the same machine | REQUIRES_REVIEW |
| G005 | Pump replaced twice (A→B→C), third unit fails | REQUIRES_REVIEW |
| G006 | Installation with no technician, work order or evidence | INSUFFICIENT_DATA |
| G007 | Wheel hub bearing PRT-022 (UNVERIFIED) | NOT_ELIGIBLE (not an approved part) |
| G008 | Verified gear pump with no fitment for the KFT-600 | NOT_ELIGIBLE (no approved fitment) |

## 6. Commands
```
python backend/scripts/canonical.py generate            # lifecycle + scenario files, validation and claim decisions derived by the rules
python backend/scripts/canonical.py validate            # offline schema/reference validation
python backend/scripts/canonical.py dry-run             # plan against the graph
python backend/scripts/canonical.py ingest --yes        # idempotent MERGE
python backend/scripts/canonical.py migrate-lifecycle [--yes]   # superseded relationship names (dry run without --yes)
python backend/scripts/canonical.py lifecycle-report    # counts, data-quality checks, golden scenarios against the graph (read-only)
```

## 7. Known limits
* Only `INSTALLATION_DATE` can start a coverage period today: no delivery or purchase dates are recorded on machine instances, so those rules return INSUFFICIENT_DATA rather than a guess.
* All dealers in the data have `warranty_capable = false` for NL; the evaluator does not use it (authorisation is `authorized_status`).
* Lifecycle data is synthetic and labelled `SYNTHETIC_DEMO`; the existing 3 claims were re-derived by the evaluator, so their earlier hand-written outcomes changed (CLM-0002 and CLM-0003 are REJECTED because their installing dealers are INDEPENDENT).
