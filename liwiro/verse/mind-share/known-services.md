# Known Services

> Record stable service-level knowledge as it becomes available.

## Entry Template

### [Service Name]
- Purpose:
- Owner:
- Key Interfaces:
- Dependencies:
- Data Owned:
- Notes:

### 2026-03-31T05:47:27.045685+00:00 | Kalulu | Text | High confidence
Basis: User initiated inventory management script design.
Thread: 4251f90f10784878a2d3ff4fff1a345d
Content Type: text
Content:
### Inventory Manager (Scripted)
- Type: Versa Script / VDB Integration
- Status: Drafted
- Data Store: VDB `inventory` collection (schema-aware)
- Primary Key: `sku`

### 2026-03-31T08:24:13.329231+00:00 | Kalulu | Text | High confidence
Basis: Defining the HR Check-in service boundary.
Thread: b691dc1a86484887b803d7ab7b96c695
Content Type: text
Content:
### HR Check-in Service (CLI/Scripted)
- Purpose: Track employee check-in and check-out events.
- Owner: HR / Operations
- Key Interfaces: Versa CLI, VDB `staff_logs` collection.
- Data Owned: Employee activity logs.
- Notes: Initial implementation is a Versa script; LAPIS draft prepared for API promotion.

### 2026-03-31T09:57:34.311980+00:00 | Kalulu | Text | High confidence
Basis: Defining the Identity Service boundary.
Thread: 414d4ed3e9e64fc69e645894458f59ea
Content Type: text
Content:
### Identity Service (Draft)
- Purpose: Manage user registration, authentication, and role assignment.
- Owner: Security/IAM
- Data Owned: `users` collection in `iam` domain.
- Notes: Supports bootstrap super-admin logic.

### 2026-03-31T13:08:34.582819+00:00 | Kalulu | Text | High confidence
Basis: Updated HR Check-in service with authentication logic.
Thread: 08b0b4b395ef406cb29cd6d6f0d31243
Content Type: text
Content:
### HR Check-in Service (Authenticated)
- Purpose: Track employee check-in and check-out events with VDB authentication.
- Owner: HR / Operations
- Key Interfaces: Versa CLI, VDB `staff_logs` and `users` collections.
- Data Owned: Employee activity logs, user profiles.
- Notes: Uses `env.VDB_USER` and `env.VDB_PASS` for secure VDB access.
