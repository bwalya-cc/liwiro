# VI Module Reference

Last updated: 2026-03-11

Use Versa modules to make HTTP requests, work with files, send email, and access VDB from your scripts.

## 1. What a module is in VI

A VI module provides functions you can import into Versa scripts and REPL sessions.

Typical examples are:

- HTTP requests
- JSON and XML parsing
- filesystem helpers
- email sending
- hashing and encryption helpers
- JWT creation and verification
- time and datetime helpers
- random value generation
- VDB integration

## 2. Import styles

## 2.1 Import everything from a module

```versa
http import *;
json_xml import *;
```

## 2.2 Import selected names

```versa
module import { resource_a, resource_b };
```

## 2.3 Import the module namespace

```versa
import module;
```

## 3. Runtime contexts that use modules

Modules are available in:

- standalone scripts
- REPL sessions
- generated-service script endpoints

That consistency matters because it means a script can usually move between local development, REPL experimentation, and service execution without changing its basic module model.

## 4. Module families

- [vdb](./vdb.md)
- [http](./http.md)
- [json_xml](./json_xml.md)
- [filer](./filer.md)
- [crypto](./crypto.md)
- [jwt](./jwt.md)
- [time](./time.md)
- [datetime](./datetime.md)
- [random](./random.md)
- [email](./email.md)
- [MediaCloud and custom modules](./mediacloud.md)

## 5. Related docs

- `docs/verun/versa/modules.md`
- `docs/verun/versa/vdb-module.md`
- `docs/verun/versa/runtime-cli-repl.md`
