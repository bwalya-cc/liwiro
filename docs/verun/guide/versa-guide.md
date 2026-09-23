# Versa Guided Path

Build Versa fluency through three stages and keep the deeper references handy alongside each checkpoint.

## Overview

- **Stage order:** Beginner ? Intermediate ? Pro
- **Goal:** Make the reference docs actionable by pairing them with concrete tasks, runtime cues, and cross-links.
- **Navigation:** Each section calls out the key reference files to open next.

---

## Stage 1 ? Beginner: setup and first scripts

- **Objective:** Run the Versa REPL, author a tiny script, and understand the literal/syntax surface before modules or runtimes.
- **Checklist:**
  - [ ] `cd verun && ./vi/scripts/run_repl.sh` to open the REPL; see `docs/verun/versa/runtime-cli-repl.md` for command-line options.
  - [ ] Write a one-off script that defines a function and prints a basic object. Reference `docs/verun/versa/syntax.md#literals` for literals and `#statements` for `let`/`return` forms.
  - [ ] Learn the syntax rules that trip new authors over: read `docs/verun/versa/syntax-rules.md#common-mistakes` before scouting more complex constructs.
- **Next steps:** jump from the beginner output to modules?start with the builtin core via `docs/verun/versa/modules.md`.

---

## Stage 2 ? Intermediate: module imports, VDB bridge, and runtime CLI

- **Objective:** Tie Versa scripts into Liwiro flows by leveraging modules, the `vdb` bridge, and REPL/runtime CLI features.
- **Checklist:**
  - [ ] Follow the `modules` overview to understand `import` syntax, naming, and namespaces; open `docs/verun/versa/modules.md` then drill into `docs/verun/versa/modules/README.md` for per-module patterns.
  - [ ] Write a script that imports `vdb`, authenticates (`vdb.auth({user, pass})`), switches domains/databases, and reads a collection?use `docs/verun/versa/vdb-module.md` for API examples.
  - [ ] Run `./vi/scripts/run_file.sh` with the script you just built; consult `docs/verun/versa/runtime-cli-repl.md#cli-flags` for runtime arguments (file mode, `--session`, etc.).
  - [ ] Explore the portal: open `/vi-portal`, authenticate, and inspect the session objects that expose the same `vdb` bridge.
- **Reference links:** `docs/verun/versa/syntax.md#functions` (for helper functions), `docs/verun/versa/vdb-module.md#collection-access` (for CRUD), `docs/verun/versa/runtime-cli-repl.md#run-file`.

---

## Stage 3 ? Pro: runtime extensions, debugging, and service integration

- **Objective:** Understand how Versa scripts power generated services, how to debug advanced module interactions, and when to lean on the canonical reference bundle.
- **Checklist:**
  - [ ] Read `verun/vi/verse-verun-reference/reference.json` for the authoritative implementation-backed model of every keyword, runtime flag, and VDB integration point.
  - [ ] Extend a module or helper script used by a produced service; use `docs/verun/versa/syntax.md#declarations` plus `modules/README` to model exported helpers.
  - [ ] Practice the `vdb` bridge within Versa custom endpoints or job scripts?refer to `docs/verun/versa/vdb-scripts-demo.md` for real-world scenarios.
  - [ ] Use the REPL?s `debug` output (`./vi/scripts/run_repl.sh --debug`) and pair it with `docs/verun/versa/syntax-rules.md#parser-errors` to interpret parser feedback.
- **When to drop back:** Return to `syntax.md` or `syntax-rules.md` whenever you bump into a new language construct; run the CLI help again to see flag changes.

---

## Deep dive references

| Topic | Doc |
| --- | --- |
| Language reference | `docs/verun/versa/syntax.md` |
| Rules and mistakes | `docs/verun/versa/syntax-rules.md` |
| Modules overview | `docs/verun/versa/modules.md` + `modules/README` |
| VDB bridge | `docs/verun/versa/vdb-module.md` |
| Runtime CLI/REPL | `docs/verun/versa/runtime-cli-repl.md` |
| Demos | `docs/verun/versa/vdb-scripts-demo.md` |

Link back to `docs/verun/README.md` for the broader Verun context and VDB guides.
