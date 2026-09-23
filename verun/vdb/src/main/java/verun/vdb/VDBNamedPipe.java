// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonSyntaxException;
import com.sun.jna.platform.win32.Kernel32;
import com.sun.jna.platform.win32.WinBase;
import com.sun.jna.platform.win32.WinError;
import com.sun.jna.platform.win32.WinNT.HANDLE;
import com.sun.jna.ptr.IntByReference;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class VDBNamedPipe implements AutoCloseable {
    private static final int PIPE_BUFFER_BYTES = 64 * 1024;

    private final Gson gson = new Gson();
    private final VDBRequestDispatcher dispatcher;
    private final ExecutorService clientExecutor;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final String pipePath;
    private final boolean consoleLogsEnabled = VDBLogSettings.isConsoleLogsEnabled();
    private volatile HANDLE acceptHandle;

    public VDBNamedPipe() {
        this(VDBInterfaceSettings.getNamedPipePath());
    }

    public VDBNamedPipe(String pipePath) {
        this(pipePath, new VDBRequestDispatcher(new SessionManager(), "VDBNamedPipe"));
    }

    public VDBNamedPipe(String pipePath, VDBRequestDispatcher dispatcher) {
        this.pipePath = VDBInterfaceSettings.normalizeNamedPipePath(pipePath);
        this.dispatcher = dispatcher == null ? new VDBRequestDispatcher() : dispatcher;
        this.clientExecutor = Executors.newCachedThreadPool(runnable -> {
            Thread thread = new Thread(runnable, "vdb-namedpipe-client");
            thread.setDaemon(true);
            return thread;
        });
    }

    public void start() throws Exception {
        if (!VDBInterfaceSettings.isNamedPipeEnabled()) {
            throw new IllegalStateException("VDBNamedPipe is disabled by configuration");
        }
        if (!running.compareAndSet(false, true)) {
            throw new IllegalStateException("VDBNamedPipe is already running");
        }

        MitLicense.initialize();
        MitLicense.requireAccepted("namedpipe");
        try {
            IndexAdvisor.startupAdvisor("namedpipe", System.console() != null);
        } catch (Exception e) {
            logInfo("Index advisor startup check failed: " + e.getMessage());
        }

        logInfo("VDBNamedPipe listening on " + pipePath);
        try {
            while (running.get()) {
                HANDLE pipeHandle = createServerPipe();
                acceptHandle = pipeHandle;
                waitForClient(pipeHandle);
                acceptHandle = null;
                if (!running.get()) {
                    closeHandle(pipeHandle);
                    break;
                }
                clientExecutor.submit(() -> handleClient(pipeHandle));
            }
        } finally {
            close();
        }
    }

    public String getPipePath() {
        return pipePath;
    }

    @Override
    public void close() {
        if (!running.compareAndSet(true, false)) {
            closeHandle(acceptHandle);
            acceptHandle = null;
            return;
        }
        closeHandle(acceptHandle);
        acceptHandle = null;
        clientExecutor.shutdownNow();
        try {
            clientExecutor.awaitTermination(2, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private HANDLE createServerPipe() throws IOException {
        HANDLE pipeHandle = Kernel32.INSTANCE.CreateNamedPipe(
                pipePath,
                WinBase.PIPE_ACCESS_DUPLEX,
                WinBase.PIPE_TYPE_BYTE | WinBase.PIPE_READMODE_BYTE | WinBase.PIPE_WAIT,
                WinBase.PIPE_UNLIMITED_INSTANCES,
                PIPE_BUFFER_BYTES,
                PIPE_BUFFER_BYTES,
                0,
                null
        );
        if (WinBase.INVALID_HANDLE_VALUE.equals(pipeHandle)) {
            throw new IOException("CreateNamedPipe failed: " + Kernel32.INSTANCE.GetLastError());
        }
        return pipeHandle;
    }

    private void waitForClient(HANDLE pipeHandle) throws IOException {
        boolean connected = Kernel32.INSTANCE.ConnectNamedPipe(pipeHandle, null);
        if (!connected) {
            int error = Kernel32.INSTANCE.GetLastError();
            if (error == WinError.ERROR_PIPE_CONNECTED) {
                return;
            }
            if (!running.get() && error == WinError.ERROR_NO_DATA) {
                return;
            }
            closeHandle(pipeHandle);
            throw new IOException("ConnectNamedPipe failed: " + error);
        }
    }

    private void handleClient(HANDLE pipeHandle) {
        try (InputStream input = new NamedPipeInputStream(pipeHandle, pipePath);
             OutputStream output = new NamedPipeOutputStream(pipeHandle, pipePath)) {
            while (running.get()) {
                String requestJson = VDBSocketFrames.readFrame(input);
                if (requestJson == null) {
                    break;
                }
                String responseJson = handleNamedPipeRequest(requestJson);
                VDBSocketFrames.writeFrame(output, responseJson);
            }
        } catch (Exception e) {
            logInfo("VDBNamedPipe client error: " + e.getMessage());
        } finally {
            try {
                Kernel32.INSTANCE.FlushFileBuffers(pipeHandle);
            } catch (Exception ignored) {
            }
            try {
                Kernel32.INSTANCE.DisconnectNamedPipe(pipeHandle);
            } catch (Exception ignored) {
            }
            closeHandle(pipeHandle);
        }
    }

    private String handleNamedPipeRequest(String rawRequest) {
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
                    "namedpipe://" + pipePath);
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

    private void closeHandle(HANDLE handle) {
        if (handle != null && !WinBase.INVALID_HANDLE_VALUE.equals(handle)) {
            Kernel32.INSTANCE.CloseHandle(handle);
        }
    }

    public static void main(String[] args) throws Exception {
        String configuredPath = args != null && args.length > 0 && args[0] != null && !args[0].trim().isEmpty()
                ? args[0].trim()
                : VDBInterfaceSettings.getNamedPipePath();
        new VDBNamedPipe(configuredPath).start();
    }

    private static final class NamedPipeInputStream extends InputStream {
        private final HANDLE handle;
        private final String pipePath;

        private NamedPipeInputStream(HANDLE handle, String pipePath) {
            this.handle = handle;
            this.pipePath = pipePath;
        }

        @Override
        public int read() throws IOException {
            byte[] single = new byte[1];
            int count = read(single, 0, 1);
            if (count < 0) {
                return -1;
            }
            return single[0] & 0xff;
        }

        @Override
        public int read(byte[] buffer, int offset, int length) throws IOException {
            if (buffer == null) {
                throw new NullPointerException("buffer");
            }
            if (offset < 0 || length < 0 || offset + length > buffer.length) {
                throw new IndexOutOfBoundsException("Invalid offset/length");
            }
            if (length == 0) {
                return 0;
            }
            byte[] chunk = new byte[length];
            IntByReference read = new IntByReference();
            boolean ok = Kernel32.INSTANCE.ReadFile(handle, chunk, length, read, null);
            if (!ok) {
                int error = Kernel32.INSTANCE.GetLastError();
                if (error == WinError.ERROR_BROKEN_PIPE || error == WinError.ERROR_NO_DATA) {
                    return -1;
                }
                throw new IOException("ReadFile failed for " + pipePath + ": " + error);
            }
            int count = read.getValue();
            if (count <= 0) {
                return -1;
            }
            System.arraycopy(chunk, 0, buffer, offset, count);
            return count;
        }
    }

    private static final class NamedPipeOutputStream extends OutputStream {
        private final HANDLE handle;
        private final String pipePath;

        private NamedPipeOutputStream(HANDLE handle, String pipePath) {
            this.handle = handle;
            this.pipePath = pipePath;
        }

        @Override
        public void write(int value) throws IOException {
            write(new byte[] {(byte) value}, 0, 1);
        }

        @Override
        public void write(byte[] buffer, int offset, int length) throws IOException {
            if (buffer == null) {
                throw new NullPointerException("buffer");
            }
            if (offset < 0 || length < 0 || offset + length > buffer.length) {
                throw new IndexOutOfBoundsException("Invalid offset/length");
            }
            int writtenTotal = 0;
            while (writtenTotal < length) {
                int remaining = length - writtenTotal;
                byte[] chunk = new byte[remaining];
                System.arraycopy(buffer, offset + writtenTotal, chunk, 0, remaining);
                IntByReference written = new IntByReference();
                boolean ok = Kernel32.INSTANCE.WriteFile(handle, chunk, remaining, written, null);
                if (!ok) {
                    throw new IOException("WriteFile failed for " + pipePath + ": " + Kernel32.INSTANCE.GetLastError());
                }
                int count = written.getValue();
                if (count <= 0) {
                    throw new IOException("WriteFile wrote zero bytes for " + pipePath);
                }
                writtenTotal += count;
            }
        }
    }
}
