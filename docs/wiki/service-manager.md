# Manage and Edit a Service

Use the structured editor to change endpoint method, path, operation type, auth requirement, script, and example request data.

## Save endpoint edits

Choose **Save Service Configuration + Restart** after making changes. Liwiro validates the complete LAPIS configuration, stores it, restarts the service, and opens the restarted service record. Continue editing and testing from the reopened service.

If validation fails, no restart is performed. Fix the named endpoint or model relationship and save again.

## Test routes

Use the Request panel for a saved route. Provide JSON request data and, for protected routes, authenticate first or paste a bearer token. Test results show the HTTP status and response body.
