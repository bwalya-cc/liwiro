# Versa Module Reference

Last updated: 2026-03-28

This is the module index for runtime-injected Versa modules.

## Import forms

All modules use one of these patterns:

```versa
module import *;
module import { thingA, thingB };
import module;
```

Use imports before executable code.

## Module list

### `http`

Purpose:

- outbound HTTP calls

Main entry points:

- `http.request(method, url, options={})`
- `http.get(url, options={})`
- `http.post(url, options={})`
- `http.put(url, options={})`
- `http.patch(url, options={})`
- `http.delete(url, options={})`

Important inputs:

- `headers`
- `query`
- `body`
- `timeoutSeconds`
- auth helpers

Output shape:

- structured response object with status/body metadata

### `json_xml`

Purpose:

- JSON parsing and serialization
- XML parsing and transformation
- text file helpers

Common functions:

- `json_xml.parse_json(text)`
- `json_xml.json_to_obj(text)`
- `json_xml.to_json(value, pretty=false)`
- `json_xml.parse_xml(text)`
- `json_xml.xml_to_json(xmlText)`
- `json_xml.xml_to_obj(xmlText)`
- `json_xml.read_json(path)`
- `json_xml.write_json(path, value, pretty=false)`
- `json_xml.read_text(path)`
- `json_xml.write_text(path, text)`

### `email`

Purpose:

- SMTP email sending

Common function:

- `email.send(options)`

Common inputs:

- `host`
- `port`
- `from`
- `to`
- `text`
- `html`
- `username`
- `password`
- `ssl`
- `startTls`

Output shape:

- structured result with status and delivery metadata

### `crypto`

Purpose:

- hashing
- HMAC
- encoding helpers
- UUID and random bytes
- key derivation
- encryption helpers

Common functions:

- `crypto.sha256(text)`
- `crypto.hmac_sha256(secret, message)`
- `crypto.base64_encode(text)`
- `crypto.random_hex(numBytes)`
- `crypto.uuid()`
- `crypto.pbkdf2(password, salt, iterations=100000, keyLength=32, algorithm="HmacSHA256")`

### `jwt`

Purpose:

- JWT signing, verification, and decoding

Common functions:

- `jwt.sign(payloadObject, secret, options={})`
- `jwt.verify(token, secret, options={})`
- `jwt.decode(token)`

Common algorithms:

- `HS256`
- `HS384`
- `HS512`

### `time`

Purpose:

- low-level time helpers

Common functions:

- `time.time()`
- `time.time_ns()`
- `time.sleep(seconds)`
- `time.localtime(timestamp?)`
- `time.gmtime(timestamp?)`
- `time.strftime(format, timeStruct?)`

### `datetime`

Purpose:

- higher-level date and time objects

Common functions:

- `datetime.now()`
- `datetime.fromtimestamp(ts)`
- `datetime.date.today()`
- `datetime.time.from_components(h, m, s, micro)`
- `datetime.timedelta(value)`
- `datetime.timezone(offset)`

Common output:

- date/time objects with formatting and helper methods

### `random`

Purpose:

- scalar randomness
- choices and samples

Common functions:

- `random.seed(value?)`
- `random.random()`
- `random.randint(min, max)`
- `random.choice(list)`
- `random.shuffle(list)`
- `random.sample(list, count)`
- `random.boolean()`

### `filer`

Purpose:

- filesystem convenience helpers

Common functions:

- `filer.join(...parts)`
- `filer.ensure_dir(path)`
- `filer.exists(path)`
- `filer.write_text(path, text)`
- `filer.read_text(path)`
- `filer.write_json(path, value, pretty=false)`
- `filer.read_json(path)`
- `filer.write_csv(path, rows)`
- `filer.read_csv(path)`

## Special case: `vdb`

The `vdb` bridge is documented separately in `docs/verun/versa/vdb-module.md` because it is partly evaluator-driven and runtime-context-sensitive.

## Common mistakes

- using module namespaces without importing them
- placing imports after executable code
- assuming module functions return plain strings when they actually return structured objects
- using `vdb` behavior without reading the dedicated bridge reference first
