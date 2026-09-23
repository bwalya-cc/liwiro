// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.google.gson.Gson;
import com.google.gson.JsonParser;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Enumeration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class VQLProcessorCommandDispatchTest {
    private static final Gson GSON = new Gson();

    @Test
    void rejectsEmptyAndNonObjectTopLevelBatches() {
        User admin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VQLProcessor processor = new VQLProcessor(admin, "default");
        Map<?, ?> empty = parse(processor.executeCommand("[]"));
        assertEquals("error", empty.get("status"));
        Map<?, ?> scalar = parse(processor.executeCommand("[1]"));
        assertEquals("error", scalar.get("status"));
    }

    @BeforeAll
    static void bootstrapVdb() {
        VdbTestSupport.ensureBootstrappedSuperAdmin();
    }

    @Test
    void aggregationPipelineSupportsMatchSortAndProjection() {
        String domain = uniqueName("aggregate_domain");
        String collection = uniqueName("events");
        User admin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VDB.setCurrentUser(admin);
        VDB.defineDomain(domain, "main", true);
        VDB.setDomain(domain);
        VDB.useDatabase("main");
        VDB.createCollection(collection);
        VDB.insert(collection, Map.of("kind", "event", "score", 2));
        VDB.insert(collection, Map.of("kind", "event", "score", 9));
        VDB.insert(collection, Map.of("kind", "audit", "score", 99));
        List<Map<String, Object>> rows = VDB.aggregate(collection, List.of(
                Map.of("$match", Map.of("kind", "event")),
                Map.of("$sort", Map.of("score", -1)),
                Map.of("$limit", 1),
                Map.of("$project", Map.of("score", 1))));
        assertEquals(1, rows.size());
        assertEquals(9.0, ((Number) rows.get(0).get("score")).doubleValue());
        assertFalse(rows.get(0).containsKey("kind"));
    }

    @Test
    void transactionAbortRestoresPersistedDocuments() {
        String domain = uniqueName("rollback_domain");
        String collection = uniqueName("documents");
        User admin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VDB.setCurrentUser(admin);
        VDB.defineDomain(domain, "main", true);
        VDB.setDomain(domain);
        VDB.useDatabase("main");
        VDB.createCollection(collection);
        VDB.insert(collection, Map.of("name", "before"));
        VDB.beginTransaction();
        VDB.insert(collection, Map.of("name", "inside"));
        VDB.abortTransaction();
        assertEquals(1, VDB.findAll(collection).size());
        assertEquals("before", VDB.findAll(collection).get(0).get("name"));
    }

    @Test
    void executesTopLevelModelGetCommand() throws Exception {
        String domain = uniqueName("model_domain");
        String collection = uniqueName("auth_users");
        User setupUser = VdbTestSupport.ensureBootstrappedSuperAdmin();
        User user = new User(uniqueName("model_app"), "model@example.com", "APPLICATION", "Aa1!aaaa");
        user.grantPermission(domain, "main", "READ");
        VDB.setCurrentUser(setupUser);
        VDB.defineDomain(domain, "main", true);
        VDB.createCollection(collection);
        Path modelPath = DirectoryUtil.getCollectionModelPath(domain, "main", collection);
        Files.createDirectories(modelPath.getParent());
        BsonStorage.writeValue(modelPath, Map.of("username", Map.of("type", "string", "required", true)));

        VDB.setCurrentUser(user);
        VQLProcessor processor = new VQLProcessor(user, domain);
        Map<String, Object> parsed = parse(processor.executeCommand("{\"action\":\"model_get\",\"model\":\"" + collection + "\"}"));

        assertEquals("success", parsed.get("status"));
        Map<?, ?> data = (Map<?, ?>) parsed.get("data");
        assertNotNull(data.get("username"));
    }

    @Test
    void executesTopLevelTransactionCommand() {
        String domain = uniqueName("txn_domain");
        User setupUser = VdbTestSupport.ensureBootstrappedSuperAdmin();
        User user = new User(uniqueName("txn_app"), "txn@example.com", "APPLICATION", "Aa1!aaaa");
        user.grantPermission(domain, "main", "WRITE");
        VDB.setCurrentUser(setupUser);
        VDB.defineDomain(domain, "main", true);

        VDB.setCurrentUser(user);
        VQLProcessor processor = new VQLProcessor(user, domain);
        Map<String, Object> parsed = parse(processor.executeCommand("{\"action\":\"transaction_begin\"}"));

        assertEquals("success", parsed.get("status"));
        assertEquals("Transaction started", parsed.get("data"));
    }

    @Test
    void executesFlatDomainLifecycleStatusActions() {
        String domain = uniqueName("status_domain");
        User admin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VDB.setCurrentUser(admin);
        VDB.defineDomain(domain, "main", true);
        VQLProcessor processor = new VQLProcessor(admin, domain);

        Map<String, Object> initial = parse(processor.executeCommand(
                "{\"action\":\"domain_status\",\"domain\":\"" + domain + "\"}"));
        assertEquals("success", initial.get("status"), initial.toString());
        assertEquals("active", ((Map<?, ?>) initial.get("data")).get("status"));

        Map<String, Object> suspended = parse(processor.executeCommand(
                "{\"action\":\"domain_suspend\",\"domain\":\"" + domain + "\"}"));
        assertEquals("success", suspended.get("status"));
        assertEquals("suspended", ((Map<?, ?>) suspended.get("data")).get("status"));

        Map<String, Object> resumed = parse(processor.executeCommand(
                "{\"action\":\"domain_resume\",\"name\":\"" + domain + "\"}"));
        assertEquals("success", resumed.get("status"));
        assertEquals("active", ((Map<?, ?>) resumed.get("data")).get("status"));
    }

    @Test
    void createsEmptyCollectionWithFlatCreateCollectionAction() {
        String domain = uniqueName("empty_collection_domain");
        String collection = uniqueName("empty_collection");
        User admin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VDB.setCurrentUser(admin);
        VDB.defineDomain(domain, "main", true);
        VDB.setDomain(domain);
        VDB.useDatabase("main");

        VQLProcessor processor = new VQLProcessor(admin, domain);
        Map<String, Object> parsed = parse(processor.executeCommand(
                "{\"action\":\"create_collection\",\"collection\":\"" + collection + "\"}"));

        assertEquals("success", parsed.get("status"));
        assertTrue(Files.isDirectory(DirectoryUtil.getCollectionPath(domain, "main", collection)));
        assertEquals(0, VDB.findAll(collection).size());
    }

    @Test
    void executesConciseOperationObject() {
        String domain = uniqueName("op_domain");
        User setupUser = VdbTestSupport.ensureBootstrappedSuperAdmin();
        User user = new User(uniqueName("op_app"), "op@example.com", "APPLICATION", "Aa1!aaaa");
        user.grantPermission(domain, "main", "READ");
        user.grantPermission(domain, "main", "WRITE");
        VDB.setCurrentUser(setupUser);
        VDB.defineDomain(domain, "main", true);
        VDB.createCollection("repairs");
        VDB.setCurrentUser(user);
        VQLProcessor processor = new VQLProcessor(user, domain);
        Map<String, Object> inserted = parse(processor.executeCommand(
                "{\"action\":\"insert\",\"collection\":\"repairs\",\"document\":{\"status\":\"open\"}}"));
        assertEquals("success", inserted.get("status"));
        Map<String, Object> found = parse(processor.executeCommand(
                "{\"action\":\"find\",\"collection\":\"repairs\",\"where\":{\"status\":\"open\"},\"limit\":5}"));
        assertEquals("success", found.get("status"));
        assertFalse(((List<?>) found.get("data")).isEmpty());
    }

    @Test
    void executesConciseIndexOperationObjects() {
        String domain = uniqueName("index_domain");
        String collection = uniqueName("repairs");
        User setupUser = VdbTestSupport.ensureBootstrappedSuperAdmin();
        User user = new User(uniqueName("index_app"), "index@example.com", "APPLICATION", "Aa1!aaaa");
        user.grantPermission(domain, "main", "READ");
        user.grantPermission(domain, "main", "WRITE");
        VDB.setCurrentUser(setupUser);
        VDB.defineDomain(domain, "main", true);
        VDB.createCollection(collection);

        VDB.setCurrentUser(user);
        VQLProcessor processor = new VQLProcessor(user, domain);
        Map<String, Object> created = parse(processor.executeCommand(
                "{\"action\":\"create_index\",\"collection\":\"" + collection
                        + "\",\"field\":\"metadata.sku\",\"unique\":true,\"sparse\":true}"));
        assertEquals("success", created.get("status"));

        Map<String, Object> listed = parse(processor.executeCommand(
                "{\"action\":\"list_indexes\",\"collection\":\"" + collection + "\"}"));
        assertEquals("success", listed.get("status"));
        List<?> indexes = (List<?>) listed.get("data");
        assertEquals(1, indexes.size());
        Map<?, ?> index = (Map<?, ?>) indexes.get(0);
        assertEquals("metadata.sku", index.get("field"));
        assertEquals(Boolean.TRUE, index.get("unique"));
        assertEquals(Boolean.TRUE, index.get("sparse"));

        Map<String, Object> rebuilt = parse(processor.executeCommand(
                "{\"action\":\"rebuild_indexes\",\"collection\":\"" + collection + "\"}"));
        assertEquals("success", rebuilt.get("status"));

        Map<String, Object> dropped = parse(processor.executeCommand(
                "{\"action\":\"drop_index\",\"collection\":\"" + collection
                        + "\",\"field\":\"metadata.sku\"}"));
        assertEquals("success", dropped.get("status"));
    }

    @Test
    void rejectsLegacyIndexCommand() {
        String domain = uniqueName("legacy_index_domain");
        String collection = uniqueName("repairs");
        User user = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VDB.setCurrentUser(user);
        VDB.defineDomain(domain, "main", true);
        VDB.createCollection(collection);

        VQLProcessor processor = new VQLProcessor(user, domain);
        Map<String, Object> parsed = parse(processor.executeCommand(
                "{\"createIndex\":{\"collection\":\"" + collection
                        + "\",\"field\":\"status\",\"unique\":false}}"));

        assertEquals("error", parsed.get("status"));
    }

    @Test
    void exportsAccessibleDomainsToRequestedDirectory() {
        String domain = uniqueName("export_domain");
        User setupUser = VdbTestSupport.ensureBootstrappedSuperAdmin();
        User user = new User(uniqueName("export_app"), "export@example.com", "APPLICATION", "Aa1!aaaa");
        user.grantPermission(domain, "main", "READ");
        user.grantPermission(domain, "main", "DATA_EXPORT");
        VDB.setCurrentUser(setupUser);
        VDB.defineDomain(domain, "main", true);
        String collection = uniqueName("docs");
        VDB.createCollection(collection);
        VDB.insert(collection, Map.of("title", "export me"));

        Path outDir = Path.of(System.getProperty("java.io.tmpdir"), uniqueName("vdb-export-test"));
        VQLProcessor processor = new VQLProcessor(user, domain);
        Map<String, Object> parsed = parse(processor.executeCommand(
                "{\"action\":\"export\",\"domains\":[\"" + domain + "\"],\"package\":\"dispatch-test\",\"out_dir\":\""
                        + outDir.toAbsolutePath().normalize().toString().replace("\\", "\\\\") + "\"}"));

        assertEquals("success", parsed.get("status"));
        Map<?, ?> data = (Map<?, ?>) parsed.get("data");
        Path zipPath = Path.of(String.valueOf(data.get("zip_file")));
        assertTrue(Files.exists(zipPath));
        assertEquals(outDir.toAbsolutePath().normalize(), zipPath.getParent());
        assertFalse(data.containsKey("export_folder"));
        assertFalse(data.containsKey("placed_in"));
        assertTrue(zipContainsCollectionJson(zipPath, domain, collection));
    }

    @Test
    void domainOwnersCanExportOwnedDomainsWithoutExplicitDataExportGrant() {
        String domain = uniqueName("owned_export_domain");
        User setupUser = VdbTestSupport.ensureBootstrappedSuperAdmin();
        User owner = new User(uniqueName("owned_export_app"), "owned-export@example.com", "APPLICATION", "Aa1!aaaa");

        VDB.setCurrentUser(setupUser);
        VDB.defineDomain(domain, "main", true);
        owner.grantDomainOwnership(domain);
        UserManager.getInstance().addUser(owner);

        Path outDir = Path.of(System.getProperty("java.io.tmpdir"), uniqueName("vdb-export-owned-test"));
        VQLProcessor processor = new VQLProcessor(owner, domain);
        Map<String, Object> parsed = parse(processor.executeCommand(
                "{\"action\":\"export\",\"domains\":[\"" + domain + "\"],\"package\":\"dispatch-owned\",\"out_dir\":\""
                        + outDir.toAbsolutePath().normalize().toString().replace("\\", "\\\\") + "\"}"));

        assertEquals("success", parsed.get("status"));
        Map<?, ?> data = (Map<?, ?>) parsed.get("data");
        assertEquals(domain, ((java.util.List<?>) data.get("exported_domains")).get(0));
    }

    @Test
    void superAdminCanExportDefaultDomain() {
        User superAdmin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VDB.setCurrentUser(superAdmin);
        VDB.defineDomain("default", "main", true);
        String collection = uniqueName("default_export_docs");
        VDB.createCollection(collection);
        VDB.insert(collection, Map.of("title", "default domain export"));

        Path outDir = Path.of(System.getProperty("java.io.tmpdir"), uniqueName("vdb-default-export-test"));
        VQLProcessor processor = new VQLProcessor(superAdmin, "default");
        Map<String, Object> parsed = parse(processor.executeCommand(
                "{\"action\":\"export\",\"domains\":[\"default\"],\"package\":\"default-export\",\"out_dir\":\""
                        + outDir.toAbsolutePath().normalize().toString().replace("\\", "\\\\") + "\"}"));

        assertEquals("success", parsed.get("status"));
        Path zipPath = Path.of(String.valueOf(((Map<?, ?>) parsed.get("data")).get("zip_file")));
        assertTrue(Files.exists(zipPath));
        assertTrue(zipContainsCollectionJson(zipPath, "default", collection));
    }

    @Test
    void rejectsExportWithoutOutDir() {
        String domain = uniqueName("export_domain");
        User user = new User(uniqueName("export_app"), "export@example.com", "APPLICATION", "Aa1!aaaa");
        user.grantPermission(domain, "main", "READ");
        user.grantPermission(domain, "main", "DATA_EXPORT");
        VDB.setCurrentUser(user);
        VDB.defineDomain(domain, "main", true);

        VQLProcessor processor = new VQLProcessor(user, domain);
        Map<String, Object> parsed = parse(processor.executeCommand(
                "{\"action\":\"export\",\"domains\":[\"" + domain + "\"]}"));

        assertEquals("error", parsed.get("status"));
        assertTrue(String.valueOf(parsed.get("message")).contains("out_dir is required"));
    }

    @Test
    void rejectsNonZipExportRequests() {
        String domain = uniqueName("export_domain");
        User user = new User(uniqueName("export_app"), "export@example.com", "APPLICATION", "Aa1!aaaa");
        user.grantPermission(domain, "main", "READ");
        user.grantPermission(domain, "main", "DATA_EXPORT");
        VDB.setCurrentUser(user);
        VDB.defineDomain(domain, "main", true);

        Path outDir = Path.of(System.getProperty("java.io.tmpdir"), uniqueName("vdb-export-test"));
        VQLProcessor processor = new VQLProcessor(user, domain);
        Map<String, Object> parsed = parse(processor.executeCommand(
                "{\"action\":\"export\",\"domains\":[\"" + domain + "\"],\"zip\":false,\"out_dir\":\""
                        + outDir.toAbsolutePath().normalize().toString().replace("\\", "\\\\") + "\"}"));

        assertEquals("error", parsed.get("status"));
        assertTrue(String.valueOf(parsed.get("message")).contains("zip output"));
    }

    @Test
    void onlyExplicitContextCommandReturnsContext() {
        User user = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VDB.setCurrentUser(user);
        VQLProcessor processor = new VQLProcessor(user, "default");

        Map<String, Object> echoParsed = parse(processor.executeCommand("{\"action\":\"echo\",\"value\":\"hello\"}"));
        Map<String, Object> warningParsed = parse(processor.executeCommand("{\"action\":\"define\",\"resource\":\"db\",\"db\":\"main\"}"));
        Map<String, Object> errorParsed = parse(processor.executeCommand("{\"action\":\"use\",\"resource\":\"domain\",\"domain\":123}"));
        Map<String, Object> contextParsed = parse(processor.executeCommand("{\"action\":\"context\"}"));

        assertEquals("success", echoParsed.get("status"));
        assertFalse(echoParsed.containsKey("context"));

        assertEquals("warning", warningParsed.get("status"));
        assertFalse(warningParsed.containsKey("context"));

        assertEquals("error", errorParsed.get("status"));
        assertFalse(errorParsed.containsKey("context"));

        assertEquals("success", contextParsed.get("status"));
        assertNotNull(contextParsed.get("data"));
    }

    @Test
    void repairsPartialExistingDomainDuringDefine() throws Exception {
        String domain = uniqueName("repair_domain");
        User setupUser = VdbTestSupport.ensureBootstrappedSuperAdmin();
        Path domainPath = DirectoryUtil.DOMAINS_DIR.resolve(domain);
        Files.createDirectories(domainPath);

        VDB.setCurrentUser(setupUser);
        VQLProcessor processor = new VQLProcessor(setupUser, "default");

        Map<String, Object> defineParsed = parse(
                processor.executeCommand("{\"action\":\"define\",\"resource\":\"domain\",\"domain\":\"" + domain + "\"}"));
        Map<String, Object> useParsed = parse(
                processor.executeCommand("{\"action\":\"use\",\"resource\":\"domain\",\"domain\":\"" + domain + "\"}"));

        assertEquals("success", defineParsed.get("status"));
        assertEquals("success", useParsed.get("status"));
        assertTrue(Files.isRegularFile(DirectoryUtil.getDomainConfigPath(domain)));
        assertTrue(Files.isRegularFile(DirectoryUtil.getDomainMetadataPath(domain)));
        assertTrue(Files.isRegularFile(DirectoryUtil.getDbMetadataPath(domain, "main")));
    }

    @Test
    void storesUsersAsManifestAndPerUserBsonRecords() throws Exception {
        User superAdmin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VDB.setCurrentUser(superAdmin);

        String username = uniqueName("manifest_user");
        User user = new User(username, username + "@example.com", "APPLICATION", "Aa1!aaaa");
        UserManager.getInstance().addUser(user);

        Path manifestPath = DirectoryUtil.getUsersStorePath();
        Map<String, Object> manifest = BsonStorage.readMap(manifestPath);
        assertTrue(manifest.get("usernames") instanceof List<?>);
        assertTrue(((List<?>) manifest.get("usernames")).contains(User.normalizeUsername(username)));
        assertTrue(Files.exists(DirectoryUtil.getUserPath(username)));
        assertEquals(
                User.normalizeUsername(username),
                BsonStorage.readMap(DirectoryUtil.getUserPath(username)).get("username"));
    }

    @Test
    void storesCustomRolesAsManifestAndPerRoleBsonRecords() throws Exception {
        User superAdmin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VDB.setCurrentUser(superAdmin);
        VDB.defineDomain("default", "main", true);

        String roleName = uniqueName("custom_role").toUpperCase();
        Tumi tumi = new Tumi(superAdmin, "default", "main");
        String response = tumi.processCommand(JsonParser.parseString(
                "{\"create\":{\"role\":{\"name\":\"" + roleName
                        + "\",\"scope\":{\"domain\":\"default\",\"db\":\"main\"},\"permissions\":[\"READ\"]}}}")
                .getAsJsonObject());

        Map<String, Object> parsed = parse(response);
        assertEquals("success", parsed.get("status"), response);

        Path manifestPath = DirectoryUtil.getRolesStorePath();
        Map<String, Object> manifest = BsonStorage.readMap(manifestPath);
        assertTrue(manifest.get("role_names") instanceof List<?>);
        assertTrue(((List<?>) manifest.get("role_names")).contains(roleName));
        assertTrue(Files.exists(DirectoryUtil.getRolePath(roleName)));
        assertEquals(roleName, BsonStorage.readMap(DirectoryUtil.getRolePath(roleName)).get("name"));
    }

    @Test
    void viTumiBridgeAcceptsFlatActionEnvelope() throws Exception {
        User superAdmin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VDB.setCurrentUser(superAdmin);
        VDB.defineDomain("default", "main", true);

        String response = VDB.tumi(Map.of(
                "action", "tumi",
                "operation", "list",
                "resource", "roles"));

        Map<String, Object> parsed = parse(response);
        assertEquals("success", parsed.get("status"), response);
    }

    @Test
    void viTumiBridgeRejectsLegacyNestedEnvelope() {
        User superAdmin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VDB.setCurrentUser(superAdmin);
        VDB.defineDomain("default", "main", true);

        assertThrows(IllegalArgumentException.class, () -> VDB.tumi(Map.of(
                "list", "roles")));
    }

    @Test
    void helpActionCarriesPagingThroughVql() {
        User admin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VQLProcessor processor = new VQLProcessor(admin, "default");
        Map<String, Object> parsed = parse(processor.executeCommand(
                "{\"action\":\"help\",\"topic\":\"Documents\",\"page\":2,\"page_size\":2}"));

        assertEquals("section", parsed.get("mode"));
        assertEquals(2.0, parsed.get("page"));
        assertEquals(2, ((List<?>) parsed.get("commands")).size());
        assertTrue(parsed.containsKey("rbac_context"));
        Map<?, ?> rbac = (Map<?, ?>) parsed.get("rbac_context");
        List<?> visibleDomains = (List<?>) rbac.get("visible_domains");
        assertTrue(visibleDomains.size() <= HelpProvider.MAX_PAGE_SIZE);
        assertTrue(((Number) rbac.get("visible_domains_count")).intValue() >= visibleDomains.size());
        assertTrue(rbac.containsKey("visible_domains_truncated"));
    }

    @Test
    void executesFlatAggregateAction() {
        String domain = uniqueName("aggregate_action_domain");
        String collection = uniqueName("aggregate_action_events");
        User admin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VDB.setCurrentUser(admin);
        VDB.defineDomain(domain, "main", true);
        VDB.setDomain(domain);
        VDB.useDatabase("main");
        VDB.createCollection(collection);
        VDB.insert(collection, Map.of("kind", "audit", "score", 7));
        VDB.insert(collection, Map.of("kind", "event", "score", 4));

        VQLProcessor processor = new VQLProcessor(admin, domain);
        Map<String, Object> parsed = parse(processor.executeCommand(
                "{\"action\":\"aggregate\",\"collection\":\"" + collection
                        + "\",\"pipeline\":[{\"$match\":{\"kind\":\"audit\"}}]}"));

        assertEquals("success", parsed.get("status"));
        assertEquals(1, ((List<?>) parsed.get("data")).size());
    }

    @Test
    void executesFlatScriptListAction() {
        User admin = VdbTestSupport.ensureBootstrappedSuperAdmin();
        VQLProcessor processor = new VQLProcessor(admin, "default");
        Map<String, Object> parsed = parse(processor.executeCommand("{\"action\":\"script_list\"}"));

        assertEquals("success", parsed.get("status"));
        assertTrue(parsed.get("data") instanceof List<?>);
    }

    private Map<String, Object> parse(String json) {
        return GSON.fromJson(json, Map.class);
    }

    private static String uniqueName(String prefix) {
        return prefix + "_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
    }

    private boolean zipContainsCollectionJson(Path zipPath, String domain, String collection) {
        try (ZipFile zip = new ZipFile(zipPath.toFile())) {
            Enumeration<? extends ZipEntry> entries = zip.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                String name = entry.getName();
                if ((name.startsWith(domain + "/") || name.contains("/" + domain + "/"))
                        && name.contains("/collections/" + collection + "/data/")
                        && name.endsWith(".json")
                        && !name.endsWith(".bson")) {
                    return true;
                }
            }
            return false;
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}
