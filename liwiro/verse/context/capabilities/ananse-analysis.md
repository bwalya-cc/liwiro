---
id: capabilities/ananse-analysis
title: Ananse Analysis Capability
type: capability
summary: Rules for returning charts, findings, and analysis payloads.
tags:
  - analytics
  - chart
  - ananse
domains:
  - analytics
  - reporting
appliesToCapabilities:
  - ananse-analysis
appliesToArtifacts:
  - ananse-analysis
appliesToAgents:
  - liwiro-analyst
appliesToPages:
  - ananse-workbench
selectionHints:
  - Use when the user asks for trends, comparisons, findings, or charts.
priority: 8
---
# Ananse Analysis Capability

Return `ananse-analysis` when the user needs chart-ready analysis.

- Include metrics and findings when possible.
- Prefer a meaningful chart intent over a generic graph.
- Include dataset linkage when the payload is tied to a known dataset.

- Use the Live platform intelligence context block: these are server-collected, permission-filtered observations with dataset IDs and chart data. No manual upload is required.
- Use the same observations in proactive reviews and user-started chats. Mention observation scope, timestamps and missing data. Never invent traffic or business results.
