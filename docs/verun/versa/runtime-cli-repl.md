# VI Runtime, CLI, and REPL

Last updated: 2026-03-11

This page covers how the Versa runtime is launched and how its file and REPL modes behave in both direct and Liwiro-managed workflows.

## 1. Entry points

Main Java entry:

- `verun.runtime.Main`

Shell helpers:

- `verun/vi/scripts/run_file.sh`
- `verun/vi/scripts/run_demo_files.sh`
- `verun/vi/scripts/run_repl.sh`

## 2. CLI flags

The runtime currently recognizes flags such as:

- `--log`
  - enables runtime logging
- `--all`
  - enables verbose success logging for completed runs
- `--msg-only`
  - keeps error output concise in common cases

These flags are used by the helper scripts so runtime feedback is more readable in local development.

## 3. File execution flow

File mode behaves roughly like this:

1. resolve the target file
2. verify extension and path
3. read source text
4. lex and parse source
5. evaluate the program
6. return process output and exit

### Helper usage

```bash
cd verun
./vi/scripts/run_file.sh <demo_or_path>
```

The helper can accept:

- a direct file path
- a demo basename
- a demo filename without the `.versa` suffix

## 4. Demo helper injection behavior

`run_file.sh` contains repo-specific convenience behavior for bundled demos.

## 4.1 VDB demos

For VDB demo categories, the helper prepends:

- shared demo settings generated from `verun/vi/demo/.env`

This keeps demo auth/config in one place instead of duplicating credentials across each file.

## 4.2 Email demos

For email demo categories, the helper prepends:

- the same shared demo settings generated from `verun/vi/demo/.env`

The same prelude is also used for MediaCloud demos, so bundled examples no longer carry secret-bearing `.versa` config files.

## 5. Error reporting

When parsing or runtime evaluation fails, the runtime attempts to report:

- a human-readable message
- line and column context when available
- source-line pointers for common parser/runtime errors

That makes direct CLI usage and portal-driven file execution much easier to debug.

## 6. REPL behavior

The REPL is a persistent evaluator session.

Prompt conventions:

- primary prompt:
  - `> `
- continuation prompt:
  - `... `

### Chunk completion rules

The REPL waits for a complete chunk before evaluation. Important completeness signals include:

- balanced braces
- statement termination with `;`
- closed blocks ending with `}`

### Exit behavior

- `exit` at an empty prompt quits the REPL

### Evaluation behavior

- environment state persists across inputs
- results are not wrapped in a synthetic `Result:` label by default

## 7. Direct REPL usage

Start it with:

```bash
cd verun
./vi/scripts/run_repl.sh
```

This ensures the built jar exists and then executes the Java runtime directly.

## 8. Liwiro VI portal behavior

The Liwiro VI portal uses the same underlying runtime, but wraps it with browser tooling.

The portal provides:

- editable source files
- directory selection for the source root
- file execution through the built jar
- a real terminal-style REPL console

## 8.1 Real REPL process

The portal REPL is not only a fake frontend console.

The backend maintains a real persistent REPL process per session and:

- writes submitted input to stdin
- reads stdout/stderr
- returns output to the browser

The browser renders a terminal-style transcript on top of that real process.

## 8.2 Input behavior in the portal

The current portal UI is designed to mimic a terminal workflow:

- input lives inside the console surface
- submitted input is echoed into the transcript
- output appears underneath
- `Ctrl+Enter` supports multiline authoring
- toggling REPL mode exits the session and clears the console state

## 8.3 VDB access in REPL

The portal does not auto-authenticate VDB inside the REPL.

If you want script-side VDB operations, authenticate explicitly:

```versa
vdb.auth({user: DEMO_VDB_USER, pass: DEMO_VDB_PASS});
vdb.set({domain: DEMO_VDB_DOMAIN, database: DEMO_VDB_DB});
```

When using the bundled demo runners, those `DEMO_VDB_*` values come from `verun/vi/demo/.env`.

## 9. Logging notes

Interpreter logging flags are runtime-level controls.

For VDB-side logs inside scripts, use VDB bridge config such as:

```versa
vdb.config({logging: true});
```

or:

```versa
vdb.config({logs: true});
```

## 10. Related docs

- `docs/verun/versa/README.md`
- `docs/verun/versa/syntax.md`
- `docs/verun/versa/modules.md`
- `docs/verun/versa/vdb-module.md`
- `docs/integration/liwiro-platform.md`
