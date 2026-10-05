# Data classification

| Class | Meaning here | Nodes | Relationships |
|---|---|---|---|
| SOURCE_DERIVED | taken from the supplied source workbook / catalogue | 456 | 778 |
| DERIVED | computed from source data | 165 | 391 |
| USER_PROVIDED | supplied by the user (plants, original statuses, data source) **and** written by the running app (orders, carts, the order-status vocabulary of the direct-order flow, `source_id = APP-SESSION`) | 32 | 26 |
| SYNTHETIC_DEMO (= SYNTHETIC_DEMO_DATA) | generated demonstration data | 9,169 | 48,044 |
| UNKNOWN / NOT_CONNECTED | none present | 0 | 0 |

All 7,647 nodes and 44,569 relationships of batch `EUFOUND-2026-10-04` (8,021 / 45,700 as first seeded, before the customer master was removed) are SYNTHETIC_DEMO with `source_id SRC-005`, `authoritative_flag false`, `demo_marker SYNTHETIC_DEMO_DATA`, and (relationships) a unique `rel_id`. Synthetic data is never relabelled as source or real; the SOURCE/DERIVED DATA INTEGRITY CHECKSUM (SOURCE_DERIVED, DERIVED and the supplied, non-app-written USER_PROVIDED seed records; records with `source_id = APP-SESSION` are excluded because the app writes them) is unchanged by the seed. Figures as of 2026-10-05. Stock `UNKNOWN` is stored without a quantity (never zero). Distances are `SYNTHETIC_*_ESTIMATE`; delivery estimates are `ESTIMATED`; freight rates are synthetic EUR records.
