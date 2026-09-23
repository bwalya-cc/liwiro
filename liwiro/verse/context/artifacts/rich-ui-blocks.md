---
id: artifacts/rich-ui-blocks
title: Rich UI Blocks Contract
type: artifact
summary: Allowed supporting block types for Verse responses.
tags:
  - ui
  - blocks
  - checklist
  - table
domains:
  - verse
appliesToAgents:
  - liwiro-architect
  - liwiro-analyst
  - liwiro-documentation-advisor
selectionHints:
  - Use when the response should include structured supporting content beyond the main card.
priority: 5
---
# Rich UI Blocks Contract

Verse may return structured supporting blocks alongside the main card.

Allowed supporting block types:

- `checklist`
- `callout`
- `table`
- `evidence-panel`

Blocks should stay typed and compact so the frontend can render them safely.
