# VersaDB (VDB) Usage Guide

Use this guide to recall the most common command shapes, command sequence, and runtime methods that are referenced in both the interactive help and the public docs.

## Setup & entry points

1. **Console mode**

```bash
cd verun/vdb
./scripts/convo.sh
```

   - paginated interactive help (`help`, `help <topic> [page]`, `help <command>`)
   - direct context switching via `use` and `define`

2. **HTTP mode**

```bash
cd verun/vdb
./scripts/serve.sh
```

   - bind: `127.0.0.1:1957`
   - endpoints: `/auth`, `/vdb` (with `/vql` as a temporary deprecated alias), `/help`, `/health`, `/license`
   - call `/vdb` with a Versa command body, `Content-Type: text/versa`, and `X-Session-Id`

3. **Unix socket mode**

```bash
cd verun/vdb
./scripts/socket.sh
```

   - preferred for Liwiro backend (Unix socket or named pipe on Windows)
   - uses length-prefixed JSON frames over the socket

## General helpers

| Command | Purpose |
| --- | --- |
| `help [page]` | Lists a bounded page of available sections |
| `help <section> [page]` | Shows up to three command entries from that section |
| `help <command>` | Shows one focused command entry with parameters and examples |
| `help <section>.<command>` | Selects an exact command when a name has multiple matches |
| `help all [page]` | Walks the complete command catalog a page at a time |
| `clear` / `cls` | Clears the console viewport and supported terminal scrollback |
| `context` | Shows the current domain and database |
| `whoami` | Returns the authenticated user and roles |
| `echo` | Returns the supplied string |

HTTP clients use the same model with `/help?topic=Documents&page=2&page_size=2`. Page size is capped at five so clients cannot accidentally request an endless help payload. Console/VQL help also caps each RBAC visibility preview at five names and reports its full count plus whether the preview was truncated.

## Domain and database commands

### Create or switch scope

```text
create domain "analytics"
create database sales;
use domain "analytics"
use db "sales"
```

### Inspect or remove

```text
read domains
read dbs
drop domain "analytics"
drop db "sales"
status domain "analytics"
suspend domain "analytics"
resume domain "analytics"
```

`domain_status` is read-only; suspend and resume require domain ownership or super-admin privileges.

## Collection management

Two main flows:

- **Schema-aware creation** (use the `schema` block to enumerate typed fields)
- **Schemaless creation** (pass `data` to establish an empty collection without a schema)

### Schema-aware collection

```text
create collection "orders" schema {"orderId":{"type":"string","required":true},"total":{"type":"number"},"status":{"type":"string","default":"draft"}}
```

The same schema definitions can be expressed from Versa via `vdb.create("collection", ClassRef)`—see `verun/vi/demo/vdb/vdb_collection_schema_demo.versa` for a full script that creates both schema-aware and schemaless collections before running CRUD commands.

### Schemaless collection

```text
create in events = { name: "deploy", level: "info" };
```

### Inspect and drop

```text
read collections
drop collection "events"
read model model "orders"
delete model model "orders"
```

## Document CRUD commands

```text
create in users = { name: "Alice", role: "admin" };
```

```text
read collection users where role == "admin" select [name, email] limit 5;
```

```text
update collection users where email == "alice@example.com" { active = true; logins += 1; };
```

```text
delete from users where active == false;
```

### Notes

- Use normal Versa expressions in `where`, `select`, `order by`, `offset`, and `limit` clauses.
- Updates are assignment blocks; JSON query/update envelopes are rejected.
- Document commands respect the authenticated user’s RBAC scope.

## Scripts, export, and TUMI

### Stored scripts

```text
create script name "greet" code "print('hello');"
run script name "greet" params {"username":"alice"}
delete script name "greet"
```

### Export

```text
export domains ["engineering"] out_dir "/tmp/vdb-exports"
export domains "*" package "all" out_dir "/tmp/vdb-exports"
```

### TUMI

```text
create user username "bot" role "APPLICATION" email "bot@example.com" password "BotPass0!"
grant username "alex" role "report_viewer" domain "engineering"
read permissions
```

## Response shape

```
{
  "status":"success",
  "result":{...},
  "metadata":{"durationMs":45}
}
```

When an error occurs, `status` flips to `error` and `result` contains the failure details along with `code` and optional `validation` data.
