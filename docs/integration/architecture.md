# Architecture Overview

Last updated: 2026-03-11

## 1. Architectural shape

The repository is a layered architecture with a generated-service runtime in the middle.

The layers are:

1. **VI**
   - language execution
2. **VDB**
   - persistence, query execution, sessions, and RBAC
3. **Liwiro backend**
   - control plane, generation, orchestration, and portal proxying
4. **Liwiro frontend**
   - operator UI and public documentation

Generated services are created by the backend and then operate as independent child processes between the Liwiro control plane and VDB.

## 2. Runtime topology

## 2.1 Main long-lived processes

In the common local stack there are up to five major process groups:

- `VDBUnixSocket`
  - local IPC interface for VDB
- VDB HTTP server
  - optional direct HTTP interface on `127.0.0.1:1957`
- Liwiro backend
  - Flask platform API on `127.0.0.1:5000`
- Liwiro frontend
  - Next.js app on `127.0.0.1:3000`
- generated service processes
  - child processes started by the backend on ports from the managed range

## 2.2 Control versus runtime planes

There are really two planes in the architecture:

### Control plane

Owned by Liwiro backend and Liwiro frontend.

It handles:

- sign-in and setup
- service design
- service lifecycle
- platform settings and users
- VDB portal proxying
- VI portal proxying

### Runtime plane

Owned by VDB, VI, and the generated services.

It handles:

- document operations
- VQL execution
- Versa execution
- live API requests hitting generated services

That separation is important because the UI does not directly own the runtime. It operates it through the control plane.

## 3. Communication paths

## 3.1 Browser -> backend

This is the only browser-facing privileged path.

The browser never talks directly to:

- `VDBUnixSocket`
- VDB HTTP server
- the Java VI runtime
- generated-service child processes for management purposes

Instead, the browser uses the backend for:

- auth state
- service generation
- service updates
- VDB portal sessions and queries
- VI portal file and REPL operations

## 3.2 Backend -> VDB

This is a transport abstraction boundary.

The backend chooses between:

- `VDBUnixSocketTransport`
- `VDBHttpTransport`

The selection logic is implemented in:

- `liwiro/backend/app/vdb_transport.py`

Normal same-machine mode prefers Unix sockets because:

- it is local-only
- it avoids exposing an HTTP surface when one is not needed
- it gives Liwiro a stable internal control path

## 3.3 Backend -> generated services

The backend is the service runtime owner.

It does not merely store configs; it actively manages processes through:

- `liwiro/backend/utils/process_manager.py`

That code is responsible for:

- allocating ports
- injecting env vars
- starting processes
- verifying successful bind
- tracking PIDs
- stopping and restarting services

## 3.4 Generated services -> VDB

Generated services are separate Flask applications with their own VDB-facing runtime behavior.

They receive injected configuration such as:

- VDB transport settings
- credentials
- Liwiro domain/db defaults
- service env vars
- runtime port

This keeps generated services independent enough to operate as real runtime units instead of in-process blueprints.

## 3.5 VI runtime -> VDB

Versa code can call into VDB through native bridge helpers.

That means the scripting layer is not isolated from the data layer. Instead, it is an extension mechanism that can participate in:

- API endpoint logic
- developer REPL sessions
- operational scripts

## 4. Generated-service architecture

Generated services are the most important runtime artifact in the platform.

## 4.1 Source of truth

Their contract comes from LAPIS, not handwritten Flask route files.

The backend validates LAPIS in:

- `liwiro/backend/config.py`

and generates a service in:

- `liwiro/backend/generators/api_generator.py`

## 4.2 Runtime composition

A generated service typically includes:

- metadata and documentation endpoints
- route definitions for each configured endpoint
- auth helpers when auth is enabled
- model setup and collection initialization
- execution branches for CRUD, custom VQL, and Versa

## 4.3 Why generated services are separate processes

Making them separate processes provides:

- lifecycle independence
- port-addressable services
- restartability without restarting the whole control plane
- clearer failure isolation

It also means service failures can be handled as operational events instead of UI crashes.

## 5. State ownership

## 5.1 VDB-owned state

VDB owns the durable application and platform data model:

- collections and documents
- domains and databases
- scripts
- sessions and RBAC data

## 5.2 Liwiro-owned operational state

Liwiro owns platform orchestration state:

- service registry records
- LAPIS config persistence
- service-manager workspace state
- platform settings

Most of that state is stored in VDB, but ownership of meaning belongs to Liwiro.

## 5.3 Filesystem-owned local source state

The VI portal manages local source files from a configured directory.

That state is not modeled like VDB documents. It is plain filesystem state under the configured source root.

## 6. Security boundaries

## 6.1 UI auth boundary

The frontend relies on backend-issued auth state to protect workspace pages.

Public wiki routes are intentionally exempt.

## 6.2 VDB credential boundary

The backend keeps the authority to connect to VDB.

That prevents raw runtime credentials from being pushed into the browser.

## 6.3 Service auth boundary

Generated services can define their own route protection model through the LAPIS auth configuration.

## 6.4 Data permission boundary

VDB enforces data visibility and mutation rights through sessions and TUMI/RBAC.

That means even if a path reaches VDB, VDB still decides whether the operation is allowed.

## 7. Startup topology

The default stack entrypoint is:

```bash
./liwiro/scripts/start_all.sh
```

That script ensures:

- a VDB Unix socket path exists and is healthy
- backend health at `/auth/status`
- frontend health at `/login`

It is a development/startup orchestration path, not a full production deployment layer.

## 8. Operational failure boundaries

The main failure zones are:

- transport mismatch between backend and VDB
- backend startup before VDB is healthy
- child-service startup failure on selected port
- invalid LAPIS config during generation or update
- invalid source directory or REPL process failure in VI portal
- permission errors returned from VDB for otherwise well-formed requests

These are useful fault lines because they map directly to logs, UI failures, and operational checks.

## 9. Companion docs

- `docs/integration/component-map.md`
- `docs/integration/runtime-flows.md`
- `docs/integration/liwiro-platform.md`
