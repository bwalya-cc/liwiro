# Liwiro Integration

Last updated: 2026-03-27

This document explains how Liwiro turns the raw Verun runtime pieces into an operator-managed platform.

## 1. What Liwiro adds

Verun already provides:

- a scripting runtime in VI
- a data/control engine in VDB

Liwiro adds the control plane and workspace around those runtime pieces:

- setup and sign-in
- headless CLI management through `./liwiro.sh`
- service authoring
- service generation
- service lifecycle controls
- VDB browser access
- VI browser access
- route testing
- user/settings administration
- public documentation

## 2. Backend integration responsibilities

The backend under `liwiro/backend` is the primary integration layer.

It is responsible for:

- authenticating Liwiro users
- storing and validating platform settings
- resolving VDB transport and credentials
- validating LAPIS
- generating runtime services
- starting, stopping, restarting, and deleting service processes
- proxying VDB portal actions
- proxying VI portal actions
- exposing a shared platform capability and action catalog for Verse and CLI clients

The central file for this is:

- `liwiro/backend/app/main.py`

The headless CLI wrapper is:

- `liwiro/cli/liwiro.py`
- launched through `./liwiro.sh`

## 2.1 Shared capability API

Liwiro now exposes a platform-wide capability registry above the subsystem routes:

- `GET /platform/capabilities`
- `GET /platform/capabilities/<capability_id>`
- `GET /platform/actions/catalog`
- `POST /platform/actions/preview`
- `POST /platform/actions/execute`

This layer gives Verse agents and the CLI one shared contract for:

- capability discovery
- target-surface mapping
- staged `move -> prepare -> execute` support
- permission metadata
- generic server-executable action dispatch where supported

Existing subsystem routes still do the real work. The capability layer sits above them so Verse and CLI can reason about the entire platform using stable capability ids instead of ad hoc per-surface assumptions.

## 3. Frontend integration responsibilities

The frontend under `liwiro/frontend` is the workspace and documentation surface.

It is responsible for:

- collecting user input
- rendering structured and raw editors
- rendering runtime output and route test results
- keeping the VDB and VI portals usable in the browser
- exposing public docs without sign-in for `/wiki`

It is not responsible for:

- holding raw runtime credentials
- owning VDB sessions
- owning generated-service processes
- talking directly to the Java runtimes

## 4. VDB integration

## 4.1 Transport resolution

The transport layer lives in:

- `liwiro/backend/app/vdb_transport.py`

It can build:

- `VDBHttpTransport`
- `VDBUnixSocketTransport`

Transport mode is resolved from config and environment, then normalized into one of the supported modes.

## 4.2 Why Unix socket is preferred

For same-machine deployments, Unix socket mode is better because:

- the control-plane path stays local
- there is no need to expose VDB HTTP externally
- the backend keeps one consistent internal transport boundary

The socket transport uses:

- JSON request envelopes
- 4-byte length-prefixed framing
- JSON response envelopes with status metadata

## 4.3 Backend-facing VDB client

The backend's higher-level VDB client wraps transport details so route handlers can work in terms of:

- document operations
- collection helpers
- VQL execution
- domain/database context

instead of raw socket or HTTP mechanics.

## 5. Service generation integration

## 5.1 The generation path

The end-to-end path is:

1. frontend builds LAPIS
2. frontend submits to `POST /generate`
3. backend validates through `config.py`
4. backend calls `generate_api_service(...)`
5. backend starts the result through `ProcessManager`
6. backend records the service in VDB
7. frontend redirects into service operations

## 5.2 Generated runtime composition

`liwiro/backend/generators/api_generator.py` produces a Flask runtime that wires:

- metadata and docs endpoints
- model/collection preparation
- auth helpers
- CRUD route handlers
- custom VQL route handlers
- Versa route handlers

This makes generated services first-class runtime applications rather than static config documents.

## 5.3 Process management integration

`liwiro/backend/utils/process_manager.py` owns generated-service process lifecycle.

It:

- reserves a port
- injects env vars
- starts a child process
- waits for the port to open
- stores runtime metadata
- updates the `services` collection

When a service is changed in a way that affects runtime behavior, the backend can restart it and update the stored record.

## 6. Frontend route integration

## 6.1 Setup and auth pages

- `/setup`
  - initial bootstrap and runtime connection setup
- `/login`
  - regular operator sign-in

These routes talk only to backend auth/setup routes.

## 6.2 Service pages

- `/service-builder`
  - creates LAPIS and submits generation requests
- `/services`
  - shows the service fleet and basic lifecycle status
- `/services/[id]`
  - edits service config, saves manager state, and runs route tests

These pages all depend on backend service APIs.

## 6.3 Portal pages

- `/vdb-portal`
  - browser VQL entry and output console
- `/vi-portal`
  - source editor, file browser, file runner, and live REPL

These pages look interactive and direct, but they are backend-proxied integration surfaces.

## 6.4 Public docs pages

- `/wiki`
- `/wiki/[slug]`

These are intentionally public so onboarding and setup documentation can be read before sign-in.

## 7. Service Manager integration model

The Service Manager combines several kinds of backend state:

- service metadata
- raw LAPIS
- structured config
- runtime lifecycle state
- saved testing workspace state

That last category is important. The testing workspace is not the same thing as the service contract. Liwiro stores it separately as `manager_state` so operators can keep test drafts without mutating runtime behavior.

## 8. VDB portal integration model

The VDB portal is not a browser-to-database direct client.

Instead:

1. frontend requests connection details from `/platform/vdb/connection`
2. frontend asks backend to create/resume a session with `/platform/vdb/session`
3. backend authenticates to VDB
4. frontend sends raw or structured VQL to `/platform/vdb/query`
5. backend forwards the request over the chosen transport
6. frontend renders the normalized response

This design keeps:

- credentials server-side
- transport switching server-side
- session lifecycle server-side

## 9. VI portal integration model

The VI portal is also backend-owned at the runtime boundary.

The backend provides routes for:

- getting current connection/source-directory info
- changing the source directory
- browsing directories
- listing, reading, writing, renaming, and deleting files
- running source files with the built VI jar
- starting and stopping REPL sessions
- sending input to the live REPL

The REPL is backed by a real persistent process. The browser only renders it.

## 10. Auth integration model

There are multiple auth layers:

- Liwiro platform auth
- backend runtime VDB credentials
- generated-service auth
- VDB/TUMI RBAC

These layers are related but separate.

For example:

- a person may be signed into Liwiro
- the backend may also have its own VDB credentials
- a generated service may enforce its own auth middleware
- VDB may still deny a specific data action based on RBAC

## 11. Startup and operational expectations

The normal local operator sequence is:

1. build Verun
2. start `VDBUnixSocket`
3. start Liwiro backend
4. start Liwiro frontend
5. optionally start VDB HTTP server

The convenience script is:

```bash
./liwiro/scripts/start_all.sh
```

That script should be read as a local orchestration helper, not as a production deployment topology.

## 12. Important code locations

- backend app factory and routes:
  - `liwiro/backend/app/main.py`
- transport layer:
  - `liwiro/backend/app/vdb_transport.py`
- backend VDB abstraction:
  - `liwiro/backend/app/vdb.py`
- validation:
  - `liwiro/backend/config.py`
- service generator:
  - `liwiro/backend/generators/api_generator.py`
- process manager:
  - `liwiro/backend/utils/process_manager.py`
- service builder UI:
  - `liwiro/frontend/app/service-builder/page.jsx`
- service manager UI:
  - `liwiro/frontend/app/services/[id]/page.jsx`
- VDB portal UI:
  - `liwiro/frontend/app/vdb-portal/page.jsx`
- VI portal UI:
  - `liwiro/frontend/app/vi-portal/page.jsx`
- public wiki UI:
  - `liwiro/frontend/app/wiki/page.jsx`
- public wiki content:
  - `liwiro/frontend/lib/wiki-content.ts`

## 13. Read next

- `docs/integration/runtime-flows.md`
- `docs/verun/vdb/README.md`
- `docs/verun/versa/README.md`
