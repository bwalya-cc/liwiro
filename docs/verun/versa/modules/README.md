# VI Module Reference

Last updated: 2026-03-11

This directory documents the native modules injected into the Versa runtime.

## 1. What a module is in VI

A VI module is a native capability surface that the evaluator makes available to Versa code. Modules exist because some behaviors are naturally implemented in the host runtime rather than in pure script syntax.

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

Most module implementation lives under:

- `verun/vi/src/main/java/verun/runtime/modules`

The `vdb` bridge is special because it also depends on evaluator-side behavior under:

- `verun/vi/src/main/java/verun/runtime/evaluator`

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

## 5. Related docs

- `docs/verun/versa/modules.md`
- `docs/verun/versa/vdb-module.md`
- `docs/verun/versa/runtime-cli-repl.md`
