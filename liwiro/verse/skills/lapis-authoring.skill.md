# Skill: LAPIS Authoring

## Purpose
Draft, repair, and validate Liwiro LAPIS service definitions so they are ready for the Service Builder and backend generator.

## Best-Suited Agent
Kalulu

## Inputs
- service goal
- domain model description
- route or CRUD requirements
- auth requirements
- platform context from Service Builder or Service Manager
- LAPIS validation errors

## Procedure
1. Start from the canonical top-level shape: metadata, auth, models, endpoints.
2. Ensure metadata includes apiName, basePath, version, and sensible database defaults.
3. Add at least one model and one endpoint for concrete service-generation requests.
4. Keep linkedModel references aligned with actual model ids.
5. For script endpoints, place logic in versaScript and keep env use in metadata.env.
6. For custom endpoints, ensure vqlQuery is a readable VDB command string.
7. Repair drafts against backend validation errors before presenting them as ready.
8. Guide the user to the LAPIS reference and Service Builder manual when helpful.

## Output Format
- concise design summary
- validated LAPIS draft
- validation notes or blocked issues
- next step in Service Builder or Service Manager

## Failure Conditions
- missing service goal
- missing model ownership
- invalid or incomplete LAPIS shape
- linkedModel references unknown models

## Quality Bar
Returned LAPIS must be generator-ready, structurally valid, and understandable to a user following along in the public manuals.
