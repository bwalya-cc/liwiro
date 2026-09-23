---
id: capabilities/service-manager-action
title: Service Manager Action Capability
type: capability
summary: Rules for returning executable Service Manager actions.
tags:
  - service
  - operations
  - manager
domains:
  - platform
  - operations
appliesToCapabilities:
  - service-manager-action
appliesToArtifacts:
  - service-manager-action
appliesToAgents:
  - liwiro-architect
appliesToPages:
  - service-manager
selectionHints:
  - Use when the user asks to start, stop, or delete an existing service.
priority: 7
---
# Service Manager Action Capability

Return `service-manager-action` when the user wants an operational action on an existing service.

- Include the exact action.
- Include `processId` or `serviceName`.
- Keep destructive actions explicit and unambiguous.
