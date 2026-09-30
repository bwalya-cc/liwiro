# VDB Usage Guide

Use VDB for domains, databases, collections, and documents. Start with a disposable workspace while learning, and check `whoami;` and `context;` before changing data.

## Start and authenticate

```bash
cd verun/vdb
./scripts/convo.sh
```

Complete the console prompts. For HTTP access, start `./scripts/serve.sh`, authenticate at `/auth`, and send command text to `/vdb` with `Content-Type: text/versa` and `X-Session-Id`. The default HTTP address is `127.0.0.1:1957`; managed startup may choose another free port.

For platform IPC use the launcher appropriate to your host. Liwiro prefers Unix sockets on Unix-like systems and named pipes on Windows, with HTTP fallback when managed IPC startup fails.

## Create a workspace

```text
create domain tutorial = {database: "main"};
use tutorial.main;
context;
create collection products = {sku: string @required @unique, name: string, price: number, active: bool = true};
```

Run this as a user permitted to create a domain. Domain/database selection is session state: another session must select its own context.

## Add and query data

```text
create in products = {sku: "P001", name: "Notebook", price: 12.5, active: true};
read collection products where active == true select [sku, name, price] order by price asc limit 20;
count collection products;
```

A read has a default limit of 100. Use explicit pagination for larger collections. Verify field names and types against `describe collection products;` when a query returns unexpected results.

## Change data

```text
update collection products where sku == "P001" { price += 2; };
read one from products where sku == "P001";
```

Use an explicit predicate for routine updates. To remove selected documents:

```text
delete from products where sku == "P001";
```

`delete from products all;` removes all documents. `drop collection products;` removes the collection itself. These operations have different scope.

## Group related writes

```text
transaction {
  create in products = {sku: "P002", name: "Pen", price: 3};
  create in products = {sku: "P003", name: "Pencil", price: 2};
};
```

An ordinary multi-command batch is not an atomic transaction. Inspect results before retrying a failed write.

## Share access

Create application users and grant only the needed scope through [TUMI](tumi-rbac.md). Liwiro login does not substitute for VDB credentials, and changing generated-service bearer authentication does not change VDB ownership.

## Export and operate

```text
export domain tutorial to "/tmp/vdb-exports" as "tutorial-backup";
```

The destination is on the VDB host. Preserve exported packages outside directories scheduled for runtime reset. See [setup and operations](setup-and-operations.md) for storage, transports, and resets, and [VQL reference](vql-reference.md) for scripts, indexes, aggregation, permissions, and command syntax.
