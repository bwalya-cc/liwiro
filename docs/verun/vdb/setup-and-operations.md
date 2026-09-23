# VDB Setup and Operations

Last updated: 2026-09-09

This page covers how VDB is built, started, authenticated, and operated in this repository.

## 1. Runtime artifacts

- jar:
  - `verun/vdb/target/vdb-1.0.0-jar-with-dependencies.jar`
- persistent data root:
  - `verun/vdb/__data__/` (checked in empty, populated on demand with BSON-backed runtime state)
- help content:
  - `verun/vdb/src/main/resources/help.json`
    - organized into focused General, Console, Server, Domains, Databases, Collections, Indexes, Models, Documents, Scripts, Transactions, Export, TUMI, and Security sections
    - every command entry includes parameters and one or more valid examples
    - topic and catalog responses are paginated so one request never dumps the whole manual
    - console/VQL RBAC visibility lists are capped at five items and include total-count and truncation fields
    - references the same native Versa command families documented in `docs/verun/vdb/vql-reference.md` and `docs/verun/vdb/usage-guide.md`

## 2. Build

Build the Verun jars from the repository root:

```bash
cd verun
./scripts/compile_all.sh
```

The helper scripts under `verun/vdb/scripts` will try to build automatically if the jar is missing.

## 3. First-time bootstrap

On the first usable startup, you need an initial VDB super admin.

The simplest path is the console flow:

```bash
cd verun/vdb
./scripts/convo.sh
```

The interactive bootstrap asks for:

- username
- email
- password
- MIT acceptance via `Accept MIT license? [y/N]:`

That first user becomes the initial `SUPER_ADMIN` and the base BSON-backed system state is initialized under `__data__/`.

## 4. Startup modes

VDB can be run in three main modes in this repository.

## 4.1 Console mode

Command:

```bash
cd verun/vdb
./scripts/convo.sh
```

Use console mode when you want:

- direct local administration
- interactive help lookup
- manual context changes
- low-level troubleshooting

Capabilities include:

- `help`
- `help [page]`
- `help <topic> [page]`
- `help <command>` or `help <topic>.<command>`
- `help all [page]`
- `clear` / `cls` and `Ctrl-L` (clears the viewport and scrollback on terminals that support ANSI erase-saved-lines)
- `license` / `licence`
- authenticated VQL execution in the active context
- `createCollection(name)` and `createCollection(name, schema)` helpers are used by the scripts and runtime to spin up schemaless or schema-aware collections before documents arrive.

## 4.2 HTTP server mode

Command:

```bash
cd verun/vdb
./scripts/serve.sh
```

Default bind behavior:

- host: `127.0.0.1`
- port: `1957`

Use HTTP mode when you want:

- curl-based testing
- non-Liwiro direct clients
- remote or loopback tooling

### Main endpoints

- `POST /auth`
  - accepts Basic auth credentials and returns a `sessionId`
- `POST /vdb` (canonical; `/vql` is a deprecated compatibility alias)
  - requires `X-Session-Id`
  - accepts readable command text such as `read users`, `create user`, or `read collection orders`
  - accepts semicolon- or newline-separated statements as a transactional batch
- `GET|POST /help`
  - requires `X-Session-Id`
  - serves the same bounded help index, topic pages, and command details as the console
  - accepts `topic`, `page`, and `page_size` (`1` through `5`) in the query string
  - POST accepts native Versa help commands; JSON command envelopes are rejected (JSON remains valid only as data literals)
- `GET /`
  - runtime status/usage summary
- `GET /license`
- `GET /health`

## 4.3 Unix socket mode

Command:

```bash
cd verun/vdb
./scripts/socket.sh
```

This mode is the preferred same-host integration path for Liwiro backend.

### Why it exists

It gives the backend:

- a local-only control path
- stable IPC without depending on exposed HTTP
- a simpler runtime trust boundary for same-machine deployments

### Transport behavior

The Unix socket interface uses:

- UTF-8 JSON request envelopes
- 4-byte length-prefixed framing
- JSON response envelopes with status and content type

### Socket path resolution

The startup script and backend transport both recognize:

- `VDB_UNIX_SOCKET_PATH`
- `VDB_INTERFACE_UNIXSOCKET_PATH`

Default path behavior:

- `/run/vdb.sock` if `/run` is writable
- otherwise `/tmp/vdb.sock`

### JVM/system property equivalents

- `vdb.interface.unixsocket.enabled=true`
- `vdb.interface.unixsocket.path=/path/to/socket`

## 5. Liwiro integration expectations

Liwiro backend normally expects:

- `VDB_TRANSPORT=unixsocket`
- a healthy socket path
- valid backend runtime VDB credentials loaded from local env files such as `liwiro/.env.local` or `liwiro/backend/.env.local`

If those are wrong, setup, sign-in, service management, and the VDB portal will fail even if the frontend is otherwise reachable.

## 6. Auth and sessions

## 6.1 HTTP auth flow

Authenticate:

```bash
curl -X POST http://127.0.0.1:1957/auth --user username:password
```

The response includes a `sessionId`.

Use that session ID in later calls:

```bash
curl -X POST http://127.0.0.1:1957/vdb \
  -H 'X-Session-Id: <SESSION_ID>' \
  -H 'Content-Type: text/plain' \
  --data 'context'
```

## 6.2 Session semantics

Sessions carry:

- authenticated identity
- active domain/database context
- permission scope used during VQL execution

That means context and authorization are evaluated together, not as unrelated post-processing.

## 7. Context model

VDB operations are context-sensitive.

The active context includes:

- `domain`
- `database`

Typical workflow:

1. authenticate
2. inspect context with `context`
3. choose a domain and database with `use domain engineering; use db main`
4. run collection or document operations

Without the right context, many otherwise valid commands will fail or behave differently than expected.

## 8. Logging controls

The main environment variables are:

- `VDB_CONSOLE_LOGS`
- `VDB_HTTP_TRAFFIC_LOGS`
- `VDB_FILE_LOGS`

Example:

```bash
VDB_CONSOLE_LOGS=false VDB_HTTP_TRAFFIC_LOGS=false ./scripts/serve.sh
```

These controls affect operator visibility, especially during local debugging and traffic tracing.

## 9. Index advisor

VDB maintains query/index telemetry under:

- `verun/vdb/__data__/sys/index_advisor/`

Depending on advisor policy, startup and runtime paths may surface:

- recommendations
- notifications
- advisory actions

This matters when performance analysis becomes part of operations.

## 10. Common operational tasks

## 10.1 Check identity and scope

```text
whoami
```

## 10.2 Check active context

```text
context
```

## 10.3 List domains or collections

```text
read domains
read collections
```

## 10.4 Export data

```text
export domains ["engineering"] out_dir "/tmp/vdb-exports" package "nightly-backup"
```

## 10.5 Inspect help

```text
help topic "export"
help topic "tumi"
help topic "documents" page 2 page_size 2
help topic "documents.find"
```

The equivalent HTTP request is:

```bash
curl -sS 'http://127.0.0.1:1957/help?topic=Documents&page=2&page_size=2' \
  -H 'X-Session-Id: <SESSION_ID>'
```

## 11. Troubleshooting

## 11.1 Super admin is not configured

Run:

```bash
cd verun/vdb
./scripts/convo.sh
```

and complete the first-user flow.

## 11.2 HTTP auth works but VQL fails with invalid session

Re-authenticate to obtain a fresh `sessionId`, then retry the request with the new `X-Session-Id`.

## 11.3 Liwiro reports Unix socket failure

Check:

- that `./scripts/socket.sh` is actually running
- that the configured path matches `VDB_UNIX_SOCKET_PATH`
- that the socket parent directory is writable
- that stale socket files were not left behind after an unclean shutdown

## 11.4 Permission denied responses

Verify:

- `whoami`
- `context`
- `read permissions`

A well-formed request can still fail if the authenticated session lacks the right scope or permission.

## 12. Related docs

- `docs/verun/vdb/README.md`
- `docs/verun/vdb/vql-reference.md`
- `docs/verun/vdb/tumi-rbac.md`
- `docs/integration/liwiro-platform.md`
