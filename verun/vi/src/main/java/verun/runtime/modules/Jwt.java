// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;

public final class Jwt {
    private static final Gson GSON = new GsonBuilder().serializeNulls().create();

    private Jwt() {
    }

    public static String sign(Map<String, Object> payload, String secret, Map<String, Object> options) {
        String algo = optionString(options, "algorithm", "HS256").toUpperCase();
        String jcaAlgo = hmacAlgorithm(algo);

        Map<String, Object> header = new LinkedHashMap<>();
        header.put("alg", algo);
        header.put("typ", "JWT");

        Map<String, Object> finalPayload = new LinkedHashMap<>();
        if (payload != null) {
            finalPayload.putAll(payload);
        }
        applyTemporalClaims(finalPayload, options);
        String issuer = optionString(options, "issuer", "");
        if (!issuer.isEmpty() && !finalPayload.containsKey("iss")) {
            finalPayload.put("iss", issuer);
        }
        String audience = optionString(options, "audience", "");
        if (!audience.isEmpty() && !finalPayload.containsKey("aud")) {
            finalPayload.put("aud", audience);
        }
        String subject = optionString(options, "subject", "");
        if (!subject.isEmpty() && !finalPayload.containsKey("sub")) {
            finalPayload.put("sub", subject);
        }

        String encodedHeader = toBase64UrlJson(header);
        String encodedPayload = toBase64UrlJson(finalPayload);
        String signingInput = encodedHeader + "." + encodedPayload;
        String signature = signHmac(signingInput, secret, jcaAlgo);
        return signingInput + "." + signature;
    }

    public static Map<String, Object> verify(String token, String secret, Map<String, Object> options) {
        try {
            TokenParts parts = parseToken(token);
            Map<String, Object> header = fromJsonBase64Url(parts.header);
            Map<String, Object> payload = fromJsonBase64Url(parts.payload);

            String alg = String.valueOf(header.getOrDefault("alg", "HS256")).toUpperCase();
            String expectedAlg = optionString(options, "algorithm", alg).toUpperCase();
            if (!expectedAlg.equals(alg)) {
                return invalid("Algorithm mismatch", header, payload);
            }

            String expectedSig = signHmac(parts.header + "." + parts.payload, secret, hmacAlgorithm(alg));
            boolean signatureValid = constantTimeEquals(parts.signature, expectedSig);
            if (!signatureValid) {
                return invalid("Invalid signature", header, payload);
            }

            String expectedIssuer = optionString(options, "issuer", "");
            if (!expectedIssuer.isEmpty() && !expectedIssuer.equals(String.valueOf(payload.getOrDefault("iss", "")))) {
                return invalid("Invalid issuer", header, payload);
            }
            String expectedAudience = optionString(options, "audience", "");
            if (!expectedAudience.isEmpty() && !expectedAudience.equals(String.valueOf(payload.getOrDefault("aud", "")))) {
                return invalid("Invalid audience", header, payload);
            }
            String expectedSubject = optionString(options, "subject", "");
            if (!expectedSubject.isEmpty() && !expectedSubject.equals(String.valueOf(payload.getOrDefault("sub", "")))) {
                return invalid("Invalid subject", header, payload);
            }

            long now = Instant.now().getEpochSecond();
            long leeway = optionLong(options, "leewaySeconds", 0L);

            if (payload.containsKey("nbf")) {
                long nbf = toEpochSeconds(payload.get("nbf"));
                if (now + leeway < nbf) {
                    return invalid("Token is not active yet", header, payload);
                }
            }
            if (payload.containsKey("exp")) {
                long exp = toEpochSeconds(payload.get("exp"));
                if (now - leeway >= exp) {
                    return invalid("Token expired", header, payload);
                }
            }

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("valid", true);
            result.put("error", "");
            result.put("header", header);
            result.put("payload", payload);
            result.put("algorithm", alg);
            return result;
        } catch (Exception e) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("valid", false);
            result.put("error", rootMessage(e));
            result.put("header", new LinkedHashMap<>());
            result.put("payload", new LinkedHashMap<>());
            result.put("algorithm", "");
            return result;
        }
    }

    public static Map<String, Object> decode(String token) {
        TokenParts parts = parseToken(token);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("header", fromJsonBase64Url(parts.header));
        result.put("payload", fromJsonBase64Url(parts.payload));
        result.put("signature", parts.signature);
        return result;
    }

    private static void applyTemporalClaims(Map<String, Object> payload, Map<String, Object> options) {
        long now = Instant.now().getEpochSecond();
        if (!payload.containsKey("iat")) {
            payload.put("iat", now);
        }
        long expiresIn = optionLong(options, "expiresInSeconds", 0L);
        if (expiresIn > 0 && !payload.containsKey("exp")) {
            payload.put("exp", now + expiresIn);
        }
        long notBeforeDelay = optionLong(options, "notBeforeSeconds", 0L);
        if (notBeforeDelay > 0 && !payload.containsKey("nbf")) {
            payload.put("nbf", now + notBeforeDelay);
        }
    }

    private static Map<String, Object> invalid(String message, Map<String, Object> header, Map<String, Object> payload) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("valid", false);
        result.put("error", message);
        result.put("header", header == null ? new LinkedHashMap<>() : header);
        result.put("payload", payload == null ? new LinkedHashMap<>() : payload);
        Object alg = header == null ? "" : header.getOrDefault("alg", "");
        result.put("algorithm", String.valueOf(alg));
        return result;
    }

    private static String optionString(Map<String, Object> options, String key, String fallback) {
        if (options == null || !options.containsKey(key) || options.get(key) == null) {
            return fallback;
        }
        String text = String.valueOf(options.get(key)).trim();
        return text.isEmpty() ? fallback : text;
    }

    private static long optionLong(Map<String, Object> options, String key, long fallback) {
        if (options == null || !options.containsKey(key) || options.get(key) == null) {
            return fallback;
        }
        Object value = options.get(key);
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        String text = String.valueOf(value).trim();
        if (text.isEmpty()) {
            return fallback;
        }
        return Long.parseLong(text);
    }

    private static long toEpochSeconds(Object value) {
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        return Long.parseLong(String.valueOf(value));
    }

    private static String toBase64UrlJson(Map<String, Object> value) {
        String json = GSON.toJson(value == null ? new LinkedHashMap<>() : value);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(json.getBytes(StandardCharsets.UTF_8));
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> fromJsonBase64Url(String encoded) {
        byte[] bytes = Base64.getUrlDecoder().decode(encoded);
        String json = new String(bytes, StandardCharsets.UTF_8);
        Object parsed = JsonXml.parseJson(json);
        if (parsed instanceof Map<?, ?>) {
            Map<String, Object> out = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) parsed).entrySet()) {
                if (entry.getKey() == null) {
                    continue;
                }
                out.put(String.valueOf(entry.getKey()), entry.getValue());
            }
            return out;
        }
        return new LinkedHashMap<>();
    }

    private static String signHmac(String input, String secret, String jcaAlgorithm) {
        try {
            Mac mac = Mac.getInstance(jcaAlgorithm);
            mac.init(new SecretKeySpec(String.valueOf(secret == null ? "" : secret).getBytes(StandardCharsets.UTF_8), jcaAlgorithm));
            byte[] sig = mac.doFinal(input.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(sig);
        } catch (Exception e) {
            throw new RuntimeException("JWT signing failed: " + rootMessage(e));
        }
    }

    private static String hmacAlgorithm(String jwtAlg) {
        switch (String.valueOf(jwtAlg).toUpperCase()) {
            case "HS256":
                return "HmacSHA256";
            case "HS384":
                return "HmacSHA384";
            case "HS512":
                return "HmacSHA512";
            default:
                throw new RuntimeException("Unsupported JWT algorithm: " + jwtAlg + " (supported: HS256/HS384/HS512)");
        }
    }

    private static boolean constantTimeEquals(String a, String b) {
        byte[] left = String.valueOf(a == null ? "" : a).getBytes(StandardCharsets.UTF_8);
        byte[] right = String.valueOf(b == null ? "" : b).getBytes(StandardCharsets.UTF_8);
        if (left.length != right.length) {
            return false;
        }
        int out = 0;
        for (int i = 0; i < left.length; i++) {
            out |= left[i] ^ right[i];
        }
        return out == 0;
    }

    private static TokenParts parseToken(String token) {
        String raw = String.valueOf(token == null ? "" : token).trim();
        if (raw.isEmpty()) {
            throw new RuntimeException("Missing JWT token");
        }
        String[] parts = raw.split("\\.");
        if (parts.length != 3) {
            throw new RuntimeException("Invalid JWT format");
        }
        return new TokenParts(parts[0], parts[1], parts[2]);
    }

    private static String rootMessage(Throwable error) {
        Throwable cursor = error;
        while (cursor.getCause() != null) {
            cursor = cursor.getCause();
        }
        String message = cursor.getMessage();
        return message == null || message.trim().isEmpty() ? cursor.getClass().getSimpleName() : message;
    }

    private static final class TokenParts {
        private final String header;
        private final String payload;
        private final String signature;

        private TokenParts(String header, String payload, String signature) {
            this.header = header;
            this.payload = payload;
            this.signature = signature;
        }
    }
}
