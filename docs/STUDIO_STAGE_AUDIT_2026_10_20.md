# Studio stage audit — Transport Operations, revision 12

## Fixes

- Generation now receives structured capability findings. One carrier connection was incorrectly counted as two because the UI split an explanation at a semicolon. The UI now names the connection and explains the available manual fallback.
- Generated tests are derived from the application's entities, required references, rules, workflow terminals and conditional paths. They run independently of Studio against isolated temporary databases. Results distinguish passes, failures and skips, and expose every case instead of truncating at 40.
- Explicit edit controls can revise earlier reviewed stages. Previously, guided mode silently filtered those actions when the active stage was later in the journey. Changes now persist and reopen the affected stage; future-stage edits return an explicit error.
- Step insertion can target a particular transition. It preserves that transition's condition and the other paths. Both the UI request and a real isolated save/reload are tested.
- Rule confirmation has a typed, audited action with an identifiable source. Confirmation preserves the predicate and blueprint origin. Policy actions remain proposals until reviewed, including in guided mode. Synthetic evidence cannot confirm a rule.
- Related records reached through entity relationships no longer produce false unused-entity notices. Optional setup questions and an explicitly deferred integration with a fallback are informational.
- Process diagrams have wrapped task headings, centered layout and readable data counts. Detailed process activities follow graph order. Stage navigation resets the main scroll position. Long rule-source details are expandable. Validation offers “Review rule” for policy confirmation rather than implying that the assistant can fix company policy automatically.

## Stage review

| Stage | Observed result |
| --- | --- |
| Requirements | Saved goal, users, three agreed requirements and acceptance criteria are displayed. All three requirements have process coverage. |
| Domain knowledge | Neo4j sources and pinned pack versions are visible. The library reports 21 system profiles and 21 industry categories, explicitly described as starting coverage rather than exhaustive or verified customer policy. |
| Business process | Twelve states, two decisions and two exception paths. Generated tests cover every configured conditional transition, including recovery loops. Step insertion persists in an isolated project and reopens this stage when edited later. |
| Data model | Eight entities, nine relationships, 42 fields. The map and relationship list are available; related-entity dependencies are included in usage analysis. |
| Screens | Nine navigable screen previews. Assignment has carrier/vehicle selections; task fields and routes follow the saved process. Preview clearly identifies unsaved records and is distinct from the runtime. |
| Rules | Six executable blueprint defaults. Their origins remain visible; business confirmation is a separate reviewed action, not an automatic promotion of synthetic knowledge. |
| Roles | Six roles and server-enforced entity/field ownership. Supporting roles with no workflow task are disclosed. Read-only warehouse entities are not silently granted creation rights. |
| Validation | Zero errors, six policy-confirmation warnings, nine informational notices. Existing demo approvals explicitly acknowledge synthetic policies and pending customer acceptance. |
| Generate | 52 files; one deferred carrier connection. Download refreshed with the expanded independent tests. Current application remains stopped, as before verification. |

## Generated application test result

50 tests: **43 passed, 0 failed, 7 skipped**. Delivery, cancellation, overload, tracking outcomes and retry transitions pass. The skips are creation/persistence/validation fixtures for read-only Pick list and Pack unit records and their required references. A customer import fixture is needed to test those writes; the TMS manual workflow does not require that optional warehouse link.

Evidence, case names, checks and stage results are recorded in [STUDIO_STAGE_VERIFICATION_2026_10_20.json](STUDIO_STAGE_VERIFICATION_2026_10_20.json). Verification confirmed that project revision 12 was unchanged and the runtime stayed stopped. The reference ZIP was refreshed; the saved runtime database was not replaced.

## Remaining inputs and limits

Regression verification: **646 backend tests passed, 316 skipped** (external graph/provider checks disabled), **415 frontend tests passed**. The final workspace interaction tests also passed after the validation-label change. Typecheck, lint, formatting and the production build passed. One existing `python_multipart` deprecation warning remains.

The six blueprint rules are not proven customer policy merely because a graph contains them. A business owner or identifiable supporting source must confirm applicability. Live carrier mapping, credentials and any provider adapter remain unconfigured. Production database access and hosted application execution remain the separate deployment phase already discussed with the owner. This audit does not claim production readiness or exhaustive domain coverage.
