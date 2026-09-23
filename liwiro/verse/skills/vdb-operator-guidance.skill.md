# Skill: VDB Operator Guidance

## Purpose
Help users form valid VDB and VQL operations for the VDB Portal, with accurate command/query shapes and operational guidance.

## Best-Suited Agent
Kalulu

## Inputs
- desired read/write/admin action
- collection or domain/db context
- VDB Portal context
- VQL snippets
- auth or RBAC questions

## Procedure
1. Determine whether the user needs a list/read/write/admin/TUMI action.
2. Keep portal-ready query payloads as readable command strings, such as `read users` or `read collection orders`.
3. Use the VQL reference and VDB manual as the canonical shape source.
4. Distinguish normal data access from TUMI/RBAC or administrative actions.
5. Avoid inventing unsupported commands or mixed payload formats.
6. If the request is risky or ambiguous, explain the safe next step before presenting a runnable query.
7. Point the user to the VDB Portal manual or VQL reference when that helps them verify the shape.

## Output Format
- concise operator explanation
- validated portal-ready VDB/VQL draft when appropriate
- warning or blocker when the requested command shape is unsafe or unsupported

## Failure Conditions
- malformed command syntax
- unsupported command shape
- missing collection/domain/db target when required
- auth-sensitive action presented as ordinary data access

## Quality Bar
Returned VDB guidance must match current portal expectations and should be directly usable or clearly blocked for a stated reason.
