# Research summary: European logistics model

Sources consulted for structure only (no data copied; every record in the graph is synthetic):
- European Commission, Trans-European Transport Network (TEN-T) and the nine core network corridors — https://transport.ec.europa.eu/transport-themes/infrastructure-and-investment/trans-european-transport-network-ten-t_en
- Eurostat, freight transport statistics, modal split — https://ec.europa.eu/eurostat/statistics-explained/index.php?title=Freight_transport_statistics_-_modal_split
- European Commission, inland waterways (NAIADES) and short-sea shipping pages — https://transport.ec.europa.eu/transport-modes_en
- Public manufacturer dealer-network pages, used only to understand how networks are organised (sales vs. service vs. parts roles), never for names or contacts.
(Section pages were read in the earlier research phase; links point to those pages and were not re-fetched in this phase.)

**Why these countries.** The EU27 only: US and UK are out of scope (the UK is not an EU member). Noordveld's plants are in NL and DE, so NL and DE carry the densest dealer, customer and ship-to coverage (14 dealers each); neighbours (BE, FR, PL, AT, CZ, IT, ES) come next; smaller and peripheral markets get one or two dealers each.

**Dealer density differs** because machinery demand follows industrial/construction/quarrying/port activity and fleet size: dense in the Benelux–German core and Northern Italy/Poland, thinner in the Baltics, Balkans and islands. Tier-1 dealers carry sales, workshop, parts and field service; thinner markets are often a single full-service dealer.

**Road is the default mode** — it carries the large majority of EU inland freight tonne-km — so every ship-to has a road route; spare parts are time-sensitive and small-parcel/pallet loads suit road.

**Other modes appear only where plausible:** rail on TEN-T corridors for long hauls (trunk ≥ 200 km); inland waterway on the Rhine–Danube and North Sea ports network (trunk ≥ 100 km, short road access); short-sea for islands and long coastal links (trunk ≥ 300 km or island destinations); air for urgent/critical shipments (≥ 300 km, from cargo airports). Multimodal routes always have explicit legs and at least two modes. Non-road options are dropped when they exceed 1.5× the direct road distance.

**TEN-T:** terminals and rail/water/sea links are labelled with the corridor they belong to (e.g. North Sea–Baltic, Rhine–Alpine). **Dealer/service structure:** sales, parts, workshop and mobile service are separate capabilities; territories are explicit (`SERVES_TERRITORY`), never inferred from distance.
