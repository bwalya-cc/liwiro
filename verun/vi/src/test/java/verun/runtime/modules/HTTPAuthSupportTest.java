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
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

public class HTTPAuthSupportTest {
    private static HttpServer server;
    private static String baseUrl;

    @BeforeAll
    static void startServer() throws IOException {
        assumeTrue(localTcpAvailable(), "Local TCP binding is unavailable in this environment");
        server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/echo", exchange -> {
            String auth = exchange.getRequestHeaders().getFirst("Authorization");
            String api = exchange.getRequestHeaders().getFirst("X-API-Key");
            String query = exchange.getRequestURI().getRawQuery();
            String response = "auth=" + (auth == null ? "" : auth)
                    + ";api=" + (api == null ? "" : api)
                    + ";query=" + (query == null ? "" : query);
            byte[] bytes = response.getBytes();
            exchange.getResponseHeaders().add("Content-Type", "text/plain");
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
    void supportsLegacyBearerOption() {
        Map<String, Object> options = new LinkedHashMap<>();
        options.put("authBearer", "token-123");

        Map<String, Object> response = HTTP.getSync(baseUrl + "/echo", options);
        String body = String.valueOf(response.get("body"));
        assertEquals(200, response.get("status"));
        assertTrue(body.contains("auth=Bearer token-123"));
    }

    @Test
    void supportsBasicAndOAuth2AuthOptions() {
        Map<String, Object> basic = new LinkedHashMap<>();
        basic.put("username", "demo");
        basic.put("password", "pass");
        Map<String, Object> options = new LinkedHashMap<>();
        options.put("authBasic", basic);

        Map<String, Object> basicResp = HTTP.getSync(baseUrl + "/echo", options);
        String basicBody = String.valueOf(basicResp.get("body"));
        assertTrue(basicBody.contains("auth=Basic "));

        Map<String, Object> oauth = new LinkedHashMap<>();
        oauth.put("accessToken", "abc123");
        oauth.put("tokenType", "Bearer");
        Map<String, Object> oauthOpts = new LinkedHashMap<>();
        oauthOpts.put("authOAuth2", oauth);
        Map<String, Object> oauthResp = HTTP.getSync(baseUrl + "/echo", oauthOpts);
        String oauthBody = String.valueOf(oauthResp.get("body"));
        assertTrue(oauthBody.contains("auth=Bearer abc123"));
    }

    @Test
    void supportsApiKeyInHeaderAndQuery() {
        Map<String, Object> headerApiKey = new LinkedHashMap<>();
        headerApiKey.put("name", "X-API-Key");
        headerApiKey.put("value", "k-1");
        headerApiKey.put("in", "header");
        Map<String, Object> headerOpts = new LinkedHashMap<>();
        headerOpts.put("authApiKey", headerApiKey);
        Map<String, Object> headerResp = HTTP.getSync(baseUrl + "/echo", headerOpts);
        assertTrue(String.valueOf(headerResp.get("body")).contains("api=k-1"));

        Map<String, Object> queryApiKey = new LinkedHashMap<>();
        queryApiKey.put("name", "api_key");
        queryApiKey.put("value", "k-2");
        queryApiKey.put("in", "query");
        Map<String, Object> queryOpts = new LinkedHashMap<>();
        queryOpts.put("authApiKey", queryApiKey);
        Map<String, Object> queryResp = HTTP.getSync(baseUrl + "/echo", queryOpts);
        assertTrue(String.valueOf(queryResp.get("body")).contains("query=api_key=k-2"));
    }

    @Test
    void supportsGenericAuthDescriptor() {
        Map<String, Object> auth = new LinkedHashMap<>();
        auth.put("type", "bearer");
        auth.put("token", "from-generic");
        Map<String, Object> opts = new LinkedHashMap<>();
        opts.put("auth", auth);

        Map<String, Object> response = HTTP.getSync(baseUrl + "/echo", opts);
        assertTrue(String.valueOf(response.get("body")).contains("auth=Bearer from-generic"));
    }
}
