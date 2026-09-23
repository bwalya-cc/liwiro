package verun.vdb;

import java.util.*;
import com.google.gson.*;
import static verun.vdb.VDBCommand.Kind;

/** Parser for VDB's native Versa-family command syntax. */
public final class VDBCommandLanguage {
    private enum TokenType { WORD, STRING, NUMBER, SYMBOL, EOF }
    private static final class Token {
        final TokenType type; final String text; final int offset;
        Token(TokenType type, String text, int offset) { this.type = type; this.text = text; this.offset = offset; }
    }
    private final String source;
    private final List<Token> tokens;
    private int position;
    private Set<String> expressionStops = Collections.emptySet();

    private VDBCommandLanguage(String source) { this.source = source; this.tokens = lex(source); }

    /** Deprecated inspection adapter; execution uses {@link #parseBatch(String)}. */
    public static JsonObject parse(String source) {
        VDBCommand.Batch batch = parseBatch(source);
        if (batch.commands.size() != 1) {
            JsonObject result = new JsonObject(); JsonArray values = new JsonArray();
            for (VDBCommand command : batch.commands) values.add(summary(command));
            result.add("commands", values); return result;
        }
        return summary(batch.commands.get(0));
    }

    public static VDBCommand.Batch parseBatch(String source) {
        String text = source == null ? "" : source.trim();
        if (text.isEmpty()) throw error("EMPTY_COMMAND", "Enter a VDB command. Type help; for examples.");
        if (text.startsWith("{") || text.startsWith("["))
            throw error("VDB_LEGACY_JSON_COMMAND", "JSON command envelopes have been removed. Use a Versa command such as: read collection users;");
        VDBCommandLanguage parser = new VDBCommandLanguage(text);
        List<VDBCommand> commands = new ArrayList<>();
        while (!parser.atEnd()) {
            if (parser.accept(";")) continue;
            commands.add(parser.statement());
            if (!parser.accept(";") && !parser.atEnd() && !parser.previousWasBlock()
                    && !isCommandVerb(parser.peek().text))
                parser.fail("EXPECTED_SEMICOLON", "Expected ';' after VDB command");
        }
        return new VDBCommand.Batch(commands);
    }

    private static JsonObject summary(VDBCommand command) {
        JsonObject result = new JsonObject(); result.addProperty("command", command.kind.name().toLowerCase(Locale.ROOT));
        result.addProperty("action", legacyAction(command.kind));
        if (command.kind == Kind.READ_DOMAINS || command.kind == Kind.READ_DATABASES || command.kind == Kind.READ_COLLECTIONS || command.kind == Kind.READ_USERS || command.kind == Kind.READ_ROLES) result.addProperty("resource", command.kind.name().replace("READ_", "").toLowerCase(Locale.ROOT));
        if (command.target != null) result.addProperty("target", command.target);
        if (command.predicate instanceof VDBCommand.Binary) {
            VDBCommand.Binary predicate = (VDBCommand.Binary) command.predicate;
            if (predicate.left instanceof VDBCommand.Field && predicate.right instanceof VDBCommand.Literal) {
                JsonObject where = new JsonObject(); where.addProperty(((VDBCommand.Field) predicate.left).path, String.valueOf(((VDBCommand.Literal) predicate.right).value)); result.add("where", where);
            }
        }
        return result;
    }
    private static String legacyAction(Kind kind) {
        switch (kind) {
            case READ_COLLECTION: case READ_ONE: return "find";
            case CREATE_DOCUMENT: return "insert";
            case CREATE_COLLECTION: return "create_collection";
            case DROP_COLLECTION: return "drop_collection";
            case CREATE_USER: case CREATE_ROLE: case READ_USERS: case READ_ROLES: return "tumi";
            default: return kind.name().toLowerCase(Locale.ROOT);
        }
    }

    private boolean previousWasBlock() { return position > 0 && "}".equals(tokens.get(position - 1).text); }
    private static boolean isCommandVerb(String token) { return Arrays.asList("context", "whoami", "echo", "help", "read", "find", "count", "create", "insert", "update", "delete", "drop", "use", "describe", "status", "suspend", "resume", "activate", "grant", "revoke", "transfer", "run", "begin", "commit", "rollback", "abort", "transaction", "rebuild", "export", "aggregate").contains(token.toLowerCase(Locale.ROOT)); }

    private VDBCommand statement() {
        String verb = word("command verb").toLowerCase(Locale.ROOT);
        switch (verb) {
            case "context": return simple(Kind.CONTEXT);
            case "whoami": return simple(Kind.WHOAMI);
            case "clear": case "cls": return simple(Kind.CLEAR);
            case "license": case "licence": return simple(Kind.LICENSE);
            case "exit": case "quit": return simple(Kind.EXIT);
            case "echo": accept("value"); return command(Kind.ECHO, null, literalValue(), null);
            case "help": return command(Kind.HELP, readHelpTopic(), null, null);
            case "read": return read();
            case "find": return readCollection(false, name());
            case "count": return count();
            case "create": return create();
            case "insert":
                if (!accept("into")) fail("VDB_LEGACY_INSERT", "Legacy insert syntax is no longer accepted. Use: insert into users = { ... };");
                return createDocument();
            case "update": return update();
            case "delete": return delete();
            case "drop": return drop();
            case "use": return use();
            case "describe": expect("collection"); return command(Kind.DESCRIBE_COLLECTION, name(), null, null);
            case "status": expect("domain"); return command(Kind.STATUS_DOMAIN, name(), null, null);
            case "suspend": expect("domain"); return command(Kind.SUSPEND_DOMAIN, name(), null, null);
            case "resume": case "activate": expect("domain"); return command(Kind.RESUME_DOMAIN, name(), null, null);
            case "grant": return permission(true);
            case "revoke": return permission(false);
            case "transfer": return transfer();
            case "run": return runScript();
            case "begin": expect("transaction"); return simple(Kind.BEGIN_TRANSACTION);
            case "commit": expect("transaction"); return simple(Kind.COMMIT_TRANSACTION);
            case "rollback": case "abort": expect("transaction"); return simple(Kind.ROLLBACK_TRANSACTION);
            case "transaction": return transactionBlock();
            case "rebuild": return rebuild();
            case "export": return export();
            case "aggregate": return aggregate();
            default: fail("UNKNOWN_COMMAND", "Unknown VDB command '" + verb + "'. Type help; for examples."); return null;
        }
    }

    private VDBCommand read() {
        if (accept("one")) { accept("from"); return readCollection(true, name()); }
        if (accept("collection")) return readCollection(false, name());
        if (accept("domain")) return command(Kind.STATUS_DOMAIN, name(), null, null);
        if (accept("model")) return command(Kind.DROP_MODEL, name(), null, null, map("read", true));
        if (accept("script")) return command(Kind.CREATE_SCRIPT, name(), null, null, map("read", true));
        if (accept("user")) return command(Kind.READ_USERS, name(), null, null, map("single", true));
        if (accept("role")) return command(Kind.READ_ROLES, name(), null, null, map("single", true));
        if (accept("indexes")) { expect("on"); return command(Kind.READ_INDEXES, name(), null, null); }
        if (accept("all")) { expect("domains"); return simple(Kind.READ_ALL_DOMAINS); }
        if (accept("owned")) { expect("domains"); return command(Kind.READ_OWNED_DOMAINS, optionalFor(), null, null); }
        String resource = word("resource").toLowerCase(Locale.ROOT);
        switch (resource) {
            case "domains":
                if (accept("with")) { expect("owners"); return simple(Kind.READ_DOMAINS_WITH_OWNERS); }
                return simple(Kind.READ_DOMAINS);
            case "databases": case "dbs": return simple(Kind.READ_DATABASES);
            case "collections": return simple(Kind.READ_COLLECTIONS);
            case "models": return simple(Kind.READ_MODELS);
            case "scripts": return simple(Kind.READ_SCRIPTS);
            case "users": return simple(Kind.READ_USERS);
            case "roles": return simple(Kind.READ_ROLES);
            case "permissions": return readPermissions();
            default: fail("UNKNOWN_READ_TARGET", "Unknown read target '" + resource + "'. Use read collection " + resource + "; for documents."); return null;
        }
    }

    private VDBCommand readPermissions() {
        String user = optionalFor(); Map<String, Object> options = new LinkedHashMap<>();
        if (user != null) options.put("user", user);
        if (accept("on")) options.put("scope", name());
        return command(Kind.READ_PERMISSIONS, null, null, null, options);
    }

    private VDBCommand readCollection(boolean one, String collection) {
        VDBCommand.Expression where = null; List<String> select = new ArrayList<>();
        List<VDBCommand.Order> order = new ArrayList<>(); int offset = 0, limit = one ? 1 : 100;
        while (!boundary()) {
            if (isCommandVerb(peek().text)) break;
            if (accept("where")) {
                rejectLegacyObject("query expression", "where active == true");
                where = expressionUntil("select", "order", "offset", "limit", ";", "}");
            } else if (accept("select")) select = fieldList();
            else if (accept("order")) { expect("by"); order = orderList(); }
            else if (accept("offset")) offset = positiveOrZero("offset");
            else if (accept("limit")) limit = positive("limit");
            else if (peek("projection")) fail("VDB_LEGACY_PROJECTION", "Legacy projection syntax is not accepted. Use: select [name, email]");
            else fail("INVALID_QUERY_CLAUSE", "Expected where, select, order by, offset, or limit");
        }
        return new VDBCommand(one ? Kind.READ_ONE : Kind.READ_COLLECTION, collection, null, where,
                select, order, list(), map(), list(), offset, limit, false);
    }

    private VDBCommand count() {
        accept("collection"); String target = name(); VDBCommand.Expression predicate = null;
        if (accept("where")) predicate = expressionUntil(";", "}");
        return command(Kind.COUNT, target, null, predicate);
    }

    private VDBCommand create() {
        if (accept("in")) return createDocument();
        String resource = word("resource type").toLowerCase(Locale.ROOT);
        if (resource.equals("domain")) {
            String target = name(); Object definition = accept("=") ? literalValue() : null;
            return command(Kind.CREATE_DOMAIN, target, definition, null);
        }
        if (resource.equals("database") || resource.equals("db")) { String target = name(); if (accept("domain")) name(); return command(Kind.CREATE_DATABASE, target, null, null); }
        if (resource.equals("collection")) {
            String target = name(); Object schema = accept("=") ? schema() : null;
            return command(Kind.CREATE_COLLECTION, target, schema, null);
        }
        if (resource.equals("user")) return definition(Kind.CREATE_USER);
        if (resource.equals("role")) return definition(Kind.CREATE_ROLE);
        if (resource.equals("script")) return createScript();
        if (resource.equals("index")) return index(Kind.CREATE_INDEX);
        if (accept("data")) fail("VDB_LEGACY_INSERT", "Legacy document syntax is no longer accepted. Use: create in " + resource + " = { ... };");
        fail("UNKNOWN_CREATE_TARGET", "Unknown create target '" + resource + "'"); return null;
    }

    private VDBCommand definition(Kind kind) {
        String target = name(); Map<String, Object> values = new LinkedHashMap<>();
        if (accept("=")) {
            Object value = literalValue(); if (!(value instanceof Map)) fail("EXPECTED_DEFINITION", "Definition must be a Versa object literal"); values.putAll((Map<String, Object>) value);
        } else {
            while (!boundary()) { String key = name(); accept("="); values.put(key, literalValue()); }
        }
        Object value = values;
        if (!(value instanceof Map)) fail("EXPECTED_DEFINITION", "Definition must be a Versa object literal");
        return command(kind, target, value, null);
    }

    private VDBCommand createDocument() {
        String target = name(); expect("="); Object value = literalValue();
        if (!(value instanceof Map) && !(value instanceof List)) fail("EXPECTED_DOCUMENT", "Document value must be an object or list of objects");
        return command(Kind.CREATE_DOCUMENT, target, value, null);
    }

    private VDBCommand createScript() {
        String target = name(); Map<String, Object> options = new LinkedHashMap<>();
        if (accept("for")) options.put("service", name());
        expect("="); options.put("code", rawBlock());
        return command(Kind.CREATE_SCRIPT, target, null, null, options);
    }

    private VDBCommand update() {
        if (accept("collection")) return updateCollection(name());
        if (accept("user")) return updateDefinition(Kind.UPDATE_USER);
        if (accept("role")) return updateDefinition(Kind.UPDATE_ROLE);
        return updateCollection(name());
    }

    private VDBCommand updateDefinition(Kind kind) {
        String target = name();
        if (accept("=")) return command(kind, target, literalValue(), null);
        return new VDBCommand(kind, target, null, null, list(), list(), updateBlock(), map(), list(), 0, 0, false);
    }

    private VDBCommand updateCollection(String target) {
        VDBCommand.Expression predicate = null;
        if (accept("where")) predicate = expressionUntil("{");
        if (peek("set") || peek("inc") || peek("unset"))
            fail("VDB_LEGACY_UPDATE", "Legacy set/inc/unset syntax is no longer accepted. Use an update block: { field = value; };");
        List<VDBCommand.Update> updates = updateBlock();
        return new VDBCommand(Kind.UPDATE_COLLECTION, target, null, predicate, list(), list(), updates, map(), list(), 0, 0, false);
    }

    private List<VDBCommand.Update> updateBlock() {
        expect("{"); List<VDBCommand.Update> updates = new ArrayList<>();
        while (!accept("}")) {
            if (atEnd()) fail("UNCLOSED_UPDATE_BLOCK", "Expected '}' after update statements");
            if (accept(";")) continue;
            if (accept("unset")) updates.add(new VDBCommand.Update(name(), VDBCommand.Update.Operation.UNSET, null));
            else {
                String field = name(); String operator = take().text; VDBCommand.Update.Operation operation;
                if ("=".equals(operator)) operation = VDBCommand.Update.Operation.SET;
                else if ("+=".equals(operator)) operation = VDBCommand.Update.Operation.INCREMENT;
                else if ("-=".equals(operator)) operation = VDBCommand.Update.Operation.DECREMENT;
                else { fail("INVALID_UPDATE_OPERATOR", "Expected =, +=, -=, or unset in update block"); return null; }
                updates.add(new VDBCommand.Update(field, operation, expressionUntil(";", "}")));
            }
            accept(";");
        }
        if (updates.isEmpty()) fail("EMPTY_UPDATE", "Update block must contain at least one statement");
        return updates;
    }

    private VDBCommand delete() {
        if (accept("from")) {
            accept("collection"); String target = name();
            if (accept("all")) return new VDBCommand(Kind.DELETE_DOCUMENT, target, null, null, list(), list(), list(), map(), list(), 0, 0, true);
            if (!accept("where")) fail("DELETE_REQUIRES_WHERE_OR_ALL", "Document deletion requires 'where <expression>' or the explicit 'all' marker");
            return command(Kind.DELETE_DOCUMENT, target, null, expressionUntil(";", "}"));
        }
        if (accept("user")) return command(Kind.DELETE_USER, name(), null, null);
        if (accept("role")) return command(Kind.DELETE_ROLE, name(), null, null);
        if (accept("script")) return command(Kind.DELETE_SCRIPT, name(), null, null);
        fail("INVALID_DELETE_TARGET", "Use delete from <collection> where ...; or delete user/role/script <name>;"); return null;
    }

    private VDBCommand drop() {
        String resource = word("structural resource").toLowerCase(Locale.ROOT);
        switch (resource) {
            case "domain": return command(Kind.DROP_DOMAIN, name(), null, null);
            case "database": case "db": return command(Kind.DROP_DATABASE, name(), null, null);
            case "collection": return command(Kind.DROP_COLLECTION, name(), null, null);
            case "index": return index(Kind.DROP_INDEX);
            case "model": return command(Kind.DROP_MODEL, name(), null, null);
            default: fail("INVALID_DROP_TARGET", "drop destroys domain, database, collection, index, or model resources"); return null;
        }
    }

    private VDBCommand use() {
        if (accept("domain")) return command(Kind.USE_DOMAIN, name(), null, null);
        if (accept("database") || accept("db")) return command(Kind.USE_DATABASE, name(), null, null);
        String target = name(); return command(target.contains(".") ? Kind.USE_PATH : Kind.USE_DOMAIN, target, null, null);
    }

    private VDBCommand index(Kind kind) {
        String path = name(); Map<String, Object> options = new LinkedHashMap<>();
        while (accept("@")) options.put(word("index annotation").toLowerCase(Locale.ROOT), true);
        return command(kind, path, null, null, options);
    }

    private VDBCommand permission(boolean grant) {
        if (accept("role")) {
            String role = name(); expect(grant ? "to" : "from");
            return command(grant ? Kind.GRANT_ROLE : Kind.REVOKE_ROLE, name(), role, null);
        }
        if (grant && accept("ownership")) {
            String domain = name(); expect("to"); return command(Kind.GRANT_OWNERSHIP, name(), domain, null);
        }
        Object permissions = literalValue(); expect("on"); String scope = name(); expect(grant ? "to" : "from");
        return command(grant ? Kind.GRANT_PERMISSION : Kind.REVOKE_PERMISSION, name(), permissions, null, map("scope", scope));
    }

    private VDBCommand transfer() {
        expect("domain"); String domain = name(); expect("to"); String user = name();
        return command(Kind.TRANSFER_DOMAIN, user, domain, null, map("relinquish", accept("relinquish")));
    }

    private VDBCommand runScript() {
        expect("script"); String target = name(); Object params = null;
        if (accept("with")) params = literalValue();
        return command(Kind.RUN_SCRIPT, target, params, null);
    }

    private VDBCommand transactionBlock() {
        expect("{"); List<VDBCommand> statements = new ArrayList<>();
        while (!accept("}")) {
            if (atEnd()) fail("UNCLOSED_TRANSACTION", "Expected '}' after transaction statements");
            if (accept(";")) continue;
            statements.add(statement()); accept(";");
        }
        return new VDBCommand(Kind.TRANSACTION_BLOCK, null, null, null, list(), list(), list(), map(), statements, 0, 0, false);
    }

    private VDBCommand rebuild() {
        if (accept("indexes")) { expect("on"); return command(Kind.REBUILD_INDEXES, name(), null, null); }
        expect("index"); return command(Kind.REBUILD_INDEX, name(), null, null);
    }

    private VDBCommand export() {
        Map<String, Object> options = new LinkedHashMap<>(); boolean all = accept("all");
        String resource = word("domain or domains"); Object targets;
        if (all) targets = Collections.emptyList(); else targets = resource.equalsIgnoreCase("domains") ? literalValue() : name();
        expect("to"); options.put("to", stringValue("export directory"));
        if (accept("as")) options.put("as", stringValue("package name"));
        if (accept("format")) options.put("format", name());
        return new VDBCommand(Kind.EXPORT, resource, targets, null, list(), list(), list(), options, list(), 0, 0, all);
    }

    private VDBCommand aggregate() {
        accept("collection"); String target = name(); VDBCommand.Expression predicate = null; Object by = null;
        if (accept("where")) predicate = expressionUntil("by", "{");
        if (accept("by")) by = peek("[") ? literalValue() : name();
        String body = rawBlock();
        Map<String, Object> options = map("by", by, "body", body);
        if (accept("order")) { expect("by"); options.put("order", orderList()); }
        if (accept("limit")) options.put("limit", positive("limit"));
        return command(Kind.AGGREGATE, target, null, predicate, options);
    }

    private Map<String, VDBCommand.SchemaField> schema() {
        expect("{"); Map<String, VDBCommand.SchemaField> result = new LinkedHashMap<>();
        while (!accept("}")) {
            String field = name(); expect(":"); String type = word("field type"); boolean nullable = accept("?");
            Object defaultValue = null; if (accept("=")) defaultValue = literalValue();
            Set<String> annotations = new LinkedHashSet<>(); while (accept("@")) annotations.add(word("annotation").toLowerCase(Locale.ROOT));
            result.put(field, new VDBCommand.SchemaField(field, type, nullable, defaultValue, annotations, Collections.emptyMap()));
            if (!accept(",") && !peek("}")) fail("EXPECTED_SCHEMA_SEPARATOR", "Expected ',' or '}' in collection schema");
        }
        return result;
    }

    private VDBCommand.Expression expressionUntil(String... stops) {
        Set<String> prior = expressionStops; expressionStops = new HashSet<>();
        for (String stop : stops) expressionStops.add(stop.toLowerCase(Locale.ROOT));
        VDBCommand.Expression result = expression(0); expressionStops = prior; return result;
    }
    private VDBCommand.Expression expression(int minPrecedence) {
        VDBCommand.Expression left = unary();
        while (!atEnd() && !expressionStops.contains(peek().text.toLowerCase(Locale.ROOT))) {
            String operator = peek().text.toLowerCase(Locale.ROOT); int precedence = precedence(operator);
            if (precedence < minPrecedence) break;
            take(); VDBCommand.Expression right = expression(precedence + 1);
            if ("=".equals(operator)) operator = "==";
            left = "..".equals(operator) ? new VDBCommand.Range(left, right) : new VDBCommand.Binary(operator, left, right);
        }
        return left;
    }
    private VDBCommand.Expression unary() {
        if (peek("!") || peek("-")) { String operator = take().text; return new VDBCommand.Unary(operator, unary()); }
        if (accept("(")) { VDBCommand.Expression value = expression(0); expect(")"); return value; }
        if (peek("{") || peek("[")) return new VDBCommand.Literal(literalValue());
        Token token = take();
        if (token.type == TokenType.STRING || token.type == TokenType.NUMBER || isLiteralWord(token.text)) return new VDBCommand.Literal(tokenValue(token));
        if (token.type != TokenType.WORD) fail("INVALID_EXPRESSION", "Unexpected token '" + token.text + "' in expression");
        if (accept("(")) {
            List<VDBCommand.Expression> args = new ArrayList<>(); if (!peek(")")) do { args.add(expression(0)); } while (accept(","));
            expect(")"); return new VDBCommand.Call(token.text, args);
        }
        return new VDBCommand.Field(token.text);
    }
    private int precedence(String op) {
        if ("??".equals(op)) return 1; if ("||".equals(op)) return 2; if ("&&".equals(op)) return 3;
        if (Arrays.asList("==", "=", "!=", ">", "<", ">=", "<=", "in", "!in").contains(op)) return 4;
        if ("..".equals(op)) return 5; if ("+".equals(op) || "-".equals(op)) return 6;
        if ("*".equals(op) || "/".equals(op)) return 7; return -1;
    }

    private Object literalValue() {
        Token token = take();
        if ("{".equals(token.text)) {
            Map<String, Object> object = new LinkedHashMap<>();
            while (!accept("}")) {
                String key = name(); expect(":"); object.put(key, literalValue());
                if (!accept(",") && !accept(";") && !peek("}")) fail("EXPECTED_OBJECT_SEPARATOR", "Expected ',' or ';' or '}' in object literal");
            }
            return object;
        }
        if ("[".equals(token.text)) {
            List<Object> values = new ArrayList<>();
            while (!accept("]")) {
                values.add(literalValue());
                if (!accept(",") && !peek("]")) fail("EXPECTED_LIST_SEPARATOR", "Expected ',' or ']' in list literal");
            }
            return values;
        }
        if (token.type == TokenType.SYMBOL) fail("EXPECTED_VALUE", "Expected Versa literal");
        return tokenValue(token);
    }

    private Object tokenValue(Token token) {
        if (token.type == TokenType.STRING) return token.text;
        if (token.type == TokenType.NUMBER) {
            try { return token.text.matches(".*[.eE].*") ? Double.valueOf(token.text) : Integer.valueOf(token.text); }
            catch (NumberFormatException ignored) { return Long.valueOf(token.text); }
        }
        if ("true".equals(token.text)) return true; if ("false".equals(token.text)) return false; if ("null".equals(token.text)) return null;
        return token.text;
    }

    private List<String> fieldList() {
        expect("["); List<String> fields = new ArrayList<>(); if (!peek("]")) do { fields.add(name()); } while (accept(",")); expect("]"); return fields;
    }
    private List<VDBCommand.Order> orderList() {
        List<VDBCommand.Order> orders = new ArrayList<>();
        do { String field = name(); boolean asc = !accept("desc"); if (asc) accept("asc"); orders.add(new VDBCommand.Order(field, asc)); } while (accept(","));
        return orders;
    }
    private String rawBlock() {
        Token open = take(); if (!"{".equals(open.text)) fail("EXPECTED_BLOCK", "Expected '{' block");
        int depth = 1, start = open.offset + 1; Token last = open;
        while (depth > 0 && !atEnd()) { last = take(); if ("{".equals(last.text)) depth++; else if ("}".equals(last.text)) depth--; }
        if (depth != 0) fail("UNCLOSED_BLOCK", "Expected '}'"); return source.substring(start, last.offset).trim();
    }
    private String readHelpTopic() { if (boundary()) return null; StringBuilder result = new StringBuilder(); while (!boundary()) { if (result.length() > 0) result.append(' '); result.append(take().text); } return result.toString(); }
    private String optionalFor() { return accept("for") ? name() : null; }
    private String name() { Token token = take(); if (token.type != TokenType.WORD && token.type != TokenType.STRING) fail("EXPECTED_NAME", "Expected resource name"); return token.text; }
    private String stringValue(String what) { Token token = take(); if (token.type != TokenType.STRING) fail("EXPECTED_STRING", "Expected quoted " + what); return token.text; }
    private int positive(String field) { int value = integer(field); if (value <= 0) fail("INVALID_" + field.toUpperCase(Locale.ROOT), field + " must be positive"); return value; }
    private int positiveOrZero(String field) { int value = integer(field); if (value < 0) fail("INVALID_" + field.toUpperCase(Locale.ROOT), field + " cannot be negative"); return value; }
    private int integer(String field) { Token token = take(); try { return Integer.parseInt(token.text); } catch (Exception e) { fail("INVALID_" + field.toUpperCase(Locale.ROOT), field + " must be an integer"); return 0; } }
    private void rejectLegacyObject(String what, String replacement) { if (peek("{")) fail("VDB_LEGACY_JSON_QUERY", "JSON " + what + "s are no longer accepted. Use: " + replacement); }
    private boolean isLiteralWord(String value) { return Arrays.asList("true", "false", "null").contains(value); }
    private boolean boundary() { return atEnd() || peek(";") || peek("}"); }
    private boolean atEnd() { return peek().type == TokenType.EOF; }
    private Token peek() { return tokens.get(position); }
    private boolean peek(String value) { return peek().text.equalsIgnoreCase(value); }
    private Token take() { if (atEnd()) fail("UNEXPECTED_END", "Unexpected end of command"); return tokens.get(position++); }
    private boolean accept(String value) { if (peek(value)) { position++; return true; } return false; }
    private void expect(String value) { if (!accept(value)) fail("EXPECTED_TOKEN", "Expected '" + value + "' but found '" + peek().text + "'"); }
    private String word(String what) { Token token = take(); if (token.type != TokenType.WORD) fail("EXPECTED_WORD", "Expected " + what); return token.text; }
    private void fail(String code, String message) { Token token = peek(); throw error(code, message + " at offset " + token.offset); }
    private static IllegalArgumentException error(String code, String message) { return new IllegalArgumentException(code + ": " + message); }
    private VDBCommand simple(Kind kind) { return command(kind, null, null, null); }
    private VDBCommand command(Kind kind, String target, Object value, VDBCommand.Expression predicate) { return command(kind, target, value, predicate, map()); }
    private VDBCommand command(Kind kind, String target, Object value, VDBCommand.Expression predicate, Map<String, Object> options) { return new VDBCommand(kind, target, value, predicate, list(), list(), list(), options, list(), 0, 0, false); }
    private static <T> List<T> list() { return new ArrayList<>(); }
    private static Map<String, Object> map(Object... entries) { Map<String, Object> result = new LinkedHashMap<>(); for (int i = 0; i + 1 < entries.length; i += 2) result.put(String.valueOf(entries[i]), entries[i + 1]); return result; }

    private static List<Token> lex(String source) {
        List<Token> out = new ArrayList<>(); int i = 0;
        while (i < source.length()) {
            char c = source.charAt(i); if (Character.isWhitespace(c)) { i++; continue; } int start = i;
            if (c == '"' || c == '\'') {
                char quote = c; StringBuilder value = new StringBuilder(); i++; boolean closed = false;
                while (i < source.length()) { char next = source.charAt(i++); if (next == quote) { closed = true; break; } if (next == '\\' && i < source.length()) { char escaped = source.charAt(i++); if (escaped == 'n') value.append('\n'); else if (escaped == 't') value.append('\t'); else value.append(escaped); } else value.append(next); }
                if (!closed) throw error("UNCLOSED_STRING", "Unclosed string at offset " + start); out.add(new Token(TokenType.STRING, value.toString(), start)); continue;
            }
            if (Character.isDigit(c) || (c == '-' && i + 1 < source.length() && Character.isDigit(source.charAt(i + 1)))) {
                i++; while (i < source.length() && (Character.isDigit(source.charAt(i)) || ".eE+-".indexOf(source.charAt(i)) >= 0)) { if (source.startsWith("..", i)) break; i++; }
                out.add(new Token(TokenType.NUMBER, source.substring(start, i), start)); continue;
            }
            if (Character.isLetter(c) || c == '_' || c == '$') {
                i++; while (i < source.length() && (Character.isLetterOrDigit(source.charAt(i)) || "_.$-".indexOf(source.charAt(i)) >= 0)) i++;
                out.add(new Token(TokenType.WORD, source.substring(start, i), start)); continue;
            }
            if (source.startsWith("!in", i)) { out.add(new Token(TokenType.SYMBOL, "!in", start)); i += 3; continue; }
            String two = i + 1 < source.length() ? source.substring(i, i + 2) : "";
            if (Arrays.asList("==", "!=", ">=", "<=", "&&", "||", "??", "..", "+=", "-=").contains(two)) { out.add(new Token(TokenType.SYMBOL, two, start)); i += 2; continue; }
            // A script body is captured as a raw block by the command parser,
            // but it is still lexed to find matching braces. Versa scripts
            // legitimately contain member-access chains after calls,
            // e.g. str(value).trim() and datetime.now().isoformat(). Accept
            // a standalone dot here so those raw script bodies can be stored
            // by generated LAPIS services instead of failing with
            // INVALID_CHARACTER at the dot.
            if ("{}[](),;:=@?!<>+-*/.".indexOf(c) >= 0) { out.add(new Token(TokenType.SYMBOL, String.valueOf(c), start)); i++; continue; }
            throw error("INVALID_CHARACTER", "Invalid character '" + c + "' at offset " + start);
        }
        out.add(new Token(TokenType.EOF, "<end>", source.length())); return out;
    }
}
