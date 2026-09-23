// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class VDBHttpServer {
    private static final int DEFAULT_PORT = 1957;
    private final HttpServer server;
    private final VDBRequestDispatcher dispatcher;
    private final boolean consoleLogsEnabled = VDBLogSettings.isConsoleLogsEnabled();
    private final int port;

    public VDBHttpServer(String domain) throws IOException {
        MitLicense.initialize();
        this.port = resolvePort();
        this.server = HttpServer.create(new InetSocketAddress(this.port), 0);
        this.dispatcher = new VDBRequestDispatcher();

        server.createContext("/vdb", this::handleRequest);
        // Temporary compatibility alias. Native clients use /vdb.
        server.createContext("/vql", this::handleRequest);
        server.createContext("/help", this::handleRequest);
        server.createContext("/auth", this::handleRequest);
        server.createContext("/health", this::handleRequest);
        server.createContext("/license", this::handleRequest);
        server.createContext("/", this::handleRequest);
        server.setExecutor(null);
    }

    public void start() {
        MitLicense.requireAccepted("http");
        try {
            IndexAdvisor.startupAdvisor("serve", System.console() != null);
        } catch (Exception e) {
            logInfo("Index advisor startup check failed: " + e.getMessage());
        }
        server.start();
        logInfo("VDB server listening on http://127.0.0.1:" + this.port);
    }

    static int resolvePort() {
        String[] candidates = {
                System.getProperty("vdb.http.port"),
                System.getenv("VDB_HTTP_PORT")
        };
        for (String candidate : candidates) {
            if (candidate == null) {
                continue;
            }
            String text = candidate.trim();
            if (text.isEmpty()) {
                continue;
            }
            try {
                int parsed = Integer.parseInt(text);
                if (parsed > 0 && parsed <= 65535) {
                    return parsed;
                }
            } catch (NumberFormatException ignored) {
                // Fall back to the default port when the value is invalid.
            }
        }
        return DEFAULT_PORT;
    }

    private void handleRequest(HttpExchange exchange) throws IOException {
        VDBTransportRequest request = toTransportRequest(exchange);
        VDBTransportResponse response = dispatcher.dispatch(request);
        sendResponse(response, exchange);
    }

    private VDBTransportRequest toTransportRequest(HttpExchange exchange) throws IOException {
        Map<String, String> headers = new LinkedHashMap<>();
        for (Map.Entry<String, List<String>> entry : exchange.getRequestHeaders().entrySet()) {
            if (entry.getValue() == null || entry.getValue().isEmpty()) {
                headers.put(entry.getKey(), "");
            } else {
                headers.put(entry.getKey(), entry.getValue().get(0));
            }
        }
        String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        String path = exchange.getRequestURI() == null ? "/" : exchange.getRequestURI().getPath();
        String rawQuery = exchange.getRequestURI() == null || exchange.getRequestURI().getRawQuery() == null
                ? ""
                : exchange.getRequestURI().getRawQuery();
        String remoteAddress = exchange.getRemoteAddress() == null ? "" : String.valueOf(exchange.getRemoteAddress());
        return new VDBTransportRequest(
                exchange.getRequestMethod(),
                path,
                rawQuery,
                headers,
                body,
                remoteAddress);
    }

    private void sendResponse(VDBTransportResponse response, HttpExchange exchange) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", response.getContentType());
        byte[] responseBytes = response.getBody().getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(response.getStatusCode(), responseBytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(responseBytes);
        }
    }

    private void logInfo(String message) {
        if (consoleLogsEnabled) {
            System.out.println(message);
        }
    }

    public static void main(String[] args) throws IOException {
        new VDBHttpServer("default").start();
    }
}
