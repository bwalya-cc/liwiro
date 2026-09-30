# TUMI and RBAC

TUMI manages VDB users, roles, ownership, and scoped permissions. Authenticate before using these commands. Use command text through the console or `/vdb`; TUMI is not a separate JSON endpoint.

## Built-in roles and privileges

Built-in roles are `SUPER_ADMIN`, `ADMIN`, and `APPLICATION`. Super-admin setup is part of initial VDB bootstrap. Ordinary user creation does not create another super admin. User and role administration requires super-admin authority; domain owners can delegate access within their managed domain subject to TUMI checks.

## Create and update users

```text
create user bot = {email: "bot@example.com", password: "<strong-password>", role: "APPLICATION"};
read users;
read user bot;
update user bot = {email: "ops@example.com"};
```

Replace the password placeholder locally. Use `ADMIN` or `APPLICATION` for newly created accounts. Deleting a user is explicit:

```text
delete user bot;
```

## Grant scoped access

```text
grant ["READ", "WRITE"] on engineering.main to bot;
grant ["READ"] on engineering.main.orders to bot;
read permissions for bot;
revoke ["WRITE"] on engineering.main from bot;
```

A scope is `domain`, `domain.database`, or `domain.database.collection`. Check the target before changing it. Broader grants can make a narrower restriction ineffective; inspect all access that applies to the user.

## Domain ownership

```text
grant ownership engineering to bot;
transfer domain engineering to bot;
```

`transfer domain engineering to bot relinquish;` requests relinquishing the caller's ownership in the supported non-super-admin flow. Ownership is broader authority than permission to read a single collection.

## Custom roles

```text
create role report_viewer = {name: "report_viewer", scope: {domain: "engineering", db: "main"}, permissions: ["READ"]};
read roles;
grant role report_viewer to bot;
revoke role report_viewer from bot;
delete role report_viewer;
```

The role definition includes its `name`. Creating a role and assigning it are separate operations. Inspect the role and resulting user permissions before relying on it for service access.

## Inspect access

```text
whoami;
read domains;
read domains with owners;
read owned domains;
read permissions;
```

Results depend on the calling user's authority. A successful login does not imply access to every domain. Liwiro workspace roles and generated-service user roles remain separate from VDB TUMI roles.
