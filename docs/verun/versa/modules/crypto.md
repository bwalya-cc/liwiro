# crypto Module

## Hashing and HMAC
- `sha256(text)`
- `sha512(text)`
- `hmac_sha256(secret, message)`
- `hmac_sha512(secret, message)`

## Encoding
- `base64_encode(text)` / `base64_decode(base64)`
- `base64url_encode(text)` / `base64url_decode(base64url)`

## Random and keys
- `random_hex(numBytes)`
- `random_bytes(numBytes)`
- `uuid()`
- `pbkdf2(password, salt, iterations=100000, keyLength=32, algorithm="HmacSHA256")`

## Symmetric encryption
- `aes_gcm_encrypt(plaintext, key, iv?)`
- `aes_gcm_decrypt(ciphertext, key, iv)`
