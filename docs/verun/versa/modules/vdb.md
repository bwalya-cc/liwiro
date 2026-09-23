# vdb Module

## Native Versa commands

VDB commands are Versa-family statements. JSON is data only, never a command envelope:

```versa
read collection repairs where status == "open" limit 5;
create in repairs = { status: "open" };
update collection repairs where id == "r-1" { status = "closed"; };
delete from repairs where id == "r-1";
drop collection repairs;
create index repairs.status;
read indexes on repairs;
rebuild indexes on repairs;
```

Use `transaction { ... }` for an atomic group. Legacy JSON command/query objects are rejected with migration guidance.

`vdb` is the bridge from VI to VersaDB.

## Core
- `vdb.auth({user, pass})`
- `vdb.config()` / `vdb.config({logging: true|false})`
- `vdb.set({domain, db|database})`
- `vdb.use({domain, db|database})`
- `vdb.define({domain?, db|database?})`

## Collection Access
- `vdb.collection(name)`
- `vdb.insert(collection, doc)`
- `vdb.find(collection, query, limit)`
- `vdb.update(collection, query, update)`
- `vdb.delete(collection, query)`
- `vdb.drop(collection)`
- `vdb.list_collections()`
- `vdb.list_databases()`
- `vdb.list_domains()`

## Indexing
- `vdb.create_index(collection, field, unique=false)`
- `vdb.drop_index(collection, field)`
- `vdb.list_indexes(collection)`
- `vdb.rebuild_indexes(collection)`

## Index Advisor (Query-Driven)
- `vdb.index_advisor_status()`
- `vdb.index_advisor_apply(limit?)`
- `vdb.index_advisor_policy(mode?)` where mode is `auto|manual|off`
- `vdb.index_advisor_remove_auto_indexes()`

Advisor telemetry is stored under `verun/vdb/__data__/sys/index_advisor/`:
- `query_log.bsonlog`
- `stats.bson`
- `policy.bson`

Structured state under `verun/vdb/__data__` is now BSON-backed internally. Export output remains JSON content packaged as a zip in the requested `out_dir`.

Authentication failures now surface named Versa exceptions:
- `VDBAuthenticationException` for invalid credentials, including wrong-password failures
- `VDBNotAuthenticatedException` when `vdb.auth(...)` has not been called yet

Returned objects can be accessed consistently with:
- `row.name`
- `row["name"]`
- `row['name']`
- `row[name]`

On `convo` and `serve` startup, the advisor checks recommendations and:
- notifies users of candidates
- optionally auto-creates indexes (policy `auto`)
- allows manual/off modes
- supports removing advisor-created indexes.

Indexes are persisted per collection and are used for exact-match candidate narrowing in `find`.

## Scripts and Jobs
- `vdb.save_script(name, service, code)`
- `vdb.load_script(name)`
- `vdb.execute_script(name, params={})`
- `vdb.delete_script(name)`
- `vdb.list_scripts()`
- `vdb.schedule_job({name, script, start_at?, every_seconds?, params?})`
- `vdb.list_jobs()`
- `vdb.cancel_job(name)`

## Transactions and Aggregation
- `vdb.begin_transaction()`
- `vdb.commit_transaction()`
- `vdb.abort_transaction()`
- `vdb.aggregate(collection, pipeline)`

## Demos
- `verun/vi/demo/vdb/vdb_indexes_and_production_features.versa`
- `verun/vi/demo/vdb/*.versa`
