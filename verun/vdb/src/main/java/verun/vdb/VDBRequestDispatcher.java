// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonSyntaxException;
import verun.common.JsonValueConverter;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Locale;

public class VDBRequestDispatcher {
    private final Gson gson = new Gson();
    private final SessionManager sessionManager;
    private final String interfaceName;
    private final boolean consoleLogsEnabled = VDBLogSettings.isConsoleLogsEnabled();
    private final boolean httpTrafficLogsEnabled = VDBLogSettings.isHttpTrafficLogsEnabled();

    public VDBRequestDispatcher() {
        this(new SessionManager(), "VDB_HTTP_SERVER");
    }

    public VDBRequestDispatcher(SessionManager sessionManager) {
        this(sessionManager, "VDB_HTTP_SERVER");
    }

    public VDBRequestDispatcher(SessionManager sessionManager, String interfaceName) {
        this.sessionManager = sessionManager == null ? new SessionManager() : sessionManager;
        this.interfaceName = interfaceName == null || interfaceName.trim().isEmpty()
                ? "VDB_HTTP_SERVER"
                : interfaceName.trim();
    }

    public VDBTransportResponse dispatch(VDBTransportRequest request) {
        String path = request == null ? "/" : request.getPath();
        if (path == null || path.trim().isEmpty()) {
            path = "/";
        }
        try {
            if ("/vdb".equals(path) || "/vql".equals(path)) {
                return handleVqlRequest(request);
            }
            if ("/auth".equals(path)) {
                return handleAuthRequest(request);
            }
            if ("/health".equals(path)) {
                return handleHealthRequest(request);
            }
            if ("/license".equals(path)) {
                return handleLicenseRequest(request);
            }
            if ("/help".equals(path) || path.startsWith("/help/")) {
                return handleHelpRequest(request);
            }
            return handleRootRequest(request);
        } catch (Exception e) {
            return jsonResponse(500, "{\"error\":\"Server error: " + safeJsonText(e.getMessage()) + "\"}");
        }
    }

    private VDBTransportResponse handleAuthRequest(VDBTransportRequest request) {
        if (!"POST".equalsIgnoreCase(request.getMethod())) {
            return jsonResponse(405, "{\"error\":\"Method not allowed\"}");
        }

        String authHeader = request.getHeader("Authorization");
        if (authHeader == null || !authHeader.startsWith("Basic ")) {
            return jsonResponse(401, "{\"error\":\"Unauthorized\"}");
        }

        String[] credentials;
        try {
            String base64Credentials = authHeader.substring(6);
            String decoded = new String(Base64.getDecoder().decode(base64Credentials), StandardCharsets.UTF_8);
            credentials = decoded.split(":", 2);
        } catch (Exception e) {
            return jsonResponse(401, "{\"error\":\"Invalid credentials\"}");
        }

        String username = User.normalizeUsername(credentials[0]);
        String password = credentials.length > 1 ? credentials[1] : "";

        User user = UserManager.getInstance().getUser(username);
        if (user == null || !user.authenticate(password)) {
            return jsonResponse(401, "{\"error\":\"Invalid credentials\"}");
        }

        String sessionId = sessionManager.createSession(user);
        Map<String, String> response = new HashMap<>();
        response.put("sessionId", sessionId);
        response.put("username", user.getUsername());
        response.put("role", user.getRole());
        return jsonResponse(200, gson.toJson(response));
    }

    private VDBTransportResponse handleHealthRequest(VDBTransportRequest request) {
        if (!"GET".equalsIgnoreCase(request.getMethod())) {
            return jsonResponse(405, "{\"error\":\"Method not allowed\"}");
        }
        return jsonResponse(200, gson.toJson(MitLicense.health(interfaceName)));
    }

    private VDBTransportResponse handleVqlRequest(VDBTransportRequest request) {
        String sessionId = request.getHeader("X-Session-Id");
        if (sessionId == null) {
            return jsonResponse(401, "{\"error\":\"Session ID required\"}");
        }

        SessionManager.Session session = sessionManager.validateSession(sessionId);
        if (session == null) {
            return jsonResponse(401, "{\"error\":\"Invalid or expired session\"}");
        }

        User authenticatedUser = session.getUser();
        VDB.setCurrentUser(authenticatedUser);
        VDB.setDomain(session.getCurrentDomain());
        VDB.useDatabase(session.getCurrentDB());

        VQLProcessor requestProcessor = new VQLProcessor(authenticatedUser, session);

        if (!"POST".equalsIgnoreCase(request.getMethod())) {
            return jsonResponse(400, "{\"error\":\"Only POST method supported\"}");
        }

        String requestBody = request.getBody() == null ? "" : request.getBody();
        logHttp("\n" + ColorUtil.colorize("Received native Versa VDB request:", ColorUtil.CYAN));
        logHttp(formatJson(requestBody));

        try {
            return processTypedCommands(requestProcessor, VDBCommandLanguage.parseBatch(requestBody));
        } catch (IllegalArgumentException error) {
            return jsonResponse(400, gson.toJson(Collections.singletonMap("error", error.getMessage())));
        }
    }

    private VDBTransportResponse processTypedCommands(VQLProcessor processor, VDBCommand.Batch batch) {
        String response = processor.execute(batch);
        logHttp(ColorUtil.colorize("Native Versa command response:", ColorUtil.MAGENTA));
        logHttp(formatJson(response));
        return jsonResponse(responseStatus(response), response);
    }

    private VDBTransportResponse processQueries(VQLProcessor requestProcessor, JsonArray queries) {
        List<Object> responses = new ArrayList<>();
        boolean success = true;
        int responseStatus = 200;

        for (JsonElement query : queries) {
            if (!query.isJsonObject()) {
                return jsonResponse(400, "{\"error\":\"Each parsed VDB batch statement must be an object\"}");
            }
            String response = requestProcessor.executeCommand(query.toString());
            try {
                responses.add(JsonValueConverter.fromJson(response));
            } catch (Exception e) {
                responses.add(response);
            }

            logHttp(ColorUtil.colorize("Query response:", ColorUtil.MAGENTA));
            logHttp(formatJson(response));

            int commandStatus = responseStatus(response);
            if (commandStatus >= 400) {
                success = false;
                responseStatus = commandStatus;
                break;
            }
        }

        Map<String, Object> finalResponseMap = new HashMap<>();
        finalResponseMap.put("status", success ? "success" : "error");
        finalResponseMap.put("responses", responses);
        String finalResponse = gson.toJson(finalResponseMap);

        logHttp(ColorUtil.colorize("Final response:", ColorUtil.GREEN));
        logHttp(formatJson(finalResponse));

        return jsonResponse(success ? 200 : responseStatus, finalResponse);
    }

    private VDBTransportResponse processSingleCommand(VQLProcessor requestProcessor, JsonObject command) {
        String response = requestProcessor.executeCommand(command.toString());

        logHttp(ColorUtil.colorize("Single command response:", ColorUtil.MAGENTA));
        logHttp(formatJson(response));

        int status = responseStatus(response);
        return jsonResponse(status, response);
    }

    private int responseStatus(String response) {
        int status = 200;
        try {
            JsonElement parsed = JsonParser.parseString(response);
            JsonObject body = parsed.isJsonObject() ? parsed.getAsJsonObject() : null;
            if (body != null && body.has("status") && "error".equalsIgnoreCase(body.get("status").getAsString())) {
                String message = body.has("message") && !body.get("message").isJsonNull() ? body.get("message").getAsString().toLowerCase(Locale.ROOT) : "";
                if (message.contains("auth") || message.contains("credential")) {
                    status = 401;
                } else if (message.contains("permission") || message.contains("forbidden")
                        || message.contains("access denied")) {
                    status = 403;
                } else {
                    status = 400;
                }
            }
        } catch (Exception ignored) { }
        return status;
    }

    private VDBTransportResponse handleHelpRequest(VDBTransportRequest request) {
        if (!"GET".equalsIgnoreCase(request.getMethod()) && !"POST".equalsIgnoreCase(request.getMethod())) {
            return jsonResponse(405, "{\"error\":\"Method not allowed\"}");
        }
        String topic = null;
        Integer page = null;
        Integer pageSize = null;
        String path = request.getPath();
        if (path != null && path.startsWith("/help/") && path.length() > 6) {
            topic = decodeHelpTopic(path.substring(6));
            if (topic == null) {
                return jsonResponse(400, "{\"error\":\"Invalid help topic encoding\"}");
            }
        }
        String query = request.getRawQuery();
        if (query != null && !query.isEmpty()) {
            for (String part : query.split("&")) {
                String[] kv = part.split("=", 2);
                if (kv.length != 2) {
                    continue;
                }
                if ("topic".equalsIgnoreCase(kv[0]) || "section".equalsIgnoreCase(kv[0])) {
                    String decodedTopic = decodeHelpTopic(kv[1]);
                    if (decodedTopic == null) {
                        return jsonResponse(400, "{\"error\":\"Invalid help topic encoding\"}");
                    }
                    topic = decodedTopic;
                } else if ("page".equalsIgnoreCase(kv[0])) {
                    page = parseHelpPositiveInteger(decodeHelpTopic(kv[1]));
                    if (page == null) {
                        return jsonResponse(400, "{\"error\":\"help page must be a positive integer\"}");
                    }
                } else if ("page_size".equalsIgnoreCase(kv[0]) || "pageSize".equalsIgnoreCase(kv[0])) {
                    pageSize = parseHelpPositiveInteger(decodeHelpTopic(kv[1]));
                    if (pageSize == null || pageSize > HelpProvider.MAX_PAGE_SIZE) {
                        return jsonResponse(400, "{\"error\":\"help page_size must be between 1 and 5\"}");
                    }
                }
            }
        }
        if ("POST".equalsIgnoreCase(request.getMethod())) {
            String body = request.getBody() == null ? "" : request.getBody().trim();
            if (!body.isEmpty()) {
                try {
                    JsonObject payload = gson.fromJson(body, JsonObject.class);
                    if (payload != null) {
                        JsonElement actionElement = payload.get("action");
                        if (actionElement != null && (!actionElement.isJsonPrimitive()
                                || !actionElement.getAsJsonPrimitive().isString())) {
                            return jsonResponse(400, "{\"error\":\"help action must be a string\"}");
                        }
                        if ("help".equalsIgnoreCase(payload.has("action") ? payload.get("action").getAsString() : "")
                                && payload.has("topic")) {
                            if (!payload.get("topic").isJsonPrimitive()
                                    || !payload.getAsJsonPrimitive("topic").isString()) {
                                return jsonResponse(400, "{\"error\":\"help topic must be a string\"}");
                            }
                            topic = payload.get("topic").getAsString();
                        } else if (payload.has("topic")) {
                            if (!payload.get("topic").isJsonPrimitive()
                                    || !payload.getAsJsonPrimitive("topic").isString()) {
                                return jsonResponse(400, "{\"error\":\"help topic must be a string\"}");
                            }
                            topic = payload.get("topic").getAsString();
                        } else if (payload.has("section")) {
                            if (!payload.get("section").isJsonPrimitive()
                                    || !payload.getAsJsonPrimitive("section").isString()) {
                                return jsonResponse(400, "{\"error\":\"help section must be a string\"}");
                            }
                            topic = payload.get("section").getAsString();
                        } else if (payload.has("help")) {
                            if (!payload.get("help").isJsonPrimitive()
                                    || !payload.getAsJsonPrimitive("help").isString()) {
                                return jsonResponse(400, "{\"error\":\"help topic must be a string\"}");
                            }
                            topic = payload.get("help").getAsString();
                        }
                        if (payload.has("page")) {
                            page = parseHelpPositiveInteger(payload.get("page"));
                            if (page == null) {
                                return jsonResponse(400, "{\"error\":\"help page must be a positive integer\"}");
                            }
                        }
                        JsonElement pageSizeElement = payload.has("page_size")
                                ? payload.get("page_size") : payload.get("pageSize");
                        if (pageSizeElement != null) {
                            pageSize = parseHelpPositiveInteger(pageSizeElement);
                            if (pageSize == null || pageSize > HelpProvider.MAX_PAGE_SIZE) {
                                return jsonResponse(400, "{\"error\":\"help page_size must be between 1 and 5\"}");
                            }
                        }
                    }
                } catch (JsonSyntaxException | IllegalStateException ignored) {
                    if ("help".equalsIgnoreCase(body)) {
                        topic = null;
                    } else if (body.toLowerCase().startsWith("help ")) {
                        topic = body.substring(5).trim();
                    }
                }
            }
        }
        String sessionId = request.getHeader("X-Session-Id");
        if (sessionId == null || sessionId.trim().isEmpty()) {
            return jsonResponse(401, "{\"error\":\"Session ID required\"}");
        }
        SessionManager.Session session = sessionManager.validateSession(sessionId.trim());
        if (session == null) {
            return jsonResponse(401, "{\"error\":\"Invalid or expired session\"}");
        }
        User user = session.getUser();
        String domain = session.getCurrentDomain();
        String db = session.getCurrentDB();
        String response = HelpProvider.getHelpJson(topic, page, pageSize, user, domain, db);
        return jsonResponse(responseStatus(response), response);
    }

    private VDBTransportResponse handleLicenseRequest(VDBTransportRequest request) {
        if (!"GET".equalsIgnoreCase(request.getMethod())) {
            return jsonResponse(405, "{\"error\":\"Method not allowed\"}");
        }
        return jsonResponse(200, gson.toJson(MitLicense.licenseDisclosure()));
    }

    private VDBTransportResponse handleRootRequest(VDBTransportRequest request) {
        Map<String, Object> responseMap = new HashMap<>();
        responseMap.put(".>", "Welcome to Verun");
        responseMap.put("Versa + VDB", "Built for Versatile Multi-tenancy");
        responseMap.put("health", "/health");
        responseMap.put("license", "/license");
        responseMap.put("help", "/help (requires X-Session-Id; supports topic and page; page_size is limited to 1..5)");

        Map<String, String> authInstructions = new HashMap<>();
        authInstructions.put("instructions", "To authenticate, send a POST request to /auth with Basic Auth headers");
        authInstructions.put("example", "curl -X POST http://localhost:1957/auth --user username:password");
        authInstructions.put("response", "This will return a session ID to use in subsequent requests");

        Map<String, Object> sessionUsage = new HashMap<>();

        Map<String, String> terminalExample = new HashMap<>();
        terminalExample.put("description", "Using curl with session ID");
        terminalExample.put("example",
                "curl -X POST http://localhost:1957/vdb -H 'X-Session-Id: YOUR_SESSION_ID' -H 'Content-Type: text/versa' --data 'echo \"Hello\";'");

        Map<String, String> postmanExample = new HashMap<>();
        postmanExample.put("description", "Using Postman with session ID");
        postmanExample.put("example",
                "1. Go to Headers\n2. Add a header with Key: X-Session-Id and Value: YOUR_SESSION_ID\n3. Send your Versa VDB command in the request body");

        sessionUsage.put("terminal", terminalExample);
        sessionUsage.put("postman", postmanExample);

        responseMap.put("authentication", authInstructions);
        responseMap.put("session_usage", sessionUsage);

        return jsonResponse(200, gson.toJson(responseMap));
    }

    private VDBTransportResponse jsonResponse(int statusCode, String body) {
        return VDBTransportResponse.json(statusCode, body);
    }

    private JsonObject readJsonPayload(String body) {
        try {
            String raw = body == null ? "" : body.trim();
            if (raw.isEmpty()) {
                return new JsonObject();
            }
            JsonElement parsed = gson.fromJson(raw, JsonElement.class);
            return parsed != null && parsed.isJsonObject() ? parsed.getAsJsonObject() : new JsonObject();
        } catch (Exception e) {
            return new JsonObject();
        }
    }

    private String queryValue(VDBTransportRequest request, String key) {
        if (request == null || request.getRawQuery() == null || request.getRawQuery().isEmpty()) {
            return "";
        }
        String raw = request.getRawQuery();
        List<String> pairs = new ArrayList<>();
        Collections.addAll(pairs, raw.split("&"));
        for (String pair : pairs) {
            String[] kv = pair.split("=", 2);
            if (kv.length == 2 && key.equalsIgnoreCase(kv[0])) {
                return java.net.URLDecoder.decode(kv[1], StandardCharsets.UTF_8);
            }
        }
        return "";
    }

    private String formatJson(String json) {
        try {
            JsonElement je = gson.fromJson(json, JsonElement.class);
            return gson.toJson(je);
        } catch (JsonSyntaxException e) {
            return json;
        }
    }

    private String safeJsonText(String text) {
        return text == null ? "" : text.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private String decodeHelpTopic(String raw) {
        try {
            return java.net.URLDecoder.decode(raw, StandardCharsets.UTF_8);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    private Integer parseHelpPositiveInteger(String raw) {
        try {
            if (raw == null || !raw.matches("[1-9][0-9]*")) {
                return null;
            }
            return Integer.valueOf(raw);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private Integer parseHelpPositiveInteger(JsonElement value) {
        try {
            if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber()) {
                return null;
            }
            java.math.BigDecimal number = value.getAsBigDecimal().stripTrailingZeros();
            if (number.scale() > 0 || number.signum() <= 0
                    || number.compareTo(java.math.BigDecimal.valueOf(Integer.MAX_VALUE)) > 0) {
                return null;
            }
            return number.intValueExact();
        } catch (ArithmeticException | NumberFormatException e) {
            return null;
        }
    }

    private void logInfo(String message) {
        if (consoleLogsEnabled) {
            System.out.println(message);
        }
    }

    private void logHttp(String message) {
        if (httpTrafficLogsEnabled) {
            System.out.println(message);
        }
    }
}
