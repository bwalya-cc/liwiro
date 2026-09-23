#!/usr/bin/env bash
# Run the deterministic Liwiro/Verun release checks.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[1/6] Java VDB tests"
(cd verun && mvn -q -pl vdb -am test)

echo "[2/6] Java Versa build"
(cd verun && mvn -q -pl vi -am test)

echo "[3/6] Backend syntax and transport/config tests"
python3 -m py_compile liwiro/backend/app/main.py liwiro/backend/generators/api_generator.py
python3 -m py_compile verun/vi/versa-wiki/build_reference.py
backend_suite_log="$(mktemp "${TMPDIR:-/tmp}/liwiro-backend-suite.XXXXXX.log")"
if ! liwiro/backend/vvv/bin/python -m unittest discover -s liwiro/backend/tests -p 'test_*.py' >"$backend_suite_log" 2>&1; then
  cat "$backend_suite_log"
  rm -f "$backend_suite_log"
  exit 1
fi
cat "$backend_suite_log"
if grep -q "VI runtime jar missing" "$backend_suite_log"; then
  echo "Release gate failed: generated-service VI runtime coverage was skipped." >&2
  rm -f "$backend_suite_log"
  exit 1
fi
backend_skip_count="$(sed -nE 's/.*OK \(skipped=([0-9]+)\).*/\1/p' "$backend_suite_log" | tail -1)"
if [[ -n "$backend_skip_count" && "$backend_skip_count" -gt 3 ]]; then
  echo "Release gate failed: unexpected backend test skips ($backend_skip_count; expected at most 3 local TCP-sandbox skips)." >&2
  rm -f "$backend_suite_log"
  exit 1
fi
rm -f "$backend_suite_log"
liwiro/backend/vvv/bin/python -m unittest liwiro.backend.tests.test_config_paths liwiro.backend.tests.test_vdb_transport
liwiro/backend/vvv/bin/python -m unittest liwiro.backend.tests.test_config_schema
liwiro/backend/vvv/bin/python -m unittest liwiro.backend.tests.test_vdb_portal
liwiro/backend/vvv/bin/python -m unittest liwiro.backend.tests.test_verse_api
liwiro/backend/vvv/bin/python -m unittest \
  liwiro.backend.tests.test_api_generator_runtime_and_script.ApiGeneratorTests.test_rate_limiting_returns_retry_after_after_limit \
  liwiro.backend.tests.test_api_generator_runtime_and_script.ApiGeneratorTests.test_custom_vql_endpoint_merges_request_query_and_body \
  liwiro.backend.tests.test_api_generator_runtime_and_script.ApiGeneratorTests.test_custom_vql_endpoint_rejects_json_object

echo "[4/6] Frontend typecheck and production build"
(cd liwiro/frontend && npm run lint && npm run typecheck && npm run build)

if [[ "${LIWIRO_RELEASE_RUN_DEMOS:-1}" == "1" ]]; then
  echo "[5/6] Versa demo suite"
  VI_DEMO_ALLOW_MISSING_EXTERNAL=1 bash verun/vi/scripts/run_demos.sh
else
  echo "[5/6] Versa demo suite (skipped; set LIWIRO_RELEASE_RUN_DEMOS=1)"
fi

echo "[6/6] JSON/config integrity"
python3 liwiro/scripts/audit_versa_configs.py
python3 - <<'PY'
import json
import sys
import re
from pathlib import Path
for path in [
    Path("verun/vdb/src/main/resources/help.json"),
    *Path("verun/vdb/src/main/resources/queries").glob("*.json"),
    Path("liwiro/frontend/lib/agent-docs.json"),
    Path("liwiro/verse/liwiro-platform-reference/reference.json"),
    Path("verun/vi/verse-verun-reference/reference.json"),
    Path("verun/vi/versa-wiki/versa-reference.json"),
]:
    json.loads(path.read_text(encoding="utf-8"))
for path in Path("liwiro/data/lapis-examples").glob("*.json"):
    payload = json.loads(path.read_text(encoding="utf-8"))
    for endpoint_id, endpoint in (payload.get("endpoints") or {}).items():
        query_text = endpoint.get("vqlQuery") if isinstance(endpoint, dict) else None
        if query_text:
            if not isinstance(query_text, str) or not query_text.strip():
                raise SystemExit(f"LAPIS custom VQL must be a non-empty Versa command string: {path}:{endpoint_id}")
            sys.path.insert(0, str(Path("liwiro/backend").resolve()))
            from app.vdb_commands import validate_command
            try:
                validate_command(query_text)
            except ValueError as exc:
                raise SystemExit(f"LAPIS custom VQL is invalid Versa syntax: {path}:{endpoint_id}: {exc}") from exc
print("JSON resources, Versa scripts, and native LAPIS VDB commands valid")
action_names = r'(?:create|read|update|delete|drop|list|tumi|model|script|transaction|use|define|find|insert|aggregate|create_collection|drop_collection|drop_domain|drop_db|create_index|drop_index|list_indexes|rebuild_indexes|model_get|model_delete|script_create|script_read|script_execute|script_delete|script_list|transaction_begin|transaction_commit|transaction_abort|domain_status|domain_suspend|domain_resume|help|context|whoami|echo|export)'
legacy = re.compile(r'\{"' + action_names + r'"\s*:')
legacy_js_object = re.compile(r'\breturn\s+\{\s*' + action_names + r'\s*:')
legacy_nested_key = re.compile(r'^\s*"' + action_names + r'"\s*:')
hits = []
frontend_sources = [p for p in Path("liwiro/frontend").rglob("*.jsx") if "node_modules" not in p.parts and ".next" not in p.parts]
for path in [*Path("docs").rglob("*.md"), *Path("verun/vdb/src/main/resources").rglob("*.json"), Path("verun/vdb/src/main/java/verun/vdb/VDBRequestDispatcher.java"), Path("verun/vi/verse-verun-reference/reference.json"), Path("verun/vi/versa-wiki/versa-reference.json"), Path("verun/vi/versa-wiki/build_reference.py"), *frontend_sources]:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if legacy.search(line): hits.append(f"{path}:{number}")
for path in [Path("liwiro/frontend/app/vdb-portal/page.jsx"), Path("liwiro/frontend/components/vdb/vdb-rbac-admin.jsx")]:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if legacy_js_object.search(line): hits.append(f"{path}:{number}")
generator_path = Path("liwiro/backend/generators/api_generator.py")
for number, line in enumerate(generator_path.read_text(encoding="utf-8").splitlines(), 1):
    if re.search(r'merged\s*\[\s*["\x27](?:create|read|update|delete|drop|list|tumi|transaction)["\x27]\s*\]', line):
        hits.append(f"{generator_path}:{number}")
for path in [*Path("docs/verun/vdb").glob("*.md"), Path("docs/verun/versa/vdb-scripts-demo.md"), Path("verun/vdb/SECURITY.md")]:
    if not path.exists():
        continue
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if legacy_nested_key.search(line): hits.append(f"{path}:{number}")
if hits:
    raise SystemExit("Legacy nested VDB examples found: " + ", ".join(hits))
print("Documentation uses flat VDB actions")
PY

echo "Release gate passed."
