---
id: capabilities/vi-script
title: Versa Draft Capability
type: capability
summary: Rules for returning runnable Versa drafts and related VI Portal cards.
tags:
  - versa
  - vi
  - script
  - cli
domains:
  - versa
  - automation
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
  - Use when the user asks for Versa code, CLI-like flows, or runnable scripts.
priority: 9
---
# Versa Draft Capability

Return `vi-script` when the user needs runnable Versa output or a VI Portal draft.

- Include real `artifact.versaSource`.
- Include a sensible `artifact.path` when it helps the user identify the draft.
- Keep the visible chat response concise and let the artifact carry the runnable payload.
- Validate against documented Versa syntax and VDB integration rules before presenting the draft as ready.
