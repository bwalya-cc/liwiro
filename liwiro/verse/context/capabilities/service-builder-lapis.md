---
id: capabilities/service-builder-lapis
title: Service Builder Capability
type: capability
summary: Rules for returning LAPIS service drafts for the Service Builder.
tags:
  - lapis
  - service
  - builder
domains:
  - platform
  - services
appliesToCapabilities:
  - service-builder-lapis
appliesToArtifacts:
  - service-builder-lapis
appliesToAgents:
  - liwiro-architect
appliesToPages:
  - service-builder
  - service-manager
selectionHints:
  - Use when the user wants a new service definition or generated service draft.
priority: 8
---
# Service Builder Capability

Return `service-builder-lapis` when the user needs a new service contract or builder-ready draft.

- Include at least one model.
- Include at least one endpoint for concrete service generation requests.
- Keep metadata builder-valid and avoid empty placeholders.
