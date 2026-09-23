export type UserManualEntry = {
  slug: string
  title: string
  summary: string
  category: string
  audience: string
  subsystem: string
  order: number
  gettingStarted?: boolean
  related?: string[]
  tags: string[]
  content: string
}

export const userManual: UserManualEntry[] = [
  {
    slug: "getting-started", title: "Getting Started", category: "Platform", audience: "All users", subsystem: "platform", order: 10, gettingStarted: true,
    summary: "Set up Liwiro, create a service, and test it from one workspace.", tags: ["setup", "services", "overview"], related: ["authentication", "service-builder", "service-manager"],
    content: `# Getting Started

Liwiro manages generated services, Versa files, VDB workspaces, and service documentation.

## First steps

1. Sign in and confirm the VDB runtime is ready.
2. Create an authenticator service if any service will have protected routes.
3. Create a service in Service Builder, then open it in Service Manager.
4. Save edits and let the service restart before testing its routes.

## Choose the right tool

- **Service Builder** creates or validates a LAPIS service definition.
- **Service Manager** edits a running service and tests its endpoints.
- **VI Portal** edits standalone \`.versa\` files.
- **VDB Portal** works directly with VDB data and commands.

The platform login, service bearer tokens, and VDB credentials are separate.`,
  },
  {
    slug: "authentication", title: "Service Authentication", category: "Security", audience: "Service authors and operators", subsystem: "security", order: 20, gettingStarted: true,
    summary: "Connect protected services to an authenticator through its real sign-in and sign-out endpoints.", tags: ["auth", "bearer", "jwt", "services"], related: ["service-builder", "service-manager"],
    content: `# Service Authentication

Liwiro uses bearer tokens for protected generated-service endpoints. The authenticator owns its users and token endpoints; dependent services verify the tokens it issues.

## Create the authenticator first

Mark one service as **This Service Is Auth Service**. Configure its sign-in and sign-out endpoints in **Authentication Configuration**. The bundled example uses:

- sign in: \`POST /api/auth/signin\`
- sign out: \`POST /api/auth/signout\`

Seed or create a user before signing in. A successful sign-in response must include a bearer token in \`token\`, \`accessToken\`, \`access_token\`, or \`jwt\`.

## Connect a dependent service

For a service with protected routes, enable authentication and select the authenticator by its exact service name. Save the service so Liwiro restarts it with the selected auth configuration. Do not configure a made-up proxy path on the dependent service.

## Test protected routes

In Service Manager, select an auth user, authenticate, and then run a protected endpoint. Liwiro copies the captured bearer token into protected route tests. A missing token returns 401. An invalid or expired token also returns 401.

## Troubleshooting

- **Authenticator not found:** select an existing, running auth service and save the dependent service again.
- **No token returned:** fix the authenticator sign-in script or response.
- **Token verification failed:** make sure both services use the same authenticator configuration and restart the dependent service after saving.
- **401 Bearer token required:** authenticate first, then retry the route.
`,
  },
  {
    slug: "service-builder", title: "Build a Service", category: "Services", audience: "Service authors", subsystem: "services", order: 30, gettingStarted: true,
    summary: "Define metadata, models, endpoints, and authentication in LAPIS.", tags: ["lapis", "builder", "endpoints"], related: ["authentication", "service-manager", "endpoint-types"],
    content: `# Build a Service

Service Builder creates a LAPIS definition. A valid definition has metadata, models when needed, and endpoints.

## Required metadata

Provide a unique API name, a base path beginning with \`/\`, a semantic version such as \`1.0.0\`, and a database name.

## Endpoint types

- **CRUD** endpoints need a linked model and create, read, update, or delete operation.
- **Custom** endpoints use a readable VDB command in \`vqlQuery\`.
- **Script** endpoints use a complete Versa script in \`versaScript\`.

Set **Requires Auth** only after selecting an authenticator. Validation blocks incomplete contracts before generation.`,
  },
  {
    slug: "service-manager", title: "Manage and Edit a Service", category: "Services", audience: "Service operators", subsystem: "services", order: 40, gettingStarted: true,
    summary: "Edit endpoint definitions, save them, restart the service, and test the running result.", tags: ["manager", "endpoints", "restart", "testing"], related: ["authentication", "endpoint-types"],
    content: `# Manage and Edit a Service

Use the structured editor to change endpoint method, path, operation type, auth requirement, script, and example request data.

## Save endpoint edits

Choose **Save Service Configuration + Restart** after making changes. Liwiro validates the complete LAPIS configuration, stores it, restarts the service, and opens the restarted service record. The new process ID is used for later edits and tests.

If validation fails, no restart is performed. Fix the named endpoint or model relationship and save again.

## Test routes

Use the Request panel for a saved route. Provide JSON request data and, for protected routes, authenticate first or paste a bearer token. Test results show the HTTP status and response body.
`,
  },
  {
    slug: "endpoint-types", title: "Endpoint Types", category: "Services", audience: "Service authors", subsystem: "services", order: 50,
    summary: "Use the correct endpoint type and required fields for generated services.", tags: ["crud", "vql", "versa", "endpoints"], related: ["service-builder", "service-manager"],
    content: `# Endpoint Types

## CRUD

CRUD endpoints operate on one linked model. Select a CRUD operation and keep the linked model name valid.

## Custom VDB command

Custom endpoints require readable VDB command text. Do not provide a JSON command envelope or SQL.

## Versa script

Script endpoints require complete Versa source. Imports must appear before executable code. Use documented Versa syntax and return a response object. Save the endpoint configuration, then test the restarted service.
`,
  },
  {
    slug: "versa", title: "Versa and VI", category: "VI Runtime", audience: "Developers", subsystem: "vi", order: 60,
    summary: "Write and validate Versa files and service scripts.", tags: ["versa", "vi", "scripts"], related: ["endpoint-types"],
    content: `# Versa and VI

Use VI Portal for standalone \`.versa\` files. Use a script endpoint for service-scoped code. These environments are related but do not have identical runtime inputs.

Versa functions use \`func name(...) { ... }\`; use \`#\` for single-line comments. Validate source before saving. For service scripts, request data is supplied through the service runtime rather than a standalone file prompt.
`,
  },
  {
    slug: "vdb", title: "VDB Workspace", category: "VDB", audience: "Developers and operators", subsystem: "vdb", order: 70,
    summary: "Work with VDB only after authentication and workspace selection.", tags: ["vdb", "vql", "data"], related: ["getting-started"],
    content: `# VDB Workspace

VDB access is separate from Liwiro login and service bearer authentication. Authenticate to VDB, select the required domain and database, then run reads or changes. Confirm the workspace before writes, exports, RBAC changes, or destructive actions.
`,
  },
]
