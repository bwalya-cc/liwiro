# Verun Type System

This document explains the data types supported in the **Verun ecosystem**, including:

1. **Versa (VI)** - The scripting language/runtime
2. **VersaDB (VDB)** - The document database
3. **Type Conversion Rules** between systems

---

## 1. Versa (VI) Types

| Type             | Keyword    | Description                          | Example                     |
|------------------|------------|--------------------------------------|-----------------------------|
| Integer          | `int`      | 64-bit signed integer                | `42`, `-15`                 |
| Float            | `float`    | 64-bit floating point                | `3.14`, `-0.5e10`           |
| Boolean          | `bool`     | Logical true/false                   | `true`, `false`             |
| String           | `str`      | UTF-8 character sequence             | `"hello"`, `'world'`        |
| List             | `list`     | Ordered collection                   | `[1, "a", true]`            |
| Dictionary       | `dict`     | Key-value pairs                      | `{"name": "Alice", "age": 30}` |
| Null             | `null`     | Explicit absence of value            | `null`                      |

Accepted runtime aliases also include:

- `integer` -> `int`
- `double` / `number` -> `float`
- `string` -> `str`
- `boolean` -> `bool`
- `array` -> `list`
- `map` / `object` -> `dict`
- `any` -> flexible match

---

## 2. VersaDB (VDB) Storage Types

VDB stores structured internal state under `verun/vdb/__data__` using BSON-backed records and logs. External APIs and export artifacts remain JSON-shaped where appropriate.

| Type       | BSON Type    | Description                  | Example                     |
|------------|--------------|------------------------------|-----------------------------|
| Number     | Double/Int32 | Auto-detected numeric type   | `42`, `3.1415`              |
| Boolean    | Boolean      | Logical value                | `true`, `false`             |
| String     | String       | UTF-8 string                 | `"hello world"`             |
| Array      | Array        | Ordered list                 | `[1, "a", true]`            |
| Object     | Document     | Key-value collection         | `{"_id": "abc", "count": 5}`|
| Null       | Null         | Empty value                  | `null`                      |
| Date       | DateTime     | ISO date                     | `ISODate("2023-09-15")`     |
| Binary     | BinData      | Raw binary data              | `<Hex representation>`      |

---

## 3. Type Conversion Rules

### VI → VDB Conversion

**Conversion Table**

| VI Type      | VDB Storage          | Conversion Logic                          |
|---------------|----------------------|-------------------------------------------|
| `int`         | Number (Int32)       | Direct mapping                            |
| `float`       | Number (Double)      | Direct mapping                            |
| Other types   | Direct equivalent    | 1:1 mapping (bool, list, dict, etc.)      |

### VDB → VI Conversion

**Key Conversion Classes**
```java
// Core conversion component
vdb/src/main/java/verun/vdb/TypeConverter.java
```

---

## 4. Best Practices

1. **For Cross-Platform Data**
   ```verun
   // Prefer portable types
   let data = {
     id: 123,                 // int → Number
     name: "Widget",          // str → String
     prices: [4.99, 9.99],    // list → Array
     meta: {                  // dict → Document
       in_stock: true
     }
   }
   ```

2. **Type Checking**
   ```verun
   // Use built-in type checks
   if (typeof value == 'int') {
     // Handle integer logic
   }
   ```

---

*Document version 2.2 - Updated 2026-03-22*
