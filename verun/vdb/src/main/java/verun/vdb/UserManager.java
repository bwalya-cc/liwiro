// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.reflect.TypeToken;
import verun.common.JsonValueConverter;
import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Scanner;
import java.util.Set;
import java.util.stream.Collectors;

public class UserManager {
    private static final Path USER_DATA_PATH = DirectoryUtil.getUsersStorePath();
    private static final Path USER_DIR = USER_DATA_PATH.getParent();
    private static final String MANIFEST_USERNAMES_KEY = "usernames";
    private static volatile UserManager instance;
    private static final java.lang.reflect.Type USER_LIST_TYPE = new TypeToken<ArrayList<User>>() {}.getType();
    private boolean initializing = false;
    private Map<String, User> users = new HashMap<>();
    private final Map<String, Long> userRecordMtimes = new HashMap<>();
    private volatile long usersFileMtime = -1L;
    private final Gson gson = new GsonBuilder()
        .registerTypeAdapter(User.class, new User.UserSerializer())
        .create();

    private UserManager() {
        initializing = true;
        loadUsers();
        ensureSuperAdminExists();
        initializing = false;
    }

    protected void ensureSuperAdminExists() {
        // Don't auto-create super admin on startup
        // Instead, check if we need first-time setup
        
        if (users.isEmpty()) {
            // First time initialization - no users exist
            System.out.println("First time setup: No users found. Please create your first user account.");
            // Defer actual creation to interactive prompt in VDBConsole
            return;
        }
        
        // If users exist but no super admin, we have a problem
        if (users.values().stream().noneMatch(User::isSuperAdmin)) {
            System.err.println("Warning: No super admin user found in existing user database");
            return;
        }
        
        User superAdmin = getSuperAdmin();
        if (!superAdmin.getOwnedDomains().contains("default")) {
            superAdmin.grantDomainOwnership("default");
            updateSuperAdmin(superAdmin);
        }

        // Move domain creation outside of constructor to avoid recursion
        if (!DirectoryUtil.domainExists("default") && !initializing) {
            try {
                VDB.defineDomain("default", "main", true);
            } catch (Exception e) {
                throw new RuntimeException("Failed to create default domain", e);
            }
        }
    }

    // Singleton access method
    public static UserManager getInstance() {
        if (instance == null) {
            synchronized (UserManager.class) {
                if (instance == null) {
                    instance = new UserManager();
                }
            }
        }
        return instance;
    }

    private void loadUsers() {
        try {
            Files.createDirectories(USER_DIR);

            if (!Files.exists(USER_DATA_PATH) && !hasAnyUserRecords()) {
                users.clear();
                userRecordMtimes.clear();
                usersFileMtime = -1L;
                return;
            }

            Object rawManifest = Files.exists(USER_DATA_PATH) ? BsonStorage.readValue(USER_DATA_PATH) : null;
            if (rawManifest instanceof List<?>) {
                migrateAggregateUsers(rawManifest);
                rawManifest = Files.exists(USER_DATA_PATH) ? BsonStorage.readValue(USER_DATA_PATH) : null;
            }

            List<String> usernames = extractManifestUsernames(rawManifest);
            if (usernames.isEmpty()) {
                usernames = discoverUsernamesFromRecords();
                if (!usernames.isEmpty()) {
                    writeUsersManifest(usernames);
                }
            }

            Map<String, User> loadedUsers = new LinkedHashMap<>();
            Map<String, Long> loadedMtimes = new HashMap<>();
            for (String username : usernames) {
                User user = readUserRecord(username);
                if (user == null) {
                    continue;
                }
                String normalizedUsername = User.normalizeUsername(user.getUsername());
                loadedUsers.put(normalizedUsername, user);
                loadedMtimes.put(normalizedUsername, safeMtime(userRecordPath(normalizedUsername)));
            }

            users.clear();
            users.putAll(loadedUsers);
            userRecordMtimes.clear();
            userRecordMtimes.putAll(loadedMtimes);

            if (!users.isEmpty()) {
                LinkedHashSet<String> normalizedUsernames = new LinkedHashSet<>(users.keySet());
                if (!new LinkedHashSet<>(usernames).equals(normalizedUsernames)) {
                    writeUsersManifest(normalizedUsernames);
                } else {
                    usersFileMtime = safeMtime(USER_DATA_PATH);
                }
            } else if (Files.exists(USER_DATA_PATH)) {
                usersFileMtime = safeMtime(USER_DATA_PATH);
            }
        } catch (Exception e) {
            System.err.println("Failed to load users: " + e.getMessage());
        }
    }

    private synchronized void refreshUsersIfChanged() {
        try {
            if (!Files.exists(USER_DATA_PATH) && !hasAnyUserRecords()) {
                if (!users.isEmpty()) {
                    users.clear();
                }
                userRecordMtimes.clear();
                usersFileMtime = -1L;
                return;
            }

            if (Files.exists(USER_DATA_PATH) && BsonStorage.readValue(USER_DATA_PATH) instanceof List<?>) {
                loadUsers();
                return;
            }

            long currentManifestMtime = safeMtime(USER_DATA_PATH);
            if (currentManifestMtime != usersFileMtime) {
                loadUsers();
                return;
            }

            for (String username : new ArrayList<>(users.keySet())) {
                long currentRecordMtime = safeMtime(userRecordPath(username));
                if (currentRecordMtime != userRecordMtimes.getOrDefault(username, -1L)) {
                    loadUsers();
                    return;
                }
            }

            if (users.isEmpty() && hasAnyUserRecords()) {
                loadUsers();
            }
        } catch (Exception ignored) {
        }
    }
    
    public boolean authenticate(String username, String password) {
        refreshUsersIfChanged();
        User user = users.get(User.normalizeUsername(username));
        if (user == null || !user.authenticate(password)) {
            System.out.println(ColorUtil.colorize("Authentication failed!", ColorUtil.RED));
            return false;
        }

        String welcome = user.isSuperAdmin()
                ? ColorUtil.colorize("[SUPER ADMIN] ", ColorUtil.YELLOW) + username
                : username;

        System.out.println(ColorUtil.colorize("\nWelcome ", ColorUtil.GREEN) +
                ColorUtil.colorize(welcome, ColorUtil.BOLD + ColorUtil.GREEN) +
                ColorUtil.colorize("!", ColorUtil.GREEN));
        return true;
    }

    public void addUser(User user) {
        // Allow first super admin creation, prevent additional ones
        if (user.getRole().equals("SUPER_ADMIN")) {
            if (users.values().stream().anyMatch(User::isSuperAdmin)) {
                throw new RuntimeException("Cannot create additional super admin users");
            }
            // This is the first super admin - allow it
        }
        String normalizedUsername = User.normalizeUsername(user.getUsername());
        users.put(normalizedUsername, user);
        persistUserRecord(user);
        writeUsersManifest(users.keySet());
    }
    
    public void updateUser(User user) {
        if (user.isSuperAdmin() && VDB.currentUser != null && !VDB.currentUser.isSuperAdmin()) {
            throw new RuntimeException("Cannot modify super admin user");
        }
        String normalizedUsername = User.normalizeUsername(user.getUsername());
        users.put(normalizedUsername, user);
        persistUserRecord(user);
        writeUsersManifest(users.keySet());
    }

    public User getUser(String username) {
        refreshUsersIfChanged();
        return users.get(User.normalizeUsername(username));
    }

    public List<User> listUsers() {
        refreshUsersIfChanged();
        return new ArrayList<>(users.values());
    }

    public void updateSuperAdmin(User user) {
        if (!user.isSuperAdmin()) {
            throw new RuntimeException("Only super admin can be updated via this method");
        }
        if (!User.normalizeUsername(user.getUsername()).equals(User.normalizeUsername(getSuperAdmin().getUsername()))) {
            throw new RuntimeException("Cannot replace super admin user");
        }
        String normalizedUsername = User.normalizeUsername(user.getUsername());
        users.put(normalizedUsername, user);
        persistUserRecord(user);
        writeUsersManifest(users.keySet());
    }

    public void deleteUser(String username) {
        String normalizedUsername = User.normalizeUsername(username);
        if (normalizedUsername.equals(User.normalizeUsername(getSuperAdmin().getUsername()))) {
            throw new RuntimeException("Cannot delete super admin user");
        }
        users.remove(normalizedUsername);
        try {
            Files.deleteIfExists(userRecordPath(normalizedUsername));
        } catch (IOException e) {
            throw new RuntimeException("Failed to delete user record: " + normalizedUsername, e);
        }
        userRecordMtimes.remove(normalizedUsername);
        writeUsersManifest(users.keySet());
    }

    public boolean userExists(String username) {
        refreshUsersIfChanged();
        return users.containsKey(User.normalizeUsername(username));
    }

    public boolean emailExists(String email) {
        refreshUsersIfChanged();
        return users.values().stream().anyMatch(user -> user.getEmail().equals(email));
    }

    public List<String> getDomainOwners(String domain) {
        refreshUsersIfChanged();
        return users.values().stream()
                .filter(user -> user.ownsDomain(domain))
                .map(User::getUsername)
                .collect(Collectors.toList());
    }

    // In UserManager.java
    private void createSuperAdmin() {
        Scanner scanner = new Scanner(System.in);
        System.out.println(ColorUtil.colorize("\n=== SUPER ADMIN CREATION ===", ColorUtil.CYAN));

        System.out.print(ColorUtil.colorize("Enter username: ", ColorUtil.BLUE));
        String username = scanner.nextLine();

        System.out.print(ColorUtil.colorize("Enter email: ", ColorUtil.BLUE));
        String email = scanner.nextLine();

        System.out.print(ColorUtil.colorize("Enter password: ", ColorUtil.BLUE));
        String password = scanner.nextLine();

        try {
            User superAdmin = new User(username, email, "SUPER_ADMIN", password);
            String normalizedUsername = User.normalizeUsername(username);
            addUser(superAdmin);

            // Verify insertion
            if (users.get(normalizedUsername) == null) {
                throw new RuntimeException("Super admin creation failed - not added to users map");
            }

            System.out.println(ColorUtil.colorize("\nSuper admin created successfully!", ColorUtil.GREEN));
        } catch (Exception e) {
            System.err.println("Critical error creating super admin: " + e.getMessage());
            System.exit(1);
        }
    }

    public User getSuperAdmin() {
        refreshUsersIfChanged();
        for (User user : users.values()) {
            if (user.isSuperAdmin()) {
                return user;
            }
        }
        return null;
    }

    private synchronized void saveUsers() {
        try {
            Files.createDirectories(USER_DIR);
            Set<String> existingUsernames = new LinkedHashSet<>(discoverUsernamesFromRecords());
            for (User user : users.values()) {
                persistUserRecord(user);
                existingUsernames.remove(User.normalizeUsername(user.getUsername()));
            }
            for (String staleUsername : existingUsernames) {
                Files.deleteIfExists(userRecordPath(staleUsername));
                userRecordMtimes.remove(staleUsername);
            }
            writeUsersManifest(users.keySet());
        } catch (Exception e) {
            System.err.println("CRITICAL: Failed to save users: " + e.getMessage());
            System.exit(1);
        }
    }

    private void migrateAggregateUsers(Object rawAggregate) {
        List<User> userList = gson.fromJson(gson.toJson(rawAggregate), USER_LIST_TYPE);
        users.clear();
        if (userList != null) {
            for (User user : userList) {
                if (user == null) {
                    continue;
                }
                users.put(User.normalizeUsername(user.getUsername()), user);
            }
        }
        saveUsers();
    }

    private void persistUserRecord(User user) {
        try {
            Path path = userRecordPath(user.getUsername());
            BsonStorage.writeValue(path, JsonValueConverter.convertViaJson(gson, user));
            userRecordMtimes.put(User.normalizeUsername(user.getUsername()), safeMtime(path));
        } catch (IOException e) {
            throw new RuntimeException("Failed to persist user: " + user.getUsername(), e);
        }
    }

    private User readUserRecord(String username) {
        try {
            Path path = userRecordPath(username);
            if (!Files.exists(path)) {
                return null;
            }
            Object raw = BsonStorage.readValue(path);
            return gson.fromJson(gson.toJson(raw), User.class);
        } catch (Exception e) {
            return null;
        }
    }

    private void writeUsersManifest(Collection<String> usernames) {
        try {
            Files.createDirectories(USER_DIR);
            List<String> normalized = new ArrayList<>();
            for (String username : usernames) {
                String value = User.normalizeUsername(username);
                if (!value.isEmpty() && !normalized.contains(value)) {
                    normalized.add(value);
                }
            }
            Map<String, Object> manifest = new LinkedHashMap<>();
            manifest.put(MANIFEST_USERNAMES_KEY, normalized);
            manifest.put("updated_at", System.currentTimeMillis());
            BsonStorage.writeValue(USER_DATA_PATH, manifest);
            usersFileMtime = safeMtime(USER_DATA_PATH);
        } catch (IOException e) {
            throw new RuntimeException("Failed to persist user manifest", e);
        }
    }

    private List<String> extractManifestUsernames(Object rawManifest) {
        if (!(rawManifest instanceof Map<?, ?>)) {
            return Collections.emptyList();
        }
        Object rawUsernames = ((Map<?, ?>) rawManifest).get(MANIFEST_USERNAMES_KEY);
        if (!(rawUsernames instanceof List<?>)) {
            return Collections.emptyList();
        }
        List<String> usernames = new ArrayList<>();
        for (Object entry : (List<?>) rawUsernames) {
            String username = User.normalizeUsername(String.valueOf(entry == null ? "" : entry));
            if (!username.isEmpty() && !usernames.contains(username)) {
                usernames.add(username);
            }
        }
        return usernames;
    }

    private List<String> discoverUsernamesFromRecords() {
        if (!Files.isDirectory(USER_DIR)) {
            return Collections.emptyList();
        }
        List<String> usernames = new ArrayList<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(USER_DIR, "*" + BsonStorage.DOCUMENT_EXTENSION)) {
            for (Path path : stream) {
                String filename = path.getFileName().toString();
                if (USER_DATA_PATH.getFileName().toString().equals(filename)) {
                    continue;
                }
                String username = filename.substring(0, filename.length() - BsonStorage.DOCUMENT_EXTENSION.length());
                username = User.normalizeUsername(username);
                if (!username.isEmpty()) {
                    usernames.add(username);
                }
            }
        } catch (IOException ignored) {
        }
        usernames.sort(String::compareTo);
        return usernames;
    }

    private boolean hasAnyUserRecords() {
        return !discoverUsernamesFromRecords().isEmpty();
    }

    private Path userRecordPath(String username) {
        return USER_DIR.resolve(User.normalizeUsername(username) + BsonStorage.DOCUMENT_EXTENSION);
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

}
