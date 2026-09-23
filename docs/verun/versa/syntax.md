# Versa Syntax Reference

Last updated: 2026-03-28

This is the practical language reference for writing parser-valid Versa.

## File and session rules

- File extension: `.versa`
- File mode requires statement semicolons.
- REPL and terminal mode still expect parser-valid statements, but the frontend may submit a completed line directly.
- Runtime-provided names may exist in specific environments:
  - service scripts commonly use `params`
  - service scripts may also use `service`

## Statement terminators

Semicolon `;` is required after:

- `let`, `var`, `const`
- assignment statements
- expression statements
- `return`
- `throw`
- import statements

Semicolon is not required after block closers:

- `if / alt / else`
- `for`
- `while`
- `try / catch / else / complete`
- `func { ... }`
- `class { ... }`

Example:

```versa
random import *;

let x = random.randint(1, 10);
if (x > 5) {
    print("high");
} else {
    print("low");
}
```

## Imports

Supported forms:

```versa
vdb import *;
crypto import { uuid };
import random;
```

Use imports at the top of the file before executable code.

If you use a module as a namespace, import it first:

```versa
vdb import *;
let users = vdb.collection("users");
```

## Variables

```versa
let count = 3;
var total = 0;
const appName = "Ella";
```

## Functions

Block form:

```versa
func add(x, y) {
    return x + y;
}
```

Arrow form:

```versa
func add(x, y) => x + y;
```

Lambda style:

```versa
let greet = (name) => { print(`Hello {name}`); };
```

## Classes

Supported features:

- `class`
- optional `extends`
- methods
- optional `static`

## Conditionals

Use `alt`, not `else if`.

```versa
if (score > 90) {
    print("A");
} alt (score > 75) {
    print("B");
} else {
    print("C");
}
```

## Loops

While loop:

```versa
while (count < 3) {
    count += 1;
}
```

C-style `for`:

```versa
for (let i = 0; i < 3; i++) {
    print(i);
}
```

Collection iteration:

```versa
for (item in items) {
    print(item);
}
```

## Exception handling

```versa
try {
    risky();
} catch (err) {
    print(err.message);
} else {
    print("ok");
} complete {
    print("always");
}
```

## Operators

Arithmetic:

- `+`
- `-`
- `*`
- `/`
- `//`
- `%`
- `**`

Comparison:

- `==`
- `!=`
- `<`
- `<=`
- `>`
- `>=`

Logical:

- `&&`
- `||`
- `!`

Bitwise:

- `&`
- `|`
- `^^`
- `~`
- `<<`
- `>>`

Assignment:

- `=`
- `+=`
- `-=`
- `*=`
- `/=`
- `%=`

Other:

- null coalescing: `??`
- ternary: `cond ? a : b`
- postfix increment/decrement: `x++`, `x--`

## Literals

Supported literal families:

- integers
- floats
- strings
- formatted strings
- booleans: `true`, `false`
- `null`
- lists
- objects

Examples:

```versa
let age = 22;
let ratio = 3.14;
let name = "Ella";
let label = `Hello {name}`;
let tags = ["fashion", "inventory"];
let item = {sku: "EFH-001", name: "Linen Dress"};
```

## Objects and member access

These object key styles are accepted:

```versa
{ key: 1 }
{ "key": 1 }
{ 'key': 1 }
```

Equivalent access patterns when the key exists:

```versa
obj.key
obj["key"]
obj['key']
obj[key]
```

## Lists and indexing

```versa
let items = ["a", "b", "c"];
print(items[0]);
print(items[1:]);
print(items[::2]);
print(items[2:0:-1]);

# Slice assignment replaces the selected range and may resize the list.
items[1:2] = ["repaired", "queue"];
items[0:1] = [];
```

Slices use inclusive start/exclusive end bounds; either bound may be omitted,
negative bounds count from the end, and an optional third bound controls the
step (which may be negative but not zero). Slice assignment is supported for
lists and requires a list on the right-hand side. Strings are immutable and
cannot be assigned through a slice. Extended slice assignment with a
non-unit step requires a replacement list of exactly the selected length.

## Comprehensions

Versa supports comprehension syntax for compact derived collections.

List and dictionary comprehensions can iterate lists, sets, maps (by key), and strings. A
string produces one-character string values (not Java character objects), and
an unsupported scalar iterable raises a clear runtime error.

Use it when it stays readable. If the logic becomes hard to scan, prefer an explicit loop.

`for (let key in record) { ... }` iterates object/map keys in insertion order
when the map preserves one. Strings iterate as one-character strings as well.

## Casting and type helpers

Cast functions:

- `int(value)`
- `float(value)`
- `str(value)`
- `bool(value)`

Type helpers:

- `type(value)`
- `is_type(value, expected)`
- `is_unset(identifier)`

Common type labels:

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

## Core built-ins

- `print(...)`
- `input(prompt?)`
- `exit()`
- `exit(code)`
- `range(end)` / `range(start, end)` / `range(start, end, step)`
- `len(value)`
- `leng(value)`
- `join(separator, iterable)`
- `map(lambdaOrCallable, iterable)`
- `filter(predicate, iterable)`
- `any(iterable)` / `all(iterable)`
- `sum(iterable, initial?)`
- `reduce(reducer, iterable, initial?)`

## Common mistakes

- Using `//` for comments instead of `#`
- Using `else if` instead of `alt`
- Forgetting semicolons on statements
- Using a module namespace without importing it
- Putting imports after executable code
- Returning pseudo-code instead of concrete Versa
