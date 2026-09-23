# json_xml Module

`parse_xml(...)` returns the structured XML wrapper object (`root`, `name`, `attributes`, `children`, `text`) used by the runtime for XML-aware access.

`xml_to_json(...)` and `xml_to_obj(...)` return plain JSON-like values instead:

- elements with only text become scalars
- `<item>` children collapse to lists
- repeated child tags group into lists
- attributes are exposed under `@attributes`
- mixed text is exposed under `#text`

## JSON
- `parse_json(text)`
- `json_to_obj(text)`
- `obj_to_json(value, pretty=false)`
- `to_json(value, pretty=false)`
- `read_json(path)`
- `write_json(path, value, pretty=false)`

## XML
- `parse_xml(text)`
- `read_xml(path)`
- `write_xml(path, xmlText)`
- `json_to_xml(value, rootName="root")`
- `obj_to_xml(value, rootName="root")`
- `xml_to_json(xmlText)`
- `xml_to_obj(xmlText)`

## Text
- `read_text(path)`
- `write_text(path, text)`

## Demo
- `verun/vi/demo/json_xml/json_xml_module_demo.versa`
