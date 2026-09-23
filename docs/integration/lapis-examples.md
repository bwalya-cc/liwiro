# LAPIS examples and generation guide

Last updated: 2026-09-10

The canonical example contracts live in `liwiro/data/lapis-examples/`. They are complete LAPIS documents, not fragments. Each file can be uploaded to Service Builder or passed directly to the CLI:

```bash
./liwiro.sh services generate liwiro/data/lapis-examples/14-create-service-e2e-noauth.json
./liwiro.sh services generate liwiro/data/lapis-examples/01-auth-core-service.json
```

## What is guaranteed

Every bundled example is checked for:

- JSON and LAPIS schema validity;
- endpoint semantics, including linked-model references;
- valid flat VDB custom commands;
- valid Versa scripts and generated-service script normalization;
- route documentation and example request payloads;
- generation coverage for CRUD, custom VQL, and Versa-script routes.

Run the focused checks from the repository root:

```bash
liwiro/backend/vvv/bin/python -m unittest \
  liwiro.backend.tests.test_config_schema \
  liwiro.backend.tests.test_api_generator_runtime_and_script
```

## Example catalog

| File | Purpose | Auth | Main coverage |
| --- | --- | --- | --- |
| `01-auth-core-service.json` | First-party authentication service | Own auth service | signup, signin, sessions, reset, RBAC |
| `02-inventory-service-auth-consumer.json` | Inventory API | AuthCoreService consumer | full CRUD, custom VQL, script |
| `03-orders-service-rbac.json` | Order lifecycle | AuthCoreService consumer | CRUD, role checks, workflow |
| `04-public-catalog-service.json` | Public catalog | None | public read and rate limiting |
| `05-events-webhook-script-service.json` | Event pipeline | Local auth | ingest, transform, dispatch |
| `06-analytics-custom-vql-service.json` | Analytics API | AuthCoreService consumer | aggregate/custom VQL and scripts |
| `07-crm-multitenant-service.json` | Tenant-aware CRM | AuthCoreService consumer | tenant-scoped CRUD and queries |
| `08-file-metadata-deep-object-service.json` | Nested metadata | Local auth | object fields and CRUD |
| `09-notification-service-auth-consumer.json` | Notifications | AuthCoreService consumer | queued notification workflow |
| `10-workflow-orchestrator-service.json` | Workflow composition | AuthCoreService consumer | chained script steps |
| `11-iot-telemetry-service.json` | Telemetry | Local auth | ingest, anomaly query, rollup |
| `12-kitchen-sink-platform-e2e.json` | Broad integration fixture | AuthCoreService consumer | CRUD, VQL, scripts, nested data |
| `13-contact-form-email-service.json` | Contact form | None | persistence and optional email |
| `14-create-service-e2e-noauth.json` | Minimal smoke fixture | None | deterministic create-service flow |
| `15-media-storage-bridge-service.json` | Media bridge | None | provider status and optional Cloudinary upload |

## How the examples work together

Use `01-auth-core-service.json` first when testing authenticated consumers. The consumer examples name `AuthCoreService` and use automatic local demo key resolution; no public-key copying or hand-editing is required. For production, provide a real shared JWT secret or explicit key material through the generated service's runtime configuration.

Each generated service receives its own VDB domain/database context and its `metadata.env` values. Script code accesses those values through `service.env.NAME`. Values that are optional integrations are deliberately safe when unset:

- SMTP examples persist the request and return a clear “SMTP not configured” result;
- the media example reports provider readiness and does not require Cloudinary credentials to generate;
- external credentials must never be committed to LAPIS files.

## Authoring rules

- Keep `metadata.apiName`, `metadata.basePath`, and semantic version together.
- Define every CRUD `linkedModel` in `models`.
- Use flat VDB action JSON in `vqlQuery`; do not nest legacy operation keys.
- Give every script endpoint a `versaScript`; imports are normalized by the generator.
- Put request examples in `exampleParams` so Service Manager can replay them.
- Put non-secret integration settings in `metadata.env`; inject secrets at runtime.
- Keep route paths unique per HTTP method.
- Use `keyManagement: "auto"` for local examples unless a real production key is supplied.
- Versa member-access chains such as `str(value).trim()` and `datetime.now().isoformat()` are supported inside script endpoints; the VDB script-block lexer preserves these raw bodies when generated services are stored.

## Generated-service documentation

After generation, each service exposes its own documentation when enabled in `metadata.documentation`:

- `GET /liwiro/docs`
- `GET /liwiro/docs.json`

The repository manuals describe the platform contract; the generated routes describe the concrete service contract. Both are derived from the same LAPIS document.
