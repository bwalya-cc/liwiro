# Command Cheatsheet

Last updated: 2026-03-11

This page is the practical operator/developer quick reference for the full stack.

## 1. Build the Java artifacts

```bash
cd verun
./scripts/compile_all.sh
```

Builds the Verun jars used by VDB and VI.

## 2. Start the normal local stack

```bash
./liwiro/scripts/start_all.sh
```

This starts:

- platform-correct VDB local transport
- Liwiro backend on `127.0.0.1:5000`
- Liwiro frontend on `127.0.0.1:3000`

It also health-checks the stack before reporting readiness.

Platform behavior:

- Windows uses named-pipe-compatible startup and keeps local VDB HTTP available for that transport
- Linux and macOS use the Unix socket interface by default
- terminal choice does not affect host detection

Runtime behavior:

- successful host detection is cached in `tmp/platform-runtime.json`
- successful Python discovery is cached in `tmp/runtime-tools.json`
- if `1957`, `5000`, or `3000` are already busy, the launcher chooses the next free local port automatically and prints the resolved URLs

## 3. Start VDB directly

## 3.1 Console

```bash
cd verun/vdb
./scripts/convo.sh
```

## 3.2 HTTP server

```bash
cd verun/vdb
./scripts/serve.sh
```

## 3.3 Unix socket server

```bash
cd verun/vdb
./scripts/socket.sh
```

To override the socket path:

```bash
VDB_UNIX_SOCKET_PATH=/tmp/vdb.sock ./scripts/socket.sh
```

## 4. Start Liwiro pieces directly

## 4.1 Backend

```bash
cd liwiro/backend
./scripts/backend-start.sh
```

This is the local development launcher and currently uses `flask run`. For production deployment, use a production WSGI server behind a reverse proxy instead.

## 4.2 Frontend

```bash
cd liwiro/frontend
npm run dev -- --hostname 127.0.0.1 --port 3000
```

## 4.3 Frontend production build

```bash
cd liwiro/frontend
npm run build
```

## 5. Liwiro CLI

Start the headless management CLI:

```bash
./liwiro.sh --help
```

Common commands:

```bash
./liwiro.sh auth status
./liwiro.sh auth login --username zulan
./liwiro.sh services list
./liwiro.sh settings set productionMode=on
./liwiro.sh services download-auth-keys 295465 --out-dir ./auth-material
```

## 6. VI commands

## 6.1 Run a Versa file

```bash
cd verun
./vi/scripts/run_file.sh <demo_or_path>
```

## 6.2 Start the Versa REPL

```bash
cd verun
./vi/scripts/run_repl.sh
```

## 7. VDB HTTP auth and query

Authenticate:

```bash
curl -X POST http://127.0.0.1:1957/auth --user username:password
```

Submit a VQL command:

```bash
curl -X POST http://127.0.0.1:1957/vql \
  -H 'X-Session-Id: <SESSION_ID>' \
  -d 'context;'
```

## 8. Common VQL

```json
context;
whoami;
read domains;
read collections;
status domain engineering;
suspend domain engineering;
resume domain engineering;
help users;
help export;
```

## 9. Common export VQL

```json
export domain engineering to "/tmp/vdb-exports" as "nightly-backup";
```

## 10. Common Versa -> VDB usage

```versa
vdb.auth({user: DEMO_VDB_USER, pass: DEMO_VDB_PASS});
vdb.set({domain: DEMO_VDB_DOMAIN, database: DEMO_VDB_DB});
let c = vdb.collection("products");
let r = c.find({}, 10);
print(r);
```

## 11. Useful Liwiro backend routes

Health/auth:

```bash
curl -sS http://127.0.0.1:5000/auth/status
curl -sS http://127.0.0.1:5000/auth/me
```

Service fleet:

```bash
curl -sS http://127.0.0.1:5000/services
```

VDB portal connection:

```bash
curl -sS http://127.0.0.1:5000/platform/vdb/connection
```

VI portal connection:

```bash
curl -sS http://127.0.0.1:5000/platform/vi/connection
```

## 12. Local env setup

```bash
cp liwiro/.env.example liwiro/.env.local
cp liwiro/backend/.env.example liwiro/backend/.env.local
cp liwiro/frontend/.env.example liwiro/frontend/.env.local
```

Keep real passwords, API keys, and demo credentials only in local env files or other ignored local files.

## 13. Useful local URLs

- Liwiro frontend:
  - `http://127.0.0.1:3000`
- Liwiro backend:
  - `http://127.0.0.1:5000`
- VDB HTTP server:
  - `http://127.0.0.1:1957`

## 14. Related docs

- `docs/integration/liwiro-platform.md`
- `docs/integration/liwiro-cli.md`
- `docs/verun/vdb/setup-and-operations.md`
- `docs/verun/vdb/vql-reference.md`
- `docs/verun/versa/runtime-cli-repl.md`
