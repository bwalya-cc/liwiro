# System Audit and Refactor Log (2026-03-07)

## Scope and Context
- Repository inspected end-to-end: `verun` (Java runtime + VDB), `liwiro/backend` (Flask orchestrator + generator), `liwiro/frontend` (Next.js control plane).
- User-provided project-context placeholders were not authoritative; repo code was treated as source of truth.
- Worktree was pre-dirty before this pass; unrelated existing edits were preserved.

## Phase 1 - Discovery

### System Overview
- `verun/vdb`: multi-tenant document DB + command processor (`VQLProcessor`) + HTTP server (`VDBHttpServer`) + RBAC (`Tumi`, `User`, `UserManager`).
- `verun/vi`: custom scripting runtime, parser, evaluator, module system (`http`, `email`, `jwt`, `crypto`, `vdb`, etc.).
- `liwiro/backend`: Flask platform that provisions API services from LAPIS config, stores service definitions in VDB, and manages runtime/auth/session orchestration.
- `liwiro/frontend`: Next.js UI for service builder/runtime/settings.

### Architecture and Flow Summary
- Auth flow:
  - VDB HTTP auth uses Basic auth -> session id (`X-Session-Id`) -> command execution.
  - Liwiro frontend authenticates against Flask backend; backend uses bearer sessions and delegated VDB credentials.
- Data flow:
  - VDB stores docs in filesystem paths under `verun/vdb/__data__/domains/<domain>/dbs/<db>/collections/<collection>/data`.
  - Liwiro stores service metadata/docs/config in VDB collections via backend VDB client.
- Business logic:
  - Multi-domain ownership and permission model with domain-level and collection-level grants.
  - Service-generation pipeline from LAPIS config to executable endpoint/runtime behavior.

### Incomplete/Partial Features Found
- `verun/vdb/src/main/java/verun/vdb/VQLProcessor.java` contains `handleDomainStatusCommand` with TODO marker and no command wiring from `processSingleCommand`.
- `liwiro/backend/generators/api_generator.py` retains explicit `Operation not implemented` fallback branch for unsupported endpoint operation types.

### Risk Areas Identified
- Script operations in VQL path were reachable without explicit RBAC checks (read/create/delete/execute).
- HTTP auth endpoint did not enforce HTTP method.
- Command validator logic could dereference invalid structures on unsupported commands.
- Frontend lint gate non-functional due missing ESLint deps.

## Phase 2 - Baseline Verification

### Baseline Results (before fixes)
- `verun`: `mvn test` passed.
- `liwiro/backend`: tests existed but local env missing test deps (`pytest`), then passed after installing in local venv.
- `liwiro/frontend`: `npm run build` passed; `npm run lint` failed due missing ESLint package.

## Phase 3/4/5 - Bug Fixes, Completion, Refactor

### Implemented Changes
1. **VDB script RBAC hardening**
   - Added explicit permission checks for script list/create/read/delete/execute.
   - File: `verun/vdb/src/main/java/verun/vdb/VQLProcessor.java`

2. **Command validator hardening**
   - Unsupported operations now fail deterministically with clear error.
   - Top-level query-operator validation now checks only actual top-level `query` object.
   - File: `verun/vdb/src/main/java/verun/vdb/CommandValidator.java`

3. **HTTP auth method safety**
   - `/auth` now rejects non-`POST` methods with `405`.
   - File: `verun/vdb/src/main/java/verun/vdb/VDBHttpServer.java`

4. **Python datetime deprecation fix**
   - Replaced `datetime.utcnow()` with timezone-aware UTC timestamp generation.
   - File: `liwiro/backend/app/auth_data.py`

5. **Frontend lint gate enablement**
   - Installed lint dependencies and resolved one lint error in auth setup text.
   - Files: `liwiro/frontend/package.json`, `liwiro/frontend/app/service-builder/components/AuthConfig.jsx`

6. **New regression tests for VDB**
   - Added VDB test infra (`junit-jupiter` + surefire) and new tests.
   - Files:
     - `verun/vdb/pom.xml`
     - `verun/vdb/src/test/java/verun/vdb/CommandValidatorTest.java`
     - `verun/vdb/src/test/java/verun/vdb/VQLProcessorScriptPermissionsTest.java`

## Phase 6 - Validation After Changes

- `verun`: `mvn test` -> PASS
  - Includes new VDB tests + existing VI tests.
- `liwiro/backend`: `./vvv/bin/python -m pytest -q` -> PASS (`7 passed`)
- `liwiro/frontend`:
  - `npm run lint` -> PASS with warnings only (React hook dependency warnings)
  - `npm run build` -> PASS

## Phase 7 - Security/Performance/Operability Review

### Security Improvements Applied
- Closed script-operation authorization gap in VQL layer.
- Enforced HTTP verb on auth endpoint.
- Reduced malformed-command handling ambiguity.

### Security/Quality Risks Remaining
- Domain status command remains partially implemented and not wired.
- Existing dependency conflicts (e.g., peer constraints around `date-fns`) require intentional package policy cleanup.

## Phase 8 - Documentation
- This file serves as the audit trail and execution log for this pass.

## Deferred/Not Changed
- No changes were made to pre-existing unrelated modified files in the dirty worktree.
- No broad architecture rewrite was performed; changes were incremental and backward-compatible.

## Follow-up Pass (Hook Dependency Cleanup)
- Resolved frontend `react-hooks/exhaustive-deps` warnings by stabilizing async loaders with `useCallback` and correcting dependency arrays.
- Files updated:
  - `liwiro/frontend/app/service-builder/page.jsx`
  - `liwiro/frontend/app/services/page.jsx`
  - `liwiro/frontend/app/services/[id]/page.jsx`
  - `liwiro/frontend/app/settings/page.jsx`
- Validation:
  - `npm run lint` -> clean (no warnings/errors)
  - `npm run build` -> pass
