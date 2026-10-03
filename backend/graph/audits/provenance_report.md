# Provenance report

Every node and relationship carries: `provenance_type`, `data_status`, `source_id`, `source_file`, `source_sheet`,
`source_record_id`, `source_name`, `source_ref`, `confidence`, `authoritative_flag`, `last_updated`.

## Classification

| Class | Meaning in this graph | Nodes | Relationships |
|---|---|---|---|
| SOURCE_DERIVED | Copied from the supplied catalogue workbook, traceable to sheet and row | 456 | 778 |
| DERIVED | Deterministic rule over source values (families, sub-categories, name groups, legacy business) | 165 | 391 |
| USER_PROVIDED | Declared by the project brief (workbook class DEMO): plants, order-status vocabulary | 10 | 6 |
| SYNTHETIC_DEMO | Generated demonstration data (`SYN_` sheets, gen_synthetic.py seed 42) | 1209 | 2637 |
| MISSING | Required by the model, absent in the data: not created, listed in `missing_data_register.csv` | 0 | 0 |
| UNKNOWN | Cannot be established: properties left absent (e.g. unresolved legacy numbers, interchangeability_status = UNKNOWN) | - | - |
| EXCLUDED | Source rows deliberately kept out, listed in `excluded_records.csv` | 40 rows | |

## Rules applied

- The workbook's row-level `data_class` decides the class; nothing is re-labelled. DEMO → USER_PROVIDED, SYNTHETIC →
  SYNTHETIC_DEMO.
- `authoritative_flag = false` on every record: the workbook states that nothing in it is externally verified.
- `confidence` keeps the workbook's own value (SOURCE_STATED, SOURCE_STATED_CONDITIONAL, RULE_DERIVED, NEEDS_REVIEW,
  NOT_STATED).
- Synthetic attributes of a part (status, orderable, weight, price...) are stored on separate `PartCatalogProfile` and
  `Price` nodes, so a synthetic value can never overwrite a catalogue value on `Part`.
- Synthetic coordinates (`SYN_geo_nodes`) are not put on plants, whose source coordinates are NOT_STATED.
- `DataSource` nodes (SRC-001, SRC-002, SRC-003, SRC-BRIEF) are the workbook's own source register plus the project brief; nodes
  and relationships reference them by `source_id`.

## Traversal to provenance

```cypher
MATCH (p:Part {part_number: 'NVM-1010-HY'})-[f:FITS]->(m:Machine)
MATCH (d:DataSource {source_id: f.source_id})
RETURN p.part_number, m.model_code, f.fitment_status, f.provenance_type, f.source_sheet, f.source_record_id, d.name
```
