# Build a Service

Service Builder creates a LAPIS definition. A valid definition has metadata, models when needed, and endpoints.

## Required metadata

Provide a unique API name, a base path beginning with `/`, a semantic version such as `1.0.0`, and a database name.

## Endpoint types

- **CRUD** endpoints need a linked model and create, read, update, or delete operation.
- **Custom** endpoints use a readable VDB command in `vqlQuery`.
- **Script** endpoints use a complete Versa script in `versaScript`.

Set **Requires Auth** only after selecting an authenticator. Liwiro checks for missing or invalid settings before creating the service.

## Build or import a definition

Start with the structured form or upload a complete LAPIS JSON file. The [example catalog](../integration/lapis-examples.md) covers authentication, inventory, orders, nested models, email, and media storage. Review an imported example before generation, especially credentials, seed users, database names, and public routes.

## Models and request data

Define the model's collection and fields before linking CRUD endpoints. Keep each endpoint's linked model aligned when renaming or removing models. Configure query/body parameters and example requests so that route tests and generated docs show callers what to send.

For custom endpoints, put native VDB command text in `vqlQuery`. For script endpoints, import modules before executable code and read service-specific values from `service.env`. Do not assume a service script has the same inputs as an interactive VI file.

## Environment and documentation

Use metadata environment settings for service-specific configuration. Media presets add provider settings and upload routes; fill in actual provider values locally before live uploads. Configure documentation visibility and its access key, and write endpoint notes that explain behavior and required inputs.

## Validate and generate

Validate the complete definition. Fix schema, linked-model, authentication, and Versa syntax errors before generating. A valid definition can still fail at runtime because of unavailable credentials, permissions, external providers, or ports. Inspect the generated service and test representative requests in Service Manager.

For the lifecycle and release checks, see [service management](../liwiro/service-management-and-governance.md).
