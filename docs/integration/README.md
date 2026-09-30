# Integration Documentation

Last updated: 2026-03-11

Use these guides to connect Liwiro services, VDB data, and Versa scripts, and to understand where each operation runs.

Read this section alongside:

- `docs/liwiro/README.md`
- `docs/verun/README.md`

The important integration boundaries are:

- Liwiro frontend -> Liwiro backend
- Liwiro backend -> VDB
- Liwiro backend -> generated services
- generated services -> VDB
- VI runtime -> VDB

## 1. Frontend to backend

Use the Liwiro workspace to edit services, run commands, and navigate your tools. The Liwiro backend manages:

- VDB credentials
- VDB sessions
- generated-service lifecycle
- local REPL process lifecycle

Keep the backend running while using these tools.

## 2. Backend to VDB

The backend can talk to VDB using:

- `unixsocket`
- `http`

That selection is centralized in:

- `liwiro/backend/app/vdb_transport.py`

Normal local integration prefers the Unix socket path because the backend and VDB are usually on the same machine.

## 3. Backend to generated services

When you create or manage a service in Liwiro, the backend handles its lifecycle.

It:

- validates LAPIS
- creates the service runtime
- starts and stops child processes
- persists service metadata
- handles service cleanup on deletion

## 4. Generated services to VDB

Generated services are separate processes with their own runtime env and VDB-facing behavior.

They do not proxy through the Liwiro backend for each request. Once started, they talk to VDB as runtime applications.

## 5. VI to VDB

Versa has a native `vdb` bridge, which lets scripts and REPL sessions perform VDB operations directly from the interpreter environment.

## 6. Primary document in this section

- `docs/integration/liwiro-platform.md`
  - the detailed platform integration document
- `docs/integration/liwiro-cli.md`
  - the headless CLI management document for `./liwiro.sh`

## 7. Architecture companions

- `docs/integration/system-description.md`
- `docs/integration/architecture.md`
- `docs/integration/component-map.md`
- `docs/integration/runtime-flows.md`
