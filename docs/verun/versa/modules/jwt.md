# jwt Module

## Exports
- `sign(payloadObject, secret, options={})`
- `verify(token, secret, options={})`
- `decode(token)`

## Typical options
- `algorithm`: `HS256|HS384|HS512`
- `issuer`, `audience`, `subject`
- `expiresInSeconds`, `notBeforeSeconds`
