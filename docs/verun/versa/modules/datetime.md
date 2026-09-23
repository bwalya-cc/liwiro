# datetime Module

## Constructors
- `now()`
- `fromtimestamp(ts)`
- `date.today()`
- `date.fromtimestamp(ts)`
- `time.from_components(hour, minute, second, microsecond)`
- `timedelta(value)`
- `timezone(offsetSecondsOrString)` where string is `+HH:MM` or `-HH:MM`

## Value helpers
`datetime`, `date`, `time`, `timedelta` values expose helpers such as:
- `isoformat()`
- `human(format?)`
- `human_readable(format?)`

Timezone values support:
- `human()`
- `human_readable()`
- `isoformat()`

## Typing alias
- `dtf` is an alias for datetime-format strings.

Example:
```versa
let format: dtf = "%A, %d %B %Y %H:%M:%S";
print(datetime.now().human(format));
```
