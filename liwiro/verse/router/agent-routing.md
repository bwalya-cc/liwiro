# Agent Routing

## Objective
Choose the best initial Verse agent for a user request based on intent, current screen context, attached artifacts, and known thread state.

## Default Routing Priorities

### Route to Kalulu (Liwiro Architect) when the user asks about:
- REST API design
- microservice boundaries
- integration planning
- schema or contract design
- authentication patterns
- service decomposition
- versioning
- backend structure

### Route to Ananse (Liwiro Analyst) when the user asks about:
- metrics
- dashboards
- trends
- anomalies
- business interpretation
- impact summaries
- comparative performance
- data-backed decisions
- uploaded datasets
- chart selection or visualization methods
- distributions, segment comparisons, and outlier explanation
- data exploration workbench tasks

### Route to Ntiili (Liwiro Reliability Advisor) when the user asks about:
- deployments
- incidents
- logging
- alerts
- retries
- scaling
- observability
- production readiness
- uptime or runtime stability

### Route to Dage (Liwiro Compliance Advisor) when the user asks about:
- controls
- audit readiness
- policy alignment
- access governance
- retention
- evidence
- process conformance
- risk posture

### Route to Nzou (Liwiro Documentation Advisor) when the user asks about:
- documentation
- API docs
- ADRs
- runbooks
- release notes
- handover notes
- summaries that should become durable artifacts

## Context-Based Overrides

- If the user is on an architecture or service design screen, bias toward **Kalulu**
- If the user is on a dashboard or metrics screen, bias toward **Ananse**
- If the user is on the Ananse workbench or an uploaded-data analysis screen, bias toward **Ananse**
- If the user is on an incident, alert, or deployment screen, bias toward **Ntiili**
- If the user is on an audit, permissions, or controls screen, bias toward **Dage**
- If the user is editing or requesting a document artifact, bias toward **Nzou**

## Ambiguous Requests

When a request spans domains:
1. choose the agent whose specialty dominates the user’s immediate goal
2. let that agent invite another specialist if needed
3. do not force multiple agents into the thread unless it improves the result

## Fallback
If the request is too vague, route to the best likely specialist and require that agent to state assumptions explicitly.
