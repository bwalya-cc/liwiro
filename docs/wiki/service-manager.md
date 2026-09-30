# Manage and Edit a Service

Use the structured editor to change endpoint method, path, operation type, auth requirement, script, and example request data.

## Save endpoint edits

Choose **Save Service Configuration + Restart** after making changes. Liwiro validates the complete LAPIS configuration, stores it, restarts the service, and opens the restarted service record. Continue editing and testing from the reopened service.

If validation fails, no restart is performed. Fix the named endpoint or model relationship and save again.

## Test routes

Use the Request panel for a saved route. Provide JSON request data and, for protected routes, authenticate first or paste a bearer token. Test results show the HTTP status and response body.

## Inspect a service

Select a service you have permission to manage. Review runtime status, base path, assigned port, logs, documentation, models, routes, and authentication settings. Start or stop it from the management controls. After a restart, use the reopened service entry rather than an old process URL.

## Configuration and test inputs

Use the structured panels for metadata, environment, documentation, auth, models, endpoints, and modules. Use raw LAPIS for a complete configuration edit. Route-test inputs are separate workspace state: saving a test request does not change the service contract.

## Protected routes

Configure and run the selected authenticator service. Authenticate using its sign-in endpoint, then use the captured token for protected route tests. Liwiro workspace login is not a service bearer token. A 401 means missing or invalid authentication; a 403 indicates an access restriction after authentication.

## Delete a service

Review the delete dialog's data-cleanup choice. Removing the managed runtime and removing its database data are separate decisions. Check dependent services before deleting an authenticator or shared data source.

See [service management and governance](../liwiro/service-management-and-governance.md) for change-impact checks, readiness scoring, error semantics, and release validation.
