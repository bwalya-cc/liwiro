# Versa and VI Reference

Last updated: 2026-03-29

Use this folder as a practical reference set for writing, validating, and running Versa.

## Guided path

- `docs/verun/guide/versa-guide.md`
  - stepwise beginner → intermediate → pro checkpoints, with tasks such as running the REPL, importing modules, exercising the `vdb` bridge, and exploring runtime CLI/REPL debugging. Follow the links in each section before digging into the detailed references.

For a searchable, machine-readable reference covering both Versa and VDB, use `verun/vi/verse-verun-reference/reference.json`. The guides below provide examples and step-by-step instructions.

## Fast path

Read these in order when you need to write or troubleshoot Versa code:

1. `docs/verun/versa/syntax.md`
   This is the language reference for statements, expressions, control flow, and literal shapes.
2. `verun/vi/verse-verun-reference/reference.json`
   Look up Versa features and shared Versa/VDB integration details in a machine-readable format.
3. `docs/verun/versa/syntax-rules.md`
   This is the rules-and-mistakes companion. Use it for parser errors, invalid constructs, and authoring constraints.
4. `docs/verun/versa/modules.md`
   This is the index of built-in modules and the entry point to module-specific docs.
5. `docs/verun/versa/vdb-module.md`
   Read this before writing scripts that use `vdb`.
6. `docs/verun/versa/runtime-cli-repl.md`
   Read this for REPL behavior, file execution, and Liwiro VI portal runtime flows.

## What lives here

- `syntax.md`
  Keywords, operators, expression forms, statements, control flow, function/class forms, and examples.
- `syntax-rules.md`
  Canonical authoring rules, invalid patterns, parser expectations, and common repair guidance.
- `modules.md`
  Module index and import guidance.
- `modules/*.md`
  Per-module function reference, inputs, outputs, and examples.
- `vdb-module.md`
  `vdb` bridge usage from Versa, including collection access and runtime expectations.
- `runtime-cli-repl.md`
  Runtime entry points, REPL behavior, and portal/runtime integration details.

## Runtime surfaces

- File execution
  `cd verun && ./vi/scripts/run_file.sh <demo_or_path>`
- REPL
  `cd verun && ./vi/scripts/run_repl.sh`
- Liwiro VI portal
  `/vi-portal`

## High-value rules

- Single-line comments are `#`, not `//`.
- Keep module imports at the top of the file.
- Import a module before using it as a namespace, for example `vdb import *;`.
- Service `versaScript` endpoints may rely on runtime-provided names such as `params` and `service`.
- Use the syntax examples in this guide when writing executable Versa scripts.
