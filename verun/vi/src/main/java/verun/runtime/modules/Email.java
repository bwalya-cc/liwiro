// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketException;
import java.nio.charset.StandardCharsets;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public class Email {
    public static Map<String, Object> sendSync(Map<String, Object> options) {
        SMTPConfig cfg = SMTPConfig.from(options);
        List<String> accepted = new ArrayList<>();
        List<String> rejected = new ArrayList<>();
        String messageId = "<" + UUID.randomUUID() + "@vi.local>";

        try (SMTPConnection conn = SMTPConnection.connect(cfg)) {
            conn.expectInitial(220);

            conn.ehlo(cfg.helo);
            if (cfg.startTls && !cfg.ssl) {
                conn.sendExpect("STARTTLS", 220);
                conn.upgradeToTls(cfg.host, cfg.port, cfg.timeoutMs);
                conn.ehlo(cfg.helo);
            }

            if (cfg.auth) {
                conn.sendExpect("AUTH LOGIN", 334);
                conn.sendExpect(base64(cfg.username), 334);
                conn.sendExpect(base64(cfg.password), 235);
            }

            conn.sendExpect("MAIL FROM:<" + cfg.from + ">", 250);
            for (String recipient : cfg.allRecipients()) {
                SMTPResponse rcpt = conn.send("RCPT TO:<" + recipient + ">");
                if (rcpt.code == 250 || rcpt.code == 251) {
                    accepted.add(recipient);
                } else {
                    rejected.add(recipient);
                }
            }
            if (accepted.isEmpty()) {
                throw new RuntimeException("No recipients accepted by SMTP server");
            }

            conn.sendExpect("DATA", 354);
            conn.sendRaw(buildMimeMessage(cfg, messageId) + "\r\n.\r\n");
            conn.expect(250);
            conn.send("QUIT");

            Map<String, Object> data = new LinkedHashMap<>();
            data.put("accepted", accepted);
            data.put("rejected", rejected);
            data.put("message_id", messageId);

            return response(true, "sent", "send_email", "Email sent successfully", data, null, context(cfg));
        } catch (Exception e) {
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("accepted", accepted);
            data.put("rejected", rejected);
            data.put("message_id", messageId);
            return response(false, "error", "send_email", "Email delivery failed", data, rootMessage(e), context(cfg));
        }
    }

    private static String buildMimeMessage(SMTPConfig cfg, String messageId) {
        StringBuilder sb = new StringBuilder();
        sb.append("From: ").append(cfg.from).append("\r\n");
        sb.append("To: ").append(String.join(", ", cfg.to)).append("\r\n");
        if (!cfg.cc.isEmpty()) {
            sb.append("Cc: ").append(String.join(", ", cfg.cc)).append("\r\n");
        }
        sb.append("Subject: ").append(cfg.subject).append("\r\n");
        sb.append("Date: ").append(DateTimeFormatter.RFC_1123_DATE_TIME.format(ZonedDateTime.now(ZoneId.systemDefault())))
                .append("\r\n");
        sb.append("Message-ID: ").append(messageId).append("\r\n");
        sb.append("MIME-Version: 1.0\r\n");

        if (cfg.textBody != null && cfg.htmlBody != null) {
            String boundary = "vi-alt-" + UUID.randomUUID().toString().replace("-", "");
            sb.append("Content-Type: multipart/alternative; boundary=\"").append(boundary).append("\"\r\n");
            sb.append("\r\n");
            sb.append("--").append(boundary).append("\r\n");
            sb.append("Content-Type: text/plain; charset=UTF-8\r\n");
            sb.append("Content-Transfer-Encoding: 8bit\r\n\r\n");
            appendBody(sb, cfg.textBody);
            sb.append("\r\n--").append(boundary).append("\r\n");
            sb.append("Content-Type: text/html; charset=UTF-8\r\n");
            sb.append("Content-Transfer-Encoding: 8bit\r\n\r\n");
            appendBody(sb, cfg.htmlBody);
            sb.append("\r\n--").append(boundary).append("--\r\n");
            return sb.toString();
        }

        if (cfg.htmlBody != null) {
            sb.append("Content-Type: text/html; charset=UTF-8\r\n");
            sb.append("Content-Transfer-Encoding: 8bit\r\n\r\n");
            appendBody(sb, cfg.htmlBody);
            sb.append("\r\n");
            return sb.toString();
        }

        sb.append("Content-Type: text/plain; charset=UTF-8\r\n");
        sb.append("Content-Transfer-Encoding: 8bit\r\n\r\n");
        appendBody(sb, cfg.textBody);
        sb.append("\r\n");
        return sb.toString();
    }

    private static void appendBody(StringBuilder sb, String body) {
        String normalized = body == null ? "" : body.replace("\r\n", "\n").replace("\r", "\n");
        String[] lines = normalized.split("\n", -1);
        for (int i = 0; i < lines.length; i++) {
            String line = lines[i];
            if (line.startsWith(".")) {
                sb.append(".");
            }
            sb.append(line);
            if (i < lines.length - 1) {
                sb.append("\r\n");
            }
        }
    }

    private static String base64(String value) {
        return Base64.getEncoder().encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    private static String rootMessage(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        if (current instanceof SocketException && "Operation not permitted".equals(current.getMessage())) {
            return "SMTP socket blocked by environment permissions";
        }
        String msg = current.getMessage();
        return (msg == null || msg.trim().isEmpty()) ? current.toString() : msg;
    }

    private static Map<String, Object> response(boolean ok, String status, String operation, String message,
            Object data, String error, Map<String, Object> context) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("ok", ok);
        out.put("status", status);
        out.put("operation", operation);
        out.put("message", message);
        out.put("data", data);
        out.put("error", error);
        out.put("context", context);
        return out;
    }

    private static Map<String, Object> context(SMTPConfig cfg) {
        Map<String, Object> ctx = new LinkedHashMap<>();
        ctx.put("host", cfg.host);
        ctx.put("port", cfg.port);
        ctx.put("ssl", cfg.ssl);
        ctx.put("start_tls", cfg.startTls);
        ctx.put("from", cfg.from);
        ctx.put("to_count", cfg.to.size());
        return ctx;
    }

    private static final class SMTPConfig {
        final String host;
        final int port;
        final boolean ssl;
        final boolean startTls;
        final int timeoutMs;
        final boolean auth;
        final String username;
        final String password;
        final String helo;
        final String from;
        final List<String> to;
        final List<String> cc;
        final List<String> bcc;
        final String subject;
        final String textBody;
        final String htmlBody;

        private SMTPConfig(String host, int port, boolean ssl, boolean startTls, int timeoutMs, boolean auth,
                String username, String password, String helo, String from, List<String> to, List<String> cc,
                List<String> bcc, String subject, String textBody, String htmlBody) {
            this.host = host;
            this.port = port;
            this.ssl = ssl;
            this.startTls = startTls;
            this.timeoutMs = timeoutMs;
            this.auth = auth;
            this.username = username;
            this.password = password;
            this.helo = helo;
            this.from = from;
            this.to = to;
            this.cc = cc;
            this.bcc = bcc;
            this.subject = subject;
            this.textBody = textBody;
            this.htmlBody = htmlBody;
        }

        static SMTPConfig from(Map<String, Object> options) {
            Map<String, Object> opts = options == null ? Collections.emptyMap() : options;
            String host = requiredText(opts, "host");
            boolean ssl = asBoolean(opts.get("ssl"), false);
            boolean startTls = asBoolean(opts.get("startTls"), !ssl);

            int portDefault = ssl ? 465 : (startTls ? 587 : 25);
            int port = asInt(opts.get("port"), portDefault);
            int timeoutMs = Math.max(1000, asInt(opts.get("timeoutMs"), 15000));

            String username = text(opts.get("username"));
            String password = text(opts.get("password"));
            boolean auth = asBoolean(opts.get("auth"), username != null && password != null);
            if (auth && (username == null || password == null)) {
                throw new RuntimeException("email.send requires username and password when auth is enabled");
            }

            String helo = text(opts.get("helo"));
            if (helo == null) {
                helo = "localhost";
            }

            String from = requiredText(opts, "from");
            List<String> to = parseRecipients(opts.get("to"));
            if (to.isEmpty()) {
                throw new RuntimeException("email.send requires at least one recipient in 'to'");
            }
            List<String> cc = parseRecipients(opts.get("cc"));
            List<String> bcc = parseRecipients(opts.get("bcc"));

            String subject = text(opts.get("subject"));
            if (subject == null) {
                subject = "";
            }

            String body = text(opts.get("body"));
            String textBody = text(opts.get("text"));
            String htmlBody = text(opts.get("html"));
            if (textBody == null && body != null) {
                textBody = body;
            }
            if (textBody == null && htmlBody == null) {
                throw new RuntimeException("email.send requires body/text or html content");
            }

            return new SMTPConfig(host, port, ssl, startTls, timeoutMs, auth, username, password, helo, from, to,
                    cc, bcc, subject, textBody, htmlBody);
        }

        List<String> allRecipients() {
            List<String> recipients = new ArrayList<>(to);
            recipients.addAll(cc);
            recipients.addAll(bcc);
            return recipients;
        }

        private static List<String> parseRecipients(Object raw) {
            if (raw == null) {
                return Collections.emptyList();
            }
            List<String> out = new ArrayList<>();
            if (raw instanceof List<?>) {
                for (Object item : (List<?>) raw) {
                    String addr = text(item);
                    if (addr != null) {
                        out.add(addr);
                    }
                }
            } else {
                String value = text(raw);
                if (value != null) {
                    String[] parts = value.split(",");
                    for (String part : parts) {
                        String trimmed = part.trim();
                        if (!trimmed.isEmpty()) {
                            out.add(trimmed);
                        }
                    }
                }
            }
            return out;
        }

        private static String requiredText(Map<String, Object> opts, String key) {
            String value = text(opts.get(key));
            if (value == null) {
                throw new RuntimeException("email.send requires '" + key + "'");
            }
            return value;
        }

        private static String text(Object value) {
            if (value == null) {
                return null;
            }
            String asText = String.valueOf(value).trim();
            return asText.isEmpty() ? null : asText;
        }

        private static int asInt(Object value, int fallback) {
            if (value == null) {
                return fallback;
            }
            if (value instanceof Number) {
                return ((Number) value).intValue();
            }
            return Integer.parseInt(String.valueOf(value).trim());
        }

        private static boolean asBoolean(Object value, boolean fallback) {
            if (value == null) {
                return fallback;
            }
            if (value instanceof Boolean) {
                return (Boolean) value;
            }
            String text = String.valueOf(value).trim().toLowerCase();
            if (text.isEmpty()) {
                return fallback;
            }
            return "true".equals(text) || "1".equals(text) || "yes".equals(text) || "on".equals(text);
        }
    }

    private static final class SMTPConnection implements AutoCloseable {
        private Socket socket;
        private BufferedReader reader;
        private BufferedWriter writer;

        private SMTPConnection(Socket socket) throws IOException {
            this.socket = socket;
            this.reader = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
            this.writer = new BufferedWriter(new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8));
        }

        static SMTPConnection connect(SMTPConfig cfg) throws IOException {
            Socket socket;
            if (cfg.ssl) {
                socket = SSLSocketFactory.getDefault().createSocket(cfg.host, cfg.port);
                socket.setSoTimeout(cfg.timeoutMs);
            } else {
                socket = new Socket();
                socket.connect(new InetSocketAddress(cfg.host, cfg.port), cfg.timeoutMs);
                socket.setSoTimeout(cfg.timeoutMs);
            }
            return new SMTPConnection(socket);
        }

        void upgradeToTls(String host, int port, int timeoutMs) throws IOException {
            SSLSocketFactory factory = (SSLSocketFactory) SSLSocketFactory.getDefault();
            SSLSocket sslSocket = (SSLSocket) factory.createSocket(socket, host, port, true);
            sslSocket.setSoTimeout(timeoutMs);
            sslSocket.startHandshake();
            this.socket = sslSocket;
            this.reader = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
            this.writer = new BufferedWriter(new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8));
        }

        void expectInitial(int expectedCode) throws IOException {
            SMTPResponse response = readResponse();
            response.assertCode(expectedCode);
        }

        void ehlo(String helo) throws IOException {
            SMTPResponse ehloResp = send("EHLO " + helo);
            if (ehloResp.code != 250) {
                sendExpect("HELO " + helo, 250);
            }
        }

        SMTPResponse send(String command) throws IOException {
            sendRaw(command + "\r\n");
            return readResponse();
        }

        void sendExpect(String command, int expectedCode) throws IOException {
            SMTPResponse response = send(command);
            response.assertCode(expectedCode);
        }

        void expect(int expectedCode) throws IOException {
            SMTPResponse response = readResponse();
            response.assertCode(expectedCode);
        }

        void sendRaw(String text) throws IOException {
            writer.write(text);
            writer.flush();
        }

        SMTPResponse readResponse() throws IOException {
            String firstLine = reader.readLine();
            if (firstLine == null) {
                throw new RuntimeException("SMTP server closed the connection unexpectedly");
            }
            StringBuilder full = new StringBuilder(firstLine);
            int code = parseCode(firstLine);

            while (firstLine.length() >= 4 && firstLine.charAt(3) == '-') {
                String continuation = reader.readLine();
                if (continuation == null) {
                    break;
                }
                full.append("\n").append(continuation);
                firstLine = continuation;
            }
            return new SMTPResponse(code, full.toString());
        }

        private int parseCode(String line) {
            if (line.length() < 3) {
                throw new RuntimeException("Invalid SMTP response: " + line);
            }
            return Integer.parseInt(line.substring(0, 3));
        }

        @Override
        public void close() throws IOException {
            if (socket != null) {
                socket.close();
            }
        }
    }

    private static final class SMTPResponse {
        final int code;
        final String text;

        private SMTPResponse(int code, String text) {
            this.code = code;
            this.text = text;
        }

        void assertCode(int expected) {
            if (this.code != expected) {
                throw new RuntimeException("SMTP " + expected + " expected but got " + this.code + ": " + this.text);
            }
        }
    }
}
