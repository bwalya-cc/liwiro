# VDB Guided Path

Walk through VDB setup, runtime operations, and advanced data/security workflows in three stages?with links to the companion reference files.

## Overview

- **Stage order:** Beginner ? Intermediate ? Pro
- **Purpose:** Provide actionable steps before diving into dense reference chapters.

---

## Stage 1 ? Beginner: getting VDB running

- **Objective:** Start VDB locally, explore the console, and understand the CLI/portal entry points.
- **Checklist:**
  - [ ] Run `./liwiro.sh local start vdb --vdb-transport unixsocket` (or `./liwiro/scripts/start_all.sh`) and verify health via `vdb status` commands; see `docs/verun/vdb/setup-and-operations.md#startup` for prereqs.
  - [ ] Launch the console (`verun/vdb/scripts/convo.sh`) or portal (`/vdb-portal`) to observe domains, users, and logs.
  - [ ] Inspect `verun/vdb/__data__/` to confirm the filesystem structure described under `docs/verun/vdb/README.md#persistence` and ensure the placeholder data is initialized.
- **Next read:** `docs/verun/vdb/setup-and-operations.md` for transport modes, sockets, and runtime diagnostics.

---

## Stage 2 ? Intermediate: documents, scripts, and day-to-day commands

- **Objective:** Manage collections, documents, and stored scripts using VQL; learn the usage guide for common tasks.
- **Checklist:**
  - [ ] Follow `docs/verun/vdb/usage-guide.md` to create a domain/database, define a collection model, and insert documents.
  - [ ] Run sample VQL commands (`list`, `read`, `update`, `transaction`, `export`); keep `docs/verun/vdb/vql-reference.md` handy for argument shapes and examples.
  - [ ] Use `docs/verun/vdb/usage-guide.md#scripts` plus `verun/vdb/scripts/run_query.sh` to execute stored script jobs or ad-hoc queries.
  - [ ] Practice `tumi` commands via `docs/verun/vdb/tumi-rbac.md` to grant read/write scopes?observe how TUMI roles map to `VDB` sessions.
- **Next read:** `docs/verun/vdb/vql-reference.md` for command families and `docs/verun/vdb/usage-guide.md#operations` for concurrency/exports.

---

## Stage 3 ? Pro: integration, auth, and persistence mastery

- **Objective:** Understand how Liwiro services and Versa scripts rely on VDB, plus the auth/transport tradeoffs.
- **Checklist:**
  - [ ] Read `docs/verun/vdb/tumi-rbac.md` and `docs/verun/vdb/auth-and-rbac-notes.md` to capture multi-tenant auth flows, TUMI role creation, and portal permission paths.
  - [ ] Inspect `liwiro/backend/app/vdb_transport.py` to see how transports (unix socket, HTTP, named pipe) are normalized for generated services.
  - [ ] Dive into persistence details via `docs/verun/architecture.md#state-ownership` and `docs/verun/vdb/README.md#persistence`; experiment with service restarts to observe state durability.
  - [ ] Pair VQL advanced commands (`model`, `tumi`) with stored scripts from `verun/vdb/scripts/` to see how services and VI portal rely on the same VDB engine.
- **Fallback:** When verifying service integrations, refer back to `docs/integration/architecture.md#backend---vdb` for transport context.

---

## Deep dive references

| Topic | Doc |
| --- | --- |
| Setup & operational scripts | `docs/verun/vdb/setup-and-operations.md` |
| Usage patterns & tasks | `docs/verun/vdb/usage-guide.md` |
| VQL command catalog | `docs/verun/vdb/vql-reference.md` |
| TUMI and RBAC | `docs/verun/vdb/tumi-rbac.md` |
| Auth notes | `docs/verun/vdb/auth-and-rbac-notes.md` |

Link back to `docs/verun/README.md` to see the complementary Versa guide.
