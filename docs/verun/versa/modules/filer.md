# filer Module

## Paths and directories
- `join(...parts)`
- `ensure_dir(path)`
- `exists(path)`

## Text/JSON/XML/CSV
- `write_text(path, text)` / `read_text(path)`
- `read_bytes_base64(path)`
- `write_json(path, value, pretty=false)` / `read_json(path)`
- `write_xml(path, xmlText)` / `read_xml(path)`
- `write_csv(path, rows)` / `read_csv(path)` / `read_csv_records(path)`
