# Skill: API Design Review

## Purpose
Review a proposed or existing REST API and identify design, consistency, versioning, error handling, and maintainability issues.

## Best-Suited Agent
Kalulu

## Inputs
- endpoint list
- request and response examples
- authentication model
- error model
- related service context
- pagination, filtering, and sorting behavior

## Procedure
1. Identify the resource model and naming patterns.
2. Check HTTP method semantics.
3. Review request and response consistency.
4. Review versioning approach.
5. Check pagination, filtering, and sorting structure.
6. Examine auth and permission boundaries.
7. Review idempotency expectations.
8. Review error response structure.
9. Identify breaking-change risks.
10. Produce prioritized recommendations.

## Output Format
- Summary
- Strengths
- Key Issues
- Risks
- Recommended Changes
- Optional Improved Endpoint Examples

## Failure Conditions
- missing route definitions
- no request or response samples
- no stated auth model
- unclear service ownership

## Quality Bar
Recommendations must be concrete, technically defensible, and tied to maintainability or integration outcomes.
