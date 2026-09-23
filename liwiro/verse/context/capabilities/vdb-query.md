---
id: capabilities/vdb-query
title: VDB Query Capability
type: capability
summary: Rules for returning ready-to-run VDB query payloads.
tags:
  - vdb
  - query
  - data
domains:
  - vdb
  - storage
appliesToCapabilities:
  - vdb-query
appliesToArtifacts:
  - vdb-query
appliesToAgents:
  - liwiro-architect
appliesToPages:
  - vdb-portal
  - service-manager
selectionHints:
  - Use when the user asks for direct VDB query or collection operations.
priority: 8
---
# VDB Query Capability

Return `vdb-query` when the user needs a readable command for the VDB Portal.

- `artifact.vdbQuery` must be a non-empty readable command string, such as `read users` or `read collection orders`.
- Use native Versa command syntax: `read collection orders where status == "open"`, `create user bob = { email: "bob@example.com", password: "secret", role: application };`, and `update collection orders where id == 1 { status = "closed"; }`. JSON command/query/update envelopes are no longer accepted.
- Require storage-target context such as collection, domain, or command intent when possible.
