# Verun Architecture

Verun provides the Versa interpreter (VI) and VDB database used by Liwiro. The Maven project in `verun/pom.xml` contains two modules: `vi` and `vdb`.

## VI: run Versa

VI parses and evaluates Versa source, supports file execution and an interactive REPL, and provides native modules for files, HTTP, data conversion, email, cryptography, and VDB access.

- `verun/vi/src/main/java/verun/runtime/Main.java` is the runtime entry point.
- `verun/vi/src/main/java/verun/runtime/parser/` parses source.
- `verun/vi/src/main/java/verun/runtime/evaluator/` evaluates expressions and statements, resolves members, and connects scripts to VDB.
- `verun/vi/src/main/java/verun/runtime/modules/` implements native modules.

Run files with `verun/vi/scripts/run_file.sh` and open the REPL with `verun/vi/scripts/run_repl.sh`. In Liwiro, VI Portal adds a file editor, terminal, source-directory selection, environment settings, and custom module management.

## VDB: store and query data

VDB manages domains, databases, collections, documents, models, users, sessions, scripts, and permissions. Its implementation lives under `verun/vdb/src/main/java/verun/vdb/`.

| Component | Responsibility |
| --- | --- |
| `VDB` and `Collection` | Database and collection operations |
| `BsonStorage` | BSON persistence |
| `VDBCommandLanguage`, `CommandValidator`, `VQLProcessor` | Command parsing, validation, and execution |
| `QueryEvaluator` | Query conditions |
| `Model` and `ModelRegistry` | Data models and validation |
| `UserManager`, `SessionManager`, `Tumi` | Accounts, sessions, and permission checks |
| `VDBRequestDispatcher` | Shared transport request handling |
| `VDBHttpServer`, `VDBUnixSocket`, `VDBNamedPipe` | HTTP and platform IPC interfaces |
| `VDBConsole`, `VDBLineEditor`, `HelpProvider` | Interactive commands, editing, and help |

The console, HTTP server, and IPC interfaces expose the database through different transports. Select the appropriate transport for your host; selecting a transport does not replace authentication or permission checks.

## How Liwiro connects

The Liwiro backend manages VDB connections and generated-service processes. The browser uses the backend for VDB Portal and VI Portal operations. Generated services run as separate processes and use their own runtime configuration to access VDB.

Versa scripts can use the native `vdb` bridge. Authenticate and select the intended domain/database before accessing collections. Service scripts receive additional context such as request parameters and service environment values; standalone files do not automatically receive those inputs.

## Data and operations

VDB stores runtime data under `verun/vdb/__data__/`. Treat it as application data, including users, permissions, collection documents, and stored scripts. Use documented export and operational procedures when moving or resetting data. A runtime reset can delete application data.

See [VDB setup and operations](vdb/setup-and-operations.md), [VQL reference](vdb/vql-reference.md), [Versa runtime usage](versa/runtime-cli-repl.md), and [Liwiro runtime flows](../integration/runtime-flows.md).
