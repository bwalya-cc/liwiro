## Authentication & Authorization

### User Management
1. **User Roles**:
   - SUPER_ADMIN: Full system access
   - ADMIN: Manage domains and databases
   - USER: Regular database user

2. **Creating Users**:
```json
{
    "createUser": {
        "username": "john",
        "password": "<PASSWORD_FROM_ENV>",
        "email": "john@example.com",
        "role": "ADMIN",
        "domains": ["domain1"]
    }
}
```

3. **Managing Permissions**:
```json
{
    "updatePermissions": {
        "username": "john",
        "domain": "ecommerce",
        "db": "inventory",
        "permission": "WRITE",
        "grant": true
    }
}
```

### Authentication Flow
1. **Console Authentication**:
```bash
java -cp ... verun.vdb.VDBConsole
Username: admin
Password: *****
```

2. **HTTP Basic Auth**:
```bash
curl -H "Authorization: Basic base64(username:password)" \
     -X POST http://localhost:1957/vdb -H 'Content-Type: text/versa' --data 'read permissions;'
```

3. **Permission Checks**:
- All operations check permissions via:
  ```java
  currentUser.hasPermission(domain, db, operation)
  ```
- Operations are validated against user's role and permissions

### Key Security Features
- BCrypt password hashing
- Role-based access control (RBAC)
- Granular database/domain permissions
- Audit logging via VDBLogger
- Persistent user storage in `__data__/sys/users/`
