# VI Demo Catalog

Explore Versa with runnable examples of language features, modules, and VDB workflows.

## Structure

- `core/`
  Language and runtime examples: control flow, functions, collections, imports, type operators, exceptions, and syntax.
- `algos/`
  Standalone algorithm demos that exercise loops, recursion, lists, and basic collection work without external modules.
- `crypto/`, `datetime/`, `email/`, `filer/`, `http/`, `json_xml/`, `jwt/`, `random/`, `time/`
  Focused module demos. Each folder has one overview demo plus smaller demos for the individual functions.
- `custom_modules/`
  Custom module registry demos for plain runtime use, service context, and VDB-aware context.
- `types/is_unset/`
  Focused demos for unset bindings and guard-style usage.
- `vdb/`
  VDB examples for auth, context, CRUD, class binding, transactions, scripts, jobs, indexes, security, and production-style workflows.
- `vdb_exceptions/`
  Focused VDB exception-family demos.
- `mediacloud/`
  Media storage demos plus helper/support files.

## Support Files

These files are inputs or helpers, not standalone demos:

- `.env`
- `.env.example`
- `mediacloud/lib/mediacloud_demo_helpers.versa`
- `import_helpers/runner_relative_lib.versa`

`demo/.env` is the single shared config source for VDB, email, and MediaCloud demos. The runners inject those values automatically after top-level imports so individual examples do not duplicate credentials or secret-bearing config.

The default demo runners skip support files automatically.

## Find an Example

| Area | Primary demo | Focused companions |
| --- | --- | --- |
| Core syntax and control flow | `core/vi_language_features.versa` | `core/conditionals.versa`, `core/for_loops.versa`, `core/exceptions.versa`, `core/comprehensions.versa` |
| Functions, lambdas, closures | `core/function.versa` | `core/lambda.versa`, `core/closures.versa`, `core/fact.versa` |
| Collections and built-ins | `core/builtins.versa` | `core/list_and_join_demo.versa`, `core/range_demo.versa`, `core/set_entry_and_floor_div_demo.versa` |
| Operators and type behavior | `core/operators.versa` | `core/type_operator.versa`, `core/type_casting_comprehensive.versa`, `core/string_operators_comprehensive.versa`, `core/types_and_exceptions_demo.versa` |
| Enums and typed symbolic values | `core/enum_type_demo.versa` | `core/type_operator.versa`, `core/types_and_exceptions_demo.versa` |
| Imports and path-relative scripts | `core/module_imports_demo.versa` | `core/module_imports_missing_demo.versa`, `core/relative_path_import_runner_demo.versa` |
| Random/time/datetime | `random/random_basics.versa` | `random/random_lists.versa`, `time/time_module_demo.versa`, `datetime/datetime_module_demo.versa` |
| HTTP / JSON / files | `http/http_demo.versa` | `http/http_module_advanced.versa`, `json_xml/json_xml_module_demo.versa` (full JSON/XML conversion matrix), `filer/file_handling_json_demo.versa`, `filer/file_handling_xml_demo.versa` |
| Crypto / JWT | `crypto/crypto_module_demo.versa` | `crypto/crypto_hash_and_hmac.versa`, `jwt/jwt_module_demo.versa`, `jwt/jwt_sign_verify_demo.versa` |
| VDB core workflow | `vdb/vdb_verify.versa` | `vdb/vdb_crud_users.versa`, `vdb/vdb_transactions.versa`, `vdb/vdb_script_lifecycle.versa`, `vdb/vdb_index_advisor_demo.versa` |
| VDB classes and returned objects | `vdb/vdb_class_oop_core_demo.versa` | `vdb/vdb_class_vdb_crud_demo.versa`, `vdb/vdb_class_schema_validation_demo.versa`, `vdb/vdb_return_objects.versa` |
| VDB security and exceptions | `vdb/vdb_security_and_sandbox.versa` | `vdb_exceptions/vdb_exception_family_demo.versa`, `vdb_exceptions/vdb_auth_exception_demo.versa`, `vdb_exceptions/vdb_not_authenticated_exception_demo.versa` |
| Media storage | `mediacloud/mediacloud_status_demo.versa` | `mediacloud/mediacloud_cloudinary_demo.versa`, `mediacloud/mediacloud_video_management_demo.versa`, `mediacloud/mediacloud_00_cleanup_demo.versa` |

## Compact Demos

- `vdb/vdb_list_and_object_access_variant.versa`
  Try an alternative to the access pattern in `vdb/vdb_list_and_object_access.versa`.
- `core/print.versa`
  Print a literal value in a minimal script.
- `core/leng.versa`
  Try the length builtin in a short example.
- `core/list_indexing.versa`
  Access list items by index in a short loop.
- `core/for_in_demo.versa`
  Iterate over a collection with a for-in loop.
- `core/for_with_index_demo.versa`
  Iterate with an index as well as a value.
- `core/fib_with_for_loop.versa`
  Calculate Fibonacci numbers with a for loop.
- `core/fib_with_while_loop.versa`
  Calculate Fibonacci numbers with a while loop.
- `core/casting_and_string_ops.versa`
  Try type casting and string operators together.
- `random/random_randints_demo.versa`
  Generate random integers in a single call.
- `crypto/crypto_hash_and_hmac.versa`
  Calculate hashes and HMACs.
- `crypto/crypto_encoding_and_uuid.versa`
  Try encoding helpers and UUID generation.
- `time/time_formatting_demo.versa`
  Format time values.

## Generated Artifacts

- `tmp/vi/demo/job_tick.log`
  Created by the VDB job scheduling demo when the stored script runs.

Look under `tmp/` for output produced by the demos.

## Runners

- Run every curated demo:
  `cd verun/vi && ./scripts/run_demo_files.sh`
- Run a single demo by basename or path:
  `cd verun/vi && ./scripts/run_file.sh core/comprehensions.versa`
- Run the curated VDB demos:
  `cd verun/vi && ./scripts/run_db_demos.sh`
- Run the MediaCloud demos:
  `cd verun/vi && ./scripts/run_mediacloud_demos.sh`

The default `run_demo_files.sh` runner executes every demo `.versa` file, skips
only support/generated helpers, and requires working SMTP and Cloudinary test
credentials so external examples are exercised for real. Copy `.env.example`
to `.env` and fill in the secret values. For a local-only pass, explicitly set
`VI_DEMO_ALLOW_MISSING_EXTERNAL=1`; external demos then report their own skips.
Every full-suite run uses a disposable VDB store and work directory and removes
them on exit.
