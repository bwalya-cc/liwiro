# VDB Authentication and Authorization

VDB authentication is separate from Liwiro workspace login and generated-service bearer authentication. A VDB session identifies a database user and carries the active domain/database context.

## Sign in through HTTP

Send Basic authentication to `/auth`, then use the returned `sessionId` as `X-Session-Id` on database requests:

```bash
curl -X POST http://127.0.0.1:1957/auth --user username
curl -X POST http://127.0.0.1:1957/vdb \
  -H "X-Session-Id: $VDB_SESSION_ID" \
  -H 'Content-Type: text/versa' \
  --data 'whoami; context;'
```

The first command prompts for the password. Set `VDB_SESSION_ID` to the returned value locally. Replace the default address with the configured VDB address. Do not send Basic credentials directly to `/vdb` as a substitute for the session header.

## Console and scripts

Start the console with `cd verun/vdb && ./scripts/convo.sh` and complete its authentication prompts. In Versa, import `vdb`, authenticate, and select the intended domain and database before data operations. See [the VDB module guide](../versa/vdb-module.md).

## Authorization

Built-in roles include `SUPER_ADMIN`, `ADMIN`, and `APPLICATION`. Domain ownership and scoped permissions determine which data a user can access. `READ`, `WRITE`, and `DATA_ACCESS` are common permission values; their scope may include a domain, database, or collection.

Use [TUMI and RBAC](tumi-rbac.md) for current commands. Old `createUser` and `updatePermissions` JSON envelopes are not accepted by the native command endpoint.

## Credential storage and troubleshooting

VDB stores user records in its BSON-backed system data under `verun/vdb/__data__/sys/`. Password handling uses BCrypt. Treat this directory as sensitive application data.

- Missing or expired session: authenticate again and use the new session ID.
- Wrong context: run `context;`, then select the intended domain/database.
- Permission denied: review the user's role, ownership, and scope grants.
- Service auth failure: determine whether it is a VDB account failure or a generated-service bearer-token failure before changing credentials.
