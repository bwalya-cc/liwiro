---
id: domains/versa-vdb-employee-cli
title: Versa VDB Employee CLI Design
type: domain
summary: Guidance for menu-driven employee attendance workflows implemented with Versa and VDB.
tags:
  - versa
  - vdb
  - employee
  - attendance
  - cli
domains:
  - versa
  - vdb
  - ux
appliesToCapabilities:
  - vi-script
  - vdb-query
appliesToArtifacts:
  - vi-script
  - vdb-query
appliesToAgents:
  - liwiro-architect
appliesToPages:
  - service-manager
  - vi-portal
  - vdb-portal
selectionHints:
  - Use for employee check-in, check-out, menu flows, and attendance storage requests.
priority: 10
---
# Versa VDB Employee CLI Design

This domain file covers the combined design problem of a menu-driven attendance workflow backed by VDB and presented through Versa.

- Model attendance as explicit events rather than implicit status flags when the workflow needs auditability.
- Separate user-facing menu flow from storage operations so the script stays understandable.
- Treat employee identity, attendance event shape, and reporting flow as core design concerns.
- When the prompt mixes UX, storage, and code generation, gather enough structure before claiming the output is runnable.
