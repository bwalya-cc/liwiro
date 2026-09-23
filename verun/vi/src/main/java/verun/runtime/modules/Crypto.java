// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

public final class Crypto {
    private static final SecureRandom RNG = new SecureRandom();

    private Crypto() {
    }

    public static String sha256(String value) {
        return digestHex("SHA-256", value);
    }

    public static String sha512(String value) {
        return digestHex("SHA-512", value);
    }

    public static String hmacSha256(String secret, String message) {
        return hmacHex("HmacSHA256", secret, message);
    }

    public static String hmacSha512(String secret, String message) {
        return hmacHex("HmacSHA512", secret, message);
    }

    public static String base64Encode(String value) {
        byte[] bytes = String.valueOf(value == null ? "" : value).getBytes(StandardCharsets.UTF_8);
        return Base64.getEncoder().encodeToString(bytes);
    }

    public static String base64Decode(String value) {
        try {
            byte[] bytes = Base64.getDecoder().decode(String.valueOf(value == null ? "" : value));
            return new String(bytes, StandardCharsets.UTF_8);
        } catch (Exception e) {
            throw new RuntimeException("crypto.base64_decode failed: " + rootMessage(e));
        }
    }

    public static String base64UrlEncode(String value) {
        byte[] bytes = String.valueOf(value == null ? "" : value).getBytes(StandardCharsets.UTF_8);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    public static String base64UrlDecode(String value) {
        try {
            byte[] bytes = Base64.getUrlDecoder().decode(String.valueOf(value == null ? "" : value));
            return new String(bytes, StandardCharsets.UTF_8);
        } catch (Exception e) {
            throw new RuntimeException("crypto.base64url_decode failed: " + rootMessage(e));
        }
    }

    public static String randomHex(int numBytes) {
        if (numBytes <= 0) {
            throw new RuntimeException("crypto.random_hex expects a positive byte length");
        }
        byte[] bytes = new byte[numBytes];
        RNG.nextBytes(bytes);
        return toHex(bytes);
    }

    public static String randomBytes(int numBytes) {
        if (numBytes <= 0) {
            throw new RuntimeException("crypto.random_bytes expects a positive byte length");
        }
        byte[] bytes = new byte[numBytes];
        RNG.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    public static String uuid() {
        return UUID.randomUUID().toString();
    }

    public static String pbkdf2(String password, String salt, int iterations, int keyLengthBytes, String algorithm) {
        if (iterations <= 0) {
            throw new RuntimeException("crypto.pbkdf2 iterations must be > 0");
        }
        if (keyLengthBytes <= 0) {
            throw new RuntimeException("crypto.pbkdf2 keyLength must be > 0");
        }
        String algo = String.valueOf(algorithm == null ? "HmacSHA256" : algorithm).trim();
        if (algo.isEmpty()) {
            algo = "HmacSHA256";
        }
        String skfAlgo;
        if ("HmacSHA512".equalsIgnoreCase(algo)) {
            skfAlgo = "PBKDF2WithHmacSHA512";
        } else {
            skfAlgo = "PBKDF2WithHmacSHA256";
        }
        try {
            PBEKeySpec spec = new PBEKeySpec(
                    String.valueOf(password == null ? "" : password).toCharArray(),
                    String.valueOf(salt == null ? "" : salt).getBytes(StandardCharsets.UTF_8),
                    iterations,
                    keyLengthBytes * 8
            );
            SecretKeyFactory skf = SecretKeyFactory.getInstance(skfAlgo);
            byte[] key = skf.generateSecret(spec).getEncoded();
            return toHex(key);
        } catch (Exception e) {
            throw new RuntimeException("crypto.pbkdf2 failed: " + rootMessage(e));
        }
    }

    public static Map<String, Object> aesGcmEncrypt(String plaintext, String key, String ivMaybeNull) {
        try {
            byte[] keyBytes = normalizeAesKey(key);
            byte[] ivBytes = ivMaybeNull == null || ivMaybeNull.trim().isEmpty()
                    ? randomIv()
                    : fromBase64Url(ivMaybeNull);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(keyBytes, "AES"), new GCMParameterSpec(128, ivBytes));
            byte[] encrypted = cipher.doFinal(String.valueOf(plaintext == null ? "" : plaintext).getBytes(StandardCharsets.UTF_8));

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("algorithm", "AES/GCM/NoPadding");
            result.put("ciphertext", toBase64Url(encrypted));
            result.put("iv", toBase64Url(ivBytes));
            result.put("tagLength", 128);
            return result;
        } catch (Exception e) {
            throw new RuntimeException("crypto.aes_gcm_encrypt failed: " + rootMessage(e));
        }
    }

    public static String aesGcmDecrypt(String ciphertext, String key, String iv) {
        try {
            byte[] keyBytes = normalizeAesKey(key);
            byte[] ivBytes = fromBase64Url(iv);
            byte[] cipherBytes = fromBase64Url(ciphertext);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(keyBytes, "AES"), new GCMParameterSpec(128, ivBytes));
            byte[] plain = cipher.doFinal(cipherBytes);
            return new String(plain, StandardCharsets.UTF_8);
        } catch (Exception e) {
            throw new RuntimeException("crypto.aes_gcm_decrypt failed: " + rootMessage(e));
        }
    }

    private static String digestHex(String algorithm, String value) {
        try {
            MessageDigest md = MessageDigest.getInstance(algorithm);
            byte[] out = md.digest(String.valueOf(value == null ? "" : value).getBytes(StandardCharsets.UTF_8));
            return toHex(out);
        } catch (Exception e) {
            throw new RuntimeException("crypto digest failed: " + rootMessage(e));
        }
    }

    private static String hmacHex(String algorithm, String secret, String message) {
        try {
            Mac mac = Mac.getInstance(algorithm);
            mac.init(new SecretKeySpec(String.valueOf(secret == null ? "" : secret).getBytes(StandardCharsets.UTF_8), algorithm));
            byte[] out = mac.doFinal(String.valueOf(message == null ? "" : message).getBytes(StandardCharsets.UTF_8));
            return toHex(out);
        } catch (Exception e) {
            throw new RuntimeException("crypto hmac failed: " + rootMessage(e));
        }
    }

    private static byte[] normalizeAesKey(String rawKey) {
        byte[] key = String.valueOf(rawKey == null ? "" : rawKey).getBytes(StandardCharsets.UTF_8);
        if (key.length == 16 || key.length == 24 || key.length == 32) {
            return key;
        }
        // Derive a fixed 32-byte key for caller-provided passphrases.
        try {
            MessageDigest sha = MessageDigest.getInstance("SHA-256");
            return sha.digest(key);
        } catch (Exception e) {
            throw new RuntimeException("crypto key normalization failed: " + rootMessage(e));
        }
    }

    private static byte[] randomIv() {
        byte[] iv = new byte[12];
        RNG.nextBytes(iv);
        return iv;
    }

    private static String toHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }

    private static String toBase64Url(byte[] bytes) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private static byte[] fromBase64Url(String value) {
        try {
            return Base64.getUrlDecoder().decode(String.valueOf(value == null ? "" : value));
        } catch (Exception e) {
            throw new RuntimeException("Invalid base64url input");
        }
    }

    private static String rootMessage(Throwable error) {
        Throwable cursor = error;
        while (cursor.getCause() != null) {
            cursor = cursor.getCause();
        }
        String message = cursor.getMessage();
        return message == null || message.trim().isEmpty() ? cursor.getClass().getSimpleName() : message;
    }
}
