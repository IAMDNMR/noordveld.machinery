# Project-specific application source

Studio now has a separate model frontend generation path. The model writes React
and CSS for the project's business contract. There is no whole-application layout
template in this path. Domain blueprints still supply reusable business knowledge;
the trusted SDK supplies data transport and the compiler supplies the backend engine.

## User journey

1. Draft the requirements, process and data model.
2. In **Screens & UI**, choose **Generate interface**. An optional design direction
   can describe the desired working experience. A draft can also be generated through
   the **Preview** dialog before advancing the stage reviews.
3. The model plans pages with exact process/entity references, then writes individual
   source files. Strict TypeScript and an isolated esbuild invocation check them.
   Build diagnostics drive bounded, targeted file repairs. The builder requires strict
   TypeScript, and a browser pass checks responsive rendering, major accessibility
   findings, empty role workspaces, and optional demo-data loading. Invalid source is
   never substituted with a shared layout or saved over the last working version.
4. Browse the generated interface. **View source** shows the saved model source.
   The preview keeps temporary form data in the isolated iframe; workflow execution
   belongs to the running application's backend.
5. Review the design. New projects cannot accept the screen stage without a current
   generated frontend. Changes to the business contract mark generated code stale.
6. Compile/download after the normal approvals. The ZIP contains the model source,
   the captured transport SDK, compiled JS/CSS, the existing backend and manifests.
   The running application uses the exact compiled bundle used in Studio's preview.

## Persistence and review

The checked source and bundle are stored in the project's versioned definition.
The configured CockroachDB project adapter therefore keeps them with revision history;
retained release ZIPs continue to use the existing immutable release store.
Generation checks the expected revision again at save time. Ordinary client edits
cannot replace the compiled artifact or disable the generation requirement.

Design approval includes the generated artifact. Process approval remains scoped to
the business design. Source generation neither approves company policy nor advances
a process on the user's behalf. Existing projects without generated source retain an
explicitly labelled earlier component draft until converted; new Studio projects use
the model frontend requirement.

## Boundaries

- Generated source is parsed/type-checked/bundled as data. No generated npm scripts,
  plugins, server code or package installations are run by this generation service.
- Imports are limited to declared local modules, React, lucide-react and the SDK.
  Additional source lint rejects browser/network globals and executable markup; local
  document focus/event APIs remain available for keyboard-accessible dialogs.
- The preview runs in `sandbox="allow-scripts"`, without `allow-same-origin`, and
  with CSP blocking network access, external assets and form submission. A separate
  outer frame restricts application-frame navigation to data documents. This browser
  isolation is the security boundary; static lint is an additional check.
- The operational application runs on its own local runtime origin. The SDK uses that
  server's session, validation, permission and workflow APIs. Clients cannot choose a
  new workflow state or supply a rule result. Unimplemented rules still fail closed.
- Page bindings are declared by the model. A browser check can find measurable defects,
  but it cannot certify task coverage or business correctness; browse and review the
  result. Unresolved business spending decisions cannot become hard-coded UI limits.

## Local tools and hosted deployment

Run `npm ci` in `frontend/` and install the backend requirements. Source generation
requires Node.js, TypeScript, esbuild and the bundled builder scripts. Python invokes
the fixed Node helper with JSON on stdin. No model text becomes a shell command.

The current split Vercel deployment does **not** provide this local Node build
environment inside the Python service. Saved previews and stored downloads do not
need it. Fresh frontend generation in that deployment requires an explicit build
service or a different packaged execution environment; the current implementation
fails clearly when tools are absent. No hosted worker or new production identity
service has been provisioned.

Local operator generation (preserves history and does not approve or launch):

```powershell
python backend/scripts/generate_studio_frontend.py PROJECT_ID --expected-revision REVISION --brief "Design direction"
```

The language model uses the configured Studio provider. Credentials are never
embedded in the generated frontend or its preview bootstrap.
