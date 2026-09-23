# VI Datetime Custom Formatting

Use `%`-style datetime tokens with `datetime` value helpers.

## Example
```versa
datetime import *;

let format: dtf = "%A, %d %B %Y %H:%M:%S";
print(datetime.now().human(format));

let tz = datetime.timezone("+02:00");
print(tz.human());
```

## Common format tokens
- `%Y` year (4-digit)
- `%m` month (01-12)
- `%d` day (01-31)
- `%H` hour 24h (00-23)
- `%M` minute (00-59)
- `%S` second (00-59)
- `%A` full weekday name
- `%a` short weekday name
- `%B` full month name
- `%b` short month name
- `%I` hour 12h
- `%p` AM/PM
- `%z` UTC offset
- `%Z` zone name
- `%f` microseconds
