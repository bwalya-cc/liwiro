# Documentation Map

Last updated: 2026-03-29

This page is the quickest route through the repository documentation after the root index.

## Main Reading Order

1. `docs/integration/system-description.md`
2. `docs/integration/architecture.md`
3. `docs/integration/component-map.md`
4. `docs/integration/runtime-flows.md`
5. `docs/integration/liwiro-platform.md`
6. `docs/integration/liwiro-cli.md`
7. `docs/integration/lapis-examples.md`

## By Area

### Liwiro

- `docs/liwiro/README.md`
- `docs/integration/liwiro-platform.md`
- `docs/integration/liwiro-cli.md`
- `docs/liwiro/verse-chat.md`
- `docs/integration/lapis-examples.md`

### Verun

- `docs/verun/README.md`
- `docs/verun/architecture.md`
- `docs/verun/type-system.md`

### Versa / VI

- `verun/vi/verse-verun-reference/reference.json`
- `verun/vi/verse-verun-reference/index.html`
- `verun/vi/versa-wiki/versa-reference.json`
- `docs/verun/versa/README.md`
- `docs/verun/versa/syntax.md`
- `docs/verun/versa/syntax-rules.md`
- `docs/verun/versa/runtime-cli-repl.md`
- `docs/verun/versa/modules.md`
- `docs/verun/versa/modules/README.md`
- `docs/verun/versa/vdb-module.md`
- `docs/verun/versa/vdb-scripts-demo.md`
- `docs/verun/versa/datetime-custom-format.md`

### VDB

- `verun/vi/verse-verun-reference/reference.json`
- `docs/verun/vdb/README.md`
- `docs/verun/vdb/setup-and-operations.md`
- `docs/verun/vdb/vql-reference.md`
- `docs/verun/vdb/tumi-rbac.md`
- `docs/verun/vdb/vdb-interface-transport-guide.html`
- `docs/verun/vdb/usage-guide.md`
- `docs/verun/vdb/auth-and-rbac-notes.md`
- `docs/verun/vdb/echo-command.md`

### Operations and Legal

- `docs/reference/command-cheatsheet.md`
- `docs/compliance/mit-license-and-acceptance.md`
- `docs/legal/license-notice.md`
- `docs/legal/third-party-licenses.md`
- `docs/legal/license-and-commercial-policy.md`
- `docs/legal/acknowledgements-and-credits.md`

### Historical Material

- `docs/archive/system-audit-2026-03-07.md`
- `docs/archive/verun-audit-2026-03-07.md`
- `docs/archive/research-notes.md`
- `docs/archive/verun-next-steps.md`
- `docs/archive/verun-roadmap.md`

## Reader Paths

### Platform operator

1. `docs/liwiro/README.md`
2. `docs/integration/runtime-flows.md`
3. `docs/integration/liwiro-platform.md`
4. `docs/verun/vdb/setup-and-operations.md`
5. `docs/reference/command-cheatsheet.md`

### Service author

1. `docs/integration/system-description.md`
2. `docs/integration/liwiro-platform.md`
3. `docs/verun/vdb/vql-reference.md`
4. `docs/verun/versa/syntax.md`
5. `docs/verun/versa/vdb-module.md`

### Runtime contributor

1. `docs/verun/README.md`
2. `docs/integration/component-map.md`
3. `docs/verun/architecture.md`
4. `docs/verun/vdb/README.md`
5. `docs/verun/versa/README.md`

## Scope Note

The repository docs are implementation-aware. When code and docs diverge, the code is authoritative until the relevant pages are updated.

The canonical combined Versa + VDB reference now lives in `verun/vi/verse-verun-reference/`. The older `verun/vi/versa-wiki/` bundle remains as the Versa-focused compatibility surface.
