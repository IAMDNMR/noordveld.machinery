# Transport Operations reference

Saved 19 October 2026. Project `app_transport_operations_20261019`, revision 12.

Generated UI snapshot refreshed 20 October 2026: work overview, full-width process summary, task record context and mobile navigation. The business specification and demo workflow data are unchanged.

The archive was refreshed again with application-derived independent tests: 43 pass, none fail, and seven require creation/import fixtures for read-only warehouse data. Tests exercise every configured decision branch as well as record validation, persistence and access boundaries. See `docs/STUDIO_STAGE_AUDIT_2026_10_20.md` for the stage review and remaining customer setup.

The editable application and its review history are stored in Neo4j in the local Studio namespace. Open `http://localhost:5180/design-studio` with the Studio servers running. The four previous demos are recoverable from Trash.

This folder also preserves an independent snapshot:

- `application.json`: saved application specification.
- `application.zip`: generated source, API schema, process, permissions, provenance and runtime guide.
- `demo.sqlite`: synthetic demo records and five shipments at different workflow stages. Active login sessions are excluded.
- `start-reference.py`: starts the saved generated application locally, restoring the demo database only when no existing database is present.

Run `python backend/data/studio-reference/transport-operations/start-reference.py` from the repository root. Python 3.12 is sufficient; the generated runtime uses the standard library. Open the printed local URL and choose a demonstration role. If Studio already runs this application on port 8100, the script chooses another available local port.

The executable application is the Python runtime in the archive. Its React source is a design preview. This snapshot is for local review, not a production deployment. The process and design approvals record automated QA of synthetic data, not customer acceptance. Carrier tracking is not connected to a provider; the manual tracking workflow can be reviewed. Real hosting, authentication and customer integrations remain deployment work.
