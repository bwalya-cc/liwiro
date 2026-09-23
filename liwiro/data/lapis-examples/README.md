# LAPIS Examples (Comprehensive)

This folder provides 15 service LAPIS examples for Liwiro feature coverage and integration testing.

See [API governance](../../docs/api-governance.md) for the shared authoring,
validation, documentation, and service-management contract.

1. `01-auth-core-service.json`
- Dedicated authentication service (`isAuthService: true`) with real VDB-backed signup/signin, super-admin-only register route, forgot-password email route, and auth user model.

2. `02-inventory-service-auth-consumer.json`
- Auth-consuming service (shared `AuthCoreService` HS256 demo secret), CRUD + custom VQL + script endpoint.

3. `03-orders-service-rbac.json`
- Order lifecycle CRUD with protected endpoints and workflow script/custom routes.

4. `04-public-catalog-service.json`
- Public-facing service with auth disabled, high rate-limit, and custom read query.

5. `05-events-webhook-script-service.json`
- Script-heavy event pipeline service (ingest/transform/dispatch/replay).

6. `06-analytics-custom-vql-service.json`
- Metrics service with custom VQL query endpoints plus scripted enrichment.

7. `07-crm-multitenant-service.json`
- Multi-tenant CRM example with tenant/contact models and tenant-scoped query route.

8. `08-file-metadata-deep-object-service.json`
- Deep nested object schemas + object templates for semi-structured metadata.

9. `09-notification-service-auth-consumer.json`
- Notification service consuming external auth with queued send script behavior.

10. `10-workflow-orchestrator-service.json`
- Modular workflow service with multiple script endpoints representing chained steps.

11. `11-iot-telemetry-service.json`
- High-ingest telemetry service with anomaly custom query + rollup script endpoint.

12. `12-kitchen-sink-platform-e2e.json`
- End-to-end all-features config covering CRUD, script, custom VQL, auth, nested objects.

13. `13-contact-form-email-service.json`
- Contact form service with `POST /contact` script endpoint using the VI `email` module and strict `service.env.*` SMTP validation.

14. `14-create-service-e2e-noauth.json`
- Live E2E-focused no-auth service that exercises CRUD + custom VQL + script endpoint flows for automated create-service verification.

15. `15-media-storage-bridge-service.json`
- Media storage bridge service with Versa-script upload routes for Cloudinary. Generation and provider-status checks work without credentials; set the optional `CLOUDINARY_*` values only when sending a real upload.

## Notes
- All files are schema-compatible with current backend validation.
- `requiresAuth` is set on protected endpoints to drive auth/rbac-focused test scenarios.
- Auth-consuming examples use `authServiceName: "AuthCoreService"` and automatic demo key resolution, so they generate and run together without copying a public-key placeholder between files. Production deployments should replace the demo JWT secret through their runtime configuration.
- Operation coverage is already present across the catalog, so no additional example files were required for builder/manager support:
  - full CRUD examples: `02-inventory-service-auth-consumer.json`, `03-orders-service-rbac.json`, `07-crm-multitenant-service.json`, `12-kitchen-sink-platform-e2e.json`, `14-create-service-e2e-noauth.json`
  - custom VQL examples: `02-inventory-service-auth-consumer.json`, `03-orders-service-rbac.json`, `06-analytics-custom-vql-service.json`, `12-kitchen-sink-platform-e2e.json`, `14-create-service-e2e-noauth.json`
  - Versa script examples: `01-auth-core-service.json`, `05-events-webhook-script-service.json`, `10-workflow-orchestrator-service.json`, `13-contact-form-email-service.json`, `15-media-storage-bridge-service.json`
  - combined CRUD + custom VQL + script examples: `02-inventory-service-auth-consumer.json`, `03-orders-service-rbac.json`, `12-kitchen-sink-platform-e2e.json`, `14-create-service-e2e-noauth.json`
- Every example now includes:
  - `metadata.documentation.enabled` for docs visibility
  - `metadata.documentation.key` default value (`liwiroservicepass0!`) for per-service docs auth
  - optional `metadata.env` for per-service script environment values (available in scripts as `service.env.*`)
  - `metadata.developerNotes` for docs/help annotations
  - `metadata.setupApiKey` shared key for setup routes
  - `metadata.seedData` for default collection seed payloads
  - Auth seed records may use `seedPassword`; it is hashed during service generation and is never persisted as plaintext.
  - endpoint-level `developerNotes`
  - endpoint-level `exampleParams` for docs auto-fill testing
  - `auth.defaultSuperAdmin` bootstrap configuration (enabled by default for auth-service examples)
