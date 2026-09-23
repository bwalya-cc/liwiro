# Versa Syntax Rules and Repair Guide

Last updated: 2026-03-28

Use this document when a script fails validation or when you need the shortest path to a correct repair.

## High-priority rules

- Use `#` for single-line comments.
- End statements with `;`.
- Use `alt` for chained conditionals.
- Keep imports at the top of the file.
- Import a module before using `moduleName.member(...)`.
- Prefer explicit, concrete Versa over mixed-language pseudo-code.

## Authoring checklist

Before calling a script valid, confirm:

1. Imports are at the top.
2. Module namespaces are imported before use.
3. Every non-block statement ends with `;`.
4. Conditionals use `if / alt / else`.
5. The script uses real Versa identifiers and operators.
6. Service script runtime names such as `params` or `service` are only used where that runtime exists.

## Parser-facing repair rules

### Missing semicolon

Typical fix:

```versa
let name = "Ella";
return name;
```

### Wrong comment syntax

Wrong:

```versa
// invalid in Versa
let x = 1;
```

Correct:

```versa
# valid in Versa
let x = 1;
```

### Wrong conditional chain

Wrong:

```versa
if (x > 0) {
    print("positive");
} else if (x < 0) {
    print("negative");
}
```

Correct:

```versa
if (x > 0) {
    print("positive");
} alt (x < 0) {
    print("negative");
}
```

### Namespace used without import

Wrong:

```versa
let users = vdb.collection("users");
```

Correct:

```versa
vdb import *;
let users = vdb.collection("users");
```

## String and casting rules

- String concatenation with `+` supports mixed operands.
- String repetition with `*` supports integer counts.
- `int(...)`, `float(...)`, `str(...)`, and `bool(...)` are the standard cast helpers.

Examples:

```versa
let label = "qty " + 3;
let stars = "*" * 5;
let count = int("42");
```

## Object and access rules

- Object keys can be bare identifiers or quoted strings.
- Dot and bracket access are interchangeable when the key exists.

Examples:

```versa
let item = {sku: "EFH-1", name: "Dress"};
print(item.sku);
print(item["name"]);
```

## Type rules

Common runtime labels:

- `int`
- `float`
- `string`
- `bool`
- `null`
- `list`
- `object`
- `function`
- `json`
- `xml`

Useful helpers:

```versa
print(type(42));
print(is_type([1, 2], "list"));
print(is_unset(maybeValue));
```

## Service-script runtime notes

Generated service `versaScript` endpoints commonly rely on runtime names such as:

- `params`
- `service`

These names are valid in the service runtime even if a standalone parse-only or evaluator path would not provide them automatically. Validation should treat them as known ambient names for service scripts, not as proof of bad syntax.

## Validation outcomes to distinguish

- Syntax failure
  Real parser problem. Fix the source.
- Runtime-surface warning
  Missing module import or invalid namespace use.
- Ambient runtime name
  A known provided name such as `params` or `service`; do not misclassify this as a syntax problem for service scripts.

## Common mistakes

- Forgetting the semicolon after a bare `return;` or a value-bearing `return expression;`
- Using `break;` when a control-flow rewrite to a boolean flag is safer in current authoring patterns
- Mixing JavaScript, Python, and Versa syntax in one file
- Calling `vdb`, `crypto`, or `datetime` without imports
- Writing service drafts that assume env/module/runtime objects that were never configured
