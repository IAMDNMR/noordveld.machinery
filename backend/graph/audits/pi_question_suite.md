# Parts Intelligence question suite

Every question ran through the real pipeline: Gemini (scope + intent + entities) -> approved intent registry -> Neo4j -> evidence -> grounded Gemini wording (checked; the template is used when the wording fails the check).

**27 of 27 passed.**

| Result | Question | Intent | Scope | Results | Evidence rows | Worded by | Answer |
|---|---|---|---|---|---|---|---|
| PASS | What machines are available? | MACHINE_LIST | IN_SCOPE | 15 | 12 | template | The catalogue holds 15 machines. Ask which parts fit any of them. |
| PASS | Which parts fit the NV-4500? | MACHINE_TO_PART | IN_SCOPE | 52 | 12 | template | NV-4500 is associated with 52 parts in the current graph. |
| PASS | Which machines use NVM-1010-HY? | PART_TO_MACHINE | IN_SCOPE | 2 | 2 | gemini | NVM-1010-HY fits the NV-3200 (demo) and NV-4500 (demo) machines. |
| PASS | What assemblies contain NVM-1010-HY? | PART_TO_ASSEMBLY | IN_SCOPE | 1 | 1 | gemini | NVM-1010-HY (demo) is part of the Hydraulics module, NV series (demo). |
| PASS | Which suppliers are connected to NVM-1010-HY? | PART_TO_SUPPLIER | IN_SCOPE | 2 | 2 | gemini | NVM-1010-HY (demo) is supplied by Veldstra Hydraulics (demo) and Rijnmond Hydraulic Supply (demo). These are synthetic demo data entries. |
| PASS | Where is NVM-1010-HY available? | PART_TO_LOCATION | IN_SCOPE | 9 | 9 | gemini | NVM-1010-HY (demo) is available at Bakker Parts Depot Coevorden (demo), Kessler Parts Depot Lingen (demo), Noordveld Central Warehouse Assen (demo), and Regiona |
| PASS | Which warehouses have NVM-1010-HY? | PART_TO_LOCATION | IN_SCOPE | 9 | 9 | gemini | NVM-1010-HY (demo) is available at Bakker Parts Depot Coevorden (demo), Kessler Parts Depot Lingen (demo), Noordveld Central Warehouse Assen (demo), and Regiona |
| PASS | What compliance requirements are associated with NVM-1010-HY? | PART_TO_COMPLIANCE | IN_SCOPE | 1 | 1 | gemini | NVM-1010-HY (demo) is associated with Hydraulic components (demo) compliance. |
| PASS | Which service plans require NVM-1010-HY? | PART_TO_SERVICE_PLAN | IN_SCOPE | 1 | 2 | gemini | SVC-2000-002 (demo) requires NVM-1010-HY (demo). This is a synthetic demo data item. |
| PASS | Which orders contain NVM-1010-HY? | PART_TO_ORDERS | IN_SCOPE | 2 | 2 | gemini | The orders ORD-0010 (demo) and ORD-0013 (demo) contain NVM-1010-HY (demo). |
| PASS | Has order ORD-0013 shipped? | ORDER_STATUS | IN_SCOPE | 2 | 3 | gemini | The evidence shows that order ORD-0013 (demo) has shipment SHP-0010 (demo). The shipping status of order ORD-0013 (demo) is unavailable in the provided evidence |
| PASS | Where is the shipment for order ORD-0014 now? | ORDER_STATUS | IN_SCOPE | 2 | 4 | gemini | The information regarding the location of shipment SHP-0011 (demo) for order ORD-0014 (demo) is unavailable. |
| PASS | What dealers are in Zwolle? | GEO_LOCATION | IN_SCOPE | 1 | 1 | gemini | IJsselvallei Equipment (demo) is a dealer located in Zwolle, NL. This information is based on the provided synthetic demo data. |
| PASS | What dealers are in Assen? | GEO_LOCATION | IN_SCOPE | 0 | 0 | template | No dealer is recorded in Assen. |
| PASS | What is the provenance of NVM-1010-HY? | PART_PROVENANCE | IN_SCOPE | 5 | 21 | gemini | The part NVM-1010-HY is recorded in the noordveld-parts-catalog.xlsx source-derived file. It originates at a plant, which is a source-derived relationship. |
| PASS | Show me everything connected to the NV-4500. | MACHINE_GRAPH | IN_SCOPE | 1 | 5 | gemini | The NV-4500 (demo) is a member of the NV series and is branded as Noordveld. It is manufactured at Assen (NL), fits 52 parts, and has 4 service plans (demo). |
| PASS | What parts are used across multiple machines? | SHARED_PARTS | IN_SCOPE | 93 | 40 | template | 93 parts are recorded as fitting more than one machine. |
| PASS | Which parts are low on stock? | LOW_STOCK_PARTS | IN_SCOPE | 9 | 9 | template | 9 parts are Limited or on Backorder in the catalogue (4 on Backorder). |
| PASS | Which parts does Hanselmann Kuehlsysteme supply? | SUPPLIER_GRAPH | IN_SCOPE | 13 | 12 | template | Hanselmann Kuehlsysteme (demo) (Hannover, DE) is connected to 13 parts through SUPPLIED_BY. It is connected to the categories Filtration, Cooling. |
| PASS | Which machines are manufactured in Lingen? | MACHINE_LIST | IN_SCOPE | 5 | 5 | gemini | The information regarding which machines are manufactured in Lingen is unavailable in the provided evidence. |
| PASS | Which warehouses have this part? | PART_TO_LOCATION | NEEDS_CLARIFICATION | 0 | 0 | template | Which part number or name are you asking about? |
| PASS | Has this order shipped? | ORDER_STATUS | NEEDS_CLARIFICATION | 0 | 0 | template | Could you please provide the order number? |
| PASS | Is NVM-1010-HY interchangeable with NVM-1050-CL? | PART_TO_PART | IN_SCOPE | 0 | 0 | template | No graph relationship links NVM-1010-HY and NVM-1050-CL, so the graph does not establish that they are interchangeable, alternatives or replacements. |
| PASS | Does Hanselmann Kuehlsysteme service the NV-4500? | ENTITY_PATH | IN_SCOPE | 1 | 2 | gemini | The provided evidence does not state that Hanselmann Kuehlsysteme (demo) services the NV-4500. This information is unavailable. |
| PASS | Is NVM-1010-HY certified? | PART_TO_COMPLIANCE | IN_SCOPE | 1 | 1 | gemini | NVM-1010-HY (demo) has the Hydraulic components (demo) compliance. |
| PASS | Which orders contain NVM-4410-SK? | PART_TO_ORDERS | IN_SCOPE | 0 | 0 | template | No order containing NVM-4410-SK is recorded in the graph. |
| PASS | What is the capital of France? | UNSUPPORTED | OUT_OF_SCOPE | 0 | 0 | template | I can help with Noordveld Parts Intelligence questions about parts, machines, fitment, suppliers, assemblies, availability, compliance, relationships and proven |
