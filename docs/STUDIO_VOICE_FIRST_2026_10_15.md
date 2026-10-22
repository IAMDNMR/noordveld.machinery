# Design Studio, voice first — 15 October 2026

Design Studio is now one workspace in which a person says what application they want, answers the assistant's questions, watches the
process, data model and screens being designed, reviews and approves them, and generates, tests and launches a real application.
`/design-studio` opens it. The earlier structured editor is still there as a secondary option (`/design-studio/visual`, "Structured editor").

## Run it locally

The Studio only runs against the isolated local app (demo identities, loopback only, temporary SQLite). From the repository root:

```bash
# API (a dedicated temp directory; the name must start with noordveld-studio-)
DESIGN_STUDIO_LOCAL_DEV=1 APP_ENV=local DESIGN_STUDIO_LOCAL_DB="$TEMP/noordveld-studio-demo/studio.sqlite" \
  python -m uvicorn app.design_studio.local_app:app --app-dir backend --host 127.0.0.1 --port 8012   # the directory must exist first
# web (frontend/config/vite.studio.ts proxies /api to 8012 and serves on 5192)
cd frontend && STUDIO_WEB_PORT=5192 STUDIO_API_TARGET=http://127.0.0.1:8012 npm run dev:studio
```

Sign in as `studio-alice` (project owner: builds, generates, launches) and `studio-bob` (business approver: approves, cannot edit). Approval
needs a person other than the project's creator, so Alice builds and Bob approves.

## What it is made of

| Piece | Where |
| --- | --- |
| Conversation turn, proposals, apply, undo, live state, voice and run routes | `backend/app/api/routes/studio_conversation.py` (included in the Studio router, so identity, organization and permission gates apply) |
| The closed set of typed changes and the engine that applies them | `backend/app/assistant/studio_actions.py` |
| Planner: language model, or the labelled local rules | `backend/app/assistant/studio_agent.py` |
| Stage statuses (computed, never asserted) | `backend/app/design_studio/stages.py` |
| Speech (Deepgram) | `backend/app/assistant/speech_deepgram.py` |
| Language model (NVIDIA, Groq or Gemini) | `backend/app/llm/` (`nvidia.py` is new; `create_studio_llm`) |
| Run what was generated: its tests, the application itself | `backend/app/design_studio/runtime_launcher.py` |
| Workspace | `frontend/src/pages/StudioWorkspacePage.tsx`, `frontend/src/components/studio/` |

## How a turn works

1. The person speaks or types. Speech is recorded in the browser, ends on silence, goes to `POST /design-studio/voice/transcribe`
   (Deepgram Nova-3), and the **text is shown in the conversation before it is used**. Audio is processed in memory and never stored.
2. `POST /projects/{id}/studio/turn` plans the turn. The language model sees a compact digest of the saved specification and the last
   few turns, and answers with JSON: what to say and a list of **typed actions** from a closed vocabulary (set the brief, add a
   requirement/role/entity/rule/exception, create a process, insert a step, add an approval, link a requirement, …). Its output is
   untrusted: every field is validated, unknown actions are dropped, ids and permissions are never taken from it.
3. The engine resolves every reference against the saved specification (by id or name; ambiguous names are refused, never guessed), builds the
   item with the same models the structured editor uses, and validates the whole candidate.
4. **Additive, low-impact changes are saved at once as a new revision** (requirements, data, answers, links). **Changes to roles, rules, approvals,
   process structure and reference knowledge come back as a proposal** bound to the exact revision and content digests; nothing is saved until
   `POST …/studio/apply` re-applies the same actions and checks the digest. "Apply" can be pressed or spoken ("yes, apply it"); a spoken
   confirmation only ever acts on the one proposal on screen and is shown in the conversation first.
5. Every change is an ordinary project revision: history, comparison, approval staleness, safe regeneration and the audit trail are unchanged.
   Undo restores earlier content as a *new* revision. A change that makes an approval stale says so.
6. The first request of a project is recorded as its goal. When reference knowledge exists for the domain (for example the Transport
   and warehouse pack for a TMS), the design builds on it instead of the model improvising a foundation; it is still a reviewed proposal.

Approval is never given by conversation. The process and the design each need a separate approver in the Validation stage.

## Stages

Requirements, Domain Knowledge, Business Process, Data Model, Screens & UI, Rules & Logic, Roles & Permissions, Validation, Generate Application.
Status is one of not started, in progress, needs input, ready for review, completed, blocked, computed from findings, open questions and
decisions, approvals and (for generation) the generator's own result. A stage is **completed** only when its approval is valid for the current
content, or — for Generate — when the generator ran and all its checks passed. The next stage is prepared when its prerequisite holds (an approved
process generates its screens). Editing after approval makes the approval stale and the stages stop claiming to be complete.

## Voice, honestly

- Speech: on when `DEEPGRAM_API_KEY` is present, off with `STUDIO_VOICE=off`. Without it the microphone is shown as unavailable with the reason; typing works everywhere.
- Language model: `AI_PROVIDER` (`nvidia` | `groq` | `gemini`) when set, otherwise `LLM_PROVIDER`; `STUDIO_ASSISTANT=off` switches it off. One provider,
  chosen by configuration; there is no silent failover. If it is missing, rate limited or returns something unusable, the turn is answered by the
  built-in rules (which understand explicit requests only) and the reply says so.
- States shown: ready, listening (with a level meter), transcribing, thinking, speaking. Interrupt by pressing the microphone while it speaks, "Stop speaking",
  or saying "stop"; "Keep listening" re-opens the microphone after each reply and lets a sustained louder voice interrupt it.
- Credentials are never returned, logged or placed in a URL. `GET /design-studio/voice/status` reports names and reasons only.

## Real applications

The Generate stage runs the deterministic compiler for the saved revision (resolve → specify → plan → generate → check), shows every check and file,
offers the ZIP, runs the generated application's own independent tests in a separate process, and launches it on this computer only
(127.0.0.1, own SQLite database, demonstration identities, server-side role/permission checks, atomic audited writes). The Screens stage is
labelled a visual preview; the running application is a different thing and the interface says so. Rules that have no executable binding are listed
as not executable yet, and the application refuses the actions that depend on them instead of guessing.

## Verified in this change

- Backend: full suite passes with network access disabled (`python backend/scripts/test_offline.py`), including 23 new tests (action engine, stages,
  proposals, tamper/replay refusal, revert, permissions, Deepgram request/response/failure handling with a mock transport, running the generated tests and application).
- Frontend: 411 tests pass; typecheck clean; no new lint errors.
- Browser journey (`frontend/scripts/studio-voice.e2e.mjs`, real Edge, real Deepgram speech-to-text and text-to-speech, real language model; a recorded sentence is the
  microphone): speak the TMS request → transcript shown → assistant answers aloud → reference-knowledge proposal reviewed → applied by voice → process diagram and entity
  diagram → role proposed and applied → business decisions answered → Bob approves the process → screens generated → Bob approves the design → application generated
  (55 files, 9 checks) → its 3 tests pass → launched and answering its own API → stopped. No page errors.
  `python backend/scripts/make_voice_fixtures.py DIR` makes the two recordings.

## Known limits

- Hands-free listening and speaking over the assistant (voice barge-in) are implemented but could not be exercised end to end here (the test microphone is a file);
  the interrupt button and spoken "stop" are verified. Speakers without echo cancellation can make barge-in trigger on the assistant's own voice.
- The Groq key on this project allows 8,000 tokens per minute; a turn is about 2.5–3.5k, so two quick turns can be rate limited (falls back to the labelled rules).
  The NVIDIA planner model answers in 3–20 seconds depending on load. `STUDIO_MODEL=fast` uses the smaller NVIDIA model (about 4–9 s) but in testing it proposed duplicates and malformed steps, so it is opt-in.
- The conversation is kept in the browser (per project) and the specification on the server; audio is never kept.
- The structured editor remains for fine-grained edits (conditions, rule bindings, sample data); the conversation covers the common changes.
- Production use remains gated as before (`backend/DESIGN_STUDIO_ACTIVATION.md`): demo identity is local-only, durable storage and a real identity provider are not wired.
