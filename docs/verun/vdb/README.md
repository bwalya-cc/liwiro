# VDB Reference

Last updated: 2026-03-29

Use this folder as the practical reference for VDB setup, transport, commands, auth, and query work.

## Guided path

- `docs/verun/guide/vdb-guide.md`
  - beginner → intermediate → pro checkpoints focused on starting VDB, managing domains/collections, and mastering VQL/TUMI auth plus service integration, with links into the deeper reference docs.

The canonical combined bundle now lives in `verun/vi/verse-verun-reference/reference.json`. Use that when you need the implementation-backed VDB reference that is structured at the same level as the Versa half, then use this folder for longer operational companion material.

## Fast path

1. `docs/verun/vdb/setup-and-operations.md`
   Use this for startup, runtime location, transport mode, and operational checks. It also explains the shared paginated console/server help catalog and its focused command lookups.
2. `verun/vi/verse-verun-reference/reference.json`
   Use this for the canonical machine-readable VDB and shared-runtime reference that Verse agents can also retrieve from directly.
3. `docs/verun/vdb/vql-reference.md`
   Use this for command families, inputs, output shapes, and valid JSON examples that match the help section payloads.
4. `docs/verun/vdb/usage-guide.md`
   Use this for day-to-day operator flows, including schemaless/schema-aware collection creation plus CRUD updates and exports.
5. `docs/verun/vdb/auth-and-rbac-notes.md`
   Use this for super-admin, app credentials, and permission behavior.
6. `docs/verun/vdb/tumi-rbac.md`
   Use this for TUMI permission rules and role management.

## What VDB is

VDB is the platform data layer. It owns:

- domains and databases
- collection models and documents
- VQL execution
- sessions and authentication
- TUMI/RBAC permission checks
- stored scripts
- export/import and operational metadata

## Core command families

Read `vql-reference.md` for full syntax. High-value families are:

- `define`
- `use`
- `list`
- `create`
- `read`
- `update`
- `delete`
- `drop`
- `model`
- `script`
- `transaction`
- `export`
- `context`
- `whoami`
- `help`
- `tumi`

## Runtime surfaces

- Console
  `cd verun/vdb && ./scripts/convo.sh`
- HTTP server
  `cd verun/vdb && ./scripts/serve.sh`
- Unix socket server
  `cd verun/vdb && ./scripts/socket.sh`

## Persistence

Runtime state lives under `verun/vdb/__data__/`. That tree becomes the durable source of truth for:

- domains and databases
- collection data and models
- users and permission metadata
- stored scripts
- operational artifacts

The interactive console command history is stored separately at
`verun/vdb/__data__/sys/command_history.txt` and is loaded again on the next
console session. The runtime reset script erases runtime and application data
by default while preserving only this file. Use
`liwiro/scripts/reset_runtime_data.sh --full-reset --yes --clear-command-history`
only when a complete destructive reset is intended. While typing in the
console, Up/Down (and Ctrl-P/Ctrl-N) search persisted history using the text
already entered as a prefix; Down returns to the draft when matches are
exhausted.

Managed startup prefers the platform's IPC interface (Unix socket on Unix-like
systems and named pipe on Windows). If IPC cannot become healthy, `start_all.sh`
reports the failure, cleans up the failed IPC process, and falls back to the
local HTTP server. Selecting IPC in the frontend uses the same platform-aware
mapping; a failed switch reports an error and restores HTTP when available.

## Where VDB is used

- Liwiro backend
  Service registry, platform metadata, cleanup, and portal queries.
- Generated services
  CRUD, custom VQL, and auth-backed workflows.
- Versa
  Through the native `vdb` bridge in scripts, REPL sessions, and script endpoints.
