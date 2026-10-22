# Industry and regional process knowledge — 19 October 2026

## Delivered

The Studio now retrieves a versioned industry/system context catalog from Neo4j. The active release is `2026.10.19.2`, with **21 system profiles, 21 industry categories, and three regional contexts: shared/global, European Union, and India**. These are starting categories, not an exhaustive statement that every industry, vendor or jurisdiction has been modeled.

The catalog points to real reusable blueprint versions and their activity-level processes, responsible roles, data reads/writes, rules and exceptions. It includes proposed operating variants such as own-fleet versus outsourced transport, single-site versus multi-site inventory, and business versus consumer ordering. Variant notes are design guidance, not a claim that each has a separately implemented or vendor-certified application.

Eight new executable sector blueprints cover healthcare administration, education enrolment, hospitality reservations, construction delivery, property maintenance, agriculture harvest handling, public-service request handling, and IT service tickets. They have distinct business fields, scoped task forms, role ownership, completion checks and recovery notes. These are operational starting points. Clinical decisions, lending/insurance eligibility, statutory determinations and tax calculations were not fabricated.

## Short, optional discovery

After the user's first description, Requirements can show just two optional setup details:

1. Where will the business operate? EU, India, or shared/global.
2. Which industry should the draft fit?

Users can answer either, skip either, choose **Skip setup**, type **skip both**, or continue without answering. Skipped values are saved as unspecified, not converted into confirmed policy. Skipping works without an AI call, persists on reload, and does not block stage continuation. An explicit region in the initial goal is recognized when unambiguous; mentioning both EU and India does not silently select one.

Selections and skips live in the project's versioned business brief in Neo4j, including the catalog version used. Existing definitions without this context retain their previous serialization and approval digests. The selected context is supplied to the model, shown in Domain Knowledge and included in new application exports as `design/business-context.json`. Formal approval and access checks remain in place.

## Graph storage and reuse

- `DKContextCatalog` preserves each immutable catalog document and hash.
- `DKSystemProfile` nodes link to exact `DKPackVersion` blueprints through `DK_REUSES_BLUEPRINT`.
- Industry and regional context nodes are connected to the profiles they describe.
- Context retrieval follows the version pinned by a saved project. A later catalog release does not silently rewrite its assumptions.
- The live graph contains 49 pack versions after the sector additions. The active reference-pack catalog has 26 packs. Legacy Noordveld packs remain source references.
- Existing customer process changes remain project-scoped proposed knowledge; storing them does not automatically certify them as shared business policy.

Live import verification checked exact document readback, repeat-import idempotency and rejection of an attempted overwrite of a published catalog version. See `STUDIO_INDUSTRY_CONTEXT_GRAPH_2026_10_19.json`.

## Sources and provenance

Studio process templates are authored, reviewable patterns. The official sources below support regional/classification context only; they do not verify the authored workflows or establish a customer's legal obligations.

- [Eurostat NACE overview](https://ec.europa.eu/eurostat/web/nace/) — classification reference, checked 19 October 2026. Studio category labels are not an official NACE code mapping.
- [MoSPI NIC 2008 code finder](https://www.mospi.gov.in/nic-2008-codefinder) — official source link; detailed classification content still requires source review. No NIC code crosswalk has been asserted.
- [European Commission VAT identification numbers](https://taxation-customs.ec.europa.eu/taxation/vat/vat-directive/vat-identification-numbers_en) — source checked 19 October 2026; no universal tax rate, invoice rule or threshold is encoded.
- [GST e-Invoice portal](https://einvoice.gst.gov.in/) — source reference only. Automated retrieval returned HTTP 403; its regulatory content was not ingested or marked verified.

Adding a named vendor's actual process requires its documentation or customer-provided process evidence. Unknown domains retain a model-proposed foundation path. Generic words such as “reservation” do not automatically classify an astronomy application as hotel software.

## Validation

87 backend tests passed across the focused regression runs, including execution of all eight new sector workflows, skip/reload/continue behavior, invalid-context rejection, source retrieval, export, stage reviews, generated runtime permissions and integration contracts. 22 frontend tests passed, including optional setup, workspace navigation, process inspection, previews and access-denied handling. The production build passed. The active pack quality report has zero structural blueprint findings; this is not a production or business-policy certification.

Browser verification used an isolated hotel-reservation project. After Skip setup, the project advanced to Domain Knowledge with its reusable process ready for review and region still unspecified. No existing customer project was used for this write test.

[Optional setup preview](C:/Users/iamdn/.codex/visualizations/2026/10/15/01a13fa0-8b76-7c51-acd2-e454b3e33d11/studio-optional-industry-setup-2026-10-19.png)

[Process draft after skipping](C:/Users/iamdn/.codex/visualizations/2026/10/15/01a13fa0-8b76-7c51-acd2-e454b3e33d11/studio-industry-process-after-skip-2026-10-19.png)
