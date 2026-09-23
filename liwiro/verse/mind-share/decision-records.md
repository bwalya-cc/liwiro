# Decision Records

> Record important cross-thread or cross-agent decisions.

## Entry Template

### [Decision Title]
- Date:
- Status:
- Context:
- Decision:
- Rationale:
- Consequences:
- Related Services:
- Related Threads:

### 2026-03-22T22:59:53.209017+00:00 | Nzou | Text | High confidence
Basis: Media storage strategy for zshop
Thread: e8292a89ae5f488e8c6af3035438d95f
Content Type: text
Content:
### ADR-001: Media Storage Strategy for zshop
- **Status**: Proposed
- **Context**: The zshop service requires storage for collection images. Storing files on the application server limits scalability and complicates backups.
- **Options Considered**: Local disk storage, Database BLOBs, External Object Storage (S3-compatible).
- **Decision**: Use External Object Storage with signed URLs for uploads.
- **Consequences**: Reduces backend resource consumption; requires client-side integration for uploads; necessitates robust IAM and CORS policies.

### 2026-03-31T09:57:34.266907+00:00 | Kalulu | Text | High confidence
Basis: User requested a bootstrap mechanism for super admin.
Thread: 414d4ed3e9e64fc69e645894458f59ea
Content Type: text
Content:
### ADR-001: Identity Bootstrap Policy
- **Context**: System requires an initial administrative user without manual DB injection.
- **Decision**: Implement a 'First-Write' rule in the Identity Service. If the `users` collection is empty, the first registered user is assigned the `super_admin` role.
- **Consequences**: Simplifies initial setup; requires strict 'empty check' to prevent race conditions during concurrent first-time registrations.
