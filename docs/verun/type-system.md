# Verun Type System

Versa values, VDB schema declarations, and BSON storage are related but distinct. Use this guide when moving data between scripts, generated services, and VDB.

## Versa values

| Value | Common type name | Example |
| --- | --- | --- |
| Integer | `int` | `42` |
| Floating-point number | `float` | `3.14` |
| Boolean | `bool` | `true` |
| String | `str` | `"hello"` |
| List | `list` | `[1, "a", true]` |
| Dictionary | `dict` | `{name: "Alice", age: 30}` |
| Null | `null` | `null` |

Integer literals are parsed with Java `Integer.parseInt`, so do not assume arbitrary precision or 64-bit integer literals. Floating literals use Java doubles. Operations, casts, and values returned from modules can have different numeric representations; verify boundary cases when precision matters.

Runtime aliases include `integer`, `double`/`number`, `string`, `boolean`, `array`, and `map`/`object`. See [Versa syntax](versa/syntax.md) for type checks, casts, classes, collections, and operator behavior.

## VDB schemas

Native VDB collection declarations describe fields with types and optional annotations:

```text
create collection products = {sku: string @required @unique, price: number, active: bool = true};
```

Use model validation to enforce the required data shape. A type name in a schema does not imply that every input string is automatically converted to that type. Test the request shape your application actually sends.

## Storage and transport

VDB stores structured state in BSON. `BsonStorage` recursively normalizes maps and lists, retaining numbers, booleans, strings, and null values. JSON conversion at API boundaries is handled by `verun/vdb/src/main/java/verun/common/JsonValueConverter.java`.

| Application value | Storage or transport consideration |
| --- | --- |
| Integer or floating-point number | Preserve its numeric value; do not assume every JSON number has the same Java subtype |
| Boolean, string, null | Keep the value's type rather than encoding it in a string |
| List | Normalize each element recursively |
| Object/map | Normalize each field recursively |
| Date or binary data | Choose an explicit application representation; BSON support alone does not introduce an `ISODate(...)` literal into VQL |

HTTP responses and export data remain JSON-shaped. JSON clients may lose precision for large integers; test round trips with the clients used by your service.

## Practical rules

- Keep identifiers as strings when arithmetic is not intended.
- Use documented Versa syntax, including `#` comments and imports before module calls.
- Check nulls and missing fields before arithmetic or member access.
- Validate schema changes against existing documents before changing service models.
- Test numeric boundaries and serialization round trips when integrating VI, VDB, and JSON clients.
