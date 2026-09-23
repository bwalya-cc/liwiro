# Verse Documentation Scaffold

Verse is the multi-agent collaboration layer for Liwiro. It provides a specialist team of agents that can collaborate with users and with each other inside a shared thread, using retrieval-augmented generation and a structured shared context space called `mind-share`.

## Purpose

Verse exists to help Liwiro users:
- design and integrate microservices
- interpret operational and business data
- improve reliability and deployment readiness
- review compliance posture and governance concerns
- produce durable, usable technical and operational documentation

## Agent Team

- **Liwiro Architect** (`Kalulu`)
- **Liwiro Analyst** (`Ananse`)
- **Liwiro Reliability Advisor** (`Ntiili`)
- **Liwiro Compliance Advisor** (`Dage`)
- **Liwiro Documentation Advisor** (`Nzou`)

## Design Principles

1. **Specialization over generic chat**
   - Each agent has a distinct remit, decision style, and output model.
2. **Shared but disciplined memory**
   - Agents can write to `mind-share`, but must preserve traceability, confidence, and source basis.
3. **Context-grounded reasoning**
   - Agents should prefer platform facts, retrieved artifacts, and current thread evidence over generic inference.
4. **Structured outputs**
   - Recommendations should be easy to act on, save, and audit.
5. **Visible handoffs**
   - When a topic crosses domains, agents should invite the best-suited specialist into the thread.

## Folder Structure

```text
/verse
  /agents
  /skills
  /router
  /mind-share
```

## File Conventions

- `*.persona.md` defines identity, scope, behavior, handoffs, and memory rules for an agent.
- `*.skill.md` defines a reusable expert procedure.
- `/router/*.md` defines initial routing, handoffs, and thread behavior.
- `/mind-share/*.md` stores shared structured context.

## Write Discipline for mind-share

Agents may:
- append structured entries
- add summaries
- record assumptions
- flag contradictions
- draft artifacts for review

Agents must not:
- silently rewrite stable facts
- convert assumptions into facts
- erase another agent’s contribution without justification
- overwrite decisions without recording a revision trail

## Standard Entry Format

```md
### 2026-03-22T14:10:00Z | Kalulu | Inference | Medium confidence
Basis: service map, API spec excerpt, thread summary
Observation: Billing Service appears tightly coupled to Account Service through shared customer state assumptions.
Recommendation: review ownership boundaries before implementing retry logic.
```

## Confidence Scale

- **High**: strongly supported by platform context, explicit user data, or validated artifacts
- **Medium**: reasonable inference with partial evidence
- **Low**: plausible but blocked by missing details
- **Blocked**: cannot proceed responsibly without more context

## Next Build Priorities

1. Implement agent loading from `agents/*.persona.md`
2. Implement skill registry from `skills/*.skill.md`
3. Build a router that chooses an initial agent and supports handoffs
4. Add file-backed read/write adapters for `mind-share`
5. Add artifact generation actions for ADRs, runbooks, design reviews, and summaries
