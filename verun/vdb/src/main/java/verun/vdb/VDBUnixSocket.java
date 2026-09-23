// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonSyntaxException;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.Channels;
import java.nio.channels.ClosedChannelException;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class VDBUnixSocket implements AutoCloseable {
    private final Gson gson = new Gson();
    private final VDBRequestDispatcher dispatcher;
    private final ExecutorService clientExecutor;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final Path socketPath;
    private final boolean consoleLogsEnabled = VDBLogSettings.isConsoleLogsEnabled();
    private volatile ServerSocketChannel serverChannel;
    private Thread shutdownHook;

    public VDBUnixSocket() {
        this(VDBInterfaceSettings.getUnixSocketPath());
    }

    public VDBUnixSocket(String socketPath) {
        this(socketPath, new VDBRequestDispatcher(new SessionManager(), "VDBUnixSocket"));
    }

    public VDBUnixSocket(String socketPath, VDBRequestDispatcher dispatcher) {
        this.socketPath = Paths.get(socketPath == null || socketPath.trim().isEmpty()
                ? VDBInterfaceSettings.getUnixSocketPath()
                : socketPath.trim()).toAbsolutePath().normalize();
        this.dispatcher = dispatcher == null ? new VDBRequestDispatcher() : dispatcher;
        this.clientExecutor = Executors.newCachedThreadPool(runnable -> {
            Thread thread = new Thread(runnable, "vdb-unixsocket-client");
            thread.setDaemon(true);
            return thread;
        });
    }

    public void start() throws Exception {
        if (!VDBInterfaceSettings.isUnixSocketEnabled()) {
            throw new IllegalStateException("VDBUnixSocket is disabled by configuration");
        }
        if (!running.compareAndSet(false, true)) {
            throw new IllegalStateException("VDBUnixSocket is already running");
        }

        MitLicense.initialize();
        MitLicense.requireAccepted("unixsocket");
        try {
            IndexAdvisor.startupAdvisor("socket", System.console() != null);
        } catch (Exception e) {
            logInfo("Index advisor startup check failed: " + e.getMessage());
        }

        try {
            prepareSocketFile();
            ServerSocketChannel channel = ServerSocketChannel.open(StandardProtocolFamily.UNIX);
            channel.bind(UnixDomainSocketAddress.of(socketPath));
            serverChannel = channel;
            registerShutdownHook();
            logInfo("VDBUnixSocket listening on " + socketPath);

            while (running.get()) {
                SocketChannel client = channel.accept();
                clientExecutor.submit(() -> handleClient(client));
            }
        } catch (ClosedChannelException ignored) {
            // Normal during shutdown.
        } catch (Exception e) {
            logInfo("VDBUnixSocket failed to start on " + socketPath + ": " + e.getMessage());
            running.set(false);
            cleanupSocketFile();
            throw e;
        } finally {
            close();
        }
    }

    public String getSocketPath() {
        return socketPath.toString();
    }

    @Override
    public void close() {
        if (!running.compareAndSet(true, false)) {
            cleanupSocketFile();
            return;
        }
        try {
            if (serverChannel != null && serverChannel.isOpen()) {
                serverChannel.close();
            }
        } catch (Exception ignored) {
        }
        clientExecutor.shutdownNow();
        try {
            clientExecutor.awaitTermination(2, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        cleanupSocketFile();
        unregisterShutdownHook();
    }

    private void prepareSocketFile() throws Exception {
        Path parent = socketPath.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }
        Files.deleteIfExists(socketPath);
    }

    private void cleanupSocketFile() {
        try {
            Files.deleteIfExists(socketPath);
        } catch (Exception e) {
            logInfo("Failed to remove unix socket file " + socketPath + ": " + e.getMessage());
        }
    }

    private void registerShutdownHook() {
        shutdownHook = new Thread(this::cleanupSocketFile, "vdb-unixsocket-cleanup");
        try {
            Runtime.getRuntime().addShutdownHook(shutdownHook);
        } catch (IllegalStateException ignored) {
            shutdownHook = null;
        }
    }

    private void unregisterShutdownHook() {
        if (shutdownHook == null) {
            return;
        }
        try {
            Runtime.getRuntime().removeShutdownHook(shutdownHook);
        } catch (IllegalStateException ignored) {
            // JVM is already shutting down.
        }
        shutdownHook = null;
    }

    private void handleClient(SocketChannel clientChannel) {
        try (SocketChannel socket = clientChannel;
             InputStream input = Channels.newInputStream(socket);
             OutputStream output = Channels.newOutputStream(socket)) {
            while (running.get()) {
                String requestJson = VDBSocketFrames.readFrame(input);
                if (requestJson == null) {
                    break;
                }
                String responseJson = handleSocketRequest(requestJson, describeRemote(socket));
                VDBSocketFrames.writeFrame(output, responseJson);
            }
        } catch (Exception e) {
            logInfo("VDBUnixSocket client error: " + e.getMessage());
        }
    }

    private String handleSocketRequest(String rawRequest, String remoteAddress) {
        try {
            JsonElement parsed = gson.fromJson(rawRequest, JsonElement.class);
            if (parsed == null || !parsed.isJsonObject()) {
                return buildEnvelope(VDBTransportResponse.json(400, "{\"error\":\"Invalid request envelope\"}"));
            }
            JsonObject requestObject = parsed.getAsJsonObject();
            String method = readString(requestObject, "method", "POST");
            String path = readString(requestObject, "path", "/");
            String rawQuery = readString(requestObject, "rawQuery", "");
            if ((rawQuery == null || rawQuery.isEmpty()) && path.contains("?")) {
                int queryPos = path.indexOf('?');
                rawQuery = path.substring(queryPos + 1);
                path = path.substring(0, queryPos);
            }

            Map<String, String> headers = new LinkedHashMap<>();
            if (requestObject.has("headers") && requestObject.get("headers").isJsonObject()) {
                JsonObject headersObject = requestObject.getAsJsonObject("headers");
                for (Map.Entry<String, JsonElement> entry : headersObject.entrySet()) {
                    headers.put(entry.getKey(), entry.getValue().isJsonNull() ? "" : entry.getValue().getAsString());
                }
            }

            String body = "";
            if (requestObject.has("body")) {
                JsonElement bodyElement = requestObject.get("body");
                if (bodyElement != null && !bodyElement.isJsonNull()) {
                    body = bodyElement.isJsonPrimitive() && bodyElement.getAsJsonPrimitive().isString()
                            ? bodyElement.getAsString()
                            : gson.toJson(bodyElement);
                }
            }

            VDBTransportRequest request = new VDBTransportRequest(
                    method,
                    path,
                    rawQuery,
                    headers,
                    body,
                    remoteAddress);
            return buildEnvelope(dispatcher.dispatch(request));
        } catch (JsonSyntaxException e) {
            return buildEnvelope(VDBTransportResponse.json(400, "{\"error\":\"Invalid request envelope JSON\"}"));
        } catch (Exception e) {
            return buildEnvelope(VDBTransportResponse.json(
                    500,
                    "{\"error\":\"Server error: " + safeJsonText(e.getMessage()) + "\"}"));
        }
    }

    private String buildEnvelope(VDBTransportResponse response) {
        JsonObject envelope = new JsonObject();
        envelope.addProperty("statusCode", response.getStatusCode());
        envelope.addProperty("contentType", response.getContentType());
        try {
            if (response.getContentType().toLowerCase().contains("application/json")) {
                JsonElement parsedBody = gson.fromJson(response.getBody(), JsonElement.class);
                envelope.add("body", parsedBody == null ? new JsonObject() : parsedBody);
            } else {
                envelope.addProperty("body", response.getBody());
            }
        } catch (Exception e) {
            envelope.addProperty("body", response.getBody());
        }
        return gson.toJson(envelope);
    }

    private String describeRemote(SocketChannel socket) {
        try {
            return String.valueOf(socket.getRemoteAddress());
        } catch (Exception ignored) {
            return "unixsocket";
        }
    }

    private String readString(JsonObject obj, String key, String fallback) {
        if (obj == null || !obj.has(key) || obj.get(key).isJsonNull()) {
            return fallback;
        }
        try {
            return obj.get(key).getAsString();
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private String safeJsonText(String text) {
        return text == null ? "" : text.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private void logInfo(String message) {
        if (consoleLogsEnabled) {
            System.out.println(message);
        }
    }

    public static void main(String[] args) throws Exception {
        String configuredPath = args != null && args.length > 0 && args[0] != null && !args[0].trim().isEmpty()
                ? args[0].trim()
                : VDBInterfaceSettings.getUnixSocketPath();
        new VDBUnixSocket(configuredPath).start();
    }
}
