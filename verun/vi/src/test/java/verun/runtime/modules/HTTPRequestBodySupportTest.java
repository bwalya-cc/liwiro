// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

public class HTTPRequestBodySupportTest {
    private static HttpServer server;
    private static String baseUrl;

    @BeforeAll
    static void startServer() throws IOException {
        assumeTrue(localTcpAvailable(), "Local TCP binding is unavailable in this environment");
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/form", exchange -> {
            String contentType = String.valueOf(exchange.getRequestHeaders().getFirst("Content-Type"));
            String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            byte[] bytes = ("contentType=" + contentType + ";body=" + body).getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(bytes);
            }
        });
        server.createContext("/bytes", exchange -> {
            String contentType = String.valueOf(exchange.getRequestHeaders().getFirst("Content-Type"));
            byte[] requestBytes = exchange.getRequestBody().readAllBytes();
            String body = "contentType=" + contentType
                    + ";len=" + requestBytes.length
                    + ";base64=" + Base64.getEncoder().encodeToString(requestBytes);
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(bytes);
            }
        });
        server.start();
        baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
    }

    private static boolean localTcpAvailable() {
        try (java.net.ServerSocket probe = new java.net.ServerSocket(0)) {
            return true;
        } catch (IOException ignored) {
            return false;
        }
    }

    @AfterAll
    static void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void supportsFormOptionWithUrlEncoding() {
        Map<String, Object> form = new LinkedHashMap<>();
        form.put("file", "data:image/png;base64,abc==");
        form.put("folder", "liwiro demo");

        Map<String, Object> options = new LinkedHashMap<>();
        options.put("form", form);

        Map<String, Object> response = HTTP.postSync(baseUrl + "/form", options);
        String body = String.valueOf(response.get("body"));

        assertEquals(200, response.get("status"));
        assertTrue(body.contains("contentType=application/x-www-form-urlencoded"));
        assertTrue(body.contains("file=data%3Aimage%2Fpng%3Bbase64%2Cabc%3D%3D"));
        assertTrue(body.contains("folder=liwiro+demo"));
    }

    @Test
    void supportsBase64DecodedBinaryBody() {
        byte[] payload = "hello-media".getBytes(StandardCharsets.UTF_8);
        Map<String, Object> options = new LinkedHashMap<>();
        options.put("bodyBytesBase64", Base64.getEncoder().encodeToString(payload));
        options.put("headers", Map.of("Content-Type", "application/octet-stream"));

        Map<String, Object> response = HTTP.putSync(baseUrl + "/bytes", options);
        String body = String.valueOf(response.get("body"));

        assertEquals(200, response.get("status"));
        assertTrue(body.contains("contentType=application/octet-stream"));
        assertTrue(body.contains("len=" + payload.length));
        assertTrue(body.contains("base64=" + Base64.getEncoder().encodeToString(payload)));
    }
}
