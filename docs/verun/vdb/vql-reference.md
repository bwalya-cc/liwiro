# VQL Reference

VDB accepts Versa-family command text in the console, VDB Portal, and `POST /vdb`. JSON is used for data and responses, not as a command envelope. The parser rejects legacy `{ "action": ... }` requests and JSON query objects after `where`.

## Syntax and help

End statements with semicolons. Names may be bare identifiers or quoted strings. Object literals contain key/value pairs; lists use square brackets. Commands operate in the authenticated session's selected domain and database.

```text
help;
help documents;
help documents 2;
help all 2;
context;
whoami;
echo "hello";
```

HTTP help supports `GET /help?topic=Documents&page=2&page_size=2` with the session header. Use the runtime help for focused lookups, and the examples below for current command syntax.

## Domains and databases

```text
create domain engineering = {database: "main"};
use domain engineering;
use database main;
context;
create database reporting;
read domains;
read databases;
read domains with owners;
status domain engineering;
```

Select a domain before creating an additional database. `use engineering.main;` selects both. Creating a domain with a `database` definition sets up that database; it does not replace checking your session context.

```text
suspend domain engineering;
resume domain engineering;
drop database reporting;
drop domain engineering;
```

Suspending or dropping a domain affects other users and services. Check ownership and the target before running these commands. Dropping a resource is destructive.

## Collections and schemas

```text
create collection events;
create collection orders = {orderId: string @required @unique, total: number, status: string = "draft"};
read collections;
describe collection orders;
read models;
read model orders;
```

The schema follows `=` and uses typed field declarations. Do not use the old `schema {"field":{"type":...}}` form. A field can include `?` for nullable values, a default literal, and annotations. Validate the types and constraints against your data before importing it.

```text
drop model orders;
drop collection events;
```

Dropping a model removes model metadata; dropping a collection removes the collection. These are distinct operations.

## Create documents

```text
create in orders = {orderId: "o-001", total: 42, status: "draft"};
insert into orders = [{orderId: "o-002", total: 18}, {orderId: "o-003", total: 27}];
```

Create the collection and any schema first. An object inserts one document; a list supplies multiple documents. Inspect the response for validation or uniqueness failures.

## Read and count

```text
read collection orders where total >= 20 && status == "draft" select [orderId, total] order by total desc offset 0 limit 10;
read one from orders where orderId == "o-001";
count collection orders where status == "draft";
```

Read clauses support `where`, `select`, `order by`, `offset`, and `limit`. Ordinary reads default to a limit of 100. Limits must be positive; offsets must be zero or greater. Predicates use expression operators such as `==`, `!=`, `<`, `<=`, `>`, `>=`, `&&`, `||`, `!`, `in`, and `!in`. Use parentheses to make grouping clear. Projection uses a list of field names, not a JSON projection object.

## Update and delete

```text
update collection orders where orderId == "o-001" { total += 5; status = "confirmed"; unset temporaryNote; };
delete from orders where status == "cancelled";
```

Updates use a block containing assignments, increments, decrements, or `unset`. An update without `where` can affect every document in the collection. Document deletion requires either a predicate or the explicit `all` marker:

```text
delete from orders all;
```

## Indexes

```text
create index orders.orderId @unique;
read indexes on orders;
rebuild indexes on orders;
rebuild index orders.orderId;
drop index orders.orderId;
```

Index targets use `collection.field`. Review existing values before adding a unique index.

## Aggregation

Aggregation uses a block of named aggregate expressions, with optional filtering, grouping, ordering, and limiting. It does not accept a MongoDB pipeline as the native command.

```text
aggregate collection orders by status { count: count(); total: sum(total); };
```

See the runtime aggregation help for supported aggregate functions. Check output against a small known dataset before relying on a report.

## Stored scripts

```text
create script greet = { print("hello"); };
read script greet;
read scripts;
run script greet;
run script greet with {username: "alice"};
delete script greet;
```

Script bodies contain Versa code. Import modules before using their namespaces. Script execution permissions and VDB context still apply.

## Batches and transactions

A semicolon-separated batch executes in order and stops at the first failed command. Earlier successful commands are not automatically rolled back. Inspect each result; a batch response can contain a failed item.

Use an explicit transaction when a group of data changes must succeed together:

```text
transaction {
  create in orders = {orderId: "o-004", total: 10};
  update collection orders where orderId == "o-004" { status = "confirmed"; };
};
```

Manual transaction control is also available:

```text
begin transaction;
commit transaction;
rollback transaction;
```

`abort transaction;` is an alias for rollback. Keep manual transaction operations in the same session. A database transaction does not undo external effects such as email or HTTP calls made by scripts.

## Users, roles, and permissions

```text
create user bot = {email: "bot@example.com", password: "<strong-password>", role: "APPLICATION"};
read users;
read roles;
read permissions;
grant ["READ", "WRITE"] on engineering.main.orders to bot;
revoke ["WRITE"] on engineering.main.orders from bot;
```

See [TUMI and RBAC](tumi-rbac.md) for role definitions, ownership, and privilege requirements.

## Export

```text
export domain engineering to "/tmp/vdb-exports" as "engineering-backup";
export domains ["engineering", "analytics"] to "/tmp/vdb-exports";
export all domains to "/tmp/vdb-exports" as "all-domains";
```

Paths refer to the VDB server's filesystem. Ensure the server account can write to the destination and the calling user can access the exported domains.

## Errors and recovery

Responses identify success or failure and include result data or an error. Fix syntax errors before retrying. For access errors, check the authenticated user, selected context, and scope permissions. For data errors, inspect schema and uniqueness constraints. Do not automatically retry writes when you cannot tell whether they already succeeded.

- `VDB_LEGACY_JSON_COMMAND`: replace the JSON command envelope with command text.
- `VDB_LEGACY_JSON_QUERY`: replace a JSON filter with a `where` expression.
- `VDB_LEGACY_UPDATE`: replace `set`/`inc` clauses with an update block.
- `DELETE_REQUIRES_WHERE_OR_ALL`: specify the rows to delete or explicitly use `all`.
