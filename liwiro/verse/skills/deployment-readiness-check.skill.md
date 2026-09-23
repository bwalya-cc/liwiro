# Skill: Deployment Readiness Check

## Purpose
Assess whether a service change is ready for production release.

## Best-Suited Agent
Ntiili

## Inputs
- deployment plan
- rollback plan
- environment notes
- monitoring coverage
- dependency and migration details

## Procedure
1. Review change scope.
2. Check rollback and recovery preparedness.
3. Check migrations and dependency changes.
4. Review observability and alert coverage.
5. Review configuration and secret handling.
6. Review blast radius and rollback triggers.
7. Produce a go/no-go style summary.

## Output Format
- Readiness Summary
- Strengths
- Missing Safeguards
- Risks
- Go/No-Go Concerns
- Immediate Fixes

## Quality Bar
The review must identify practical risks that could turn a routine release into a production mess.
