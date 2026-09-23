# Versa `vdb` Bridge Reference

Last updated: 2026-03-28

Use this document when writing Versa that talks to VDB.

## What `vdb` is

`vdb` is a runtime bridge exposed to Versa. It is not just a plain module wrapper. Some behavior is evaluator-driven and depends on runtime authentication and active context.

## Authentication

Authenticate before most operations:

```versa
vdb.auth({user: "username", pass: "password"});
```

Common failure cases:

- not authenticated
- wrong password
- invalid runtime/session context

## Context setters

### `vdb.config(...)`

Use for bridge-level configuration.

Examples:

```versa
vdb.config();
vdb.config({logging: true});
vdb.config({logs: true});
```

### `vdb.set(...)` and `vdb.use(...)`

Use these to choose the active domain and database.

Accepted keys:

- `domain`
- `database`
- `db`

Example:

```versa
vdb.set({domain: "ellafashionhouse", db: "operations"});
```

## Response envelope

Most bridge operations normalize to a structured object with fields like:

- `ok`
- `status`
- `operation`
- `message`
- `data`
- `error`
- `context`

Typical `context` members:

- `domain`
- `database`
- `collection`
- `timestamp`

Not-found style outcomes commonly normalize to:

- `ok: false`
- `status: "not_found"`

## Collection access

Create a collection handle:

```versa
let products = vdb.collection("products");
```

Common collection methods:

- `insert(doc)`
- `find(query, limit?)`
- `update(query, data)`
- `delete(query)`

Example:

```versa
vdb import *;

let products = vdb.collection("products");
let result = products.find({status: {$eq: "active"}}, 10);
let rows = result.data ?? [];
```

## Creating collections from Versa

Use `vdb.create(name)` when you only need a schemaless collection, and pass a class reference when you want Versa to define a schema before documents arrive.

```versa
vdb import *;

vdb.auth({user: DEMO_VDB_USER, pass: DEMO_VDB_PASS});
vdb.set({domain: DEMO_VDB_DOMAIN, database: DEMO_VDB_DB});

// Schemaless collection
vdb.create("events_log");
let events = vdb.collection("events_log");
events.insert({level: "INFO", message: "started"});

// Schema-aware collection via a class definition
class AuditEntry {
    schema() {
        return {
            id: {type: "string", required: true},
            severity: {type: "string", default: "info"},
            details: {type: "object"},
        };
    }
}

vdb.create("audit_entries", AuditEntry);
let audit = vdb.collection("audit_entries");
audit.insert({id: "A-123", details: {source: "demo"}});

// Cleanup
vdb.drop("events_log");
vdb.drop("audit_entries");
```

## Domain and database operations

Common bridge calls:

- `vdb.define({...})`
- `vdb.use({...})`
- `vdb.set({...})`
- `vdb.list_domains()`
- `vdb.list_databases()`
- `vdb.list_collections()`
- `vdb.drop(...)`

## Stored scripts

Common script operations:

- `vdb.save_script(name, service, code)`
- `vdb.load_script(name)`
- `vdb.execute_script(name, params?)`
- `vdb.delete_script(name)`
- `vdb.list_scripts()`

## Transactions

Common functions:

- `vdb.begin_transaction()`
- `vdb.commit_transaction()`
- `vdb.abort_transaction()`

## Aggregation

```versa
let result = vdb.aggregate("orders", pipeline);
```

## TUMI / RBAC

Use:

```versa
vdb.tumi({...});
```

Read `docs/verun/vdb/tumi-rbac.md` for role and permission rules.

## Scheduler utilities

Available helpers:

- `vdb.schedule_job({...})`
- `vdb.list_jobs()`
- `vdb.cancel_job(name)`

Common scheduling keys:

- `name`
- `script`
- `start_at`
- `every_seconds`
- `params`

## Service-script notes

In generated service `versaScript` routes:

- `params` is commonly the request/runtime payload
- `service` may expose service env/config

Those names may be ambient runtime values rather than locally declared variables.

## Common mistakes

- forgetting `vdb.auth(...)`
- using `vdb.collection(...)` without importing `vdb`
- assuming `find(...)` returns rows directly instead of a result object with `data`
- forgetting to select the correct domain/database before CRUD
- treating service runtime values like `params` or `service` as bad syntax during validation
