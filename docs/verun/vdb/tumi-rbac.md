# TUMI and RBAC

Last updated: 2026-03-01

TUMI is VDB's user/role/permission command namespace. It is not a separate standalone module folder in this repository.

Implementation:

- `verun/vdb/src/main/java/verun/vdb/Tumi.java`

## Role Model

Built-in user roles:

- `SUPER_ADMIN`
- `ADMIN`
- `APPLICATION`

Role levels are defined in `User` and used for authorization hierarchy.

## Ownership and Permission Scopes

RBAC scope model:

- domain ownership
- database-level permissions
- collection-level permissions

Permission strings commonly used:

- `READ`
- `WRITE`
- `DATA_ACCESS`

## Command Families

Top-level TUMI commands:

- `create`
- `delete`
- `grant`
- `revoke`
- `transfer`
- `list`

## Privilege Rules

### SUPER_ADMIN only

- create users/roles
- delete users/roles
- full visibility across domains

### Domain owner or SUPER_ADMIN

- grant/revoke permissions within managed domain
- transfer domain ownership access

## Create User

```text
create user username "liwiro" email "liwiro@local.com" password "<strong-password>" role "APP"
```

Constraints:

- cannot create additional `SUPER_ADMIN`
- allowed new roles are `ADMIN` and `APPLICATION`

## Grant Permissions

### Domain ownership grant

```text
grant username "john" domain "hr"
```

### Database scope grant

```text
grant username "john" domain "hr" db "employee_data" permissions ["READ","WRITE"]
```

### Collection scope grant

```text
grant username "john" domain "hr" db "employee_data" collection "payroll" permissions ["READ"]
```

Default permission fallback when omitted for scoped grant/revoke is `DATA_ACCESS`.

## Revoke Permissions

Patterns mirror grant, using `revoke`.

```text
revoke username "john" domain "hr" db "employee_data" collection "payroll" permissions ["READ"]
```

## Transfer Domain Access

```text
transfer username "jane" domain "marketing"
```

Optional `relinquish` behavior is available for non-super-admin transfer flows.

## List Commands

- `read domains`
- `read domains with owners`
- `read users`
- `read roles`
- `read permissions`
- `read permissions username alice`

## Who Can Inspect Permissions

- SUPER_ADMIN: can inspect any user
- Non-super-admin: only own permissions

## TUMI via VI

VI bridge call:

```versa
let res = vdb.tumi("read permissions;");
print(res);
```

Result is wrapped in VI standard VDB response envelope (`ok`, `status`, `operation`, `message`, `data`, `error`, `context`).
