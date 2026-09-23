# Handoff Rules

## Objective
Define when Verse agents should invite one another into a thread.

## Handoff Principles
An agent should invite another agent when:
- the question crosses specialist boundaries
- confidence would materially improve with another perspective
- the requested output requires another specialist’s artifact or validation
- there is meaningful risk outside the current agent’s remit

## Common Handoffs

### Kalulu → Ntiili
Use when architecture recommendations affect:
- deployment safety
- observability
- retry and timeout behavior
- failure isolation
- runtime resilience

### Kalulu → Dage
Use when design choices affect:
- access boundaries
- auditability
- control ownership
- retention obligations
- policy-sensitive flows

### Kalulu → Nzou
Use when the discussion should become:
- an ADR
- architecture note
- API reference
- implementation summary

### Ananse → Kalulu
Use when patterns suggest:
- bad service boundaries
- inefficient API design
- brittle integration design
- capacity issues rooted in architecture

### Ananse → Ntiili
Use when metrics suggest:
- incidents
- reliability regression
- alerting blind spots
- unstable deployment outcomes

### Ananse → Nzou
Use when findings should become:
- management brief
- summary artifact
- repeatable report

### Ntiili → Kalulu
Use when incidents point to:
- design flaws
- coupling
- schema misuse
- bad ownership boundaries

### Ntiili → Dage
Use when runtime practices raise:
- logging exposure concerns
- evidence integrity problems
- access governance issues
- retention or traceability risk

### Ntiili → Nzou
Use when operational guidance should become:
- a runbook
- post-incident summary
- recovery note
- deployment checklist

### Dage → Kalulu
Use when policy or control issues are caused by:
- architecture decisions
- poor separation of responsibility
- data ownership ambiguity

### Dage → Nzou
Use when control expectations should become:
- policy notes
- audit artifacts
- evidence templates
- procedural documentation

### Nzou → Any Specialist
Use when documentation exposes unresolved issues that need a specialist review before publication.

## Constraints
- Keep handoffs visible to the user
- State the reason for the handoff
- Avoid unnecessary agent pileups
- If two specialists disagree, preserve both views and make the tradeoff explicit
