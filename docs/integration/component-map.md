# Component Map

Last updated: 2026-03-11

This page is the repository-wide component index. Use it when you need to answer four questions quickly:

1. what the component is
2. where it lives
3. what it owns
4. what calls it

## 1. Top-level components

| Component | Path | Owns | Called by |
| --- | --- | --- | --- |
| VI runtime | `verun/vi` | Versa parsing, AST evaluation, REPL, native modules | shell scripts, generated services, Liwiro VI portal |
| VDB engine | `verun/vdb` | persistence, VQL, sessions, RBAC/TUMI, export, stored scripts | console, HTTP clients, Liwiro backend, VI `vdb` bridge |
| Liwiro backend | `liwiro/backend` | control plane APIs, generation, process management, VDB/VI portal proxying | Liwiro frontend, operator tooling |
| Liwiro frontend | `liwiro/frontend` | operator UI, route editors, consoles, public docs | browsers |
| generated services | runtime child processes | API routes, runtime docs, auth, VDB-facing business behavior | clients, tests, operators |

## 2. VI component map

## 2.1 Runtime entry and shell wrappers

- `verun/vi/src/main/java/verun/runtime/Main.java`
  - main CLI entry point for file execution and REPL startup
- `verun/vi/scripts/run_file.sh`
  - resolves a file or demo name, ensures the jar exists, injects demo config for selected categories, and executes the runtime
- `verun/vi/scripts/run_repl.sh`
  - ensures the jar exists and starts the Java REPL entrypoint
- `verun/vi/scripts/run_demo_files.sh`
  - convenience wrapper for bundled demos

### Ownership

These files own runtime startup behavior, not language semantics.

### Called by

- developers directly
- Liwiro VI portal backend helpers when executing files or starting REPL sessions

## 2.2 Lexer

- `verun/vi/src/main/java/verun/runtime/lexer`

### Ownership

- token types
- lexical scanning
- turning raw source text into parser input

### Called by

- the parser pipeline from `Main`

## 2.3 Parser

- `verun/vi/src/main/java/verun/runtime/parser`

### Ownership

- grammar parsing
- statement boundaries
- expression structure
- AST construction

### Called by

- file execution and REPL chunk parsing

## 2.4 AST model

- `verun/vi/src/main/java/verun/runtime/ast`

### Ownership

- the node classes the evaluator consumes

### Called by

- parser output
- evaluator input

## 2.5 Evaluator

- `verun/vi/src/main/java/verun/runtime/evaluator/Evaluator.java`
- `verun/vi/src/main/java/verun/runtime/evaluator/BuiltinsEvaluator.java`
- `verun/vi/src/main/java/verun/runtime/evaluator/MemberAccessEvaluator.java`
- `verun/vi/src/main/java/verun/runtime/evaluator/VersaClassValue.java`
- `verun/vi/src/main/java/verun/runtime/evaluator/VersaInstanceValue.java`

### Ownership

- execution semantics
- scope and environment
- built-in functions
- control flow
- classes and instances
- module/member dispatch
- dynamic object behavior

### Called by

- `Main`
- any runtime path that executes parsed Versa code

## 2.6 VDB bridge inside VI

- `verun/vi/src/main/java/verun/runtime/evaluator/VDBNative.java`
- `verun/vi/src/main/java/verun/runtime/evaluator/VDBScriptJobs.java`
- parts of `MemberAccessEvaluator.java`

### Ownership

- script-side VDB auth and context helpers
- collection access wrappers
- script and job operations

### Called by

- Versa code that uses the native `vdb` surface

## 2.7 Native modules

- `verun/vi/src/main/java/verun/runtime/modules/HTTP.java`
- `verun/vi/src/main/java/verun/runtime/modules/JsonXml.java`
- `verun/vi/src/main/java/verun/runtime/modules/Email.java`
- `verun/vi/src/main/java/verun/runtime/modules/Crypto.java`
- `verun/vi/src/main/java/verun/runtime/modules/Jwt.java`
- `verun/vi/src/main/java/verun/runtime/modules/TimeDate.java`
- `verun/vi/src/main/java/verun/runtime/modules/RandomModule.java`
- `verun/vi/src/main/java/verun/runtime/modules/Filer.java`
- `verun/vi/src/main/java/verun/runtime/modules/File.java`

### Ownership

- native capabilities that are awkward to express in pure language syntax

### Called by

- scripts, REPL sessions, and generated service scripts

## 3. VDB component map

## 3.1 Console and servers

- `verun/vdb/src/main/java/verun/vdb/VDBConsole.java`
  - interactive terminal interface
- `verun/vdb/src/main/java/verun/vdb/VDBHttpServer.java`
  - HTTP interface
- `verun/vdb/src/main/java/verun/vdb/VDBUnixSocket.java`
  - Unix socket server

### Ownership

- transport-specific request intake
- transport lifecycle
- connection/session entry behavior

### Called by

- startup scripts under `verun/vdb/scripts`

## 3.2 Dispatch layer

- `verun/vdb/src/main/java/verun/vdb/VDBRequestDispatcher.java`

### Ownership

- transport-neutral request dispatch
- request normalization
- auth endpoint handling and VQL forwarding

### Called by

- HTTP server
- Unix socket server

## 3.3 VQL execution

- `verun/vdb/src/main/java/verun/vdb/VQLProcessor.java`

### Ownership

- interpreting top-level VQL command families
- collection/model operations
- script commands
- transaction commands
- export commands
- help/context/whoami behavior

### Called by

- console mode
- HTTP requests to `/vql`
- Unix socket requests to `/vql`

## 3.4 Sessions and permissions

- `verun/vdb/src/main/java/verun/vdb/SessionManager.java`
- `verun/vdb/src/main/java/verun/vdb/Tumi.java`

### Ownership

- user authentication and session issuance
- role creation and deletion
- grants and revokes
- scoped permission checks

### Called by

- request dispatcher
- VQL processor

## 3.5 Storage support and operational helpers

- `verun/vdb/src/main/java/verun/vdb/DirectoryUtil.java`
- `verun/vdb/src/main/java/verun/vdb/IndexAdvisor.java`
- `verun/vdb/src/main/resources/help.json`

### Ownership

- filesystem layout and data path helpers
- query/index telemetry and recommendations
- built-in operator help content

### Called by

- VDB startup
- VQL help requests
- advisory/reporting paths

## 3.6 Persistent data root

- `verun/vdb/__data__/`

### Ownership

- the on-disk state of VDB itself, recreated as BSON-backed runtime state from an empty repo placeholder

### Called by

- the Java VDB engine

## 4. Liwiro backend component map

## 4.1 App factory and route registry

- `liwiro/backend/app/main.py`

### Ownership

- Flask app creation
- auth routes
- service generation routes
- service management routes
- VDB portal routes
- VI portal routes
- platform settings and user routes
- service cleanup behavior

### Called by

- `flask run`
- backend startup script
- tests

## 4.2 Backend VDB transport layer

- `liwiro/backend/app/vdb_transport.py`

### Ownership

- choosing HTTP or Unix socket mode
- local URL normalization
- socket framing and envelope handling
- transport-specific errors

### Called by

- app startup
- VDB client code
- VDB portal routes

## 4.3 Backend VDB client abstraction

- `liwiro/backend/app/vdb.py`

### Ownership

- convenient document and VQL helpers on top of transport details

### Called by

- route handlers
- process manager
- cleanup code

## 4.4 Config and validation

- `liwiro/backend/config.py`

### Ownership

- environment-backed platform settings
- LAPIS schema validation
- endpoint-specific validation rules

### Called by

- generation routes
- service update routes
- startup config resolution

## 4.5 Service generator

- `liwiro/backend/generators/api_generator.py`

### Ownership

- translating LAPIS into a runnable Flask application
- route registration
- CRUD/custom/script handler creation
- auth route generation
- docs/runtime helper endpoints

### Called by

- process manager child-service startup path

## 4.6 Process manager

- `liwiro/backend/utils/process_manager.py`

### Ownership

- port allocation
- startup env injection
- process start/stop/restart
- child-process health verification
- process metadata tracking

### Called by

- generation and lifecycle routes in `main.py`

## 4.7 Tests

- `liwiro/backend/tests`

### Ownership

- regression coverage for cleanup, config validation, transport behavior, runtime generation, and portal APIs

## 5. Liwiro frontend component map

## 5.1 App shell and auth surfaces

- `liwiro/frontend/components/layout/app-shell.tsx`
  - shared shell, navigation, top bar, route-aware layout
- `liwiro/frontend/components/auth/auth-gate.jsx`
  - route protection and public-route exceptions
- `liwiro/frontend/components/auth/auth-console.jsx`
  - shared sign-in/setup presentation

## 5.2 Shared editor/workspace primitives

- `liwiro/frontend/components/ide/workspace-layout.tsx`
- `liwiro/frontend/components/ide/navigation-config.tsx`
- `liwiro/frontend/components/ide/code-editor.tsx`
- `liwiro/frontend/components/ui/json-textarea.tsx`
- `liwiro/frontend/components/ide/markdown-document.tsx`

### Ownership

- workspace splits
- navigation model
- code and JSON editing
- markdown rendering for public docs

## 5.3 Platform pages

- `liwiro/frontend/app/service-builder/page.jsx`
  - new-service authoring and queue/generation workflow
- `liwiro/frontend/app/services/page.jsx`
  - fleet summary and service list
- `liwiro/frontend/app/services/[id]/page.jsx`
  - deep service manager, config editor, tester, lifecycle actions
- `liwiro/frontend/app/vdb-portal/page.jsx`
  - VDB query builder, raw query entry, session controls, output console
- `liwiro/frontend/app/vi-portal/page.jsx`
  - local source editor, directory picker, console, real REPL session controls
- `liwiro/frontend/app/settings/page.jsx`
  - platform settings, user management, roles
- `liwiro/frontend/app/wiki/page.jsx`
  - documentation catalog
- `liwiro/frontend/app/wiki/[slug]/page.jsx`
  - documentation reader pages

## 5.4 Frontend content models

- `liwiro/frontend/lib/wiki-content.ts`
  - public manual content map
- `liwiro/frontend/lib/json-editor.ts`
  - relaxed-JSON validation and auto-formatting helpers

## 6. Generated service runtime map

Generated services do not live as a static checked-in directory. Their runtime is constructed from:

- `liwiro/backend/generators/api_generator.py`
- validated LAPIS documents
- injected runtime env
- VDB transport and auth configuration

At runtime, each generated service owns:

- its route table
- its auth behavior
- its docs endpoints
- its model and collection prep
- its endpoint dispatch logic

## 7. Persistent state map

| State | Location | Owned by |
| --- | --- | --- |
| VDB data and system metadata | `verun/vdb/__data__/` | VDB |
| service registry | VDB `services` collection | Liwiro backend |
| example LAPIS documents | `liwiro/data/lapis-examples/` | repository |
| VI portal source files | configured `VI_PORTAL_SOURCE_DIR` | filesystem / Liwiro VI portal |
| public manual content | `liwiro/frontend/lib/wiki-content.ts` | Liwiro frontend |

## 8. Companion docs

- `docs/integration/system-description.md`
- `docs/integration/runtime-flows.md`
- `docs/integration/liwiro-platform.md`
