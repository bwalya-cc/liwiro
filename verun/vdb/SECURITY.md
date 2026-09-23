# VDB Security Model

VDB uses authenticated RBAC with domain ownership.

## User Types and Role Levels

- `SUPER_ADMIN` (level `100`)
- `ADMIN` (level `70`)
- `APPLICATION` (level `40`)

Only one super admin is allowed. It is created during first-time console setup.

## Authentication

- Console: interactive login required.
- HTTP server: `/auth` issues session; `/vdb` requires a valid session (`/vql` is a deprecated alias).
- Versa: `vdb.auth({user: "...", pass: "..."})` is required before VDB operations.

## Authorization Rules

- `SUPER_ADMIN`: full access everywhere.
- Domain owner: full access within owned domains.
- `ADMIN` and `APPLICATION`: scoped by ownership and explicit permissions.
- `default/main` can be reserved for super-admin ownership and system operations.

## TUMI User Management

TUMI is super-admin only.

Example user creation:

```versa
create user app_user = {
  password: "StrongPass0!",
  email: "app@example.com",
  role: "APPLICATION",
  domains: ["liwiro"]
};
```

Allowed roles for new users via TUMI:

- `ADMIN`
- `APPLICATION`

`SUPER_ADMIN` cannot be created again through TUMI.
