# VDB Guided Path

Learn VDB in a disposable workspace before applying the same commands to service data.

## 1. Start and sign in

Start the local stack with `./liwiro/scripts/start_all.sh`, or use the direct launchers in [setup and operations](../vdb/setup-and-operations.md). Open VDB Portal or the console, authenticate, and inspect `whoami;` and `context;`.

For HTTP access, follow [authentication and authorization](../vdb/auth-and-rbac-notes.md). Use the returned session ID for subsequent requests.

## 2. Create and query data

Follow [the usage guide](../vdb/usage-guide.md) to create a domain, select a database, declare a collection, and insert documents. Practice a filtered read, a projected read, an update with a predicate, and a selected-document delete.

Use [the VQL reference](../vdb/vql-reference.md) for exact syntax. Native commands are text; old JSON action envelopes are rejected. Keep JSON data literals separate from command syntax.

## 3. Add transactions and access control

Group related data changes with `transaction { ... }`. Compare this with a normal multi-command batch: a batch stops at an error without automatically undoing earlier successes.

Create an application account, grant access to the intended database or collection, and verify that account's reads and writes. Follow [TUMI and RBAC](../vdb/tumi-rbac.md) for commands and privilege requirements.

## 4. Connect services and scripts

Use the [Versa VDB bridge](../versa/vdb-module.md) for script access. Generated services use their own runtime credentials and context; Liwiro workspace login and service bearer tokens do not replace VDB authentication.

Review [Liwiro runtime flows](../../integration/runtime-flows.md) when tracing a request through the platform. Inspect service logs and VDB responses to identify which layer rejected an operation.

## 5. Operate the workspace

Export a test domain to a directory writable by the VDB host. Inspect the result and preserve it outside runtime-reset directories. Review the [persistence guidance](../vdb/README.md#persistence) before moving, backing up, or resetting data.

Use [Verun architecture](../architecture.md) to understand the runtime components, and return to the command reference whenever an operation's scope or syntax is unclear.
