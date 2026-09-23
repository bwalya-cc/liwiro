# email Module

## Export
- `send(options)`

## Typical options
- `host`, `port`
- `ssl`, `startTls`
- `auth`, `username`, `password`
- `from`, `to`
- `subject`
- `text` and/or `html`

Returns a normalized response envelope with `ok`, `status`, `message`, and delivery details.
