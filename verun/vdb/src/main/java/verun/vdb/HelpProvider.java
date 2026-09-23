// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonSyntaxException;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Loads and serves the bounded, shared console/server VDB help catalog. */
public class HelpProvider {
    static final int DEFAULT_PAGE_SIZE = 3;
    static final int MAX_PAGE_SIZE = 5;

    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create();
    private static final Pattern INDEX_PAGE = Pattern.compile("(?i)^(?:page\\s+)?(\\d+)$");
    private static final Pattern TRAILING_PAGE = Pattern.compile("(?i)^(.+?)\\s+(?:page\\s+)?(\\d+)$");
    private static JsonObject CACHED_HELP;

    private static final class ParsedRequest {
        private final String topic;
        private final int page;

        private ParsedRequest(String topic, int page) {
            this.topic = topic;
            this.page = page;
        }
    }

    private static final class CommandMatch {
        private final String section;
        private final JsonObject command;

        private CommandMatch(String section, JsonObject command) {
            this.section = section;
            this.command = command;
        }
    }

    private static String normalizeKey(String key) {
        return key == null ? "" : key.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]", "");
    }

    private static boolean isSecurityTopic(String key) {
        String norm = normalizeKey(key);
        return "security".equals(norm) || "tumi".equals(norm);
    }

    private static boolean canSeeSecurity(User user, String domain) {
        if (user == null) {
            return true;
        }
        return user.isSuperAdmin() || (domain != null && user.ownsDomain(domain));
    }

    private static JsonElement deepCopy(JsonElement element) {
        return GSON.fromJson(GSON.toJson(element), JsonElement.class);
    }

    private static synchronized JsonObject loadHelpRoot() throws IOException {
        if (CACHED_HELP != null) {
            return CACHED_HELP;
        }
        try (InputStream helpStream = HelpProvider.class.getClassLoader().getResourceAsStream("help.json")) {
            if (helpStream == null) {
                throw new IOException("help.json not found in resources");
            }
            StringBuilder sb = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(helpStream, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    sb.append(line).append('\n');
                }
            }
            CACHED_HELP = GSON.fromJson(sb.toString(), JsonObject.class);
            return CACHED_HELP;
        }
    }

    private static JsonObject filterTumiSection(JsonObject source, User user, String domain) {
        if (source == null) {
            return new JsonObject();
        }
        if (user == null || user.isSuperAdmin()) {
            return deepCopy(source).getAsJsonObject();
        }

        JsonObject out = new JsonObject();
        boolean domainOwner = domain != null && user.ownsDomain(domain);
        for (Map.Entry<String, JsonElement> entry : source.entrySet()) {
            if (!"commands".equals(normalizeKey(entry.getKey())) || !entry.getValue().isJsonArray()) {
                out.add(entry.getKey(), deepCopy(entry.getValue()));
                continue;
            }
            JsonArray commands = new JsonArray();
            if (domainOwner) {
                for (JsonElement element : entry.getValue().getAsJsonArray()) {
                    if (!element.isJsonObject()) {
                        continue;
                    }
                    JsonObject command = element.getAsJsonObject();
                    String access = command.has("access") ? command.get("access").getAsString() : "domain_owner";
                    if (!"super_admin".equalsIgnoreCase(access)) {
                        commands.add(deepCopy(command));
                    }
                }
            }
            out.add(entry.getKey(), commands);
        }
        if (domainOwner) {
            out.addProperty("visibility_note", "Commands limited to operations available to an owner of the active domain.");
        }
        return out;
    }

    private static JsonObject filterPayloadByRbac(JsonObject payload, User user, String domain) {
        JsonObject out = new JsonObject();
        if (payload == null) {
            return out;
        }
        boolean allowSecurity = canSeeSecurity(user, domain);
        for (Map.Entry<String, JsonElement> entry : payload.entrySet()) {
            String key = entry.getKey();
            JsonElement value = entry.getValue();
            if (isSecurityTopic(key) && !allowSecurity) {
                continue;
            }
            if ("tumi".equals(normalizeKey(key)) && value.isJsonObject()) {
                out.add(key, filterTumiSection(value.getAsJsonObject(), user, domain));
            } else {
                out.add(key, deepCopy(value));
            }
        }
        return out;
    }

    private static ParsedRequest parseRequest(String rawTopic, Integer explicitPage) {
        String topic = rawTopic == null ? "" : rawTopic.trim();
        int page = explicitPage == null ? 1 : explicitPage;
        if (explicitPage == null && !topic.isEmpty()) {
            Matcher index = INDEX_PAGE.matcher(topic);
            if (index.matches()) {
                return new ParsedRequest("", Integer.parseInt(index.group(1)));
            }
            Matcher trailing = TRAILING_PAGE.matcher(topic);
            if (trailing.matches()) {
                topic = trailing.group(1).trim();
                page = Integer.parseInt(trailing.group(2));
            }
        }
        return new ParsedRequest(topic, page);
    }

    private static JsonArray commandsOf(JsonObject section) {
        if (section != null && section.has("commands") && section.get("commands").isJsonArray()) {
            return section.getAsJsonArray("commands");
        }
        return new JsonArray();
    }

    private static String sectionSummary(JsonObject section) {
        return section != null && section.has("summary") ? section.get("summary").getAsString() : "";
    }

    private static String commandName(JsonObject command) {
        return command.has("name") ? command.get("name").getAsString() : "command";
    }

    private static boolean commandMatches(JsonObject command, String query) {
        String normalized = normalizeKey(query);
        for (String field : new String[]{"name", "action", "operation"}) {
            if (command.has(field) && command.get(field).isJsonPrimitive()
                    && normalizeKey(command.get(field).getAsString()).equals(normalized)) {
                return true;
            }
        }
        if (command.has("aliases") && command.get("aliases").isJsonArray()) {
            for (JsonElement alias : command.getAsJsonArray("aliases")) {
                if (alias.isJsonPrimitive() && normalizeKey(alias.getAsString()).equals(normalized)) {
                    return true;
                }
            }
        }
        return false;
    }

    private static Map.Entry<String, JsonElement> findSection(JsonObject payload, String requested) {
        String normalized = normalizeKey(requested);
        for (Map.Entry<String, JsonElement> entry : payload.entrySet()) {
            if (normalizeKey(entry.getKey()).equals(normalized) && entry.getValue().isJsonObject()) {
                return entry;
            }
        }
        return null;
    }

    private static List<CommandMatch> allCommands(JsonObject payload) {
        List<CommandMatch> out = new ArrayList<>();
        for (Map.Entry<String, JsonElement> sectionEntry : payload.entrySet()) {
            if (!sectionEntry.getValue().isJsonObject()) {
                continue;
            }
            for (JsonElement element : commandsOf(sectionEntry.getValue().getAsJsonObject())) {
                if (element.isJsonObject()) {
                    out.add(new CommandMatch(sectionEntry.getKey(), element.getAsJsonObject()));
                }
            }
        }
        return out;
    }

    private static List<CommandMatch> findCommands(JsonObject payload, String requested) {
        List<CommandMatch> matches = new ArrayList<>();
        for (CommandMatch candidate : allCommands(payload)) {
            if (commandMatches(candidate.command, requested)) {
                matches.add(candidate);
            }
        }
        return matches;
    }

    private static JsonObject pageError(String topic, int page, int totalPages) {
        JsonObject error = new JsonObject();
        error.addProperty("status", "error");
        error.addProperty("message", "Help page " + page + " is out of range for " + topic);
        error.addProperty("requested_page", page);
        error.addProperty("total_pages", totalPages);
        error.addProperty("hint", totalPages == 1 ? "Use page 1." : "Choose a page from 1 to " + totalPages + ".");
        return error;
    }

    private static int totalPages(int totalItems, int pageSize) {
        return Math.max(1, (totalItems + pageSize - 1) / pageSize);
    }

    private static void addPageMetadata(JsonObject out, int page, int pageSize, int totalItems) {
        out.addProperty("page", page);
        out.addProperty("page_size", pageSize);
        out.addProperty("total_items", totalItems);
        out.addProperty("total_pages", totalPages(totalItems, pageSize));
    }

    private static String consolePageCommand(String topic, int page) {
        return topic == null || topic.isEmpty() ? "help " + page : "help " + topic + " " + page;
    }

    private static String serverPagePath(String topic, int page, int pageSize) {
        StringBuilder path = new StringBuilder("/help?");
        if (topic != null && !topic.isEmpty()) {
            path.append("topic=").append(URLEncoder.encode(topic, StandardCharsets.UTF_8)).append('&');
        }
        path.append("page=").append(page).append("&page_size=").append(pageSize);
        return path.toString();
    }

    private static void addNavigation(JsonObject out, String topic, int page, int pageSize, int totalItems) {
        int pages = totalPages(totalItems, pageSize);
        JsonObject navigation = new JsonObject();
        navigation.addProperty("index", "help");
        if (page > 1) {
            navigation.addProperty("previous", consolePageCommand(topic, page - 1));
            navigation.addProperty("server_previous", serverPagePath(topic, page - 1, pageSize));
        }
        if (page < pages) {
            navigation.addProperty("next", consolePageCommand(topic, page + 1));
            navigation.addProperty("server_next", serverPagePath(topic, page + 1, pageSize));
        }
        out.add("navigation", navigation);
    }

    private static JsonObject renderIndex(JsonObject payload, int page, int pageSize) {
        List<Map.Entry<String, JsonElement>> sections = new ArrayList<>(payload.entrySet());
        int pages = totalPages(sections.size(), pageSize);
        if (page <= 0 || page > pages) {
            return pageError("the topic index", page, pages);
        }
        JsonObject out = new JsonObject();
        out.addProperty("mode", "index");
        JsonArray usage = new JsonArray();
        usage.add("help [page]");
        usage.add("help <topic> [page]");
        usage.add("help <command>");
        usage.add("help all [page]");
        usage.add("GET /help?topic=<topic>&page=<page>&page_size=<1-5>");
        out.add("usage", usage);
        addPageMetadata(out, page, pageSize, sections.size());
        JsonArray topics = new JsonArray();
        int from = (page - 1) * pageSize;
        int to = Math.min(sections.size(), from + pageSize);
        for (int i = from; i < to; i++) {
            Map.Entry<String, JsonElement> entry = sections.get(i);
            JsonObject section = entry.getValue().getAsJsonObject();
            JsonObject summary = new JsonObject();
            summary.addProperty("topic", entry.getKey());
            summary.addProperty("summary", sectionSummary(section));
            summary.addProperty("commands", commandsOf(section).size());
            summary.addProperty("open", "help " + entry.getKey());
            topics.add(summary);
        }
        out.add("topics", topics);
        addNavigation(out, "", page, pageSize, sections.size());
        return out;
    }

    private static JsonObject renderSection(String sectionName, JsonObject section, int page, int pageSize) {
        JsonArray commands = commandsOf(section);
        int pages = totalPages(commands.size(), pageSize);
        if (page <= 0 || page > pages) {
            return pageError(sectionName, page, pages);
        }
        JsonObject out = new JsonObject();
        out.addProperty("mode", "section");
        out.addProperty("topic", sectionName);
        out.addProperty("summary", sectionSummary(section));
        if (section.has("visibility_note")) {
            out.add("visibility_note", deepCopy(section.get("visibility_note")));
        }
        addPageMetadata(out, page, pageSize, commands.size());
        JsonArray pageCommands = new JsonArray();
        int from = (page - 1) * pageSize;
        int to = Math.min(commands.size(), from + pageSize);
        for (int i = from; i < to; i++) {
            pageCommands.add(publicCommand(commands.get(i)));
        }
        out.add("commands", pageCommands);
        out.addProperty("command_help", "help " + sectionName + ".<command>");
        addNavigation(out, sectionName, page, pageSize, commands.size());
        return out;
    }

    private static JsonObject renderCatalog(JsonObject payload, int page, int pageSize) {
        List<CommandMatch> commands = allCommands(payload);
        int pages = totalPages(commands.size(), pageSize);
        if (page <= 0 || page > pages) {
            return pageError("the command catalog", page, pages);
        }
        JsonObject out = new JsonObject();
        out.addProperty("mode", "catalog");
        out.addProperty("note", "The complete catalog is paginated; use next or request one command for focused help.");
        addPageMetadata(out, page, pageSize, commands.size());
        JsonArray items = new JsonArray();
        int from = (page - 1) * pageSize;
        int to = Math.min(commands.size(), from + pageSize);
        for (int i = from; i < to; i++) {
            CommandMatch match = commands.get(i);
            JsonObject item = publicCommand(match.command);
            item.addProperty("topic", match.section);
            item.addProperty("open", "help " + match.section + "." + commandName(match.command));
            items.add(item);
        }
        out.add("commands", items);
        addNavigation(out, "all", page, pageSize, commands.size());
        return out;
    }

    private static JsonObject renderCommand(CommandMatch match) {
        JsonObject out = new JsonObject();
        out.addProperty("mode", "command");
        out.addProperty("topic", match.section);
        out.add("command", publicCommand(match.command));
        JsonObject navigation = new JsonObject();
        navigation.addProperty("back", "help " + match.section);
        navigation.addProperty("server_back", "/help?topic="
                + URLEncoder.encode(match.section, StandardCharsets.UTF_8));
        out.add("navigation", navigation);
        return out;
    }

    private static JsonObject renderMatches(String requested, List<CommandMatch> matches, int page, int pageSize) {
        int pages = totalPages(matches.size(), pageSize);
        if (page <= 0 || page > pages) {
            return pageError("matches for " + requested, page, pages);
        }
        JsonObject out = new JsonObject();
        out.addProperty("mode", "matches");
        out.addProperty("query", requested);
        out.addProperty("hint", "Use the open value to select one command.");
        addPageMetadata(out, page, pageSize, matches.size());
        JsonArray items = new JsonArray();
        int from = (page - 1) * pageSize;
        int to = Math.min(matches.size(), from + pageSize);
        for (int i = from; i < to; i++) {
            CommandMatch match = matches.get(i);
            JsonObject item = new JsonObject();
            item.addProperty("topic", match.section);
            item.addProperty("name", commandName(match.command));
            item.addProperty("summary", match.command.has("summary")
                    ? match.command.get("summary").getAsString() : "");
            item.addProperty("open", "help " + match.section + "." + commandName(match.command));
            items.add(item);
        }
        out.add("matches", items);
        addNavigation(out, requested, page, pageSize, matches.size());
        return out;
    }

    /** Hide implementation action identifiers from the native language help surface. */
    private static JsonObject publicCommand(JsonElement source) {
        JsonObject command = deepCopy(source).getAsJsonObject();
        command.remove("action");
        command.remove("operation");
        command.remove("parameters");
        command.remove("console_examples");
        String syntax = canonicalSyntax(command);
        if (syntax != null) {
            command.addProperty("syntax", syntax);
            JsonArray examples = new JsonArray();
            for (String example : canonicalExamples(command.get("name").getAsString(), syntax)) examples.add(example);
            command.add("examples", examples);
        }
        return command;
    }

    private static List<String> canonicalExamples(String name, String syntax) {
        String key = name == null ? "" : name.toLowerCase(Locale.ROOT);
        List<String> examples = new ArrayList<>();
        switch (key) {
            case "list_users":
                examples.add("read users;");
                examples.add("read user alice;");
                break;
            case "tumi_list":
                examples.add("read users;");
                examples.add("read user alice;");
                examples.add("read roles;");
                examples.add("read permissions for alice on engineering.main;");
                examples.add("read owned domains;");
                break;
            case "tumi_read":
                examples.add("read user alice;");
                examples.add("read role REPORT_VIEWER;");
                break;
            case "tumi_create":
                examples.add("create user report_bot = { email: \"bot@example.com\", password: \"StrongPass1!\", role: application };");
                examples.add("create role REPORT_VIEWER = { scope: engineering.analytics; permissions: [read]; };");
                break;
            case "tumi_update":
                examples.add("update user alice { email = \"alice.new@example.com\"; };");
                examples.add("update role REPORT_VIEWER = { scope: engineering.analytics; permissions: [read, data_access]; };");
                break;
            case "tumi_delete":
                examples.add("delete user report_bot;");
                examples.add("delete role REPORT_VIEWER;");
                break;
            case "find": case "read":
                examples.add("read collection users;");
                examples.add("read one from users where email == \"alice@example.com\";");
                examples.add("read collection users where active == true select [name, email] order by name asc limit 20;");
                break;
            case "insert": case "create": case "create_document":
                examples.add("create in users = { name: \"Alice\", active: true };");
                examples.add("create in users = [{ name: \"Alice\" }, { name: \"Bob\" }];");
                break;
            case "update":
                examples.add("update collection users where email == \"alice@example.com\" { active = true; logins += 1; };");
                examples.add("update collection users where id == \"u-1\" { profile.city = \"Lusaka\"; unset temporary_code; };");
                break;
            case "delete":
                examples.add("delete from users where active == false;");
                examples.add("delete from users all;");
                break;
            case "create_collection":
                examples.add("create collection users;");
                examples.add("create collection products = { sku: string @required @unique, price: decimal @required, stock: int = 0 };");
                break;
            case "create_user":
                examples.add("create user report_bot = { email: \"bot@example.com\", password: \"StrongPass1!\", role: application };");
                examples.add("read user report_bot;");
                break;
            case "create_role":
                examples.add("create role REPORT_VIEWER = { scope: engineering.analytics; permissions: [read]; };");
                examples.add("grant role REPORT_VIEWER to report_bot;");
                break;
            default: examples.add(syntax);
        }
        return examples;
    }

    private static String canonicalSyntax(JsonObject command) {
        String name = command.has("name") ? command.get("name").getAsString().toLowerCase(Locale.ROOT) : "";
        switch (name) {
            case "echo": return "echo \"hello\";";
            case "context": return "context;";
            case "whoami": return "whoami;";
            case "list_users": return "read users;";
            case "batch": return "transaction { ... };";
            case "define_domain": return "create domain engineering;";
            case "define_domain_database": return "create domain engineering = { database: analytics };";
            case "use_domain": return "use domain engineering;";
            case "list_domains": return "read domains;";
            case "domains_and_owners": return "read domains with owners;";
            case "all_domains": return "read all domains;";
            case "drop_domain": return "drop domain engineering;";
            case "domain_status": return "status domain engineering;";
            case "domain_suspend": return "suspend domain engineering;";
            case "domain_resume": return "resume domain engineering;";
            case "define_database": return "create database analytics;";
            case "use_database": return "use database analytics;";
            case "list_databases": return "read databases;";
            case "drop_db": return "drop database analytics;";
            case "create_collection": return "create collection products = { sku: string @required };";
            case "list_collections": return "read collections;";
            case "drop_collection": return "drop collection events;";
            case "list_indexes": return "read indexes on users;";
            case "rebuild_indexes": return "rebuild indexes on users;";
            case "create_index": return "create index users.email @unique;";
            case "drop_index": return "drop index users.email;";
            case "list_models": return "read models;";
            case "model_get": return "read model users;";
            case "model_delete": return "drop model users;";
            case "insert": case "create_document": return "create in users = { name: \"Alice\" };";
            case "find": case "read": return "read collection users where active == true select [name, email] limit 20;";
            case "update": return "update collection users where email == \"alice@example.com\" { active = true; logins += 1; };";
            case "delete": return "delete from users where active == false;";
            case "aggregate": return "aggregate collection orders by customer_id { orders: count(); revenue: sum(total); };";
            case "script_create": return "create script greet = { print(\"hello\"); };";
            case "script_read": return "read script greet;";
            case "script_execute": return "run script greet with { username: \"Alice\" };";
            case "script_delete": return "delete script greet;";
            case "script_list": return "read scripts;";
            case "transaction_begin": return "begin transaction;";
            case "transaction_commit": return "commit transaction;";
            case "transaction_abort": return "rollback transaction;";
            case "export": return "export domain engineering to \"/tmp/vdb-exports\";";
            case "create_user": return "create user report_bot = { email: \"bot@example.com\", password: \"StrongPass1!\", role: application };";
            case "create_role": return "create role REPORT_VIEWER = { scope: engineering.analytics; permissions: [read]; };";
            case "read_role": return "read role REPORT_VIEWER;";
            case "update_role": return "update role REPORT_VIEWER = { scope: engineering.analytics; permissions: [read]; };";
            case "delete_user": return "delete user report_bot;";
            case "delete_role": return "delete role REPORT_VIEWER;";
            case "grant_permissions": return "grant [read, write] on engineering.analytics to alex;";
            case "revoke_permissions": return "revoke write on engineering.analytics from alex;";
            case "grant_role": return "grant role REPORT_VIEWER to alex;";
            case "revoke_role": return "revoke role REPORT_VIEWER from alex;";
            case "transfer_ownership": return "transfer domain engineering to alex;";
            case "list_roles": return "read roles;";
            case "list_permissions": return "read permissions;";
            case "list_owned_domains": return "read owned domains;";
            case "tumi_list": return "read users;";
            case "tumi_read": return "read user alice;";
            case "tumi_create": return "create user report_bot = { email: \"bot@example.com\", password: \"StrongPass1!\", role: application };";
            case "tumi_update": return "update user alice { email = \"alice.new@example.com\"; };";
            case "tumi_delete": return "delete user report_bot;";
            default: return command.has("examples") && command.get("examples").isJsonArray() && command.getAsJsonArray("examples").size() > 0 ? command.getAsJsonArray("examples").get(0).getAsString() : null;
        }
    }

    private static JsonObject unknownTopic(JsonObject payload, String requested, int pageSize) {
        JsonObject out = new JsonObject();
        out.addProperty("status", "error");
        out.addProperty("message", "Unknown help topic or command: " + requested);
        out.addProperty("hint", "Use 'help' for topics or 'help all' for the paginated command catalog.");
        JsonArray suggestions = new JsonArray();
        int count = 0;
        for (String section : payload.keySet()) {
            if (count++ >= pageSize) {
                break;
            }
            suggestions.add(section);
        }
        out.add("topic_suggestions", suggestions);
        return out;
    }

    public static String getHelpJson(
            String topic,
            Integer requestedPage,
            Integer requestedPageSize,
            User user,
            String domain,
            String db) {
        try {
            JsonObject root = loadHelpRoot();
            JsonObject payload = root.has("help") && root.get("help").isJsonObject()
                    ? root.getAsJsonObject("help") : root;
            JsonObject filteredPayload = filterPayloadByRbac(payload, user, domain);
            ParsedRequest request = parseRequest(topic, requestedPage);
            int pageSize = requestedPageSize == null
                    ? DEFAULT_PAGE_SIZE : Math.min(MAX_PAGE_SIZE, requestedPageSize);
            if (request.page <= 0 || pageSize <= 0) {
                return GSON.toJson(pageError("help", request.page, 1));
            }

            String requested = request.topic;
            String normalized = normalizeKey(requested);
            if (requested.isEmpty() || "index".equals(normalized) || "topics".equals(normalized)) {
                return GSON.toJson(renderIndex(filteredPayload, request.page, pageSize));
            }
            if ("all".equals(normalized) || "commands".equals(normalized)
                    || "catalog".equals(normalized) || "*".equals(requested)) {
                return GSON.toJson(renderCatalog(filteredPayload, request.page, pageSize));
            }

            Map.Entry<String, JsonElement> section = findSection(filteredPayload, requested);
            if (section != null) {
                return GSON.toJson(renderSection(
                        section.getKey(), section.getValue().getAsJsonObject(), request.page, pageSize));
            }

            String[] qualified = requested.split("[.:/]", 2);
            if (qualified.length == 2) {
                Map.Entry<String, JsonElement> requestedSection = findSection(filteredPayload, qualified[0]);
                if (requestedSection != null) {
                    List<CommandMatch> matches = new ArrayList<>();
                    for (JsonElement element : commandsOf(requestedSection.getValue().getAsJsonObject())) {
                        if (element.isJsonObject() && commandMatches(element.getAsJsonObject(), qualified[1])) {
                            matches.add(new CommandMatch(requestedSection.getKey(), element.getAsJsonObject()));
                        }
                    }
                    if (matches.size() == 1 && request.page == 1) {
                        return GSON.toJson(renderCommand(matches.get(0)));
                    }
                    if (!matches.isEmpty()) {
                        return GSON.toJson(renderMatches(requested, matches, request.page, pageSize));
                    }
                }
            }

            List<CommandMatch> matches = findCommands(filteredPayload, requested);
            if (matches.size() == 1 && request.page == 1) {
                return GSON.toJson(renderCommand(matches.get(0)));
            }
            if (!matches.isEmpty()) {
                return GSON.toJson(renderMatches(requested, matches, request.page, pageSize));
            }
            return GSON.toJson(unknownTopic(filteredPayload, requested, pageSize));
        } catch (JsonSyntaxException e) {
            JsonObject error = new JsonObject();
            error.addProperty("status", "error");
            error.addProperty("message", "help.json is invalid: " + e.getMessage());
            return GSON.toJson(error);
        } catch (Exception e) {
            JsonObject error = new JsonObject();
            error.addProperty("status", "error");
            error.addProperty("message", "Failed to load help: " + e.getMessage());
            return GSON.toJson(error);
        }
    }

    public static String getHelpJson(String topic, User user, String domain, String db) {
        return getHelpJson(topic, null, null, user, domain, db);
    }

    public static String getHelpJson(String topic) {
        return getHelpJson(topic, null, null, null, null, null);
    }

    /** Human-readable terminal/Markdown rendering of the help catalog. */
    public static String getHelpText(String topic, User user, String domain, String db) {
        JsonObject page = GSON.fromJson(getHelpJson(topic, null, null, user, domain, db), JsonObject.class);
        if (page == null) return "VDB Help\nUnable to load help.";
        if ("error".equalsIgnoreCase(page.has("status") ? page.get("status").getAsString() : ""))
            return "VDB Help\n\nError: " + page.get("message").getAsString();
        StringBuilder out = new StringBuilder("VDB Help\n========\n");
        String mode = page.has("mode") ? page.get("mode").getAsString() : "";
        if ("index".equals(mode)) {
            out.append("Topics (page ").append(page.get("page").getAsInt()).append('/').append(page.get("total_pages").getAsInt()).append(")\n\n");
            for (JsonElement item : page.getAsJsonArray("topics")) {
                JsonObject topicItem = item.getAsJsonObject();
                out.append("  ").append(topicItem.get("topic").getAsString()).append("  —  ")
                        .append(topicItem.get("summary").getAsString()).append("\n");
            }
            out.append("\nUse: help <topic>  |  help all. At an empty prompt, use ←/→ to move between help pages.\n");
        } else if ("section".equals(mode) || "catalog".equals(mode)) {
            if (page.has("topic")) out.append(page.get("topic").getAsString()).append("\n\n");
            JsonArray commands = page.getAsJsonArray("commands");
            for (JsonElement item : commands) {
                JsonObject command = item.getAsJsonObject();
                out.append("  ").append(command.get("name").getAsString()).append("\n");
                if (command.has("summary")) out.append("    ").append(command.get("summary").getAsString()).append("\n");
                if (command.has("syntax")) out.append("    Syntax: ").append(command.get("syntax").getAsString()).append("\n");
                if (command.has("examples") && command.get("examples").isJsonArray()) {
                    out.append("    Examples:\n");
                    for (JsonElement example : command.getAsJsonArray("examples")) out.append("      ").append(example.getAsString()).append("\n");
                }
                out.append('\n');
            }
            if (page.has("navigation")) {
                JsonObject nav = page.getAsJsonObject("navigation");
                out.append("Navigation: ");
                if (nav.has("previous")) out.append("previous (" ).append(nav.get("previous").getAsString()).append(") ");
                if (nav.has("next")) out.append("next (" ).append(nav.get("next").getAsString()).append(")");
                out.append('\n');
            }
        } else if ("command".equals(mode)) {
            JsonObject command = page.getAsJsonObject("command");
            out.append(command.get("name").getAsString()).append("\n\n");
            if (command.has("summary")) out.append(command.get("summary").getAsString()).append("\n\n");
            if (command.has("syntax")) out.append("Syntax\n------\n").append(command.get("syntax").getAsString()).append("\n");
            if (command.has("examples") && command.get("examples").isJsonArray()) {
                out.append("\nExamples\n--------\n");
                for (JsonElement example : command.getAsJsonArray("examples")) out.append(example.getAsString()).append('\n');
            }
        } else if ("matches".equals(mode)) {
            out.append("Matches for ").append(page.get("query").getAsString()).append("\n\n");
            for (JsonElement item : page.getAsJsonArray("matches")) {
                JsonObject match = item.getAsJsonObject(); out.append("  ").append(match.get("name").getAsString()).append(" — ").append(match.get("summary").getAsString()).append("\n");
            }
        }
        return out.toString();
    }
}
