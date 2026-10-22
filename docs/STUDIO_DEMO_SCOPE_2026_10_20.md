# Studio demo scope

The owner clarified that this is a demonstration: viewers need to see and explore the application. Production sign-in and a hosted execution/worker service are deferred, not blockers for this demo. Earlier requests for those provider details are no longer pending.

## Implemented viewing path

- `/design-studio/demo` is a read-only reference application viewer. It opens directly, without Studio demo sign-in, a worker, database access, or runtime launch. It browses the curated Transport Operations design and its workflow/record layouts.
- The public reference snapshot excludes approval identities, fixture records, knowledge-adoption state, discovery questions, decisions and customer integration settings. It is a bundled design, not an export of operational databases or private Studio projects. It does not automatically update when a private project changes.
- The Studio landing page offers **Explore the demo**. If the editable local Studio cannot open, its entry page also offers the public demo.
- Every project with generated screens has a **View demo** action in Generate. That preview uses the currently saved design, supports browsing screens/records and theme exploration, and needs no application process. Starting a local executable remains a separate option.
- The preview labels its behavior honestly: records are not saved and business rules are not executed in this viewer. The local executable and its existing records remain available independently.

## Demo acceptance checks

- Open the public reference page without Studio credentials.
- Navigate from Overview to Plan the shipment and through other workflow/record pages.
- Confirm no login, launch, integration or saving request is required by the viewer.
- Use the mobile navigation without horizontal overflow.
- Verify the private saved project and runtime records remain unchanged.

Component tests cover public browsing with a rejected network stub, sanitized snapshot content and viewing a project when workers are unavailable. The browser check exercised task navigation and the mobile layout. Frontend code/build checks and the source test suite were run.

Verification result: 426 frontend tests passed across 32 files; TypeScript, lint, formatting and the production build passed. No backend, saved-project or operational-record change was needed for this viewing path.

## Deferred from this demo

Production identity, hosted generated-app execution, live PostgreSQL migration, GitHub deployment synchronization and provider-specific integrations remain future delivery work. Backend authentication is not weakened to make public viewing possible. Existing skipped external/read-only fixture tests and draft domain references stay explicit; a view-only demo does not turn them into validated customer integrations or confirmed business policies.

The remaining Studio quality work should be judged against this demonstration scope, with reproducible UI/function failures fixed as found, rather than requiring production hosting infrastructure.
