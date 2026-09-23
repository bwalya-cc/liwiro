# VQL Reference

Last updated: 2026-09-09

This document is the narrative companion to the runtime help catalog. The catalog is the exhaustive command list and supplies syntax plus examples for every entry; this page highlights common workflows you can submit via the console, the canonical `/vdb` HTTP endpoint, or automation scripts.

## Navigate runtime help

Console help is intentionally returned in small pieces:

```text
help
help 2
help documents
help documents 2
help find
help Documents.find
help all 2
```

The readable VDB form supports explicit paging:

```text
help topic "Documents" page 2 page_size 2
help topic "Documents.find"
```

HTTP clients can make the equivalent request with `GET /help?topic=Documents&page=2&page_size=2`. Page size is capped at five.

## General commands

Use these when you only need context, identity, or echo behavior before issuing data commands.

### `context`

```text
context
```

### `whoami`

```text
whoami
```

### `echo`

```text
echo value "hello"
```

### Transactional command batch

```text
context;
read collections
```

Separate statements with semicolons or newlines. A failed entry aborts the batch.

## Domain and database operations

### Define a domain

```text
create domain "engineering"
```

### Define a domain+database together

```text
create domain engineering = { database: main };
```

### Use a specific domain or database context

```text
use domain "engineering"
use db "main"
```

### List domains/databases

```text
read domains
read dbs
read domains with owners
```

### Drop domain or database

```text
drop domain "engineering"
drop db "main"
```

### Inspect or change domain lifecycle state

```text
status domain "engineering"
suspend domain "engineering"
resume domain "engineering"
```

Domain lifecycle mutations require domain ownership or super-admin privileges. Suspended domains cannot be selected by ordinary users.

## Collections and models

### List collections or models

```text
read collections
read models
```

### Create a schema-aware collection

```text
create collection "orders" schema {"orderId":{"type":"string","required":true},"total":{"type":"number"},"placedAt":{"type":"date"}}
```

Create the collection first, then seed a document with a separate flat `insert` action. The schema fields use the same type keywords referenced by the Versa `vdb.create` helper, so you can move between console queries and scripted workflows easily.

```text
create collection "reports" schema {"reportId":{"type":"string","required":true},"status":{"type":"string","default":"draft"}}
create in reports = { reportId: "r-001", status: "draft" };
```

See `verun/vi/demo/vdb/vdb_collection_schema_demo.versa` for a Versa script that pairs this command with `vdb.create(...)` and schema-aware collection handling.

### Create a schemaless collection (or seed data)

```text
create in events = { name: "demo", status: "start" };
```

### Inspect or drop models

```text
read model model "orders"
delete model model "orders"
drop collection "events"
```

### Manage indexes

```text
create index collection "orders" field "orderId" unique true
list indexes collection "orders"
rebuild indexes collection "orders"
drop index collection "orders" field "orderId"
```

## Document CRUD commands

### Create documents

```text
create in users = { name: "Alice", role: "admin" };
```

### Read documents

```text
read collection users where role == "admin" select [name, email] limit 10;
```

### Update documents

```text
update collection users where name == "Alice" { active = true; logins += 1; };
```

### Delete documents

```text
delete from users where active == false;
```

### Aggregate documents

```text
aggregate collection "events" pipeline [{"$match":{"kind":"audit"}},{"$sort":{"created_at":-1}},{"$limit":10}]
```

## Scripts

```text
create script name "greet" code "print('hello');"
read script name "greet"
run script name "greet" params {"username":"alice"}
read scripts
delete script name "greet"
```

## Transactions

```text
begin transaction
commit transaction
abort transaction
```

## Export

```text
export domains ["engineering"] out_dir "/tmp/vdb-exports"
export domains "*" package "all" out_dir "/tmp/vdb-exports"
```

## TUMI

```text
create user username "bot" email "bot@example.com" password "<strong-password>" role "APPLICATION"
grant username "alex" role "REPORT_VIEWER"
read roles
read permissions
```

## Security and RBAC

Always pair `tumi` commands with the `RBAC` model referenced in the `help.json` “Security” section so you can see the allowed scopes (domain, db, collection) for each grant before running the command.
