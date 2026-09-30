# Settings and Access

Use **Settings** to configure Liwiro, manage users, and adjust Verse collaboration. Available controls depend on your account permissions.

## Platform and service access

A Liwiro session controls access to the workspace and management operations. It is separate from generated-service bearer tokens and VDB credentials.

Super admins can manage user accounts, roles, platform permissions, and service access in **User Accounts & Roles**. Review both platform permissions and the services assigned to a user: access to a page does not imply access to every service.

For protected generated-service routes, configure an authenticator in the service definition and obtain a service bearer token. For direct VDB operations, use the VDB account and selected domain/database context.

## VDB connection

Review the selected transport and connection status. IPC uses a Unix socket on Unix-like systems and a named pipe on Windows. HTTP uses the configured local VDB server address. Enter account credentials appropriate to the selected VDB instance; leave a saved password field blank when its label says to keep the current password.

If a connection fails, verify the runtime is running, the address or IPC path is correct, and the account can access the intended workspace. Do not reset application data to resolve an ordinary connection error.

## Verse settings

Configure collaboration, proactive reviews, and specialist activity in the Verse section. More collaboration or more frequent activity can create additional provider requests. Configure provider models and the shared reasoning usage level separately in [AI Setup](ai-setup.md).

## Account changes

Use clear role and service assignments. After changing access, verify the affected user can perform the intended task and cannot access services outside their assignment. A role change in Liwiro does not automatically redefine every generated service's authentication policy.
