# Repository Documentation

This `docs/` tree is the canonical documentation set for the repository.

Use it as four main sections:

- `docs/liwiro/`
  - Liwiro product and operator-facing material
- `docs/verun/`
  - Verun internals, including Versa and VDB
- `docs/integration/`
  - how Liwiro, Verun, VDB, VI, generated services, and LAPIS fit together
- `docs/reference/`
  - quick lookup material, commands, and documentation maps

## Start Here

Read in this order if you want the shortest path to a full picture:

1. `docs/liwiro/README.md`
2. `docs/verun/README.md`
3. `docs/integration/README.md`
4. `docs/reference/documentation-map.md`

## Local Startup

For a fresh local checkout:

1. Copy the example env files into local ignored env files.
2. Put real credentials only in the local env files or other ignored local files.
3. Run `./liwiro/scripts/start_all.sh`.

The startup layer is platform-aware and terminal-agnostic:

- public entrypoints stay under `liwiro/scripts/`
- platform-specific implementations live under `liwiro/scripts/unix/` and `liwiro/scripts/win/`
- host detection is cached in `tmp/platform-runtime.json` after a successful startup
- Python discovery is cached in `tmp/runtime-tools.json`
- busy default ports automatically roll forward to the next free local port

## Structure

- `docs/liwiro/`
  - Liwiro-specific guidance and platform-focused notes
- `docs/verun/`
  - Verun architecture, type system, Versa docs, and VDB docs
- `docs/integration/`
  - system description, architecture, component map, runtime flows, and Liwiro integration
- `docs/reference/`
  - command cheatsheets and document indexes
- `docs/legal/`
  - license notice, third-party licenses, credits, and commercial-policy notes
- `docs/compliance/`
  - compliance-specific operational notes such as MIT acceptance behavior
- `docs/archive/`
  - historical audits, research notes, and roadmap material
- `docs/assets/`
  - screenshots and shared documentation assets

## Storage Note

`verun/vdb/__data__` is intentionally checked in as an empty fresh-start directory. VDB recreates operational state there on demand, and structured runtime state under that tree is BSON-backed rather than JSON-backed.

## Runtime Docs Note

The generated-service route `/liwiro/docs` and `/liwiro/docs.json` is runtime API documentation exposed by generated services. It is separate from this repository documentation tree.

## Useful Entry Points

- `docs/integration/system-description.md`
- `docs/integration/liwiro-platform.md`
- `docs/integration/lapis-examples.md`
- `docs/liwiro/service-management-and-governance.md`
- `docs/verun/versa/README.md`
- `docs/verun/vdb/README.md`
- `docs/reference/command-cheatsheet.md`
