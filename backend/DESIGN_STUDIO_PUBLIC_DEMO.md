# Design Studio on Vercel: public demo (no sign-in)

Anyone who opens `/design-studio` gets their own anonymous workspace. There is no account: a random visitor id lives in a signed
cookie, owns only the projects that browser creates, and nobody can read another visitor's projects or any real account's.
Shared domain knowledge stays read-only (nobody holds domain permissions on a deployed backend). The commerce demo sign-in stays closed.

## Limits (code: `app/design_studio/visitors.py`)
- 3 live projects per visitor (Trash does not count).
- 40 assistant/voice/generation requests per visitor per hour, and 600 per server instance per hour. Best effort: serverless
  instances do not share memory, so the true ceiling scales with the number of instances.
- Launching or testing a generated application needs a local process, so on Vercel it answers "available when running locally".
- Visitor projects are never expired automatically. Plan a clean-up (for example, delete visitor projects older than 30 days).

## Settings to add in Vercel (Project, Settings, Environment Variables)
| Variable | Value |
|---|---|
| `DESIGN_STUDIO_PUBLIC_DEMO` | `1` (the switch; without it the Studio stays closed on a deployed site) |
| `APP_ENV` | `production` |
| `SESSION_SECRET` | a long random value (signs the visitor cookie) |
| `SESSION_COOKIE_SECURE` | `true` (the cookie is sent only over https) |
| `DESIGN_STUDIO_STORAGE_BACKEND` | `cockroach` |
| `DESIGN_STUDIO_POSTGRES_ENABLED` | `1` |
| `DESIGN_STUDIO_DATABASE_URL` | the CockroachDB connection string for `noordveld_studio` |
| `DESIGN_KNOWLEDGE_SOURCE` | `neo4j`, with the existing `NEO4J_*` values |
| the language-model key and provider variables | as in `backend/.env` (NVIDIA, Gemini, Groq as used) |

The CockroachDB certificate: if `DESIGN_STUDIO_PG_CA_FILE` is not set or the file is missing, the public CA bundle is used and the
connection stays `verify-full`. Do not commit `backend/.env`; set the values in Vercel only.

## What is not covered
Real sign-in, invitations and organizations (see `DESIGN_STUDIO_ACTIVATION.md`) are a separate step. This public mode is for a demo:
do not put confidential designs in it, since anyone who has the project's browser cookie can open it.
