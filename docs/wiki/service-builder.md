# Build a Service

Service Builder creates a LAPIS definition. A valid definition has metadata, models when needed, and endpoints.

## Required metadata

Provide a unique API name, a base path beginning with `/`, a semantic version such as `1.0.0`, and a database name.

## Endpoint types

- **CRUD** endpoints need a linked model and create, read, update, or delete operation.
- **Custom** endpoints use a readable VDB command in `vqlQuery`.
- **Script** endpoints use a complete Versa script in `versaScript`.

Set **Requires Auth** only after selecting an authenticator. Liwiro checks for missing or invalid settings before creating the service.
