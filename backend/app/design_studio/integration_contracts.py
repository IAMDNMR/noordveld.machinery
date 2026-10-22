"""Provider-neutral record exchange; no customer connection is fabricated."""

import json


def files(definition):
    contracts = []
    for integration in definition.business.integrations:
        contracts.append(
            {
                "id": integration.id,
                "name": integration.name,
                "source_system_hint": integration.system,
                "provider": None,
                "connection_status": "not_configured",
                "direction": integration.direction,
                "events": integration.events,
                "entity_schemas": {
                    entity: f"../schemas/{entity}.schema.json" for entity in integration.entity_ids
                },
                "failure_handling": integration.failure_handling,
                "contract_status": integration.contract_status,
                "mapping": [],
                "record_api": f"/api/integrations/{integration.id}/records",
                "implemented": [
                    "signed_inbound_records",
                    "idempotent_receipts",
                    "scoped_snapshot_export",
                ],
                "not_implemented": [
                    "provider_specific_delivery",
                    "binary_document_storage",
                    "change_data_capture",
                ],
                "required_configuration": [
                    "provider",
                    "authentication_secret_reference",
                    "tenant",
                    "service_role",
                    "field_mapping",
                ],
            }
        )
    return {
        "integrations/contracts.json": json.dumps(
            {"version": 2, "integrations": contracts}, sort_keys=True, indent=2
        ).encode(),
        "integrations/README.md": b"""# Customer integration setup

Generated apps own their schemas and database. No Noordveld API is connected.
The portable runtime provides signed inbound records and scoped outbound snapshot
export. Provider-specific delivery, binary document storage and change-data capture
require an adapter. Document records contain metadata/references only.

Keep configuration outside exported source and inside the isolated data directory.
Start with --integration-config PATH. The file is a JSON array, for example:
[{"id":"DECLARED_INTEGRATION_ID","enabled":true,"tenant":"demo_noordveld",
  "role":"APPLICATION_ROLE_ID","secret_env":"CUSTOMER_EXCHANGE_SECRET",
  "entities":{"ENTITY_ID":{"external_field":"local_attribute"}}}]

Use IDs from contracts.json/schema.json, a least privileged role and explicit field
allowlists. Secret environment values need at least 32 characters. Never commit
secrets or put them in Neo4j. All connections are disabled until configured.
This is a local loopback runtime; production identity, HTTPS and hosting need a
separate deployment implementation.

POST /api/integrations/{id}/records with application/json:
{"event_id":"unique-event","entity_id":"ENTITY_ID","data":{"external_field":"value"}}
For updates include record_id and expected_revision. Retry the identical body and
event_id after transport failure; changed payload with the same ID returns 409.
Record validation, references, ownership and revisions are enforced. Record and
receipt commit atomically. This API never advances a process.

GET the same route with ?entity_id=ENTITY_ID&after=0 for at most 100 records.
Use next_cursor for the next page. Only mapped fields in the configured tenant
are returned. This is snapshot pagination, not a change feed; restart at zero for
another refresh. Contract direction restricts inbound versus outbound operations.

Both methods require X-Studio-Timestamp (Unix seconds) and X-Studio-Signature.
Signature is HMAC-SHA256 hex over timestamp + newline + method + newline + exact
request path including query + newline + raw body bytes. Use an empty GET body.
Requests expire after five minutes. See runtime/integrations.py signature().
Payloads cannot set tenant, role, process state or rule outputs. Write receipts
contain IDs/revisions only, never unmapped stored business fields.
""",
    }
