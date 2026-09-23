# Service Management and Governance

Liwiro manages a service as a versioned LAPIS contract plus its local runtime,
data scope, authentication boundary, documentation, and operational evidence.
The Service Builder authors the contract; Service Manager operates it.

## Safe service lifecycle

1. Author or upload LAPIS with a stable API name, base path, version, database,
   models, endpoints, and authentication configuration.
2. Validate before generation. Validation checks the LAPIS schema, model and
   endpoint references, and Versa syntax. It is deterministic; it does not
   silently rewrite a contract.
3. Generate the service and confirm its runtime state in Service Manager.
4. Use Route Testing to exercise configured endpoints. Tests are relayed by
   Liwiro to the configured local service, so the browser does not need direct
   cross-origin access. Route results retain the upstream HTTP status.
5. Record examples, developer notes, and operational decisions in LAPIS, then
   save and restart only when the contract change is ready.
6. Stop or delete a service intentionally. Data deletion is a separate choice
   and must be confirmed in the management UI.

## Change control

Before a model is renamed, removed, or its fields are changed, Liwiro checks
CRUD endpoint links and warns when the change affects an existing route. Keep
the endpoint's `linkedModel` aligned with the model name in the same change, or
acknowledge the impact deliberately. Authentication-model removal receives the
same protection because it can break sign-in and protected routes.

Use the raw LAPIS editor only for complete, reviewable changes. The structured
editors are safer for routine model, endpoint, environment, and authentication
updates. Save route-test inputs separately: they are operator workspace state,
not part of the API contract.

## Service readiness score

Every managed service exposes a deterministic `governance` summary in the
Service Manager API and list view. It checks for an API name, base path,
version, enabled documentation, authentication for protected routes, endpoint
summaries, and request examples. The score is an operator triage signal, not a
security certification: a green score means the declared controls are present;
route tests and production review are still required. The summary includes the
first missing control so teams can fix the contract without searching through a
large LAPIS document.

## Error semantics

Generated routes must return meaningful HTTP status codes. For example, a
resource that already exists in VDB must return `409 Conflict`, not `200 OK`.
Use `400` for invalid request data, `401` for missing or invalid credentials,
`403` for an authenticated caller without permission, `404` for absent
resources, and `409` for conflicts. Script routes can set `statusCode`; the
generated runtime also maps failed `created`, `updated`, or `deleted` responses
that report duplicate/conflict errors to `409`.

## Operational evidence

- Service Manager shows runtime state, logs, routes, documentation access, and
  authentication context for services the current user is permitted to see.
- Generated `/liwiro/docs` and `/liwiro/docs.json` describe the running API
  when documentation is enabled. Keep examples free of production secrets.
- Ananse analyzes permission-filtered platform and service observations. Its
  live Service Performance dataset aggregates request volume, errors, error
  rate, average latency, and approximate p95 latency by accessible service.
  Its quality profile flags missing cells and exact duplicate rows before those
  records are used to support operational conclusions.
- `/platform/api/governance` is the machine-readable governance manifest for
  automation and control-plane integrations.

## Release checklist

- Validate the final LAPIS document and review every reported issue.
- Test public, protected, invalid-input, not-found, and duplicate-create paths.
- Confirm auth-service wiring and token acquisition for protected consumers.
- Verify the generated docs match the intended base path, examples, and auth
  requirements.
- Review Ananse’s data-quality warnings before using dashboard conclusions for
  an operational decision.
