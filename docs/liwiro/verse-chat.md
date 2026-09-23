# Verse Chat in Liwiro

## Summary

Verse Chat is Liwiro's multi-agent collaboration workspace. It runs through the Liwiro backend, uses the `liwiro/verse` scaffold as the behavior spec, persists thread state durably in BSON-backed storage, and writes durable shared knowledge into `liwiro/verse/mind-share`.

The product route remains `/verse-ai` for compatibility, but the product name in the UI is now **Verse Chat**.

## Source of truth

Verse Chat behavior is grounded in:

- `liwiro/verse/agents/*.persona.md`
- `liwiro/verse/skills/*.skill.md`
- `liwiro/verse/router/*.md`
- `liwiro/verse/mind-share/*.md`

These files define:

- which specialist agents exist
- what each agent is allowed to do
- how initial routing works
- when handoffs should happen
- which `mind-share` files each agent can read and write

## Architecture

Verse Chat is implemented as a backend-mediated subsystem, not as a direct browser-to-model integration.

Current runtime flow:

1. The frontend opens `/verse-ai`.
2. The frontend calls authenticated Verse backend routes under `/platform/verse/...`.
3. Protected Liwiro pages outside `/verse-ai` also expose a bottom-right Verse Chat assistant dock.
4. The backend loads Verse personas, skills, router rules, and `mind-share`.
5. The backend selects the active agent or honors an explicit `@agent` invocation.
6. The backend retrieves only the relevant Verse and platform context.
7. The backend calls the configured AI provider through the shared provider abstraction.
8. The backend stores thread state, messages, handoffs, and synthesis in BSON-backed Verse Chat storage.
9. Safe append-oriented `mind-share` writes are applied and audited.

## Persistence

Verse Chat runtime state is stored under the configured Verse data directory:

- default: `liwiro/data/verse`

This store currently contains:

- thread documents
- agent display-name override profiles

`mind-share` itself remains file-backed Markdown under:

- `liwiro/verse/mind-share`

That split is intentional:

- thread state is runtime/audit data
- `mind-share` is shared durable knowledge authored through controlled append-style writes

## Agents

Verse Chat ships with these specialists:

- Liwiro Architect → `Kalulu`
- Liwiro Analyst → `Ananse`
- Liwiro Reliability Advisor → `Ntiili`
- Liwiro Compliance Advisor → `Dage`
- Liwiro Documentation Advisor → `Nzou`

Users can explicitly route a prompt by mention, for example:

- `@Kalulu review this API boundary`
- `@Liwiro Reliability Advisor assess rollout risk`

If there is no explicit mention, Verse Chat starts with:

- `Kalulu` / Liwiro Architect

The router files still shape specialist remit, retrieval relevance, and handoff behavior:

- `liwiro/verse/router/agent-routing.md`

## Handoffs

Agents may invite another agent when the topic crosses domains. Handoffs are:

- visible in-thread
- reasoned
- limited to avoid unnecessary agent pileups
- expected to produce an actual specialist reply, not only a narrated invite

Handoff rules are defined in:

- `liwiro/verse/router/handoff-rules.md`

## Retrieval

Verse Chat does not dump the whole scaffold into every prompt. Retrieval is scoped to:

- recent thread messages
- the current thread summary
- the active persona
- relevant skills
- relevant public manuals and references
- relevant `mind-share` files inside the agent's read scope
- relevant learned correction records from earlier Verse failures
- current Liwiro context passed from the UI

Each generated agent message stores retrieval trace metadata so the UI can show which sources shaped the answer.

Verse Chat now presents that metadata in collapsed inspect views instead of pushing it into the main chat flow. Normal replies are meant to read like ordinary chat, while technical traces, provider/model details, and durable write details stay available but out of the way.

## Prompt and context flow

Verse Chat now uses an OpenClaw-style prompt assembly flow instead of a flat prompt.

For a normal lead turn, the backend assembles context in this general order:

1. Verse bootstrap files such as identity, soul, user model, agent topology, and tools.
2. The active specialist profile and contract.
3. Universal guardrails and thread-behavior rules.
4. Current thread summary and recent thread delta.
5. Relevant skills and allowed `mind-share` documents.
6. Structured references and manuals such as the Liwiro platform reference and Verse-Verun references.
7. Learned correction records and current page context from Liwiro.

Invited specialist follow-up turns use a narrower `minimal` prompt mode. That mode keeps the handoff focused and lighter-weight while still carrying the current specialist identity, tools, relevant thread delta, and the most relevant platform/reference context for the specific question.

Each generated agent message stores a prompt assembly report in inspect metadata so operators can see how the answer was grounded without exposing raw prompt text in the visible chat.

## Page context and inspect metadata

Verse Chat treats attached Liwiro page context as first-class runtime input, not decorative metadata.

Common context fields include:

- `pathname`
- `screen`
- `pageKind`
- `selectedServiceId`
- `selectedServiceName`
- `desiredArtifactKind`

Inspect metadata for generated Verse messages can include:

- `promptMode`
- `contextReport`
- `bootstrapFiles`
- `handoffChain`
- `synthesisParticipants`
- truncation warnings when a context block had to be shortened

This split is intentional:

- the visible reply should stay concise and operator-friendly
- inspect metadata should explain routing, retrieval, prompt assembly, and multi-agent flow

## Cross-page assistant

Verse Chat is not limited to the dedicated `/verse-ai` workspace.

On authenticated Liwiro pages other than the Verse Chat page, Liwiro now exposes a bottom-right Verse Chat assistant dock. It behaves like a normal chat surface and can use current page context to prepare page-specific artifacts and actions.

Current page-aware action targets:

- Service Builder: draft LAPIS configs, open them in the builder, and generate services after confirmation
- Service Manager: prepare start, stop, and delete actions for existing services and run them after confirmation
- VI Portal: draft or revise Versa source, load it into the editor, and run it in the VI terminal after confirmation
- VDB Portal: prepare VDB query JSON, load it into the console, and run it after confirmation
- Ananse Workbench: open richer analytics views and refresh chart-ready analysis on saved datasets

On other pages, the dock still provides contextual help even if there is no direct action target.

## Chat behavior

Fresh threads begin with the placeholder title `Hello, Chat`. Once Verse Chat has enough context to produce a real summary, the thread title and sidebar summary are updated automatically.

Verse Chat should not expose raw JSON blobs, raw LAPIS, raw Versa source, or raw VDB query bodies in normal visible chat replies. When a specialist prepares something technical, the chat reply stays conversational and the concrete payload is attached as an action card or hidden inspect detail instead.

Verse Chat now validates technical artifacts before presenting them as ready:

- LAPIS drafts are checked against the backend validator and concrete service requests should include models and endpoints
- Versa drafts are checked against current syntax expectations such as `#` single-line comments
- VDB drafts are checked for portal-ready JSON object shape

Action cards may therefore show:

- `Validated`
- `Repaired`
- `Blocked`

Verse should not claim a draft was loaded or executed until the target page or backend has confirmed that action.

## Ananse analytics

Ananse is no longer limited to a small inline metric bar card.

Liwiro now includes a full-screen `Ananse Workbench` at `/ananse-workbench` with:

- pasted dataset ingestion
- archived CSV, TSV, and JSON uploads
- saved dataset history per Liwiro user
- chart switching across bar, grouped bar, stacked bar, line, area, pie, donut, scatter, histogram, leaderboard, table, and metric-list views
- filters, aggregation, and comparison controls
- reusable dataset previews and findings

Uploaded files are handled in two layers:

- the original file is archived in the Verse data area for provenance
- the parsed dataset is stored separately as normalized rows and inferred column metadata

Verse Chat can still show a compact analytics card inline, but deeper dataset work should move into the Ananse Workbench.

## mind-share writes

Verse Chat writes to `mind-share` using append-style structured entries only.

Every applied write records:

- timestamp
- agent id and display name
- confidence
- basis
- content type
- thread id
- content

Verse Chat does not silently rewrite stable shared records. The write guardrails come from:

- `liwiro/verse/mind-share/guardrails.md`

## Learning loop

Verse Chat now records validated lessons from corrected or failed interactions. These lessons can improve later turns by:

- steering retrieval toward known pitfalls
- reinforcing current platform rules such as valid LAPIS structure and Versa syntax
- highlighting where Verse actuators or backend APIs still need stronger support

This learning is curated operational memory, not raw transcript dumping.

## Provider abstraction

Verse Chat uses a provider layer instead of a hardcoded model client.

Current providers:

- Google Gemini
- Anthropic Claude
- OpenAI / ChatGPT API

Current config:

```env
AI_PROVIDER=openai
GOOGLE_API_KEY=change_me_google_api_key
GOOGLE_MODEL=gemini-3-flash-preview
ANTHROPIC_API_KEY=change_me_anthropic_api_key
ANTHROPIC_MODEL=claude-sonnet-4-20250514
OPENAI_API_KEY=change_me_openai_api_key
OPENAI_MODEL=gpt-5-mini
```

The backend default provider fallback is currently `openai`.

Place those keys in local env files that the backend loads on startup:

- preferred: `liwiro/backend/.env.local`
- optional shared local file: `liwiro/.env.local`

Verse Chat runs through the backend, so provider keys should live in a backend-loaded env file, not in committed docs, frontend-only env files, or tracked source files.

Verse Chat lets users switch between configured providers directly from the chat composer. The active thread keeps the selected provider and model.

The provider abstraction is designed so additional providers can still be added later without rewriting Verse Chat orchestration.

## Capability and actuator API

Verse Chat now maps its staged actions onto the shared platform capability API:

- capability registry: `/platform/capabilities`
- capability detail: `/platform/capabilities/<capability_id>`
- generic action catalog: `/platform/actions/catalog`
- generic preview: `/platform/actions/preview`
- generic execute: `/platform/actions/execute`
- Verse compatibility routes: `/platform/verse/actions/...`

This splits responsibilities more cleanly:

- the capability registry describes what Liwiro can do, where it should happen, and which stages it supports
- Verse artifacts carry `capabilityId` metadata so page-navigation, prepare, and execute cards stay mapped to a stable backend contract
- page-local artifacts like Service Builder drafts, VI drafts, VDB queries, and Ananse analysis still apply through the relevant page
- server-executable capabilities like Service Manager lifecycle actions can run through the shared backend action API
- the Liwiro CLI now uses the shared platform action API for service-manager start, stop, and delete operations, so CLI and Verse share the same capability ids and execution path

Ananse dataset and analysis APIs live alongside the rest of Verse under `/platform/verse/...`, including:

- dataset list and read
- pasted dataset create
- upload-backed dataset create
- analysis refresh for a saved dataset

## Google Gemini local developer setup

Use Google AI Studio as the first development path.

1. Go to Google AI Studio.
2. Sign in with a Google account.
3. Create or view an API key.
4. Store the key in local environment variables only.
5. Configure Liwiro with:

```env
AI_PROVIDER=google
GOOGLE_API_KEY=change_me_google_api_key
GOOGLE_MODEL=gemini-3-flash-preview
```

Put those values in `liwiro/backend/.env.local` for local development. If you use the shared root local env file instead, place them in `liwiro/.env.local`.

6. Start Liwiro and run a Verse Chat provider probe from the same machine as the backend:

```bash
curl -sS "http://127.0.0.1:5000/platform/verse/health?probe=1"
```

Expected behavior:

- `configured: true`
- `probe.ok: true` when the key and model are accepted

Pricing note:

- Gemini Developer API currently has both a free tier for testing and a paid tier with higher limits.

## Anthropic Claude local developer setup

Use Anthropic Claude as a paid API path.

1. Go to the Anthropic Console.
2. Sign in or create an Anthropic account.
3. Open API key management in the Console and create a key.
4. Add billing or prepaid usage credits in the Anthropic Console before expecting live API responses.
5. Store the key in local environment variables only.
6. Configure Liwiro with:

```env
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=change_me_anthropic_api_key
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

Put those values in `liwiro/backend/.env.local` for local development. If you use the shared root local env file instead, place them in `liwiro/.env.local`.

7. Start Liwiro and run the same local Verse Chat probe:

```bash
curl -sS "http://127.0.0.1:5000/platform/verse/health?probe=1"
```

Important note:

- Anthropic API usage should be treated as paid/prepaid usage.
- Do not document or rely on a free Claude API credit path for Liwiro setup.

## OpenAI / ChatGPT API setup

Use OpenAI as a paid API path.

1. Create an OpenAI API key.
2. Store the key in local environment variables only.
3. Configure Liwiro with:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=change_me_openai_api_key
OPENAI_MODEL=gpt-5-mini
```

Put those values in `liwiro/backend/.env.local` for local development. If you use the shared root local env file instead, place them in `liwiro/.env.local`.

4. Start Liwiro and run the same local Verse Chat probe:

```bash
curl -sS "http://127.0.0.1:5000/platform/verse/health?probe=1"
```

## Operational notes

- Keep API keys out of source control and logs.
- Missing keys return a Verse Chat provider configuration error instead of fake behavior.
- Verse Chat can expose multiple configured providers at once, and users can switch between them per thread in the composer.
- Invalid keys return explicit provider authentication errors.
- Quota and rate-limit failures are surfaced as provider errors rather than being hidden.
- To switch models later, change the provider-specific model variable only.
- To add another provider later, extend the Verse provider factory rather than changing the orchestrator.

## Agent rename support

Verse Chat supports global admin-managed agent display-name overrides.

Important behavior:

- persona markdown remains the canonical identity source
- the rename is stored as a display override, not a rewrite of persona files
- routing and explicit mentions recognize renamed display names
- historical thread messages preserve the display name that was active when the message was created

## Developer extension points

To add a new agent:

1. add a new `*.persona.md` file under `liwiro/verse/agents`
2. update routing and handoff rules under `liwiro/verse/router`
3. expose any new display conventions in the UI if needed
4. add tests for routing and handoffs

To add a new skill:

1. add a new `*.skill.md` file under `liwiro/verse/skills`
2. ensure its best-suited agent is named consistently with the relevant persona
3. add loader/retrieval coverage if the format changes

## Current limitations

- Verse Chat currently uses simple lexical retrieval rather than embeddings.
- Verse Chat thread ownership is user-scoped, not multi-user shared collaboration.
- Provider-native JSON schema enforcement is not yet used; Verse Chat currently instructs the provider to return JSON and validates it on the backend.
- Direct page apply and execute support is currently wired for Service Builder, Service Manager, VI Portal, and VDB Portal first.
