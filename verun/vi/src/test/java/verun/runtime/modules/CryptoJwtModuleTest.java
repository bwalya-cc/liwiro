// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import org.junit.jupiter.api.Test;

import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

public class CryptoJwtModuleTest {

    @Test
    void hashesAndEncodesDeterministically() {
        assertEquals("9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08", Crypto.sha256("test"));
        String b64 = Crypto.base64Encode("hello");
        assertEquals("hello", Crypto.base64Decode(b64));
        assertFalse(Crypto.randomHex(8).isEmpty());
        assertFalse(Crypto.randomBytes(8).isEmpty());
    }

    @Test
    void encryptsAndDecryptsWithAesGcm() {
        Map<String, Object> encrypted = Crypto.aesGcmEncrypt("payload", "demo-key", null);
        String ciphertext = String.valueOf(encrypted.get("ciphertext"));
        String iv = String.valueOf(encrypted.get("iv"));
        String plaintext = Crypto.aesGcmDecrypt(ciphertext, "demo-key", iv);
        assertEquals("payload", plaintext);
    }

    @Test
    void signsAndVerifiesJwt() {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("sub", "alice");
        payload.put("role", "SUPER_ADMIN");

        Map<String, Object> signOptions = new LinkedHashMap<>();
        signOptions.put("algorithm", "HS256");
        signOptions.put("expiresInSeconds", 60);
        signOptions.put("issuer", "AuthCoreService");

        String token = Jwt.sign(payload, "secret-123", signOptions);
        assertEquals(3, token.split("\\.").length);

        Map<String, Object> verifyOptions = new LinkedHashMap<>();
        verifyOptions.put("algorithm", "HS256");
        verifyOptions.put("issuer", "AuthCoreService");

        Map<String, Object> verified = Jwt.verify(token, "secret-123", verifyOptions);
        assertEquals(true, verified.get("valid"));

        Map<String, Object> claims = (Map<String, Object>) verified.get("payload");
        assertEquals("alice", String.valueOf(claims.get("sub")));

        Map<String, Object> failed = Jwt.verify(token, "wrong-secret", verifyOptions);
        assertEquals(false, failed.get("valid"));
    }
}
