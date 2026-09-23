// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.reflect.TypeToken;
import verun.common.JsonValueConverter;

import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.time.Instant;

public class Tumi {
    private static final Path ROLE_DATA_PATH = DirectoryUtil.getRolesStorePath();
    private static final Path ROLE_DIR = ROLE_DATA_PATH.getParent();
    private static final String MANIFEST_ROLE_NAMES_KEY = "role_names";
    private static final Set<String> SYSTEM_ROLES = Set.of("SUPER_ADMIN", "ADMIN", "APPLICATION");
    private static volatile long roleStoreMtime = -1L;
    private static volatile Map<String, Object> cachedRoleStore = new LinkedHashMap<>();
    private static final Map<String, Long> roleRecordMtimes = new LinkedHashMap<>();
    private final User currentUser;
    private final String currentDomain;
    private final String currentDB;
    private final Gson gson = new GsonBuilder()
            .setPrettyPrinting()
            .disableHtmlEscaping()
            .create();

    public Tumi(User user, String domain, String db) {
        this.currentUser = user;
        this.currentDomain = domain;
        this.currentDB = db;
    }

    public String processCommand(JsonObject tumiCmd) {
        if (currentUser == null) {
            return errorResponse("Authentication required");
        }

        if (!tumiCmd.has("create") && !tumiCmd.has("read") && !tumiCmd.has("update")
                && !tumiCmd.has("delete") && !tumiCmd.has("grant")
                && !tumiCmd.has("revoke") && !tumiCmd.has("list") && !tumiCmd.has("transfer")) {
            return errorResponse("Invalid TUMI command structure");
        }

        if (tumiCmd.has("create")) {
            if (!currentUser.isSuperAdmin()) {
                return errorResponse("Permission denied: Only super admin can create users/roles");
            }
            JsonElement createElement = tumiCmd.get("create");
            if (!createElement.isJsonObject()) {
                return errorResponse("Invalid create command structure");
            }
            return processCreateCommand(createElement.getAsJsonObject());
        }

        if (tumiCmd.has("delete")) {
            if (!currentUser.isSuperAdmin()) {
                return errorResponse("Permission denied: Only super admin can delete users/roles");
            }
            JsonElement deleteElement = tumiCmd.get("delete");
            if (!deleteElement.isJsonObject()) {
                return errorResponse("Invalid delete command structure");
            }
            return processDeleteCommand(deleteElement.getAsJsonObject());
        }

        if (tumiCmd.has("read")) {
            if (!currentUser.isSuperAdmin()) {
                return errorResponse("Permission denied: Only super admin can read roles");
            }
            JsonElement readElement = tumiCmd.get("read");
            if (!readElement.isJsonObject()) {
                return errorResponse("Invalid read command structure");
            }
            return processReadCommand(readElement.getAsJsonObject());
        }

        if (tumiCmd.has("update")) {
            if (!currentUser.isSuperAdmin()) {
                return errorResponse("Permission denied: Only super admin can update roles");
            }
            JsonElement updateElement = tumiCmd.get("update");
            if (!updateElement.isJsonObject()) {
                return errorResponse("Invalid update command structure");
            }
            return processUpdateCommand(updateElement.getAsJsonObject());
        }

        if (tumiCmd.has("grant")) {
            JsonElement grantElement = tumiCmd.get("grant");
            if (!grantElement.isJsonObject()) {
                return errorResponse("Invalid grant command structure");
            }
            return processGrantCommand(grantElement.getAsJsonObject());
        }

        if (tumiCmd.has("revoke")) {
            JsonElement revokeElement = tumiCmd.get("revoke");
            if (!revokeElement.isJsonObject()) {
                return errorResponse("Invalid revoke command structure");
            }
            return processRevokeCommand(revokeElement.getAsJsonObject());
        }

        if (tumiCmd.has("transfer")) {
            JsonElement transferElement = tumiCmd.get("transfer");
            if (!transferElement.isJsonObject()) {
                return errorResponse("Invalid transfer command structure");
            }
            return processTransferCommand(transferElement.getAsJsonObject());
        }

        if (tumiCmd.has("list")) {
            JsonElement listElement = tumiCmd.get("list");
            if (listElement.isJsonPrimitive()) {
                return processListCommand(listElement.getAsString());
            } else if (listElement.isJsonObject()) {
                return processListCommand(listElement.getAsJsonObject());
            }
            return errorResponse("Invalid list command structure");
        }

        return errorResponse("Invalid TUMI command");
    }

    private String processCreateCommand(JsonObject createCmd) {
        if (createCmd.has("username")) {
            return createUser(createCmd);
        }
        if (createCmd.has("role")) {
            JsonElement roleElement = createCmd.get("role");
            if (!roleElement.isJsonObject()) {
                return errorResponse("Invalid role creation structure");
            }
            return createRole(roleElement.getAsJsonObject());
        }

        return errorResponse("Invalid create command");
    }

    private String createUser(JsonObject createCmd) {
        try {
            if (!createCmd.has("username") || !createCmd.has("password")
                    || !createCmd.has("email") || !createCmd.has("role")) {
                return errorResponse("Missing required fields for user creation");
            }

            String username = User.normalizeUsername(createCmd.get("username").getAsString());
            String password = createCmd.get("password").getAsString();
            String email = createCmd.get("email").getAsString().trim();
            String role = normalizeCreateUserRole(createCmd.get("role").getAsString());

            if ("SUPER_ADMIN".equals(role)) {
                return errorResponse("Cannot create additional super admin users");
            }
            if (!"ADMIN".equals(role) && !"APPLICATION".equals(role)) {
                return errorResponse("Invalid role. Allowed create roles: ADMIN, APPLICATION (alias: APP). Reserved role: SUPER_ADMIN");
            }
            if (UserManager.getInstance().userExists(username)) {
                return errorResponse("User already exists");
            }

            User newUser = new User(username, email, role, password);

            if (createCmd.has("domains")) {
                JsonArray domains = createCmd.getAsJsonArray("domains");
                for (JsonElement domain : domains) {
                    String d = domain.getAsString().toLowerCase(Locale.ROOT);
                    if (!canManageDomain(d)) {
                        return errorResponse("Permission denied for domain: " + d);
                    }
                    newUser.grantDomainOwnership(d);
                }
            }

            UserManager.getInstance().addUser(newUser);
            return successResponse("User created: " + username);
        } catch (Exception e) {
            return errorResponse("User creation failed: " + e.getMessage());
        }
    }

    private String normalizeCreateUserRole(String rawRole) {
        String role = rawRole == null ? "" : rawRole.trim().toUpperCase(Locale.ROOT);
        if ("APP".equals(role)) {
            return "APPLICATION";
        }
        return role;
    }

    private String createRole(JsonObject roleCmd) {
        try {
            String roleName = normalizeRoleName(roleCmd.has("name") ? roleCmd.get("name").getAsString() : null);
            if (roleName.isEmpty()) {
                return errorResponse("Role creation failed: role name is required");
            }
            if (SYSTEM_ROLES.contains(roleName)) {
                return errorResponse("Role creation failed: '" + roleName + "' is a reserved system role");
            }
            String validationError = validateRoleCommand(roleCmd);
            if (validationError != null) {
                return errorResponse(validationError);
            }
            Map<String, Object> roles = loadRoleStore();
            if (roles.containsKey(roleName)) {
                return errorResponse("Role creation failed: role already exists");
            }
            JsonObject roleDoc = buildRoleDoc(roleName, roleCmd, true);
            upsertRole(roleName, asMap(JsonValueConverter.fromJsonElement(roleDoc)));
            return successResponse("Role created: " + roleName);
        } catch (Exception e) {
            return errorResponse("Role creation failed: " + e.getMessage());
        }
    }

    private String processReadCommand(JsonObject readCmd) {
        if (!readCmd.has("role")) {
            return errorResponse("Invalid read command: missing role");
        }
        String roleName = normalizeRoleName(extractName(readCmd.get("role")));
        if (roleName.isEmpty()) {
            return errorResponse("Invalid read command: invalid role value");
        }
        try {
            if (SYSTEM_ROLES.contains(roleName)) {
                return successResponse(systemRoleDoc(roleName));
            }
            Map<String, Object> roles = loadRoleStore();
            if (!roles.containsKey(roleName)) {
                return errorResponse("Role not found: " + roleName);
            }
            return successResponse(roles.get(roleName));
        } catch (Exception e) {
            return errorResponse("Role read failed: " + e.getMessage());
        }
    }

    private String processUpdateCommand(JsonObject updateCmd) {
        if (!updateCmd.has("role")) {
            return errorResponse("Invalid update command: missing role");
        }
        JsonElement roleElement = updateCmd.get("role");
        if (!roleElement.isJsonObject()) {
            return errorResponse("Invalid update command: role must be an object");
        }
        JsonObject roleCmd = roleElement.getAsJsonObject();
        String roleName = normalizeRoleName(roleCmd.has("name") ? roleCmd.get("name").getAsString() : null);
        if (roleName.isEmpty()) {
            return errorResponse("Invalid update command: role name is required");
        }
        if (SYSTEM_ROLES.contains(roleName)) {
            return errorResponse("Role update failed: '" + roleName + "' is a reserved system role");
        }
        try {
            String validationError = validateRoleCommand(roleCmd);
            if (validationError != null) {
                return errorResponse(validationError);
            }
            Map<String, Object> roles = loadRoleStore();
            if (!roles.containsKey(roleName)) {
                return errorResponse("Role not found: " + roleName);
            }
            JsonObject updated = buildRoleDoc(roleName, roleCmd, false);
            upsertRole(roleName, asMap(JsonValueConverter.fromJsonElement(updated)));
            return successResponse("Role updated: " + roleName);
        } catch (Exception e) {
            return errorResponse("Role update failed: " + e.getMessage());
        }
    }

    private String processDeleteCommand(JsonObject deleteCmd) {
        if (deleteCmd.has("username")) {
            String username = extractName(deleteCmd.get("username"));
            if (username == null || username.isEmpty()) {
                return errorResponse("Invalid username value");
            }
            return deleteUser(username);
        }
        if (deleteCmd.has("role")) {
            String roleName = extractName(deleteCmd.get("role"));
            if (roleName == null || roleName.isEmpty()) {
                return errorResponse("Invalid role value");
            }
            return deleteRole(roleName);
        }

        return errorResponse("Invalid delete command");
    }

    private String deleteUser(String username) {
        try {
            User superAdmin = UserManager.getInstance().getSuperAdmin();
            if (superAdmin != null
                    && User.normalizeUsername(username).equals(User.normalizeUsername(superAdmin.getUsername()))) {
                return errorResponse("Cannot delete super admin user");
            }
            UserManager.getInstance().deleteUser(username);
            return successResponse("User deleted: " + username);
        } catch (Exception e) {
            return errorResponse("User deletion failed: " + e.getMessage());
        }
    }

    private String deleteRole(String roleName) {
        try {
            String normalized = normalizeRoleName(roleName);
            if (normalized.isEmpty()) {
                return errorResponse("Role deletion failed: role name is required");
            }
            if (SYSTEM_ROLES.contains(normalized)) {
                return errorResponse("Role deletion failed: '" + normalized + "' is a reserved system role");
            }
            Map<String, Object> roles = loadRoleStore();
            if (!roles.containsKey(normalized)) {
                return errorResponse("Role not found: " + normalized);
            }
            removeRole(normalized);
            return successResponse("Role deleted: " + normalized);
        } catch (Exception e) {
            return errorResponse("Role deletion failed: " + e.getMessage());
        }
    }

    private String processGrantCommand(JsonObject grantCmd) {
        if (!grantCmd.has("username")) {
            return errorResponse("Invalid grant command: missing username");
        }
        String username = extractName(grantCmd.get("username"));
        if (username == null || username.isEmpty()) {
            return errorResponse("Invalid grant command: invalid username");
        }
        return grantPermissions(username, grantCmd);
    }

    private String processTransferCommand(JsonObject transferCmd) {
        if (!transferCmd.has("username")) {
            return errorResponse("Invalid transfer command: missing username");
        }
        String username = extractName(transferCmd.get("username"));
        if (username == null || username.isEmpty()) {
            return errorResponse("Invalid transfer command: invalid username");
        }

        if (!transferCmd.has("domain")) {
            return errorResponse("Invalid transfer command: missing domain");
        }

        String domain = transferCmd.get("domain").getAsString().toLowerCase(Locale.ROOT);
        if (!canManageDomain(domain)) {
            return errorResponse("Permission denied for domain: " + domain);
        }

        User user = UserManager.getInstance().getUser(username);
        if (user == null) {
            return errorResponse("User not found");
        }

        user.grantDomainOwnership(domain);
        UserManager.getInstance().updateUser(user);

        if (transferCmd.has("relinquish") && transferCmd.get("relinquish").getAsBoolean() && !currentUser.isSuperAdmin()) {
            user = UserManager.getInstance().getUser(currentUser.getUsername());
            if (user != null) {
                user.revokeDomainOwnership(domain);
                UserManager.getInstance().updateUser(user);
            }
        }

        return successResponse("Domain access transferred/granted for user: " + username);
    }

    private String grantPermissions(String username, JsonObject cmd) {
        try {
            User user = UserManager.getInstance().getUser(username);
            if (user == null) {
                return errorResponse("User not found");
            }

            if (cmd.has("role")) {
                return grantRoleToUser(user, cmd.get("role"));
            }

            String domain = cmd.has("domain") ? cmd.get("domain").getAsString().toLowerCase(Locale.ROOT) : null;
            String db = cmd.has("db") ? cmd.get("db").getAsString().toLowerCase(Locale.ROOT) : currentDB;
            String collection = cmd.has("collection") ? cmd.get("collection").getAsString().toLowerCase(Locale.ROOT) : null;
            List<String> targetDomains = resolveTargetDomains(cmd, domain);
            if (targetDomains.isEmpty()) {
                return errorResponse("Grant requires domain or domains");
            }
            for (String targetDomain : targetDomains) {
                if (!canManageDomain(targetDomain)) {
                    return errorResponse("Permission denied for domain: " + targetDomain);
                }
            }

            // Domain ownership grant (no explicit permission list provided).
            if (collection == null && !cmd.has("permissions") && !cmd.has("permission") && !cmd.has("db")) {
                for (String targetDomain : targetDomains) {
                    user.grantDomainOwnership(targetDomain);
                }
                UserManager.getInstance().updateUser(user);
                return successResponse("Domain ownership granted");
            }

            Set<String> perms = parsePermissions(cmd);
            if (perms.isEmpty()) {
                perms.add("DATA_ACCESS");
            }
            if (perms.contains("DATA_EXPORT") && !currentUser.isSuperAdmin()) {
                return errorResponse("Permission denied: only super admin can grant DATA_EXPORT");
            }

            for (String targetDomain : targetDomains) {
                for (String perm : perms) {
                    if (collection != null) {
                        user.grantCollectionPermission(targetDomain, db, collection, perm);
                    } else {
                        user.grantPermission(targetDomain, db, perm);
                    }
                }
            }
            UserManager.getInstance().updateUser(user);
            return successResponse("Permissions granted");
        } catch (Exception e) {
            return errorResponse("Permission granting failed: " + e.getMessage());
        }
    }

    private String processRevokeCommand(JsonObject revokeCmd) {
        if (!revokeCmd.has("username")) {
            return errorResponse("Invalid revoke command: missing username");
        }
        String username = extractName(revokeCmd.get("username"));
        if (username == null || username.isEmpty()) {
            return errorResponse("Invalid revoke command: invalid username");
        }
        return revokePermissions(username, revokeCmd);
    }

    private String revokePermissions(String username, JsonObject cmd) {
        try {
            User user = UserManager.getInstance().getUser(username);
            if (user == null) {
                return errorResponse("User not found");
            }

            if (cmd.has("role")) {
                return revokeRoleFromUser(user, cmd.get("role"));
            }

            String domain = cmd.has("domain") ? cmd.get("domain").getAsString().toLowerCase(Locale.ROOT) : null;
            String db = cmd.has("db") ? cmd.get("db").getAsString().toLowerCase(Locale.ROOT) : currentDB;
            String collection = cmd.has("collection") ? cmd.get("collection").getAsString().toLowerCase(Locale.ROOT) : null;
            List<String> targetDomains = resolveTargetDomains(cmd, domain);
            if (targetDomains.isEmpty()) {
                return errorResponse("Revoke requires domain or domains");
            }
            for (String targetDomain : targetDomains) {
                if (!canManageDomain(targetDomain)) {
                    return errorResponse("Permission denied for domain: " + targetDomain);
                }
            }

            if (collection == null && !cmd.has("permissions") && !cmd.has("permission") && !cmd.has("db")) {
                for (String targetDomain : targetDomains) {
                    user.revokeDomainOwnership(targetDomain);
                }
                UserManager.getInstance().updateUser(user);
                return successResponse("Domain ownership revoked");
            }

            Set<String> perms = parsePermissions(cmd);
            if (perms.isEmpty()) {
                perms.add("DATA_ACCESS");
            }
            if (perms.contains("DATA_EXPORT") && !currentUser.isSuperAdmin()) {
                return errorResponse("Permission denied: only super admin can revoke DATA_EXPORT");
            }

            for (String targetDomain : targetDomains) {
                for (String perm : perms) {
                    if (collection != null) {
                        user.revokeCollectionPermission(targetDomain, db, collection, perm);
                    } else {
                        user.revokePermission(targetDomain, db, perm);
                    }
                }
            }
            UserManager.getInstance().updateUser(user);
            return successResponse("Permissions revoked");
        } catch (Exception e) {
            return errorResponse("Permission revocation failed: " + e.getMessage());
        }
    }

    private List<String> resolveTargetDomains(JsonObject cmd, String singleDomain) {
        LinkedHashSet<String> domains = new LinkedHashSet<>();
        if (singleDomain != null && !singleDomain.isBlank()) {
            if ("*".equals(singleDomain.trim())) {
                if (currentUser.isSuperAdmin()) {
                    domains.addAll(DirectoryUtil.getDomains());
                } else {
                    domains.addAll(currentUser.getOwnedDomains());
                }
            } else {
                domains.add(singleDomain.trim().toLowerCase(Locale.ROOT));
            }
        }
        if (cmd.has("domains")) {
            JsonElement domainsEl = cmd.get("domains");
            if (domainsEl.isJsonArray()) {
                for (JsonElement element : domainsEl.getAsJsonArray()) {
                    if (element != null && element.isJsonPrimitive()) {
                        String d = element.getAsString().trim().toLowerCase(Locale.ROOT);
                        if (!d.isEmpty()) {
                            domains.add(d);
                        }
                    }
                }
            } else if (domainsEl.isJsonPrimitive()) {
                String d = domainsEl.getAsString().trim().toLowerCase(Locale.ROOT);
                if ("*".equals(d)) {
                    if (currentUser.isSuperAdmin()) {
                        domains.addAll(DirectoryUtil.getDomains());
                    } else {
                        domains.addAll(currentUser.getOwnedDomains());
                    }
                } else if (!d.isEmpty()) {
                    domains.add(d);
                }
            }
        }
        return new ArrayList<>(domains);
    }

    protected String processListCommand(JsonElement listCmd) {
        if (listCmd.isJsonPrimitive()) {
            return processListCommand(listCmd.getAsString());
        } else if (listCmd.isJsonObject()) {
            JsonObject listObject = listCmd.getAsJsonObject();
            if (listObject.has("domains_and_owners")) {
                return listDomainsAndOwners();
            }
            if (listObject.has("roles")) {
                return listRoles();
            }
            if (listObject.has("permissions")) {
                return listPermissions(listObject.get("permissions"));
            }
        }

        return errorResponse("Invalid list command");
    }

    protected String listDomainsAndOwners() {
        try {
            List<Map<String, Object>> domains = new ArrayList<>();
            for (String domain : DirectoryUtil.getDomains()) {
                if (!currentUser.isSuperAdmin() && !currentUser.ownsDomain(domain)) {
                    continue;
                }
                Path metadataPath = DirectoryUtil.getDomainMetadataPath(domain);
                Map<String, Object> metadata = new HashMap<>();
                if (Files.exists(metadataPath)) {
                    metadata = BsonStorage.readMap(metadataPath);
                }

                List<String> owners = UserManager.getInstance().getDomainOwners(domain);
                Object owner = metadata.get("owner");
                if (owner == null) {
                    owner = owners.isEmpty() ? "unknown" : owners.get(0);
                }

                Map<String, Object> domainInfo = new LinkedHashMap<>();
                domainInfo.put("domain", domain);
                domainInfo.put("owner", owner);
                domainInfo.put("owners", owners);
                domainInfo.put("created_at", metadata.get("created_at"));
                domainInfo.put("modified_at", metadata.get("modified_at"));
                domains.add(domainInfo);
            }
            return successResponse(domains);
        } catch (Exception e) {
            return errorResponse("Domain listing failed: " + e.getMessage());
        }
    }

    private String processListCommand(String type) {
        switch (type.toLowerCase(Locale.ROOT)) {
            case "domains":
                return listDomains();
            case "domains_and_owners":
                return listDomainsAndOwners();
            case "owned_domains":
                return listOwnedDomains();
            case "users":
                return listUsers();
            case "roles":
                return listRoles();
            case "permissions":
                return listPermissions(null);
            default:
                return errorResponse("Unknown list type");
        }
    }

    private String listDomains() {
        try {
            if (currentUser.isSuperAdmin()) {
                return successResponse(DirectoryUtil.getDomains());
            }
            return successResponse(new ArrayList<>(currentUser.getOwnedDomains()));
        } catch (Exception e) {
            return errorResponse("Domain listing failed: " + e.getMessage());
        }
    }

    private String listOwnedDomains() {
        return successResponse(new ArrayList<>(currentUser.getOwnedDomains()));
    }

    private String listUsers() {
        if (!currentUser.isSuperAdmin()) {
            return errorResponse("Permission denied: only super admin can list users");
        }
        try {
            List<String> users = UserManager.getInstance().listUsers()
                    .stream()
                    .map(User::getUsername)
                    .collect(Collectors.toList());
            return successResponse(users);
        } catch (Exception e) {
            return errorResponse("User listing failed: " + e.getMessage());
        }
    }

    private String listRoles() {
        try {
            List<Object> system = new ArrayList<>();
            system.add(systemRoleDoc("SUPER_ADMIN"));
            system.add(systemRoleDoc("ADMIN"));
            system.add(systemRoleDoc("APPLICATION"));
            Map<String, Object> roles = loadRoleStore();
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("valid_roles", roleValidationDoc());
            out.put("system_roles", system);
            out.put("custom_roles", new ArrayList<>(roles.values()));
            return successResponse(out);
        } catch (Exception e) {
            return errorResponse("Role listing failed: " + e.getMessage());
        }
    }

    private String listPermissions(JsonElement target) {
        try {
            User targetUser = currentUser;
            if (target != null && target.isJsonPrimitive()) {
                String username = User.normalizeUsername(target.getAsString());
                User found = UserManager.getInstance().getUser(username);
                if (found == null) {
                    return errorResponse("User not found: " + username);
                }
                if (!currentUser.isSuperAdmin()
                        && !username.equals(User.normalizeUsername(currentUser.getUsername()))) {
                    return errorResponse("Permission denied for listing other user permissions");
                }
                targetUser = found;
            }

            Map<String, Object> data = new LinkedHashMap<>();
            data.put("username", targetUser.getUsername());
            data.put("owned_domains", targetUser.getOwnedDomains());
            data.put("db_permissions", targetUser.getPermissions());
            data.put("collection_permissions", targetUser.getCollectionPermissions());
            return successResponse(data);
        } catch (Exception e) {
            return errorResponse("Permission listing failed: " + e.getMessage());
        }
    }

    private boolean canManageDomain(String domain) {
        return currentUser.isSuperAdmin() || currentUser.ownsDomain(domain);
    }

    private Set<String> parsePermissions(JsonObject cmd) {
        Set<String> permissions = new LinkedHashSet<>();
        if (cmd.has("permission")) {
            permissions.add(cmd.get("permission").getAsString().trim().toUpperCase(Locale.ROOT));
        }
        if (cmd.has("permissions")) {
            JsonElement permsEl = cmd.get("permissions");
            if (permsEl.isJsonArray()) {
                for (JsonElement p : permsEl.getAsJsonArray()) {
                    permissions.add(p.getAsString().trim().toUpperCase(Locale.ROOT));
                }
            } else if (permsEl.isJsonPrimitive()) {
                permissions.add(permsEl.getAsString().trim().toUpperCase(Locale.ROOT));
            }
        }
        permissions.removeIf(String::isEmpty);
        return permissions;
    }

    private String extractName(JsonElement element) {
        if (element == null) {
            return null;
        }
        if (element.isJsonPrimitive()) {
            return element.getAsString();
        }
        if (element.isJsonObject()) {
            JsonObject obj = element.getAsJsonObject();
            if (obj.has("name")) {
                return obj.get("name").getAsString();
            }
            if (obj.has("username")) {
                return obj.get("username").getAsString();
            }
        }
        return null;
    }

    private String normalizeRoleName(String rawRole) {
        if (rawRole == null) {
            return "";
        }
        String role = rawRole.trim().toUpperCase(Locale.ROOT);
        if ("APP".equals(role)) {
            return "APPLICATION";
        }
        return role;
    }

    private JsonObject systemRoleDoc(String roleName) {
        JsonObject doc = new JsonObject();
        doc.addProperty("name", roleName);
        doc.addProperty("system", true);
        doc.addProperty("read_only", true);
        doc.addProperty("description", "Built-in system role");
        return doc;
    }

    private JsonObject roleValidationDoc() {
        JsonObject doc = new JsonObject();
        JsonArray canonical = new JsonArray();
        canonical.add("SUPER_ADMIN");
        canonical.add("ADMIN");
        canonical.add("APPLICATION");
        JsonArray createAllowed = new JsonArray();
        createAllowed.add("ADMIN");
        createAllowed.add("APPLICATION");
        createAllowed.add("APP");
        doc.add("canonical", canonical);
        doc.add("create_user_allowed", createAllowed);
        doc.addProperty("create_user_notes", "SUPER_ADMIN is reserved; APP alias maps to APPLICATION.");
        return doc;
    }

    private String validateRoleCommand(JsonObject roleCmd) {
        if (!roleCmd.has("scope") || !roleCmd.get("scope").isJsonObject()) {
            return "Role definition requires scope with domain and db";
        }
        JsonObject scope = roleCmd.getAsJsonObject("scope");
        String domain = scope.has("domain") ? scope.get("domain").getAsString().trim() : "";
        String db = scope.has("db") ? scope.get("db").getAsString().trim() : "";
        if (domain.isEmpty() || db.isEmpty()) {
            return "Role definition requires non-empty scope.domain and scope.db";
        }
        Set<String> perms = parsePermissions(roleCmd);
        if (perms.isEmpty()) {
            return "Role definition requires at least one permission";
        }
        return null;
    }

    private String grantRoleToUser(User user, JsonElement roleElement) {
        String roleName = normalizeRoleName(extractName(roleElement));
        if (roleName.isEmpty()) {
            return errorResponse("Invalid role value for grant");
        }
        if (SYSTEM_ROLES.contains(roleName)) {
            return errorResponse("Granting system roles is not supported through tumi grant role");
        }
        try {
            Map<String, Object> roleDef = getCustomRole(roleName);
            if (roleDef == null) {
                return errorResponse("Role not found: " + roleName);
            }
            String domain = getRoleScopeValue(roleDef, "domain");
            String db = getRoleScopeValue(roleDef, "db");
            if (domain == null || db == null) {
                return errorResponse("Role '" + roleName + "' has invalid scope");
            }
            if (!canManageDomain(domain)) {
                return errorResponse("Permission denied for domain: " + domain);
            }
            Set<String> perms = getRolePermissions(roleDef);
            if (perms.isEmpty()) {
                return errorResponse("Role '" + roleName + "' has no permissions");
            }
            for (String perm : perms) {
                user.grantPermission(domain, db, perm);
            }
            UserManager.getInstance().updateUser(user);
            return successResponse("Role granted: " + roleName + " to user " + user.getUsername());
        } catch (Exception e) {
            return errorResponse("Role grant failed: " + e.getMessage());
        }
    }

    private String revokeRoleFromUser(User user, JsonElement roleElement) {
        String roleName = normalizeRoleName(extractName(roleElement));
        if (roleName.isEmpty()) {
            return errorResponse("Invalid role value for revoke");
        }
        if (SYSTEM_ROLES.contains(roleName)) {
            return errorResponse("Revoking system roles is not supported through tumi revoke role");
        }
        try {
            Map<String, Object> roleDef = getCustomRole(roleName);
            if (roleDef == null) {
                return errorResponse("Role not found: " + roleName);
            }
            String domain = getRoleScopeValue(roleDef, "domain");
            String db = getRoleScopeValue(roleDef, "db");
            if (domain == null || db == null) {
                return errorResponse("Role '" + roleName + "' has invalid scope");
            }
            if (!canManageDomain(domain)) {
                return errorResponse("Permission denied for domain: " + domain);
            }
            Set<String> perms = getRolePermissions(roleDef);
            if (perms.isEmpty()) {
                return errorResponse("Role '" + roleName + "' has no permissions");
            }
            for (String perm : perms) {
                user.revokePermission(domain, db, perm);
            }
            UserManager.getInstance().updateUser(user);
            return successResponse("Role revoked: " + roleName + " from user " + user.getUsername());
        } catch (Exception e) {
            return errorResponse("Role revoke failed: " + e.getMessage());
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> getCustomRole(String roleName) throws IOException {
        Map<String, Object> roles = loadRoleStore();
        Object found = roles.get(roleName);
        if (!(found instanceof Map)) {
            return null;
        }
        return (Map<String, Object>) found;
    }

    @SuppressWarnings("unchecked")
    private String getRoleScopeValue(Map<String, Object> roleDef, String key) {
        Object scopeObj = roleDef.get("scope");
        if (!(scopeObj instanceof Map)) {
            return null;
        }
        Object value = ((Map<String, Object>) scopeObj).get(key);
        if (value == null) {
            return null;
        }
        String text = String.valueOf(value).trim().toLowerCase(Locale.ROOT);
        return text.isEmpty() ? null : text;
    }

    @SuppressWarnings("unchecked")
    private Set<String> getRolePermissions(Map<String, Object> roleDef) {
        Set<String> out = new LinkedHashSet<>();
        Object raw = roleDef.get("permissions");
        if (raw instanceof List) {
            for (Object item : (List<Object>) raw) {
                String perm = String.valueOf(item == null ? "" : item).trim().toUpperCase(Locale.ROOT);
                if (!perm.isEmpty()) {
                    out.add(perm);
                }
            }
        } else if (raw != null) {
            String perm = String.valueOf(raw).trim().toUpperCase(Locale.ROOT);
            if (!perm.isEmpty()) {
                out.add(perm);
            }
        }
        return out;
    }

    private JsonObject buildRoleDoc(String roleName, JsonObject roleCmd, boolean creating) {
        JsonObject doc = new JsonObject();
        doc.addProperty("name", roleName);
        doc.addProperty("system", false);
        doc.addProperty("updated_at", Instant.now().toString());

        if (creating) {
            doc.addProperty("created_at", Instant.now().toString());
        } else {
            try {
                Map<String, Object> existing = getCustomRole(roleName);
                if (existing != null) {
                    Object createdAt = existing.get("created_at");
                    if (createdAt != null) {
                        doc.addProperty("created_at", String.valueOf(createdAt));
                    }
                }
            } catch (Exception ignore) {
                // best-effort preserve created_at
            }
        }

        if (roleCmd.has("scope") && roleCmd.get("scope").isJsonObject()) {
            JsonObject scope = roleCmd.getAsJsonObject("scope");
            JsonObject normalizedScope = new JsonObject();
            if (scope.has("domain")) {
                normalizedScope.addProperty("domain", scope.get("domain").getAsString().trim().toLowerCase(Locale.ROOT));
            }
            if (scope.has("db")) {
                normalizedScope.addProperty("db", scope.get("db").getAsString().trim().toLowerCase(Locale.ROOT));
            }
            doc.add("scope", normalizedScope);
        }

        JsonArray permissions = new JsonArray();
        if (roleCmd.has("permissions")) {
            JsonElement p = roleCmd.get("permissions");
            if (p.isJsonArray()) {
                for (JsonElement item : p.getAsJsonArray()) {
                    permissions.add(item.getAsString().trim().toUpperCase(Locale.ROOT));
                }
            } else if (p.isJsonPrimitive()) {
                permissions.add(p.getAsString().trim().toUpperCase(Locale.ROOT));
            }
        }
        doc.add("permissions", permissions);
        return doc;
    }

    private Map<String, Object> loadRoleStore() throws IOException {
        if (!isRoleStoreCurrent()) {
            reloadRoleStore();
        }
        return new LinkedHashMap<>(cachedRoleStore);
    }

    private synchronized void reloadRoleStore() throws IOException {
        Files.createDirectories(ROLE_DIR);
        Object rawStore = Files.exists(ROLE_DATA_PATH) ? BsonStorage.readValue(ROLE_DATA_PATH) : null;
        if (rawStore instanceof Map<?, ?> && !((Map<?, ?>) rawStore).containsKey(MANIFEST_ROLE_NAMES_KEY) && !((Map<?, ?>) rawStore).isEmpty()) {
            migrateAggregateRoleStore(asMap(rawStore));
            rawStore = Files.exists(ROLE_DATA_PATH) ? BsonStorage.readValue(ROLE_DATA_PATH) : null;
        }

        List<String> roleNames = extractManifestRoleNames(rawStore);
        if (roleNames.isEmpty()) {
            roleNames = discoverRoleNamesFromFiles();
            if (!roleNames.isEmpty()) {
                writeRoleManifest(roleNames);
            }
        }

        Map<String, Object> loadedRoles = new LinkedHashMap<>();
        Map<String, Long> loadedMtimes = new LinkedHashMap<>();
        for (String roleName : roleNames) {
            Map<String, Object> roleDoc = readRoleRecord(roleName);
            if (roleDoc.isEmpty()) {
                continue;
            }
            loadedRoles.put(roleName, roleDoc);
            loadedMtimes.put(roleName, safeMtime(DirectoryUtil.getRolePath(roleName)));
        }

        cachedRoleStore = new LinkedHashMap<>(loadedRoles);
        roleRecordMtimes.clear();
        roleRecordMtimes.putAll(loadedMtimes);
        if (!loadedRoles.isEmpty()) {
            LinkedHashSet<String> loadedRoleNames = new LinkedHashSet<>(loadedRoles.keySet());
            if (!loadedRoleNames.equals(new LinkedHashSet<>(roleNames))) {
                writeRoleManifest(loadedRoleNames);
                return;
            }
        }
        roleStoreMtime = safeMtime(ROLE_DATA_PATH);
    }

    private boolean isRoleStoreCurrent() {
        if (!Files.exists(ROLE_DATA_PATH) && !hasAnyRoleRecords()) {
            cachedRoleStore = new LinkedHashMap<>();
            roleRecordMtimes.clear();
            roleStoreMtime = -1L;
            return true;
        }
        if (Files.exists(ROLE_DATA_PATH)) {
            try {
                Object rawStore = BsonStorage.readValue(ROLE_DATA_PATH);
                if (rawStore instanceof Map<?, ?> && !((Map<?, ?>) rawStore).containsKey(MANIFEST_ROLE_NAMES_KEY) && !((Map<?, ?>) rawStore).isEmpty()) {
                    return false;
                }
            } catch (IOException e) {
                return false;
            }
        }
        if (safeMtime(ROLE_DATA_PATH) != roleStoreMtime) {
            return false;
        }
        for (String roleName : cachedRoleStore.keySet()) {
            long currentMtime = safeMtime(DirectoryUtil.getRolePath(roleName));
            if (currentMtime != roleRecordMtimes.getOrDefault(roleName, -1L)) {
                return false;
            }
        }
        return !(cachedRoleStore.isEmpty() && hasAnyRoleRecords());
    }

    private List<String> extractManifestRoleNames(Object rawStore) {
        if (!(rawStore instanceof Map<?, ?>)) {
            return Collections.emptyList();
        }
        Object rawRoleNames = ((Map<?, ?>) rawStore).get(MANIFEST_ROLE_NAMES_KEY);
        if (!(rawRoleNames instanceof List<?>)) {
            return Collections.emptyList();
        }
        List<String> roleNames = new ArrayList<>();
        for (Object rawRoleName : (List<?>) rawRoleNames) {
            String roleName = normalizeRoleName(rawRoleName == null ? "" : String.valueOf(rawRoleName));
            if (!roleName.isEmpty() && !roleNames.contains(roleName)) {
                roleNames.add(roleName);
            }
        }
        return roleNames;
    }

    private List<String> discoverRoleNamesFromFiles() {
        if (!Files.isDirectory(ROLE_DIR)) {
            return Collections.emptyList();
        }
        List<String> roleNames = new ArrayList<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(ROLE_DIR, "*" + BsonStorage.DOCUMENT_EXTENSION)) {
            for (Path path : stream) {
                String filename = path.getFileName().toString();
                if (ROLE_DATA_PATH.getFileName().toString().equals(filename)) {
                    continue;
                }
                String roleName = normalizeRoleName(filename.substring(0, filename.length() - BsonStorage.DOCUMENT_EXTENSION.length()));
                if (!roleName.isEmpty() && !roleNames.contains(roleName)) {
                    roleNames.add(roleName);
                }
            }
        } catch (IOException ignored) {
        }
        roleNames.sort(String::compareTo);
        return roleNames;
    }

    private boolean hasAnyRoleRecords() {
        return !discoverRoleNamesFromFiles().isEmpty();
    }

    private Map<String, Object> readRoleRecord(String roleName) {
        Path rolePath = DirectoryUtil.getRolePath(roleName);
        if (!Files.exists(rolePath)) {
            return new LinkedHashMap<>();
        }
        try {
            Map<String, Object> parsed = BsonStorage.readMap(rolePath);
            return parsed == null ? new LinkedHashMap<>() : new LinkedHashMap<>(parsed);
        } catch (IOException e) {
            return new LinkedHashMap<>();
        }
    }

    private void writeRoleManifest(java.util.Collection<String> roleNames) throws IOException {
        Files.createDirectories(ROLE_DIR);
        List<String> normalizedRoleNames = new ArrayList<>();
        for (String roleName : roleNames) {
            String normalized = normalizeRoleName(roleName);
            if (!normalized.isEmpty() && !normalizedRoleNames.contains(normalized)) {
                normalizedRoleNames.add(normalized);
            }
        }
        Map<String, Object> manifest = new LinkedHashMap<>();
        manifest.put(MANIFEST_ROLE_NAMES_KEY, normalizedRoleNames);
        manifest.put("updated_at", Instant.now().toString());
        BsonStorage.writeValue(ROLE_DATA_PATH, manifest);
        roleStoreMtime = safeMtime(ROLE_DATA_PATH);
    }

    private void migrateAggregateRoleStore(Map<String, Object> aggregateRoles) throws IOException {
        Files.createDirectories(ROLE_DIR);
        Map<String, Object> normalizedRoles = new LinkedHashMap<>();
        for (Map.Entry<String, Object> entry : aggregateRoles.entrySet()) {
            String roleName = normalizeRoleName(entry.getKey());
            if (roleName.isEmpty() || SYSTEM_ROLES.contains(roleName)) {
                continue;
            }
            normalizedRoles.put(roleName, asMap(entry.getValue()));
        }
        saveRoleStore(normalizedRoles);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> asMap(Object rawValue) {
        if (rawValue instanceof Map<?, ?>) {
            return new LinkedHashMap<>((Map<String, Object>) rawValue);
        }
        if (rawValue == null) {
            return new LinkedHashMap<>();
        }
        Object converted = JsonValueConverter.convertViaJson(gson, rawValue);
        if (converted instanceof Map<?, ?>) {
            return new LinkedHashMap<>((Map<String, Object>) converted);
        }
        return new LinkedHashMap<>();
    }

    private void upsertRole(String roleName, Map<String, Object> roleDoc) throws IOException {
        Map<String, Object> roles = loadRoleStore();
        roles.put(roleName, roleDoc);
        Path rolePath = DirectoryUtil.getRolePath(roleName);
        Files.createDirectories(rolePath.getParent());
        BsonStorage.writeValue(rolePath, roleDoc == null ? Collections.emptyMap() : roleDoc);
        roleRecordMtimes.put(roleName, safeMtime(rolePath));
        cachedRoleStore = new LinkedHashMap<>(roles);
        writeRoleManifest(roles.keySet());
    }

    private void removeRole(String roleName) throws IOException {
        Map<String, Object> roles = loadRoleStore();
        roles.remove(roleName);
        Files.deleteIfExists(DirectoryUtil.getRolePath(roleName));
        roleRecordMtimes.remove(roleName);
        cachedRoleStore = new LinkedHashMap<>(roles);
        writeRoleManifest(roles.keySet());
    }

    private void saveRoleStore(Map<String, Object> roles) throws IOException {
        Files.createDirectories(ROLE_DATA_PATH.getParent());
        Map<String, Object> normalizedRoles = roles == null ? Collections.emptyMap() : new LinkedHashMap<>(roles);
        Set<String> staleRoleNames = new LinkedHashSet<>(discoverRoleNamesFromFiles());
        for (Map.Entry<String, Object> entry : normalizedRoles.entrySet()) {
            String roleName = normalizeRoleName(entry.getKey());
            if (roleName.isEmpty()) {
                continue;
            }
            Path rolePath = DirectoryUtil.getRolePath(roleName);
            BsonStorage.writeValue(rolePath, entry.getValue() == null ? Collections.emptyMap() : entry.getValue());
            roleRecordMtimes.put(roleName, safeMtime(rolePath));
            staleRoleNames.remove(roleName);
        }
        for (String staleRoleName : staleRoleNames) {
            Files.deleteIfExists(DirectoryUtil.getRolePath(staleRoleName));
            roleRecordMtimes.remove(staleRoleName);
        }
        cachedRoleStore = new LinkedHashMap<>(normalizedRoles);
        writeRoleManifest(normalizedRoles.keySet());
    }

    private long safeMtime(Path path) {
        if (path == null || !Files.exists(path)) {
            return -1L;
        }
        try {
            return Files.getLastModifiedTime(path).toMillis();
        } catch (IOException e) {
            return -1L;
        }
    }

    private String successResponse() {
        return successResponse("ok");
    }

    private String successResponse(Object data) {
        Map<String, Object> response = new HashMap<>();
        response.put("status", "success");
        response.put("data", data);
        return gson.toJson(response);
    }

    private String successResponse(String message) {
        Map<String, Object> response = new HashMap<>();
        response.put("status", "success");
        response.put("message", message);
        return gson.toJson(response);
    }

    private String errorResponse(String message) {
        Map<String, Object> response = new HashMap<>();
        response.put("status", "error");
        response.put("message", message);
        return gson.toJson(response);
    }
}
