# Verun Audit & Stabilization Report (2026-03-07)

## Scope
This pass focused on full runtime discovery, baseline verification, and high-impact stabilization for:
- `vi` demo execution reliability
- `vdb` query/test pipeline non-interactive execution
- `vi`/`vdb` integration flow correctness in demo paths

## 1) System Overview
- Multi-module Maven project with root aggregator `pom.xml`
- Modules:
  - `vi`: Versa interpreter/runtime + stdlib modules (`http`, `email`, `json_xml`, `filer`, `crypto`, `jwt`, `time`, `datetime`, `random`) and VDB native integration
  - `vdb`: File-backed DB runtime, VQL console/server, auth, scripts, index advisor, transaction APIs
- Operational scripts:
  - Build: `scripts/compile_all.sh`
  - Pipeline: `scripts/test_pipeline.sh`
  - VDB query runners: `vdb/scripts/run_query.sh`
  - Demo runners: `vi/scripts/run_demo_files.sh`, `vi/scripts/run_file.sh`

## 2) Architecture Summary
- `vi` parses and evaluates `.versa` scripts, optionally exposing `vdb` via `VDBNative` and `MemberAccessEvaluator`.
- `vdb` enforces user auth and context (domain/database), supports CRUD, script persistence/execution, jobs, and indexing.
- `vi` demo flow calls VDB APIs via native bridge methods (`auth`, `set`, `collection`, `save_script`, `schedule_job`, etc.).

## 3) Baseline Failures Observed
- Script failures returned process exit code `0` from `vi` main entrypoint, causing false green runs.
- Demo failures:
  - `vi/demo/core/for_loops.versa` used undefined variable (`numbers`).
  - `vi/demo/email/email_message_template_demo.versa` had broken import/declaration semantics.
  - `vi/demo/vdb/vdb_script_jobs_http_and_crud.versa` used `time.*` without importing `time`.
  - `vi/demo/vdb/vdb_list_and_object_access.versa` attempted insert before collection creation.
- Pipeline setup issues:
  - VDB console now requires Aegis acceptance prompts on first run; bootstrap script did not handle this.
  - Query runner and demo credentials could drift because auth defaults were hardcoded and not synced to local env-driven demo credentials.

## 4) Changes Implemented

### Runtime correctness
- `vi/src/main/java/verun/runtime/Main.java`
  - File execution mode now exits non-zero on runtime/read/validation failures.
  - This makes demo and CI scripts accurately fail on script errors.

### Demo fixes
- `vi/demo/core/for_loops.versa`
  - Added missing `numbers` definition.
- `vi/demo/email/email_message_template_demo.versa`
  - Fixed import style to supported single-line local import (`email_config import *;`).
  - Added required semicolon for object declaration.
  - Ensured `email` module import is explicit.
- `vi/demo/vdb/vdb_script_jobs_http_and_crud.versa`
  - Added `time import *;` for `time.time()`/`time.sleep()` usage.
- `vi/demo/vdb/vdb_list_and_object_access.versa`
  - Added explicit collection creation before insert and cleanup drop.

### Runner/pipeline hardening
- `vi/scripts/run_file.sh`
  - Email demo path now avoids prepending `email_config` when the script already imports it.
- `scripts/test_pipeline.sh`
  - Cleans `vdb/__data__/` in addition to root `__data__/` for deterministic DB state.
- `vdb/scripts/setup_demo_admin.sh`
  - Handles first-run Aegis acceptance non-interactively.
  - Resolves bootstrap user/password from local env-driven demo credentials (or `credentials.local.versa`) instead of baked-in defaults.
  - No longer hard-fails if other users already exist but target bootstrap user is missing.
- `vdb/scripts/run_query.sh`
  - Resolves auth defaults from local env-driven demo credentials (or `credentials.local.versa`) and runs console with explicit credentials.
  - Calls demo bootstrap helper before query execution.

## 5) Validation Results
- `./scripts/compile_all.sh`: PASS
- `./scripts/test_pipeline.sh`: PASS
- `./vi/scripts/run_demo_files.sh`: PASS (`EXIT:0`)
- `./vi/scripts/run_file.sh email/email_message_template_demo.versa`: PASS (returns handled SMTP result object)

## 6) Business Logic & Integration Notes
- VDB operations require explicit auth before context/CRUD calls; demos now consistently reflect this.
- Email/HTTP demos are environment-sensitive; network-blocked environments now fail gracefully in script output while runner behavior remains deterministic.
- Query pipeline uses console-mode auth and now stays aligned with demo credentials to prevent accidental credential drift.

## 7) Remaining Risks / Technical Debt
- Pre-existing dirty workspace files existed before this pass and were not reverted.
- Some query fixtures still include intentionally failing paths (e.g., schema mismatch examples); these are test-data semantics, not runtime breakages.
- Repository still contains generated `.class` files under `vi/src/main/java` (hygiene issue; not changed in this pass to avoid broad side effects).
- VDB module has no Java test suite; confidence relies on script/pipeline integration coverage.

## 8) Recommendations
1. Add dedicated JUnit coverage for VDB core (auth/context/CRUD/index/transactions).
2. Add a CI gate that runs `vi/scripts/run_demo_files.sh` and enforces non-zero failures.
3. Remove committed compiled artifacts from `src/main/java` and enforce via `.gitignore` + CI check.
4. Consider formalizing demo credentials as env-driven templates to avoid plaintext secrets in repo-managed demo files.
