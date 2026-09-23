// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import org.junit.jupiter.api.Test;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

class EmailModuleTest {

    @Test
    void sendsEmailThroughLocalSmtpServer() throws Exception {
        assumeTrue(localTcpAvailable(), "Local TCP binding is unavailable in this environment");
        try (FakeSmtpServer smtp = new FakeSmtpServer()) {
            smtp.start();

            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("host", "127.0.0.1");
            payload.put("port", smtp.port());
            payload.put("startTls", false);
            payload.put("ssl", false);
            payload.put("auth", false);
            payload.put("from", "sender@example.com");
            payload.put("to", java.util.Collections.singletonList("receiver@example.com"));
            payload.put("subject", "Local SMTP Test");
            payload.put("body", "Hello from test");

            Map<String, Object> result = Email.sendSync(payload);

            assertEquals(true, result.get("ok"));
            assertEquals("sent", result.get("status"));
            assertEquals("send_email", result.get("operation"));
            assertEquals("Email sent successfully", result.get("message"));
            assertTrue(smtp.awaitData(2, TimeUnit.SECONDS), "Expected SMTP DATA payload to be captured");
            String data = smtp.lastData();
            assertNotNull(data);
            assertTrue(data.contains("Subject: Local SMTP Test"));
            assertTrue(data.contains("Hello from test"));
        }
    }

    private static boolean localTcpAvailable() {
        try (ServerSocket probe = new ServerSocket(0)) {
            return true;
        } catch (IOException ignored) {
            return false;
        }
    }

    private static final class FakeSmtpServer implements AutoCloseable {
        private final ServerSocket serverSocket;
        private final AtomicReference<String> lastData = new AtomicReference<>();
        private final CountDownLatch dataLatch = new CountDownLatch(1);
        private Thread worker;

        private FakeSmtpServer() throws IOException {
            this.serverSocket = new ServerSocket(0);
        }

        int port() {
            return serverSocket.getLocalPort();
        }

        void start() {
            worker = new Thread(this::serveOnce, "fake-smtp-server");
            worker.setDaemon(true);
            worker.start();
        }

        boolean awaitData(long timeout, TimeUnit unit) throws InterruptedException {
            return dataLatch.await(timeout, unit);
        }

        String lastData() {
            return lastData.get();
        }

        private void serveOnce() {
            try (Socket socket = serverSocket.accept();
                    BufferedReader in = new BufferedReader(
                            new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
                    BufferedWriter out = new BufferedWriter(
                            new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8))) {
                send(out, "220 fake-smtp ESMTP ready");
                boolean inData = false;
                StringBuilder data = new StringBuilder();
                String line;
                while ((line = in.readLine()) != null) {
                    if (inData) {
                        if (".".equals(line)) {
                            inData = false;
                            lastData.set(data.toString());
                            dataLatch.countDown();
                            send(out, "250 2.0.0 queued");
                            continue;
                        }
                        data.append(line).append("\n");
                        continue;
                    }

                    if (line.startsWith("EHLO") || line.startsWith("HELO")) {
                        send(out, "250-fake-smtp");
                        send(out, "250 AUTH LOGIN");
                    } else if (line.startsWith("MAIL FROM:")) {
                        send(out, "250 2.1.0 OK");
                    } else if (line.startsWith("RCPT TO:")) {
                        send(out, "250 2.1.5 OK");
                    } else if (line.equals("DATA")) {
                        inData = true;
                        send(out, "354 End data with <CR><LF>.<CR><LF>");
                    } else if (line.equals("QUIT")) {
                        send(out, "221 2.0.0 Bye");
                        break;
                    } else if (line.equals("RSET") || line.equals("NOOP")) {
                        send(out, "250 OK");
                    } else {
                        send(out, "250 OK");
                    }
                }
            } catch (IOException ignored) {
                // Best-effort test server; assertion path checks captured DATA.
            } finally {
                dataLatch.countDown();
            }
        }

        private void send(BufferedWriter out, String line) throws IOException {
            out.write(line);
            out.write("\r\n");
            out.flush();
        }

        @Override
        public void close() throws Exception {
            try {
                serverSocket.close();
            } finally {
                if (worker != null) {
                    worker.join(1000);
                }
            }
        }
    }
}
