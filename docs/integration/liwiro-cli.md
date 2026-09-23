# Liwiro CLI

Last updated: 2026-03-27

`./liwiro.sh` is the terminal-first control plane for Liwiro. It now covers:

- shared platform capability discovery
- authentication and bootstrap
- profiles and backend selection
- platform settings and users
- service generation, update, lifecycle, and auth-key export
- VDB portal connection, queries, export, options, and domain management
- VI portal config, files, execution, and REPL
- VI module catalog, CRUD, and domain assignment
- local stack start, stop, restart, status, and logs

The shell launcher executes `liwiro/cli/liwiro.py`.

Management operations now expect an authenticated Liwiro session. In practice:

- `settings`, `users`, `services`, `vdb`, `vi`, and `modules` require `auth login`
- `local start`, `local stop`, `local restart`, and `local logs` also require `auth login`
- read-only checks like `auth status`, `health check`, `license show`, `profiles ...`, and `local status` remain available before sign-in

When the CLI is targeting the local Liwiro backend at `http://127.0.0.1:*` or `http://localhost:*`, backend-bound commands automatically start the backend in the background if it is not already running, then retry the command once the backend is healthy.

## 0. Interactive shell

The CLI now has a prompt-driven shell for terminal use:

```bash
./liwiro.sh shell
```

If `./liwiro.sh` is run with no subcommand from an interactive terminal, it opens the shell automatically.

Prompt forms:

- root: `liwiro!>`
- area contexts: `liwiro:vdb>`, `liwiro:vi>`, `liwiro:services>`, `liwiro:modules>`, `liwiro:users>`, `liwiro:local>`
- selected service context: `liwiro:[service_name]>`

Core shell commands:

```text
menu
help
help <command>
enter <area>
use service <process_id|apiName>
whereami
back
exit
```

Helpful shell notes:

- `exit`, `quit`, or `Ctrl-D` leaves the shell
- `back` leaves the current service or area context
- `help <command>` shows detailed syntax for the current prompt
- `help --stdin` explains the piped-input pattern used by JSON/source-heavy commands
- before sign-in, the interactive shell keeps the management prompts locked; use `auth` and `profiles` first to complete setup or sign in

The shell now adds ANSI color to prompts, tables, headings, warnings, and errors when running in a terminal. Set `NO_COLOR=1` to disable color, or `LIWIRO_CLI_COLOR=1` to force color in environments that do not report a TTY cleanly.

The direct `--help` output is also more opinionated now. `./liwiro.sh --help`, `./liwiro.sh services generate --help`, `./liwiro.sh vdb query --help`, and similar subcommand help now include example invocations and stdin/editor guidance.

Example flow:

```text
liwiro!> enter services
liwiro:services> list
liwiro:services> use auth-api
liwiro:[auth-api]> show
liwiro:[auth-api]> update --edit
liwiro:[auth-api]> back
liwiro:services> back
liwiro!> exit
```

Examples of contextual help from inside the shell:

```text
liwiro!> help exit
liwiro:services> help generate
liwiro:vdb> help --stdin
```

## 1. State and profiles

The CLI stores state in:

- `~/.liwiro_cli.json`

That file now supports multiple profiles. The active profile tracks:

- backend URL
- frontend auth token
- current Liwiro username
- active VDB portal token

Examples:

```bash
./liwiro.sh profiles list
./liwiro.sh profiles set-backend prod https://example.com
./liwiro.sh profiles use prod
./liwiro.sh --profile staging auth login --username zulan
```

## 2. Authentication and setup

Bootstrap or sign in:

```bash
./liwiro.sh auth status
./liwiro.sh auth vdb-status --attempt-autostart
./liwiro.sh auth login --username zulan
./liwiro.sh auth me
./liwiro.sh auth logout
```

During first bootstrap, `auth login` can still carry the VDB connection fields normally collected by the setup UI:

```bash
./liwiro.sh auth login \
  --username zulan \
  --vdb-transport unixsocket \
  --vdb-unix-socket-path /tmp/vdb.sock \
  --vdb-app-username liwiro
```

## 3. Common CLI patterns

Global JSON mode:

```bash
./liwiro.sh --json services list
```

Most JSON-heavy commands support one of:

- file input
- stdin
- `$EDITOR`

Examples:

```bash
./liwiro.sh services generate ./examples/auth-service.json
cat ./examples/auth-service.json | ./liwiro.sh services generate --stdin
./liwiro.sh services update 295465 --edit
./liwiro.sh vdb query --edit
./liwiro.sh vi files write examples/demo.versa --edit
```

Shared capability discovery:

```bash
./liwiro.sh capabilities list --client cli
./liwiro.sh capabilities list --surface-id vi-portal
./liwiro.sh capabilities show vi.script.draft
```

`--stdin` also works from inside the interactive shell. Run the command first, then paste the payload and press `Ctrl-D` to end stdin for that command:

```text
liwiro:services> generate --stdin
liwiro:vdb> query --stdin
liwiro:[auth-api]> manager-state --stdin
liwiro:vi> repl send --stdin
```

For direct CLI use, the same pattern is fully documented in the subcommand help:

```bash
./liwiro.sh services generate --help
./liwiro.sh services update --help
./liwiro.sh vdb query --help
./liwiro.sh vi files write --help
./liwiro.sh vi repl send --help
```

## 4. Platform settings and users

```bash
./liwiro.sh settings show
./liwiro.sh settings set productionMode=on autoRefreshServiceStatus=off

./liwiro.sh users list
./liwiro.sh users show zulan
./liwiro.sh users create dev1 --role viewer --service-access auth-api
./liwiro.sh users update dev1 --permissions-file ./tmp/perms.json
./liwiro.sh users delete dev1 --yes
```

For complex user payloads, use `--from-file` or `--edit`.

## 5. Services

List and inspect:

```bash
./liwiro.sh services list
./liwiro.sh services list --full
./liwiro.sh services show 295465
```

Generate and update:

```bash
./liwiro.sh services generate ./examples/auth-service.json
./liwiro.sh services generate --edit --no-start
./liwiro.sh services update 295465 ./examples/auth-service.json
./liwiro.sh services update 295465 --edit --manager-state-file ./tmp/manager-state.json
```

Lifecycle and auth material:

```bash
./liwiro.sh services start 295465
./liwiro.sh services stop 295465
./liwiro.sh services delete 295465 --delete-data --yes
./liwiro.sh services download-auth-keys 295465 --out-dir ./auth-material
```

Service lifecycle commands now execute through the shared platform action endpoint with capability ids such as:

- `service.manager.start`
- `service.manager.stop`
- `service.manager.delete`

## 6. VDB portal

Create a portal session first:

```bash
./liwiro.sh vdb connect
./liwiro.sh vdb status
./liwiro.sh vdb whoami
./liwiro.sh vdb context
```

Run queries:

```bash
./liwiro.sh vdb query '{"action":"whoami"}'
./liwiro.sh vdb query ./tmp/query.json
./liwiro.sh vdb query --stdin
./liwiro.sh vdb query --edit
```

Options, export, and domains:

```bash
./liwiro.sh vdb options
./liwiro.sh vdb export --domain default --out-dir /tmp/vdb-exports
./liwiro.sh vdb export --all-domains
./liwiro.sh vdb domains list
./liwiro.sh vdb domains create media --database main
./liwiro.sh vdb disconnect
```

## 7. VI portal

Connection and directories:

```bash
./liwiro.sh vi status
./liwiro.sh vi config get
./liwiro.sh vi config set --source-dir ./liwiro/vi_portal_sources
./liwiro.sh vi dirs list
```

Files and execution:

```bash
./liwiro.sh vi files list
./liwiro.sh vi files read examples/hello.versa
./liwiro.sh vi files write examples/hello.versa --edit
./liwiro.sh vi files move examples/hello.versa examples/hello-renamed.versa
./liwiro.sh vi files delete examples/hello-renamed.versa --yes
./liwiro.sh vi run examples/hello.versa
```

REPL:

```bash
./liwiro.sh vi repl start
./liwiro.sh vi repl send 'print("hello")'
./liwiro.sh vi repl send --edit
./liwiro.sh vi repl stop
```

## 8. VI modules

```bash
./liwiro.sh modules catalog
./liwiro.sh modules list
./liwiro.sh modules show mediacloud
./liwiro.sh modules create my_module --edit
./liwiro.sh modules update my_module --from-file ./tmp/module.json
./liwiro.sh modules assign-domain my_module media portal
./liwiro.sh modules delete my_module --yes
```

`modules create` and `modules update` support both full JSON payload editing and flag-based overrides for:

- `title`
- `description`
- `scope`
- assigned domains
- source
- config schema
- config defaults

## 9. Local operator workflow

The CLI can manage the local Liwiro stack directly:

```bash
./liwiro.sh local status
./liwiro.sh local start all
./liwiro.sh local start backend
./liwiro.sh local start vdb --vdb-transport http
./liwiro.sh local logs all --lines 100
./liwiro.sh local restart frontend
./liwiro.sh local stop all
```

Background starts write logs under:

- `~/.liwiro_cli_runtime/logs`

If VDB MIT acceptance has not been recorded yet, `local start vdb` and `local start all` will prompt for it before backgrounding the process.

## 10. Help

Every command group exposes built-in help, and the shell exposes contextual `help` and `menu`:

```bash
./liwiro.sh --help
./liwiro.sh shell
./liwiro.sh services --help
./liwiro.sh vdb query --help
./liwiro.sh vi files write --help
./liwiro.sh local start --help
```
