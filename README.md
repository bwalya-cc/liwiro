# Liwiro

Liwiro is a local-first platform for designing, running, and managing services. This monorepo includes the Liwiro application and the Verun runtime components it uses.

## Quick start

Prerequisites: Python 3, Node.js, and the tools required by the Verun runtime. Copy only the templates you need; all local environment files are excluded from Git.

```bash
cp liwiro/.env.example liwiro/.env.local
cp liwiro/backend/.env.example liwiro/backend/.env.local
cp liwiro/frontend/.env.example liwiro/frontend/.env.local
./liwiro/scripts/start_all.sh
```

Set API keys, passwords, and service credentials only in the copied local files. Do not put real credentials in an example file, script, test fixture, or commit.

The launcher selects the appropriate host scripts, discovers a Python interpreter, and uses an available local port when the defaults are occupied.

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
