// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.nio.file.*;
import java.io.IOException;
import java.util.*;
import java.util.stream.Collectors;

public class DirectoryUtil {
    public static final Path VDB_ROOT = resolveVdbRoot();
    public static final Path DATA_DIR = VDB_ROOT.resolve("__data__").normalize();
    public static final Path DOMAINS_DIR = DATA_DIR.resolve("domains");
    public static final Path SCRIPTS_DIR = DATA_DIR.resolve("scripts");
    public static final Path SYS_DIR = DATA_DIR.resolve("sys");
    public static final Path SYS_DOMAINS_DIR = SYS_DIR.resolve("domains");
    public static final Path SYS_DBS_DIR = SYS_DIR.resolve("dbs");
    public static final Path INDEX_ADVISOR_DIR = SYS_DIR.resolve("index_advisor");
    public static final Path INDEX_ADVISOR_QUERY_LOG = INDEX_ADVISOR_DIR.resolve("query_log" + BsonStorage.LOG_EXTENSION);
    public static final Path INDEX_ADVISOR_STATS = INDEX_ADVISOR_DIR.resolve("stats" + BsonStorage.DOCUMENT_EXTENSION);
    public static final Path INDEX_ADVISOR_POLICY = INDEX_ADVISOR_DIR.resolve("policy" + BsonStorage.DOCUMENT_EXTENSION);

    public static final Path LOGS_DIR = Paths.get("logs");
    public static final Path VI_LOGS_DIR = LOGS_DIR.resolve("vi");
    public static final Path VDB_LOGS_DIR = LOGS_DIR.resolve("vdb");
    public static final Path SESSIONS_LOG = LOGS_DIR.resolve("sessions.log");

    static String sessionId = UUID.randomUUID().toString();
    public static VDBLogger logger;

    static {
        initializeDirectoriesAndLogger();
    }

    private static Path resolveVdbRoot() {
        String configuredRoot = System.getProperty("verun.vdb.root");
        if (configuredRoot == null || configuredRoot.isBlank()) {
            configuredRoot = System.getenv("VERUN_VDB_ROOT");
        }
        if (configuredRoot != null && !configuredRoot.isBlank()) {
            return Paths.get(configuredRoot).toAbsolutePath().normalize();
        }

        try {
            Path codeSource = Paths.get(DirectoryUtil.class.getProtectionDomain()
                    .getCodeSource()
                    .getLocation()
                    .toURI())
                    .toAbsolutePath()
                    .normalize();

            Path current = Files.isRegularFile(codeSource) ? codeSource.getParent() : codeSource;
            for (Path p = current; p != null; p = p.getParent()) {
                if (p.getFileName() != null && "vdb".equals(p.getFileName().toString())) {
                    return p;
                }
                Path candidate = p.resolve("vdb");
                if (Files.isDirectory(candidate)) {
                    return candidate.toAbsolutePath().normalize();
                }
            }
        } catch (Exception ignored) {
        }

        Path cwd = Paths.get("").toAbsolutePath().normalize();
        Path candidate = cwd.resolve("verun").resolve("vdb");
        if (Files.isDirectory(candidate)) {
            return candidate;
        }
        candidate = cwd.resolve("vdb");
        if (Files.isDirectory(candidate)) {
            return candidate;
        }
        return cwd;
    }

    private static synchronized void initializeDirectoriesAndLogger() {
        try {
            Files.createDirectories(VI_LOGS_DIR);
            Files.createDirectories(VDB_LOGS_DIR);
            if (!Files.exists(SESSIONS_LOG)) {
                Files.createFile(SESSIONS_LOG);
            }

            logger = new VDBLogger(sessionId);
        } catch (IOException e) {
            System.err.println("Failed to initialize directories/logger: " + e.getMessage());
        }
    }

    public static void ensureDirectories() {
        try {
            createDirIfNeeded(DOMAINS_DIR);
            createDirIfNeeded(SCRIPTS_DIR);
            createDirIfNeeded(SYS_DIR);
            createDirIfNeeded(SYS_DOMAINS_DIR);
            createDirIfNeeded(SYS_DBS_DIR);
            createDirIfNeeded(INDEX_ADVISOR_DIR);
        } catch (Exception e) {
            logger.log("An unexpected error occurred while ensuring directories: " + e.getMessage());
        }
    }

    private static void createDirIfNeeded(Path path) {
        if (!Files.exists(path)) {
            try {
                Files.createDirectories(path);
            } catch (IOException e) {
                logger.log("Failed to create directory: " + path + " - " + e.getMessage());
                throw new RuntimeException("Failed to create directory: " + path, e);
            } catch (Exception e) {
                logger.log("An unexpected error occurred while creating directory: " + path + " - " + e.getMessage());
                throw new RuntimeException("Failed to create directory: " + path, e);
            }
        }
    }

    public static void createDomainMetadata(String domain, User creator) throws IOException {
        Path metadataPath = getDomainMetadataPath(domain);
        Files.createDirectories(metadataPath.getParent());

        Map<String, Object> domainMetadata = new LinkedHashMap<>();
        domainMetadata.put("owner", creator.getUsername());
        domainMetadata.put("created_by", creator.getUsername());
        domainMetadata.put("created_at", System.currentTimeMillis());
        domainMetadata.put("modified_at", System.currentTimeMillis());

        BsonStorage.writeDocument(metadataPath, domainMetadata);

        // Grant ownership to creator
        creator.grantDomainOwnership(domain);

        // Always update the creator's record
        if (creator.isSuperAdmin()) {
            UserManager.getInstance().updateSuperAdmin(creator);
        } else {
            UserManager.getInstance().updateUser(creator); // Force save regular user
        }

        // Update current session's user reference if it's the same user
        if (VDB.currentUser != null &&
                VDB.currentUser.getUsername().equals(creator.getUsername())) {
            VDB.currentUser = creator; // Refresh session reference
        }
    }

    public static Path getSysDomainPath(String domain) {
        return SYS_DOMAINS_DIR.resolve(domain + BsonStorage.DOCUMENT_EXTENSION);
    }

    public static Path getSysDbPath(String domain, String db) {
        return SYS_DBS_DIR.resolve(domain + "_" + db + BsonStorage.DOCUMENT_EXTENSION);
    }

    public static boolean domainExists(String domain) {
        return Files.exists(DOMAINS_DIR.resolve(normalizeDomainName(domain)));
    }

    public static boolean dbExists(String domain, String db) {
        return Files.exists(getDbPath(domain, db));
    }

    public static void ensureDbExists(String domain, String db) throws IOException {
        Path dbPath = getDbPath(domain, db);
        if (!Files.exists(dbPath)) {
            throw new IOException("Database not found in domain");
        }
        Files.createDirectories(dbPath.resolve("collections"));
    }

    public static List<String> getDatabases(String domain) {
        List<String> databases = new ArrayList<>();
        Path domainPath = getDomainPath(domain);
        Path dbsPath = domainPath.resolve("dbs");
        try {
            Files.createDirectories(dbsPath); // Ensure the directory exists
            try (DirectoryStream<Path> stream = Files.newDirectoryStream(dbsPath)) {
                for (Path path : stream) {
                    if (Files.isDirectory(path)) {
                        databases.add(path.getFileName().toString());
                    }
                }
            }
        } catch (IOException e) {
            logger.log("Failed to list databases in domain " + domain + ": " + e.getMessage());
            throw new RuntimeException("Failed to list databases", e);
        }
        return databases;
    }

    public static List<String> getCollections(String domain, String dbName) {
        List<String> collections = new ArrayList<>();
        Path dbPath = getDbPath(domain, dbName);
        Path collectionsDir = dbPath.resolve("collections");
        if (!Files.exists(collectionsDir)) {
            return collections; // Return empty list if no collections
        }

        try (DirectoryStream<Path> stream = Files.newDirectoryStream(collectionsDir)) {
            for (Path path : stream) {
                if (Files.isDirectory(path)) {
                    collections.add(path.getFileName().toString());
                }
            }
        } catch (IOException e) {
            logger.log("Failed to list collections: " + e.getMessage());
        }
        return collections;
    }

    public static void deleteDomain(String domain) throws IOException {
        Path domainPath = getDomainPath(domain);
        if (!Files.exists(domainPath)) {
            throw new IOException("Domain directory not found: " + domain);
        }

        // Delete all databases in the domain first
        List<String> databases = getDatabases(domain);
        for (String db : databases) {
            deleteDatabase(domain, db);
        }

        // Delete the domain directory and sys entry
        deleteDirectory(domainPath);
        Files.deleteIfExists(getSysDomainPath(domain));
    }

    public static void deleteDirectory(Path path) throws IOException {
        if (Files.exists(path)) {
            Files.walk(path)
                    .sorted(Comparator.reverseOrder())
                    .forEach(p -> {
                        try {
                            Files.delete(p);
                        } catch (IOException e) {
                            throw new RuntimeException("Failed to delete: " + p, e);
                        }
                    });
        }
    }

    public static Path getDomainPath(String domain) {
        domain = normalizeDomainName(domain);
        Path path = DOMAINS_DIR.resolve(domain);
        if (!Files.exists(path)) {
            try {
                Files.createDirectories(path);
            } catch (IOException e) {
                logger.log("Domain directory creation failed: " + e.getMessage());
            }
        }
        return path;
    }

    public static Path getDomainScriptsPath(String domain) {
        return getDomainPath(domain).resolve("scripts");
    }

    public static Path getDbPath(String domain, String db) {
        return getDomainPath(domain).resolve("dbs").resolve(db);
    }

    public static Path getCollectionPath(String domain, String db, String collection) {
        return getDbPath(domain, db).resolve("collections").resolve(collection);
    }

    public static Path getCollectionSysPath(String domain, String db, String collection) {
        return getCollectionPath(domain, db, collection).resolve("sys");
    }

    public static Path getCollectionDataPath(String domain, String db, String collection) {
        return getCollectionPath(domain, db, collection).resolve("data");
    }

    public static Path getIndexPath(String domain, String db, String collection, String field) {
        return getCollectionSysPath(domain, db, collection)
                .resolve(field + "_index" + BsonStorage.DOCUMENT_EXTENSION);
    }

    public static void ensureCollectionDirs(String domain, String db, String collection) throws IOException {
        Path dbPath = getDbPath(domain, db);
        Path collectionsDir = dbPath.resolve("collections");
        if (!Files.exists(collectionsDir)) {
            Files.createDirectories(collectionsDir);
        }
        Path sysPath = getCollectionSysPath(domain, db, collection);
        Path dataPath = getCollectionDataPath(domain, db, collection);
        Files.createDirectories(sysPath);
        Files.createDirectories(dataPath);
    }

    public static void deleteDatabase(String domain, String db) throws IOException {
        deleteDirectory(getDbPath(domain, db));
    }

    public static List<String> getDomains() {
        List<String> domains = new ArrayList<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(DOMAINS_DIR)) {
            for (Path path : stream) {
                if (Files.isDirectory(path)) {
                    domains.add(path.getFileName().toString());
                }
            }
        } catch (IOException e) {
            logger.log("Failed to list domains: " + e.getMessage());
        }
        return domains;
    }

    public static List<String> getUsersInDomain(String currentDomain) {
        List<String> users = new ArrayList<>();
        Path usersPath = SYS_DIR.resolve("users");
        try {
            if (Files.exists(usersPath)) {
                try (DirectoryStream<Path> stream = Files.newDirectoryStream(usersPath)) {
                    for (Path path : stream) {
                        if (Files.isDirectory(path)) {
                            users.add(path.getFileName().toString());
                        }
                    }
                }
            }
        } catch (IOException e) {
            logger.log("Failed to list users in domain " + currentDomain + ": " + e.getMessage());
        }
        return users;
    }

    public static void createDomain(String domain, User creator) throws IOException {
        domain = normalizeDomainName(domain);
        Path domainPath = DOMAINS_DIR.resolve(domain);

        if (Files.exists(domainPath) && isDomainStructureComplete(domainPath)) {
            throw new IOException("Domain already exists");
        }

        if (Files.exists(domainPath)) {
            logger.log("Repairing incomplete domain structure: " + domain);
        }

        // Create or repair domain structure.
        Files.createDirectories(domainPath);

        // Create sys directory with mandatory files
        Path sysDir = domainPath.resolve("sys");
        Files.createDirectories(sysDir);

        Path metadataPath = getDomainMetadataPath(domain);
        if (!Files.isRegularFile(metadataPath)) {
            Map<String, Object> domainMetadata = new LinkedHashMap<>();
            domainMetadata.put("owner", creator.getUsername());
            domainMetadata.put("created_by", creator.getUsername());
            domainMetadata.put("created_at", System.currentTimeMillis());
            domainMetadata.put("modified_at", System.currentTimeMillis());
            BsonStorage.writeDocument(metadataPath, domainMetadata);
        }

        Path configPath = getDomainConfigPath(domain);
        if (!Files.isRegularFile(configPath)) {
            Map<String, String> config = new HashMap<>();
            config.put("default_db", "main");
            BsonStorage.writeValue(configPath, config);
        }

        // Create or repair default database
        Path dbPath = domainPath.resolve("dbs/main");
        Files.createDirectories(dbPath);

        Path dbMetadataPath = getDbMetadataPath(domain, "main");
        if (!Files.isRegularFile(dbMetadataPath)) {
            Map<String, Object> dbMetadata = new LinkedHashMap<>();
            dbMetadata.put("owner", creator.getUsername());
            dbMetadata.put("created_at", System.currentTimeMillis());
            BsonStorage.writeDocument(dbMetadataPath, dbMetadata);
        }

        // Update ownership
        creator.grantDomainOwnership(domain);
        if (creator.isSuperAdmin()) {
            UserManager.getInstance().updateSuperAdmin(creator);
        } else {
            UserManager.getInstance().updateUser(creator);
        }
    }

    private static boolean isDomainStructureComplete(Path domainPath) {
        Path sysDir = domainPath.resolve("sys");
        Path metadataPath = sysDir.resolve("metadata" + BsonStorage.DOCUMENT_EXTENSION);
        Path configPath = sysDir.resolve("config" + BsonStorage.DOCUMENT_EXTENSION);
        Path dbPath = domainPath.resolve("dbs").resolve("main");
        Path dbMetadataPath = dbPath.resolve("metadata" + BsonStorage.DOCUMENT_EXTENSION);
        return Files.isRegularFile(metadataPath)
                && Files.isRegularFile(configPath)
                && Files.isDirectory(dbPath)
                && Files.isRegularFile(dbMetadataPath);
    }

    public static String normalizeDomainName(String domain) {
        String normalized = String.valueOf(domain == null ? "" : domain).trim().toLowerCase(Locale.ROOT)
                .replaceAll("[\\s\\-]+", "_")
                .replaceAll("[^a-z0-9_]", "_")
                .replaceAll("_+", "_");
        normalized = normalized.replaceAll("^_+", "").replaceAll("_+$", "");
        return normalized.isEmpty() ? "default" : normalized;
    }
    
    public static boolean userExists(String username) {
        Path userPath = SYS_DIR.resolve("users").resolve(User.normalizeUsername(username) + BsonStorage.DOCUMENT_EXTENSION);
        return Files.exists(userPath);
    }

    public static Path getUserPath(String username) {
        if (!userExists(username)) {
            throw new IllegalArgumentException("User does not exist: " + username);
        }
        return SYS_DIR.resolve("users").resolve(User.normalizeUsername(username) + BsonStorage.DOCUMENT_EXTENSION);
    }

    public static Path getDomainMetadataPath(String domain) {
        return getDomainPath(domain).resolve("sys").resolve("metadata" + BsonStorage.DOCUMENT_EXTENSION);
    }

    public static Path getDomainConfigPath(String domain) {
        return getDomainPath(domain).resolve("sys").resolve("config" + BsonStorage.DOCUMENT_EXTENSION);
    }

    public static Path getDbMetadataPath(String domain, String db) {
        return getDbPath(domain, db).resolve("metadata" + BsonStorage.DOCUMENT_EXTENSION);
    }

    public static Path getCollectionModelPath(String domain, String db, String collection) {
        return getCollectionSysPath(domain, db, collection).resolve("model" + BsonStorage.DOCUMENT_EXTENSION);
    }

    public static Path getCollectionIndexDefinitionsPath(String domain, String db, String collection) {
        return getCollectionSysPath(domain, db, collection).resolve("indexes" + BsonStorage.DOCUMENT_EXTENSION);
    }

    public static Path getUsersStorePath() {
        return SYS_DIR.resolve("users").resolve("users" + BsonStorage.DOCUMENT_EXTENSION);
    }

    public static Path getRolesStorePath() {
        return SYS_DIR.resolve("roles").resolve("roles" + BsonStorage.DOCUMENT_EXTENSION);
    }

    public static Path getRolePath(String roleName) {
        return SYS_DIR.resolve("roles").resolve(String.valueOf(roleName == null ? "" : roleName).trim().toUpperCase(Locale.ROOT) + BsonStorage.DOCUMENT_EXTENSION);
    }

    public static Path getScriptPath(String name) {
        return SCRIPTS_DIR.resolve(name + BsonStorage.DOCUMENT_EXTENSION);
    }
}
