# Liwiro Documentation

Liwiro is the control plane and operator workspace in this repository.

It owns:

- setup and sign-in
- the workspace shell and navigation
- service authoring and service generation
- service lifecycle management
- VDB Portal and VI Portal access through backend-mediated routes
- settings, platform administration, and public wiki/manual pages

## Read This Section With

- `docs/integration/liwiro-platform.md`
  - backend/frontend responsibilities and how Liwiro sits over Verun
- `docs/integration/liwiro-cli.md`
  - headless control-plane operations through `./liwiro.sh`
- `docs/reference/command-cheatsheet.md`
  - quick startup and operator commands

## Liwiro-Specific Notes

- `docs/liwiro/verse-chat.md`
  - Verse Chat architecture, provider setup, routing, mind-share, and agent rename behavior
- `docs/liwiro/service-management-and-governance.md`
  - safe service lifecycle, route testing, change impact warnings, error semantics, and release evidence

## Local Development

The canonical local launcher is `./liwiro/scripts/start_all.sh`.

That entrypoint now keeps the public command surface stable while routing internally through:

- `liwiro/scripts/unix/`
- `liwiro/scripts/win/`

Runtime behavior to expect:

- host platform is detected from runtime OS signals rather than shell type
- first successful startup writes `tmp/platform-runtime.json`
- first successful Python discovery writes `tmp/runtime-tools.json`
- backend auth/runtime state is written under `liwiro/backend/.runtime/`
- local secrets belong in `.env.local` files and other ignored local runtime files only
- frontend, backend, and local VDB HTTP startup automatically move to the next free port when defaults are busy

## Runtime Docs Boundary

Generated services can expose `/liwiro/docs` and `/liwiro/docs.json` at runtime. Those are service-level API docs, not the repository manuals under `docs/`.
