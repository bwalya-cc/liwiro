# http Module

## Exports
- `request(method, url, options={})`
- `get(url, options={})`
- `post(url, options={})`
- `put(url, options={})`
- `patch(url, options={})`
- `delete(url, options={})`

## Common options
- `headers`: object
- `query`: object
- `body`: object/list/string/scalar
- `form`: object for `application/x-www-form-urlencoded` bodies
- `bodyBytesBase64`: base64 string decoded into raw request bytes
- `timeoutSeconds`: number
- auth helpers: `authHeader`, `authBearer`, `authBasic`, `authOAuth2`, `authApiKey`, `auth`
