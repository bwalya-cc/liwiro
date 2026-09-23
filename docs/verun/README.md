# Verun Documentation

Verun contains the two runtime layers beneath Liwiro:

- `VI`
  - the Versa interpreter and runtime
- `VDB`
  - the storage, query, session, and RBAC engine

## Guided Learning Paths

- `docs/verun/guide/versa-guide.md`
  - beginner → intermediate → pro checkpoints for running Versa, importing modules, and reaching production scripting plus REPL/CLI insights.
- `docs/verun/guide/vdb-guide.md`
  - staged VDB operations: setup, day-to-day VQL, auth/TUMI, persistence, and service-integration guidance.

## Start Here

- `docs/verun/architecture.md`
  - high-level Verun architecture and subsystem boundaries
- `docs/verun/type-system.md`
  - cross-runtime type mapping between Versa and VDB

## Versa / VI

- `docs/verun/versa/README.md`
- `docs/verun/versa/syntax.md`
- `docs/verun/versa/syntax-rules.md`
- `docs/verun/versa/runtime-cli-repl.md`
- `docs/verun/versa/modules.md`
- `docs/verun/versa/modules/README.md`
- `docs/verun/versa/vdb-module.md`
- `docs/verun/versa/vdb-scripts-demo.md`

## VDB

- `docs/verun/vdb/README.md`
- `docs/verun/vdb/setup-and-operations.md`
- `docs/verun/vdb/vql-reference.md`
- `docs/verun/vdb/tumi-rbac.md`
- `docs/verun/vdb/usage-guide.md`

## Storage Note

`verun/vdb/__data__` is a fresh-start runtime directory. The repository keeps only an empty placeholder there. Structured state under that tree is BSON-backed, and operational files are recreated on demand by VDB startup and runtime flows.
