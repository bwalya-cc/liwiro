// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.util.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.io.IOException;
import java.util.stream.Collectors;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import com.google.gson.JsonObject;
import verun.common.JsonValueConverter;

public class VDB {
    private static final Gson gson = new Gson();
    private static final boolean CONSOLE_LOGS_ENABLED = VDBLogSettings.isConsoleLogsEnabled();
    private static String currentDomain = "default";
    private static String currentDB = "";
    protected static User currentUser;
    protected static VDBLogger logger;
    private static volatile boolean runtimeLogsEnabled = false;
    private static final String SCRIPT_EXTENSION = ".versa";

    // In-memory stores
    private static final Map<String, Map<String, Object>> collections = new HashMap<>();
    protected static final Map<String, User> users = new HashMap<>();
    protected static Map<String, ScriptDocument> scriptStore = new HashMap<>();
    public static Map<String, String> nameIndex = new HashMap<>();
    private static final Map<String, CachedValue<Map<String, Object>>> schemaCache = new HashMap<>();
    private static final Map<String, CachedValue<Map<String, Object>>> indexDefinitionCache = new HashMap<>();
    private static final Map<String, CachedValue<Map<String, List<String>>>> indexBucketCache = new HashMap<>();

    static {
        try {
            DirectoryUtil.ensureDirectories();
            logger = DirectoryUtil.logger;
            VDB.initialize(); // Initial initialization
        } catch (IllegalStateException e) {
            System.out.println("Super admin not configured. Creating initial admin...");
            VDB.checkSuperAdmin();
        } catch (Exception e) {
            System.err.println("Directory initialization failed: " + e.getMessage());
        }
        Runtime.getRuntime().addShutdownHook(new Thread(VDB::cleanupTransactionSnapshots, "verun-vdb-tx-cleanup"));
    }

    private static void cleanupTransactionSnapshots() {
        for (Path snapshot : new ArrayList<>(transactionSnapshots.values())) {
            try { clearPath(snapshot); } catch (Exception ignored) { }
        }
        transactionSnapshots.clear();
    }

    public static boolean hasPermission(String operation) {
        if (currentUser == null) {
            return false;
        }
        // Allow certain operations without explicit permission
        if (operation.equals("WHOAMI") ||
                operation.equals("CONTEXT") ||
                operation.equals("ECHO") ||
                operation.equals("LIST_DOMAINS") ||
                operation.equals("DEFINE_DOMAIN")) {
            return true;
        }

        if (currentUser.isSuperAdmin()) {
            return true;
        }

        // Check if the user owns the domain
        if (currentUser.ownsDomain(currentDomain)) {
            return true;
        }

        return currentUser.hasPermission(currentDomain, currentDB, operation);
    }

    public static Map<String, Object> update(String collectionName, String id, Map<String, Object> updateData) {

        // Ensure collection exists and is loaded
        if (!collectionExists(collectionName)) {
            throw new RuntimeException("Collection '" + collectionName + "' not found");
        }
        Map<String, Object> coll = collections.computeIfAbsent(collectionName, k -> new HashMap<>());

        if (!coll.containsKey(id)) {
            throw new RuntimeException("Document with id " + id + " not found in collection " + collectionName);
        }

        // Cast the document to Map<String, Object>
        Map<String, Object> existingDoc = (Map<String, Object>) coll.get(id);

        Map<String, Object> candidate = new HashMap<>(existingDoc);
        if (updateData != null) {
            candidate.putAll(updateData);
        }
        candidate.put("_id", id);
        validateDocumentAgainstSchema(collectionName, candidate, id);
        existingDoc.clear();
        existingDoc.putAll(candidate);

        // Persist the updated document
        try {
            persistDocument(collectionName, existingDoc);
        } catch (Exception e) {
            System.err.println("ERROR: Failed to persist document: " + e.getMessage());
            throw e;
        }

        return existingDoc;

    }

    public static String defineDomain(String domainName, String dbName, boolean use) {
        try {
            String normalizedDomain = DirectoryUtil.normalizeDomainName(domainName);
            User creator = currentUser != null ? currentUser : UserManager.getInstance().getSuperAdmin();
            String finalDBName = (dbName != null && !dbName.isEmpty()) ? dbName : "main";

            // Check if domain exists without creating the directory
            Path domainPath = DirectoryUtil.DOMAINS_DIR.resolve(normalizedDomain);
            if (!Files.exists(domainPath)) {
                DirectoryUtil.createDomain(normalizedDomain, creator);
            }
            domainPath = DirectoryUtil.getDomainPath(normalizedDomain); // Ensure proper path handling after creation

            // Ensure the database exists
            Path dbPath = domainPath.resolve("dbs").resolve(finalDBName);
            if (!Files.exists(dbPath)) {
                Files.createDirectories(dbPath);
                Map<String, Object> dbMeta = new HashMap<>();
                dbMeta.put("owner", creator.getUsername());
                dbMeta.put("created_at", System.currentTimeMillis());
                BsonStorage.writeDocument(DirectoryUtil.getDbMetadataPath(normalizedDomain, finalDBName), dbMeta);
            }

            // Update domain config to set default_db
            Path configPath = DirectoryUtil.getDomainConfigPath(normalizedDomain);
            Files.createDirectories(configPath.getParent());
            Map<String, String> config = new HashMap<>();
            config.put("default_db", finalDBName);
            BsonStorage.writeValue(configPath, config);

            // Update current context if needed
            if (use) {
                setDomain(normalizedDomain);
                useDatabase(finalDBName);
            }

            // Grant ownership to creator if super admin
            if (creator.isSuperAdmin()) {
                creator.grantDomainOwnership(normalizedDomain);
                UserManager.getInstance().updateSuperAdmin(creator);
            }

            return "Domain defined: " + normalizedDomain + " with database '" + finalDBName + "'";
        } catch (IOException e) {
            throw new RuntimeException("Domain creation failed: " + e.getMessage());
        }
    }

    private static void verifySystemPaths() throws IOException {
        Path[] criticalPaths = {
                DirectoryUtil.getDomainPath("default"),
                DirectoryUtil.getDomainPath("default").resolve("dbs/main"),
                DirectoryUtil.getDomainConfigPath("default"),
                DirectoryUtil.getDomainMetadataPath("default")
        };

        for (Path path : criticalPaths) {
            if (!Files.exists(path)) {
                throw new IOException("Critical system path missing: " + path);
            }
        }
    }

    protected static void initialize() {
        try {
            // Set context to default
            setDomain("default");
            
            // Check if database exists, create if not
            if (!dbExists("main")) {
                // Create default domain and database if they don't exist
                if (!domainExists("default")) {
                    // We need to defer this to avoid circular dependency
                    // Domain creation will be handled by UserManager or on first user login
                    System.out.println("First time initialization: Domain and database will be created on first login");
                } else {
                    // Domain exists but database doesn't - create it
                    createDatabase("main");
                }
            }
            
            // Now we can safely use the database
            useDatabase("main");

            // Verify initialization
            if (!domainExists("default")) {
                throw new RuntimeException("Default domain initialization failed");
            }
        } catch (Exception e) {
            System.err.println("VDB initialization failed: ");
            e.printStackTrace();
            System.exit(1);
        }
    }

    protected static void checkSuperAdmin() {
        UserManager userManager = UserManager.getInstance();
        userManager.ensureSuperAdminExists();
    }

    public static boolean authenticate(String username) {
        return users.containsKey(username);
    }

    public static Map<String, Object> insertDocument(String collectionName, Map<String, Object> doc) {
        if (!hasPermission("WRITE")) {
            throw new RuntimeException("Write permission denied");
        }

        Map<String, Object> schema = getSchema(collectionName);
        if (schema != null) {
            validateDocument(doc, schema);
        }
        return insert(collectionName, doc);
    }

    private static Map<String, Object> getSchema(String collectionName) {
        Path modelFile = DirectoryUtil.getCollectionModelPath(currentDomain, currentDB, collectionName);
        try {
            return readCachedMapIfExists(modelFile, schemaCache);
        } catch (Exception e) {
            return null;
        }
    }

    private static void persistScript(ScriptDocument doc) {
        Path filePath = DirectoryUtil.getScriptPath(doc.name);
        try {
            Files.createDirectories(DirectoryUtil.SCRIPTS_DIR);
            BsonStorage.writeValue(filePath, JsonValueConverter.fromJson(doc.toJSON()));
            nameIndex.put(doc.name, doc.name);
            scriptStore.put(doc.name, doc);
            log("SCRIPT_PERSIST", "Saved script " + doc.name + " (" + doc.extension + ")");
        } catch (IOException e) {
            throw new RuntimeException("Failed to persist script " + doc.name, e);
        }
    }

    public static ScriptDocument getScript(String name) {
        loadScriptsFromDisk();
        if (nameIndex.containsKey(name)) {
            String id = nameIndex.get(name);
            return scriptStore.get(id);
        } else {
            throw new RuntimeException("Script not found: " + name);
        }
    }

    private static void validateDocument(Map<String, Object> doc, Map<String, Object> schema) {
        for (Map.Entry<String, Object> entry : schema.entrySet()) {
            String field = entry.getKey();
            Map<String, Object> rules = (Map<String, Object>) entry.getValue();
            if (Boolean.TRUE.equals(rules.get("required")) && !doc.containsKey(field)) {
                throw new RuntimeException("Missing required field: " + field);
            }

            String type = (String) rules.get("type");
            Object value = doc.get(field);
            if (value != null && !isValidType(value, type)) {
                throw new RuntimeException("Invalid type for field '" + field + "'. Expected " + type);
            }

            if (type.equals("object") && rules.containsKey("properties")) {
                Map<String, Object> nestedSchema = (Map<String, Object>) rules.get("properties");
                validateDocument((Map<String, Object>) value, nestedSchema);
            }
        }
    }

    private static boolean isValidType(Object value, String type) {
        switch (type) {
            case "string":
                return value instanceof String;
            case "int":
                return value instanceof Integer;
            case "float":
                return value instanceof Float || value instanceof Double;
            case "bool":
                return value instanceof Boolean;
            default:
                return true;
        }
    }

    public static boolean collectionExists(String domain, String db, String collectionName) {
        Path collPath = DirectoryUtil.getCollectionPath(domain, db, collectionName);
        if (!Files.exists(collPath)) {
            logInfo("Collection " + collectionName + " does not exist in domain " + domain + ", database " + db);
        }
        return Files.exists(collPath);
    }

    public static void createCollection(String name) {
        createCollection(name, null);
    }

    public static void createDatabase(String dbName) {
        try {
            Path dbPath = DirectoryUtil.getDbPath(currentDomain, dbName);
            if (Files.exists(dbPath)) {
                throw new RuntimeException("Database already exists");
            }
            Files.createDirectories(dbPath);
        } catch (IOException e) {
            throw new RuntimeException("Database creation failed: " + e.getMessage());
        }
    }

    public static void deleteDomain(String domain) {
        try {
            DirectoryUtil.deleteDomain(domain);
        } catch (IOException e) {
            throw new RuntimeException("Domain deletion failed: " + e.getMessage());
        }
    }

    public static void deleteDatabase(String domain, String db) {
        try {
            DirectoryUtil.deleteDatabase(domain, db);
        } catch (IOException e) {
            throw new RuntimeException("Database deletion failed: " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        logInfo("VersaDB engine starting up...");
    }

    private static final Map<String, Map<String, Boolean>> transactionStates = new HashMap<>();
    private static final Map<String, Path> transactionSnapshots = new HashMap<>();

    private static String transactionKey(String domain, String db) { return String.valueOf(domain) + "\u0000" + String.valueOf(db); }

    private static void snapshotTransaction(String domain, String db) {
        String key = transactionKey(domain, db);
        if (transactionSnapshots.containsKey(key)) return;
        try {
            Path source = DirectoryUtil.getDbPath(domain, db);
            Path snapshot = Files.createTempDirectory("verun-vdb-tx-");
            if (Files.exists(source)) {
                try (var paths = Files.walk(source)) {
                    paths.forEach(path -> {
                        try {
                            Path target = snapshot.resolve(source.relativize(path).toString());
                            if (Files.isDirectory(path)) Files.createDirectories(target);
                            else Files.copy(path, target, StandardCopyOption.REPLACE_EXISTING);
                        } catch (IOException e) { throw new RuntimeException(e); }
                    });
                }
            }
            transactionSnapshots.put(key, snapshot);
        } catch (IOException e) { throw new RuntimeException("Unable to begin transaction", e); }
    }

    private static void clearPath(Path path) throws IOException {
        if (!Files.exists(path)) return;
        try (var paths = Files.walk(path)) { paths.sorted(Comparator.reverseOrder()).forEach(p -> { try { Files.deleteIfExists(p); } catch (IOException e) { throw new RuntimeException(e); } }); }
    }

    public static synchronized void beginTransaction(String domain, String db) {
        snapshotTransaction(domain, db);
        transactionStates.computeIfAbsent(domain, k -> new HashMap<>())
                .put(db, true);
    }

    public static synchronized void commitTransaction(String domain, String db) {
        if (transactionStates.containsKey(domain) && transactionStates.get(domain).containsKey(db)) {
            transactionStates.get(domain).remove(db);
        }
        Path snapshot = transactionSnapshots.remove(transactionKey(domain, db));
        if (snapshot != null) try { clearPath(snapshot); } catch (IOException ignored) { }
    }

    public static synchronized void abortTransaction(String domain, String db) {
        if (transactionStates.containsKey(domain) && transactionStates.get(domain).containsKey(db)) {
            transactionStates.get(domain).remove(db);
        }
        Path snapshot = transactionSnapshots.remove(transactionKey(domain, db));
        if (snapshot != null) try {
            Path target = DirectoryUtil.getDbPath(domain, db);
            clearPath(target);
            Files.createDirectories(target);
            try (var paths = Files.walk(snapshot)) {
                paths.forEach(path -> {
                    try {
                        Path restored = target.resolve(snapshot.relativize(path).toString());
                        if (Files.isDirectory(path)) Files.createDirectories(restored);
                        else Files.copy(path, restored, StandardCopyOption.REPLACE_EXISTING);
                    } catch (IOException e) { throw new RuntimeException(e); }
                });
            }
            clearPath(snapshot);
            collections.clear();
        } catch (IOException e) { throw new RuntimeException("Unable to rollback transaction", e); }
    }

    public static String create(String collectionName) {
        try {
            createCollection(collectionName);
            return "Collection created: " + collectionName;
        } catch (Exception e) {
            throw new RuntimeException("Failed to create collection: " + e.getMessage(), e);
        }
    }

    public static String create(String collectionName, Class<?> collectionClass) {
        if (collectionClass == null) {
            return create(collectionName);
        }
        try {
            Map<String, Object> schema = getSchemaFromClass(collectionClass);
            createCollection(collectionName, schema);
            return "Collection created: " + collectionName;
        } catch (Exception e) {
            throw new RuntimeException("Failed to create collection: " + e.getMessage(), e);
        }
    }

    public static Map<String, Object> getCollection(String collectionName) {
        if (!collectionExists(collectionName)) {
            createCollection(collectionName);
        } else {
            collections.computeIfAbsent(collectionName, k -> new HashMap<>());
        }
        return collections.get(collectionName);
    }

    public static Map<String, Object> insert(String collectionName, Map<String, Object> document) {
        if (!collectionExists(collectionName)) {
            throw new RuntimeException("Collection '" + collectionName + "' not found in database '" + currentDB + "'");
        }

        Map<String, Object> storedDocument = new LinkedHashMap<>(document == null ? Collections.emptyMap() : document);
        validateDocumentAgainstSchema(collectionName, storedDocument);

        String id = UUID.randomUUID().toString();
        storedDocument.put("_id", id);
        Map<String, Object> coll = collections.computeIfAbsent(collectionName, k -> new HashMap<>());
        coll.put(id, storedDocument);
        persistDocument(collectionName, storedDocument);
        rebuildIndexesForCollection(collectionName);
        log("INSERT", "Inserted document in " + collectionName + " id=" + id);
        return storedDocument;
    }

    public static List<Map<String, Object>> find(String collectionName, Map<String, Object> query, int limit) {
        if (!collectionExists(collectionName)) {
            throw new RuntimeException("Collection '" + collectionName + "' not found in database '" + currentDB + "'");
        }
        long started = System.nanoTime();

        Map<String, Object> coll = collections.computeIfAbsent(collectionName, k -> new HashMap<>());
        if (coll.isEmpty()) {
            findAll(collectionName); // Loads the collection into memory
            coll = collections.get(collectionName);
        }
        int totalDocs = coll.size();
        IndexLookupResult indexLookup = resolveIndexedCandidates(collectionName, query);
        Set<String> candidateIds = indexLookup.ids;
        Map<String, Object> source = coll;
        if (candidateIds != null) {
            source = new HashMap<>();
            for (String id : candidateIds) {
                Object doc = coll.get(id);
                if (doc != null) {
                    source.put(id, doc);
                }
            }
        }
        int scannedDocs = source.size();
        List<Map<String, Object>> results = new ArrayList<>();
        for (Map.Entry<String, Object> entry : source.entrySet()) {
            Map<String, Object> document = (Map<String, Object>) entry.getValue();
            if (QueryEvaluator.matches(document, query)) {
                results.add(document);
                if (results.size() >= limit) {
                    break;
                }
            }
        }
        long elapsed = System.nanoTime() - started;
        IndexAdvisor.recordFind(
                currentDomain,
                currentDB,
                collectionName,
                query == null ? Collections.emptyMap() : query,
                totalDocs,
                scannedDocs,
                indexLookup.usedFields,
                elapsed);
        if (candidateIds != null) {
            log("FIND_INDEX",
                    "collection=" + collectionName
                            + " total=" + totalDocs
                            + " scanned=" + scannedDocs
                            + " matched=" + results.size()
                            + " used_fields=" + indexLookup.usedFields);
        } else {
            log("FIND_SCAN",
                    "collection=" + collectionName
                            + " total=" + totalDocs
                            + " scanned=" + scannedDocs
                            + " matched=" + results.size());
        }
        return results;
    }

    // In VDB.java (ensure this method exists)
    public static Map<String, Object> findById(String collectionName, String id) {
        if (!collectionExists(collectionName)) {
            return null;
        }
        Map<String, Object> coll = collections.computeIfAbsent(collectionName, k -> new HashMap<>());
        return (Map<String, Object>) coll.get(id);
    }

    public static String update(String collectionName, Map<String, Object> query, Map<String, Object> updateData) {

        // Ensure collection exists and is loaded
        if (!collectionExists(collectionName)) {
            throw new RuntimeException(
                    "Collection '" + collectionName + "' not found in current database '" + currentDB + "'");
        }
        Map<String, Object> coll = collections.computeIfAbsent(collectionName, k -> new HashMap<>());

        int updatedCount = 0;

        for (Map.Entry<String, Object> entry : new HashMap<>(coll).entrySet()) {
            Map<String, Object> document = (Map<String, Object>) entry.getValue();
            if (QueryEvaluator.matches(document, query)) {
                Map<String, Object> candidate = new HashMap<>(document);
                if (updateData != null) {
                    candidate.putAll(updateData);
                }
                Object existingId = document.get("_id");
                if (existingId != null) {
                    candidate.put("_id", existingId);
                }
                validateDocumentAgainstSchema(collectionName, candidate, existingId == null ? null : String.valueOf(existingId));
                document.clear();
                document.putAll(candidate);
                coll.put(entry.getKey(), document);
                persistDocument(collectionName, document);
                updatedCount++;
            }
        }
        if (updatedCount > 0) {
            rebuildIndexesForCollection(collectionName);
        }

        return "Updated " + updatedCount + " documents";
    }

    // In VDB.java
    public static void delete(String collectionName, String id) {
        if (!collectionExists(collectionName)) {
            throw new RuntimeException("Collection not found: " + collectionName);
        }
        Map<String, Object> coll = collections.computeIfAbsent(collectionName, k -> new HashMap<>());
        coll.remove(id);
        deleteDocumentFile(collectionName, id);
        rebuildIndexesForCollection(collectionName);
    }

    public static String delete(String collectionName, Map<String, Object> query) {
        if (!collectionExists(collectionName)) {
            throw new RuntimeException(
                    "Collection '" + collectionName + "' not found in current database '" + currentDB + "'");
        }

        Map<String, Object> coll = collections.computeIfAbsent(collectionName, k -> new HashMap<>());
        int deletedCount = 0;

        for (Iterator<Map.Entry<String, Object>> it = coll.entrySet().iterator(); it.hasNext();) {
            Map.Entry<String, Object> entry = it.next();
            Map<String, Object> document = (Map<String, Object>) entry.getValue();
            if (QueryEvaluator.matches(document, query)) {
                it.remove();
                deleteDocumentFile(collectionName, entry.getKey());
                deletedCount++;
            }
        }
        if (deletedCount > 0) {
            rebuildIndexesForCollection(collectionName);
        }

        return "Deleted " + deletedCount + " documents";
    }

    public static List<String> listCollections() {
        return DirectoryUtil.getCollections(currentDomain, currentDB);
    }

    public static List<String> listDatabases() {
        return DirectoryUtil.getDatabases(currentDomain);
    }

    public static void drop(String collectionName) {
        collections.remove(collectionName);
        deleteCollectionFolder(collectionName);
    }

    public static void useDomain(String domainName) {
        String normalizedDomain = DirectoryUtil.normalizeDomainName(domainName);
        if (!domainExists(normalizedDomain)) {
            throw new RuntimeException("Domain does not exist: " + normalizedDomain);
        }
        setDomain(normalizedDomain);
    }

    public static void useDatabase(String dbName) {
        if (!dbExists(dbName)) {
            throw new RuntimeException("Database does not exist in domain " + currentDomain + ": " + dbName);
        }
        currentDB = dbName;
    }

    public static String tumi(Map<String, Object> tumiCmd) {
        Tumi tumiProcessor = new Tumi(currentUser, currentDomain, currentDB);
        JsonObject command = new Gson().toJsonTree(tumiCmd).getAsJsonObject();
        // The public VI/JVM bridge follows the same flat action contract as
        // HTTP, sockets, and the console. Tumi's nested operation object is
        // an internal implementation detail and must not leak back into the
        // runtime-facing API.
        CommandValidator.validateCommandStructure(command);
        // Keep the public VI bridge on the same flat action contract as the
        // HTTP/console VDB surfaces, while adapting once to Tumi's internal
        // operation dispatcher.
        if (command.has("action") && "tumi".equalsIgnoreCase(command.get("action").getAsString())) {
            String operation = command.has("operation") ? command.get("operation").getAsString() : "";
            JsonObject payload = command.deepCopy();
            payload.remove("action");
            payload.remove("operation");
            if ("list".equalsIgnoreCase(operation) && command.has("resource")) {
                payload.add("list", command.get("resource"));
                command = payload;
            } else if (!operation.isBlank()) {
                JsonObject nested = new JsonObject();
                nested.add(operation.toLowerCase(java.util.Locale.ROOT), payload);
                command = nested;
            }
        }
        return tumiProcessor.processCommand(command);
    }

    public static ScriptDocument saveScript(String name, String service, String code) {
        ScriptDocument existing = null;
        try {
            existing = loadScript(name);
        } catch (RuntimeException ignored) {
            // no-op
        }

        ScriptDocument doc = existing != null
                ? existing
                : new ScriptDocument(name, service, code, "Versa", SCRIPT_EXTENSION);
        doc.serviceName = service;
        doc.updateCode(code);
        doc.extension = SCRIPT_EXTENSION;
        doc.language = "Versa";
        persistScript(doc);
        return doc;
    }

    public static ScriptDocument loadScript(String name) {
        loadScriptsFromDisk();
        if (nameIndex.containsKey(name)) {
            String id = nameIndex.get(name);
            return scriptStore.get(id);
        } else {
            throw new RuntimeException("Script not found: " + name);
        }
    }

    public static List<Map<String, Object>> aggregate(String collectionName, List<Map<String, Object>> pipeline) {
        List<Map<String, Object>> results = new ArrayList<>(findAll(collectionName));
        if (pipeline == null) return results;
        for (Map<String, Object> stage : pipeline) {
            if (stage == null || stage.isEmpty()) continue;
            if (stage.containsKey("$match") && stage.get("$match") instanceof Map) {
                Map<String, Object> match = (Map<String, Object>) stage.get("$match");
                results.removeIf(doc -> !QueryEvaluator.matches(doc, match));
            } else if (stage.containsKey("$limit")) {
                int n = Math.max(0, toInt(stage.get("$limit")));
                if (results.size() > n) results = new ArrayList<>(results.subList(0, n));
            } else if (stage.containsKey("$skip")) {
                int n = Math.min(results.size(), Math.max(0, toInt(stage.get("$skip"))));
                results = new ArrayList<>(results.subList(n, results.size()));
            } else if (stage.containsKey("$project") && stage.get("$project") instanceof Map) {
                Map<String, Object> projection = (Map<String, Object>) stage.get("$project");
                results = results.stream().map(doc -> {
                    Map<String, Object> projected = new LinkedHashMap<>();
                    projection.forEach((field, include) -> { if (Boolean.TRUE.equals(include) || (include instanceof Number && ((Number) include).intValue() != 0)) if (doc.containsKey(field)) projected.put(field, doc.get(field)); });
                    return projected;
                }).collect(Collectors.toList());
            } else if (stage.containsKey("$sort") && stage.get("$sort") instanceof Map) {
                Map<String, Object> sort = (Map<String, Object>) stage.get("$sort");
                results.sort((a, b) -> { for (Map.Entry<String, Object> e : sort.entrySet()) { int c = compareValues(a.get(e.getKey()), b.get(e.getKey())); if (c != 0) return toInt(e.getValue()) < 0 ? -c : c; } return 0; });
            } else {
                throw new IllegalArgumentException("Unsupported aggregation stage: " + stage.keySet());
            }
        }
        return results;
    }

    private static int compareValues(Object a, Object b) {
        if (a == b) return 0; if (a == null) return -1; if (b == null) return 1;
        if (a instanceof Number && b instanceof Number) return Double.compare(((Number)a).doubleValue(), ((Number)b).doubleValue());
        return String.valueOf(a).compareTo(String.valueOf(b));
    }

    private static int toInt(Object value) {
        if (value instanceof Number) return ((Number) value).intValue();
        try { return Integer.parseInt(String.valueOf(value)); } catch (Exception ignored) { return 0; }
    }

    public static synchronized void beginTransaction() {
        snapshotTransaction(currentDomain, currentDB);
        transactionStates.computeIfAbsent(currentDomain, k -> new HashMap<>())
                .put(currentDB, true);
    }

    public static synchronized void commitTransaction() {
        if (transactionStates.containsKey(currentDomain)
                && transactionStates.get(currentDomain).containsKey(currentDB)) {
            transactionStates.get(currentDomain).remove(currentDB);
        }
        Path snapshot = transactionSnapshots.remove(transactionKey(currentDomain, currentDB));
        if (snapshot != null) try { clearPath(snapshot); } catch (IOException ignored) { }
    }

    public static synchronized void abortTransaction() {
        if (transactionStates.containsKey(currentDomain)
                && transactionStates.get(currentDomain).containsKey(currentDB)) {
            transactionStates.get(currentDomain).remove(currentDB);
        }
        Path snapshot = transactionSnapshots.remove(transactionKey(currentDomain, currentDB));
        if (snapshot != null) try {
            Path target = DirectoryUtil.getDbPath(currentDomain, currentDB);
            clearPath(target); Files.createDirectories(target.getParent());
            Files.createDirectories(target);
            try (var paths = Files.walk(snapshot)) {
                paths.forEach(path -> {
                    try {
                        Path restored = target.resolve(snapshot.relativize(path).toString());
                        if (Files.isDirectory(path)) Files.createDirectories(restored);
                        else Files.copy(path, restored, StandardCopyOption.REPLACE_EXISTING);
                    } catch (IOException e) { throw new RuntimeException(e); }
                });
            }
            clearPath(snapshot); collections.clear();
        } catch (IOException e) { throw new RuntimeException("Unable to rollback transaction", e); }
    }

    public static void createCollection(String name, Map<String, Object> schema) {
        Path collPath = DirectoryUtil.getCollectionPath(currentDomain, currentDB, name);
        try {
            if (Files.exists(collPath)) {
                collections.putIfAbsent(name, new HashMap<>());
                if (schema != null) {
                    Path modelPath = DirectoryUtil.getCollectionModelPath(currentDomain, currentDB, name);
                    Files.createDirectories(modelPath.getParent());
                    BsonStorage.writeValue(modelPath, schema);
                    cacheMapValue(modelPath, schema, schemaCache);
                    logInfo("Collection " + name + " schema updated in domain " + currentDomain + ", database " + currentDB);
                }
                return;
            }

            collections.putIfAbsent(name, new HashMap<>());
            DirectoryUtil.ensureCollectionDirs(currentDomain, currentDB, name);
            if (schema != null) {
                Path modelPath = DirectoryUtil.getCollectionModelPath(currentDomain, currentDB, name);
                BsonStorage.writeValue(modelPath, schema);
                cacheMapValue(modelPath, schema, schemaCache);
            }
            logInfo("Collection " + name + " created in domain " + currentDomain + ", database " + currentDB);
        } catch (IOException e) {
            throw new RuntimeException("Failed to create collection: " + name, e);
        }
    }

    public static String createIndex(String collectionName, String field, boolean unique) {
        return createIndex(collectionName, field, unique, false);
    }

    public static String createIndex(String collectionName, String field, boolean unique, boolean sparse) {
        return createIndex(collectionName, field, unique, sparse, "manual", "created manually");
    }

    public static String createIndex(String collectionName, String field, boolean unique, String createdBy, String reason) {
        return createIndex(collectionName, field, unique, false, createdBy, reason);
    }

    public static String createIndex(
            String collectionName,
            String field,
            boolean unique,
            boolean sparse,
            String createdBy,
            String reason) {
        if (field == null || field.trim().isEmpty()) {
            throw new RuntimeException("Index field is required");
        }
        if (!collectionExists(collectionName)) {
            throw new RuntimeException("Collection '" + collectionName + "' not found in database '" + currentDB + "'");
        }
        Map<String, Object> defs = readIndexDefinitions(collectionName);
        Map<String, Object> cfg = new LinkedHashMap<>();
        cfg.put("field", field);
        cfg.put("unique", unique);
        cfg.put("sparse", sparse);
        cfg.put("created_at", System.currentTimeMillis());
        cfg.put("created_by", createdBy == null ? "manual" : createdBy);
        cfg.put("reason", reason == null ? "" : reason);
        defs.put(field, cfg);
        writeIndexDefinitions(collectionName, defs);
        rebuildIndex(collectionName, field, unique, sparse);
        return "Index created on " + collectionName + "." + field;
    }

    public static String dropIndex(String collectionName, String field) {
        if (!collectionExists(collectionName)) {
            throw new RuntimeException("Collection '" + collectionName + "' not found in database '" + currentDB + "'");
        }
        Map<String, Object> defs = readIndexDefinitions(collectionName);
        defs.remove(field);
        writeIndexDefinitions(collectionName, defs);
        try {
            Path indexPath = DirectoryUtil.getIndexPath(currentDomain, currentDB, collectionName, field);
            Files.deleteIfExists(indexPath);
            invalidateIndexBucket(indexPath);
        } catch (IOException e) {
            throw new RuntimeException("Failed to remove index file: " + e.getMessage(), e);
        }
        return "Index dropped on " + collectionName + "." + field;
    }

    public static List<Map<String, Object>> listIndexes(String collectionName) {
        if (!collectionExists(collectionName)) {
            throw new RuntimeException("Collection '" + collectionName + "' not found in database '" + currentDB + "'");
        }
        Map<String, Object> defs = readIndexDefinitions(collectionName);
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map.Entry<String, Object> e : defs.entrySet()) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("field", e.getKey());
            boolean unique = false;
            boolean sparse = false;
            if (e.getValue() instanceof Map<?, ?>) {
                Object rawUnique = ((Map<?, ?>) e.getValue()).get("unique");
                unique = Boolean.TRUE.equals(rawUnique);
                sparse = Boolean.TRUE.equals(((Map<?, ?>) e.getValue()).get("sparse"));
                row.put("created_by", ((Map<?, ?>) e.getValue()).get("created_by"));
                row.put("reason", ((Map<?, ?>) e.getValue()).get("reason"));
                row.put("created_at", ((Map<?, ?>) e.getValue()).get("created_at"));
            }
            row.put("unique", unique);
            row.put("sparse", sparse);
            row.put("path", DirectoryUtil.getIndexPath(currentDomain, currentDB, collectionName, e.getKey()).toString());
            out.add(row);
        }
        return out;
    }

    public static String rebuildIndexes(String collectionName) {
        if (!collectionExists(collectionName)) {
            throw new RuntimeException("Collection '" + collectionName + "' not found in database '" + currentDB + "'");
        }
        rebuildIndexesForCollection(collectionName);
        return "Indexes rebuilt for " + collectionName;
    }

    private static void persistDocument(String collectionName, Map<String, Object> document) {
        Path dataDir = DirectoryUtil.getCollectionDataPath(currentDomain, currentDB, collectionName);
        try {
            Files.createDirectories(dataDir);

            String id = (String) document.get("_id");
            Path filePath;
            if (ModelRegistry.getModel(collectionName) != null) {
                filePath = dataDir.resolve(id + BsonStorage.DOCUMENT_EXTENSION);
            } else {
                filePath = dataDir.resolve("doc_" + id + BsonStorage.DOCUMENT_EXTENSION);
            }
            BsonStorage.writeDocument(filePath, document);
        } catch (IOException e) {
            throw new RuntimeException("Failed to persist document to " + dataDir, e);
        }
    }

    private static void deleteDocumentFile(String collectionName, String id) {
        Path dataDir = DirectoryUtil.getCollectionDataPath(currentDomain, currentDB, collectionName);
        Path filePath;
        if (ModelRegistry.getModel(collectionName) != null) {
            filePath = dataDir.resolve(id + BsonStorage.DOCUMENT_EXTENSION);
        } else {
            filePath = dataDir.resolve("doc_" + id + BsonStorage.DOCUMENT_EXTENSION);
        }
        try {
            Files.deleteIfExists(filePath);
        } catch (IOException e) {
            throw new RuntimeException(
                    "Failed to delete document file for id " + id + " in collection " + collectionName, e);
        }
    }

    private static void deleteCollectionFolder(String collectionName) {
        Path collPath = DirectoryUtil.getCollectionPath(currentDomain, currentDB, collectionName);
        if (Files.exists(collPath)) {
            try {
                Files.walk(collPath)
                        .sorted((a, b) -> b.compareTo(a)) // Delete files before directory
                        .forEach(path -> {
                            try {
                                Files.delete(path);
                            } catch (IOException e) {
                                // Log or handle exception
                            }
                        });
            } catch (IOException e) {
                throw new RuntimeException("Failed to drop collection folder for " + collectionName, e);
            }
        }
    }

    private static boolean collectionExists(String collectionName) {
        return Files.exists(DirectoryUtil.getCollectionPath(currentDomain, currentDB, collectionName));
    }

    public static List<Map<String, Object>> findAll(String collectionName) {
        // Load collection from disk
        Path dataDir = DirectoryUtil.getCollectionDataPath(currentDomain, currentDB, collectionName);
        if (!Files.exists(dataDir)) {
            return new ArrayList<>();
        }

        List<Map<String, Object>> results = new ArrayList<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(dataDir, "*" + BsonStorage.DOCUMENT_EXTENSION)) {
            for (Path filePath : stream) {
                Map<String, Object> doc = BsonStorage.readDocument(filePath);
                results.add(doc);
            }
            Map<String, Object> inMemory = collections.computeIfAbsent(collectionName, k -> new HashMap<>());
            inMemory.clear();
            for (Map<String, Object> doc : results) {
                Object id = doc.get("_id");
                if (id != null) {
                    inMemory.put(id.toString(), doc);
                }
            }
        } catch (IOException e) {
            throw new RuntimeException("Error loading collection data", e);
        }
        return results;
    }

    private static Map<String, Object> getSchemaFromClass(Class<?> clazz) {
        try {
            return (Map<String, Object>) clazz.getField("schema").get(null);
        } catch (Exception e) {
            throw new RuntimeException("Failed to get schema from class: " + e.getMessage(), e);
        }
    }

    private static void validateDocumentAgainstSchema(String collectionName, Map<String, Object> document) {
        validateDocumentAgainstSchema(collectionName, document, null);
    }

    private static void validateDocumentAgainstSchema(String collectionName, Map<String, Object> document, String ignoreId) {
        Map<String, Object> schema = getSchema(collectionName);
        if (schema == null || schema.isEmpty()) {
            return;
        }

        try {
            for (Map.Entry<String, Object> entry : schema.entrySet()) {
                String field = entry.getKey();
                if (!(entry.getValue() instanceof Map<?, ?>)) {
                    continue;
                }
                Map<String, Object> fieldSchema = (Map<String, Object>) entry.getValue();

                if (fieldSchema.containsKey("required") && Boolean.TRUE.equals(fieldSchema.get("required"))) {
                    if (!document.containsKey(field)) {
                        throw new RuntimeException("Missing required field: " + field);
                    }
                }

                if (document.containsKey(field)) {
                    Object value = document.get(field);
                    String type = fieldSchema.get("type") == null ? null : String.valueOf(fieldSchema.get("type"));
                    if (type != null && !schemaTypeMatches(type, value)) {
                        throw new RuntimeException("Invalid type for field '" + field + "'. Expected " + type);
                    }
                    if (Boolean.TRUE.equals(fieldSchema.get("unique"))) {
                        assertUniqueFieldValue(collectionName, field, value, ignoreId);
                    }
                }
            }
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("Failed to read schema: " + e.getMessage(), e);
        }
    }

    private static boolean schemaTypeMatches(String rawType, Object value) {
        if (value == null) {
            return true;
        }
        String type = rawType == null ? "" : rawType.trim().toLowerCase(Locale.ROOT);
        switch (type) {
            case "int":
            case "integer":
                return value instanceof Integer;
            case "float":
            case "double":
                return value instanceof Number;
            case "number":
                return value instanceof Number;
            case "str":
            case "string":
                return value instanceof String;
            case "bool":
            case "boolean":
                return value instanceof Boolean;
            case "dict":
            case "map":
            case "object":
                return value instanceof Map<?, ?>;
            case "list":
            case "array":
                return value instanceof List<?>;
            case "":
            case "any":
                return true;
            default:
                return true;
        }
    }

    private static void assertUniqueFieldValue(String collectionName, String field, Object value, String ignoreId) {
        if (value == null) {
            return;
        }
        findAll(collectionName);
        Map<String, Object> coll = collections.computeIfAbsent(collectionName, k -> new HashMap<>());
        for (Object rawDoc : coll.values()) {
            if (!(rawDoc instanceof Map<?, ?>)) {
                continue;
            }
            Map<?, ?> doc = (Map<?, ?>) rawDoc;
            Object existingId = doc.get("_id");
            if (ignoreId != null && existingId != null && ignoreId.equals(String.valueOf(existingId))) {
                continue;
            }
            if (Objects.equals(doc.get(field), value)) {
                throw new RuntimeException("Unique constraint failed for field '" + field + "': " + value);
            }
        }
    }

    private static void rebuildIndexesForCollection(String collectionName) {
        Map<String, Object> defs = readIndexDefinitions(collectionName);
        for (Map.Entry<String, Object> e : defs.entrySet()) {
            String field = e.getKey();
            boolean unique = false;
            boolean sparse = false;
            if (e.getValue() instanceof Map<?, ?>) {
                unique = Boolean.TRUE.equals(((Map<?, ?>) e.getValue()).get("unique"));
                sparse = Boolean.TRUE.equals(((Map<?, ?>) e.getValue()).get("sparse"));
            }
            rebuildIndex(collectionName, field, unique, sparse);
        }
    }

    @SuppressWarnings("unchecked")
    private static void rebuildIndex(String collectionName, String field, boolean unique, boolean sparse) {
        findAll(collectionName);
        Map<String, Object> coll = collections.computeIfAbsent(collectionName, k -> new HashMap<>());
        Map<String, List<String>> buckets = new LinkedHashMap<>();
        for (Object raw : coll.values()) {
            if (!(raw instanceof Map<?, ?>)) {
                continue;
            }
            Map<?, ?> doc = (Map<?, ?>) raw;
            Object id = doc.get("_id");
            if (id == null) {
                continue;
            }
            String idStr = String.valueOf(id);
            Object fieldValue = QueryEvaluator.getNestedField((Map<String, Object>) doc, field);
            if (sparse && fieldValue == null) {
                continue;
            }
            String key = normalizeIndexKey(fieldValue);
            List<String> ids = buckets.computeIfAbsent(key, k -> new ArrayList<>());
            if (unique && !ids.isEmpty() && !ids.contains(idStr)) {
                throw new RuntimeException("Unique index violation on " + collectionName + "." + field);
            }
            ids.add(idStr);
        }
        try {
            Path indexPath = DirectoryUtil.getIndexPath(currentDomain, currentDB, collectionName, field);
            BsonStorage.writeValue(indexPath, buckets);
            cacheIndexBucket(indexPath, buckets);
        } catch (IOException e) {
            throw new RuntimeException("Failed to persist index " + collectionName + "." + field, e);
        }
    }

    private static IndexLookupResult resolveIndexedCandidates(String collectionName, Map<String, Object> query) {
        if (query == null || query.isEmpty()) {
            return IndexLookupResult.none();
        }
        Map<String, Object> defs = readIndexDefinitions(collectionName);
        if (defs.isEmpty()) {
            return IndexLookupResult.none();
        }
        Set<String> candidates = null;
        List<String> usedFields = new ArrayList<>();
        for (Map.Entry<String, Object> q : query.entrySet()) {
            String field = q.getKey();
            if (!defs.containsKey(field)) {
                continue;
            }
            Object queryValue = q.getValue();
            if (queryValue instanceof Map<?, ?> || queryValue instanceof List<?>) {
                continue;
            }
            Object definition = defs.get(field);
            if (queryValue == null && definition instanceof Map<?, ?>
                    && Boolean.TRUE.equals(((Map<?, ?>) definition).get("sparse"))) {
                continue;
            }
            Map<String, List<String>> bucket = readIndexBucket(collectionName, field);
            List<String> ids = bucket.getOrDefault(normalizeIndexKey(queryValue), Collections.emptyList());
            usedFields.add(field);
            if (candidates == null) {
                candidates = new HashSet<>(ids);
            } else {
                candidates.retainAll(ids);
            }
            if (candidates.isEmpty()) {
                return new IndexLookupResult(Collections.emptySet(), usedFields);
            }
        }
        return new IndexLookupResult(candidates, usedFields);
    }

    private static String normalizeIndexKey(Object value) {
        return gson.toJson(value);
    }

    private static Map<String, List<String>> readIndexBucket(String collectionName, String field) {
        Path path = DirectoryUtil.getIndexPath(currentDomain, currentDB, collectionName, field);
        try {
            return readCachedIndexBucket(path);
        } catch (IOException e) {
            throw new RuntimeException("Failed to read index file for " + collectionName + "." + field, e);
        }
    }

    private static Map<String, Object> readIndexDefinitions(String collectionName) {
        Path path = DirectoryUtil.getCollectionIndexDefinitionsPath(currentDomain, currentDB, collectionName);
        try {
            Map<String, Object> parsed = readCachedMapIfExists(path, indexDefinitionCache);
            return parsed == null ? new LinkedHashMap<>() : parsed;
        } catch (IOException e) {
            throw new RuntimeException("Failed to read index definitions for " + collectionName, e);
        }
    }

    private static void writeIndexDefinitions(String collectionName, Map<String, Object> defs) {
        Path path = DirectoryUtil.getCollectionIndexDefinitionsPath(currentDomain, currentDB, collectionName);
        try {
            Files.createDirectories(path.getParent());
            BsonStorage.writeValue(path, defs == null ? Collections.emptyMap() : defs);
            cacheMapValue(path, defs == null ? Collections.emptyMap() : defs, indexDefinitionCache);
        } catch (IOException e) {
            throw new RuntimeException("Failed to save index definitions for " + collectionName, e);
        }
    }

    private static synchronized Map<String, Object> readCachedMapIfExists(
            Path path,
            Map<String, CachedValue<Map<String, Object>>> cache) throws IOException {
        if (path == null || !Files.exists(path)) {
            if (path != null) {
                cache.remove(cacheKey(path));
            }
            return null;
        }
        String key = cacheKey(path);
        long mtime = safeMtime(path);
        CachedValue<Map<String, Object>> cached = cache.get(key);
        if (cached != null && cached.mtime == mtime) {
            return new LinkedHashMap<>(cached.value);
        }
        Map<String, Object> parsed = BsonStorage.readMap(path);
        LinkedHashMap<String, Object> copy = parsed == null ? new LinkedHashMap<>() : new LinkedHashMap<>(parsed);
        cache.put(key, new CachedValue<>(mtime, copy));
        return new LinkedHashMap<>(copy);
    }

    private static synchronized Map<String, List<String>> readCachedIndexBucket(Path path) throws IOException {
        if (path == null || !Files.exists(path)) {
            if (path != null) {
                indexBucketCache.remove(cacheKey(path));
            }
            return Collections.emptyMap();
        }
        String key = cacheKey(path);
        long mtime = safeMtime(path);
        CachedValue<Map<String, List<String>>> cached = indexBucketCache.get(key);
        if (cached != null && cached.mtime == mtime) {
            return copyIndexBucket(cached.value);
        }
        Map<String, List<String>> parsed = gson.fromJson(
                BsonStorage.toJson(BsonStorage.readValue(path)),
                new TypeToken<Map<String, List<String>>>() {}.getType()
        );
        Map<String, List<String>> normalized = parsed == null ? Collections.emptyMap() : copyIndexBucket(parsed);
        indexBucketCache.put(key, new CachedValue<>(mtime, normalized));
        return copyIndexBucket(normalized);
    }

    private static synchronized void cacheMapValue(
            Path path,
            Map<String, Object> value,
            Map<String, CachedValue<Map<String, Object>>> cache) {
        if (path == null) {
            return;
        }
        LinkedHashMap<String, Object> copy = value == null ? new LinkedHashMap<>() : new LinkedHashMap<>(value);
        cache.put(cacheKey(path), new CachedValue<>(safeMtime(path), copy));
    }

    private static synchronized void cacheIndexBucket(Path path, Map<String, List<String>> value) {
        if (path == null) {
            return;
        }
        indexBucketCache.put(cacheKey(path), new CachedValue<>(safeMtime(path), copyIndexBucket(value)));
    }

    private static synchronized void invalidateIndexBucket(Path path) {
        if (path != null) {
            indexBucketCache.remove(cacheKey(path));
        }
    }

    private static Map<String, List<String>> copyIndexBucket(Map<String, List<String>> value) {
        if (value == null || value.isEmpty()) {
            return Collections.emptyMap();
        }
        Map<String, List<String>> copy = new LinkedHashMap<>();
        for (Map.Entry<String, List<String>> entry : value.entrySet()) {
            copy.put(entry.getKey(), entry.getValue() == null ? new ArrayList<>() : new ArrayList<>(entry.getValue()));
        }
        return copy;
    }

    private static String cacheKey(Path path) {
        return path.toAbsolutePath().normalize().toString();
    }

    private static long safeMtime(Path path) {
        if (path == null || !Files.exists(path)) {
            return -1L;
        }
        try {
            return Files.getLastModifiedTime(path).toMillis();
        } catch (IOException e) {
            return -1L;
        }
    }

    public static void logRuntime(String operation, String detail) {
        log(operation == null ? "RUNTIME" : operation, detail == null ? "" : detail);
    }

    private static final class IndexLookupResult {
        final Set<String> ids;
        final List<String> usedFields;

        IndexLookupResult(Set<String> ids, List<String> usedFields) {
            this.ids = ids;
            this.usedFields = usedFields == null ? new ArrayList<>() : new ArrayList<>(usedFields);
        }

        static IndexLookupResult none() {
            return new IndexLookupResult(null, new ArrayList<>());
        }
    }

    private static final class CachedValue<T> {
        final long mtime;
        final T value;

        CachedValue(long mtime, T value) {
            this.mtime = mtime;
            this.value = value;
        }
    }

    public static String getCurrentDomain() {
        return currentDomain;
    }

    public static String getCurrentDB() {
        return currentDB;
    }

    public static void setDomain(String domain) {
        currentDomain = DirectoryUtil.normalizeDomainName(domain);
    }

    public static boolean domainExists(String domainName) {
        return DirectoryUtil.domainExists(DirectoryUtil.normalizeDomainName(domainName));
    }

    public static boolean dbExists(String dbName) {
        return DirectoryUtil.dbExists(currentDomain, dbName);
    }

    public static void setCurrentUser(User user) {
        currentUser = user;
    }

    public static User getCurrentUser() {
        return currentUser;
    }

    public static void setRuntimeLogsEnabled(boolean enabled) {
        runtimeLogsEnabled = enabled;
        VDBLogSettings.setRuntimeLogsEnabled(enabled);
    }

    public static boolean isRuntimeLogsEnabled() {
        return runtimeLogsEnabled;
    }

    public static String auth(Map<String, String> authData) {
        String username = User.normalizeUsername(authData.get("user"));
        String password = authData.get("pass");

        if (UserManager.getInstance().listUsers().isEmpty()) {
            return "{\"error\": \"No VDB users configured. Run vdb console first and create the initial super admin.\"}";
        }

        User user = UserManager.getInstance().getUser(username);
        if (user == null) {
            return "{\"error\": \"Unknown VDB user: " + username + "\"}";
        }
        if (password == null || password.isBlank()) {
            return "{\"error\": \"Password is required for VDB authentication\"}";
        }
        if (!user.authenticate(password)) {
            return "{\"error\": \"Wrong password for VDB user '" + username + "'\"}";
        }
        setCurrentUser(user);

        return "{\"message\": \"Authentication successful\"}";
    }

    public static List<Map<String, Object>> findDocuments(String collectionName) {
        if (!collectionExists(collectionName)) {
            return null;
        }
        Map<String, Object> coll = collections.computeIfAbsent(collectionName, k -> new HashMap<>());
        if (coll.isEmpty()) {
            findAll(collectionName);
        }
        return coll.values().stream()
                .map(doc -> (Map<String, Object>) doc)
                .collect(Collectors.toList());
    }

    public static List<String> listScripts() {
        loadScriptsFromDisk();
        return new ArrayList<>(nameIndex.keySet());
    }

    public static boolean deleteScript(String name) {
        loadScriptsFromDisk();
        if (!nameIndex.containsKey(name)) {
            return false;
        }
        String id = nameIndex.remove(name);
        scriptStore.remove(id);
        Path filePath = DirectoryUtil.getScriptPath(name);
        try {
            Files.deleteIfExists(filePath);
            log("SCRIPT_DELETE", "Deleted script " + name);
            return true;
        } catch (IOException e) {
            throw new RuntimeException("Failed to delete script " + name, e);
        }
    }

    public static Map<String, Object> executeScript(String name, Map<String, Object> params) {
        ScriptDocument script = loadScript(name);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("name", script.name);
        result.put("service", script.serviceName);
        result.put("language", script.language);
        result.put("extension", script.extension);
        result.put("last_edited", script.lastEdited);
        result.put("params", params != null ? params : Collections.emptyMap());

        if (params != null && params.containsKey("collection")) {
            String collection = params.get("collection").toString();
            result.put("collection_data", find(collection, Collections.emptyMap(), Integer.MAX_VALUE));
        }
        log("SCRIPT_EXECUTE", "Executed script " + name);
        return result;
    }

    private static void loadScriptsFromDisk() {
        try {
            Files.createDirectories(DirectoryUtil.SCRIPTS_DIR);
            scriptStore.clear();
            nameIndex.clear();
            try (DirectoryStream<Path> stream = Files.newDirectoryStream(DirectoryUtil.SCRIPTS_DIR, "*" + BsonStorage.DOCUMENT_EXTENSION)) {
                for (Path filePath : stream) {
                    ScriptDocument doc = gson.fromJson(
                            BsonStorage.toJson(BsonStorage.readValue(filePath)),
                            ScriptDocument.class
                    );
                    if (doc == null || doc.name == null) {
                        continue;
                    }
                    scriptStore.put(doc.name, doc);
                    nameIndex.put(doc.name, doc.name);
                }
            }
        } catch (IOException e) {
            throw new RuntimeException("Failed to load scripts from disk", e);
        }
    }

    private static void log(String operation, String detail) {
        if (!runtimeLogsEnabled) {
            return;
        }
        try {
            if (logger == null && DirectoryUtil.logger != null) {
                logger = DirectoryUtil.logger;
            }
            if (logger != null) {
                logger.log("[VDB][" + operation + "] " + detail + " [domain=" + currentDomain + ", db=" + currentDB + "]");
            }
        } catch (Exception ignored) {
            // logging should not block execution
        }
    }

    private static void logInfo(String message) {
        if (runtimeLogsEnabled && CONSOLE_LOGS_ENABLED) {
            System.out.println(message);
        }
    }

}
