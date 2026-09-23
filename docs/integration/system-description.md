# Verun + Liwiro System Description

Last updated: 2026-03-11

## 1. What this repository is

This repository is a complete platform stack for designing, generating, running, and operating data-backed services.

It is made of four major runtime layers:

1. `verun/vi`
   - the Versa Interpreter (VI), which executes `.versa` source code
2. `verun/vdb`
   - the VersaDB (VDB) engine, which stores data, executes VQL, manages sessions, and enforces TUMI/RBAC
3. `liwiro/backend`
   - the Liwiro control plane, which validates LAPIS, generates services, manages processes, and exposes platform APIs
4. `liwiro/frontend`
   - the Liwiro operator UI, which provides setup, sign-in, service design, service management, VDB access, VI access, settings, and public documentation

The repository is not just a language runtime, not just a database, and not just a dashboard. The point of the stack is the combination:

- design a service contract in LAPIS
- validate it centrally
- generate a runnable API from it
- persist data in VDB
- optionally execute custom VQL or Versa for non-trivial route behavior
- operate the whole runtime through Liwiro

## 2. Repository layout

The important top-level directories are:

- `verun/vi`
  - Versa runtime, parser, evaluator, shell scripts, demo programs, and native modules
- `verun/vdb`
  - VDB engine, VQL processor, transports, session manager, TUMI, help resources, and startup scripts
- `liwiro/backend`
  - Flask control plane, LAPIS validation, VDB client layer, API generator, process manager, and tests
- `liwiro/frontend`
  - Next.js application, workspace shell, service builder, service manager, VDB portal, VI portal, settings, and public wiki
- `liwiro/data/lapis-examples`
  - example service definitions used as demonstrations and regression fixtures
- `docs`
  - the technical documentation set for the full stack

## 3. Runtime goals of each layer

## 3.1 VI

VI exists to execute Versa in consistent ways across:

- standalone script files
- interactive REPL sessions
- generated API endpoints that use `versaScript`
- VDB stored-script or job-style execution paths

Its internal runtime pipeline is:

1. read source text
2. tokenize source with the lexer
3. parse tokens into AST nodes
4. evaluate AST nodes in an interpreter environment
5. expose native modules and VDB bridge helpers to the running program

Key implementation areas:

- `verun/vi/src/main/java/verun/runtime/Main.java`
- `verun/vi/src/main/java/verun/runtime/lexer`
- `verun/vi/src/main/java/verun/runtime/parser`
- `verun/vi/src/main/java/verun/runtime/ast`
- `verun/vi/src/main/java/verun/runtime/evaluator`
- `verun/vi/src/main/java/verun/runtime/modules`

## 3.2 VDB

VDB is the repository's persistent data and command engine.

It owns:

- domains
- databases
- collections and document storage
- collection models/schema metadata
- VQL execution
- session management
- user and role management through TUMI
- export tooling
- stored script lifecycle

VDB is surfaced through three interfaces:

- `VDBConsole`
  - interactive terminal interface
- `VDBHttpServer`
  - HTTP interface on port `1957`
- `VDBUnixSocket`
  - same-host local IPC interface preferred by Liwiro backend

Key implementation areas:

- `verun/vdb/src/main/java/verun/vdb/VDBConsole.java`
- `verun/vdb/src/main/java/verun/vdb/VDBHttpServer.java`
- `verun/vdb/src/main/java/verun/vdb/VDBUnixSocket.java`
- `verun/vdb/src/main/java/verun/vdb/VDBRequestDispatcher.java`
- `verun/vdb/src/main/java/verun/vdb/VQLProcessor.java`
- `verun/vdb/src/main/java/verun/vdb/SessionManager.java`
- `verun/vdb/src/main/java/verun/vdb/Tumi.java`

Persistent VDB state lives under:

- `verun/vdb/__data__/`

The repository ships that directory as a clean placeholder. VDB recreates BSON-backed runtime state there when the engine is bootstrapped and used.

## 3.3 Liwiro backend

The backend is the control plane that turns Verun into an operator-managed platform.

It owns:

- platform bootstrap and sign-in
- runtime connection settings for VDB
- LAPIS validation
- service generation
- generated-service lifecycle
- service metadata persistence
- VDB portal proxy routes
- VI portal file and REPL proxy routes

Its most important files are:

- `liwiro/backend/app/main.py`
  - Flask application factory and the majority of platform routes
- `liwiro/backend/app/vdb_transport.py`
  - HTTP versus Unix socket transport selection and implementation
- `liwiro/backend/app/vdb.py`
  - higher-level backend client for VDB operations
- `liwiro/backend/config.py`
  - environment config resolution and LAPIS validation
- `liwiro/backend/generators/api_generator.py`
  - generated API factory
- `liwiro/backend/utils/process_manager.py`
  - child-process orchestration for generated services

## 3.4 Liwiro frontend

The frontend is the operator interface and public documentation surface.

It is responsible for:

- setup and sign-in screens
- authenticated workspace shell
- service builder
- service fleet view
- service manager and route tester
- VDB portal
- VI portal
- user and settings administration
- public wiki/manual pages

Important route groups live under `liwiro/frontend/app`:

- `/login`
- `/setup`
- `/service-builder`
- `/services`
- `/services/[id]`
- `/vdb-portal`
- `/vi-portal`
- `/settings`
- `/wiki`
- `/wiki/[slug]`

The frontend does not talk directly to VDB or the Java runtime. It talks to the Liwiro backend over HTTP and renders backend-owned state.

## 3.5 Generated services

Generated services are runtime-created Flask applications produced from LAPIS definitions.

They are not manually authored source trees in normal operation. Instead, the backend:

1. receives LAPIS from the Service Builder or Service Manager
2. validates the config
3. calls `generate_api_service(lapis_config)`
4. starts the generated app in a child process
5. records service metadata in the `services` collection

Generated services can expose:

- CRUD endpoints
- custom VQL endpoints
- Versa endpoints
- auth routes
- runtime docs and example endpoints
- service-specific setup/bootstrap behavior

## 4. The service model

## 4.1 LAPIS as the contract

LAPIS is the declarative service definition format used by Liwiro.

Its important sections are:

- `metadata`
- `auth`
- `models`
- `endpoints`

That design has a few consequences:

- service structure is data-driven
- the same contract can be edited in structured mode or raw JSON mode
- route docs and example payloads can live alongside the contract
- backend generation logic can stay consistent across services

## 4.2 Three endpoint execution modes

Every generated route falls into one of three patterns:

### CRUD

Best when the route is a direct data operation on a linked model.

Typical behavior:

- request params/body are normalized
- the linked collection is selected
- create/read/update/delete behavior is mapped into VDB operations

### Custom VQL

Best when the route still fits a query shape but needs more control than generic CRUD.

Typical behavior:

- a configured strict flat-action JSON `vqlQuery` is parsed
- request `query`, `args`, or `data` can be merged in where supported
- the combined flat-action JSON command is executed against VDB

### Versa

Best when the route needs procedural logic, orchestration, or multi-step workflows.

Typical behavior:

- the request is mapped into script-visible context
- the script executes in VI
- native modules and `vdb` bridge helpers are available
- the script result becomes the route result

## 5. Communication boundaries

## 5.1 Browser to backend

The browser interacts only with Liwiro backend APIs.

That includes:

- setup and sign-in
- service generation and service updates
- service list and lifecycle actions
- VDB portal session and query operations
- VI portal file operations and REPL operations
- platform settings and users

This boundary is important because the browser never gets raw VDB transport ownership.

## 5.2 Backend to VDB

The backend can talk to VDB using:

- HTTP transport
- Unix domain socket transport

The transport decision is made in:

- `liwiro/backend/app/vdb_transport.py`

Same-host mode prefers Unix socket because it keeps the backend-to-VDB path local and avoids depending on public HTTP exposure.

## 5.3 Backend to generated services

The backend owns generated-service lifecycle entirely.

Through `ProcessManager`, it:

- chooses ports
- injects runtime env
- launches child processes
- waits for ports to bind
- records PIDs and ports
- restarts or stops services later

## 5.4 Generated services to VDB

Generated services resolve their own runtime configuration and connect to VDB using the credentials and workspace information injected at startup.

This matters because a generated service is a separate process, not an in-process backend plugin.

## 5.5 VI to VDB

Versa can access VDB through native runtime helpers.

That makes it possible to write:

- standalone scripts
- REPL-driven data exploration
- script-backed endpoint logic

with the same VDB-facing programming model.

## 6. Platform state and persistence

The stack has several distinct state domains.

## 6.1 VDB persistent state

Owned by VDB and stored under:

- `verun/vdb/__data__/`

In the repository, that tree starts empty. At runtime it becomes the BSON-backed state root for domains, metadata, users, scripts, and collection data.

This includes:

- domains
- databases
- collections
- documents
- stored scripts
- user/role metadata
- system metadata and index-advisor artifacts

## 6.2 Liwiro control state

Owned logically by the Liwiro backend but generally persisted in VDB.

This includes:

- service registry documents
- LAPIS configs for generated services
- saved manager workspace state
- platform user records and settings

## 6.3 Local source state

Owned by the VI portal file surface.

This includes:

- the configured VI source directory
- editable `.versa` files
- local script artifacts used in the portal

## 7. Auth layers

There is more than one auth system in this repository.

## 7.1 Liwiro platform auth

Controls who can access the Liwiro operator UI and backend platform routes.

This is what powers:

- setup
- sign-in
- `/auth/status`
- `/auth/signin`
- `/auth/me`
- `/auth/logout`

## 7.2 Backend runtime VDB credentials

These are the credentials the backend uses to authenticate to VDB for control-plane tasks.

They are not the same thing as frontend sign-in credentials.

## 7.3 Generated-service auth

If a service is configured as an auth-capable service, the generated runtime exposes auth-specific routes and route guards based on the service's LAPIS config.

## 7.4 VDB/TUMI RBAC

This is the VDB-side permission system governing:

- users
- roles
- grants and revokes
- scope-specific data permissions

These layers cooperate, but they serve different boundaries.

## 8. Normal startup model

The normal local stack is:

1. build the Verun artifacts
2. start `VDBUnixSocket`
3. start Liwiro backend
4. start Liwiro frontend
5. optionally start VDB HTTP server for direct access

The convenience script for this path is:

```bash
./liwiro/scripts/start_all.sh
```

That script:

- resolves a socket path
- starts `VDBUnixSocket` if needed
- starts the backend on `127.0.0.1:5000`
- starts the frontend on `127.0.0.1:3000`
- waits for health checks before declaring success

## 9. Operational fault boundaries

The main failure boundaries in the platform are:

- backend cannot authenticate to VDB
- backend is pointed at the wrong Unix socket path
- generated service fails to boot or bind a port
- generated service runtime config is inconsistent with the control plane
- VI portal source directory is invalid or not writable
- VDB portal session creation succeeds but the chosen context or permissions do not

These are the boundaries that show up most often in setup, sign-in, service generation, service management, and portal troubleshooting.

## 10. How to use this document

Use this page as the top-level mental model, then move into the implementation views:

1. `docs/integration/architecture.md`
2. `docs/integration/component-map.md`
3. `docs/integration/runtime-flows.md`
4. `docs/integration/liwiro-platform.md`
5. subsystem docs under `docs/vdb` and `docs/vi`
