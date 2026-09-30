# Service Authentication

Liwiro uses bearer tokens for protected generated-service endpoints. The authenticator owns its users and token endpoints; dependent services verify the tokens it issues.

## Create the authenticator first

Mark one service as **This Service Is Auth Service**. Configure its sign-in and sign-out endpoints in **Authentication Configuration**. The bundled example uses:

- sign in: `POST /api/auth/signin`
- sign out: `POST /api/auth/signout`

Seed or create a user before signing in. A successful sign-in response must include a bearer token in `token`, `accessToken`, `access_token`, or `jwt`.

## Connect a dependent service

For a service with protected routes, enable authentication and select the authenticator by its exact service name. Save the service so Liwiro restarts it with the selected auth configuration. Use the sign-in and sign-out paths configured on the authenticator.

## Test protected routes

In Service Manager, select an auth user, authenticate, and then run a protected endpoint. Liwiro copies the captured bearer token into protected route tests. A missing token returns 401. An invalid or expired token also returns 401.

## Troubleshooting

- **Authenticator not found:** select an existing, running auth service and save the dependent service again.
- **No token returned:** fix the authenticator sign-in script or response.
- **Token verification failed:** make sure both services use the same authenticator configuration and restart the dependent service after saving.
- **401 Bearer token required:** authenticate first, then retry the route.
