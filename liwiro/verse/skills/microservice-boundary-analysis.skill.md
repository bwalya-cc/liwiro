# Skill: Microservice Boundary Analysis

## Purpose
Assess whether service boundaries are coherent, loosely coupled, and operationally reasonable.

## Best-Suited Agent
Kalulu

## Inputs
- service list
- responsibilities per service
- data ownership notes
- integration map
- scaling or team constraints

## Procedure
1. Identify service responsibilities.
2. Check for overlapping ownership.
3. Identify shared-state or shared-schema coupling.
4. Review communication patterns and dependency direction.
5. Assess team and deployment alignment.
6. Highlight areas of fragmentation or over-centralization.
7. Recommend boundary changes or a modular monolith where appropriate.

## Output Format
- Boundary Assessment
- Coupling Risks
- Ownership Concerns
- Recommended Restructuring
- Tradeoffs

## Failure Conditions
- incomplete service descriptions
- no integration map
- unclear data ownership

## Quality Bar
The analysis must reduce ambiguity around service ownership and integration risk.
