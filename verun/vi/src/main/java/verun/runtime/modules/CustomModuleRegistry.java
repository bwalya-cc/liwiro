// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import org.bson.BSONObject;
import org.bson.BasicBSONDecoder;
import org.bson.BasicBSONEncoder;
import org.bson.BasicBSONObject;
import org.bson.types.BasicBSONList;
import verun.vdb.DirectoryUtil;

import java.io.IOException;
import java.lang.reflect.Type;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

public final class CustomModuleRegistry {
    private static final Gson GSON = new Gson();
    private static final Type MAP_TYPE = new TypeToken<Map<String, Object>>() { }.getType();
    private static final ThreadLocal<Deque<String>> LOAD_STACK = ThreadLocal.withInitial(ArrayDeque::new);
    private static final String ROOT_VALUE_KEY = "_value";
    private static final String DEFAULT_VDB_MODULE_DOMAIN = "default";
    private static final String DEFAULT_VDB_MODULE_DB = "main";
    private static final String DEFAULT_VDB_MODULE_COLLECTION = "modules";

    public static final class CustomModule {
        public final String name;
        public final String title;
        public final String description;
        public final String scope;
        public final List<String> assignedDomains;
        public final List<String> ownerDomains;
        public final Map<String, Object> configDefaults;
        public final Map<String, Object> configSchema;
        public final String source;

        public CustomModule(
                String name,
                String title,
                String description,
                String scope,
                List<String> assignedDomains,
                List<String> ownerDomains,
                Map<String, Object> configDefaults,
                Map<String, Object> configSchema,
                String source) {
            this.name = name;
            this.title = title;
            this.description = description;
            this.scope = scope;
            this.assignedDomains = assignedDomains;
            this.ownerDomains = ownerDomains;
            this.configDefaults = configDefaults;
            this.configSchema = configSchema;
            this.source = source;
        }
    }

    private CustomModuleRegistry() {
    }

    public static boolean isKnownCustomModule(String name) {
        return loadAllModules().containsKey(normalizeName(name));
    }

    public static Set<String> listModuleNames() {
        return loadAllModules().keySet();
    }

    public static CustomModule resolveModule(String name, String currentDomain) {
        CustomModule module = loadAllModules().get(normalizeName(name));
        if (module == null) {
            return null;
        }
        if ("global".equals(module.scope)) {
            return module;
        }
        String normalizedDomain = normalizeName(currentDomain);
        if (normalizedDomain.isEmpty()) {
            return null;
        }
        return module.assignedDomains.contains(normalizedDomain) ? module : null;
    }

    public static boolean isLoading(String name) {
        return LOAD_STACK.get().contains(normalizeName(name));
    }

    public static void pushLoading(String name) {
        LOAD_STACK.get().push(normalizeName(name));
    }

    public static void popLoading(String name) {
        String normalized = normalizeName(name);
        Deque<String> stack = LOAD_STACK.get();
        if (!stack.isEmpty() && normalized.equals(stack.peek())) {
            stack.pop();
            return;
        }
        stack.remove(normalized);
    }

    public static String currentLoadChain() {
        Deque<String> stack = LOAD_STACK.get();
        List<String> chain = new ArrayList<>(stack);
        Collections.reverse(chain);
        return String.join(" -> ", chain);
    }

    private static Map<String, CustomModule> loadAllModules() {
        Map<String, CustomModule> modules = new LinkedHashMap<>();
        modules.putAll(loadVdbModules());

        Path registryPath = resolveRegistryPath();
        if (registryPath == null || !Files.isRegularFile(registryPath)) {
            return modules;
        }
        try {
            String raw = Files.readString(registryPath);
            Map<String, Object> payload = GSON.fromJson(raw, MAP_TYPE);
            Object rawModules = payload == null ? null : payload.get("modules");
            if (!(rawModules instanceof List<?>)) {
                return modules;
            }
            for (Object item : (List<?>) rawModules) {
                if (!(item instanceof Map<?, ?>)) {
                    continue;
                }
                @SuppressWarnings("unchecked")
                Map<String, Object> entry = (Map<String, Object>) item;
                String name = normalizeName(entry.get("name"));
                if (name.isEmpty()) {
                    continue;
                }
                String title = stringValue(entry.get("title"));
                String description = stringValue(entry.get("description"));
                String scope = "global".equals(normalizeName(entry.get("scope"))) ? "global" : "domain";
                List<String> assignedDomains = normalizeStringList(entry.get("assigned_domains"));
                List<String> ownerDomains = normalizeStringList(entry.get("owner_domains"));
                Map<String, Object> configDefaults = mapValue(entry.get("config_defaults"));
                Map<String, Object> configSchema = mapValue(entry.get("config_schema"));
                String source = readSource(registryPath.getParent(), entry);
                modules.putIfAbsent(name, new CustomModule(
                        name,
                        title.isEmpty() ? name : title,
                        description,
                        scope,
                        assignedDomains,
                        ownerDomains,
                        configDefaults,
                        configSchema,
                        source
                ));
            }
            return modules;
        } catch (Exception ignored) {
            return modules;
        }
    }

    private static Map<String, CustomModule> loadVdbModules() {
        ensureVdbModuleStore();
        Path dataDir = DirectoryUtil.getCollectionDataPath(
                DEFAULT_VDB_MODULE_DOMAIN,
                DEFAULT_VDB_MODULE_DB,
                DEFAULT_VDB_MODULE_COLLECTION
        );
        if (!Files.isDirectory(dataDir)) {
            return Collections.emptyMap();
        }

        Map<String, CustomModule> modules = new LinkedHashMap<>();
        try {
            try (var stream = Files.newDirectoryStream(dataDir, "*.bson")) {
                for (Path filePath : stream) {
                    Map<String, Object> entry = readBsonMap(filePath);
                    if (entry.isEmpty()) {
                        continue;
                    }
                    String name = normalizeName(entry.get("name"));
                    if (name.isEmpty()) {
                        name = normalizeName(entry.get("_id"));
                    }
                    if (name.isEmpty()) {
                        continue;
                    }
                    String title = stringValue(entry.get("title"));
                    String description = stringValue(entry.get("description"));
                    String scope = "global".equals(normalizeName(entry.get("scope"))) ? "global" : "domain";
                    List<String> assignedDomains = normalizeStringList(entry.get("assigned_domains"));
                    List<String> ownerDomains = normalizeStringList(entry.get("owner_domains"));
                    Map<String, Object> configDefaults = mapValue(entry.get("config_defaults"));
                    Map<String, Object> configSchema = mapValue(entry.get("config_schema"));
                    String source = stringValue(entry.get("source"));
                    modules.put(name, new CustomModule(
                            name,
                            title.isEmpty() ? name : title,
                            description,
                            scope,
                            assignedDomains,
                            ownerDomains,
                            configDefaults,
                            configSchema,
                            source
                    ));
                }
            }
        } catch (Exception ignored) {
            return Collections.emptyMap();
        }
        return modules;
    }

    private static void ensureVdbModuleStore() {
        try {
            DirectoryUtil.ensureDirectories();
            Files.createDirectories(DirectoryUtil.getCollectionSysPath(
                    DEFAULT_VDB_MODULE_DOMAIN,
                    DEFAULT_VDB_MODULE_DB,
                    DEFAULT_VDB_MODULE_COLLECTION
            ));
            Files.createDirectories(DirectoryUtil.getCollectionDataPath(
                    DEFAULT_VDB_MODULE_DOMAIN,
                    DEFAULT_VDB_MODULE_DB,
                    DEFAULT_VDB_MODULE_COLLECTION
            ));

            ensureBsonFile(DirectoryUtil.getDomainMetadataPath(DEFAULT_VDB_MODULE_DOMAIN), defaultSystemMetadata());
            ensureBsonFile(DirectoryUtil.getDomainConfigPath(DEFAULT_VDB_MODULE_DOMAIN), Map.of("default_db", DEFAULT_VDB_MODULE_DB));
            ensureBsonFile(DirectoryUtil.getDbMetadataPath(DEFAULT_VDB_MODULE_DOMAIN, DEFAULT_VDB_MODULE_DB), defaultSystemMetadata());
            ensureBsonFile(
                    DirectoryUtil.getCollectionModelPath(
                            DEFAULT_VDB_MODULE_DOMAIN,
                            DEFAULT_VDB_MODULE_DB,
                            DEFAULT_VDB_MODULE_COLLECTION
                    ),
                    defaultVdbModuleSchema()
            );
            ensureBsonFile(
                    DirectoryUtil.getCollectionIndexDefinitionsPath(
                            DEFAULT_VDB_MODULE_DOMAIN,
                            DEFAULT_VDB_MODULE_DB,
                            DEFAULT_VDB_MODULE_COLLECTION
                    ),
                    Collections.emptyMap()
            );
            syncSeedModuleRecord(
                    DirectoryUtil.getCollectionDataPath(
                            DEFAULT_VDB_MODULE_DOMAIN,
                            DEFAULT_VDB_MODULE_DB,
                            DEFAULT_VDB_MODULE_COLLECTION
                    ).resolve("mediacloud.bson"),
                    seedVdbModuleRecord()
            );
        } catch (Exception ignored) {
        }
    }

    private static void ensureBsonFile(Path path, Object value) throws IOException {
        if (Files.isRegularFile(path)) {
            return;
        }
        writeBsonValue(path, value);
    }

    private static void syncSeedModuleRecord(Path path, Map<String, Object> desired) throws IOException {
        if (!Files.isRegularFile(path)) {
            writeBsonValue(path, desired);
            return;
        }
        Map<String, Object> current = readBsonMap(path);
        if (
                !stringValue(current.get("description")).equals(stringValue(desired.get("description")))
                        || !mapValue(current.get("config_schema")).equals(mapValue(desired.get("config_schema")))
                        || !stringValue(current.get("source")).equals(stringValue(desired.get("source")))
        ) {
            writeBsonValue(path, desired);
        }
    }

    private static Map<String, Object> defaultSystemMetadata() {
        long now = System.currentTimeMillis();
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("owner", "system");
        metadata.put("created_by", "system");
        metadata.put("created_at", now);
        metadata.put("modified_at", now);
        return metadata;
    }

    private static Map<String, Object> defaultVdbModuleSchema() {
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("_id", Map.of("type", "string", "required", true, "unique", true));
        schema.put("name", Map.of("type", "string", "required", true, "unique", true));
        schema.put("title", Map.of("type", "string"));
        schema.put("description", Map.of("type", "string"));
        schema.put("scope", Map.of("type", "string"));
        schema.put("owner_username", Map.of("type", "string"));
        schema.put("owner_domains", Map.of("type", "array"));
        schema.put("assigned_domains", Map.of("type", "array"));
        schema.put("domain_restore", Map.of("type", "array"));
        schema.put("service_domain", Map.of("type", "string"));
        schema.put("config_schema", Map.of("type", "object"));
        schema.put("config_defaults", Map.of("type", "object"));
        schema.put("source", Map.of("type", "string"));
        schema.put("created_at", Map.of("type", "string"));
        schema.put("updated_at", Map.of("type", "string"));
        schema.put("created_by", Map.of("type", "string"));
        schema.put("updated_by", Map.of("type", "string"));
        return schema;
    }

    private static Map<String, Object> seedVdbModuleRecord() {
        long now = System.currentTimeMillis();
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("_id", "mediacloud");
        record.put("name", "mediacloud");
        record.put("title", "MediaCloud");
        record.put("description", "Cloudinary media-storage adapter for Versa services and demos.");
        record.put("scope", "global");
        record.put("owner_username", "system");
        record.put("owner_domains", Collections.emptyList());
        record.put("assigned_domains", Collections.emptyList());
        record.put("domain_restore", Collections.emptyList());
        record.put("service_domain", "services");
        record.put("config_schema", Map.of(
                "defaultProvider", Map.of("type", "string", "enum", List.of("cloudinary")),
                "cloudName", Map.of("type", "string"),
                "apiKey", Map.of("type", "string"),
                "apiSecret", Map.of("type", "string"),
                "folder", Map.of("type", "string")
        ));
        record.put("config_defaults", Map.of("defaultProvider", "cloudinary"));
        record.put("source", loadSeedModuleSource());
        record.put("created_at", String.valueOf(now));
        record.put("updated_at", String.valueOf(now));
        record.put("created_by", "system");
        record.put("updated_by", "system");
        return record;
    }

    private static String loadSeedModuleSource() {
        LinkedHashSet<Path> candidates = new LinkedHashSet<>();
        Path registryPath = resolveRegistryPath();
        if (registryPath != null) {
            candidates.add(registryPath.getParent().resolve("modules").resolve("mediacloud.versa").normalize());
        }
        Path cwd = Paths.get("").toAbsolutePath().normalize();
        for (Path current = cwd; current != null; current = current.getParent()) {
            candidates.add(current.resolve("verun").resolve("vi").resolve("custom_modules").resolve("modules").resolve("mediacloud.versa").normalize());
            candidates.add(current.resolve("vi").resolve("custom_modules").resolve("modules").resolve("mediacloud.versa").normalize());
            candidates.add(current.resolve("custom_modules").resolve("modules").resolve("mediacloud.versa").normalize());
        }
        for (Path candidate : candidates) {
            try {
                if (Files.isRegularFile(candidate)) {
                    return Files.readString(candidate);
                }
            } catch (IOException ignored) {
            }
        }
        return "";
    }

    private static void writeBsonValue(Path path, Object value) throws IOException {
        Files.createDirectories(path.getParent());
        Path tempPath = path.resolveSibling(path.getFileName().toString() + ".tmp");
        Files.write(tempPath, encodeBsonValue(value));
        Files.move(tempPath, path, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
    }

    private static byte[] encodeBsonValue(Object value) {
        BasicBSONObject root = new BasicBSONObject();
        root.put(ROOT_VALUE_KEY, toBsonValue(value));
        return new BasicBSONEncoder().encode(root);
    }

    private static Object toBsonValue(Object value) {
        if (value instanceof Map<?, ?>) {
            BasicBSONObject out = new BasicBSONObject();
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
                out.put(String.valueOf(entry.getKey()), toBsonValue(entry.getValue()));
            }
            return out;
        }
        if (value instanceof List<?>) {
            BasicBSONList out = new BasicBSONList();
            for (Object item : (List<?>) value) {
                out.add(toBsonValue(item));
            }
            return out;
        }
        if (value instanceof Number || value instanceof Boolean || value instanceof String || value == null) {
            return value;
        }
        return String.valueOf(value);
    }

    private static String readSource(Path registryDir, Map<String, Object> entry) throws IOException {
        String source = stringValue(entry.get("source"));
        if (!source.isEmpty()) {
            return source;
        }
        String sourcePath = stringValue(entry.get("source_path"));
        if (sourcePath.isEmpty()) {
            return "";
        }
        Path resolved = registryDir.resolve(sourcePath).normalize();
        if (!Files.isRegularFile(resolved)) {
            return "";
        }
        return Files.readString(resolved);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> readBsonMap(Path path) throws IOException {
        Object decoded = new BasicBSONDecoder().readObject(Files.readAllBytes(path));
        if (!(decoded instanceof BSONObject)) {
            return Collections.emptyMap();
        }
        Object value = ((BSONObject) decoded).get(ROOT_VALUE_KEY);
        Object normalized = value == null && !((BSONObject) decoded).containsField(ROOT_VALUE_KEY)
                ? decoded
                : value;
        Object mapped = fromBsonValue(normalized);
        if (mapped instanceof Map<?, ?>) {
            return new LinkedHashMap<>((Map<String, Object>) mapped);
        }
        return Collections.emptyMap();
    }

    private static Object fromBsonValue(Object value) {
        if (value instanceof List<?>) {
            List<Object> out = new ArrayList<>();
            for (Object item : (List<?>) value) {
                out.add(fromBsonValue(item));
            }
            return out;
        }
        if (value instanceof BSONObject) {
            Map<String, Object> out = new LinkedHashMap<>();
            for (String key : ((BSONObject) value).keySet()) {
                out.put(key, fromBsonValue(((BSONObject) value).get(key)));
            }
            return out;
        }
        return value;
    }

    private static Map<String, Object> mapValue(Object value) {
        if (!(value instanceof Map<?, ?>)) {
            return Collections.emptyMap();
        }
        Map<String, Object> out = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
            out.put(String.valueOf(entry.getKey()), entry.getValue());
        }
        return out;
    }

    private static List<String> normalizeStringList(Object value) {
        if (!(value instanceof List<?>)) {
            return Collections.emptyList();
        }
        Set<String> out = new LinkedHashSet<>();
        for (Object item : (List<?>) value) {
            String normalized = normalizeName(item);
            if (!normalized.isEmpty()) {
                out.add(normalized);
            }
        }
        return new ArrayList<>(out);
    }

    private static String stringValue(Object value) {
        return value == null ? "" : String.valueOf(value).trim();
    }

    private static String normalizeName(Object value) {
        return value == null ? "" : String.valueOf(value).trim().toLowerCase(Locale.ROOT);
    }

    private static Path resolveRegistryPath() {
        LinkedHashSet<Path> candidates = new LinkedHashSet<>();
        addConfiguredCandidate(candidates, System.getProperty("vi.custom.modules.dir"));
        addConfiguredCandidate(candidates, System.getenv("VI_CUSTOM_MODULES_DIR"));

        Path cwd = Paths.get("").toAbsolutePath().normalize();
        for (Path current = cwd; current != null; current = current.getParent()) {
            candidates.add(current.resolve("verun").resolve("vi").resolve("custom_modules").resolve("registry.json").normalize());
            candidates.add(current.resolve("vi").resolve("custom_modules").resolve("registry.json").normalize());
            candidates.add(current.resolve("custom_modules").resolve("registry.json").normalize());
        }

        for (Path candidate : candidates) {
            if (Files.isRegularFile(candidate)) {
                return candidate;
            }
        }
        return null;
    }

    private static void addConfiguredCandidate(Set<Path> candidates, String rawPath) {
        String value = rawPath == null ? "" : rawPath.trim();
        if (value.isEmpty()) {
            return;
        }
        Path path = Paths.get(value).toAbsolutePath().normalize();
        if (value.toLowerCase(Locale.ROOT).endsWith(".json")) {
            candidates.add(path);
            return;
        }
        candidates.add(path.resolve("registry.json").normalize());
    }
}
