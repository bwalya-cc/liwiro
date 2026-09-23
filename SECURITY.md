# Security policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability or exposed credential. Contact the project maintainers through the private channel published by the project before disclosure, and include enough detail to reproduce the issue safely.

## Handling secrets

Use the committed `*.example` files only as templates. Store real credentials in ignored local environment files or in your deployment secret manager. If a credential is exposed, revoke and rotate it immediately; deleting it from Git does not make it safe to reuse.

## Scope

Generated runtime data, local databases, private keys, certificates, and local credential files must not be committed.
