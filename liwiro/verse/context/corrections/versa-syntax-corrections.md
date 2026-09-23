---
id: corrections/versa-syntax-corrections
title: Versa Syntax Corrections
type: correction
summary: Known Verse-specific mistakes that must influence routing and validation.
tags:
  - versa
  - corrections
  - syntax
domains:
  - versa
appliesToCapabilities:
  - vi-script
appliesToArtifacts:
  - vi-script
appliesToAgents:
  - liwiro-architect
appliesToPages:
  - vi-portal
  - service-manager
selectionHints:
  - Use when Versa code generation or repair is involved.
priority: 9
---
# Versa Syntax Corrections

Known failure patterns should be carried into Versa generation and repair.

- Single-line comments use `#`, not `//`.
- Avoid undocumented runtime assumptions for CLI wrappers or hidden globals.
- Validate VDB authentication usage before returning a VDB-connected Versa draft.
