# VI + VDB Scripts Demo

Last updated: 2026-03-01

This guide shows how to store, execute, and manage Versa (`.versa`) code in VDB from:

- VDB console
- VDB HTTP server (`/vdb`; `/vql` is a deprecated alias)
- VI runtime (`vdb.*` API inside scripts)

## Important runtime rules

- Module imports should be at the top of the script file/source.
- Example:

```vi
vdb import *;
json_xml import *;
time import *;
```

- Supported import forms in VI:
  - `module import *;`
  - `module import { resource_a, resource_b };`
  - `import module;`

- `json()` and `xml()` builtins can cast JSON/XML strings without importing `json_xml`.
- Domain names are normalized to lowercase with underscores, so `My Domain`, `my-domain`, and `MY_domain` map consistently.

## 1. Start VDB server / console

Server:

```bash
./verun/vdb/scripts/serve.sh
```

Console:

```bash
./verun/vdb/scripts/convo.sh
```

## 2. Manage scripts from VDB console / Versa (HTTP server)

Create (store) a script:

```versa
create script hello_script for demo = {
  vdb import *;
  let who = params.name ?? "world";
  { message: "Hello " + who };
};
```

Read script metadata/source:

```versa
read script hello_script;
```

Execute script:

```versa
run script hello_script with { name: "Cameron" };
```

Delete script:

```versa
delete script hello_script;
```

HTTP example:

```bash
curl -s http://127.0.0.1:1957/vdb \
  -H 'Content-Type: text/versa' \
  --data 'run script hello_script with { name: "Cameron" };'
```

## 3. Manage scripts from VI (`vdb.*`)

Example script (`vdb import *;` required):

```vi
vdb import *;

let authRes = vdb.auth({user: DEMO_VDB_USER, pass: DEMO_VDB_PASS});
let ctxRes = vdb.set({domain: "My Domain", database: "main"}); # normalized -> my_domain

let code = "vdb import *;\\njson_xml import *;\\nlet p = params.name ?? \\\"world\\\";\\n{hello: p};";

print(vdb.save_script("hello_from_vi", "demo", code));
print(vdb.load_script("hello_from_vi"));
print(vdb.execute_script("hello_from_vi", {name: "Ava"}));
print(vdb.list_scripts());
print(vdb.delete_script("hello_from_vi"));
```

When you run the bundled VI demos through the helper scripts, `DEMO_VDB_*` comes from `verun/vi/demo/.env`.

## 4. Stored scripts using modules (full language features)

Stored scripts can use normal Versa features (functions, try/catch, collections, VDB API, module calls), but modules must be imported at the top of the stored source:

```vi
vdb import *;
time import *;
json_xml import *;

try {
    let now = time.ctime(null, "iso");
    let logs = vdb.collection("script_logs");
    logs.insert({ran_at: now});
    {ok: true, ran_at: now}
} catch (e) {
    {ok: false, errorType: e.type, error: e.message, line: e.line, column: e.column}
}
```

## 5. Exception handling in scripts

`catch (e)` now exposes:

- `e.type`
- `e.message`
- `e.line`
- `e.column`
- `e.source_line`

This makes VDB-managed scripts easier to debug when executed from console/server.

## 6. Demos added/updated

- `verun/vi/demo/core/exceptions.versa`
- `verun/vi/play_scripts/except.versa`
- `verun/vi/demo/json_xml/json_xml_module_demo.versa` (full JSON/XML conversion coverage)
- `verun/vi/demo/core/module_imports_demo.versa`
- `verun/vi/demo/core/module_imports_missing_demo.versa`
- `verun/vi/demo/vdb/vdb_class_oop_core_demo.versa`
- `verun/vi/demo/vdb/vdb_class_schema_validation_demo.versa`
- `verun/vi/demo/vdb/vdb_class_vdb_crud_demo.versa`
- `verun/vi/demo/vdb/vdb_class_vdb_advanced_ops_demo.versa`
- `verun/vi/demo/vdb/vdb_script_jobs_http_and_crud.versa` (embedded stored-script imports added)
- `verun/vi/demo/vdb/vdb_collection_schema_demo.versa` (shows `vdb.create(...)` for schemaless and schema-aware collections plus CRUD operations)
