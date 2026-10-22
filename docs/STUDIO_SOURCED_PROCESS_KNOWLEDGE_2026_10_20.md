# Cross-domain sourced process knowledge

The configured Neo4j database now holds 23 versioned vendor-process references covering all 23 current shared blueprints. This includes the 21 system/capability profiles plus shared master-data foundations and parts-commerce reference patterns. Company-specific blueprints are not treated as universal shared policy.

The live import was run twice with the same version. Both runs returned 23 stored reference versions, 27 source records, 138 claims, 138 evidence links and 32 documented relationships. A follow-up query found zero claims without evidence. The saved Transport Operations project remains revision 12.

## What is stored

Each reference records the relevant domain and exact blueprint version, vendor/system, source product/documentation version, check date, applicability, review state and limitations. Claims are classified as entities, relationships, activities, rules, statuses or exceptions. Every claim has a source ID and locator. Relationship claims refer to validated entity endpoints.

The references cover transport, warehouse operations, inventory, procurement, manufacturing, e-commerce, CRM, finance, workforce, after-sales, agriculture, construction, education, healthcare administration, hospitality, IT service, property operations and public-service requests, together with shared approvals, documents, task management, master data and parts commerce.

Primary documentation includes Oracle Transportation Management 25c, Odoo, Frappe/ERPNext and Microsoft Dynamics 365/Power Automate. For example, the OTM reference links planning and rate concepts to Oracle's [itinerary setup](https://docs.oracle.com/en/cloud/saas/transportation/25c/otmol/planning/itinerary_manager/manage_itinerary/setting_up_itineraries.htm), [multi-leg planning](https://docs.oracle.com/en/cloud/saas/transportation/25c/otmol/bulk_plan_manager/data_setup/itineraries_and_bulk_plan.htm), [rate offerings](https://docs.oracle.com/en/cloud/saas/transportation/25c/otmol/planning/rate_manager/create_rate_offering.htm) and [tender acceptance](https://docs.oracle.com/en/cloud/saas/transportation/25c/otmol/planning/shipment_manager/accept_tender.htm).

## Scope and maturity

These are partial, source-checked extractions with **draft** review state, not a complete implementation of each vendor system. Missing categories remain visible as research gaps. Construction uses an analogous project/task reference, property uses an analogous asset-maintenance reference, public-service requests use generic case management, and shared foundations/parts commerce use explicitly limited master-data/product-configuration patterns.

The records are shared process references. They do not establish EU or India statutory compliance, company-specific policy, real transport prices, API connectivity or legal permission to automate a decision. Regional primary-source coverage and additional vendor variants remain research work. Coverage of every current blueprint does not mean coverage of every industry or system in existence.

## How Studio uses it

- Local development reads the same validated reference documents as the import tool. Neo4j mode reads the graph and does not silently substitute local references when the graph is empty.
- The Knowledge stage displays relevant references, per-category claims, evidence links, versions, gaps and applicability. Repeated vendor names are distinguished by the business area.
- The assistant receives matching references for the project's selected domain and adopted blueprints. Its instructions preserve evidence, versions and applicability, and prohibit promoting vendor behavior to confirmed customer policy.
- References are not executed or silently merged into an approved application. Existing draft/review actions and the customer's current stage still govern changes.
- Existing optional region/industry questions and skip behavior are preserved.

## Graph representation

`DKProcessReference` points to an exact `DKPackVersion` through `DK_REFERENCES_BLUEPRINT`. It owns `DKReferenceSource` and `DKReferenceClaim` nodes. Claims link to sources through `DK_SUPPORTED_BY`; relationship claims link to their entity endpoints through `DK_RELATION_SUBJECT` and `DK_RELATION_TARGET`.

Reference documents are hashed and immutable by ID/version. Import rejects conflicting content or missing blueprint versions. Import is additive and transactional; it neither rewrites project revisions nor promotes source claims into confirmed `DKRule` policies. Old versions remain available for provenance.

## Extending the library

1. Research the actual primary documentation for the intended system and version. Record narrow, paraphrased claims; do not fill missing details with model guesses.
2. Add a reference in `backend/scripts/build_process_references.py` or supply documents conforming to `ProcessReference`. New domains first need a versioned blueprint.
3. Run `python backend/scripts/build_process_references.py` to rebuild the local catalog and run `python backend/scripts/test_offline.py backend/tests/test_process_references.py -q`.
4. Use a new reference version for changed published content. Run `python backend/scripts/import_process_references.py` against the configured database. The full `import_design_knowledge.py` workflow also imports these references after the blueprints.
5. Review applicability and research gaps before incorporating the reference into customer policy or executable rules.

The machine-readable live inventory and evidence are in `STUDIO_PROCESS_REFERENCES_2026_10_20.json`.

## Verification

652 backend tests passed; 316 external/live tests were skipped. 418 frontend tests passed. The new source panel's final interaction tests, typecheck, lint, formatting and production build passed. Live checks verified graph retrieval, evidence links and the unchanged TMS revision. The existing `python_multipart` deprecation warning remains.
