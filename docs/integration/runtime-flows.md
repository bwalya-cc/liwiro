# Runtime Flows

Last updated: 2026-03-11

This page describes the major end-to-end sequences in the platform.

## 1. Stack startup flow

### Goal

Bring up the control plane and the local runtime interfaces in the right order.

### Sequence

1. Build the Verun jars if they are missing.
2. Start `VDBUnixSocket`.
3. Start Liwiro backend.
4. Start Liwiro frontend.
5. Optionally start VDB HTTP server.

### Why the order matters

- the backend expects VDB transport to be available before many platform routes are useful
- the frontend depends on backend auth and runtime status routes
- generated services depend on the backend, not the other way around

### Normal helper

```bash
./liwiro/scripts/start_all.sh
```

That script performs health checks for the socket, backend, and frontend before declaring the stack ready.

## 2. First-time setup flow

### Goal

Create the initial Liwiro operator access and the backend runtime connection settings.

### Sequence

1. Browser opens `/setup`.
2. Frontend calls `/auth/status`.
3. User submits setup data including platform credentials and VDB runtime connection data.
4. Backend persists bootstrap state and validates that VDB can be reached with the configured transport.
5. Backend returns authenticated platform state.
6. Frontend stores auth state and enters the workspace.

### Critical boundary

Setup does not only create UI access. It also establishes whether the backend can actually talk to VDB.

## 3. Sign-in flow

### Goal

Re-enter the platform using existing Liwiro credentials.

### Sequence

1. Browser opens `/login`.
2. User submits credentials to `/auth/signin`.
3. Backend validates platform credentials.
4. Backend confirms runtime VDB initialization is still healthy.
5. Backend issues frontend auth state.
6. Frontend loads the authenticated workspace shell.

### Failure modes

- valid Liwiro credentials but broken runtime VDB config
- valid UI sign-in but expired or changed VDB credentials

## 4. Service generation flow

### Goal

Turn a LAPIS contract into a running service.

### Sequence

1. User builds a service in `/service-builder`.
2. Frontend submits LAPIS to `POST /generate`.
3. Backend validates the config through `config.py`.
4. Backend calls `generate_api_service(lapis_config)`.
5. `ProcessManager` chooses a free port.
6. Backend injects runtime env into the child process.
7. Child process starts the generated Flask app through Uvicorn's WSGI interface.
8. `ProcessManager` waits for the chosen port to accept connections.
9. Backend writes the service record into the `services` collection.
10. Frontend clears the generation queue and redirects to the service or service list.

### Important runtime env pieces

- `VDB_SERVER_URL`
- `VDB_UNIX_SOCKET_PATH`
- `VDB_USERNAME`
- `VDB_PASSWORD`
- `LIWIRO_DOMAIN`
- `LIWIRO_DB`
- `PORT`

## 5. Generated request flow

### Goal

Serve an actual API request using a generated service.

### Sequence

1. A client calls the generated service on its assigned port.
2. The generated Flask app matches the route configured in LAPIS.
3. The route resolves `operationType`.
4. One of three handlers executes:
   - CRUD
   - custom VQL
   - Versa
5. The handler performs VDB operations or script evaluation as needed.
6. The service returns a normalized HTTP response.

### Handler differences

#### CRUD

- operates against a linked model
- translates request data into collection operations

#### Custom VQL

- uses a configured strict flat-action JSON `vqlQuery`
- can merge request `query`, `args`, or `data`

#### Versa

- evaluates procedural logic in VI
- has access to request context and native modules

## 6. Service update flow

### Goal

Change a running service without regenerating the entire platform.

### Sequence

1. User opens `/services/[id]`.
2. Frontend fetches current service detail from `GET /services/<process_id>`.
3. User edits structured config, raw LAPIS, manager state, or route-testing state.
4. Frontend submits `PUT /services/<process_id>`.
5. Backend validates LAPIS if the contract changed.
6. Backend persists changes.
7. If runtime-affecting config changed, backend restarts the service process.
8. Updated runtime metadata is written back to the registry record.

### Split state model

Two important kinds of state are persisted:

- `lapis_config`
  - the service contract and runtime behavior
- `manager_state`
  - operator workspace drafts such as testing state

Manager-only saves do not require a service restart.

## 7. Service stop/start/restart flow

### Stop

1. Frontend calls `POST /services/<process_id>/stop`.
2. Backend resolves the child PID.
3. `ProcessManager` terminates the process tree.
4. Runtime status is updated in the registry.

### Start

1. Frontend calls `POST /services/<process_id>/start`.
2. Backend reloads the stored LAPIS config.
3. `ProcessManager` launches a new child process.
4. New PID and port metadata replace the old runtime record.

### Restart via update

This is logically a stop plus start triggered by a config update.

## 8. Service deletion and cleanup flow

### Goal

Remove the runtime, registry record, and backing service domain without leaving stale ownership/domain state behind.

### Sequence

1. Frontend calls `DELETE /services/<process_id>/delete`.
2. Backend stops the process if it is running.
3. Backend performs service cleanup and drops the service domain.
4. Backend verifies that the domain is actually gone.
5. Backend deletes the registry record.

### Important rule

Deletion is not considered successful if the service domain still exists afterward.

## 9. VDB portal flow

### Goal

Expose VDB safely in the browser without handing transport ownership to the browser.

### Sequence

1. Frontend loads `/platform/vdb/connection`.
2. Frontend asks backend to create or resume a portal session with `POST /platform/vdb/session`.
3. Backend authenticates to VDB using the configured transport.
4. Frontend submits structured or raw VQL to `POST /platform/vdb/query`.
5. Backend forwards the request to VDB over Unix socket or HTTP.
6. Backend normalizes the result and returns it to the browser.
7. Frontend renders query history, context, and output.

### Why it is proxied

- browser code never receives raw VDB transport control
- transport switching stays backend-owned
- credentials remain server-side

## 10. VI portal file flow

### Goal

Allow browser-based editing and execution of local Versa source files.

### Sequence

1. Frontend loads `/platform/vi/connection`.
2. Frontend requests available directories from `GET /platform/vi/directories`.
3. User selects or edits the active source directory.
4. Frontend lists files via `GET /platform/vi/files`.
5. User opens, creates, saves, renames, deletes, or runs files through backend routes.
6. Backend performs the filesystem work and invokes the built VI runtime for file execution.

### Important boundary

This flow operates on local filesystem state, not VDB document state.

## 11. VI REPL flow

### Goal

Expose a real persistent REPL session through the browser.

### Sequence

1. Frontend enters REPL mode in `/vi-portal`.
2. Frontend calls `POST /platform/vi/repl/session`.
3. Backend creates or resumes a persistent Java REPL process for the current authenticated user.
4. Frontend sends input to `POST /platform/vi/repl/input`.
5. Backend writes input to the REPL process stdin and drains stdout/stderr.
6. Frontend renders prompt, echoed source, multiline continuation, and output in a terminal-style console.
7. User exits REPL mode and backend tears down the session.

### Important behavior

- REPL evaluator state persists between submissions
- `Enter` submits
- `Ctrl+Enter` supports multiline authoring from the portal UI
- VDB access inside REPL still requires explicit `vdb.auth(...)`

## 12. Public wiki/manual flow

### Goal

Expose documentation without requiring platform sign-in.

### Sequence

1. User opens `/wiki` or `/wiki/[slug]`.
2. Frontend route protection recognizes the wiki as public.
3. The public page loads the manual content from `wiki-content.ts`.
4. Markdown is rendered through the workspace documentation components.

### Why this matters

Documentation remains accessible during setup, evaluation, and onboarding before a user signs in.

## 13. Companion docs

- `docs/integration/component-map.md`
- `docs/integration/liwiro-platform.md`
- `docs/verun/vdb/setup-and-operations.md`
- `docs/verun/versa/runtime-cli-repl.md`
