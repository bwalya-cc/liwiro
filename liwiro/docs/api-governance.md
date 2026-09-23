# Liwiro API Governance

Liwiro treats a REST API as a living, managed contract. LAPIS is the source of
truth shared by the Service Builder, validation pipeline, generated runtime,
Service Manager, and service documentation. A service is ready when its
contract, runtime, data scope, auth boundary, documentation, and operational
evidence agree.

## Governed lifecycle

1. Author a complete LAPIS document in the Service Builder or upload an
   equivalent `.json`/`.lapis` file.
2. Validate schema, endpoint semantics, model dependencies, and Versa scripts
   before creation. Runtime route testing remains an explicit operator action.
3. Generate the service. Workspace creation is idempotent and creates the
   service domain and declared database together, without a manual VDB setup
   step.
4. Document the running contract through `/liwiro/docs` and
   `/liwiro/docs.json`; notes, examples, setup routes, auth context, and
   endpoint enablement come from LAPIS metadata.
5. Operate through Service Manager: inspect health and logs, test routes,
   manage credentials, edit the contract, restart, stop, or delete services.
6. Audit changes through platform activity and service records. Manager test
   state remains separate from the canonical LAPIS contract.

## Minimum controls

- Give every service a stable API name, base path, version, and database.
- Declare rate limits explicitly, even when disabled.
- Declare whether auth is disabled, provided by this service, or consumed from
  a named auth service; protected endpoints must set `requiresAuth: true`.
- Keep model references valid; CRUD endpoints identify both `linkedModel` and
  `crudOperation`.
- Use native Versa VQL for custom queries and validate every Versa script.
- Provide notes and request/response examples for operator-facing endpoints.
- Treat setup keys, documentation keys, JWT keys, SMTP credentials, and seeded
  passwords as deployment secrets. Example `seedPassword` values are transient
  and are hashed during setup/generation.

## Management surfaces

- `GET /platform/api/governance` exposes this contract as a machine-readable
  manifest for operator consoles, automation, and API clients.
- `POST /generate` validates and creates a service from LAPIS.
- `GET /services` lists managed services and runtime state.
- Service Manager actions start, stop, restart, update, test, and delete
  services with permission checks and optional data deletion.
- `/platform/lapis/validate` provides deterministic feedback for custom files
  and builder drafts. Canonical examples are kept valid without automatic
  rewriting.
- Generated services expose authenticated `/liwiro/docs` and
  `/liwiro/docs.json` when documentation is enabled.

Together, creation, execution, documentation, policy, testing, and lifecycle
management form one REST API automation platform.

## Acceptance evidence

Schema validation establishes that the bundled contracts need no static repairs.
Generator tests with mocked VDB clients check
route construction and request handling; they do not establish live database,
authentication, or process-management correctness.

Release acceptance also requires a runtime with the backend dependencies
installed and permission to bind local sockets. Verify auth-service setup,
sign-in, protected requests, revocation, and service creation, update, stop,
start, and deletion against real VDB persistence. Exercise authenticated consumer
examples after creating AuthCoreService. Record external-integration skips
separately when SMTP or media-provider credentials are unavailable.

A suite run with dependency stubs or skipped socket tests is partial evidence
and must not be reported as end-to-end acceptance.
