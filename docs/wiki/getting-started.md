# Getting Started

Liwiro brings service design, runtime management, VDB data, Versa scripting, and Verse specialists into one workspace.

## Start Liwiro

Install Python 3.11 or later, Node.js with npm, and the Java/Maven tools required to build Verun. Run the following commands from the repository root for a fresh setup:

```bash
cp liwiro/.env.example liwiro/.env.local
cp liwiro/backend/.env.example liwiro/backend/.env.local
cp liwiro/frontend/.env.example liwiro/frontend/.env.local
./liwiro/scripts/start_all.sh
```

Copy templates only when you have not already configured those local files. Fill in credentials locally and keep them out of source control. The launcher starts the local components and prints their addresses. Use those addresses: busy default ports can cause it to select another available port.

## First sign-in

Open the frontend and complete setup. First-time setup requires a Liwiro super-admin account and a VDB application account. Liwiro prepares its system metadata workspace in the `liwiro` domain and `config` database. Keep VDB credentials distinct from the password you use to access the Liwiro workspace.

After signing in, check the database connection and runtime status. Resolve connection errors before creating services that depend on VDB. See [settings and access](../liwiro/settings-and-access.md) for account and connection guidance.

## Create your first service

1. Open **Service Builder**.
2. Load `liwiro/data/lapis-examples/14-create-service-e2e-noauth.json` for a basic service with CRUD, custom VQL, and script routes.
3. Review the API name, base path, database, models, and endpoints.
4. Validate the definition and fix any reported errors.
5. Generate the service and open it in **Service Manager**.
6. Confirm it is running, then test a route using its example request.
7. Open its generated API docs when documentation is enabled.

Use a unique API name and available base path when creating another service. For protected endpoints, create the authenticator first and then configure dependent services. See [service authentication](authentication.md) and [the example catalog](../integration/lapis-examples.md).

## Choose the right tool

- **Service Builder** creates and validates LAPIS service definitions.
- **Service Manager** edits configuration, starts and stops services, and tests endpoints.
- **VI Portal** edits and runs standalone `.versa` files and manages custom modules.
- **VDB Portal** queries data and manages database workspaces and access.
- **Verse Chat** provides specialist help and reviewable proposed actions.
- **Ananse** explores service health and platform observations.
- **AI Setup** configures providers, models, and shared usage level.
- **Settings** manages platform configuration, accounts, and Verse collaboration.

## Keep authentication layers separate

Liwiro login controls the management workspace. Service bearer tokens control protected generated-service routes. VDB credentials control database access. A successful login in one layer does not automatically authenticate another.

## When something fails

Check the displayed error and the affected component first. For service errors, inspect status and logs in Service Manager. For database failures, verify VDB transport, credentials, and context. For script failures, validate Versa syntax and confirm module imports. For provider failures, use the connection test in AI Setup.

The [command cheatsheet](../reference/command-cheatsheet.md) and [CLI guide](../integration/liwiro-cli.md) cover terminal workflows.
