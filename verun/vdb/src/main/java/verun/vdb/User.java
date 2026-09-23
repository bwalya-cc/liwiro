// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;
import org.mindrot.jbcrypt.BCrypt;

import com.google.gson.JsonDeserializationContext;
import com.google.gson.JsonDeserializer;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonSerializationContext;
import com.google.gson.JsonSerializer;
import com.google.gson.reflect.TypeToken;

import java.lang.reflect.Type;
import java.util.*;



public class User {
    private static final Map<String, Integer> ROLE_LEVELS;
    static {
        Map<String, Integer> levels = new HashMap<>();
        levels.put("SUPER_ADMIN", 100);
        levels.put("ADMIN", 70);
        levels.put("APPLICATION", 40);
        ROLE_LEVELS = Collections.unmodifiableMap(levels);
    }

    protected String username;
    protected String email;
    protected String role;
    private String passwordHash;
    private Map<String, Map<String, Set<String>>> permissions = new HashMap<>();
    private Map<String, Map<String, Map<String, Set<String>>>> collectionPermissions = new HashMap<>();
    private Set<String> ownedDomains;

    // Constructor for new users
    public User(String username, String email, String role, String password) {
        this.username = normalizeUsername(username);
        this.email = email;
        this.role = normalizeRole(role);
        validateRole(this.role);
        this.passwordHash = hashPassword(password);
        this.permissions = new HashMap<>();
        this.collectionPermissions = new HashMap<>();
        this.ownedDomains = new HashSet<>();
    }

    // Constructor for deserialization
    protected User(String username, String email, String role, String passwordHash,
                  Map<String, Map<String, Set<String>>> permissions,
                  Map<String, Map<String, Map<String, Set<String>>>> collectionPermissions,
                  Set<String> ownedDomains) {
        this.username = normalizeUsername(username);
        this.email = email;
        this.role = normalizeRole(role);
        validateRole(this.role);
        this.passwordHash = passwordHash;
        this.permissions = permissions != null ? new HashMap<>(permissions) : new HashMap<>();
        this.collectionPermissions = collectionPermissions != null ? new HashMap<>(collectionPermissions) : new HashMap<>();
        this.ownedDomains = ownedDomains != null ? new HashSet<>(ownedDomains) : new HashSet<>();
    }

    private static String normalizeRole(String role) {
        return role == null ? "" : role.trim().toUpperCase(Locale.ROOT);
    }

    public static String normalizeUsername(String username) {
        return username == null ? "" : username.trim().toLowerCase(Locale.ROOT);
    }

    private static void validateRole(String role) {
        if (!ROLE_LEVELS.containsKey(role)) {
            throw new IllegalArgumentException("Invalid role '" + role +
                    "'. Allowed roles: SUPER_ADMIN, ADMIN, APPLICATION");
        }
    }

    public static class UserSerializer implements JsonSerializer<User>, JsonDeserializer<User> {
        public JsonElement serialize(User user, Type type, JsonSerializationContext context) {
            JsonObject obj = new JsonObject();
            obj.addProperty("username", user.username);
            obj.addProperty("email", user.email);
            obj.addProperty("role", user.role);
            obj.addProperty("passwordHash", user.passwordHash);
            Type permsType = new TypeToken<Map<String, Map<String, Set<String>>>>() {}.getType();
            Type collPermsType = new TypeToken<Map<String, Map<String, Map<String, Set<String>>>>>() {}.getType();
            Type domainsType = new TypeToken<Set<String>>() {}.getType();
            obj.add("permissions", context.serialize(user.permissions, permsType));
            obj.add("collectionPermissions", context.serialize(user.collectionPermissions, collPermsType));
            obj.add("ownedDomains", context.serialize(user.ownedDomains, domainsType));
            return obj;
        }

        public User deserialize(JsonElement json, Type type, JsonDeserializationContext context) {
            JsonObject obj = json.getAsJsonObject();
            Type permsType = new TypeToken<Map<String, Map<String, Set<String>>>>() {}.getType();
            Type collPermsType = new TypeToken<Map<String, Map<String, Map<String, Set<String>>>>>() {}.getType();
            return new User(
                obj.get("username").getAsString(),
                obj.get("email").getAsString(),
                obj.get("role").getAsString(),
                obj.get("passwordHash").getAsString(),
                obj.has("permissions") ? context.deserialize(obj.get("permissions"), permsType) : Collections.emptyMap(),
                obj.has("collectionPermissions") ? context.deserialize(obj.get("collectionPermissions"), collPermsType) : Collections.emptyMap(),
                context.deserialize(obj.get("ownedDomains"), new TypeToken<Set<String>>(){}.getType())
            );
        }
    }

    public boolean ownsDomain(String domain) {
        if (domain == null || domain.isEmpty()) {
            throw new IllegalArgumentException("Domain cannot be null or empty");
        }

        Set<String> ownedDomains = this.ownedDomains;

        if (ownedDomains.isEmpty()) {
            return false;
        }

        return ownedDomains.contains(domain.toLowerCase(Locale.ROOT));
    }

    public boolean authenticate(String password) {
        return BCrypt.checkpw(password, passwordHash);
    }

    public Map<String, Object> getPermissions() {
        return Collections.unmodifiableMap(permissions);
    }

    private void validatePasswordPolicy(String password) {
        if (password.length() < 8) {
            throw new IllegalArgumentException("Password must be at least 8 characters");
        }
        if (!password.matches(".*[A-Z].*")) {
            throw new IllegalArgumentException("Password must contain at least one uppercase letter");
        }
        if (!password.matches(".*[a-z].*")) {
            throw new IllegalArgumentException("Password must contain at least one lowercase letter");
        }
        if (!password.matches(".*\\d.*")) {
            throw new IllegalArgumentException("Password must contain at least one number");
        }
        if (!password.matches(".*[!@#$%^&*()_+\\-=\\[\\]{};':\"\\\\|,.<>\\/?].*")) {
            throw new IllegalArgumentException("Password must contain at least one special character");
        }
    }

    private String hashPassword(String password) {
        validatePasswordPolicy(password);
        return BCrypt.hashpw(password, BCrypt.gensalt(12));
    }

    public void grantDomainOwnership(String domain) {
        if (this.ownedDomains == null) {
            this.ownedDomains = new HashSet<>();
        }
        this.ownedDomains.add(domain.toLowerCase(Locale.ROOT));
    }

    public void revokeDomainOwnership(String domain) {
        ownedDomains.remove(domain.toLowerCase(Locale.ROOT));
    }

    public void grantPermission(String domain, String db, String permission) {
        String d = domain.toLowerCase(Locale.ROOT);
        String b = db.toLowerCase(Locale.ROOT);
        String p = permission.toUpperCase(Locale.ROOT);
        permissions.computeIfAbsent(d, k -> new HashMap<>())
                .computeIfAbsent(b, k -> new HashSet<>())
                .add(p);
    }

    public void revokePermission(String domain, String db, String permission) {
        String d = domain.toLowerCase(Locale.ROOT);
        String b = db.toLowerCase(Locale.ROOT);
        String p = permission.toUpperCase(Locale.ROOT);
        if (permissions.containsKey(d)) {
            permissions.get(d).getOrDefault(b, Collections.emptySet()).remove(p);
        }
    }

    public boolean hasPermission(String domain, String db, String permission) {
        String d = domain.toLowerCase(Locale.ROOT);
        String b = db.toLowerCase(Locale.ROOT);
        String p = permission.toUpperCase(Locale.ROOT);
        if (isSuperAdmin()) {
            return true;
        }
    
        if (ownsDomain(d)) {
            return true;
        }
    
        return permissions.getOrDefault(d, Collections.emptyMap())
                .getOrDefault(b, Collections.emptySet())
                .contains(p);
    }

    public boolean hasExplicitPermission(String domain, String db, String permission) {
        String d = domain.toLowerCase(Locale.ROOT);
        String b = db.toLowerCase(Locale.ROOT);
        String p = permission.toUpperCase(Locale.ROOT);
        return permissions.getOrDefault(d, Collections.emptyMap())
                .getOrDefault(b, Collections.emptySet())
                .contains(p);
    }

    public boolean hasExplicitDomainPermission(String domain, String permission) {
        String d = domain.toLowerCase(Locale.ROOT);
        String p = permission.toUpperCase(Locale.ROOT);
        Map<String, Set<String>> byDb = permissions.getOrDefault(d, Collections.emptyMap());
        for (Set<String> perms : byDb.values()) {
            if (perms != null && perms.contains(p)) {
                return true;
            }
        }
        return false;
    }

    public Set<String> getAccessibleDomains() {
        Set<String> out = new HashSet<>();
        out.addAll(ownedDomains);
        out.addAll(permissions.keySet());
        out.addAll(collectionPermissions.keySet());
        return out;
    }

    public void grantCollectionPermission(String domain, String db, String collection, String permission) {
        String d = domain.toLowerCase(Locale.ROOT);
        String b = db.toLowerCase(Locale.ROOT);
        String c = collection.toLowerCase(Locale.ROOT);
        String p = permission.toUpperCase(Locale.ROOT);
        collectionPermissions
                .computeIfAbsent(d, k -> new HashMap<>())
                .computeIfAbsent(b, k -> new HashMap<>())
                .computeIfAbsent(c, k -> new HashSet<>())
                .add(p);
    }

    public void revokeCollectionPermission(String domain, String db, String collection, String permission) {
        String d = domain.toLowerCase(Locale.ROOT);
        String b = db.toLowerCase(Locale.ROOT);
        String c = collection.toLowerCase(Locale.ROOT);
        String p = permission.toUpperCase(Locale.ROOT);
        if (collectionPermissions.containsKey(d)
                && collectionPermissions.get(d).containsKey(b)
                && collectionPermissions.get(d).get(b).containsKey(c)) {
            collectionPermissions.get(d).get(b).get(c).remove(p);
        }
    }

    public boolean hasCollectionPermission(String domain, String db, String collection, String permission) {
        String d = domain.toLowerCase(Locale.ROOT);
        String b = db.toLowerCase(Locale.ROOT);
        String c = collection.toLowerCase(Locale.ROOT);
        String p = permission.toUpperCase(Locale.ROOT);
        if (isSuperAdmin() || ownsDomain(d)) {
            return true;
        }
        return collectionPermissions
                .getOrDefault(d, Collections.emptyMap())
                .getOrDefault(b, Collections.emptyMap())
                .getOrDefault(c, Collections.emptySet())
                .contains(p);
    }

    public Map<String, Map<String, Map<String, Set<String>>>> getCollectionPermissions() {
        return Collections.unmodifiableMap(collectionPermissions);
    }

    public boolean isSuperAdmin() {
        return "SUPER_ADMIN".equals(role);
    }

    public boolean isAdmin() {
        return "ADMIN".equals(role);
    }

    public boolean isApplication() {
        return "APPLICATION".equals(role);
    }

    public int getRoleLevel() {
        return ROLE_LEVELS.getOrDefault(role, 0);
    }

    // Getters
    public String getUsername() { return username; }
    public String getPasswordHash() { return passwordHash; }
    public String getEmail() { return email; }
    public String getRole() { return role; }

    /** Controlled mutations used by the native Versa user update command. */
    public void updateProfile(String email, String role, String password) {
        if (email != null) this.email = email.trim();
        if (role != null) { String normalized = normalizeRole(role); validateRole(normalized); this.role = normalized; }
        if (password != null) this.passwordHash = hashPassword(password);
    }
    public Set<String> getOwnedDomains() { return Collections.unmodifiableSet(ownedDomains); }
}
