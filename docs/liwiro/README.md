# Liwiro Guide

Use Liwiro to design, run, and manage services from one workspace.

## Get Started

Follow the [quick start](../../README.md#quick-start), then open the frontend address shown by the launcher. Set up your account and sign in.

- **Service Builder**: define models, authentication, and endpoints, or load a LAPIS example.
- **Service Manager**: start and stop services, edit their configuration, and test routes.
- **VDB Portal**: select a database workspace and run queries or manage access.
- **VI Portal**: write and run Versa files.
- **Verse Chat**: work with specialists on service design, analysis, reliability, and documentation.
- **Settings**: configure the platform and manage users.
- **Wiki**: browse the manual without signing in.

## Guides

- [Service management](service-management-and-governance.md): edit services, test routes, and review the impact of changes.
- [Verse Chat](verse-chat.md): configure providers, choose specialists, and work with shared context.
- [Command-line usage](../integration/liwiro-cli.md): manage Liwiro through `./liwiro.sh`.
- [Command cheatsheet](../reference/command-cheatsheet.md): look up startup and operator commands.
- [Platform integration](../integration/liwiro-platform.md): understand how Liwiro connects to its runtimes.

## Running Locally

Start Liwiro with `./liwiro/scripts/start_all.sh`. The launcher detects your platform and Python installation. If a default frontend, backend, or VDB HTTP port is busy, it uses the next free port.

Keep local credentials in `.env.local` files. Authentication and runtime state are stored under `liwiro/backend/.runtime/`.

## Service API Documentation

Generated services can expose `/liwiro/docs` and `/liwiro/docs.json`. Use those pages for the API reference of a specific service, and these guides for working with Liwiro itself.
