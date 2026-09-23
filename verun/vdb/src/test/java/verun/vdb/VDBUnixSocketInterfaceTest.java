// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.Channels;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class VDBUnixSocketInterfaceTest {
    private static final Gson GSON = new Gson();

    @BeforeAll
    static void bootstrapVdb() {
        VdbTestSupport.ensureBootstrappedSuperAdmin();
    }

    @Test
    void acceptsAuthAndVqlRequestsAndCleansUpSocketFile() throws Exception {
        assumeTrue(unixSocketOperational(), "Unix socket binding is unavailable in this environment");
        UserManager userManager = UserManager.getInstance();
        String username = "socket_" + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        String password = "Aa1!aaaa";
        userManager.addUser(new User(username, username + "@local.test", "APPLICATION", password));

        Path socketDir = Files.createTempDirectory("vdb-unixsocket-test");
        Path socketPath = socketDir.resolve("vdb.sock");
        Files.writeString(socketPath, "stale");

        VDBUnixSocket server = new VDBUnixSocket(socketPath.toString());
        Thread serverThread = new Thread(() -> {
            try {
                server.start();
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }, "vdb-unixsocket-test-server");
        serverThread.setDaemon(true);
        serverThread.start();

        try {
            waitForSocket(socketPath);

            JsonObject authRequest = new JsonObject();
            authRequest.addProperty("method", "POST");
            authRequest.addProperty("path", "/auth");
            JsonObject authHeaders = new JsonObject();
            String basic = Base64.getEncoder().encodeToString((username + ":" + password).getBytes());
            authHeaders.addProperty("Authorization", "Basic " + basic);
            authRequest.add("headers", authHeaders);

            JsonObject authResponse = send(socketPath, authRequest);
            assertEquals(200, authResponse.get("statusCode").getAsInt());
            JsonObject authBody = authResponse.getAsJsonObject("body");
            String sessionId = authBody.get("sessionId").getAsString();
            assertFalse(sessionId.trim().isEmpty());

            JsonObject vqlRequest = new JsonObject();
            vqlRequest.addProperty("method", "POST");
            vqlRequest.addProperty("path", "/vql");
            JsonObject vqlHeaders = new JsonObject();
            vqlHeaders.addProperty("X-Session-Id", sessionId);
            vqlRequest.add("headers", vqlHeaders);
            JsonObject vqlBody = new JsonObject();
            vqlBody.addProperty("action", "whoami");
            vqlRequest.add("body", vqlBody);

            JsonObject vqlResponse = send(socketPath, vqlRequest);
            assertEquals(200, vqlResponse.get("statusCode").getAsInt());
            JsonObject vqlBodyResponse = vqlResponse.getAsJsonObject("body");
            assertEquals("success", vqlBodyResponse.get("status").getAsString());
            JsonObject vqlData = vqlBodyResponse.getAsJsonObject("data");
            assertNotNull(vqlData);
            assertEquals(username, vqlData.get("username").getAsString());
        } finally {
            server.close();
            serverThread.join(4000);
            userManager.deleteUser(username);
            Files.deleteIfExists(socketDir);
        }

        assertFalse(serverThread.isAlive());
        assertTrue(Files.notExists(socketPath));
    }

    @Test
    void returnsJsonErrorForMalformedRequestEnvelope() throws Exception {
        assumeTrue(unixSocketOperational(), "Unix socket binding is unavailable in this environment");
        Path socketDir = Files.createTempDirectory("vdb-unixsocket-test");
        Path socketPath = socketDir.resolve("vdb.sock");
        AtomicReference<Throwable> serverFailure = new AtomicReference<>();

        VDBUnixSocket server = new VDBUnixSocket(socketPath.toString());
        Thread serverThread = new Thread(() -> {
            try {
                server.start();
            } catch (Throwable t) {
                serverFailure.set(t);
            }
        }, "vdb-unixsocket-malformed-server");
        serverThread.setDaemon(true);
        serverThread.start();

        try {
            waitForSocket(socketPath);

            JsonObject response = sendRaw(socketPath, "{bad-json");
            assertEquals(400, response.get("statusCode").getAsInt());
            JsonObject body = response.getAsJsonObject("body");
            assertTrue(body.get("error").getAsString().contains("Invalid request envelope JSON"));
        } finally {
            server.close();
            serverThread.join(4000);
            Files.deleteIfExists(socketDir);
        }

        Throwable failure = serverFailure.get();
        if (failure != null) {
            throw new AssertionError("Server thread failed unexpectedly", failure);
        }
        assertFalse(serverThread.isAlive());
        assertTrue(Files.notExists(socketPath));
    }

    private JsonObject send(Path socketPath, JsonObject request) throws Exception {
        return sendRaw(socketPath, GSON.toJson(request));
    }

    private static boolean unixSocketOperational() {
        if (!VDBInterfaceSettings.supportsUnixSocket()) {
            return false;
        }
        Path directory = null;
        try {
            directory = Files.createTempDirectory("vdb-unixsocket-probe");
            Path path = directory.resolve("probe.sock");
            try (ServerSocketChannel channel = ServerSocketChannel.open(StandardProtocolFamily.UNIX)) {
                channel.bind(UnixDomainSocketAddress.of(path));
                return true;
            }
        } catch (Exception ignored) {
            return false;
        } finally {
            if (directory != null) {
                try (var entries = Files.list(directory)) {
                    entries.forEach(item -> {
                        try { Files.deleteIfExists(item); } catch (Exception ignored) { }
                    });
                } catch (Exception ignored) { }
                try { Files.deleteIfExists(directory); } catch (Exception ignored) { }
            }
        }
    }

    private JsonObject sendRaw(Path socketPath, String requestJson) throws Exception {
        Exception lastError = null;
        for (int i = 0; i < 20; i++) {
            try (SocketChannel channel = SocketChannel.open(StandardProtocolFamily.UNIX)) {
                channel.connect(UnixDomainSocketAddress.of(socketPath));
                try (InputStream input = Channels.newInputStream(channel);
                     OutputStream output = Channels.newOutputStream(channel)) {
                    VDBSocketFrames.writeFrame(output, requestJson);
                    String responseJson = VDBSocketFrames.readFrame(input);
                    return GSON.fromJson(responseJson, JsonObject.class);
                }
            } catch (Exception exc) {
                lastError = exc;
                Thread.sleep(100);
            }
        }
        throw lastError == null ? new IllegalStateException("Socket request failed") : lastError;
    }

    private void waitForSocket(Path socketPath) throws Exception {
        for (int i = 0; i < 50; i++) {
            if (Files.exists(socketPath)) {
                return;
            }
            Thread.sleep(100);
        }
        throw new IllegalStateException("Socket file was not created: " + socketPath);
    }
}
