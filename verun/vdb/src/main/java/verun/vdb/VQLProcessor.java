// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import com.google.gson.*;
import java.nio.file.*;
import java.util.*;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.BigInteger;
import com.google.gson.reflect.TypeToken;
import java.nio.charset.StandardCharsets;
import java.util.stream.Collectors;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import verun.common.JsonValueConverter;

import verun.vdb.VDBLogger;

public class VQLProcessor {

    private final Gson gson = new GsonBuilder()
            .disableHtmlEscaping()
            .setPrettyPrinting()
            .serializeNulls()
            .create();
    protected String currentDomain;
    protected String currentDB;
    private User currentUser;
    private String currentInterface;
    private SessionManager.Session session;

    public VQLProcessor(User user, SessionManager.Session session) {
        this.currentUser = user;
        this.session = session;
        this.currentDomain = session.getCurrentDomain();
        this.currentDB = session.getCurrentDB();
    }

    public VQLProcessor(User user, String initialDomain) {
        this.currentUser = user;
        this.currentDomain = initialDomain;
        this.currentDB = "main";
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> jsonObjectToMap(JsonObject object) {
        if (object == null) {
            return new LinkedHashMap<>();
        }
        Object converted = JsonValueConverter.fromJsonElement(object);
        if (converted instanceof Map<?, ?>) {
            return new LinkedHashMap<>((Map<String, Object>) converted);
        }
        return new LinkedHashMap<>();
    }

    private Map<String, Boolean> jsonObjectToBooleanMap(JsonObject object) {
        Map<String, Boolean> out = new LinkedHashMap<>();
        for (Map.Entry<String, Object> entry : jsonObjectToMap(object).entrySet()) {
            Object value = entry.getValue();
            if (value instanceof Boolean) {
                out.put(entry.getKey(), (Boolean) value);
            } else {
                out.put(entry.getKey(), Boolean.parseBoolean(String.valueOf(value)));
            }
        }
        return out;
    }

    private Object jsonElementToValue(JsonElement element) {
        return JsonValueConverter.fromJsonElement(element);
    }

    private String handleListCommand(String type) {
        try {
            switch (type.toLowerCase()) {
                case "all_domains":
                    if (!currentUser.isSuperAdmin()) {
                        return errorResponse("Permission denied: Requires SUPER_ADMIN role");
                    }
                    return listAllDomains();
                case "domains_and_owners":
                    return listDomainsAndOwners();
                case "domains":
                    return listDomains();
                case "dbs":
                    return listDatabases();
                case "collections":
                    return listCollections();
                case "models":
                    return listModels();
                case "scripts":
                    return listScripts();
                case "users":
                    List<String> users = UserManager.getInstance().listUsers()
                            .stream()
                            .map(User::getUsername)
                            .collect(Collectors.toList());
                    return successResponse(users);
                default:
                    return errorResponse("Unknown list type");
            }
        } catch (Exception e) {
            return errorResponse("Listing failed: " + e.getMessage());
        }
    }

    private String listDomainsAndOwners() {
        try {
            List<Map<String, Object>> domains = new ArrayList<>();
            for (String domain : DirectoryUtil.getDomains()) {
                if (!currentUser.isSuperAdmin() && !currentUser.ownsDomain(domain)) {
                    continue;
                }
                Path metadataPath = DirectoryUtil.getDomainMetadataPath(domain);
                if (Files.exists(metadataPath)) {
                    Map<String, Object> metadata = BsonStorage.readMap(metadataPath);
                    List<String> owners = UserManager.getInstance().getDomainOwners(domain);

                    Map<String, Object> domainInfo = new LinkedHashMap<>();
                    domainInfo.put("domain", domain);
                    domainInfo.put("owner", metadata.get("owner"));
                    domainInfo.put("owners", owners);
                    domainInfo.put("created_at", metadata.get("created_at"));
                    domainInfo.put("created_by", metadata.get("created_by"));
                    domains.add(domainInfo);
                }
            }
            return successResponse(domains);
        } catch (Exception e) {
            return errorResponse("Failed to list domains: " + e.getMessage());
        }
    }

    private String successResponse(Object data) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("status", "success");
        response.put("timestamp", System.currentTimeMillis());
        response.put("data", data);
        return gson.toJson(response);
    }

    public void setInterface(String intfc) {
        currentInterface = intfc;
    }

    public String getCurrentInterface() {
        return currentInterface;
    }

    public User getCurrentUser() {
        return currentUser;
    }

    public String getContext() {
        Map<String, Object> response = new HashMap<>();
        response.put("status", "success");
        response.put("data", createResponseMap(
                "domain", currentDomain,
                "database", currentDB));
        return gson.toJson(response);
    }

    public String executeReadableCommand(String command) {
        try { return execute(VDBCommandLanguage.parseBatch(command)); }
        catch (IllegalArgumentException error) { return errorResponse(error.getMessage()); }
    }

    /** Execute typed commands produced by the native parser; no JSON command envelope is involved. */
    public String execute(VDBCommand.Batch batch) {
        if (currentUser == null) return errorResponse("Not authenticated");
        if (session != null) { currentDomain = session.getCurrentDomain(); currentDB = session.getCurrentDB(); }
        try {
            if (batch.commands.size() == 1) return executeTyped(batch.commands.get(0));
            List<Object> results = new ArrayList<>();
            for (VDBCommand command : batch.commands) {
                String response = executeTyped(command);
                results.add(JsonValueConverter.fromJson(response));
                if (responseStatusIsError(response)) break;
            }
            syncSessionContext();
            return successResponse(results);
        } catch (Exception error) {
            return errorResponse(error.getMessage());
        }
    }

    private String executeTyped(VDBCommand command) {
        String result;
        switch (command.kind) {
            case CONTEXT: result = getContext(); break;
            case WHOAMI: result = handleWhoamiCommand(); break;
            case ECHO: System.out.println(String.valueOf(command.value)); result = successResponse(command.value); break;
            case HELP: result = handleHelpCommand(command.target == null ? new JsonObject() : new JsonPrimitive(command.target)); break;
            case CLEAR: result = successResponse("Console cleared"); break;
            case LICENSE: result = successResponse(MitLicense.licenseDisclosure()); break;
            case EXIT: result = successResponse("Exit requested"); break;
            case READ_DOMAINS: result = handleListCommand("domains"); break;
            case READ_ALL_DOMAINS: result = handleListCommand("all_domains"); break;
            case READ_DOMAINS_WITH_OWNERS: result = handleListCommand("domains_and_owners"); break;
            case READ_DATABASES: result = handleListCommand("dbs"); break;
            case READ_COLLECTIONS: result = handleListCommand("collections"); break;
            case READ_MODELS: result = handleListCommand("models"); break;
            case READ_SCRIPTS: result = handleListCommand("scripts"); break;
            case READ_USERS: result = typedTumiRead(command, "users"); break;
            case READ_ROLES: result = typedTumiRead(command, "roles"); break;
            case READ_PERMISSIONS: result = typedTumiRead(command, "permissions"); break;
            case READ_OWNED_DOMAINS: result = typedTumiRead(command, "owned_domains"); break;
            case READ_COLLECTION: case READ_ONE: result = typedRead(command); break;
            case COUNT: result = typedCount(command); break;
            case CREATE_COLLECTION: result = typedCreateCollection(command); break;
            case CREATE_DOCUMENT: result = typedCreateDocuments(command); break;
            case UPDATE_COLLECTION: result = typedUpdate(command); break;
            case DELETE_DOCUMENT: result = typedDelete(command); break;
            case CREATE_DOMAIN: result = typedCreateDomain(command); break;
            case CREATE_DATABASE: result = typedCreateDatabase(command); break;
            case USE_DOMAIN: result = typedUse(command.target, null); break;
            case USE_DATABASE: result = typedUse(null, command.target); break;
            case USE_PATH: result = typedUsePath(command.target); break;
            case DROP_DOMAIN: result = handleDomainDrop(command.target.toLowerCase(Locale.ROOT)); break;
            case DROP_DATABASE: result = handleDbDrop(command.target.toLowerCase(Locale.ROOT)); break;
            case DROP_COLLECTION: result = typedDropCollection(command.target); break;
            case STATUS_DOMAIN: result = typedDomainStatus(command.target, "get"); break;
            case SUSPEND_DOMAIN: result = typedDomainStatus(command.target, "suspend"); break;
            case RESUME_DOMAIN: result = typedDomainStatus(command.target, "resume"); break;
            case CREATE_INDEX: result = typedIndex(command, "create"); break;
            case DROP_INDEX: result = typedIndex(command, "drop"); break;
            case READ_INDEXES: result = typedIndex(command, "list"); break;
            case REBUILD_INDEXES: result = typedIndex(command, "rebuild"); break;
            case REBUILD_INDEX: result = typedIndex(command, "rebuild"); break;
            case DROP_MODEL: result = command.options.containsKey("read") ? handleGetModelCommand(command.target) : handleDeleteModelCommand(command.target); break;
            case CREATE_SCRIPT: result = typedScript(command); break;
            case RUN_SCRIPT: result = typedRunScript(command); break;
            case DELETE_SCRIPT: result = typedDeleteScript(command.target); break;
            case CREATE_USER: case CREATE_ROLE: case UPDATE_USER: case UPDATE_ROLE:
            case DELETE_USER: case DELETE_ROLE: case GRANT_PERMISSION: case REVOKE_PERMISSION:
            case GRANT_ROLE: case REVOKE_ROLE: case GRANT_OWNERSHIP: case TRANSFER_DOMAIN:
                result = typedTumi(command); break;
            case BEGIN_TRANSACTION: beginTransaction(); result = successResponse("Transaction started"); break;
            case COMMIT_TRANSACTION: commitTransaction(); result = successResponse("Transaction committed"); break;
            case ROLLBACK_TRANSACTION: abortTransaction(); result = successResponse("Transaction rolled back"); break;
            case TRANSACTION_BLOCK: result = typedTransaction(command); break;
            case DESCRIBE_COLLECTION: result = typedDescribe(command.target); break;
            case EXPORT: result = typedExport(command); break;
            case AGGREGATE: result = typedAggregate(command); break;
            default: result = errorResponse("Unsupported typed VDB operation: " + command.kind);
        }
        syncSessionContext();
        return result;
    }

    private String typedRead(VDBCommand command) {
        if (!canReadCollection(command.target)) return errorResponse("Permission denied for reading collection: " + command.target);
        try {
            List<Map<String, Object>> docs = VDB.findAll(command.target).stream()
                    .filter(doc -> QueryEvaluator.matches(doc, command.predicate)).collect(Collectors.toList());
            if (!command.order.isEmpty()) docs.sort((a, b) -> compareDocuments(a, b, command.order));
            return successResponse(docs.stream().skip(command.offset).limit(command.limit)
                    .map(doc -> typedProjection(doc, command.selection)).collect(Collectors.toList()));
        } catch (Exception error) { return errorResponse("Read failed: " + error.getMessage()); }
    }

    private String typedCount(VDBCommand command) {
        if (!canReadCollection(command.target)) return errorResponse("Permission denied for counting collection: " + command.target);
        long count = VDB.findAll(command.target).stream().filter(doc -> QueryEvaluator.matches(doc, command.predicate)).count();
        return successResponse(createResponseMap("count", count));
    }

    @SuppressWarnings("unchecked")
    private String typedCreateDocuments(VDBCommand command) {
        if (!canWriteCollection(command.target)) return errorResponse("Permission denied for writing collection: " + command.target);
        try {
            if (command.value instanceof List<?>) {
                List<Object> inserted = new ArrayList<>();
                for (Object value : (List<?>) command.value) {
                    if (!(value instanceof Map)) return errorResponse("Every created record must be an object");
                    inserted.add(VDB.insert(command.target, new LinkedHashMap<>((Map<String, Object>) value)));
                }
                return successResponse(inserted);
            }
            return successResponse(VDB.insert(command.target, new LinkedHashMap<>((Map<String, Object>) command.value)));
        } catch (Exception error) { return errorResponse("Document creation failed: " + error.getMessage()); }
    }

    @SuppressWarnings("unchecked")
    private String typedCreateCollection(VDBCommand command) {
        if (!canWriteCollection(command.target)) return errorResponse("Permission denied for creating collection/schema: " + command.target);
        try {
            Map<String, Object> schema = new LinkedHashMap<>();
            if (command.value instanceof Map) {
                for (Map.Entry<String, VDBCommand.SchemaField> entry : ((Map<String, VDBCommand.SchemaField>) command.value).entrySet()) {
                    VDBCommand.SchemaField field = entry.getValue(); Map<String, Object> definition = new LinkedHashMap<>();
                    definition.put("type", normalizeSchemaType(field.type));
                    if (field.annotations.contains("required")) definition.put("required", true);
                    if (field.annotations.contains("unique")) definition.put("unique", true);
                    if (field.nullable) definition.put("nullable", true);
                    if (field.defaultValue != null) definition.put("default", field.defaultValue);
                    schema.put(entry.getKey(), definition);
                }
            }
            VDB.createCollection(command.target, schema);
            for (Map.Entry<String, Object> entry : schema.entrySet()) {
                Map<String, Object> definition = (Map<String, Object>) entry.getValue();
                if (Boolean.TRUE.equals(definition.get("unique"))) VDB.createIndex(command.target, entry.getKey(), true, false);
            }
            return successResponse("Collection created: " + command.target);
        } catch (Exception error) { return errorResponse("Collection creation failed: " + error.getMessage()); }
    }

    private String typedUpdate(VDBCommand command) {
        if (!canWriteCollection(command.target)) return errorResponse("Permission denied for updating collection: " + command.target);
        int updated = 0;
        try {
            for (Map<String, Object> doc : VDB.findAll(command.target)) {
                if (!QueryEvaluator.matches(doc, command.predicate)) continue;
                for (VDBCommand.Update update : command.updates) applyTypedUpdate(doc, update);
                VDB.update(command.target, String.valueOf(doc.get("_id")), doc); updated++;
            }
            return successResponse(createResponseMap("updated", updated));
        } catch (Exception error) { return errorResponse("Update failed: " + error.getMessage()); }
    }

    private String typedDelete(VDBCommand command) {
        if (!canWriteCollection(command.target)) return errorResponse("Permission denied for deleting from collection: " + command.target);
        int deleted = 0;
        try {
            for (Map<String, Object> doc : new ArrayList<>(VDB.findAll(command.target))) {
                if (command.all || QueryEvaluator.matches(doc, command.predicate)) { VDB.delete(command.target, String.valueOf(doc.get("_id"))); deleted++; }
            }
            return successResponse(createResponseMap("deleted", deleted));
        } catch (Exception error) { return errorResponse("Delete failed: " + error.getMessage()); }
    }

    private boolean responseStatusIsError(String response) {
        try { JsonObject body = gson.fromJson(response, JsonObject.class); return body != null && "error".equalsIgnoreCase(body.get("status").getAsString()); }
        catch (Exception ignored) { return true; }
    }
    private void syncSessionContext() {
        if (session != null) { session.setCurrentDomain(currentDomain); session.setCurrentDB(currentDB); }
    }
    private String typedCreateDomain(VDBCommand command) {
        try {
            String domain = command.target.toLowerCase(Locale.ROOT);
            if (command.value instanceof Map && ((Map<?, ?>) command.value).get("database") != null) {
                String db = String.valueOf(((Map<?, ?>) command.value).get("database")).toLowerCase(Locale.ROOT);
                // defineDomain is idempotent and repairs an existing domain's
                // default_db metadata; createDomain rejects complete domains.
                VDB.defineDomain(domain, db, true);
            } else {
                DirectoryUtil.createDomain(domain, currentUser);
            }
            return successResponse("Domain created: " + command.target);
        }
        catch (Exception e) { return errorResponse("Domain creation failed: " + e.getMessage()); }
    }
    private String typedCreateDatabase(VDBCommand command) {
        try { VDB.createDatabase(command.target.toLowerCase(Locale.ROOT)); return successResponse("Database created: " + command.target); }
        catch (Exception e) { return errorResponse("Database creation failed: " + e.getMessage()); }
    }
    private String typedUse(String domain, String db) {
        try {
            if (domain != null) { currentDomain = domain.toLowerCase(Locale.ROOT); VDB.setDomain(currentDomain); }
            if (db != null) { currentDB = db.toLowerCase(Locale.ROOT); VDB.useDatabase(currentDB); }
            return successResponse(createResponseMap("domain", currentDomain, "database", currentDB));
        } catch (Exception e) { return errorResponse("Context switch failed: " + e.getMessage()); }
    }
    private String typedUsePath(String path) { String[] parts = path.split("\\.", 2); return typedUse(parts[0], parts.length > 1 ? parts[1] : null); }
    private String typedDropCollection(String target) {
        try { if (!canWriteCollection(target)) return errorResponse("Permission denied for dropping collection"); VDB.drop(target); return successResponse("Collection dropped: " + target); }
        catch (Exception e) { return errorResponse("Collection drop failed: " + e.getMessage()); }
    }
    private String typedDomainStatus(String domain, String operation) {
        JsonObject object = new JsonObject(); object.addProperty("domain", domain); object.addProperty("operation", operation); return handleDomainStatusCommand(object);
    }
    private String typedIndex(VDBCommand command, String operation) {
        String[] path = command.target.split("\\.", 2); if (path.length != 2) return errorResponse("Index target must be collection.field");
        JsonObject object = new JsonObject(); object.addProperty("operation", operation); object.addProperty("collection", path[0]); object.addProperty("field", path[1]);
        object.addProperty("unique", Boolean.TRUE.equals(command.options.get("unique"))); object.addProperty("sparse", Boolean.TRUE.equals(command.options.get("sparse")));
        return handleIndexCommand(object);
    }
    private String typedScript(VDBCommand command) {
        if (command.options.containsKey("read")) {
            try { return successResponse(VDB.loadScript(command.target)); }
            catch (Exception e) { return errorResponse("Script read failed: " + e.getMessage()); }
        }
        JsonObject script = new JsonObject(); script.addProperty("name", command.target); script.addProperty("code", String.valueOf(command.options.get("code")));
        if (command.options.containsKey("service")) script.addProperty("service", String.valueOf(command.options.get("service")));
        return handleScriptCreate(script);
    }
    private String typedRunScript(VDBCommand command) {
        JsonObject wrapper = new JsonObject(); JsonObject execute = new JsonObject(); execute.addProperty("name", command.target); execute.add("params", gson.toJsonTree(command.value == null ? Collections.emptyMap() : command.value)); wrapper.add("execute", execute); return handleScriptCommand(wrapper);
    }
    private String typedDeleteScript(String target) { JsonObject wrapper = new JsonObject(); wrapper.addProperty("delete", target); return handleScriptCommand(wrapper); }
    private String typedDescribe(String target) { return successResponse(createResponseMap("collection", target, "indexes", VDB.listIndexes(target), "record_count", VDB.findAll(target).size())); }
    private String typedExport(VDBCommand command) {
        JsonObject options = new JsonObject();
        Object targets = command.value;
        if (targets instanceof List<?>) options.add("domains", gson.toJsonTree(targets)); else if (targets != null) { JsonArray domains = new JsonArray(); domains.add(String.valueOf(targets)); options.add("domains", domains); }
        if (command.options.get("to") != null) options.addProperty("out_dir", String.valueOf(command.options.get("to")));
        if (command.options.get("as") != null) options.addProperty("package", String.valueOf(command.options.get("as")));
        if (command.options.get("format") != null) options.addProperty("format", String.valueOf(command.options.get("format")));
        return handleExportCommand(options);
    }
    private String typedAggregate(VDBCommand command) {
        if (!canReadCollection(command.target)) return errorResponse("Permission denied for aggregating collection: " + command.target);
        try {
            List<Map<String, Object>> docs = VDB.findAll(command.target).stream().filter(doc -> QueryEvaluator.matches(doc, command.predicate)).collect(Collectors.toList());
            Object byValue = command.options.get("by"); List<String> groups = new ArrayList<>();
            if (byValue instanceof List) for (Object value : (List<?>) byValue) groups.add(String.valueOf(value)); else if (byValue != null) groups.add(String.valueOf(byValue));
            Map<String, List<Map<String, Object>>> grouped = new LinkedHashMap<>();
            if (groups.isEmpty()) grouped.put("", docs); else for (Map<String, Object> doc : docs) { StringBuilder key = new StringBuilder(); for (String field : groups) { if (key.length() > 0) key.append('|'); key.append(String.valueOf(QueryEvaluator.getNestedField(doc, field))); } grouped.computeIfAbsent(key.toString(), ignored -> new ArrayList<>()).add(doc); }
            List<Map<String, Object>> output = new ArrayList<>(); String body = String.valueOf(command.options.get("body"));
            for (Map.Entry<String, List<Map<String, Object>>> group : grouped.entrySet()) { Map<String, Object> row = new LinkedHashMap<>(); if (!groups.isEmpty()) { String[] keys = group.getKey().split("\\|", -1); for (int i = 0; i < groups.size(); i++) row.put(groups.get(i), keys[i]); } java.util.regex.Matcher matcher = java.util.regex.Pattern.compile("(?m)([A-Za-z_][A-Za-z0-9_]*)\\s*:\\s*(count|sum|avg|min|max)\\s*\\(\\s*([A-Za-z0-9_.]+)?\\s*\\)\\s*;").matcher(body); while (matcher.find()) { String alias = matcher.group(1), fn = matcher.group(2); String field = matcher.group(3); List<Object> values = group.getValue().stream().map(doc -> field == null ? null : QueryEvaluator.getNestedField(doc, field)).filter(Objects::nonNull).collect(Collectors.toList()); if ("count".equals(fn)) row.put(alias, group.getValue().size()); else if (values.isEmpty()) row.put(alias, null); else if ("sum".equals(fn) || "avg".equals(fn)) { double sum = values.stream().mapToDouble(v -> ((Number) v).doubleValue()).sum(); row.put(alias, "avg".equals(fn) ? sum / values.size() : sum); } else { values.sort((a,b) -> String.valueOf(a).compareTo(String.valueOf(b))); row.put(alias, "min".equals(fn) ? values.get(0) : values.get(values.size()-1)); } } output.add(row); }
            Object orderValue = command.options.get("order"); if (orderValue instanceof List) output.sort((a,b) -> compareAggregateRows(a,b,(List<VDBCommand.Order>) orderValue));
            int limit = command.options.get("limit") instanceof Number ? ((Number) command.options.get("limit")).intValue() : output.size(); return successResponse(output.stream().limit(limit).collect(Collectors.toList()));
        } catch (Exception e) { return errorResponse("Aggregation failed: " + e.getMessage()); }
    }
    private int compareAggregateRows(Map<String,Object> a, Map<String,Object> b, List<VDBCommand.Order> orders) { for (VDBCommand.Order order : orders) { Object av=a.get(order.field), bv=b.get(order.field); int c=av instanceof Number && bv instanceof Number ? Double.compare(((Number)av).doubleValue(), ((Number)bv).doubleValue()) : String.valueOf(av).compareTo(String.valueOf(bv)); if(c!=0) return order.ascending?c:-c; } return 0; }
    private String typedTransaction(VDBCommand command) {
        VDB.beginTransaction(); List<Object> results = new ArrayList<>();
        for (VDBCommand child : command.statements) { String response = executeTyped(child); results.add(JsonValueConverter.fromJson(response)); if (responseStatusIsError(response)) { VDB.abortTransaction(); return successResponse(createResponseMap("committed", false, "results", results)); } }
        VDB.commitTransaction(); return successResponse(createResponseMap("committed", true, "results", results));
    }
    private String typedTumiRead(VDBCommand command, String resource) {
        if (Boolean.TRUE.equals(command.options.get("single"))) {
            if ("users".equals(resource)) {
                User user = UserManager.getInstance().getUser(command.target);
                if (user == null) return errorResponse("User not found: " + command.target);
                return successResponse(createResponseMap("username", user.getUsername(), "email", user.getEmail(), "role", user.getRole()));
            }
            JsonObject read = new JsonObject(); read.addProperty("role".equals(resource) ? "role" : "username", command.target);
            JsonObject wrapper = new JsonObject(); wrapper.add("read", read); return handleTumiCommand(wrapper);
        }
        // Tumi's list dispatcher accepts the canonical resource name directly;
        // the old {users:true}/{roles:true} object was the source of
        // "Invalid list command" for `read users`.
        JsonObject wrapper = new JsonObject();
        if ("permissions".equals(resource) && command.options.containsKey("user")) {
            JsonObject scoped = new JsonObject(); scoped.addProperty("permissions", String.valueOf(command.options.get("user")));
            wrapper.add("list", scoped);
        } else {
            wrapper.addProperty("list", resource);
        }
        return handleTumiCommand(wrapper);
    }
    private String typedTumi(VDBCommand command) {
        JsonObject wrapper = new JsonObject(); JsonObject payload = new JsonObject(); String username = command.target;
        switch (command.kind) {
            case CREATE_USER: payload.addProperty("username", username); break;
            case CREATE_ROLE: payload.add("role", gson.toJsonTree(command.value)); break;
            case DELETE_USER: payload.addProperty("username", username); wrapper.add("delete", payload); return handleTumiCommand(wrapper);
            case DELETE_ROLE: payload.addProperty("role", username); wrapper.add("delete", payload); return handleTumiCommand(wrapper);
            case GRANT_ROLE: payload.addProperty("username", username); payload.add("role", new JsonPrimitive(String.valueOf(command.value))); wrapper.add("grant", payload); return handleTumiCommand(wrapper);
            case REVOKE_ROLE: payload.addProperty("username", username); payload.add("role", new JsonPrimitive(String.valueOf(command.value))); wrapper.add("revoke", payload); return handleTumiCommand(wrapper);
            case GRANT_PERMISSION: case REVOKE_PERMISSION:
                payload.addProperty("username", username);
                String scope = String.valueOf(command.options.get("scope")); String[] parts = scope.split("\\.", 3);
                payload.addProperty("domain", parts[0]); if (parts.length > 1) payload.addProperty("db", parts[1]); if (parts.length > 2) payload.addProperty("collection", parts[2]);
                payload.add("permissions", gson.toJsonTree(command.value)); wrapper.add(command.kind == VDBCommand.Kind.GRANT_PERMISSION ? "grant" : "revoke", payload); return handleTumiCommand(wrapper);
            case TRANSFER_DOMAIN: payload.addProperty("username", username); payload.addProperty("domain", String.valueOf(command.value)); payload.addProperty("relinquish", Boolean.TRUE.equals(command.options.get("relinquish"))); wrapper.add("transfer", payload); return handleTumiCommand(wrapper);
            case UPDATE_USER:
                User existing = UserManager.getInstance().getUser(username);
                if (existing == null || !currentUser.isSuperAdmin()) return errorResponse("Permission denied or user not found");
                Map<?, ?> values = command.value instanceof Map ? (Map<?, ?>) command.value : Collections.emptyMap();
                Map<String, Object> updates = new LinkedHashMap<>(values instanceof Map ? (Map<String,Object>) values : Collections.emptyMap());
                for (VDBCommand.Update update : command.updates) if (update.value != null) updates.put(update.field, update.value.evaluate(Collections.emptyMap(), Collections.emptyMap()));
                existing.updateProfile(updates.get("email") == null ? null : String.valueOf(updates.get("email")), updates.get("role") == null ? null : String.valueOf(updates.get("role")), updates.get("password") == null ? null : String.valueOf(updates.get("password")));
                UserManager.getInstance().updateUser(existing); return successResponse("User updated: " + username);
            case UPDATE_ROLE:
                JsonObject roleUpdate = new JsonObject(); roleUpdate.addProperty("name", username);
                if (command.value instanceof Map) for (Map.Entry<?, ?> entry : ((Map<?, ?>) command.value).entrySet()) roleUpdate.add(entry.getKey().toString(), gson.toJsonTree(entry.getValue()));
                JsonObject updatePayload = new JsonObject(); updatePayload.add("role", roleUpdate); wrapper.add("update", updatePayload); return handleTumiCommand(wrapper);
            default: break;
        }
        if (command.kind == VDBCommand.Kind.CREATE_USER && command.value instanceof Map) {
            Map<?, ?> values = (Map<?, ?>) command.value; for (Map.Entry<?, ?> entry : values.entrySet()) payload.add(entry.getKey().toString(), gson.toJsonTree(entry.getValue()));
        }
        if (command.kind == VDBCommand.Kind.CREATE_USER) wrapper.add("create", payload);
        else if (command.kind == VDBCommand.Kind.CREATE_ROLE) {
            JsonObject role = new JsonObject(); role.addProperty("name", username);
            if (command.value instanceof Map) for (Map.Entry<?, ?> entry : ((Map<?, ?>) command.value).entrySet()) {
                if ("scope".equals(entry.getKey().toString()) && entry.getValue() instanceof String) {
                    String[] scope = String.valueOf(entry.getValue()).split("\\.", 2); JsonObject scopeObject = new JsonObject(); scopeObject.addProperty("domain", scope[0]); if (scope.length > 1) scopeObject.addProperty("db", scope[1]); role.add("scope", scopeObject);
                } else role.add(entry.getKey().toString(), gson.toJsonTree(entry.getValue()));
            }
            payload = new JsonObject(); payload.add("role", role); wrapper.add("create", payload);
        }
        return handleTumiCommand(wrapper);
    }
    private Map<String, Object> typedProjection(Map<String, Object> doc, List<String> fields) { if (fields.isEmpty()) return doc; Map<String, Object> result = new LinkedHashMap<>(); for (String field : fields) { Object value = QueryEvaluator.getNestedField(doc, field); if (value != null) result.put(field, value); } return result; }
    @SuppressWarnings({"unchecked", "rawtypes"})
    private int compareDocuments(Map<String, Object> a, Map<String, Object> b, List<VDBCommand.Order> orders) {
        for (VDBCommand.Order order : orders) {
            Object av = QueryEvaluator.getNestedField(a, order.field), bv = QueryEvaluator.getNestedField(b, order.field);
            int comparison;
            if (av == null) comparison = bv == null ? 0 : -1;
            else if (bv == null) comparison = 1;
            else if (av instanceof Number && bv instanceof Number) comparison = Double.compare(((Number) av).doubleValue(), ((Number) bv).doubleValue());
            else if (av instanceof Comparable && av.getClass().isInstance(bv)) comparison = ((Comparable) av).compareTo(bv);
            else comparison = String.valueOf(av).compareTo(String.valueOf(bv));
            if (comparison != 0) return order.ascending ? comparison : -comparison;
        }
        return 0;
    }
    private String normalizeSchemaType(String type) { return type == null ? "string" : type.toLowerCase(Locale.ROOT); }
    private void applyTypedUpdate(Map<String, Object> document, VDBCommand.Update update) {
        if (update.operation == VDBCommand.Update.Operation.UNSET) { unsetNested(document, update.field); return; }
        Object value = update.value.evaluate(document, Collections.emptyMap());
        if (update.operation == VDBCommand.Update.Operation.SET) setNested(document, update.field, value);
        else { Object current = QueryEvaluator.getNestedField(document, update.field); if (!(value instanceof Number) || (current != null && !(current instanceof Number))) throw new IllegalArgumentException("Numeric update requires numeric values"); double result = (current == null ? 0 : ((Number) current).doubleValue()) + ((Number) value).doubleValue() * (update.operation == VDBCommand.Update.Operation.DECREMENT ? -1 : 1); setNested(document, update.field, result); }
    }
    @SuppressWarnings("unchecked") private void setNested(Map<String, Object> doc, String path, Object value) { String[] parts = path.split("\\."); Map<String, Object> current = doc; for (int i = 0; i < parts.length - 1; i++) current = (Map<String, Object>) current.computeIfAbsent(parts[i], key -> new LinkedHashMap<>()); current.put(parts[parts.length - 1], value); }
    @SuppressWarnings("unchecked") private void unsetNested(Map<String, Object> doc, String path) { String[] parts = path.split("\\."); Map<String, Object> current = doc; for (int i = 0; i < parts.length - 1; i++) { Object next = current.get(parts[i]); if (!(next instanceof Map)) return; current = (Map<String, Object>) next; } current.remove(parts[parts.length - 1]); }

    public String executeCommand(String vqlJson) {
        boolean isConsoleInterface = "CONSOLE".equalsIgnoreCase(currentInterface);
        if (!isConsoleInterface && DirectoryUtil.logger != null) {
            DirectoryUtil.logger.log("[VQL][REQUEST] " + vqlJson);
        }
        if (session != null) {
            currentDomain = session.getCurrentDomain();
            currentDB = session.getCurrentDB();
        }

        if (currentUser == null) {
            return errorResponse("Not authenticated");
        }

        try {
            JsonElement requestElement = gson.fromJson(vqlJson, JsonElement.class);
            if (requestElement.isJsonArray()) {
                JsonArray commands = requestElement.getAsJsonArray();
                if (commands.size() == 0) {
                    return errorResponse("VDB batch command must contain at least one action");
                }
                List<String> results = new ArrayList<>();
                for (JsonElement cmd : commands) {
                    if (!cmd.isJsonObject()) {
                        return errorResponse("Each VDB batch action must be a JSON object");
                    }
                    results.add(processSingleCommand(cmd.getAsJsonObject()));
                }
                return successResponse(results);
            }

            JsonObject command = requestElement.getAsJsonObject();
            CommandValidator.validateCommandStructure(command);
            if (command.has("commands")) {
                JsonArray batch = command.getAsJsonArray("commands");
                VDB.beginTransaction();
                List<Object> results = new ArrayList<>();
                for (int i = 0; i < batch.size(); i++) {
                    String raw = processSingleCommand(batch.get(i).getAsJsonObject());
                    JsonObject parsed = gson.fromJson(raw, JsonObject.class);
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("index", i);
                    item.put("status", parsed.has("status") ? parsed.get("status").getAsString() : "error");
                    if (parsed.has("data")) item.put("data", jsonElementToValue(parsed.get("data")));
                    results.add(item);
                    if (!"success".equals(item.get("status"))) {
                        VDB.abortTransaction();
                        return successResponse(createResponseMap("committed", false, "results", results));
                    }
                }
                VDB.commitTransaction();
                return successResponse(createResponseMap("committed", true, "results", results));
            }
            String result = processSingleCommand(command);
            if (!isConsoleInterface && DirectoryUtil.logger != null) {
                DirectoryUtil.logger.log("[VQL][RESPONSE] " + result);
            }

            if (session != null && (!session.getCurrentDomain().equals(currentDomain) ||
                    !session.getCurrentDB().equals(currentDB))) {
                session.setCurrentDomain(currentDomain);
                session.setCurrentDB(currentDB);
            }

            return result;
        } catch (Exception e) {
            return errorResponse(e.getMessage());
        }
    }

    private String processSingleCommand(JsonObject command) {
        try {
            CommandValidator.validateCommandStructure(command);
            if (command.has("action")) {
                command = normalizeOperationCommand(command);
            }
            if (command.has("whoami")) {
                return handleWhoamiCommand();
            } else if (command.has("help")) {
                return handleHelpCommand(command.get("help"));
            } else if (command.has("context")) {
                return getContext();
            } else if (command.has("echo")) {
                return processEchoCommand(command);
            } else if (command.has("list")) {
                String listType = command.get("list").getAsString();
                return handleListCommand(listType);
            } else if (command.has("define")) {
                return handleDefineCommand(command.getAsJsonObject("define"));
            } else if (command.has("use")) {
                JsonElement useElement = command.get("use");
                if (useElement.isJsonObject()) {
                    return handleUseCommand(useElement.getAsJsonObject());
                }
                if (useElement.isJsonPrimitive() && useElement.getAsJsonPrimitive().isString()) {
                    JsonObject useCmd = new JsonObject();
                    useCmd.addProperty("domain", useElement.getAsString());
                    return handleUseCommand(useCmd);
                }
                return errorResponse("Invalid use command: expected string or object");
            } else if (command.has("create")) {
                return handleCreateCommand(command.getAsJsonObject("create"));
            } else if (command.has("read")) {
                return handleReadCommand(command);
            } else if (command.has("update")) {
                return handleUpdateCommand(command);
            } else if (command.has("delete")) {
                return handleDeleteCommand(command.getAsJsonObject("delete"));
            } else if (command.has("aggregate")) {
                return handleAggregateCommand(command);
            } else if (command.has("drop")) {
                return handleDropCommand(command);
            } else if (command.has("domain_status")) {
                return handleDomainStatusCommand(command.getAsJsonObject("domain_status"));
            } else if (command.has("index")) {
                return handleIndexCommand(command.getAsJsonObject("index"));
            } else if (command.has("model")) {
                return handleModelCommand(command.getAsJsonObject("model"));
            } else if (command.has("tumi")) {
                return handleTumiCommand(command.getAsJsonObject("tumi"));
            } else if (command.has("script")) {
                return handleScriptCommand(command.getAsJsonObject("script"));
            } else if (command.has("transaction")) {
                return handleTransactionCommand(command.get("transaction"));
            } else if (command.has("export")) {
                return handleExportCommand(command.get("export"));
            }

            return errorResponse("No valid command found");
        } catch (Exception e) {
            return errorResponse(e.getMessage());
        }
    }

    /** Convert the concise operation-object form into the existing internal handlers. */
    private JsonObject normalizeOperationCommand(JsonObject source) {
        String action = source.get("action").getAsString().trim().toLowerCase(Locale.ROOT);
        JsonObject out = new JsonObject();
        String collection = source.has("collection") ? source.get("collection").getAsString() : "";
        JsonElement where = source.has("where") ? source.get("where") : new JsonObject();
        switch (action) {
            case "help": {
                JsonObject help = new JsonObject();
                if (source.has("topic")) help.add("topic", source.get("topic"));
                if (source.has("section")) help.add("section", source.get("section"));
                if (source.has("page")) help.add("page", source.get("page"));
                if (source.has("page_size")) help.add("page_size", source.get("page_size"));
                if (source.has("pageSize")) help.add("page_size", source.get("pageSize"));
                out.add("help", help);
                break;
            }
            case "context": out.add("context", new JsonObject()); break;
            case "whoami": out.add("whoami", new JsonObject()); break;
            case "echo": out.add("echo", source.has("value") ? source.get("value") : new JsonPrimitive("")); break;
            case "export": {
                JsonObject export = source.deepCopy();
                export.remove("action");
                if (export.entrySet().isEmpty() && source.has("value")) {
                    export.add("value", source.get("value"));
                }
                out.add("export", export);
                break;
            }
            case "define": case "use": {
                JsonObject target = new JsonObject();
                if (source.has("domain")) target.add("domain", source.get("domain"));
                if (source.has("db")) target.add("db", source.get("db"));
                if (source.has("database")) target.add("db", source.get("database"));
                if (source.has("name")) {
                    String resource = source.has("resource") ? source.get("resource").getAsString() : "domain";
                    target.add(resource.equalsIgnoreCase("db") || resource.equalsIgnoreCase("database") ? "db" : "domain", source.get("name"));
                }
                out.add(action, target);
                break;
            }
            case "list":
                out.addProperty("list", source.has("resource") ? source.get("resource").getAsString() : source.has("type") ? source.get("type").getAsString() : "collections");
                break;
            case "find": case "read":
                out.addProperty("read", collection);
                out.add("query", where);
                JsonObject args = new JsonObject();
                if (source.has("limit")) args.add("limit", source.get("limit"));
                if (source.has("projection")) args.add("projection", source.get("projection"));
                out.add("args", args);
                break;
            case "insert": case "create":
                JsonObject create = new JsonObject();
                create.add(collection, source.get("document"));
                out.add("create", create);
                break;
            case "update":
                JsonObject update = new JsonObject();
                JsonObject updateData = new JsonObject();
                updateData.add("query", where);
                JsonObject flatData = source.has("set") && source.get("set").isJsonObject()
                        ? source.getAsJsonObject("set") : new JsonObject();
                if (source.has("inc") && source.get("inc").isJsonObject()) {
                    flatData.add("$inc", source.get("inc"));
                }
                if (source.has("unset") && source.get("unset").isJsonObject()) {
                    flatData.add("$unset", source.get("unset"));
                }
                updateData.add("data", flatData);
                update.add(collection, updateData);
                out.add("update", update);
                break;
            case "delete":
                JsonObject delete = new JsonObject();
                JsonObject deleteData = new JsonObject();
                deleteData.add("query", where);
                delete.add(collection, deleteData);
                out.add("delete", delete);
                break;
            case "drop":
                JsonObject drop = new JsonObject();
                if (source.has("domain")) drop.add("domain", source.get("domain"));
                else if (source.has("db") || source.has("database")) drop.add("db", source.has("db") ? source.get("db") : source.get("database"));
                else drop.addProperty("collection", collection);
                out.add("drop", drop); break;
            case "drop_collection": {
                JsonObject dropCollection = new JsonObject(); dropCollection.addProperty("collection", collection); out.add("drop", dropCollection); break;
            }
            case "drop_domain": {
                JsonObject dropDomain = new JsonObject(); dropDomain.add("domain", source.has("domain") ? source.get("domain") : source.get("name")); out.add("drop", dropDomain); break;
            }
            case "drop_db": {
                JsonObject dropDb = new JsonObject(); dropDb.add("db", source.has("db") ? source.get("db") : source.has("database") ? source.get("database") : source.get("name")); out.add("drop", dropDb); break;
            }
            case "domain_status": case "domain_suspend": case "domain_resume": {
                JsonObject status = new JsonObject();
                if (source.has("domain")) status.add("domain", source.get("domain"));
                else if (source.has("name")) status.add("domain", source.get("name"));
                String operation = action.equals("domain_suspend") ? "suspend"
                        : action.equals("domain_resume") ? "resume"
                        : source.has("operation") ? source.get("operation").getAsString() : "get";
                status.addProperty("operation", operation);
                out.add("domain_status", status);
                break;
            }
            case "aggregate": {
                out.addProperty("aggregate", collection);
                out.add("pipeline", source.has("pipeline") ? source.get("pipeline") : new JsonArray());
                break;
            }
            case "create_collection":
                JsonObject schema = source.has("schema") && source.get("schema").isJsonObject() ? source.getAsJsonObject("schema") : new JsonObject();
                schema.addProperty("__liwiro_collection_only", true);
                JsonObject createCollection = new JsonObject(); createCollection.add(collection, schema); out.add("create", createCollection); break;
            case "create_index": case "drop_index": case "list_indexes": case "rebuild_indexes":
                JsonObject index = new JsonObject();
                index.addProperty("operation", action.substring(
                        0,
                        action.length() - (action.endsWith("_indexes") ? "_indexes".length() : "_index".length())));
                index.addProperty("collection", collection);
                if (source.has("field")) index.add("field", source.get("field"));
                if (source.has("unique")) index.add("unique", source.get("unique"));
                if (source.has("sparse")) index.add("sparse", source.get("sparse"));
                out.add("index", index);
                break;
            case "model_get": case "model_delete": {
                JsonObject model = new JsonObject();
                model.add(action.endsWith("delete") ? "delete" : "get", source.has("model") ? source.get("model") : source.get("name"));
                out.add("model", model);
                break;
            }
            case "script_create": {
                JsonObject script = new JsonObject();
                JsonObject createScript = new JsonObject();
                createScript.addProperty("name", source.get("name").getAsString());
                if (source.has("service")) createScript.add("service", source.get("service"));
                if (source.has("code")) createScript.add("code", source.get("code"));
                script.add("create", createScript); out.add("script", script); break;
            }
            case "script_read": case "script_delete": {
                JsonObject script = new JsonObject(); script.add(action.endsWith("delete") ? "delete" : "read", source.get("name")); out.add("script", script); break;
            }
            case "script_execute": {
                JsonObject script = new JsonObject(); JsonObject execute = new JsonObject(); execute.add("name", source.get("name")); execute.add("params", source.has("params") ? source.get("params") : new JsonObject()); script.add("execute", execute); out.add("script", script); break;
            }
            case "script_list": {
                JsonObject script = new JsonObject(); script.addProperty("list", true); out.add("script", script); break;
            }
            case "transaction_begin": case "transaction_commit": case "transaction_abort":
                out.addProperty("transaction", action.substring("transaction_".length())); break;
            case "tumi":
                JsonObject tumi = new JsonObject();
                if (source.has("payload") && source.get("payload").isJsonObject()) {
                    tumi.add(source.has("operation") ? source.get("operation").getAsString() : "list", source.get("payload"));
                } else {
                    JsonObject payload = source.deepCopy();
                    payload.remove("action");
                    String operation = payload.has("operation") ? payload.remove("operation").getAsString() : "list";
                    if ("list".equalsIgnoreCase(operation) && payload.has("resource")) {
                        String resource = payload.get("resource").getAsString();
                        if ("permissions".equalsIgnoreCase(resource) && payload.has("username")) {
                            JsonObject list = new JsonObject();
                            list.add("permissions", payload.get("username"));
                            tumi.add("list", list);
                        } else {
                            tumi.add("list", payload.get("resource"));
                        }
                    } else if (("create".equalsIgnoreCase(operation) || "update".equalsIgnoreCase(operation))
                            && payload.has("role") && payload.get("role").isJsonPrimitive()
                            && !payload.has("username")) {
                        JsonObject role = new JsonObject();
                        role.addProperty("name", payload.remove("role").getAsString());
                        if (payload.has("permissions")) role.add("permissions", payload.remove("permissions"));
                        if (payload.has("scope")) role.add("scope", payload.remove("scope"));
                        tumi.add(operation, new JsonObject());
                        tumi.getAsJsonObject(operation).add("role", role);
                    } else {
                        tumi.add(operation, payload);
                    }
                }
                out.add("tumi", tumi);
                break;
            default:
                throw new IllegalArgumentException("Unsupported action: " + action);
        }
        return out;
    }

    private String processEchoCommand(JsonObject command) {
        String message = command.get("echo").getAsString();
        System.out.println(message);
        return successResponse();
    }

    private String handleDefineCommand(JsonObject defineCmd) {
        if (defineCmd.has("domain") && defineCmd.has("db")) {
            String domain = defineCmd.get("domain").getAsString().toLowerCase();
            String db = defineCmd.get("db").getAsString().toLowerCase();

            try {
                VDB.defineDomain(domain, db, true);
                return successResponse("Domain defined: " + domain + " with default database '" + db + "'");
            } catch (Exception e) {
                return errorResponse(e.getMessage());
            }
        } else if (defineCmd.has("domain")) {
            return handleDomainCreationCommand(defineCmd);
        } else if (defineCmd.has("db")) {
            String db = defineCmd.get("db").getAsString().toLowerCase();
            if (VDB.dbExists(db)) {
                return warningResponse("Database already exists: " + db);
            }
            try {
                VDB.createDatabase(db);
                return successResponse("Database defined: " + db);
            } catch (Exception e) {
                return errorResponse("Failed to create database: " + e.getMessage());
            }
        }
        return errorResponse("Invalid define command");
    }

    private String handleDomainCreationCommand(JsonObject defineCmd) {
        try {
            String domain = defineCmd.get("domain").getAsString().toLowerCase();
            User creator = VDB.currentUser;

            if (creator == null) {
                return errorResponse("Authentication required to create domains");
            }

            // Create domain with ownership
            DirectoryUtil.createDomain(domain, creator);

            // Verify persistence
            User freshUser = UserManager.getInstance().getUser(creator.getUsername());
            if (!freshUser.getOwnedDomains().contains(domain)) {
                throw new RuntimeException("Domain ownership not persisted");
            }

            return successResponse("Domain defined: " + domain + " with default database 'main'");

        } catch (Exception e) {
            return errorResponse("Domain creation failed: " + e.getMessage());
        }
    }

    private String listScripts() {
        try {
            if (!canReadScripts()) {
                return errorResponse("Permission denied for listing scripts");
            }
            List<String> scripts = VDB.listScripts();
            return successResponse(scripts);
        } catch (Exception e) {
            return errorResponse("Failed to list scripts: " + e.getMessage());
        }
    }

    private String listModels() {
        try {
            List<String> models = new ArrayList<>(ModelRegistry.registry.keySet());
            return successResponse(models);
        } catch (Exception e) {
            return errorResponse("Failed to list models: " + e.getMessage());
        }
    }

    private String handleUseCommand(JsonObject useCmd) {
        String newDomain = useCmd.has("domain") ? useCmd.get("domain").getAsString().toLowerCase() : null;
        String newDb = useCmd.has("db") ? useCmd.get("db").getAsString().toLowerCase() : null;

        if (newDomain != null && !DirectoryUtil.domainExists(newDomain)) {
            return errorResponse("Domain does not exist: " + newDomain);
        }

        if (newDomain != null && !currentUser.isSuperAdmin()) {
            try {
                Map<String, Object> domainInfo = BsonStorage.readMap(DirectoryUtil.getDomainMetadataPath(newDomain));
                if ("suspended".equalsIgnoreCase(String.valueOf(domainInfo.getOrDefault("status", "active")))) {
                    return errorResponse("Domain is suspended: " + newDomain);
                }
            } catch (IOException e) {
                return errorResponse("Failed to read domain status for " + newDomain);
            }
        }

        // Ownership check here
        if (newDomain != null) {
            if (!currentUser.isSuperAdmin() && !currentUser.ownsDomain(newDomain)) {
                return errorResponse("Permission denied: You don't own this domain");
            }
        }

        if (newDomain != null && newDb == null) {
            Path configPath = DirectoryUtil.getDomainConfigPath(newDomain);
            try {
                Map<String, String> config = gson.fromJson(
                        BsonStorage.toJson(BsonStorage.readValue(configPath)),
                        new TypeToken<Map<String, String>>() {
                        }.getType()
                );
                newDb = config.getOrDefault("default_db", "main");
            } catch (IOException e) {
                return errorResponse("Failed to read domain config for " + newDomain);
            }
        }

        if (newDb != null) {
            String targetDomain = newDomain != null ? newDomain : currentDomain;
            if (!DirectoryUtil.dbExists(targetDomain, newDb)) {
                return errorResponse("Database does not exist in domain " + targetDomain + ": " + newDb);
            }
        }

        if (newDomain != null) {
            currentDomain = newDomain;
            VDB.setDomain(newDomain);
        }

        if (newDb != null) {
            currentDB = newDb;
            VDB.useDatabase(newDb);
        }

        return successResponse("Using domain: " + currentDomain + ", database: " + currentDB);
    }

    private String handleTumiCommand(JsonObject tumiCmd) {
        Tumi tumiProcessor = new Tumi(currentUser, currentDomain, currentDB);
        return tumiProcessor.processCommand(tumiCmd);
    }

    private String handleModelCommand(JsonObject modelCmd) {
        if (modelCmd == null) {
            return errorResponse("Invalid model command");
        }
        if (modelCmd.has("get")) {
            return handleGetModelCommand(modelCmd.get("get").getAsString());
        }
        if (modelCmd.has("delete")) {
            if (!currentUser.isSuperAdmin()
                    && !currentUser.ownsDomain(currentDomain)
                    && !currentUser.hasPermission(currentDomain, currentDB, "WRITE")) {
                return errorResponse("Permission denied for deleting model");
            }
            return handleDeleteModelCommand(modelCmd.get("delete").getAsString());
        }
        return errorResponse("Invalid model command");
    }

    private String handleGetModelCommand(String collectionName) {
        try {
            if (!VDB.collectionExists(currentDomain, currentDB, collectionName)) {
                return errorResponse("Collection does not exist: " + collectionName);
            }

            Path modelPath = DirectoryUtil.getCollectionModelPath(currentDomain, currentDB, collectionName);

            if (!Files.exists(modelPath)) {
                return errorResponse("No model defined for collection: " + collectionName);
            }

            Map<String, Object> model = BsonStorage.readMap(modelPath);

            return successResponse(model);
        } catch (IOException e) {
            return errorResponse("Failed to read model: " + e.getMessage());
        }
    }

    private String handleDeleteModelCommand(String collectionName) {
        try {
            if (!VDB.collectionExists(currentDomain, currentDB, collectionName)) {
                return errorResponse("Collection does not exist: " + collectionName);
            }

            Path modelPath = DirectoryUtil.getCollectionModelPath(currentDomain, currentDB, collectionName);

            if (Files.exists(modelPath)) {
                Files.delete(modelPath);
                return successResponse("Model deleted for collection: " + collectionName);
            } else {
                return warningResponse("No model found for collection: " + collectionName);
            }
        } catch (IOException e) {
            return errorResponse("Failed to delete model: " + e.getMessage());
        }
    }

    private String handleWhoamiCommand() {
        if (currentUser == null)
            return errorResponse("Not authenticated");

        // Get fresh copy from UserManager
        User freshUser = UserManager.getInstance().getUser(currentUser.getUsername());
        Set<String> visibleDomains = new HashSet<>(DirectoryUtil.getDomains());
        List<String> ownedDomains = freshUser.getOwnedDomains().stream()
                .filter(visibleDomains::contains)
                .sorted()
                .collect(Collectors.toList());

        Map<String, Object> userInfo = new LinkedHashMap<>();
        userInfo.put("owned_domains", ownedDomains);
        userInfo.put("username", freshUser.getUsername());
        userInfo.put("email", freshUser.getEmail());
        userInfo.put("role", freshUser.getRole());
        userInfo.put("role_level", freshUser.getRoleLevel());
        userInfo.put("user_type", freshUser.getRole());

        return successResponse(userInfo);
    }

    private String handleHelpCommand(JsonElement helpElement) {
        String topic = null;
        Integer page = null;
        Integer pageSize = null;
        if (helpElement != null) {
            if (helpElement.isJsonPrimitive()) {
                topic = helpElement.getAsString();
            } else if (helpElement.isJsonObject()) {
                JsonObject obj = helpElement.getAsJsonObject();
                if (obj.has("topic")) {
                    topic = obj.get("topic").getAsString();
                } else if (obj.has("section")) {
                    topic = obj.get("section").getAsString();
                }
                if (obj.has("page")) {
                    page = obj.get("page").getAsInt();
                }
                if (obj.has("page_size")) {
                    pageSize = obj.get("page_size").getAsInt();
                }
            }
        }
        String raw = HelpProvider.getHelpJson(topic, page, pageSize, currentUser, currentDomain, currentDB);
        JsonElement parsed = gson.fromJson(raw, JsonElement.class);
        if (parsed != null && parsed.isJsonObject() && currentUser != null) {
            JsonObject root = parsed.getAsJsonObject();
            JsonObject rbac = new JsonObject();
            rbac.addProperty("user", currentUser.getUsername());
            rbac.addProperty("role", currentUser.getRole());
            rbac.addProperty("domain", currentDomain);
            rbac.addProperty("database", currentDB);
            try {
                JsonElement domains = gson.fromJson(listDomains(), JsonObject.class).getAsJsonObject().get("data");
                JsonElement dbs = gson.fromJson(listDatabases(), JsonObject.class).getAsJsonObject().get("data");
                JsonElement collections = gson.fromJson(listCollections(), JsonObject.class).getAsJsonObject().get("data");
                if (domains != null) {
                    addBoundedHelpVisibility(rbac, "visible_domains", domains);
                }
                if (dbs != null) {
                    addBoundedHelpVisibility(rbac, "visible_databases", dbs);
                }
                if (collections != null) {
                    addBoundedHelpVisibility(rbac, "visible_collections", collections);
                }
            } catch (Exception ignored) {
                // Keep help resilient even if RBAC context extraction fails.
            }
            root.add("rbac_context", rbac);
        }
        return gson.toJson(parsed);
    }

    private void addBoundedHelpVisibility(JsonObject rbac, String field, JsonElement values) {
        if (!values.isJsonArray()) {
            rbac.add(field, values.deepCopy());
            return;
        }
        JsonArray source = values.getAsJsonArray();
        JsonArray preview = new JsonArray();
        int limit = Math.min(source.size(), HelpProvider.MAX_PAGE_SIZE);
        for (int i = 0; i < limit; i++) {
            preview.add(source.get(i).deepCopy());
        }
        rbac.add(field, preview);
        rbac.addProperty(field + "_count", source.size());
        rbac.addProperty(field + "_truncated", source.size() > limit);
    }

    private String handleCreateCommand(JsonObject createCmd) {
        for (String key : createCmd.keySet()) {
            JsonElement element = createCmd.get(key);

            if (key.equals("script")) {
                JsonObject scriptData = element.getAsJsonObject();
                return handleScriptCreate(scriptData);
            }

            if (element.isJsonObject()) {
                JsonObject data = element.getAsJsonObject();

                if (data.has("__liwiro_collection_only")) {
                    data.remove("__liwiro_collection_only");
                    if (!canWriteCollection(key)) {
                        return errorResponse("Permission denied for creating collection/schema: " + key);
                    }
                    Map<String, Object> schema = jsonObjectToMap(data);
                    try {
                        VDB.createCollection(key, schema);
                        return successResponse("Collection created: " + key);
                    } catch (Exception e) {
                        return errorResponse("Collection creation failed: " + e.getMessage());
                    }
                }

                if (isSchemaDefinition(data)) {
                    if (!canWriteCollection(key)) {
                        return errorResponse("Permission denied for creating collection/schema: " + key);
                    }
                    Map<String, Object> schema = jsonObjectToMap(data);
                    try {
                        VDB.createCollection(key, schema);
                        return successResponse("Collection created with schema: " + key);
                    } catch (Exception e) {
                        return errorResponse("Collection creation failed: " + e.getMessage());
                    }
                } else {
                    if (!canWriteCollection(key)) {
                        return errorResponse("Permission denied for writing collection: " + key);
                    }
                    try {
                        Map<String, Object> doc = jsonObjectToMap(data);
                        Map<String, Object> insertedDoc = VDB.insert(key, doc);
                        return successResponse(insertedDoc);
                    } catch (Exception e) {
                        return errorResponse("Document creation failed: " + e.getMessage());
                    }
                }
            }
        }

        return errorResponse("Invalid create command");
    }

    private boolean isSchemaDefinition(JsonObject data) {
        for (Map.Entry<String, JsonElement> entry : data.entrySet()) {
            JsonElement element = entry.getValue();
            if (element.isJsonObject()) {
                JsonObject fieldDef = element.getAsJsonObject();
                if (fieldDef.has("type") || fieldDef.has("required") || fieldDef.has("properties")) {
                    return true;
                }
            }
        }
        return false;
    }

    private String handleReadCommand(JsonObject command) {
        String collection = command.get("read").getAsString();
        if (!canReadCollection(collection)) {
            return errorResponse("Permission denied for reading collection: " + collection);
        }
        JsonObject queryJson = command.has("query") ? command.getAsJsonObject("query") : new JsonObject();
        JsonObject argsJson = command.has("args") ? command.getAsJsonObject("args") : new JsonObject();

        try {
            List<Map<String, Object>> docs = VDB.findAll(collection);

            Map<String, Object> query = jsonObjectToMap(queryJson);
            Map<String, Boolean> projection = argsJson.has("projection")
                    ? jsonObjectToBooleanMap(argsJson.getAsJsonObject("projection"))
                    : Collections.emptyMap();

            List<Map<String, Object>> filtered = docs.stream()
                    .filter(doc -> QueryEvaluator.matches(doc, query))
                    .collect(Collectors.toList());

            List<Map<String, Object>> projected = filtered.stream()
                    .map(doc -> applyProjection(doc, projection))
                    .collect(Collectors.toList());

            int limit = argsJson.has("limit") ? argsJson.get("limit").getAsInt() : 100;
            List<Map<String, Object>> results = projected.stream()
                    .limit(limit)
                    .collect(Collectors.toList());

            return successResponse(results);
        } catch (Exception e) {
            return errorResponse("Read failed: " + e.getMessage());
        }
    }

    private Map<String, Object> applyProjection(Map<String, Object> doc, Map<String, Boolean> projection) {
        if (projection.isEmpty()) {
            return doc;
        }
        Map<String, Object> result = new HashMap<>();
        projection.forEach((field, include) -> {
            if (include) {
                Object val = QueryEvaluator.getNestedField(doc, field);
                if (val != null) {
                    result.put(field, val);
                }
            }
        });
        return result;
    }

    private String handleUpdateCommand(JsonObject command) {
        JsonObject updateCmd = command.getAsJsonObject("update");

        for (Map.Entry<String, JsonElement> entry : updateCmd.entrySet()) {
            String collectionName = entry.getKey();
            if (!canWriteCollection(collectionName)) {
                return errorResponse("Permission denied for updating collection: " + collectionName);
            }
            JsonObject updateData = entry.getValue().getAsJsonObject();

            JsonObject query = updateData.getAsJsonObject("query");
            JsonObject data = updateData.getAsJsonObject("data");

            try {
                List<Map<String, Object>> docs = new Collection(collectionName).find(
                        jsonObjectToMap(query), Integer.MAX_VALUE);

                int updatedCount = docs.stream()
                        .map(doc -> {
                            data.entrySet().forEach(e -> applyUpdateField(doc, e.getKey(), e.getValue()));
                            try {
                                VDB.update(collectionName, (String) doc.get("_id"), doc);
                                return doc;
                            } catch (Exception ex) {
                                System.err.println("Error updating document: " + ex.getMessage());
                                return null;
                            }
                        })
                        .filter(Objects::nonNull)
                        .collect(Collectors.toList()).size();

                return successResponse(createResponseMap("updated", updatedCount));
            } catch (Exception e) {
                return errorResponse("Update failed: " + e.getMessage());
            }
        }
        return errorResponse("Invalid update command");
    }

    private void applyUpdateField(Map<String, Object> document, String key, JsonElement value) {
        if ("$set".equals(key) && value.isJsonObject()) {
            value.getAsJsonObject().entrySet().forEach(entry ->
                    document.put(entry.getKey(), jsonElementToValue(entry.getValue())));
            return;
        }
        if ("$inc".equals(key) && value.isJsonObject()) {
            value.getAsJsonObject().entrySet().forEach(entry -> {
                Object deltaValue = jsonElementToValue(entry.getValue());
                Object currentValue = document.get(entry.getKey());
                if (!(deltaValue instanceof Number) || (currentValue != null && !(currentValue instanceof Number))) {
                    throw new IllegalArgumentException("$inc requires numeric fields: " + entry.getKey());
                }
                boolean decimal = deltaValue instanceof Double || deltaValue instanceof Float
                        || currentValue instanceof Double || currentValue instanceof Float;
                BigDecimal current = currentValue == null
                        ? BigDecimal.ZERO : new BigDecimal(currentValue.toString());
                BigDecimal result = current.add(new BigDecimal(deltaValue.toString()));
                if (decimal) {
                    document.put(entry.getKey(), result.doubleValue());
                    return;
                }
                BigInteger integral = result.toBigIntegerExact();
                if (integral.compareTo(BigInteger.valueOf(Integer.MIN_VALUE)) >= 0
                        && integral.compareTo(BigInteger.valueOf(Integer.MAX_VALUE)) <= 0) {
                    document.put(entry.getKey(), integral.intValue());
                } else if (integral.compareTo(BigInteger.valueOf(Long.MIN_VALUE)) >= 0
                        && integral.compareTo(BigInteger.valueOf(Long.MAX_VALUE)) <= 0) {
                    document.put(entry.getKey(), integral.longValue());
                } else {
                    throw new IllegalArgumentException("$inc result exceeds supported integer range: " + entry.getKey());
                }
            });
            return;
        }
        if ("$unset".equals(key) && value.isJsonObject()) {
            value.getAsJsonObject().entrySet().forEach(entry -> document.remove(entry.getKey()));
            return;
        }
        document.put(key, jsonElementToValue(value));
    }

    private String handleDeleteCommand(JsonObject deleteCommand) {
        for (String collection : deleteCommand.keySet()) {
            if (!canWriteCollection(collection)) {
                return errorResponse("Permission denied for deleting from collection: " + collection);
            }
            JsonObject deleteData = deleteCommand.getAsJsonObject(collection);
            JsonObject query = deleteData.getAsJsonObject("query");

            try {
                int deletedCount = new Collection(collection)
                        .delete(jsonObjectToMap(query));
                return successResponse(createResponseMap("deleted", deletedCount));
            } catch (Exception e) {
                return errorResponse("Delete failed: " + e.getMessage());
            }
        }
        return errorResponse("Invalid delete command");
    }

    private String handleAggregateCommand(JsonObject command) {
        String collection = command.get("aggregate").getAsString();
        if (!canReadCollection(collection)) {
            return errorResponse("Permission denied for aggregating collection: " + collection);
        }
        if (!command.has("pipeline") || !command.get("pipeline").isJsonArray()) {
            return errorResponse("Aggregate requires a pipeline array");
        }
        try {
            List<Map<String, Object>> pipeline = new ArrayList<>();
            for (JsonElement stage : command.getAsJsonArray("pipeline")) {
                if (!stage.isJsonObject()) {
                    return errorResponse("Each aggregate pipeline stage must be an object");
                }
                pipeline.add(jsonObjectToMap(stage.getAsJsonObject()));
            }
            return successResponse(VDB.aggregate(collection, pipeline));
        } catch (Exception e) {
            return errorResponse("Aggregation failed: " + e.getMessage());
        }
    }

    private String handleDropCommand(JsonObject command) {
        if (!command.has("drop")) {
            return errorResponse("Invalid drop command structure");
        }

        JsonObject dropCmd = command.getAsJsonObject("drop");

        if (dropCmd.has("domain")) {
            String domain = dropCmd.get("domain").getAsString().toLowerCase();
            return handleDomainDrop(domain);
        } else if (dropCmd.has("db")) {
            String db = dropCmd.get("db").getAsString().toLowerCase();
            return handleDbDrop(db);
        } else if (dropCmd.has("collection")) {
            String collection = dropCmd.get("collection").getAsString().toLowerCase();
            try {
                if (!currentUser.hasPermission(currentDomain, currentDB, "DROP_COLLECTION")) {
                    return errorResponse("Permission denied for dropping collection");
                }
                VDB.drop(collection);
                return successResponse("Collection dropped: " + collection);
            } catch (Exception e) {
                return errorResponse("Collection drop failed: " + e.getMessage());
            }
        }
        return errorResponse("Invalid drop command: No valid target specified");
    }

    private String handleIndexCommand(JsonObject indexCommand) {
        if (indexCommand == null || !indexCommand.has("operation") || !indexCommand.has("collection")) {
            return errorResponse("Invalid index command: operation and collection are required");
        }

        String operation = indexCommand.get("operation").getAsString().trim().toLowerCase(Locale.ROOT);
        String collection = indexCommand.get("collection").getAsString().trim();
        if (collection.isEmpty()) {
            return errorResponse("Invalid index command: collection is required");
        }

        boolean readOnly = "list".equals(operation);
        if (readOnly ? !canReadCollection(collection) : !canWriteCollection(collection)) {
            return errorResponse("Permission denied for " + operation + " indexes on collection: " + collection);
        }

        try {
            switch (operation) {
                case "create":
                    if (!indexCommand.has("field") || indexCommand.get("field").getAsString().trim().isEmpty()) {
                        return errorResponse("Invalid index command: field is required for create_index");
                    }
                    return successResponse(VDB.createIndex(
                            collection,
                            indexCommand.get("field").getAsString().trim(),
                            indexCommand.has("unique") && indexCommand.get("unique").getAsBoolean(),
                            indexCommand.has("sparse") && indexCommand.get("sparse").getAsBoolean()));
                case "drop":
                    if (!indexCommand.has("field") || indexCommand.get("field").getAsString().trim().isEmpty()) {
                        return errorResponse("Invalid index command: field is required for drop_index");
                    }
                    return successResponse(VDB.dropIndex(collection, indexCommand.get("field").getAsString().trim()));
                case "list":
                    return successResponse(VDB.listIndexes(collection));
                case "rebuild":
                    return successResponse(VDB.rebuildIndexes(collection));
                default:
                    return errorResponse("Unknown index operation: " + operation);
            }
        } catch (Exception e) {
            return errorResponse("Index operation failed: " + e.getMessage());
        }
    }

    private String handleDomainDrop(String domain) {
        try {
            if (!currentUser.isSuperAdmin() && !currentUser.ownsDomain(domain)) {
                return errorResponse("Permission denied: You don't own this domain");
            }
            boolean droppedActiveDomain = currentDomain.equals(domain);
            DirectoryUtil.deleteDomain(domain);
            if (droppedActiveDomain) {
                resetContextAfterDomainDrop();
            }
            return successResponse("Domain dropped: " + domain);
        } catch (IOException e) {
            return errorResponse("Domain deletion failed: " + e.getMessage());
        }
    }

    private String handleDbDrop(String dbName) {
        dbName = dbName.toLowerCase();

        if (!DirectoryUtil.dbExists(currentDomain, dbName)) {
            return errorResponse("Database '" + dbName + "' does not exist in domain '" + currentDomain + "'");
        }

        if (!currentUser.hasPermission(currentDomain, dbName, "DROP_DATABASE")) {
            return errorResponse("Permission denied for dropping database");
        }

        try {
            boolean droppedCurrentDb = currentDB.equals(dbName);
            DirectoryUtil.deleteDatabase(currentDomain, dbName);
            if (droppedCurrentDb) {
                resetContextAfterDbDrop();
            }
            return successResponse("Database dropped: " + dbName);
        } catch (IOException e) {
            return errorResponse("Database drop failed: " + e.getMessage());
        }
    }

    private void resetContextAfterDomainDrop() {
        String fallbackDomain = "default";
        if (!DirectoryUtil.domainExists(fallbackDomain)) {
            List<String> domains = DirectoryUtil.getDomains();
            if (!domains.isEmpty()) {
                fallbackDomain = domains.get(0);
            }
        }
        currentDomain = fallbackDomain;
        currentDB = "main";
        if (!DirectoryUtil.dbExists(currentDomain, currentDB)) {
            List<String> dbs = DirectoryUtil.getDatabases(currentDomain);
            if (!dbs.isEmpty()) {
                currentDB = dbs.get(0);
            }
        }
    }

    private void resetContextAfterDbDrop() {
        String fallbackDb = "main";
        if (!DirectoryUtil.dbExists(currentDomain, fallbackDb)) {
            List<String> dbs = DirectoryUtil.getDatabases(currentDomain);
            if (!dbs.isEmpty()) {
                fallbackDb = dbs.get(0);
            }
        }
        currentDB = fallbackDb;
    }

    private Map<String, Object> createResponseMap(Object... keyValues) {
        Map<String, Object> responseMap = new HashMap<>();
        for (int i = 0; i < keyValues.length; i += 2) {
            if (i + 1 < keyValues.length) {
                responseMap.put(keyValues[i].toString(), keyValues[i + 1]);
            }
        }
        return responseMap;
    }

    private String listAllDomains() {
        try {
            List<String> domains = DirectoryUtil.getDomains();
            return successResponse(domains);
        } catch (Exception e) {
            return errorResponse("Failed to list domains: " + e.getMessage());
        }
    }

    private String listDomains() {
        try {
            List<String> domains = DirectoryUtil.getDomains();
            if (currentUser.isSuperAdmin()) {
                return successResponse(domains);
            }
            Set<String> ownedDomains = currentUser.getOwnedDomains();
            domains = domains.stream().filter(ownedDomains::contains).collect(Collectors.toList());
            return successResponse(domains);
        } catch (Exception e) {
            return errorResponse("Failed to list domains: " + e.getMessage());
        }
    }

    private String listDatabases() {
        try {
            if (!currentUser.isSuperAdmin() && !currentUser.ownsDomain(currentDomain)) {
                if (!currentUser.hasPermission(currentDomain, currentDB, "READ")
                        && !currentUser.hasPermission(currentDomain, currentDB, "DATA_ACCESS")) {
                    return errorResponse("Permission denied for listing databases in domain: " + currentDomain);
                }
            }
            List<String> databases = DirectoryUtil.getDatabases(currentDomain);
            return successResponse(databases);
        } catch (Exception e) {
            return errorResponse("Failed to list databases: " + e.getMessage());
        }
    }

    private String listCollections() {
        try {
            List<String> collections = DirectoryUtil.getCollections(currentDomain, currentDB);
            if (currentUser.isSuperAdmin() || currentUser.ownsDomain(currentDomain)
                    || currentUser.hasPermission(currentDomain, currentDB, "READ")
                    || currentUser.hasPermission(currentDomain, currentDB, "DATA_ACCESS")) {
                return successResponse(collections);
            }
            List<String> filtered = collections.stream()
                    .filter(c -> currentUser.hasCollectionPermission(currentDomain, currentDB, c, "READ")
                            || currentUser.hasCollectionPermission(currentDomain, currentDB, c, "WRITE")
                            || currentUser.hasCollectionPermission(currentDomain, currentDB, c, "DATA_ACCESS"))
                    .collect(Collectors.toList());
            return successResponse(filtered);
        } catch (Exception e) {
            return errorResponse("Failed to list collections: " + e.getMessage());
        }
    }

    private boolean canReadCollection(String collection) {
        return currentUser.isSuperAdmin()
                || currentUser.ownsDomain(currentDomain)
                || currentUser.hasPermission(currentDomain, currentDB, "READ")
                || currentUser.hasPermission(currentDomain, currentDB, "DATA_ACCESS")
                || currentUser.hasCollectionPermission(currentDomain, currentDB, collection, "READ")
                || currentUser.hasCollectionPermission(currentDomain, currentDB, collection, "DATA_ACCESS")
                || currentUser.hasCollectionPermission(currentDomain, currentDB, collection, "WRITE");
    }

    private boolean canWriteCollection(String collection) {
        return currentUser.isSuperAdmin()
                || currentUser.ownsDomain(currentDomain)
                || currentUser.hasPermission(currentDomain, currentDB, "WRITE")
                || currentUser.hasCollectionPermission(currentDomain, currentDB, collection, "WRITE");
    }

    private String handleDomainStatusCommand(JsonObject command) {
        // Read or apply a domain lifecycle status transition and persist metadata.
        if (command == null || !command.has("domain") || !command.has("operation")) {
            return errorResponse("Domain status requires domain and operation");
        }
        String operation = command.get("operation").getAsString().trim().toLowerCase(Locale.ROOT);
        String domain = command.get("domain").getAsString().trim().toLowerCase(Locale.ROOT);
        if (!operation.matches("get|status|suspend|resume|activate")) {
            return errorResponse("Unsupported domain status operation: " + operation);
        }

        if (!currentUser.ownsDomain(domain) && !currentUser.isSuperAdmin()) {
            return errorResponse("Permission denied for domain operation");
        }

        try {
            Path sysPath = DirectoryUtil.getDomainMetadataPath(domain);
            if (!Files.exists(sysPath)) {
                return errorResponse("Domain not found");
            }

            Map<String, Object> domainInfo = BsonStorage.readMap(sysPath);
            if (operation.equals("suspend")) {
                domainInfo.put("status", "suspended");
                BsonStorage.writeValue(sysPath, domainInfo);
            } else if (operation.equals("resume") || operation.equals("activate")) {
                domainInfo.put("status", "active");
                BsonStorage.writeValue(sysPath, domainInfo);
            } else {
                domainInfo.putIfAbsent("status", "active");
            }

            Map<String, Object> responseMap = new HashMap<>();
            responseMap.put("domain", domain);
            responseMap.put("status", domainInfo.getOrDefault("status", "active"));
            return successResponse(responseMap);
        } catch (Exception e) {
            return errorResponse("Operation failed: " + e.getMessage());
        }
    }

    private String handleScriptCreate(JsonObject scriptData) {
        try {
            if (!canWriteScripts()) {
                return errorResponse("Permission denied for creating scripts");
            }
            String scriptName = scriptData.get("name").getAsString();
            String service = scriptData.get("service").getAsString();
            String code = scriptData.get("code").getAsString();

            ScriptDocument doc = VDB.saveScript(scriptName, service, code);
            return successResponse(JsonValueConverter.fromJson(doc.toJSON()));
        } catch (Exception e) {
            return errorResponse("Script creation failed: " + e.getMessage());
        }
    }

    private String successResponse() {
        return successResponse("ok");
    }

    private String handleScriptCommand(JsonObject scriptCmd) {
        try {
            if (scriptCmd.has("create")) {
                return handleScriptCreate(scriptCmd.getAsJsonObject("create"));
            }

            if (scriptCmd.has("read")) {
                if (!canReadScripts()) {
                    return errorResponse("Permission denied for reading scripts");
                }
                String name = scriptCmd.get("read").getAsString();
                ScriptDocument doc = VDB.loadScript(name);
                return successResponse(JsonValueConverter.fromJson(doc.toJSON()));
            }

            if (scriptCmd.has("delete")) {
                if (!canWriteScripts()) {
                    return errorResponse("Permission denied for deleting scripts");
                }
                String name = scriptCmd.get("delete").getAsString();
                boolean deleted = VDB.deleteScript(name);
                if (!deleted) {
                    return warningResponse("Script not found: " + name);
                }
                return successResponse("Script deleted: " + name);
            }

            if (scriptCmd.has("execute")) {
                if (!canReadScripts()) {
                    return errorResponse("Permission denied for executing scripts");
                }
                JsonObject exec = scriptCmd.getAsJsonObject("execute");
                String name = exec.get("name").getAsString();
                Map<String, Object> params = exec.has("params")
                        ? jsonObjectToMap(exec.getAsJsonObject("params"))
                        : Collections.emptyMap();
                return successResponse(VDB.executeScript(name, params));
            }

            if (scriptCmd.has("list")) {
                return listScripts();
            }

            return errorResponse("Invalid script command");
        } catch (Exception e) {
            return errorResponse("Script command failed: " + e.getMessage());
        }
    }

    private boolean canReadScripts() {
        return currentUser.isSuperAdmin()
                || currentUser.ownsDomain(currentDomain)
                || currentUser.hasPermission(currentDomain, currentDB, "READ")
                || currentUser.hasPermission(currentDomain, currentDB, "DATA_ACCESS")
                || currentUser.hasPermission(currentDomain, currentDB, "WRITE");
    }

    private boolean canWriteScripts() {
        return currentUser.isSuperAdmin()
                || currentUser.ownsDomain(currentDomain)
                || currentUser.hasPermission(currentDomain, currentDB, "WRITE");
    }

    private String handleExportCommand(JsonElement exportCmd) {
        Path stagingDir = null;
        try {
            JsonObject options = exportCmd != null && exportCmd.isJsonObject() ? exportCmd.getAsJsonObject() : new JsonObject();
            Path outDir = resolveRequiredExportBaseDirectory(options);
            validateZipOnlyExport(options);
            List<String> requestedDomains = parseRequestedDomains(options);
            List<String> allDomains = DirectoryUtil.getDomains();
            if (requestedDomains.isEmpty()) {
                requestedDomains = allDomains;
            }

            String packageName = options.has("package")
                    ? options.get("package").getAsString()
                    : "vdb-export-" + currentUser.getUsername();
            String safePackageName = sanitizeExportName(packageName);
            String timestamp = String.valueOf(System.currentTimeMillis());

            stagingDir = Files.createTempDirectory("vdb-export-stage-");
            Path exportRoot = stagingDir.resolve(safePackageName + "-" + timestamp).normalize();
            Files.createDirectories(exportRoot);

            List<String> exported = new ArrayList<>();
            Map<String, String> skipped = new LinkedHashMap<>();

            for (String rawDomain : requestedDomains) {
                String domain = rawDomain == null ? "" : rawDomain.trim().toLowerCase(Locale.ROOT);
                if (domain.isEmpty()) {
                    continue;
                }
                if (!allDomains.contains(domain)) {
                    skipped.put(domain, "Domain not found");
                    continue;
                }
                if (!canAccessDomainForExport(domain)) {
                    skipped.put(domain, "No domain access");
                    continue;
                }
                if (!canExportDomain(domain)) {
                    skipped.put(domain, "DATA_EXPORT permission required");
                    continue;
                }
                Path source = DirectoryUtil.getDomainPath(domain);
                Path target = exportRoot.resolve(domain).normalize();
                copyDirectory(source, target);
                exported.add(domain);
            }

            if (exported.isEmpty()) {
                return errorResponse("No domains exported. Verify domain access and DATA_EXPORT permission.");
            }

            Path zipPath = ensureUniquePath(outDir.resolve(exportRoot.getFileName().toString() + ".zip").normalize());
            zipDirectory(exportRoot, zipPath);

            Map<String, Object> out = new LinkedHashMap<>();
            out.put("exported_domains", exported);
            out.put("skipped_domains", skipped);
            out.put("zip_file", zipPath.toString());
            out.put("out_dir", outDir.toString());
            return successResponse(out);
        } catch (Exception e) {
            return errorResponse("Export failed: " + e.getMessage());
        } finally {
            if (stagingDir != null) {
                try {
                    DirectoryUtil.deleteDirectory(stagingDir);
                } catch (Exception ignored) {
                }
            }
        }
    }

    private String handleTransactionCommand(JsonElement transactionCmd) {
        if (transactionCmd == null || !transactionCmd.isJsonPrimitive()) {
            return errorResponse("Invalid transaction command");
        }
        String action = transactionCmd.getAsString().trim().toLowerCase(Locale.ROOT);
        switch (action) {
            case "begin":
                beginTransaction();
                return successResponse("Transaction started");
            case "commit":
                commitTransaction();
                return successResponse("Transaction committed");
            case "abort":
                abortTransaction();
                return successResponse("Transaction aborted");
            default:
                return errorResponse("Invalid transaction command");
        }
    }

    private Path resolveRequiredExportBaseDirectory(JsonObject options) throws IOException {
        if (options == null || !options.has("out_dir") || !options.get("out_dir").isJsonPrimitive()) {
            throw new IOException("out_dir is required for export");
        }
        String requested = options.get("out_dir").getAsString().trim();
        if (requested.isEmpty()) {
            throw new IOException("out_dir is required for export");
        }
        Path requestedPath = Paths.get(requested).toAbsolutePath().normalize();
        if (Files.exists(requestedPath) && !Files.isDirectory(requestedPath)) {
            throw new IOException("out_dir must point to a directory");
        }
        Files.createDirectories(requestedPath);
        return requestedPath;
    }

    private void validateZipOnlyExport(JsonObject options) throws IOException {
        if (options != null && options.has("zip")) {
            JsonElement zipOption = options.get("zip");
            if (zipOption != null && zipOption.isJsonPrimitive() && !zipOption.getAsBoolean()) {
                throw new IOException("Export only supports zip output");
            }
        }
    }

    private Path ensureUniquePath(Path path) throws IOException {
        if (!Files.exists(path)) {
            return path;
        }
        String fileName = path.getFileName().toString();
        int dot = fileName.lastIndexOf('.');
        String base = dot > 0 ? fileName.substring(0, dot) : fileName;
        String ext = dot > 0 ? fileName.substring(dot) : "";
        int i = 1;
        while (i < 10_000) {
            Path candidate = path.getParent().resolve(base + "-" + i + ext).normalize();
            if (!Files.exists(candidate)) {
                return candidate;
            }
            i++;
        }
        throw new IOException("Unable to allocate unique export file name");
    }

    private boolean canAccessDomainForExport(String domain) {
        if (currentUser.isSuperAdmin()) {
            return true;
        }
        if (currentUser.ownsDomain(domain)) {
            return true;
        }
        return currentUser.getAccessibleDomains().contains(domain);
    }

    private boolean canExportDomain(String domain) {
        if (currentUser.isSuperAdmin()) {
            return true;
        }
        return currentUser.ownsDomain(domain) || currentUser.hasExplicitDomainPermission(domain, "DATA_EXPORT");
    }

    private List<String> parseRequestedDomains(JsonObject options) {
        List<String> domains = new ArrayList<>();
        if (options == null || !options.has("domains")) {
            return domains;
        }
        JsonElement domainsEl = options.get("domains");
        if (domainsEl.isJsonArray()) {
            for (JsonElement el : domainsEl.getAsJsonArray()) {
                if (el != null && el.isJsonPrimitive()) {
                    String d = el.getAsString().trim().toLowerCase(Locale.ROOT);
                    if ("*".equals(d)) {
                        return new ArrayList<>();
                    }
                    if (!d.isEmpty()) {
                        domains.add(d);
                    }
                }
            }
        } else if (domainsEl.isJsonPrimitive()) {
            String one = domainsEl.getAsString().trim().toLowerCase(Locale.ROOT);
            if ("*".equals(one)) {
                return new ArrayList<>();
            }
            if (!one.isEmpty()) {
                domains.add(one);
            }
        }
        return domains;
    }

    private String sanitizeExportName(String raw) {
        String safe = (raw == null ? "" : raw).trim();
        if (safe.isEmpty()) {
            safe = "vdb-export";
        }
        return safe.replaceAll("[^a-zA-Z0-9._-]+", "_");
    }

    private void copyDirectory(Path source, Path target) throws IOException {
        if (!Files.exists(source)) {
            return;
        }
        Files.walk(source).forEach(path -> {
            try {
                Path relative = source.relativize(path);
                Path destination = target.resolve(relative.toString());
                if (Files.isDirectory(path)) {
                    Files.createDirectories(destination);
                } else {
                    if (BsonStorage.isBsonDocument(path)) {
                        String fileName = destination.getFileName().toString();
                        String exportName = fileName.substring(0, fileName.length() - BsonStorage.DOCUMENT_EXTENSION.length()) + ".json";
                        Path exportPath = destination.resolveSibling(exportName);
                        Files.createDirectories(exportPath.getParent());
                        Files.writeString(exportPath, BsonStorage.toJson(BsonStorage.readValue(path)), StandardCharsets.UTF_8);
                        return;
                    }
                    if (BsonStorage.isBsonLog(path)) {
                        String fileName = destination.getFileName().toString();
                        String exportName = fileName.substring(0, fileName.length() - BsonStorage.LOG_EXTENSION.length()) + ".jsonl";
                        Path exportPath = destination.resolveSibling(exportName);
                        Files.createDirectories(exportPath.getParent());
                        StringBuilder buffer = new StringBuilder();
                        for (Map<String, Object> row : BsonStorage.readLogEntries(path)) {
                            if (buffer.length() > 0) {
                                buffer.append(System.lineSeparator());
                            }
                            buffer.append(BsonStorage.toJson(row));
                        }
                        if (buffer.length() > 0) {
                            buffer.append(System.lineSeparator());
                        }
                        Files.writeString(exportPath, buffer.toString(), StandardCharsets.UTF_8);
                        return;
                    }
                    Files.createDirectories(destination.getParent());
                    Files.copy(path, destination, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.COPY_ATTRIBUTES);
                }
            } catch (IOException e) {
                throw new RuntimeException("Failed copying " + path + ": " + e.getMessage(), e);
            }
        });
    }

    private void zipDirectory(Path sourceDir, Path zipPath) throws IOException {
        try (OutputStream os = Files.newOutputStream(zipPath);
             ZipOutputStream zos = new ZipOutputStream(os)) {
            Files.walk(sourceDir)
                    .filter(path -> !Files.isDirectory(path))
                    .forEach(path -> {
                        Path relative = sourceDir.relativize(path);
                        ZipEntry entry = new ZipEntry(relative.toString().replace("\\", "/"));
                        try {
                            zos.putNextEntry(entry);
                            try (InputStream is = Files.newInputStream(path)) {
                                is.transferTo(zos);
                            }
                            zos.closeEntry();
                        } catch (IOException e) {
                            throw new RuntimeException("Failed to zip " + path + ": " + e.getMessage(), e);
                        }
                    });
        }
    }

    private String errorResponse(String message) {
        Map<String, Object> response = new HashMap<>();
        response.put("status", "error");
        response.put("message", message);
        return gson.toJson(response);
    }

    private String warningResponse(String message) {
        Map<String, Object> response = new HashMap<>();
        response.put("status", "warning");
        response.put("message", message);
        return gson.toJson(response);
    }

    public void beginTransaction() {
        VDB.beginTransaction(currentDomain, currentDB);
    }

    public void commitTransaction() {
        VDB.commitTransaction(currentDomain, currentDB);
    }

    public void abortTransaction() {
        VDB.abortTransaction(currentDomain, currentDB);
    }
}
