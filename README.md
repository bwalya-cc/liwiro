# Liwiro

Liwiro is a local-first platform for designing, running, and managing services. Build APIs, manage their data with VDB, run Versa scripts, and get help from Verse specialists in one workspace.

## Quick start

Prerequisites: Python 3, Node.js, and the tools required by the Verun runtime. Copy the environment templates below and configure them for your local setup.

```bash
cp liwiro/.env.example liwiro/.env.local
cp liwiro/backend/.env.example liwiro/backend/.env.local
cp liwiro/frontend/.env.example liwiro/frontend/.env.local
./liwiro/scripts/start_all.sh
```

Set API keys, passwords, and service credentials only in the copied local files. Do not put real credentials in an example file, script, test fixture, or commit.

The launcher starts Liwiro and its local runtimes. Open the frontend address shown in the startup output to set up your account. If a default port is busy, the launcher uses the next available local port.

## Security and local data

- `.env*` files are ignored except committed `*.example` templates.
- Certificates, private keys, credential files, databases, logs, generated runtime data, and Verse conversation state are ignored.
- Keep production secrets in an external secret manager or deployment environment, not in this repository.
- Report suspected vulnerabilities privately; see [SECURITY.md](SECURITY.md).

If a secret was ever committed to another clone or remote, revoke and rotate it before publishing. Removing it from the working tree does not invalidate an exposed credential.

## Documentation

- [Documentation map](docs/README.md)
- [Liwiro guide](docs/liwiro/README.md)
- [Command cheatsheet](docs/reference/command-cheatsheet.md)
- [License](LICENSE)
