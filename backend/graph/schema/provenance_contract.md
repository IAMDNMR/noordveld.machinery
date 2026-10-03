# Provenance contract

Required on every node and relationship:

| Property | Meaning |
|---|---|
| provenance_type | SOURCE_DERIVED, DERIVED, USER_PROVIDED or SYNTHETIC_DEMO |
| data_status | Same value as provenance_type (the marker queries filter on) |
| source_id | DataSource node id (SRC-001 catalogue, SRC-002 rules, SRC-003 synthetic generator, SRC-BRIEF project brief) |
| source_file | noordveld-complete-dataset-synthetic-demo.xlsx |
| source_sheet | Workbook sheet |
| source_record_id | Row id in that sheet |
| source_name / source_ref | The workbook's own source citation (row / column reference for catalogue rows) |
| confidence | Workbook confidence, verbatim |
| authoritative_flag | false (nothing is externally verified) |
| last_updated | Workbook last_updated |

Not used, because the workbook does not provide them (never fabricated): source_url, effective_from / effective_to (except
`Price.valid_from / valid_to`), created_at.

MISSING data is never stored as a node or value; it is listed in `graph/audits/missing_data_register.csv`. EXCLUDED rows
are listed in `graph/audits/excluded_records.csv`.
