---
id: surfaces/service-manager
title: Service Manager Surface
type: surface
summary: Behavior and expectations when Verse is invoked from the Service Manager.
tags:
  - services
  - operations
  - manager
domains:
  - platform
appliesToCapabilities:
  - service-manager-action
  - service-builder-lapis
  - vi-script
appliesToAgents:
  - liwiro-architect
appliesToPages:
  - service-manager
selectionHints:
  - Use whenever the current page is /services.
priority: 7
---
# Service Manager Surface

The Service Manager is operational by default, but users may still ask for adjacent build artifacts from there.

- Starting, stopping, or deleting services should map to service-manager actions.
- New service definitions may map to Service Builder drafts.
- Scratch Versa tooling may still be valid when the user explicitly asks for a CLI or script from this page.
